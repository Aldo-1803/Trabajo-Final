from django.db import migrations, models
import django.db.models.deletion


SKILLS = (
    ('DIAGNOSTICO', 'Diagnóstico'),
    ('LAVADO', 'Lavado'),
    ('COLORACION', 'Coloración'),
)


def seed_and_backfill_skills(apps, schema_editor):
    Habilidad = apps.get_model('gestion', 'Habilidad')
    Personal = apps.get_model('gestion', 'Personal')
    PersonalHabilidad = apps.get_model('gestion', 'PersonalHabilidad')
    Servicio = apps.get_model('gestion', 'Servicio')
    ServicioHabilidad = apps.get_model('gestion', 'ServicioHabilidad')

    skills = {}
    for code, nombre in SKILLS:
        skill, _ = Habilidad.objects.get_or_create(
            code=code,
            defaults={'nombre': nombre, 'descripcion': '', 'activa': True},
        )
        skills[code] = skill

    legacy_fields = (
        ('realiza_diagnostico', 'DIAGNOSTICO'),
        ('realiza_lavado', 'LAVADO'),
        ('realiza_color', 'COLORACION'),
    )
    for personal in Personal.objects.all().iterator():
        for legacy_field, skill_code in legacy_fields:
            if not getattr(personal, legacy_field):
                continue
            assignment, created = PersonalHabilidad.objects.get_or_create(
                personal_id=personal.pk,
                habilidad_id=skills[skill_code].pk,
                defaults={'activa': True},
            )
            if not created and not assignment.activa:
                assignment.activa = True
                assignment.save(update_fields=['activa'])

    for servicio in Servicio.objects.select_related('categoria').all().iterator():
        categoria = (servicio.categoria.nombre if servicio.categoria_id else '').lower()
        skill_code = None
        if 'diseño' in categoria or 'color' in categoria:
            skill_code = 'COLORACION'
        elif 'complemento' in categoria:
            skill_code = 'LAVADO'
        if skill_code is not None:
            ServicioHabilidad.objects.get_or_create(
                servicio_id=servicio.pk,
                habilidad_id=skills[skill_code].pk,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0020_seed_business_roles'),
    ]

    operations = [
        migrations.CreateModel(
            name='Habilidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True)),
                ('nombre', models.CharField(max_length=100)),
                ('descripcion', models.TextField(blank=True)),
                ('activa', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Habilidad',
                'verbose_name_plural': 'Habilidades',
                'ordering': ['nombre'],
            },
        ),
        migrations.CreateModel(
            name='PersonalHabilidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activa', models.BooleanField(default=True)),
                ('fecha_asignacion', models.DateTimeField(auto_now_add=True)),
                ('habilidad', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='asignaciones_personal', to='gestion.habilidad')),
                ('personal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='habilidades_personal', to='gestion.personal')),
            ],
            options={
                'verbose_name': 'Habilidad de Personal',
                'verbose_name_plural': 'Habilidades de Personal',
            },
        ),
        migrations.CreateModel(
            name='ServicioHabilidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('habilidad', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requisitos_servicio', to='gestion.habilidad')),
                ('servicio', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requisitos_habilidad', to='gestion.servicio')),
            ],
            options={
                'verbose_name': 'Habilidad requerida por Servicio',
                'verbose_name_plural': 'Habilidades requeridas por Servicio',
            },
        ),
        migrations.AddConstraint(
            model_name='personalhabilidad',
            constraint=models.UniqueConstraint(fields=('personal', 'habilidad'), name='unique_personal_habilidad'),
        ),
        migrations.AddField(
            model_name='servicio',
            name='habilidades_requeridas',
            field=models.ManyToManyField(blank=True, related_name='servicios_requeridos', through='gestion.ServicioHabilidad', to='gestion.habilidad'),
        ),
        migrations.AddConstraint(
            model_name='serviciohabilidad',
            constraint=models.UniqueConstraint(fields=('servicio', 'habilidad'), name='unique_servicio_habilidad'),
        ),
        migrations.RunPython(seed_and_backfill_skills, migrations.RunPython.noop),
    ]
