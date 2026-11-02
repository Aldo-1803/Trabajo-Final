from rest_framework.permissions import BasePermission

from .roles import BusinessPermission


class CanViewClients(BasePermission):
    message = 'No tiene permisos para consultar clientes.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.VIEW_CLIENTS)
