from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0018_alter_agendacuidados_options_and_more'),  # ← Ajusta si la última es otra
    ]

    operations = [
        migrations.AddField(
            model_name='horariolaboral',
            name='permite_diseno_color',
            field=models.BooleanField(default=True, help_text='Si se tilda, Yani puede recibir servicios largos (Diseño) en este horario.'),
        ),
        migrations.AddField(
            model_name='horariolaboral',
            name='permite_complemento',
            field=models.BooleanField(default=True, help_text='Si se tilda, se permiten servicios cortos (Corte, Nutrición).'),
        ),
        migrations.AddField(
            model_name='horariolaboral',
            name='activo',
            field=models.BooleanField(default=True),
        ),
    ]