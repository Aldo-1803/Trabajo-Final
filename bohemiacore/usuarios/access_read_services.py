from collections import defaultdict

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .roles import BusinessPermission, BusinessRole, ROLE_BASE_PERMISSIONS


ACCESS_ADMIN_PERMISSIONS = (
    BusinessPermission.MANAGE_USERS,
    BusinessPermission.ASSIGN_ROLES,
    BusinessPermission.MANAGE_PERSONAL,
    BusinessPermission.VIEW_AUDIT,
    BusinessPermission.REVERT_AUDIT,
)


def _permission_code(permission):
    return f'{permission.content_type.app_label}.{permission.codename}'


def _warning(code, message, **details):
    warning = {'code': code, 'message': message}
    warning.update(details)
    return warning


def _origin_sort_key(origin):
    origin_type = origin['type']
    type_order = {
        'BUSINESS_ROLE': 0,
        'TECHNICAL_GROUP': 1,
        'INDIVIDUAL': 2,
        'SUPERUSER': 3,
    }
    identifier = origin.get('identifier')
    if origin_type == 'BUSINESS_ROLE':
        identifier_order = BusinessRole.ALL.index(identifier)
    else:
        identifier_order = identifier or ''
    return type_order[origin_type], identifier_order


def _profile_summary(user):
    cliente = getattr(user, 'cliente', None)
    personal = getattr(user, 'perfil_profesional', None)
    return {
        'cliente': {
            'exists': cliente is not None,
            'id': cliente.pk if cliente is not None else None,
            'active': cliente.activo if cliente is not None else None,
        },
        'personal': {
            'exists': personal is not None,
            'id': personal.pk if personal is not None else None,
            'active': personal.activo if personal is not None else None,
            'job_role': personal.rol if personal is not None else None,
        },
    }


