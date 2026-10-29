from django.db import migrations


PERMISSIONS = (
    ('usuarios', 'cliente', 'create_walkin_client', 'Can create walk-in clients'),
    ('usuarios', 'cliente', 'view_clients', 'Can view clients'),
    ('usuarios', 'usuario', 'manage_users', 'Can manage users'),
    ('usuarios', 'usuario', 'assign_roles', 'Can assign business roles'),
    ('gestion', 'turno', 'view_global_agenda', 'Can view the global agenda'),
    ('gestion', 'turno', 'create_turno_for_client', 'Can create appointments for clients'),
    ('gestion', 'turno', 'register_arrival', 'Can register client arrival'),
    ('gestion', 'turno', 'reprogram_any_turno', 'Can reschedule any appointment'),
    ('gestion', 'turno', 'cancel_any_turno', 'Can cancel any appointment'),
    ('gestion', 'turno', 'finalize_service', 'Can finalize services'),
    ('gestion', 'turno', 'confirm_deposit', 'Can confirm deposits'),
    ('gestion', 'pago', 'register_payment', 'Can register payments'),
    (
        'gestion',
        'configuracion',
        'manage_payment_configuration',
        'Can manage payment configuration',
    ),
    ('gestion', 'diagnosticocapilar', 'create_diagnosis', 'Can create diagnoses'),
    (
        'gestion',
        'fichatecnica',
        'manage_technical_record',
        'Can manage technical records',
    ),
    ('gestion', 'fichatecnica', 'manage_formulas', 'Can manage formulas'),
    ('gestion', 'rutina', 'assign_routines', 'Can assign routines'),
    ('gestion', 'producto', 'manage_products', 'Can manage products'),
    ('gestion', 'producto', 'view_stock', 'Can view stock'),
    ('gestion', 'producto', 'manage_stock', 'Can manage stock'),
    ('gestion', 'servicio', 'manage_prices', 'Can manage prices'),
    ('gestion', 'promocion', 'manage_promotions', 'Can manage promotions'),
    ('gestion', 'contenidoeducativo', 'manage_content', 'Can manage educational content'),
    ('gestion', 'personal', 'manage_personal', 'Can manage personnel'),
    ('gestion', 'personal', 'manage_skills', 'Can manage personnel skills'),
    ('gestion', 'auditoria', 'view_reports', 'Can view reports'),
    ('gestion', 'auditoria', 'view_financial_reports', 'Can view financial reports'),
    ('gestion', 'auditoria', 'view_audit', 'Can view audit records'),
    ('gestion', 'auditoria', 'revert_audit', 'Can revert audited changes'),
    ('gestion', 'configuracion', 'manage_configuration', 'Can manage configuration'),
)

EMPLOYEE_PERMISSIONS = (
    'usuarios.create_walkin_client',
    'usuarios.view_clients',
    'gestion.view_global_agenda',
    'gestion.create_turno_for_client',
    'gestion.register_arrival',
    'gestion.reprogram_any_turno',
    'gestion.cancel_any_turno',
    'gestion.confirm_deposit',
    'gestion.register_payment',
    'gestion.view_stock',
)

PROFESSIONAL_PERMISSIONS = EMPLOYEE_PERMISSIONS + (
    'gestion.create_diagnosis',
    'gestion.manage_technical_record',
    'gestion.manage_formulas',
    'gestion.assign_routines',
    'gestion.finalize_service',
)

ALL_PERMISSIONS = tuple(
    f'{app_label}.{codename}'
    for app_label, _model, codename, _name in PERMISSIONS
)

ROLE_PERMISSIONS = {
    'CLIENTE': (),
    'EMPLEADO': EMPLOYEE_PERMISSIONS,
    'PROFESIONAL': PROFESSIONAL_PERMISSIONS,
    'ADMINISTRADOR': ALL_PERMISSIONS,
}


def seed_business_roles(apps, schema_editor):
    alias = schema_editor.connection.alias
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')

    permissions_by_label = {}
    for app_label, model, codename, name in PERMISSIONS:
        content_type, _ = ContentType.objects.using(alias).get_or_create(
            app_label=app_label,
            model=model,
        )
        permission, _ = Permission.objects.using(alias).update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={'name': name},
        )
        permissions_by_label[f'{app_label}.{codename}'] = permission

    for role, permission_labels in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.using(alias).get_or_create(name=role)
        group.permissions.set(
            permissions_by_label[label] for label in permission_labels
        )


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0019_role_permissions'),
        ('usuarios', '0002_role_permissions'),
    ]

    operations = [
        migrations.RunPython(
            seed_business_roles,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
