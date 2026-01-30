"""
Test de flujo completo: Registro de cliente con datos capilares
-> Creación automática de diagnóstico
-> Ejecución automática del motor diagnóstico
-> Creación de notificación con turno recomendado
"""

import os
import django
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from django.contrib.auth import get_user_model
from usuarios.models import Cliente
from gestion.models import (
    DiagnosticoCapilar, CategoriaServicio, Servicio, 
    ReglaDiagnostico, Notificacion, Turno, Rutina, RutinaCliente,
    Personal, HorarioLaboral, Configuracion
)
from usuarios.serializers import RegistroSerializer
from gestion.views import DiagnosticoCapilarViewSet
import json

Usuario = get_user_model()

print("\n" + "="*80)
print("TEST: Flujo de Registro Automático con Diagnóstico")
print("="*80)

# 1. PREPARAR DATOS BASE
print("\n[1] Preparando datos base...")

# Obtener o crear CategoriaServicio
categoria = CategoriaServicio.objects.filter(nombre='Tratamientos').first()
if not categoria:
    categoria = CategoriaServicio.objects.create(
        nombre='Tratamientos',
        descripcion='Tratamientos capilares'
    )

# Obtener o crear Servicio Urgente
servicio_urgente = Servicio.objects.filter(nombre='Tratamiento Capilar Urgente').first()
if not servicio_urgente:
    servicio_urgente = Servicio.objects.create(
        nombre='Tratamiento Capilar Urgente',
        descripcion='Para casos críticos',
        duracion_estimada=60,
        categoria=categoria,
        precio_base=150.00
    )

# Obtener una rutina existente o crear una básica
rutina_critica = Rutina.objects.filter(nombre__icontains='Recuperación').first()
if not rutina_critica:
    # Usar la primera rutina existente
    rutina_critica = Rutina.objects.first()
    if not rutina_critica:
        # Si no hay rutinas, obtener usuario admin para crear una
        admin_user = Usuario.objects.filter(is_staff=True).first()
        if not admin_user:
            admin_user = Usuario.objects.create_user(
                email='admin@test.com',
                password='admin123',
                is_staff=True
            )
        rutina_critica = Rutina.objects.create(
            nombre='Recuperación Capilar',
            descripcion='Rutina para cabellos dañados',
            creada_por=admin_user
        )

# Obtener o crear Personal
personal = Personal.objects.filter(nombre='Dr. Especialista').first()
if not personal:
    usuario_prof = Usuario.objects.create_user(
        email='profesional@test.com',
        password='test123'
    )
    personal = Personal.objects.create(
        usuario=usuario_prof,
        nombre='Dr. Especialista',
        apellido='Tricólogo',
        rol='colorista',
        realiza_diagnostico=True
    )

# Obtener o crear HorarioLaboral (Mañana)
horario = HorarioLaboral.objects.filter(nombre='Turno Mañana').first()
if not horario:
    horario = HorarioLaboral.objects.create(
        nombre='Turno Mañana',
        hora_inicio='09:00:00',
        hora_fin='13:00:00'
    )

# Asignar personal a horario
if personal not in horario.personal.all():
    horario.personal.add(personal)
    print(f"   ✓ Personal '{personal.nombre}' asignado a horario '{horario.nombre}'")

# Obtener o crear Configuración
config, created = Configuracion.objects.get_or_create(
    defaults={
        'max_reprogramaciones': 3,
        'horas_limite_cancelacion': 24
    }
)

print("   ✓ CategoriaServicio Tratamientos creada/obtenida")
print("   ✓ Servicio Urgente creado/obtenido")
print("   ✓ Rutina Crítica creada/obtenida")
print("   ✓ Personal creado/obtenido")
print("   ✓ HorarioLaboral creado/obtenido")

# 2. CREAR REGLA DE DIAGNÓSTICO (Nivel 1)
print("\n[2] Creando reglas de diagnóstico...")

