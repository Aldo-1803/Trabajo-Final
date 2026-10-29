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

ROLE_BASE_PERMISSIONS = {
    BusinessRole.CLIENTE: (),
    BusinessRole.EMPLEADO: EMPLOYEE_BASE_PERMISSIONS,
    BusinessRole.PROFESIONAL: PROFESSIONAL_BASE_PERMISSIONS,
    BusinessRole.ADMINISTRADOR: BusinessPermission.ALL,
}


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
