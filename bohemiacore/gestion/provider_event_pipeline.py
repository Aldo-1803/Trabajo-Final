"""Pipeline durable C2a -> C2b para eventos autenticados de proveedores."""

from dataclasses import dataclass
from datetime import timedelta
import logging
import uuid

from django.db import DatabaseError, models, transaction
from django.db.models import Q
from django.utils import timezone

from .models import ProviderEvent
from .provider_event_services import (
    ProviderEventProcessingResult,
    process_pending_provider_events,
)
from .provider_reconciliation_services import (
    ProviderReconciliationConflict,
    mark_verified_provider_event_for_review,
    reconcile_verified_provider_event,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderReconciliationProcessingResult:
    examined: int
    applied: int
    review_required: int
    ignored: int
    retryable: int


@dataclass(frozen=True)
class ProviderEventPipelineResult:
    verification: ProviderEventProcessingResult
    reconciliation: ProviderReconciliationProcessingResult

    @property
    def examined(self):
        return self.verification.examined + self.reconciliation.examined


@dataclass(frozen=True)
class ClaimedProviderReconciliation:
    event_id: int
    claim_token: uuid.UUID


def _cleanup_terminal_reconciliation_claims(now):
    return (
        ProviderEvent.objects.filter(
            status=ProviderEvent.Status.VERIFIED,
            claim_token__isnull=False,
        )
        .exclude(
            reconciliation_status=(
                ProviderEvent.ReconciliationStatus.NOT_EVALUATED
            )
        )
        .update(
            claim_token=None,
            processing_started_at=None,
            next_retry_at=None,
            last_error_code='',
            last_error_detail='',
            updated_at=now,
        )
    )


def _claim_next_verified_event(*, stale_after, now):
    stale_before = now - stale_after
    unclaimed_due = Q(claim_token__isnull=True) & (
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    )
    stale_claim = Q(claim_token__isnull=False) & (
        Q(processing_started_at__isnull=True)
        | Q(processing_started_at__lte=stale_before)
    )
    with transaction.atomic():
        _cleanup_terminal_reconciliation_claims(now)
        event = (
            ProviderEvent.objects.select_for_update(skip_locked=True)
            .filter(
                status=ProviderEvent.Status.VERIFIED,
                reconciliation_status=(
                    ProviderEvent.ReconciliationStatus.NOT_EVALUATED
                ),
            )
            .filter(unclaimed_due | stale_claim)
            .order_by('received_at', 'pk')
            .first()
        )
        if event is None:
            return None
        claim_token = uuid.uuid4()
        ProviderEvent.objects.filter(pk=event.pk).update(
            claim_token=claim_token,
            processing_started_at=now,
            next_retry_at=None,
            reconciliation_attempts=models.F('reconciliation_attempts') + 1,
            updated_at=now,
        )
        return ClaimedProviderReconciliation(
            event_id=event.pk,
            claim_token=claim_token,
        )


def _clear_reconciliation_claim(claim, *, clear_error):
    values = {
        'claim_token': None,
        'processing_started_at': None,
        'next_retry_at': None,
        'updated_at': timezone.now(),
    }
    if clear_error:
        values.update(last_error_code='', last_error_detail='')
    return ProviderEvent.objects.filter(
        pk=claim.event_id,
        claim_token=claim.claim_token,
    ).update(**values) == 1


def _schedule_reconciliation_retry(claim, *, retry_delay, code):
    now = timezone.now()
    return ProviderEvent.objects.filter(
        pk=claim.event_id,
        status=ProviderEvent.Status.VERIFIED,
        reconciliation_status=ProviderEvent.ReconciliationStatus.NOT_EVALUATED,
        claim_token=claim.claim_token,
    ).update(
        claim_token=None,
        processing_started_at=None,
        next_retry_at=now + retry_delay,
        last_error_code=str(code)[:50],
        last_error_detail='La conciliación financiera podrá reintentarse.',
        updated_at=now,
    ) == 1


def _reconciliation_outcome(result):
    status = result.event.reconciliation_status
    if status == ProviderEvent.ReconciliationStatus.APPLIED:
        return 'applied'
    if status == ProviderEvent.ReconciliationStatus.REVIEW_REQUIRED:
        return 'review_required'
    if status == ProviderEvent.ReconciliationStatus.IGNORED:
        return 'ignored'
    raise RuntimeError('C2b terminó sin un estado de conciliación terminal.')


def process_verified_provider_events(
    *,
    limit=100,
    stale_after=timedelta(minutes=10),
    retry_delay=timedelta(minutes=1),
):
    """Ejecuta C2b sin llamadas externas ni locks compartidos con C2a."""
    if limit < 1 or limit > 1000:
        raise ValueError('limit debe estar entre 1 y 1000.')
    if stale_after.total_seconds() <= 0 or retry_delay.total_seconds() <= 0:
        raise ValueError('Los intervalos del worker deben ser positivos.')
    counters = {
        'applied': 0,
        'review_required': 0,
        'ignored': 0,
        'retryable': 0,
    }
    examined = 0
    while examined < limit:
        claim = _claim_next_verified_event(
            stale_after=stale_after,
            now=timezone.now(),
        )
        if claim is None:
            break
        examined += 1
        try:
            result = reconcile_verified_provider_event(claim.event_id)
        except ProviderReconciliationConflict as exc:
            try:
                result = mark_verified_provider_event_for_review(
                    claim.event_id,
                    reason_code=exc.code,
                    detail=exc.detail,
                )
            except Exception:
                logger.exception(
                    'No se pudo persistir la revisión de ProviderEvent %s.',
                    claim.event_id,
                )
                _schedule_reconciliation_retry(
                    claim,
                    retry_delay=retry_delay,
                    code='REVIEW_PERSIST_FAILED',
                )
                counters['retryable'] += 1
                continue
        except DatabaseError:
            logger.exception(
                'Error de base al conciliar ProviderEvent %s; se reintentará.',
                claim.event_id,
            )
            _schedule_reconciliation_retry(
                claim,
                retry_delay=retry_delay,
                code='RECONCILIATION_DATABASE_ERROR',
            )
            counters['retryable'] += 1
            continue
        except Exception:
            logger.exception(
                'Error inesperado al conciliar ProviderEvent %s; se reintentará.',
                claim.event_id,
            )
            _schedule_reconciliation_retry(
                claim,
                retry_delay=retry_delay,
                code='RECONCILIATION_UNEXPECTED_ERROR',
            )
            counters['retryable'] += 1
            continue

        outcome = _reconciliation_outcome(result)
        _clear_reconciliation_claim(claim, clear_error=True)
        counters[outcome] += 1

    return ProviderReconciliationProcessingResult(
        examined=examined,
        applied=counters['applied'],
        review_required=counters['review_required'],
        ignored=counters['ignored'],
        retryable=counters['retryable'],
    )


def process_provider_event_pipeline(
    *,
    limit=100,
    stale_after=timedelta(minutes=10),
    retry_delay=timedelta(minutes=1),
):
    """Verifica eventos pendientes y concilia todo VERIFIED recuperable."""
    verification = process_pending_provider_events(
        limit=limit,
        stale_after=stale_after,
        retry_delay=retry_delay,
    )
    reconciliation = process_verified_provider_events(
        limit=limit,
        stale_after=stale_after,
        retry_delay=retry_delay,
    )
    return ProviderEventPipelineResult(
        verification=verification,
        reconciliation=reconciliation,
    )