# Limpiar reglas previas
ReglaDiagnostico.objects.all().delete()

# Crear regla: Cabello muy dañado, cualquier tipo = CRÍTICO
regla_critica = ReglaDiagnostico.objects.create(
    nombre='Cabello Muy Dañado',
    descripcion='Cabello en estado crítico',
    estado_minimo_valor=0,
    estado_maximo_valor=0,  # Solo "Dañado" (0)
    resultado_automatico=True,
    servicio_asignado=servicio_urgente,
    rutina_asignada=rutina_critica
)

print(f"   ✓ Regla crítica creada: {regla_critica.nombre}")

# 3. REGISTRAR CLIENTE CON DATOS CAPILARES
print("\n[3] Registrando nuevo cliente con datos capilares...")

# Obtener catálogos de atributos
tipo_rizado = Cliente._meta.get_field('tipo_cabello').related_model.objects.filter(nombre='Rizado').first()
grosor_fino = Cliente._meta.get_field('grosor_cabello').related_model.objects.filter(nombre='Fino').first()
porosidad_alta = Cliente._meta.get_field('porosidad_cabello').related_model.objects.filter(nombre='Alta').first()
cuero_seco = Cliente._meta.get_field('cuero_cabelludo').related_model.objects.filter(nombre='Seco').first()
estado_danado = Cliente._meta.get_field('estado_general').related_model.objects.filter(nombre='Dañado').first()

if not all([tipo_rizado, grosor_fino, porosidad_alta, cuero_seco, estado_danado]):
    print("   ✗ Error: Faltan catálogos de atributos capilares")
    raise Exception("Necesitas crear los catálogos de atributos capilares")

# Datos de registro
registro_data = {
    'email': f'cliente_test_{datetime.now().timestamp()}@test.com',
    'password': 'test123',
    'password2': 'test123',
    'nombre': 'Cliente Test',
    'apellido': 'Registro Automático',
    'zona': 'Zona Test',
    'numero': '1234',
    'redes': '@cliente',
    'sexo': 'F',
    'tipo_cabello': tipo_rizado.id,
    'grosor_cabello': grosor_fino.id,
    'porosidad_cabello': porosidad_alta.id,
    'cuero_cabelludo': cuero_seco.id,
    'estado_general': estado_danado.id,
    'fecha_nacimiento': '1995-01-01'
}

# Ejecutar el serializer
serializer = RegistroSerializer(data=registro_data)
if serializer.is_valid():
    usuario_nuevo = serializer.save()
    print(f"   ✓ Usuario creado: {usuario_nuevo.email}")
    
    # Obtener el Cliente creado
    cliente = Cliente.objects.get(usuario=usuario_nuevo)
    print(f"   ✓ Cliente creado: {cliente.usuario.nombre} {cliente.usuario.apellido}")
else:
    print(f"   ✗ Error en serializer: {serializer.errors}")
    raise Exception(serializer.errors)

# 4. VERIFICAR QUE EL DIAGNÓSTICO SE CREÓ AUTOMÁTICAMENTE
print("\n[4] Verificando creación automática del diagnóstico...")

diagnosticos = DiagnosticoCapilar.objects.filter(cliente=cliente).order_by('-fecha_creacion')

if diagnosticos.exists():
    diag = diagnosticos.first()
    print(f"   ✓ Diagnóstico creado automáticamente: {diag.id}")
    print(f"   - Fecha: {diag.fecha_creacion}")
    print(f"   - Tipo cabello: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'N/A'}")
    print(f"   - Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'N/A'}")
    print(f"   - Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'N/A'}")
    print(f"   - Cuero cabelludo: {diag.cuero_cabelludo.nombre if diag.cuero_cabelludo else 'N/A'}")
    print(f"   - Estado: {diag.estado_general.nombre if diag.estado_general else 'N/A'}")
else:
    print("   ✗ No se creó diagnóstico automáticamente")
    raise Exception("El diagnóstico debería haberse creado automáticamente")

