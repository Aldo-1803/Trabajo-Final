import hashlib
import json
from types import MappingProxyType

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction


class BusinessRole:
    CLIENTE = 'CLIENTE'
    EMPLEADO = 'EMPLEADO'
    PROFESIONAL = 'PROFESIONAL'
    ADMINISTRADOR = 'ADMINISTRADOR'

    ALL = (CLIENTE, EMPLEADO, PROFESIONAL, ADMINISTRADOR)


class BusinessPermission:
    CREATE_WALKIN_CLIENT = 'usuarios.create_walkin_client'
    VIEW_CLIENTS = 'usuarios.view_clients'
    MANAGE_USERS = 'usuarios.manage_users'
    ASSIGN_ROLES = 'usuarios.assign_roles'

    VIEW_GLOBAL_AGENDA = 'gestion.view_global_agenda'
    CREATE_TURNO_FOR_CLIENT = 'gestion.create_turno_for_client'
    REGISTER_ARRIVAL = 'gestion.register_arrival'
    REPROGRAM_ANY_TURNO = 'gestion.reprogram_any_turno'
    CANCEL_ANY_TURNO = 'gestion.cancel_any_turno'
    FINALIZE_SERVICE = 'gestion.finalize_service'
    CONFIRM_DEPOSIT = 'gestion.confirm_deposit'
    REGISTER_PAYMENT = 'gestion.register_payment'
    RECONCILE_EXTERNAL_PAYMENT = 'gestion.reconcile_external_payment'
    MANAGE_PAYMENT_CONFIGURATION = 'gestion.manage_payment_configuration'
    CREATE_DIAGNOSIS = 'gestion.create_diagnosis'
    MANAGE_TECHNICAL_RECORD = 'gestion.manage_technical_record'
    MANAGE_FORMULAS = 'gestion.manage_formulas'
    ASSIGN_ROUTINES = 'gestion.assign_routines'
    MANAGE_PRODUCTS = 'gestion.manage_products'
    VIEW_STOCK = 'gestion.view_stock'
    MANAGE_STOCK = 'gestion.manage_stock'
    MANAGE_PRICES = 'gestion.manage_prices'
    MANAGE_PROMOTIONS = 'gestion.manage_promotions'
    MANAGE_CONTENT = 'gestion.manage_content'
    MANAGE_PERSONAL = 'gestion.manage_personal'
    MANAGE_SKILLS = 'gestion.manage_skills'
    REVIEW_TECHNICAL_BOOKING = 'gestion.review_technical_booking'
    MANAGE_TECHNICAL_RISK_POLICY = 'gestion.manage_technical_risk_policy'
    VIEW_REPORTS = 'gestion.view_reports'
    VIEW_FINANCIAL_REPORTS = 'gestion.view_financial_reports'
    VIEW_AUDIT = 'gestion.view_audit'
    REVERT_AUDIT = 'gestion.revert_audit'
    MANAGE_CONFIGURATION = 'gestion.manage_configuration'

    ALL = (
        CREATE_WALKIN_CLIENT,
        VIEW_CLIENTS,
        MANAGE_USERS,
        ASSIGN_ROLES,
        VIEW_GLOBAL_AGENDA,
        CREATE_TURNO_FOR_CLIENT,
        REGISTER_ARRIVAL,
        REPROGRAM_ANY_TURNO,
        CANCEL_ANY_TURNO,
        FINALIZE_SERVICE,
        CONFIRM_DEPOSIT,
        REGISTER_PAYMENT,
        RECONCILE_EXTERNAL_PAYMENT,
        MANAGE_PAYMENT_CONFIGURATION,
        CREATE_DIAGNOSIS,
        MANAGE_TECHNICAL_RECORD,
        MANAGE_FORMULAS,
        ASSIGN_ROUTINES,
        MANAGE_PRODUCTS,
        VIEW_STOCK,
        MANAGE_STOCK,
        MANAGE_PRICES,
        MANAGE_PROMOTIONS,
        MANAGE_CONTENT,
        MANAGE_PERSONAL,
        MANAGE_SKILLS,
        REVIEW_TECHNICAL_BOOKING,
        MANAGE_TECHNICAL_RISK_POLICY,
        VIEW_REPORTS,
        VIEW_FINANCIAL_REPORTS,
        VIEW_AUDIT,
        REVERT_AUDIT,
        MANAGE_CONFIGURATION,
    )


