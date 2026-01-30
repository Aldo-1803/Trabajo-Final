#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import DiagnosticoCapilar, TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral

# Obtener el diagnóstico
diag = DiagnosticoCapilar.objects.get(id=1)

print("\n" + "="*80)
print("CÁLCULO DE PUNTOS DEL DIAGNÓSTICO")
print("="*80)

# Obtener puntajes de cada atributo
tipo_puntaje = diag.tipo_cabello.puntaje_base if diag.tipo_cabello else 0
grosor_puntaje = diag.grosor_cabello.puntaje_base if diag.grosor_cabello else 0
porosidad_puntaje = diag.porosidad_cabello.puntaje_base if diag.porosidad_cabello else 0
cuero_puntaje = diag.cuero_cabelludo.puntaje_base if diag.cuero_cabelludo else 0
estado_puntaje = diag.estado_general.puntaje_base if diag.estado_general else 0

print(f"\nDatos Seleccionados:")
print(f"  Tipo: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'None'} = {tipo_puntaje} pts")
print(f"  Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'None'} = {grosor_puntaje} pts")
print(f"  Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'None'} = {porosidad_puntaje} pts")
print(f"  Cuero Cabelludo: {diag.cuero_cabelludo.nombre if diag.cuero_cabelludo else 'None'} = {cuero_puntaje} pts")
print(f"  Estado General: {diag.estado_general.nombre if diag.estado_general else 'None'} = {estado_puntaje} pts")

total = tipo_puntaje + grosor_puntaje + porosidad_puntaje + cuero_puntaje + estado_puntaje
print(f"\n  TOTAL: {total} puntos")

if total <= 5:
    print(f"  Nivel: CRÍTICO (≤5) -> Debería asignar servicio_urgente y buscar turno")
elif total <= 9:
    print(f"  Nivel: ALERTA (6-9) -> Asignar rutina de Nutrición")
else:
    print(f"  Nivel: SALUDABLE (10+) -> Asignar rutina de Mantenimiento")

print(f"\nDatos en BD:")
print(f"  servicio_urgente: {diag.servicio_urgente}")
print(f"  rutina_asignada: {diag.rutina_asignada}")
print(f"  rutina_sugerida: {diag.rutina_sugerida}")

print("\n" + "="*80)
