from rest_framework.permissions import BasePermission

from .roles import BusinessPermission


class CanViewClients(BasePermission):
    message = 'No tiene permisos para consultar clientes.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.VIEW_CLIENTS)


class CanManageUsers(BasePermission):
    message = 'No tiene permisos para administrar usuarios.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.MANAGE_USERS)
        )


class CanManageUsersAndAssignRoles(BasePermission):
    message = 'No tiene permisos para cambiar roles de negocio.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.MANAGE_USERS)
            and user.has_perm(BusinessPermission.ASSIGN_ROLES)
        )
