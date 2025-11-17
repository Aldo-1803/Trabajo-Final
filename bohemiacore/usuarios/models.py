from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.conf import settings

from gestion.models import (
    TipoCabello, 
    GrosorCabello, 
    PorosidadCabello, 
    CueroCabelludo, 
    EstadoGeneral,
    Servicio
)

# 1. Manager Personalizado (SIN CAMBIOS)
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


# 2. Modelo de Usuario Personalizado (SIN CAMBIOS)
class Usuario(AbstractUser):
    email = models.EmailField(unique=True, null=False, blank=False)
    username = None 
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']
    objects = UsuarioManager()

    class Meta:
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return self.email
    

# 3. Modelo de Cliente (¡CORREGIDO Y CONSOLIDADO!)
class Cliente(models.Model):
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

    # --- CAMPO MOVIDO AQUÍ ---
    productos_actuales = models.TextField(
        blank=True, 
        null=True, 
        verbose_name="Productos Actuales"
    )

    # --- CAMPO HISTORIAL (ya estaba aquí, perfecto) ---
    historial_servicios = models.ManyToManyField(
        Servicio,
        blank=True,
        verbose_name="Historial de Servicios (Estructurado)"
    )

    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return self.usuario.email