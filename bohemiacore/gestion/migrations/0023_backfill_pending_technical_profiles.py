from django.db import migrations


def backfill_pending_technical_profiles(apps, schema_editor):
    Servicio = apps.get_model('gestion', 'Servicio')
    PerfilTecnicoServicio = apps.get_model(
        'gestion', 'PerfilTecnicoServicio'
    )
    alias = schema_editor.connection.alias
    service_ids = (
        Servicio.objects.using(alias)
        .filter(perfil_tecnico__isnull=True)
        .values_list('pk', flat=True)
    )
    for service_id in service_ids.iterator():
        PerfilTecnicoServicio.objects.using(alias).get_or_create(
            servicio_id=service_id,
            defaults={
                'familia_id': None,
                'estado_clasificacion': 'PENDIENTE',
                'nivel_riesgo': 'NO_DEFINIDO',
                'activa': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('gestion', '0022_familiaprocesotecnico_diagnosticocapilar_procedencia_and_more'),
    ]

    operations = [
        migrations.RunPython(
            backfill_pending_technical_profiles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
