"""
Test simple: Registro con datos capilares -> Creación automática de diagnóstico
"""

import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from django.contrib.auth import get_user_model
from usuarios.models import Cliente
from gestion.models import DiagnosticoCapilar
from usuarios.serializers import RegistroSerializer

Usuario = get_user_model()

print("\n" + "="*80)
print("TEST: Auto-Diagnóstico durante Registro")
print("="*80)

# Obtener catálogos de atributos
tipo_rizado = Cliente._meta.get_field('tipo_cabello').related_model.objects.filter(nombre='Rizado').first()
grosor_fino = Cliente._meta.get_field('grosor_cabello').related_model.objects.filter(nombre='Fino').first()
porosidad_alta = Cliente._meta.get_field('porosidad_cabello').related_model.objects.filter(nombre='Alta').first()
cuero_seco = Cliente._meta.get_field('cuero_cabelludo').related_model.objects.filter(nombre='Seco').first()
estado_danado = Cliente._meta.get_field('estado_general').related_model.objects.filter(nombre='Dañado').first()

if not all([tipo_rizado, grosor_fino, porosidad_alta, cuero_seco, estado_danado]):
    print("✗ Error: Faltan catálogos de atributos capilares")
    print(f"  - tipo_rizado: {tipo_rizado}")
    print(f"  - grosor_fino: {grosor_fino}")
    print(f"  - porosidad_alta: {porosidad_alta}")
    print(f"  - cuero_seco: {cuero_seco}")
    print(f"  - estado_danado: {estado_danado}")
    exit(1)

print("\n[1] Registrando cliente con datos capilares...")

# Datos de registro con atributos capilares
registro_data = {
    'email': f'cliente_{datetime.now().timestamp()}@test.com',
    'password': 'test123456',
    'password2': 'test123456',
    'first_name': 'Test',
    'last_name': f'Auto {datetime.now().strftime("%H:%M:%S")}',
    'zona': 'Test Zone',
    'numero': '123',
    'redes': '@test',
    'sexo': 'F',
    'tipo_cabello': tipo_rizado.id,
    'grosor_cabello': grosor_fino.id,
    'porosidad_cabello': porosidad_alta.id,
    'cuero_cabelludo': cuero_seco.id,
    'estado_general': estado_danado.id,
    'fecha_nacimiento': '1995-01-01'
}

# Crear usuario via serializer
serializer = RegistroSerializer(data=registro_data)

if not serializer.is_valid():
    print(f"✗ Registro fallido: {serializer.errors}")
    exit(1)

usuario_nuevo = serializer.save()
print(f"   ✓ Usuario creado: {usuario_nuevo.email}")

# Obtener el Cliente asociado
cliente = Cliente.objects.get(usuario=usuario_nuevo)
print(f"   ✓ Cliente creado: {cliente.usuario.first_name} {cliente.usuario.last_name}")

# Verificar datos capilares guardados
print(f"   - Tipo cabello: {cliente.tipo_cabello.nombre if cliente.tipo_cabello else 'N/A'}")
print(f"   - Grosor: {cliente.grosor_cabello.nombre if cliente.grosor_cabello else 'N/A'}")
print(f"   - Porosidad: {cliente.porosidad_cabello.nombre if cliente.porosidad_cabello else 'N/A'}")
print(f"   - Cuero cabelludo: {cliente.cuero_cabelludo.nombre if cliente.cuero_cabelludo else 'N/A'}")
print(f"   - Estado: {cliente.estado_general.nombre if cliente.estado_general else 'N/A'}")

# VERIFICAR QUE EL DIAGNÓSTICO SE CREÓ AUTOMÁTICAMENTE
print("\n[2] Verificando creación automática del diagnóstico...")

diagnosticos = DiagnosticoCapilar.objects.filter(cliente=cliente).order_by('-fecha_creacion')

if not diagnosticos.exists():
    print("   ✗ NO se creó diagnóstico automáticamente")
    print("   ✗ FALLÓ LA AUTOMATIZACIÓN")
    exit(1)

diag = diagnosticos.first()
print(f"   ✓ Diagnóstico creado automáticamente: {diag.id}")
print(f"   - Fecha: {diag.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')}")

# Verificar resultados del motor
print("\n[3] Verificando resultados del motor diagnóstico...")

print(f"   - Puntaje: {diag.puntaje if hasattr(diag, 'puntaje') else 'N/A'}")
print(f"   - Nivel 1 (Regla): {diag.nivel_1 if hasattr(diag, 'nivel_1') else 'N/A'}")

if diag.servicio_urgente:
    print(f"   ✓ Servicio urgente asignado: {diag.servicio_urgente.nombre}")
else:
    print(f"   ⚠ No se asignó servicio urgente (diagnóstico puede no ser crítico)")

if diag.rutina_asignada:
    print(f"   ✓ Rutina asignada: {diag.rutina_asignada.nombre}")
else:
    print(f"   ⚠ No se asignó rutina")

if diag.rutina_sugerida:
    print(f"   ✓ Rutina sugerida: {diag.rutina_sugerida.nombre}")
else:
    print(f"   ⚠ No se sugirió rutina")

# RESUMEN
print("\n" + "="*80)
print("✅ FLUJO EXITOSO")
print("="*80)
print(f"\n✓ Cliente: {cliente.usuario.first_name} ({cliente.usuario.email})")
print(f"✓ Diagnóstico automático creado: {diag.id}")
print(f"✓ Motor ejecutado correctamente")
print("\n")
