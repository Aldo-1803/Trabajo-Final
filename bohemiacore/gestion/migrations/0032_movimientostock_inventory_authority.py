import warnings

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def preflight_and_create_opening_balances(apps, schema_editor):
    Producto = apps.get_model('gestion', 'Producto')
    MovimientoStock = apps.get_model('gestion', 'MovimientoStock')
    alias = schema_editor.connection.alias

    negative_minimum_ids = list(
        Producto.objects.using(alias)
        .filter(stock_minimo__lt=0)
        .order_by('pk')
        .values_list('pk', flat=True)[:50]
    )
    if negative_minimum_ids:
        raise RuntimeError(
            'BH-058 D1 preflight: existen Productos con stock_minimo negativo. '
            f'Corrija explícitamente los IDs {negative_minimum_ids} antes de '
            'aplicar la migración; no se modificarán silenciosamente.'
        )

    inconsistent_commitment_ids = list(
        Producto.objects.using(alias)
        .filter(stock_comprometido__gt=models.F('stock_real'))
        .order_by('pk')
        .values_list('pk', flat=True)[:50]
    )
    if inconsistent_commitment_ids:
        warnings.warn(
            'BH-058 D1 preflight: stock_comprometido supera stock_real en los '
            f'Productos {inconsistent_commitment_ids}. D1 no altera ni oculta '
            'esta deuda legacy; su migración corresponde a D2.',
            RuntimeWarning,
        )

    openings = []
    for product in (
        Producto.objects.using(alias)
        .filter(stock_real__gt=0)
        .order_by('pk')
        .iterator()
    ):
        openings.append(MovimientoStock(
            producto_id=product.pk,
            delta=product.stock_real,
            tipo='OPENING_BALANCE',
            reason_code='LEGACY_MIGRATION',
            nota=(
                'Saldo físico legacy preservado por la migración BH-058 D1; '
                'no representa una compra ni una recepción histórica.'
            ),
            actor_kind='SYSTEM',
            actor_id=None,
            reference_type='MIGRATION',
            reference_id='0032',
            idempotency_key=(
                f'opening-balance:0032:product:{product.pk}'
            ),
            stock_before=0,
            stock_after=product.stock_real,
            reverses_movement_id=None,
        ))
    if openings:
        MovimientoStock.objects.using(alias).bulk_create(openings, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0031_paymentintent_confirmation_operation_key_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MovimientoStock',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('delta', models.IntegerField()),
                (
                    'tipo',
                    models.CharField(
                        choices=[
                            ('OPENING_BALANCE', 'Saldo inicial'),
                            ('RECEIPT_IN', 'Recepción'),
                            ('ORDER_SALE_OUT', 'Salida por venta'),
                            ('MANUAL_ADJUSTMENT', 'Ajuste manual'),
                            ('CORRECTION', 'Corrección'),
                        ],
                        max_length=24,
                    ),
                ),
                ('reason_code', models.CharField(max_length=50)),
                ('nota', models.CharField(blank=True, default='', max_length=500)),
                (
                    'actor_kind',
                    models.CharField(
                        choices=[('HUMAN', 'Humano'), ('SYSTEM', 'Sistema')],
                        max_length=10,
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                    ),
                ),
                (
                    'reference_type',
                    models.CharField(blank=True, default='', max_length=50),
                ),
                (
                    'reference_id',
                    models.CharField(blank=True, default='', max_length=100),
                ),
                (
                    'idempotency_key',
                    models.CharField(max_length=128, unique=True),
                ),
                ('stock_before', models.IntegerField()),
                ('stock_after', models.IntegerField()),
                (
                    'actor',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='movimientos_stock',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'producto',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='movimientos_stock',
                        to='gestion.producto',
                    ),
                ),
                (
                    'reverses_movement',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='correction_movements',
                        to='gestion.movimientostock',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Movimiento de stock',
                'verbose_name_plural': 'Movimientos de stock',
                'ordering': ['-created_at', '-pk'],
                'base_manager_name': 'objects',
                'default_manager_name': 'objects',
                'indexes': [
                    models.Index(
                        fields=['producto', '-created_at'],
                        name='stock_move_product_time_idx',
                    ),
                    models.Index(
                        fields=['tipo', '-created_at'],
                        name='stock_move_type_time_idx',
                    ),
                ],
                'constraints': [
                    models.CheckConstraint(
                        condition=~models.Q(delta=0),
                        name='stock_movement_nonzero_delta',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(stock_before__gte=0),
                        name='stock_movement_nonnegative_before',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(stock_after__gte=0),
                        name='stock_movement_nonnegative_after',
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            stock_after=models.F('stock_before') + models.F('delta')
                        ),
                        name='stock_movement_coherent_balance',
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(actor_kind='HUMAN', actor__isnull=False)
                            | models.Q(actor_kind='SYSTEM', actor__isnull=True)
                        ),
                        name='stock_movement_coherent_actor',
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(reason_code=''),
                        name='stock_movement_reason_required',
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(idempotency_key=''),
                        name='stock_movement_key_required',
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(reverses_movement__isnull=True)
                            | ~models.Q(pk=models.F('reverses_movement_id'))
                        ),
                        name='stock_movement_not_self_reversing',
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                tipo='CORRECTION',
                                reverses_movement__isnull=False,
                            )
                            | (
                                ~models.Q(tipo='CORRECTION')
                                & models.Q(reverses_movement__isnull=True)
                            )
                        ),
                        name='stock_movement_correction_reference',
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                tipo__in=['OPENING_BALANCE', 'RECEIPT_IN'],
                                delta__gt=0,
                            )
                            | models.Q(tipo='ORDER_SALE_OUT', delta__lt=0)
                            | models.Q(
                                tipo__in=['MANUAL_ADJUSTMENT', 'CORRECTION']
                            )
                        ),
                        name='stock_movement_fixed_type_sign',
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(reverses_movement__isnull=False),
                        fields=('reverses_movement',),
                        name='stock_movement_one_correction',
                    ),
                ],
            },
        ),
        migrations.RunPython(
            preflight_and_create_opening_balances,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='producto',
            constraint=models.CheckConstraint(
                condition=models.Q(stock_real__gte=0),
                name='product_nonnegative_real_stock',
            ),
        ),
        migrations.AddConstraint(
            model_name='producto',
            constraint=models.CheckConstraint(
                condition=models.Q(stock_minimo__gte=0),
                name='product_nonnegative_minimum_stock',
            ),
        ),
    ]
