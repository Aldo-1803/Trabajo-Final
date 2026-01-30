#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import DiagnosticoCapilar, Notificacion

# Obtener el ultimo diagnostico creado
diag = DiagnosticoCapilar.objects.order_by('-fecha_diagnostico').first()

if not diag:
    print("NO HAY DIAGNOSTICOS EN LA BD")
    exit()

print("\n" + "="*80)
print("DIAGNOSTICO MAS RECIENTE")
print("="*80)

print(f"\nID: {diag.id}")
print(f"Cliente: {diag.cliente.usuario.email}")
print(f"Fecha: {diag.fecha_diagnostico}")

# Mostrar atributos seleccionados
print(f"\nAtributos:")
print(f"  - Tipo cabello: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'N/A'} ({diag.tipo_cabello.puntaje_base if diag.tipo_cabello else 0} pts)")
print(f"  - Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'N/A'} ({diag.grosor_cabello.puntaje_base if diag.grosor_cabello else 0} pts)")
print(f"  - Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'N/A'} ({diag.porosidad_cabello.puntaje_base if diag.porosidad_cabello else 0} pts)")
print(f"  - Cuero cabelludo: {diag.cuero_cabelludo.nombre if diag.cuero_cabelludo else 'N/A'} ({diag.cuero_cabelludo.puntaje_base if diag.cuero_cabelludo else 0} pts)")
print(f"  - Estado general: {diag.estado_general.nombre if diag.estado_general else 'N/A'} ({diag.estado_general.puntaje_base if diag.estado_general else 0} pts)")

# Calcular puntos
puntos = 0
if diag.tipo_cabello:
    puntos += diag.tipo_cabello.puntaje_base
if diag.grosor_cabello:
    puntos += diag.grosor_cabello.puntaje_base
if diag.porosidad_cabello:
    puntos += diag.porosidad_cabello.puntaje_base
if diag.cuero_cabelludo:
    puntos += diag.cuero_cabelludo.puntaje_base
if diag.estado_general:
    puntos += diag.estado_general.puntaje_base

print(f"\n  TOTAL PUNTOS: {puntos}")
if puntos <= 5:
    print(f"    -> CRITICO (deberia buscar turno urgente)")
elif puntos <= 9:
    print(f"    -> ALERTA (nutricion)")
else:
    print(f"    -> SALUDABLE (mantenimiento)")

print(f"\nResultados del motor:")
print(f"  - servicio_urgente: {diag.servicio_urgente}")
print(f"  - rutina_asignada: {diag.rutina_asignada}")
print(f"  - rutina_sugerida: {diag.rutina_sugerida}")
print(f"  - regla_diagnostico: {diag.regla_diagnostico}")

print(f"\nNotificaciones creadas para este cliente:")
notifs = Notificacion.objects.filter(usuario=diag.cliente.usuario).order_by('-fecha_envio')[:10]
if notifs.exists():
    for n in notifs:
        print(f"  - {n.titulo}")
else:
    print(f"  *** NO HAY NOTIFICACIONES ***")

print("\n" + "="*80)