def build_administrative_access_summary(user):
    """Build a deterministic, read-only projection of Django access state.

    A fresh Usuario instance is loaded intentionally. Django memoizes permission
    checks on model instances, and an administrative read must not reuse stale
    `_perm_cache`, `_user_perm_cache` or `_group_perm_cache` values.
    """
    user_model = get_user_model()
    if not isinstance(user, user_model) or user.pk is None:
        raise ValueError('A persisted Usuario is required.')

    target = user_model.objects.select_related(
        'cliente',
        'perfil_profesional',
    ).get(pk=user.pk)
    groups = list(
        Group.objects.filter(user=target)
        .prefetch_related('permissions__content_type')
        .order_by('name', 'pk')
    )
    direct_permissions = list(
        target.user_permissions.select_related('content_type').order_by(
            'content_type__app_label',
            'codename',
            'pk',
        )
    )

    catalog = tuple(BusinessPermission.ALL)
    catalog_set = set(catalog)
    roles = tuple(
        role
        for role in BusinessRole.ALL
        if any(group.name == role for group in groups)
    )
    business_role = roles[0] if len(roles) == 1 else None
    role_state = (
        'NO_ROLE'
        if not roles
        else 'MULTIPLE_ROLES'
        if len(roles) > 1
        else 'VALID'
    )

    origins = defaultdict(list)
    assigned_catalog = set()
    role_catalog = set()
    technical_group_catalog = set()
    outside_catalog = set()
    outside_source_types = set()
    technical_group_details = {}

    for group in groups:
        is_business_role = group.name in BusinessRole.ALL
        source_type = 'BUSINESS_ROLE' if is_business_role else 'TECHNICAL_GROUP'
        group_catalog = set()
        for permission in group.permissions.all():
            code = _permission_code(permission)
            if code not in catalog_set:
                outside_catalog.add(code)
                outside_source_types.add(source_type)
                continue
            group_catalog.add(code)
            assigned_catalog.add(code)
            origins[code].append({
                'type': source_type,
                'identifier': group.name,
            })

        if is_business_role:
            role_catalog.update(group_catalog)
        elif group_catalog:
            technical_group_catalog.update(group_catalog)
            technical_group_details[group.name] = tuple(
                code for code in catalog if code in group_catalog
            )

    individual_catalog = set()
    for permission in direct_permissions:
        code = _permission_code(permission)
        if code not in catalog_set:
            outside_catalog.add(code)
            outside_source_types.add('INDIVIDUAL')
            continue
        individual_catalog.add(code)
        assigned_catalog.add(code)
        origins[code].append({
            'type': 'INDIVIDUAL',
            'identifier': None,
        })

    # This is Django's effective contract. An inactive user receives no
    # permissions, while an active superuser receives every registered
    # permission. Intersecting with the canonical catalog avoids publishing
    # arbitrary Django permissions as an editable capability catalog.
    effective_catalog = set(target.get_all_permissions()) & catalog_set
    if target.is_active and target.is_superuser:
        for code in effective_catalog:
            origins[code].append({
                'type': 'SUPERUSER',
                'identifier': None,
            })

    capabilities = []
    for code in catalog:
        assigned = code in assigned_catalog
        effective = code in effective_catalog
        if not assigned and not effective:
            continue
        capabilities.append({
            'code': code,
            'assigned': assigned,
            'effective': effective,
            'origins': sorted(origins[code], key=_origin_sort_key),
        })

    expected_catalog = set()
    for role in roles:
        expected_catalog.update(ROLE_BASE_PERMISSIONS[role])

    profiles = _profile_summary(target)
    warnings = []
    if role_state == 'NO_ROLE':
        warnings.append(_warning(
            'NO_ROLE',
            'La cuenta no tiene un BusinessRole canónico asignado.',
        ))
    elif role_state == 'MULTIPLE_ROLES':
        warnings.append(_warning(
            'MULTIPLE_ROLES',
            'La cuenta tiene múltiples BusinessRoles canónicos.',
            roles=list(roles),
        ))

    if BusinessRole.CLIENTE in roles and not profiles['cliente']['exists']:
        warnings.append(_warning(
            'MISSING_CLIENT_PROFILE',
            'El rol CLIENTE requiere un perfil Cliente.',
        ))

    labor_roles = tuple(
        role
        for role in roles
        if role in (BusinessRole.EMPLEADO, BusinessRole.PROFESIONAL)
    )
    if labor_roles and not profiles['personal']['exists']:
        warnings.append(_warning(
            'MISSING_PERSONAL_PROFILE',
            'El rol laboral requiere un perfil Personal vinculado.',
            roles=list(labor_roles),
        ))
    elif labor_roles and not profiles['personal']['active']:
        warnings.append(_warning(
            'INACTIVE_PERSONAL_FOR_LABOR_ROLE',
            'El BusinessRole laboral está vinculado a Personal inactivo.',
            roles=list(labor_roles),
        ))

    missing_role_capabilities = tuple(
        code for code in catalog if code in expected_catalog - role_catalog
    )
    unexpected_role_capabilities = tuple(
        code for code in catalog if code in role_catalog - expected_catalog
    )
    if missing_role_capabilities or unexpected_role_capabilities:
        warnings.append(_warning(
            'ROLE_CAPABILITY_DRIFT',
            'Los permisos reales del grupo de rol difieren de su contrato base.',
            missing=list(missing_role_capabilities),
            unexpected=list(unexpected_role_capabilities),
        ))

    observed_admin = assigned_catalog | effective_catalog
    residual_admin = tuple(
        code
        for code in ACCESS_ADMIN_PERMISSIONS
        if code in observed_admin and code not in expected_catalog
    )
    if residual_admin:
        warnings.append(_warning(
            'ADMIN_CAPABILITIES_OUTSIDE_ROLE',
            'La cuenta conserva capacidades administrativas fuera de su rol.',
            capabilities=list(residual_admin),
            effective_capabilities=[
                code for code in residual_admin if code in effective_catalog
            ],
        ))

    if individual_catalog:
        warnings.append(_warning(
            'INDIVIDUAL_BUSINESS_PERMISSIONS',
            'La cuenta tiene capacidades de negocio asignadas individualmente.',
            capabilities=[
                code for code in catalog if code in individual_catalog
            ],
        ))

    if technical_group_catalog:
        warnings.append(_warning(
            'TECHNICAL_GROUP_BUSINESS_PERMISSIONS',
            'Grupos técnicos aportan capacidades de negocio a la cuenta.',
            groups=[
                {
                    'name': group_name,
                    'capabilities': list(technical_group_details[group_name]),
                }
                for group_name in sorted(technical_group_details)
            ],
        ))

    if outside_catalog:
        warnings.append(_warning(
            'PERMISSIONS_OUTSIDE_BUSINESS_CATALOG',
            'Existen permisos Django asignados fuera del catálogo de negocio.',
            count=len(outside_catalog),
            source_types=sorted(outside_source_types),
        ))

    if not target.is_active and assigned_catalog:
        warnings.append(_warning(
            'INACTIVE_ACCOUNT_CAPABILITIES_NOT_EFFECTIVE',
            'La cuenta conserva asignaciones, pero Django no las hace efectivas mientras esté inactiva.',
            capabilities=[
                code for code in catalog if code in assigned_catalog
            ],
        ))

    if target.is_superuser:
        warnings.append(_warning(
            'SUPERUSER_ACCOUNT',
            'La cuenta usa el bypass técnico de superusuario de Django.',
            effective=target.is_active,
        ))

    return {
        'identity': {
            'id': target.pk,
            'email': target.email,
            'first_name': target.first_name,
            'last_name': target.last_name,
        },
        'account': {
            'is_active': target.is_active,
            'is_staff': target.is_staff,
            'is_superuser': target.is_superuser,
        },
        'business_role': business_role,
        'business_roles': list(roles),
        'role_state': role_state,
        'profiles': profiles,
        'assigned_capabilities': [
            code for code in catalog if code in assigned_catalog
        ],
        'effective_capabilities': [
            code for code in catalog if code in effective_catalog
        ],
        'capabilities': capabilities,
        'warnings': warnings,
        'technical': {
            'permission_evaluation': (
                'EFFECTIVE'
                if target.is_active
                else 'SUPPRESSED_INACTIVE_ACCOUNT'
            ),
            'has_individual_business_permissions': bool(individual_catalog),
            'has_technical_group_business_permissions': bool(
                technical_group_catalog
            ),
            'has_permissions_outside_business_catalog': bool(outside_catalog),
        },
    }
