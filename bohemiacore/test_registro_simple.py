"""
Test simple: Verificar que diagnóstico se crea automáticamente al registrar cliente
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from django.contrib.auth import get_user_model
from usuarios.models import Cliente
from gestion.models import DiagnosticoCapilar
from usuarios.serializers import RegistroSerializer
from datetime import datetime

Usuario = get_user_model()

print("\n" + "="*80)
print("TEST SIMPLE: Registro Automático con Diagnóstico")
print("="*80)

# Obtener catálogos de atributos capilares (deben existir ya en la BD)
print("\n[1] Obteniendo catálogos de atributos capilares...")

tipo_rizado = Cliente._meta.get_field('tipo_cabello').related_model.objects.first()
grosor_fino = Cliente._meta.get_field('grosor_cabello').related_model.objects.first()
porosidad_alta = Cliente._meta.get_field('porosidad_cabello').related_model.objects.first()
cuero_seco = Cliente._meta.get_field('cuero_cabelludo').related_model.objects.first()
estado_danado = Cliente._meta.get_field('estado_general').related_model.objects.first()

if not all([tipo_rizado, grosor_fino, porosidad_alta, cuero_seco, estado_danado]):
    print("   ✗ Error: Faltan catálogos de atributos capilares")
    print(f"   - tipo_rizado: {tipo_rizado}")
    print(f"   - grosor_fino: {grosor_fino}")
    print(f"   - porosidad_alta: {porosidad_alta}")
    print(f"   - cuero_seco: {cuero_seco}")
    print(f"   - estado_danado: {estado_danado}")
    raise Exception("Necesitas crear los catálogos de atributos capilares primero")

print(f"   ✓ Tipo cabello: {tipo_rizado.nombre}")
print(f"   ✓ Grosor: {grosor_fino.nombre}")
print(f"   ✓ Porosidad: {porosidad_alta.nombre}")
print(f"   ✓ Cuero cabelludo: {cuero_seco.nombre}")
print(f"   ✓ Estado: {estado_danado.nombre}")

# Datos de registro
print("\n[2] Registrando cliente con datos capilares...")

email_test = f'cliente_test_{datetime.now().timestamp()}@test.com'
registro_data = {
    'email': email_test,
    'password': 'TestPassword123!Secure',
    'password2': 'TestPassword123!Secure',
    'first_name': 'Cliente',
    'last_name': 'Test',
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

# Ejecutar serializer
serializer = RegistroSerializer(data=registro_data)
if serializer.is_valid():
    usuario_nuevo = serializer.save()
    print(f"   ✓ Usuario creado: {usuario_nuevo.email}")
    
    cliente = Cliente.objects.get(usuario=usuario_nuevo)
    print(f"   ✓ Cliente creado: {cliente.usuario.first_name} {cliente.usuario.last_name}")
else:
    print(f"   ✗ Error: {serializer.errors}")
    raise Exception(serializer.errors)

# Verificar diagnóstico automático
print("\n[3] Verificando creación automática del diagnóstico...")

diagnosticos = DiagnosticoCapilar.objects.filter(cliente=cliente).order_by('-fecha_diagnostico')

if diagnosticos.exists():
    diag = diagnosticos.first()
    print(f"   ✓ Diagnóstico CREADO AUTOMÁTICAMENTE: {diag.id}")
    print(f"   - Fecha: {diag.fecha_diagnostico}")
    print(f"   - Tipo cabello: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'N/A'}")
    print(f"   - Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'N/A'}")
    print(f"   - Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'N/A'}")
    print(f"   - Cuero cabelludo: {diag.cuero_cabelludo.nombre if diag.cuero_cabelludo else 'N/A'}")
    print(f"   - Estado: {diag.estado_general.nombre if diag.estado_general else 'N/A'}")
else:
    print("   ✗ FALLÓ: No se creó diagnóstico automáticamente")
    raise Exception("El diagnóstico debería haberse creado automáticamente")

# Verificar que el motor se ejecutó
print("\n[4] Verificando ejecución del motor diagnóstico...")

if diag.servicio_urgente:
    print(f"   ✓ Motor ejecutado: Servicio urgente asignado = {diag.servicio_urgente.nombre}")
else:
    print("   ⚠ No se asignó servicio urgente (podría no ser crítico)")

if diag.rutina_asignada:
    print(f"   ✓ Rutina asignada: {diag.rutina_asignada.nombre}")
else:
    print("   ⚠ No se asignó rutina")

# Mostrar el mensaje profesional generado
print("\n[5] Mensaje Profesional Generado:")
if diag.observaciones:
    print(f"   {diag.observaciones}")
else:
    print("   ⚠ No hay mensaje generado")

print("\n" + "="*80)
print("✅ TEST EXITOSO - REGISTRO CON DIAGNÓSTICO AUTOMÁTICO FUNCIONA")
print("="*80 + "\n")