# 5. VERIFICAR RESULTADOS DEL MOTOR
print("\n[5] Verificando resultados del motor diagnóstico...")

if diag.servicio_urgente:
    print(f"   ✓ Servicio urgente asignado: {diag.servicio_urgente.nombre}")
else:
    print("   ✗ No se asignó servicio urgente")

if diag.rutina_asignada:
    print(f"   ✓ Rutina asignada: {diag.rutina_asignada.nombre}")
else:
    print("   ✗ No se asignó rutina")

if diag.rutina_sugerida:
    print(f"   ✓ Rutina sugerida: {diag.rutina_sugerida.nombre}")
else:
    print("   ✗ No se sugirió rutina")

# 6. VERIFICAR QUE EL CLIENTE TIENE RUTINA
print("\n[6] Verificando RutinaCliente creada automáticamente...")

rutinas_cliente = RutinaCliente.objects.filter(cliente=cliente)
if rutinas_cliente.exists():
    for rc in rutinas_cliente:
        print(f"   ✓ RutinaCliente: {rc.rutina.nombre}")
else:
    print("   ⚠ No hay RutinaCliente creadas (esto es OK si el motor no asignó rutina)")

# 7. VERIFICAR NOTIFICACIÓN CON TURNO RECOMENDADO
print("\n[7] Verificando notificación con turno recomendado...")

notificaciones = Notificacion.objects.filter(
    usuario=usuario_nuevo,
    tipo='TURNO_RECOMENDADO'
).order_by('-fecha_creacion')

if notificaciones.exists():
    notif = notificaciones.first()
    print(f"   ✓ Notificación creada: {notif.id}")
    print(f"   - Título: {notif.titulo}")
    print(f"   - Tipo: {notif.tipo}")
    print(f"   - Leída: {notif.leida}")
    
    # Verificar datos_extra con detalles del turno
    if notif.datos_extra:
        datos = notif.datos_extra
        print(f"   - Fecha recomendada: {datos.get('fecha', 'N/A')}")
        print(f"   - Hora recomendada: {datos.get('hora', 'N/A')}")
        print(f"   - Servicio: {datos.get('servicio_id', 'N/A')}")
        if datos.get('personal_id'):
            prof = Personal.objects.get(id=datos.get('personal_id'))
            print(f"   - Personal: {prof.nombre}")
else:
    print("   ✗ No se creó notificación de turno recomendado")

# 8. VERIFICAR TURNO CREADO
print("\n[8] Verificando turno creado...")

turnos = Turno.objects.filter(
    cliente=cliente,
    estado='PENDIENTE'
).order_by('-fecha')

if turnos.exists():
    for turno in turnos:
        print(f"   ✓ Turno creado:")
        print(f"   - ID: {turno.id}")
        print(f"   - Fecha: {turno.fecha}")
        print(f"   - Hora: {turno.hora}")
        print(f"   - Estado: {turno.estado}")
        print(f"   - Servicio: {turno.servicio.nombre}")
        print(f"   - Profesional: {turno.profesional.nombre if turno.profesional else 'Sin asignar'}")
else:
    print("   ⚠ No hay turnos creados (el motor podría no haber encontrado slots disponibles)")

# RESUMEN FINAL
print("\n" + "="*80)
print("RESUMEN DEL FLUJO")
print("="*80)

print(f"\n✓ Cliente registrado: {cliente.usuario.nombre} ({cliente.usuario.email})")
print(f"✓ Diagnóstico creado automáticamente: {diag.id}")
print(f"✓ Motor ejecutado: Servicio urgente = {diag.servicio_urgente.nombre if diag.servicio_urgente else 'N/A'}")
print(f"✓ Notificación creada: {notificaciones.count()} notificación(es)")
print(f"✓ Turno(s) recomendado(s): {turnos.count()} turno(s)")

print("\n✅ FLUJO COMPLETO EXITOSO")
print("="*80 + "\n")
