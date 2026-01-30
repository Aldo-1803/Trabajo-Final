#!/usr/bin/env python
"""
Script para probar el flujo completo de diagnóstico + turno recomendado
Ahora usa la API REST en lugar de crear directamente en la BD
"""
import os
import sys
import django
import requests
import json
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import DiagnosticoCapilar, TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral, Notificacion, HorarioLaboral, Servicio
from usuarios.models import Cliente, Usuario
from rest_framework_simplejwt.tokens import RefreshToken

print("\n" + "="*80)
print("[TEST] Iniciando: Diagnostico + Turno Recomendado")
print("="*80 + "\n")

# 1. VERIFICAR SETUP BÁSICO
print("✓ Verificando setup...")
usuarios = Cliente.objects.count()
print(f"  - Clientes en BD: {usuarios}")

# 2. USAR CLIENTE EXISTENTE Y GENERAR TOKEN
if usuarios > 0:
    cliente = Cliente.objects.first()
    usuario = cliente.usuario
    print(f"  - Cliente: {usuario.email}")
    
    # Para crear diagnóstico, necesitamos un usuario staff
    # Buscamos uno que sea staff
    staff_user = Usuario.objects.filter(is_staff=True).first()
    if staff_user:
        print(f"  - Staff/Profesional: {staff_user.email}")
        refresh = RefreshToken.for_user(staff_user)
        token = str(refresh.access_token)
    else:
        print("  ❌ No hay usuario staff para crear diagnósticos")
        sys.exit(1)
    
    print(f"  - Token JWT generado")
else:
    print("  ❌ No hay clientes. Crea uno primero en el admin.")
    sys.exit(1)

# 3. VERIFICAR SERVICIOS DISPONIBLES
servicios = Servicio.objects.filter(nombre__icontains='Tratamiento')
print(f"  - Servicios disponibles: {servicios.count()}")

# 4. PREPARAR DATOS PARA POST
tipo = TipoCabello.objects.filter(activo=True).first()
grosor = GrosorCabello.objects.filter(activo=True).first()
porosidad = PorosidadCabello.objects.filter(activo=True).first()
cuero = CueroCabelludo.objects.filter(activo=True).first()
estado = EstadoGeneral.objects.filter(activo=True).first()

if not all([tipo, grosor, porosidad, cuero, estado]):
    print("  ❌ Faltan catálogos de pelo.")
    sys.exit(1)

print(f"  ✓ Catálogos OK: {tipo.nombre}, {grosor.nombre}, {porosidad.nombre}, {cuero.nombre}, {estado.nombre}")

# 5. CREAR DIAGNÓSTICO VÍA API
print("\n📊 Creando diagnóstico capilar (vía API)...")
payload = {
    "cliente": cliente.pk,  # Usar pk en lugar de id
    "tipo_cabello": tipo.pk,
    "grosor_cabello": grosor.pk,
    "porosidad_cabello": porosidad.pk,
    "cuero_cabelludo": cuero.pk,
    "estado_general": estado.pk
}

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# Variable para almacenar el diagnostico
diag = None

try:
    response = requests.post(
        "http://127.0.0.1:8000/api/gestion/diagnosticos-capilares/",
        json=payload,
        headers=headers,
        timeout=5
    )
    
    if response.status_code in [201, 200]:
        diag_data = response.json()
        print(f"  ✓ Diagnóstico creado vía API (ID: {diag_data.get('id')})")
    else:
        print(f"  ❌ Error en API: {response.status_code}")
        print(f"  Nota: Si ves HTML, el servidor no está sirviendo la API")
        print(f"  Intentando crear diagnóstico directamente en BD...")
        
        # Fallback: crear directamente en la BD pero LLAMANDO AL MOTOR
        from gestion.serializers import DiagnosticoCapilarSerializer
        from gestion.views import DiagnosticoCapilarViewSet
        
        # Crear el diagnóstico de forma que SÍ ejecute el motor
        serializer = DiagnosticoCapilarSerializer(data=payload)
        if serializer.is_valid():
            diag = serializer.save()  # Crear en BD
            
            # Ahora llamar manualmente al motor diagnóstico (lo que perform_create hace)
            viewset = DiagnosticoCapilarViewSet()
            viewset._ejecutar_motor_diagnostico(diag)
            
            print(f"  ✓ Diagnóstico creado en BD (ID: {diag.id})")
        else:
            print(f"  ❌ Error en serializer: {serializer.errors}")
            sys.exit(1)
except requests.exceptions.ConnectionError:
    print("  ⚠️  No se pudo conectar al servidor HTTP, creando diagnóstico en BD...")
    from gestion.serializers import DiagnosticoCapilarSerializer
    from gestion.views import DiagnosticoCapilarViewSet
    
    serializer = DiagnosticoCapilarSerializer(data=payload)
    if serializer.is_valid():
        diag = serializer.save()
        
        # Llamar al motor diagnóstico manualmente
        viewset = DiagnosticoCapilarViewSet()
        viewset._ejecutar_motor_diagnostico(diag)
        
        print(f"  ✓ Diagnóstico creado en BD (ID: {diag.id})")
    else:
        print(f"  ❌ Error en serializer: {serializer.errors}")
        sys.exit(1)
except Exception as e:
    print(f"  ❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 6. ESPERAR UN POCO PARA QUE SE PROCESE
import time
time.sleep(1)

# 7. VERIFICAR NOTIFICACIÓN
print("\n📬 Verificando notificaciones creadas...")
notifs = Notificacion.objects.filter(usuario=usuario).order_by('-fecha_envio')
print(f"  - Total de notificaciones: {notifs.count()}")

# Verificar si hay notificaciones recientes
all_notifs = Notificacion.objects.all().order_by('-fecha_envio')[:10]
print(f"\n  DEBUG: Ultimas 10 notificaciones en el sistema:")
for n in all_notifs:
    print(f"    - {n.usuario.email}: {n.titulo}")

recomendacion = notifs.filter(titulo__icontains='Recomendación').first()
if recomendacion:
    print(f"\n✓ NOTIFICACION DE RECOMENDACION ENCONTRADA")
    print(f"  - Título: {recomendacion.titulo}")
    print(f"  - Mensaje: {recomendacion.mensaje[:70]}...")
    print(f"  - Datos extra: {recomendacion.datos_extra}")
else:
    print(f"\n❌ NO SE ENCONTRÓ NOTIFICACIÓN DE RECOMENDACIÓN")

print("\n" + "="*80)
if recomendacion and recomendacion.datos_extra:
    print("✅ TEST EXITOSO - El flujo completo funcionó!")
    print(f"   Fecha recomendada: {recomendacion.datos_extra.get('fecha')}")
    print(f"   Hora recomendada: {recomendacion.datos_extra.get('hora')}")
else:
    print("❌ TEST FALLIDO - Revisar logs arriba")
print("="*80 + "\n")