EMPLOYEE_BASE_PERMISSIONS = (
    BusinessPermission.CREATE_WALKIN_CLIENT,
    BusinessPermission.VIEW_CLIENTS,
    BusinessPermission.VIEW_GLOBAL_AGENDA,
    BusinessPermission.CREATE_TURNO_FOR_CLIENT,
    BusinessPermission.REGISTER_ARRIVAL,
    BusinessPermission.REPROGRAM_ANY_TURNO,
    BusinessPermission.CANCEL_ANY_TURNO,
    BusinessPermission.REGISTER_PAYMENT,
    BusinessPermission.VIEW_STOCK,
)

PROFESSIONAL_BASE_PERMISSIONS = tuple(
    permission
    for permission in EMPLOYEE_BASE_PERMISSIONS
    if permission != BusinessPermission.REGISTER_PAYMENT
) + (
    BusinessPermission.CREATE_DIAGNOSIS,
    BusinessPermission.MANAGE_TECHNICAL_RECORD,
    BusinessPermission.MANAGE_FORMULAS,
    BusinessPermission.ASSIGN_ROUTINES,
    BusinessPermission.FINALIZE_SERVICE,
    BusinessPermission.REVIEW_TECHNICAL_BOOKING,
)

ROLE_CAPABILITY_CONTRACT_V1 = 'bh061-role-capabilities-v1'
ROLE_CAPABILITY_CONTRACT_VERSION = ROLE_CAPABILITY_CONTRACT_V1
ROLE_CAPABILITY_FINGERPRINT_ALGORITHM = 'sha256'
ROLE_CAPABILITY_FINGERPRINT_ENCODING = 'json-utf8-sorted-unique-v1'

_ROLE_CAPABILITY_CONTRACT_V1 = MappingProxyType({
    BusinessRole.CLIENTE: (),
    BusinessRole.EMPLEADO: tuple(EMPLOYEE_BASE_PERMISSIONS),
    BusinessRole.PROFESIONAL: tuple(PROFESSIONAL_BASE_PERMISSIONS),
    BusinessRole.ADMINISTRADOR: tuple(BusinessPermission.ALL),
})

# Published contracts are append-only. A capability change must add a new
# immutable snapshot and update ROLE_CAPABILITY_CONTRACT_VERSION; v1 must not
# be edited in place.
ROLE_CAPABILITY_CONTRACTS = MappingProxyType({
    ROLE_CAPABILITY_CONTRACT_V1: _ROLE_CAPABILITY_CONTRACT_V1,
})

ROLE_CAPABILITY_CONTRACT_FINGERPRINTS = MappingProxyType({
    ROLE_CAPABILITY_CONTRACT_V1: MappingProxyType({
        BusinessRole.CLIENTE: (
            '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'
        ),
        BusinessRole.EMPLEADO: (
            '50e04a16d3ae0b6bd98b4b2ca2febb3f57d00165bb7e75fb7e890f16e579e58f'
        ),
        BusinessRole.PROFESIONAL: (
            '1af6d25083401d4b4624047fc4674eea00a4b6fd2540f3e35c941382cb51fb4a'
        ),
        BusinessRole.ADMINISTRADOR: (
            '8d700df9707ad7c16d82cf01ca310e6da43a3bb57af6dd26ec95aef265a4b3da'
        ),
    }),
})


