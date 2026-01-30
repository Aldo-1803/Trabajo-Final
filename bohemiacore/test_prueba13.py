#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import (
    DiagnosticoCapilar, TipoCabello, GrosorCabello, PorosidadCabello, 
    CueroCabelludo, EstadoGeneral, Notificacion
)
from usuarios.models import Cliente
from gestion.views import DiagnosticoCapilarViewSet

# Obtener el cliente que creaste
cliente = Cliente.objects.get(usuario__email="prueba13@gmail.com")
print(f"\nCliente encontrado: {cliente.usuario.email}")

# Obtener atributos CRITICOS
tipo = TipoCabello.objects.get(nombre="Afro")
grosor = GrosorCabello.objects.get(nombre="Fino")
porosidad = PorosidadCabello.objects.get(nombre="Alta")
cuero = CueroCabelludo.objects.get(nombre="Graso")
estado = EstadoGeneral.objects.get(nombre="Dañado")

print(f"\nCreando diagnostico con puntuacion CRITICA (2 pts)...")

# Crear diagnostico
diag = DiagnosticoCapilar.objects.create(
    cliente=cliente,
    tipo_cabello=tipo,
    grosor_cabello=grosor,
    porosidad_cabello=porosidad,
    cuero_cabelludo=cuero,
    estado_general=estado
)
print(f"OK - Diagnostico ID: {diag.id}")

# Ejecutar motor
print(f"\nEjecutando motor diagnostico...")
viewset = DiagnosticoCapilarViewSet()
viewset._ejecutar_motor_diagnostico(diag)

# Verificar resultados
diag.refresh_from_db()
print(f"\nResultados:")
print(f"  - servicio_urgente: {diag.servicio_urgente}")
print(f"  - rutina_asignada: {diag.rutina_asignada}")

# Verificar notificaciones
notifs = Notificacion.objects.filter(usuario=cliente.usuario).order_by('-fecha_envio')
print(f"\nNotificaciones creadas: {notifs.count()}")
for n in notifs:
    print(f"  - {n.titulo}")
    if "Recomend" in n.titulo:
        print(f"    Fecha: {n.datos_extra.get('fecha')}")
        print(f"    Hora: {n.datos_extra.get('hora')}")
