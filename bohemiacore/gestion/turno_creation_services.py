from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from usuarios.models import Cliente

from .models import (
    BloqueoAgenda,
    Configuracion,
    DetalleTurno,
    Equipamiento,
    HorarioLaboral,
    Personal,
    RequisitoServicio,
    Servicio,
    SlotHold,
    SlotHoldEquipmentRequirement,
    TipoEquipamiento,
    Turno,
)
from .service_skill_compatibility import service_skill_policy
from .slot_hold_clock import database_now


ACTIVE_TURNO_STATES = (
    Turno.Estado.SOLICITADO,
    Turno.Estado.ESPERANDO_SENA,
    Turno.Estado.CONFIRMADO,
    Turno.Estado.SUGERIDO,
    Turno.Estado.PENDIENTE,
    Turno.Estado.EN_PROCESO,
)


class TurnoCreationError(Exception):
    def __init__(self, code, detail, field='non_field_errors'):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.field = field


@dataclass(frozen=True)
class TurnoDetailDraft:
    servicio: Servicio
    duracion_minutos: int


class TurnoAvailabilityService:
    @classmethod
    def matching_schedules(
        cls,
        *,
        fecha,
        servicio,
        profesional=None,
        servicios=None,
        skill_policy=None,
    ):
        slot_services = tuple(servicios or (servicio,))
        policy = skill_policy or service_skill_policy(slot_services)
        rules = HorarioLaboral.objects.filter(
            personal__activo=True,
            dia_semana=fecha.weekday(),
            activo=True,
        ).filter(
            Q(personal__usuario__isnull=True)
            | Q(personal__usuario__is_active=True),
        ).filter(
            Q(fecha_desde__isnull=True) | Q(fecha_desde__lte=fecha),
            Q(fecha_hasta__isnull=True) | Q(fecha_hasta__gte=fecha),
        )
        if profesional is not None:
            rules = rules.filter(personal=profesional)

        compatible_personal = policy.filter_personal(Personal.objects.all())
        rules = rules.filter(personal_id__in=compatible_personal.values('pk'))
        rules = policy.filter_schedule_flags(rules)

        return rules.select_related('personal')

    @staticmethod
    def _slot_datetimes(fecha, hora_inicio, duracion_minutos):
        inicio = datetime.combine(fecha, hora_inicio)
        fin = inicio + timedelta(minutes=duracion_minutos)
        return inicio, fin

    @classmethod
    def _aware_slot_datetimes(cls, fecha, hora_inicio, duracion_minutos):
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion_minutos)
        current_timezone = timezone.get_current_timezone()
        return (
            timezone.make_aware(inicio, current_timezone),
            timezone.make_aware(fin, current_timezone),
        )

    @classmethod
    def _matching_schedule_exists(
        cls,
        *,
        fecha,
        hora_inicio,
        servicio,
        profesional,
        duracion_minutos=None,
        servicios=None,
        skill_policy=None,
    ):
        duracion = duracion_minutos or servicio.duracion_estimada or 60
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion)
        rules = cls.matching_schedules(
            fecha=fecha,
            servicio=servicio,
            profesional=profesional,
            servicios=servicios,
            skill_policy=skill_policy,
        )

        return any(
            inicio.time() >= rule.hora_inicio and fin.time() <= rule.hora_fin
            for rule in rules
        )

    @classmethod
    def _has_turno_conflict(
        cls,
        *,
        fecha,
        hora_inicio,
        duracion_minutos,
        profesional,
        excluir_turno_id=None,
    ):
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion_minutos)
        turnos = (
            Turno.objects.filter(
                fecha=fecha,
                profesional=profesional,
                estado__in=ACTIVE_TURNO_STATES,
            )
            .prefetch_related('detalles')
        )
        if excluir_turno_id:
            turnos = turnos.exclude(pk=excluir_turno_id)

        for turno in turnos:
            duracion_turno = sum(
                detalle.duracion_minutos for detalle in turno.detalles.all()
            ) or 60
            turno_inicio, turno_fin = cls._slot_datetimes(
                fecha,
                turno.hora_inicio,
                duracion_turno,
            )
            if inicio < turno_fin and fin > turno_inicio:
                return True
        return False

    @classmethod
    def _has_hold_conflict(
        cls,
        *,
        fecha,
        hora_inicio,
        duracion_minutos,
        profesional=None,
        cliente=None,
        excluir_hold_id=None,
        now=None,
    ):
        inicio, fin = cls._aware_slot_datetimes(
            fecha, hora_inicio, duracion_minutos
        )
        holds = SlotHold.objects.filter(
            state=SlotHold.State.ACTIVE,
            expires_at__gt=now or database_now(),
            starts_at__lt=fin,
            ends_at__gt=inicio,
        )
        if profesional is not None:
            holds = holds.filter(personal=profesional)
        if cliente is not None:
            holds = holds.filter(cliente=cliente)
        if excluir_hold_id:
            holds = holds.exclude(pk=excluir_hold_id)
        return holds.exists()

    @classmethod
    def _has_client_turno_conflict(
        cls,
        *,
        fecha,
        hora_inicio,
        duracion_minutos,
        cliente,
        excluir_turno_id=None,
    ):
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion_minutos)
        turnos = Turno.objects.filter(
            fecha=fecha,
            cliente=cliente,
            estado__in=ACTIVE_TURNO_STATES,
        ).prefetch_related('detalles')
        if excluir_turno_id:
            turnos = turnos.exclude(pk=excluir_turno_id)
        for turno in turnos:
            turno_duration = sum(
                detail.duracion_minutos for detail in turno.detalles.all()
            ) or 60
            turno_start, turno_end = cls._slot_datetimes(
                fecha, turno.hora_inicio, turno_duration
            )
            if inicio < turno_end and fin > turno_start:
                return True
        return False

    @classmethod
    def _has_block_conflict(cls, *, fecha, hora_inicio, duracion_minutos, profesional):
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion_minutos)
        timezone_current = timezone.get_current_timezone()
        inicio = timezone.make_aware(inicio, timezone_current)
        fin = timezone.make_aware(fin, timezone_current)

        bloqueos = BloqueoAgenda.objects.filter(
            Q(personal=profesional) | Q(personal__isnull=True),
            fecha_inicio__lt=fin,
            fecha_fin__gt=inicio,
        )
        return bloqueos.exists()

    @classmethod
    def _has_equipment_capacity(
        cls,
        *,
        fecha,
        hora_inicio,
        duracion_minutos,
        servicio,
        servicios=None,
        excluir_turno_id=None,
        excluir_hold_id=None,
        now=None,
        equipment_requirements=None,
    ):
        services = tuple(servicios or (servicio,))
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion_minutos)
        inicio_aware, fin_aware = cls._aware_slot_datetimes(
            fecha, hora_inicio, duracion_minutos
        )
        effective_now = now or database_now()
        if equipment_requirements is None:
            requisitos = RequisitoServicio.objects.filter(
                servicio__in=services,
                obligatorio=True,
            )
            requirements_by_type = {}
            for requisito in requisitos:
                requirements_by_type[requisito.tipo_equipamiento_id] = max(
                    requirements_by_type.get(
                        requisito.tipo_equipamiento_id,
                        0,
                    ),
                    requisito.cantidad_minima,
                )
        else:
            requirements_by_type = dict(equipment_requirements)
        if not requirements_by_type:
            return True

        for equipment_type_id, required_quantity in requirements_by_type.items():
            stock_total = Equipamiento.objects.filter(
                tipo_id=equipment_type_id,
                is_active=True,
                estado=Equipamiento.EstadoRecurso.DISPONIBLE,
            ).count()
            if stock_total < required_quantity:
                return False

            turnos = (
                Turno.objects.filter(
                    fecha=fecha,
                    estado__in=ACTIVE_TURNO_STATES,
                    detalles__servicio__requisitos_equipamiento__tipo_equipamiento=(
                        equipment_type_id
                    ),
                )
                .distinct()
                .prefetch_related('detalles')
            )
            if excluir_turno_id:
                turnos = turnos.exclude(pk=excluir_turno_id)

            ocupados = 0
            for turno in turnos:
                duracion_turno = sum(
                    detalle.duracion_minutos for detalle in turno.detalles.all()
                ) or 60
                turno_inicio, turno_fin = cls._slot_datetimes(
                    fecha,
                    turno.hora_inicio,
                    duracion_turno,
                )
                if inicio >= turno_fin or fin <= turno_inicio:
                    continue

                ocupados += (
                    RequisitoServicio.objects.filter(
                        servicio__detalles__turno=turno,
                        tipo_equipamiento_id=equipment_type_id,
                        obligatorio=True,
                    ).aggregate(maximo=Max('cantidad_minima'))['maximo']
                    or 1
                )

            hold_occupancy = (
                SlotHoldEquipmentRequirement.objects.filter(
                    tipo_equipamiento_id=equipment_type_id,
                    hold__state=SlotHold.State.ACTIVE,
                    hold__expires_at__gt=effective_now,
                    hold__starts_at__lt=fin_aware,
                    hold__ends_at__gt=inicio_aware,
                )
            )
            if excluir_hold_id:
                hold_occupancy = hold_occupancy.exclude(hold_id=excluir_hold_id)
            ocupados += (
                hold_occupancy.aggregate(total=Sum('cantidad_snapshot'))['total']
                or 0
            )

            if ocupados + required_quantity > stock_total:
                return False

        return True

    @classmethod
    def validate_slot(
        cls,
        *,
        fecha,
        hora_inicio,
        servicio,
        profesional,
        check_schedule=True,
        excluir_turno_id=None,
        duracion_minutos=None,
        servicios=None,
        skill_policy=None,
        cliente=None,
        excluir_hold_id=None,
        now=None,
        equipment_requirements=None,
    ):
        if not profesional.activo:
            raise TurnoCreationError(
                'INACTIVE_PERSONAL',
                'El Personal seleccionado no está activo.',
                'profesional',
            )
        if profesional.usuario_id and not profesional.usuario.is_active:
            raise TurnoCreationError(
                'INACTIVE_PERSONAL',
                'El Personal seleccionado no está operativo.',
                'profesional',
            )
        slot_services = tuple(servicios or (servicio,))
        if any(not slot_service.activo for slot_service in slot_services):
            raise TurnoCreationError(
                'INACTIVE_SERVICE',
                'El Servicio seleccionado no está activo.',
                'servicio',
            )

        policy = skill_policy or service_skill_policy(slot_services)
        if not policy.is_executable:
            raise TurnoCreationError(
                'INACTIVE_REQUIRED_SKILL',
                'El Servicio tiene una habilidad requerida inactiva.',
                'servicio',
            )
        if not policy.personal_can_perform(profesional):
            raise TurnoCreationError(
                'PERSONAL_SKILL_MISMATCH',
                'El Personal seleccionado no cumple las habilidades requeridas.',
                'profesional',
            )

        duracion = duracion_minutos or servicio.duracion_estimada or 60
        inicio, fin = cls._slot_datetimes(fecha, hora_inicio, duracion)
        if fin.date() != fecha:
            raise TurnoCreationError(
                'CROSS_DAY_SLOT',
                'El intervalo debe comenzar y terminar en el mismo día.',
                'hora_inicio',
            )
        inicio_aware = timezone.make_aware(
            inicio,
            timezone.get_current_timezone(),
        )
        authoritative_now = now or database_now()
        if inicio_aware <= authoritative_now:
            raise TurnoCreationError(
                'PAST_SLOT',
                'La fecha y hora deben ser futuras.',
                'fecha',
            )

        config = Configuracion.objects.first()
        max_dias = config.max_dias_anticipacion if config else 60
        if fecha > timezone.localdate() + timedelta(days=max_dias):
            raise TurnoCreationError(
                'OUTSIDE_BOOKING_WINDOW',
                'La fecha supera el horizonte habilitado para reservas.',
                'fecha',
            )

        if check_schedule and not cls._matching_schedule_exists(
                fecha=fecha,
                hora_inicio=hora_inicio,
                servicio=servicio,
                profesional=profesional,
                duracion_minutos=duracion,
                servicios=slot_services,
                skill_policy=policy,
            ):
            raise TurnoCreationError(
                'OUTSIDE_WORK_SCHEDULE',
                'El horario no está habilitado para el Servicio y Personal seleccionados.',
                'hora_inicio',
            )

        if cls._has_turno_conflict(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_minutos=duracion,
            profesional=profesional,
            excluir_turno_id=excluir_turno_id,
        ):
            raise TurnoCreationError(
                'SLOT_UNAVAILABLE',
                'El horario seleccionado ya no está disponible.',
                'hora_inicio',
            )

        if cls._has_hold_conflict(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_minutos=duracion,
            profesional=profesional,
            excluir_hold_id=excluir_hold_id,
            now=authoritative_now,
        ):
            raise TurnoCreationError(
                'SLOT_UNAVAILABLE',
                'El horario seleccionado ya no está disponible.',
                'hora_inicio',
            )

        if cliente is not None:
            if cls._has_client_turno_conflict(
                fecha=fecha,
                hora_inicio=hora_inicio,
                duracion_minutos=duracion,
                cliente=cliente,
                excluir_turno_id=excluir_turno_id,
            ) or cls._has_hold_conflict(
                fecha=fecha,
                hora_inicio=hora_inicio,
                duracion_minutos=duracion,
                cliente=cliente,
                excluir_hold_id=excluir_hold_id,
                now=authoritative_now,
            ):
                raise TurnoCreationError(
                    'CLIENT_UNAVAILABLE',
                    'El Cliente ya tiene una reserva que se superpone.',
                    'hora_inicio',
                )

        if cls._has_block_conflict(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_minutos=duracion,
            profesional=profesional,
        ):
            raise TurnoCreationError(
                'SLOT_BLOCKED',
                'El horario seleccionado no está disponible.',
                'hora_inicio',
            )

        if not cls._has_equipment_capacity(
            fecha=fecha,
            hora_inicio=hora_inicio,
            duracion_minutos=duracion,
            servicio=servicio,
            servicios=servicios,
            excluir_turno_id=excluir_turno_id,
            excluir_hold_id=excluir_hold_id,
            now=authoritative_now,
            equipment_requirements=equipment_requirements,
        ):
            raise TurnoCreationError(
                'EQUIPMENT_UNAVAILABLE',
                'El horario seleccionado no está disponible.',
                'hora_inicio',
            )

        return True

    @classmethod
    def is_slot_available(cls, **kwargs):
        try:
            cls.validate_slot(**kwargs)
        except TurnoCreationError:
            return False
        return True

    @classmethod
    def available_slots_for_schedule(
        cls,
        *,
        fecha,
        schedule,
        servicio,
        intervalo_minutos,
        excluir_turno_id=None,
        duracion_minutos=None,
        servicios=None,
        skill_policy=None,
        cliente=None,
    ):
        slots = []
        duracion = duracion_minutos or servicio.duracion_estimada or 60
        slot_services = tuple(servicios or (servicio,))
        policy = skill_policy or service_skill_policy(slot_services)
        current_minute = schedule.hora_inicio.hour * 60 + schedule.hora_inicio.minute
        end_minute = schedule.hora_fin.hour * 60 + schedule.hora_fin.minute

        while current_minute + duracion <= end_minute:
            hora_inicio = datetime.min.replace(
                hour=current_minute // 60,
                minute=current_minute % 60,
            ).time()
            if cls.is_slot_available(
                fecha=fecha,
                hora_inicio=hora_inicio,
                servicio=servicio,
                profesional=schedule.personal,
                check_schedule=True,
                excluir_turno_id=excluir_turno_id,
                duracion_minutos=duracion,
                servicios=servicios,
                skill_policy=policy,
                cliente=cliente,
            ):
                slots.append({
                    'hora': hora_inicio.strftime('%H:%M'),
                    'profesional_id': schedule.personal_id,
                })
            current_minute += intervalo_minutos

        return slots