def fingerprint_business_permissions(permissions):
    """Fingerprint a permission set using canonical JSON encoded as UTF-8."""
    if isinstance(permissions, str):
        raise TypeError('Permissions must be an iterable of permission codes.')

    canonical_permissions = tuple(sorted(set(permissions)))
    if not all(
        isinstance(permission, str) and permission
        for permission in canonical_permissions
    ):
        raise ValueError('Permission codes must be non-empty strings.')

    canonical_json = json.dumps(
        canonical_permissions,
        ensure_ascii=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def get_business_role_permissions_fingerprint(
    role,
    *,
    version=ROLE_CAPABILITY_CONTRACT_VERSION,
):
    """Return the published capability fingerprint for one role or None."""
    if role is None:
        return None
    try:
        contract = ROLE_CAPABILITY_CONTRACTS[version]
    except KeyError as exc:
        raise ValueError(f'Unknown role capability contract: {version}') from exc
    if role not in contract:
        raise ValueError(f'Unknown business role: {role}')
    return fingerprint_business_permissions(contract[role])


def build_business_role_audit_metadata(
    previous_role,
    new_role,
    *,
    version=ROLE_CAPABILITY_CONTRACT_VERSION,
):
    """Build versioned capability metadata for an effective role mutation."""
    if new_role is None:
        raise ValueError('A new business role is required for audit metadata.')
    return {
        'role_contract_version': version,
        'previous_role_permissions_fingerprint': (
            get_business_role_permissions_fingerprint(
                previous_role,
                version=version,
            )
        ),
        'new_role_permissions_fingerprint': (
            get_business_role_permissions_fingerprint(
                new_role,
                version=version,
            )
        ),
    }


def _validate_published_role_capability_contracts():
    for version, expected_fingerprints in (
        ROLE_CAPABILITY_CONTRACT_FINGERPRINTS.items()
    ):
        contract = ROLE_CAPABILITY_CONTRACTS[version]
        if tuple(contract) != BusinessRole.ALL:
            raise RuntimeError(
                f'Role capability contract {version} has an invalid role set.'
            )
        actual_fingerprints = {
            role: fingerprint_business_permissions(contract[role])
            for role in BusinessRole.ALL
        }
        if actual_fingerprints != dict(expected_fingerprints):
            raise RuntimeError(
                f'Published role capability contract {version} was modified. '
                'Publish a new version instead.'
            )


_validate_published_role_capability_contracts()

ROLE_BASE_PERMISSIONS = ROLE_CAPABILITY_CONTRACTS[
    ROLE_CAPABILITY_CONTRACT_VERSION
]


class InconsistentBusinessRoleError(ValueError):
    pass


def get_business_role_groups():
    return Group.objects.filter(name__in=BusinessRole.ALL)


def get_business_roles(user):
    if not getattr(user, 'is_authenticated', False):
        return ()

    assigned_roles = set(
        user.groups.filter(name__in=BusinessRole.ALL).values_list(
            'name', flat=True
        )
    )
    return tuple(role for role in BusinessRole.ALL if role in assigned_roles)


def has_inconsistent_business_roles(user):
    return len(get_business_roles(user)) > 1


def get_business_role(user):
    roles = get_business_roles(user)
    if len(roles) > 1:
        raise InconsistentBusinessRoleError(
            f'User {user.pk} has multiple business roles: {", ".join(roles)}'
        )
    return roles[0] if roles else None


def has_business_role(user, role):
    _validate_business_role(role)
    return get_business_role(user) == role


@transaction.atomic
def assign_business_role(user, role):
    _validate_business_role(role)
    if user.pk is None:
        raise ValueError('A saved user is required to assign a business role.')

    user_model = get_user_model()
    locked_user = user_model.objects.select_for_update().get(pk=user.pk)
    role_group = Group.objects.get(name=role)
    role_group_ids = get_business_role_groups().values_list('pk', flat=True)

    locked_user.groups.remove(*role_group_ids)
    locked_user.groups.add(role_group)
    _clear_permission_caches(user)
    return role


def _validate_business_role(role):
    if role not in BusinessRole.ALL:
        raise ValueError(f'Unknown business role: {role}')


def _clear_permission_caches(user):
    for cache_name in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
        user.__dict__.pop(cache_name, None)
    if hasattr(user, '_prefetched_objects_cache'):
        user._prefetched_objects_cache.pop('groups', None)
