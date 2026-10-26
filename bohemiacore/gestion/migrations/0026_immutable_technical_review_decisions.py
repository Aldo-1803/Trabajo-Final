from django.db import migrations, models


def backfill_decision_traceability(apps, schema_editor):
    Decision = apps.get_model('gestion', 'DecisionRevisionTecnica')
    target_states = {
        'APROBAR': 'APROBADA_TECNICAMENTE',
        'RECHAZAR': 'RECHAZADA_TECNICAMENTE',
        'SOLICITAR_INFORMACION': 'INFORMACION_REQUERIDA',
        'RECOMENDAR_OTRA_FECHA': 'EN_REVISION',
    }
    for decision in Decision.objects.select_related(
        'evaluacion__politica'
    ).iterator():
        result_snapshot = decision.evaluacion.result_snapshot or {}
        decision.policy_version = (
            result_snapshot.get('policy_version')
            or decision.evaluacion.politica.version
        )
        decision.estado_anterior = 'EN_REVISION'
        decision.estado_nuevo = target_states[decision.accion]
        decision.save(update_fields=[
            'policy_version',
            'estado_anterior',
            'estado_nuevo',
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0025_solicitudtecnicareserva_decisionrevisiontecnica_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='decisionrevisiontecnica',
            options={
                'base_manager_name': 'objects',
                'default_manager_name': 'objects',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='decisionrevisiontecnica',
            name='estado_anterior',
            field=models.CharField(
                blank=True,
                choices=[
                    ('EVALUANDO', 'Evaluando'),
                    ('ADVERTENCIA_PENDIENTE', 'Advertencia pendiente'),
                    ('APROBADA_TECNICAMENTE', 'Aprobada técnicamente'),
                    ('EN_REVISION', 'En revisión'),
                    ('INFORMACION_REQUERIDA', 'Información requerida'),
                    ('RECHAZADA_TECNICAMENTE', 'Rechazada técnicamente'),
                    ('SUPERADA', 'Superada'),
                    ('VENCIDA', 'Vencida'),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='decisionrevisiontecnica',
            name='estado_nuevo',
            field=models.CharField(
                blank=True,
                choices=[
                    ('EVALUANDO', 'Evaluando'),
                    ('ADVERTENCIA_PENDIENTE', 'Advertencia pendiente'),
                    ('APROBADA_TECNICAMENTE', 'Aprobada técnicamente'),
                    ('EN_REVISION', 'En revisión'),
                    ('INFORMACION_REQUERIDA', 'Información requerida'),
                    ('RECHAZADA_TECNICAMENTE', 'Rechazada técnicamente'),
                    ('SUPERADA', 'Superada'),
                    ('VENCIDA', 'Vencida'),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='decisionrevisiontecnica',
            name='policy_version',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.RunPython(
            backfill_decision_traceability,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='decisionrevisiontecnica',
            name='estado_anterior',
            field=models.CharField(
                choices=[
                    ('EVALUANDO', 'Evaluando'),
                    ('ADVERTENCIA_PENDIENTE', 'Advertencia pendiente'),
                    ('APROBADA_TECNICAMENTE', 'Aprobada técnicamente'),
                    ('EN_REVISION', 'En revisión'),
                    ('INFORMACION_REQUERIDA', 'Información requerida'),
                    ('RECHAZADA_TECNICAMENTE', 'Rechazada técnicamente'),
                    ('SUPERADA', 'Superada'),
                    ('VENCIDA', 'Vencida'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='decisionrevisiontecnica',
            name='estado_nuevo',
            field=models.CharField(
                choices=[
                    ('EVALUANDO', 'Evaluando'),
                    ('ADVERTENCIA_PENDIENTE', 'Advertencia pendiente'),
                    ('APROBADA_TECNICAMENTE', 'Aprobada técnicamente'),
                    ('EN_REVISION', 'En revisión'),
                    ('INFORMACION_REQUERIDA', 'Información requerida'),
                    ('RECHAZADA_TECNICAMENTE', 'Rechazada técnicamente'),
                    ('SUPERADA', 'Superada'),
                    ('VENCIDA', 'Vencida'),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name='decisionrevisiontecnica',
            name='policy_version',
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name='decisionrevisiontecnica',
            name='datos_faltantes',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
