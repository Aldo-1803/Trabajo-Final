#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import DiagnosticoCapilar, RutinaCliente, Notificacion

# Check latest diagnostico
diag = DiagnosticoCapilar.objects.last()
print(f"Diagnostico ID: {diag.id}")
print(f"Cliente: {diag.cliente.usuario.email}")
print(f"Tipo: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'None'}")
print(f"Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'None'}")
print(f"Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'None'}")
print(f"Cuero cabelludo: {diag.cuero_cabelludo_cabello.nombre if diag.cuero_cabelludo_cabello else 'None'}")
print(f"Estado general: {diag.estado_general_cabello.nombre if diag.estado_general_cabello else 'None'}")
print(f"Regladura: {diag.regladura_utilizada.regla_id if diag.regladura_utilizada else 'None'}")
print(f"Servicio urgente: {diag.servicio_urgente.nombre if diag.servicio_urgente else 'None'}")
print(f"Rutina asignada: {diag.rutina_asignada.id if diag.rutina_asignada else 'None'}")

# Check for RutinaCliente created
rc = RutinaCliente.objects.filter(cliente=diag.cliente).last()
if rc:
    print(f"\nRutinaCliente encontrada:")
    print(f"  ID: {rc.id}")
    print(f"  Rutina: {rc.rutina.nombre}")
else:
    print("\nNO RutinaCliente encontrada")

# Check for recommendation notification
notif = Notificacion.objects.filter(usuario=diag.cliente.usuario, titulo__icontains='Recomend').first()
if notif:
    print(f"\nNotificacion encontrada: {notif.titulo}")
    print(f"  Datos: {notif.datos_extra}")
else:
    print("\nNO Notificacion de recomendacion encontrada")
