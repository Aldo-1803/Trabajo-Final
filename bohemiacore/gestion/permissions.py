from rest_framework.permissions import BasePermission

from usuarios.roles import BusinessPermission


class CanViewGlobalAgenda(BasePermission):
    message = 'No tiene permisos para consultar la agenda global.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.VIEW_GLOBAL_AGENDA)
