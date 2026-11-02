from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('gestion', '0023_backfill_pending_technical_profiles'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='evaluacionriesgotecnico',
            options={
                'base_manager_name': 'objects',
                'default_manager_name': 'objects',
                'ordering': ['-evaluated_at'],
                'permissions': [
                    (
                        'review_technical_booking',
                        'Can review technical bookings',
                    ),
                ],
                'verbose_name': 'Evaluación de riesgo técnico',
                'verbose_name_plural': 'Evaluaciones de riesgo técnico',
            },
        ),
    ]
