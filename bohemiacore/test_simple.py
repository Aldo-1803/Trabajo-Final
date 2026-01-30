#!/usr/bin/env python
import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import (
    DiagnosticoCapilar, TipoCabello, GrosorCabello, PorosidadCabello, 
    CueroCabelludo, EstadoGeneral, Notificacion
)
from usuarios.models import Cliente, Usuario
from gestion.views import DiagnosticoCapilarViewSet

print("\n" + "="*80)
print("TEST SIMPLE: Crear diagnostico y ejecutar motor")
print("="*80)

# Obtener cliente
cliente = Cliente.objects.first()
print(f"\n1. Cliente: {cliente.usuario.email}")

# Obtener atributos CRITICOS (2 puntos)
tipo = TipoCabello.objects.get(nombre="Afro")
grosor = GrosorCabello.objects.get(nombre="Fino")
porosidad = PorosidadCabello.objects.get(nombre="Alta")
cuero = CueroCabelludo.objects.get(nombre="Graso")
estado = EstadoGeneral.objects.get(nombre="Dañado")

print(f"\n2. Atributos seleccionados:")
print(f"   - Tipo: {tipo.nombre} ({tipo.puntaje_base} pts)")
print(f"   - Grosor: {grosor.nombre} ({grosor.puntaje_base} pts)")
print(f"   - Porosidad: {porosidad.nombre} ({porosidad.puntaje_base} pts)")
print(f"   - Cuero: {cuero.nombre} ({cuero.puntaje_base} pts)")
print(f"   - Estado: {estado.nombre} ({estado.puntaje_base} pts)")
print(f"   TOTAL: {tipo.puntaje_base + grosor.puntaje_base + porosidad.puntaje_base + cuero.puntaje_base + estado.puntaje_base} pts")

# Crear diagnostico
print(f"\n3. Creando diagnostico...")
diag = DiagnosticoCapilar.objects.create(
    cliente=cliente,
    tipo_cabello=tipo,
    grosor_cabello=grosor,
    porosidad_cabello=porosidad,
    cuero_cabelludo=cuero,
    estado_general=estado
)
print(f"   OK - Diagnostico ID: {diag.id}")

# Ejecutar motor manualmente
print(f"\n4. Ejecutando motor diagnostico...")
viewset = DiagnosticoCapilarViewSet()
viewset._ejecutar_motor_diagnostico(diag)

# Verificar resultados
print(f"\n5. Resultados en BD:")
diag.refresh_from_db()
print(f"   - servicio_urgente: {diag.servicio_urgente}")
print(f"   - rutina_asignada: {diag.rutina_asignada}")
print(f"   - rutina_sugerida: {diag.rutina_sugerida}")

# Verificar notificaciones
print(f"\n6. Notificaciones creadas:")
notifs = Notificacion.objects.filter(usuario=cliente.usuario).order_by('-fecha_envio')[:5]
for n in notifs:
    print(f"   - {n.titulo}")

if not notifs:
    print(f"   NO hay notificaciones para {cliente.usuario.email}")

print("\n" + "="*80)
