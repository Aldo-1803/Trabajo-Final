import uuid

from django.db import models
from django.db.models.functions import Lower
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.conf import settings

from gestion.models import (
    TipoCabello, 
    GrosorCabello, 
    PorosidadCabello, 
    CueroCabelludo, 
    EstadoGeneral,
    Servicio,
    Turno
)

# 1. Manager Personalizado 
class UsuarioManager(BaseUserManager):
    """
    Manager que garantiza que el campo 'email' siempre se use
    y se normalice.
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """Crea y guarda un Usuario con el email y password dados."""
        if not email:
            raise ValueError('El Email debe ser proporcionado')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser debe tener is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


# 2. Modelo de Usuario Personalizado 
class Usuario(AbstractUser):
    class WebAccessStatus(models.TextChoices):
        LEGACY_UNKNOWN = 'LEGACY_UNKNOWN', 'Legacy / desconocido'
        PENDING_CLAIM = 'PENDING_CLAIM', 'Pendiente de reclamo'
        CLAIMED = 'CLAIMED', 'Reclamado'

    email = models.EmailField(unique=True, null=True, blank=True)
    web_access_status = models.CharField(
        max_length=20,
        choices=WebAccessStatus.choices,
        default=WebAccessStatus.LEGACY_UNKNOWN,
    )
    username = None 
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = UsuarioManager()

    class Meta:
        verbose_name_plural = 'Usuarios'
        permissions = [
            ('manage_users', 'Can manage users'),
            ('assign_roles', 'Can assign business roles'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(email=''),
                name='usuario_email_not_blank',
            ),
            models.UniqueConstraint(
                Lower('email'),
                condition=models.Q(email__isnull=False),
                name='usuarios_usuario_email_ci_unique',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(email__isnull=False)
                    | models.Q(web_access_status='PENDING_CLAIM')
                ),
                name='usuario_null_email_only_pending_claim',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(web_access_status='PENDING_CLAIM')
                    | models.Q(password__startswith='!')
                ),
                name='usuario_pending_claim_unusable_password',
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(web_access_status='CLAIMED')
                    | models.Q(email__isnull=False)
                ),
                name='usuario_claimed_requires_email',
            ),
        ]

    def __str__(self):
        return self.email or f'Usuario #{self.pk or "sin-id"} sin email'
    

# 3. Modelo de Cliente
class Cliente(models.Model):
    class PhoneNormalizationStatus(models.TextChoices):
        LEGACY_UNKNOWN = 'LEGACY_UNKNOWN', 'Legacy / desconocido'
        VALID = 'VALID', 'Válido'
        INVALID = 'INVALID', 'Inválido'

    # 1. VÍNCULO 1:1
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True
    )

    # 2. CAMPOS DE DOMINIO
    zona = models.CharField(max_length=100, blank=True, null=True)
    redes = models.CharField(max_length=100, blank=True, null=True)
    numero = models.CharField(max_length=20, blank=True, null=True)
    numero_normalizado = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        db_index=True,
    )
    numero_normalizacion_estado = models.CharField(
        max_length=20,
        choices=PhoneNormalizationStatus.choices,
        default=PhoneNormalizationStatus.LEGACY_UNKNOWN,
    )
    fecha_nacimiento = models.DateField(blank=True, null=True)
    sexo = models.CharField(max_length=1, default='F', blank=True)

    # 3. RELACIONES DE DIAGNÓSTICO (FK a Catálogos)
    tipo_cabello = models.ForeignKey(
        TipoCabello, 
        on_delete=models.SET_NULL,
        null=True, 
        blank=True
    )
    grosor_cabello = models.ForeignKey(
        GrosorCabello, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    porosidad_cabello = models.ForeignKey(
        PorosidadCabello, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    cuero_cabelludo = models.ForeignKey(
        CueroCabelludo, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    estado_general = models.ForeignKey(
        EstadoGeneral, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )

    productos_actuales = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Productos Actuales"
    )
    
    activo = models.BooleanField(
        default=True,
        verbose_name="¿Cliente Activo?"
    )

    @property
    def historial_completo(self):
        # Importación local para evitar importación circular
        return Turno.objects.filter(cliente=self, estado='realizado').order_by('-fecha')

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        permissions = [
            ('create_walkin_client', 'Can create walk-in clients'),
            ('view_clients', 'Can view clients'),
        ]

    def __str__(self):
        return self.usuario.email or self.usuario.get_full_name() or str(self.pk)


class WalkInClientOperation(models.Model):
    class Command(models.TextChoices):
        CREATE = 'CREATE', 'Alta rápida'

    operation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='operaciones_alta_presencial',
    )
    command = models.CharField(
        max_length=20,
        choices=Command.choices,
        default=Command.CREATE,
    )
    idempotency_key_digest = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name='operaciones_alta_presencial',
    )
    result_created = models.BooleanField()
    duplicate_resolution = models.CharField(max_length=20, blank=True)
    reviewed_candidate_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['actor', 'command', 'idempotency_key_digest'],
                name='unique_walkin_operation_key_per_actor',
            ),
        ]
        indexes = [
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['cliente', '-created_at']),
        ]


class WalkInRateBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    hits = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)


class WebAccessClaimDelivery(models.Model):
    # Referencia transitoria, no una concesión de acceso. El worker verifica
    # identidad, contacto y elegibilidad de nuevo antes de emitir un token.
    target_user_id = models.BigIntegerField(null=True)
    contact_digest = models.CharField(max_length=64)
    requested_at = models.DateTimeField(auto_now_add=True)


class WebAccessClaimToken(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='web_access_claim_tokens',
    )
    token_digest = models.CharField(max_length=64, unique=True)
    email_fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['usuario', '-created_at']),
            models.Index(fields=['expires_at']),
        ]
