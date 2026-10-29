from rest_framework.permissions import BasePermission

from usuarios.roles import BusinessPermission

from .technical_skill_access import DIAGNOSIS_SKILL_CODE, user_has_active_skill


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


class CanManageTechnicalRiskPolicy(BasePermission):
    message = 'No tiene permisos para gestionar políticas de riesgo técnico.'

    def has_permission(self, request, view):
        return request.user.has_perm(
            BusinessPermission.MANAGE_TECHNICAL_RISK_POLICY
        )


class CanReviewTechnicalBooking(BasePermission):
    message = (
        'Se requiere permiso de revisión técnica, Personal activo y la '
        'habilidad DIAGNOSTICO activa.'
    )

    def has_permission(self, request, view):
        user = request.user
        return bool(
            getattr(user, 'is_active', False)
            and user.has_perm(BusinessPermission.REVIEW_TECHNICAL_BOOKING)
            and user_has_active_skill(user, DIAGNOSIS_SKILL_CODE)
        )


class CanCreateDiagnosisWithSkill(BasePermission):
    message = (
        'Se requiere permiso para crear diagnósticos y la habilidad '
        'DIAGNOSTICO activa.'
    )

    def has_permission(self, request, view):
        return (
            request.user.has_perm(BusinessPermission.CREATE_DIAGNOSIS)
            and user_has_active_skill(request.user, DIAGNOSIS_SKILL_CODE)
        )


class CanReadOwnedOrManageDiagnosis(BasePermission):
    message = 'No tiene permisos para consultar estos diagnósticos.'

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, 'is_active', False):
            return False
        if getattr(user, 'cliente', None) is not None:
            return True
        return (
            user.has_perm(BusinessPermission.MANAGE_TECHNICAL_RECORD)
            and user_has_active_skill(user, DIAGNOSIS_SKILL_CODE)
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
