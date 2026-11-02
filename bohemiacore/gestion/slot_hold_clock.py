"""Reloj autoritativo y semántica efectiva de SlotHold."""

from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def database_now():
    """Obtiene un reloj de statement de la base, incluso dentro de una TX larga."""
    statement = (
        'SELECT STATEMENT_TIMESTAMP()'
        if connection.vendor == 'postgresql'
        else 'SELECT CURRENT_TIMESTAMP'
    )
    with connection.cursor() as cursor:
        cursor.execute(statement)
        value = cursor.fetchone()[0]
    if isinstance(value, str):
        value = parse_datetime(value)
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def effective_hold_state(hold, *, at=None):
    """ACTIVE en almacenamiento puede ser EXPIRED de forma efectiva."""
    from .models import SlotHold

    at = at or database_now()
    if hold.state == SlotHold.State.ACTIVE and hold.expires_at <= at:
        return SlotHold.State.EXPIRED
    return hold.state
