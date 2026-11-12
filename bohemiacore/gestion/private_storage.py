from django.conf import settings
from django.core.files.storage import FileSystemStorage


legacy_payment_receipt_storage = FileSystemStorage(
    location=settings.MEDIA_ROOT,
    base_url=settings.MEDIA_URL,
)


class PrivatePaymentReceiptStorage(FileSystemStorage):
    """Storage sin URL pública; los archivos se sirven por un endpoint autorizado."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            'location',
            settings.PRIVATE_PAYMENT_RECEIPT_ROOT,
        )
        kwargs.setdefault('base_url', None)
        super().__init__(*args, **kwargs)

    def url(self, name):
        raise ValueError('Los comprobantes de Pago no tienen URL pública.')

    @staticmethod
    def _is_legacy_name(name):
        return str(name).replace('\\', '/').startswith('pagos/comprobantes/')

    def _open(self, name, mode='rb'):
        try:
            return super()._open(name, mode)
        except FileNotFoundError:
            if self._is_legacy_name(name):
                return legacy_payment_receipt_storage.open(name, mode)
            raise

    def exists(self, name):
        return super().exists(name) or (
            self._is_legacy_name(name)
            and legacy_payment_receipt_storage.exists(name)
        )


private_payment_receipt_storage = PrivatePaymentReceiptStorage()
