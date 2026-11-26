"""Read-only projection over the scoped assisted command ledger."""

from usuarios.roles import BusinessPermission

from .assisted_technical_booking_serializers import (
    AssistedPaymentIntentPublicSerializer,
    AssistedSlotHoldPublicSerializer,
    AssistedTechnicalRequestPublicSerializer,
)
from .assisted_technical_booking_services import assisted_request_for_actor
from .models import PaymentIntent, SolicitudTecnicaAsistidaOperacion, Turno
from .slot_hold_clock import database_now


def reception_projection(*, actor, operation_id, command_id=None):
    command = SolicitudTecnicaAsistidaOperacion.Command
    roots = SolicitudTecnicaAsistidaOperacion.objects.filter(actor=actor)
    root = roots.select_related('alta_cliente').filter(
        operation_id=operation_id, command=command.CREATE,
    ).first()
    if root is None:
        return None

    solicitud = assisted_request_for_actor(solicitud_id=root.solicitud_id, actor=actor)
    request_data = AssistedTechnicalRequestPublicSerializer(solicitud).data
    operations = roots.filter(solicitud=solicitud).order_by('-created_at', '-pk')
    now = database_now()
    hold_operation = operations.select_related('hold__personal').filter(
        command=command.HOLD, hold__cliente_id=solicitud.cliente_id,
        hold__solicitud=solicitud, hold__created_by=actor,
    ).first()
    hold = None
    if hold_operation:
        hold = AssistedSlotHoldPublicSerializer(hold_operation.hold, context={
            'database_now': now, 'operation_id': str(hold_operation.operation_id),
        }).data

    can_read_finance = actor.has_perm(BusinessPermission.REGISTER_PAYMENT)
    intent_operations = operations.select_related(
        'payment_intent__slot_hold', 'payment_intent__confirmed_turno',
    ).filter(
        command=command.INTENT, payment_intent__solicitud=solicitud,
        payment_intent__cliente_id=solicitud.cliente_id,
        payment_intent__slot_hold_id__in=operations.filter(
            command=command.HOLD, hold__cliente_id=solicitud.cliente_id,
            hold__solicitud=solicitud, hold__created_by=actor,
        ).values('hold_id'),
    )
    confirmed = intent_operations.filter(
        payment_intent__status=PaymentIntent.Status.APPROVED,
        payment_intent__confirmed_turno__cliente_id=solicitud.cliente_id,
    ).first()
    intent_op = confirmed or (intent_operations.first() if can_read_finance else None)
    turno = None
    if confirmed:
        booking = confirmed.payment_intent.confirmed_turno
        turno = {'id': booking.pk, 'estado': booking.estado, 'personal_id': booking.profesional_id}
    intent = None
    if can_read_finance and intent_op:
        intent = AssistedPaymentIntentPublicSerializer(intent_op.payment_intent, context={
            'database_now': now, 'operation_id': str(intent_op.operation_id),
        }).data

    next_action = request_data['siguiente_accion']['code']
    tracking = intent['tracking']['state'] if intent else None
    evaluation = solicitud.evaluacion_vigente
    if turno:
        stage = 'CONFIRMED' if turno['estado'] == Turno.Estado.CONFIRMADO else 'CLOSED'
        next_action = 'VIEW_BOOKING'
    elif tracking in {'ADMIN_REVIEW', 'PAYMENT_PENDING', 'PAYMENT_VERIFICATION', 'CHECKOUT_UNCERTAIN'}:
        stage, next_action = 'PAYMENT_PENDING', 'CHECK_CASHIER'
    elif intent and tracking == 'READY_FOR_CHECKOUT':
        stage, next_action = 'PAYMENT_PENDING', 'CONTINUE_IN_CASHIER'
    elif intent and (tracking == 'PAID_WITHOUT_BOOKING' or (
        hold and hold['public_id'] == intent['slot_hold_public_id']
    )):
        stage, next_action = 'RECOVERABLE_FAILURE', 'CHECK_CASHIER'
    elif evaluation and evaluation.superseded_by_id:
        stage, next_action = 'RECOVERABLE_FAILURE', 'TECHNICAL_CONTEXT_NOT_CURRENT'
    elif next_action == 'REGISTER_ASSISTED_CONSENT':
        stage = 'CONSENT_PENDING'
    elif next_action == 'WAIT_FOR_TECHNICAL_REVIEW':
        stage = 'TECHNICAL_REVIEW'
    elif solicitud.estado == solicitud.Estado.EVALUANDO:
        stage, next_action = 'TECHNICAL_PENDING', 'CHECK_TECHNICAL_RESULT'
    elif not request_data['siguiente_accion']['can_continue_to_future_hold']:
        stage = 'CLOSED'
    elif hold and hold['effective_state'] == 'ACTIVE':
        stage, next_action = 'HOLD_ACTIVE', 'PREPARE_PAYMENT' if can_read_finance else 'WAIT_FOR_AUTHORIZED_PAYMENT'
    elif hold:
        stage, next_action = 'RECOVERABLE_FAILURE', 'CHOOSE_AVAILABLE_SLOT'
    else:
        stage = 'TECHNICAL_PENDING'

    consent = operations.filter(
        command=command.CONSENT, consentimiento__evaluacion_id=solicitud.evaluacion_vigente_id,
    ).first()
    acknowledged = operations.filter(operation_id=command_id) if command_id else operations.none()
    if not can_read_finance:
        acknowledged = acknowledged.exclude(command=command.INTENT)
    alta = root.alta_cliente if actor.has_perm(BusinessPermission.CREATE_WALKIN_CLIENT) else None
    return {
        'operation_id': str(root.operation_id),
        'alta_operation_id': str(alta.operation_id) if alta else None,
        'stage': stage,
        'next_action': next_action,
        'last_error_code': next_action if stage == 'RECOVERABLE_FAILURE' else None,
        'command_committed': acknowledged.exists(),
        'evaluation_id': solicitud.evaluacion_vigente_id,
        'consent_operation_id': str(consent.operation_id) if consent else None,
        'request': request_data,
        'hold': hold,
        'intent': intent,
        'turno': turno,
    }
