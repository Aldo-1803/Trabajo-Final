"""Cuotas BH-064 compartidas por todos los workers de PostgreSQL."""

from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from django.db import connection
from django.utils.crypto import salted_hmac

from .models import WalkInRateBucket


@dataclass(frozen=True)
class Quota:
    name: str
    limit: int
    seconds: int


WALKIN_CREATE = Quota('create', 30, 600)
WALKIN_RECOVER = Quota('recover', 60, 60)
WALKIN_SELECT = Quota('select', 60, 60)
CLAIM_REQUEST_SOURCE = Quota('claim-source', 30, 600)
CLAIM_REQUEST_CONTACT = Quota('claim-contact', 3, 3600)
CLAIM_CONFIRM_SOURCE = Quota('claim-confirm-source', 30, 600)


def request_source(request):
    # No confiar en headers aportados por el cliente. El despliegue puede
    # fijar REMOTE_ADDR desde un proxy de confianza antes de llegar a Django.
    try:
        address = ip_address(request.META.get('REMOTE_ADDR', ''))
    except ValueError:
        return 'unknown'
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ip_network(f'{address}/64', strict=False))
    return str(address)


def take_quota(quota, subject):
    key = salted_hmac(
        f'bh064.rate.{quota.name}', str(subject), algorithm='sha256',
    ).hexdigest()
    table = connection.ops.quote_name(WalkInRateBucket._meta.db_table)
    # Un único UPSERT condicional serializa intentos por clave sin hueco de
    # lectura/grabación (incluso cuando la fila aún no existe). Una denegación
    # no renueva la ventana. El reloj es común, no el del worker.
    with connection.cursor() as cursor:
        cursor.execute(f'''
            INSERT INTO {table} AS bucket (key, hits, expires_at)
            VALUES (%s, 1, statement_timestamp() + %s * interval '1 second')
            ON CONFLICT (key) DO UPDATE SET
                hits = CASE WHEN bucket.expires_at <= statement_timestamp()
                       THEN 1 ELSE bucket.hits + 1 END,
                expires_at = CASE WHEN bucket.expires_at <= statement_timestamp()
                             THEN EXCLUDED.expires_at ELSE bucket.expires_at END
            WHERE bucket.expires_at <= statement_timestamp() OR bucket.hits < %s
            RETURNING key
        ''', [key, quota.seconds, quota.limit])
        return cursor.fetchone() is not None
