from rest_framework.permissions import BasePermission

from usuarios.roles import BusinessPermission


class CanViewGlobalAgenda(BasePermission):
    message = 'No tiene permisos para consultar la agenda global.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.VIEW_GLOBAL_AGENDA)


class CanCreateTurnoForClient(BasePermission):
    message = 'No tiene permisos para crear Turnos para Clientes.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.CREATE_TURNO_FOR_CLIENT)


class CanRegisterTurnoArrival(BasePermission):
    message = 'No tiene permisos para registrar la llegada de Turnos.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.REGISTER_ARRIVAL)


class CanReprogramAnyTurno(BasePermission):
    message = 'No tiene permisos para reprogramar Turnos.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.REPROGRAM_ANY_TURNO)


class CanCancelAnyTurno(BasePermission):
    message = 'No tiene permisos para cancelar Turnos.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.CANCEL_ANY_TURNO)


class CanManageSkills(BasePermission):
    message = 'No tiene permisos para gestionar habilidades técnicas.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.MANAGE_SKILLS)
