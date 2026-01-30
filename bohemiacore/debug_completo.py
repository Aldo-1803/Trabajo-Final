#!/usr/bin/env python
import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bohemiacore.settings')
django.setup()

from gestion.models import (
    DiagnosticoCapilar, Personal, HorarioLaboral, Servicio, 
    Notificacion, RutinaCliente, DiasSemana
)
from usuarios.models import Usuario

print("\n" + "="*80)
print("DEBUG: Análisis Completo de Diagnóstico y Configuración")
print("="*80)

# 1. VERIFICAR ÚLTIMO DIAGNÓSTICO
print("\n1. ÚLTIMO DIAGNÓSTICO CREADO:")
diag = DiagnosticoCapilar.objects.last()
if diag:
    print(f"   ID: {diag.id}")
    print(f"   Cliente: {diag.cliente.usuario.email}")
    print(f"   Tipo: {diag.tipo_cabello.nombre if diag.tipo_cabello else 'None'}")
    print(f"   Grosor: {diag.grosor_cabello.nombre if diag.grosor_cabello else 'None'}")
    print(f"   Porosidad: {diag.porosidad_cabello.nombre if diag.porosidad_cabello else 'None'}")
    print(f"   Cuero Cabelludo: {diag.cuero_cabelludo.nombre if diag.cuero_cabelludo else 'None'}")
    print(f"   Estado General: {diag.estado_general.nombre if diag.estado_general else 'None'}")
    print(f"   Regladura: {diag.regla_diagnostico}")
    print(f"   Rutina Sugerida: {diag.rutina_sugerida}")
else:
    print("   ❌ NO hay diagnósticos")
    diag = None

# 2. VERIFICAR SI EXISTE RUTINACLIE NTE PARA ESTE CLIENTE
print("\n2. RUTINASCLIENTE PARA ESTE CLIENTE:")
if diag:
    rcs = RutinaCliente.objects.filter(cliente=diag.cliente)
    if rcs.exists():
        for rc in rcs:
            rutina_name = rc.rutina_original.nombre if rc.rutina_original else rc.nombre
            print(f"   - {rutina_name} (ID: {rc.id})")
    else:
        print("   ❌ NO hay RutinaCliente creada (motor NO ejecutado completamente)")
else:
    print("   Saltado (no hay diagnóstico)")

# 3. VERIFICAR PERSONAL CON SKILLS
print("\n3. PERSONAL CON SKILLS DE DIAGNÓSTICO:")
personal_list = Personal.objects.filter(realiza_diagnostico=True)
if personal_list.exists():
    for p in personal_list:
        print(f"   ✓ {p.nombre} - rol: {p.rol}")
else:
    print("   ❌ NO hay personal con realiza_diagnostico=True")

# 4. VERIFICAR HORARIOS PARA ESTA SEMANA
print("\n4. HORARIOS LABORALES CONFIGURADOS:")
horarios = HorarioLaboral.objects.all()
print(f"   Total: {horarios.count()}")
if horarios.exists():
    for h in horarios[:5]:  # Primeros 5
        dia_label = DiasSemana(h.dia_semana).label
        print(f"   - {h.personal.nombre if h.personal else 'NO PERSONAL'}: {dia_label} {h.hora_inicio}-{h.hora_fin} " +
              f"(Diseño: {h.permite_diseno_color}, Complemento: {h.permite_complemento})")
else:
    print("   ❌ NO hay horarios configurados")

# 5. VERIFICAR PRÓXIMA FECHA QUE CORRESPONDE A MAÑANA
print("\n5. BÚSQUEDA DE HORARIOS PARA MAÑANA:")
mañana = date.today() + timedelta(days=1)
dia_semana_num = mañana.weekday()
dia_label = DiasSemana(dia_semana_num).label

print(f"   Fecha: {mañana} ({dia_label})")
horarios_mañana = HorarioLaboral.objects.filter(
    activo=True,
    dia_semana=dia_semana_num,
    personal__isnull=False
)
print(f"   Horarios encontrados: {horarios_mañana.count()}")
for h in horarios_mañana:
    print(f"      - {h.personal.nombre}: {h.hora_inicio}-{h.hora_fin}")

# 6. VERIFICAR SERVICIOS CATEGORÍA
print("\n6. SERVICIOS CON CATEGORÍA (para filtrado):")
servicios = Servicio.objects.filter(categoria__isnull=False)
print(f"   Total: {servicios.count()}")
for s in servicios[:3]:
    print(f"   - {s.nombre}: {s.categoria.nombre} ({s.duracion_estimada} min)")

# 7. VERIFICAR NOTIFICACIONES CREADAS HOY
print("\n7. NOTIFICACIONES CREADAS HOY:")
from django.utils import timezone
hoy = timezone.now().date()
notifs_hoy = Notificacion.objects.filter(fecha_envio__date=hoy)
print(f"   Total: {notifs_hoy.count()}")
for n in notifs_hoy.order_by('-fecha_envio')[:5]:
    print(f"   - {n.usuario.email}: {n.titulo}")

print("\n" + "="*80)