class TurnoCreationService:
    @staticmethod
    def _requires_hair_damage_alert(cliente, servicio):
        if not servicio.categoria_id or servicio.dias_espera_minima <= 0:
            return False

        ultimo_turno = (
            Turno.objects.filter(
                cliente=cliente,
                estado=Turno.Estado.REALIZADO,
                detalles__servicio__categoria_id=servicio.categoria_id,
            )
            .order_by('-fecha', '-hora_inicio')
            .first()
        )
        if not ultimo_turno:
            return False

        ultimo_inicio = datetime.combine(
            ultimo_turno.fecha,
            ultimo_turno.hora_inicio,
        )
        ultimo_inicio = timezone.make_aware(
            ultimo_inicio,
            timezone.get_current_timezone(),
        )
        return (timezone.now() - ultimo_inicio).days < servicio.dias_espera_minima

    @classmethod
    def _create_from_locked_resources(
        cls,
        *,
        cliente,
        profesional,
        fecha,
        hora_inicio,
        source,
        estado,
        detail_drafts,
    ):
        """Persiste el agregado Turno; el caller bloquea y revalida recursos."""
        drafts = tuple(detail_drafts)
        if not drafts:
            raise TurnoCreationError(
                'MISSING_TURNO_SERVICE',
                'El Turno requiere al menos un Servicio.',
            )
        turno = Turno.objects.create(
            cliente=cliente,
            profesional=profesional,
            fecha=fecha,
            hora_inicio=hora_inicio,
            estado=estado,
            canal_origen=source,
            alerta_daño_capilar=any(
                cls._requires_hair_damage_alert(cliente, draft.servicio)
                for draft in drafts
            ),
            tipo_pago_registro=None,
            monto_abonado=Decimal('0.00'),
            saldo_pendiente=Decimal('0.00'),
        )
        DetalleTurno.objects.bulk_create([
            DetalleTurno(
                turno=turno,
                servicio=draft.servicio,
                precio_historico=(
                    draft.servicio.precio_base or Decimal('0.00')
                ),
                duracion_minutos=draft.duracion_minutos,
            )
            for draft in drafts
        ])
        return turno

    @classmethod
    @transaction.atomic
    def create(
        cls,
        *,
        cliente_id,
        servicio_id,
        profesional_id,
        fecha,
        hora_inicio,
        source,
    ):
        try:
            cliente = Cliente.objects.select_for_update().select_related('usuario').get(
                pk=cliente_id,
                activo=True,
                usuario__is_active=True,
            )
        except Cliente.DoesNotExist:
            raise TurnoCreationError(
                'INVALID_CLIENT',
                'El Cliente seleccionado no existe o no está activo.',
                'cliente_id',
            )

        try:
            servicio = Servicio.objects.select_for_update().prefetch_related(
                'requisitos_habilidad__habilidad'
            ).get(
                pk=servicio_id,
                activo=True,
            )
        except Servicio.DoesNotExist:
            raise TurnoCreationError(
                'INVALID_SERVICE',
                'El Servicio seleccionado no existe o no está activo.',
                'servicio',
            )

        try:
            profesional = Personal.objects.select_for_update().get(
                pk=profesional_id
            )
        except Personal.DoesNotExist:
            raise TurnoCreationError(
                'INVALID_PERSONAL',
                'El Personal seleccionado no existe.',
                'profesional',
            )

        required_equipment_type_ids = list(
            RequisitoServicio.objects.filter(
                servicio=servicio,
                obligatorio=True,
            ).values_list('tipo_equipamiento_id', flat=True)
        )
        if required_equipment_type_ids:
            list(
                TipoEquipamiento.objects.select_for_update()
                .filter(pk__in=required_equipment_type_ids)
                .order_by('pk')
                .values_list('pk', flat=True)
            )

        if Turno.objects.filter(
            cliente=cliente,
            fecha=fecha,
            hora_inicio=hora_inicio,
            estado__in=ACTIVE_TURNO_STATES,
        ).exists():
            raise TurnoCreationError(
                'DUPLICATE_CLIENT_SLOT',
                'El Cliente ya tiene un Turno en esa fecha y hora.',
                'hora_inicio',
            )

        TurnoAvailabilityService.validate_slot(
            fecha=fecha,
            hora_inicio=hora_inicio,
            servicio=servicio,
            profesional=profesional,
            cliente=cliente,
        )

        return cls._create_from_locked_resources(
            cliente=cliente,
            profesional=profesional,
            fecha=fecha,
            hora_inicio=hora_inicio,
            source=source,
            estado=Turno.Estado.SOLICITADO,
            detail_drafts=(
                TurnoDetailDraft(
                    servicio=servicio,
                    duracion_minutos=servicio.duracion_estimada or 60,
                ),
            ),
        )
