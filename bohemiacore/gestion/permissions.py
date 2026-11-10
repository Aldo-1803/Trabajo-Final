from rest_framework.permissions import BasePermission

from usuarios.roles import BusinessPermission

from .effective_access import (
    user_can_create_diagnosis,
    user_can_manage_service_formula,
    user_can_manage_technical_record,
    user_can_read_global_technical_record,
    user_can_review_technical_booking,
)


class IsActiveUser(BasePermission):
    message = 'La cuenta debe estar activa.'

    def has_permission(self, request, view):
        return bool(getattr(request.user, 'is_active', False))


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


class CanManagePersonal(BasePermission):
    message = 'No tiene permisos para administrar Personal.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.MANAGE_PERSONAL)
        )


class CanViewAudit(BasePermission):
    message = 'No tiene permisos para consultar auditoría.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.VIEW_AUDIT)
        )


class CanRevertAudit(BasePermission):
    message = 'No tiene permisos para revertir auditoría.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.REVERT_AUDIT)
        )


class CanManageTechnicalRiskPolicy(BasePermission):
    message = 'No tiene permisos para gestionar políticas de riesgo técnico.'

    def has_permission(self, request, view):
        return request.user.has_perm(
            BusinessPermission.MANAGE_TECHNICAL_RISK_POLICY
        )


class CanManageConfiguration(BasePermission):
    message = 'No tiene permisos para administrar la configuración.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.MANAGE_CONFIGURATION)
        )


class CanViewGlobalAgendaOrManageConfiguration(BasePermission):
    message = 'No tiene permisos para consultar la configuración de horarios.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and (
                user.has_perm(BusinessPermission.VIEW_GLOBAL_AGENDA)
                or user.has_perm(BusinessPermission.MANAGE_CONFIGURATION)
            )
        )


class CanViewReports(BasePermission):
    message = 'No tiene permisos para consultar reportes generales.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.VIEW_REPORTS)
        )


class CanViewGeneralOrFinancialReports(BasePermission):
    message = 'No tiene permisos para consultar reportes.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and (
                user.has_perm(BusinessPermission.VIEW_REPORTS)
                or user.has_perm(BusinessPermission.VIEW_FINANCIAL_REPORTS)
            )
        )


class CanReviewTechnicalBooking(BasePermission):
    message = (
        'Se requiere permiso de revisión técnica, Personal activo y la '
        'habilidad DIAGNOSTICO activa.'
    )

    def has_permission(self, request, view):
        return user_can_review_technical_booking(request.user)


class CanCreateDiagnosisWithSkill(BasePermission):
    message = (
        'Se requiere permiso para crear diagnósticos y la habilidad '
        'DIAGNOSTICO activa.'
    )

    def has_permission(self, request, view):
        return user_can_create_diagnosis(request.user)


class CanReadOwnedOrManageDiagnosis(BasePermission):
    message = 'No tiene permisos para consultar estos diagnósticos.'

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, 'is_active', False):
            return False
        if getattr(user, 'cliente', None) is not None:
            return True
        return user_can_read_global_technical_record(user)


class CanReadOwnedOrManageTechnicalRecord(BasePermission):
    message = 'No tiene permisos para consultar fichas técnicas.'

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, 'is_active', False):
            return False
        cliente = getattr(user, 'cliente', None)
        if cliente is not None:
            return bool(cliente.activo)
        return user_can_read_global_technical_record(user)


class CanManageTechnicalRecordWithSkill(BasePermission):
    message = (
        'Se requiere permiso de ficha técnica, Personal activo y la habilidad '
        'DIAGNOSTICO activa.'
    )

    def has_permission(self, request, view):
        return user_can_manage_technical_record(request.user)


class CanManagePricesOrFormulas(BasePermission):
    message = 'No tiene permisos para modificar precios ni fórmulas.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and (
                user.has_perm(BusinessPermission.MANAGE_PRICES)
                or user_can_manage_service_formula(user)
            )
        )


class CanAssignRoutines(BasePermission):
    message = 'No tiene permisos para administrar o asignar rutinas.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.ASSIGN_ROUTINES)
        )


class CanFinalizeService(BasePermission):
    message = 'No tiene permisos para finalizar Servicios.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.FINALIZE_SERVICE)


class CanViewFinancialReports(BasePermission):
    message = 'No tiene permisos para consultar reportes financieros.'

    def has_permission(self, request, view):
        return request.user.has_perm(
            BusinessPermission.VIEW_FINANCIAL_REPORTS
        )


class CanReconcileExternalPayment(BasePermission):
    message = 'No tiene permisos para consultar incidencias financieras.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(
                BusinessPermission.RECONCILE_EXTERNAL_PAYMENT
            )
        )


class CanViewStock(BasePermission):
    message = 'No tiene permisos para consultar stock interno.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.VIEW_STOCK)


class CanManageStock(BasePermission):
    message = 'No tiene permisos para gestionar stock.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.MANAGE_STOCK)


class CanManageProducts(BasePermission):
    message = 'No tiene permisos para administrar productos.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.MANAGE_PRODUCTS)


class CanManagePrices(BasePermission):
    message = 'No tiene permisos para administrar precios.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.MANAGE_PRICES)


class CanManagePromotions(BasePermission):
    message = 'No tiene permisos para administrar promociones.'

    def has_permission(self, request, view):
        return request.user.has_perm(BusinessPermission.MANAGE_PROMOTIONS)


class CanManageProductsOrPrices(BasePermission):
    message = 'No tiene permisos para modificar productos o precios.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.has_perm(BusinessPermission.MANAGE_PRODUCTS)
            or user.has_perm(BusinessPermission.MANAGE_PRICES)
        )


class CanManageProductsAndPrices(BasePermission):
    message = 'Crear productos requiere permisos de productos y precios.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user.has_perm(BusinessPermission.MANAGE_PRODUCTS)
            and user.has_perm(BusinessPermission.MANAGE_PRICES)
        )
