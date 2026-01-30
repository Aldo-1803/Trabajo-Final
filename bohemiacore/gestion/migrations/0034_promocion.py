# Generated migration for Promocion model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0033_alter_configuracion_options_configuracionretoque_and_more'),
        ('usuarios', '0002_cliente_rutinas'),
    ]

    operations = [
        migrations.CreateModel(
            name='Promocion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text="Nombre de la promoción (ej: 'Combo Hidratación Profunda')", max_length=100)),
                ('descripcion', models.TextField(help_text='Descripción detallada de la promoción')),
                ('tipo', models.CharField(choices=[('COMBO', 'Combo de Productos'), ('RETOQUE', 'Pack Retoque Servicio'), ('LAST_MINUTE', 'Promoción Last Minute')], help_text='Tipo de promoción', max_length=20)),
                ('descuento_porcentaje', models.IntegerField(default=10, help_text='Porcentaje de descuento aplicado')),
                ('fecha_inicio', models.DateField(help_text='Fecha de inicio de la promoción')),
                ('fecha_fin', models.DateField(help_text='Fecha de finalización de la promoción')),
                ('is_active', models.BooleanField(default=True, help_text='Si está activa la promoción')),
                ('hora_inicio_promo', models.TimeField(blank=True, help_text='Hora de inicio si la promoción es por horario específico', null=True)),
                ('hora_fin_promo', models.TimeField(blank=True, help_text='Hora de fin si la promoción es por horario específico', null=True)),
                ('fecha_especifica', models.DateField(blank=True, help_text='Fecha específica si la promoción aplica solo en un día concreto', null=True)),
                ('cliente_especifico', models.ForeignKey(blank=True, help_text='Si se especifica, esta promoción es solo para este cliente (ej: Mantenimiento post-servicio)', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='promociones_personalizadas', to='usuarios.cliente')),
                ('fecha_envio_notificacion', models.DateField(blank=True, help_text='Día en que se enviará el aviso al cliente (para promociones diferidas)', null=True)),
                ('procesada', models.BooleanField(default=False, help_text='Indica si la notificación ya fue enviada al cliente')),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('productos', models.ManyToManyField(blank=True, help_text='Productos incluidos en este combo', related_name='promociones', to='gestion.producto')),
                ('servicios', models.ManyToManyField(blank=True, help_text='Servicios incluidos en este pack/promoción', related_name='promociones', to='gestion.servicio')),
            ],
            options={
                'verbose_name': 'Promoción',
                'verbose_name_plural': 'Promociones',
            },
        ),
    ]
