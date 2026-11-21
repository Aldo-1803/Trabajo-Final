from decimal import Decimal

from django.apps import apps
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken

from gestion.models import (
    Auditoria,
    Configuracion,
    OrdenPendiente,
    Personal,
    Producto,
    TipoCabello,
)
from gestion.middleware import _thread_locals
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole


class DjangoAdminHttpSecurityTests(TestCase):
    password = 'AdminHTTP!2026'

    business_admin_labels = (
        'gestion.auditoria',
        'gestion.bloqueoagenda',
        'gestion.categoriaproducto',
        'gestion.categoriaservicio',
        'gestion.compromisostock',
        'gestion.configuracion',
        'gestion.contenidoeducativo',
        'gestion.contenidoguardado',
        'gestion.cuerocabelludo',
        'gestion.diagnosticocapilar',
        'gestion.equipamiento',
        'gestion.estadogeneral',
        'gestion.fichatecnica',
        'gestion.grosorcabello',
        'gestion.horariolaboral',
        'gestion.imagenproducto',
        'gestion.megusta',
        'gestion.movimientostock',
        'gestion.ordenpendiente',
        'gestion.personal',
        'gestion.porosidadcabello',
        'gestion.producto',
        'gestion.promocion',
        'gestion.regladiagnostico',
        'gestion.requisitoservicio',
        'gestion.rutina',
        'gestion.rutinacliente',
        'gestion.servicio',
        'gestion.tipocabello',
        'gestion.tipoequipamiento',
        'usuarios.cliente',
        'usuarios.usuario',
    )
    technical_admin_labels = (
        'gestion.notificacion',
        'token_blacklist.blacklistedtoken',
        'token_blacklist.outstandingtoken',
    )
    read_only_admin_labels = (
        'usuarios.usuario',
        'usuarios.cliente',
        'gestion.rutina',
        'gestion.notificacion',
        'gestion.rutinacliente',
        'gestion.configuracion',
        'gestion.personal',
        'gestion.horariolaboral',
        'gestion.bloqueoagenda',
        'gestion.fichatecnica',
        'gestion.diagnosticocapilar',
        'gestion.megusta',
        'gestion.contenidoguardado',
        'gestion.auditoria',
        'gestion.movimientostock',
        'gestion.compromisostock',
        'gestion.ordenpendiente',
        'token_blacklist.blacklistedtoken',
        'token_blacklist.outstandingtoken',
    )

    def setUp(self):
        _thread_locals.user = None
        _thread_locals.request = None
        self.anonymous = Client()
        self.client_user = self.user_with_role(
            'admin-http-client@test.com',
            BusinessRole.CLIENTE,
        )
        self.employee = self.user_with_role(
            'admin-http-employee@test.com',
            BusinessRole.EMPLEADO,
        )
        self.professional = self.user_with_role(
            'admin-http-professional@test.com',
            BusinessRole.PROFESIONAL,
        )
        self.business_administrator = self.user_with_role(
            'admin-http-business-admin@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        self.staff_without_permissions = self.create_user(
            'admin-http-staff-empty@test.com',
            is_staff=True,
        )
        self.staff_model_only = self.create_user(
            'admin-http-staff-model@test.com',
            is_staff=True,
        )
        self.staff_business_only = self.create_user(
            'admin-http-staff-business@test.com',
            is_staff=True,
        )
        self.staff_with_both = self.create_user(
            'admin-http-staff-both@test.com',
            is_staff=True,
        )
        self.superuser = Usuario.objects.create_superuser(
            email='admin-http-superuser@test.com',
            password=self.password,
        )
        self.inactive_staff = self.create_user(
            'admin-http-inactive@test.com',
            is_staff=True,
            is_active=False,
        )

        self.grant_business_catalog(self.staff_business_only)
        self.grant_business_catalog(self.staff_with_both)
        for label in self.business_admin_labels + self.technical_admin_labels:
            self.grant_model_permission(self.staff_model_only, label, 'view')
            self.grant_model_permission(self.staff_with_both, label, 'view')

    def tearDown(self):
        _thread_locals.user = None
        _thread_locals.request = None
        super().tearDown()

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password=self.password,
            **extra_fields,
        )

    def user_with_role(self, email, role):
        user = self.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    @staticmethod
    def clear_permission_cache(user):
        for cache_name in (
            '_perm_cache',
            '_user_perm_cache',
            '_group_perm_cache',
        ):
            user.__dict__.pop(cache_name, None)

    def grant_business_catalog(self, user):
        permissions = []
        for permission_name in BusinessPermission.ALL:
            app_label, codename = permission_name.split('.', 1)
            permissions.append(Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            ))
        user.user_permissions.add(*permissions)
        self.clear_permission_cache(user)

    def grant_business_permission(self, user, permission_name):
        app_label, codename = permission_name.split('.', 1)
        user.user_permissions.add(Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        ))
        self.clear_permission_cache(user)

    def grant_model_permission(self, user, label, operation):
        model = apps.get_model(label)
        user.user_permissions.add(Permission.objects.get(
            content_type__app_label=model._meta.app_label,
            content_type__model=model._meta.model_name,
            codename=f'{operation}_{model._meta.model_name}',
        ))
        self.clear_permission_cache(user)

    @staticmethod
    def admin_url(label, operation, obj=None):
        app_label, model_name = label.split('.', 1)
        name = f'admin:{app_label}_{model_name}_{operation}'
        return reverse(name, args=[obj.pk] if obj is not None else None)

    @staticmethod
    def authenticated_client(user):
        client = Client()
        client.force_login(user)
        return client

    def test_registered_modeladmin_inventory_and_excluded_sensitive_models(self):
        registered_labels = {
            model._meta.label_lower
            for model in admin.site._registry
        }

        self.assertSetEqual(
            registered_labels,
            set(self.business_admin_labels + self.technical_admin_labels),
        )
        self.assertNotIn(Group, admin.site._registry)
        self.assertNotIn(Permission, admin.site._registry)
        for label in (
            'gestion.habilidad',
            'gestion.personalhabilidad',
            'gestion.turno',
            'gestion.ordencompra',
            'gestion.pago',
            'gestion.paymentpolicy',
            'gestion.paymentintent',
            'gestion.paymentintentline',
            'gestion.paymentreconciliationcase',
            'gestion.financialresolutionrequest',
            'gestion.financialresolutiondecision',
            'gestion.financialrefundoperation',
            'gestion.financialrefundoperationevent',
            'gestion.financialadjustment',
            'gestion.financialresolutionevent',
            'gestion.financialcaseclosure',
        ):
            with self.subTest(label=label):
                self.assertNotIn(apps.get_model(label), admin.site._registry)

    def test_login_and_index_keep_staff_as_technical_gate(self):
        login_url = reverse('admin:login')
        index_url = reverse('admin:index')

        self.assertEqual(self.anonymous.get(login_url).status_code, 200)
        self.assertEqual(self.anonymous.get(index_url).status_code, 302)

        for actor in (
            self.client_user,
            self.employee,
            self.professional,
            self.business_administrator,
        ):
            with self.subTest(actor=actor.email):
                client = Client()
                response = client.post(login_url, {
                    'username': actor.email,
                    'password': self.password,
                    'next': index_url,
                })
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('_auth_user_id', client.session)
                client.force_login(actor)
                self.assertEqual(client.get(index_url).status_code, 302)

        staff_client = Client()
        staff_login = staff_client.post(login_url, {
            'username': self.staff_without_permissions.email,
            'password': self.password,
            'next': index_url,
        })
        self.assertEqual(staff_login.status_code, 302)
        self.assertEqual(staff_client.get(index_url).status_code, 200)

        inactive_client = Client()
        inactive_login = inactive_client.post(login_url, {
            'username': self.inactive_staff.email,
            'password': self.password,
            'next': index_url,
        })
        self.assertEqual(inactive_login.status_code, 200)
        self.assertNotIn('_auth_user_id', inactive_client.session)

        superuser_client = Client()
        superuser_login = superuser_client.post(login_url, {
            'username': self.superuser.email,
            'password': self.password,
            'next': index_url,
        })
        self.assertEqual(superuser_login.status_code, 302)
        self.assertEqual(superuser_client.get(index_url).status_code, 200)

    def test_every_business_changelist_requires_model_and_business_permissions(self):
        model_only = self.authenticated_client(self.staff_model_only)
        business_only = self.authenticated_client(self.staff_business_only)
        authorized = self.authenticated_client(self.staff_with_both)
        technical = self.authenticated_client(self.superuser)

        for label in self.business_admin_labels:
            url = self.admin_url(label, 'changelist')
            with self.subTest(label=label, actor='model-only'):
                self.assertEqual(model_only.get(url).status_code, 403)
            with self.subTest(label=label, actor='business-only'):
                self.assertEqual(business_only.get(url).status_code, 403)
            with self.subTest(label=label, actor='both'):
                self.assertEqual(authorized.get(url).status_code, 200)
            with self.subTest(label=label, actor='superuser'):
                self.assertEqual(technical.get(url).status_code, 200)

    def test_technical_changelists_are_superuser_only(self):
        regular_staff = self.authenticated_client(self.staff_with_both)
        technical = self.authenticated_client(self.superuser)

        for label in self.technical_admin_labels:
            url = self.admin_url(label, 'changelist')
            with self.subTest(label=label, actor='regular-staff'):
                self.assertEqual(regular_staff.get(url).status_code, 403)
            with self.subTest(label=label, actor='superuser'):
                self.assertEqual(technical.get(url).status_code, 200)

    def test_read_only_admins_reject_add_get_and_post_even_for_superuser(self):
        client = self.authenticated_client(self.superuser)

        for label in self.read_only_admin_labels:
            url = self.admin_url(label, 'add')
            with self.subTest(label=label, method='GET'):
                self.assertEqual(client.get(url).status_code, 403)
            with self.subTest(label=label, method='POST'):
                self.assertEqual(client.post(url, {'name': 'forged'}).status_code, 403)

    def test_group_and_permission_admin_urls_are_not_exposed(self):
        client = self.authenticated_client(self.superuser)

        self.assertEqual(client.get('/admin/auth/group/').status_code, 404)
        self.assertEqual(client.post('/admin/auth/group/add/', {}).status_code, 404)
        self.assertEqual(client.get('/admin/auth/permission/').status_code, 404)
        self.assertEqual(
            client.post('/admin/auth/permission/add/', {}).status_code,
            404,
        )

    def test_user_client_personal_and_last_admin_cannot_be_forged(self):
        actor = self.staff_with_both
        for label in (
            'usuarios.usuario',
            'usuarios.cliente',
            'gestion.personal',
        ):
            self.grant_model_permission(actor, label, 'change')
            self.grant_model_permission(actor, label, 'delete')

        target = self.create_user('admin-http-target@test.com')
        target.groups.add(Group.objects.get(name=BusinessRole.ADMINISTRADOR))
        technical_group = Group.objects.create(name='ADMIN_HTTP_TECHNICAL')
        target.groups.add(technical_group)
        target.user_permissions.add(Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_prices',
        ))
        target_group_ids = set(target.groups.values_list('pk', flat=True))
        target_permission_ids = set(
            target.user_permissions.values_list('pk', flat=True)
        )
        original_password = target.password
        cliente = Cliente.objects.create(usuario=target, activo=True)
        personal_user = self.create_user('admin-http-personal-target@test.com')
        personal = Personal.objects.create(
            usuario=personal_user,
            nombre='Perfil',
            apellido='Protegido',
            email='perfil-protegido@test.com',
            rol='colorista',
            activo=True,
        )
        client = self.authenticated_client(actor)
        audit_count = Auditoria.objects.count()

        for label, obj in (
            ('usuarios.usuario', target),
            ('usuarios.cliente', cliente),
            ('gestion.personal', personal),
        ):
            with self.subTest(label=label, method='GET'):
                self.assertEqual(
                    client.get(self.admin_url(label, 'change', obj)).status_code,
                    200,
                )

        user_post = client.post(
            self.admin_url('usuarios.usuario', 'change', target),
            {
                'email': 'forged-admin@test.com',
                'password': 'Forged!2026',
                'is_active': '',
                'is_staff': 'on',
                'is_superuser': 'on',
                'groups': [],
                'user_permissions': [],
            },
        )
        password_post = client.post(
            reverse(
                'admin:auth_user_password_change',
                args=[target.pk],
            ),
            {'password1': 'Forged!2026', 'password2': 'Forged!2026'},
        )
        cliente_post = client.post(
            self.admin_url('usuarios.cliente', 'change', cliente),
            {'usuario': personal_user.pk, 'activo': ''},
        )
        personal_post = client.post(
            self.admin_url('gestion.personal', 'change', personal),
            {
                'usuario': target.pk,
                'activo': '',
                'rol': 'administrador',
            },
        )
        delete_post = client.post(
            self.admin_url('usuarios.usuario', 'delete', target),
            {'post': 'yes'},
        )

        for response in (
            user_post,
            password_post,
            cliente_post,
            personal_post,
            delete_post,
        ):
            self.assertEqual(response.status_code, 403)

        target.refresh_from_db()
        cliente.refresh_from_db()
        personal.refresh_from_db()
        self.assertEqual(target.email, 'admin-http-target@test.com')
        self.assertEqual(target.password, original_password)
        self.assertTrue(target.is_active)
        self.assertFalse(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertSetEqual(
            set(target.groups.values_list('pk', flat=True)),
            target_group_ids,
        )
        self.assertSetEqual(
            set(target.user_permissions.values_list('pk', flat=True)),
            target_permission_ids,
        )
        self.assertEqual(cliente.usuario_id, target.pk)
        self.assertTrue(cliente.activo)
        self.assertEqual(personal.usuario_id, personal_user.pk)
        self.assertTrue(personal.activo)
        self.assertEqual(personal.rol, 'colorista')
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_configuration_order_and_audit_are_immutable_through_admin(self):
        actor = self.staff_with_both
        for label in (
            'gestion.configuracion',
            'gestion.ordenpendiente',
            'gestion.auditoria',
        ):
            self.grant_model_permission(actor, label, 'change')
            self.grant_model_permission(actor, label, 'delete')

        configuration = Configuracion.objects.create(
            monto_sena=Decimal('5000.00'),
        )
        target_user = self.create_user('admin-http-order-client@test.com')
        target_client = Cliente.objects.create(usuario=target_user)
        order = OrdenPendiente.objects.create(
            cliente=target_client,
            estado='PENDIENTE',
            items_json=[{'nombre': 'Producto', 'cantidad': 1}],
            monto_total=Decimal('100.00'),
            nota_cliente='Original',
        )
        audit = Auditoria.objects.create(
            tabla='usuarios_usuario',
            registro_id=target_user.pk,
            accion='MODIFICACION',
            valor_anterior={'is_active': True},
            valor_nuevo={'is_active': False},
        )
        client = self.authenticated_client(actor)
        audit_count = Auditoria.objects.count()

        for label, obj in (
            ('gestion.configuracion', configuration),
            ('gestion.ordenpendiente', order),
            ('gestion.auditoria', audit),
        ):
            with self.subTest(label=label, method='GET'):
                self.assertEqual(
                    client.get(self.admin_url(label, 'change', obj)).status_code,
                    200,
                )

        responses = (
            client.post(
                self.admin_url('gestion.configuracion', 'change', configuration),
                {'monto_sena': '1.00', 'max_dias_anticipacion': 1},
            ),
            client.post(
                self.admin_url('gestion.ordenpendiente', 'change', order),
                {'estado': 'COMPLETADA', 'monto_total': '1.00'},
            ),
            client.post(
                self.admin_url('gestion.auditoria', 'change', audit),
                {
                    'tabla': 'auth_group',
                    'valor_nuevo': {'is_superuser': True},
                },
            ),
            client.post(
                self.admin_url('gestion.auditoria', 'delete', audit),
                {'post': 'yes'},
            ),
        )
        self.assertTrue(all(response.status_code == 403 for response in responses))

        configuration.refresh_from_db()
        order.refresh_from_db()
        audit.refresh_from_db()
        self.assertEqual(configuration.monto_sena, Decimal('5000.00'))
        self.assertEqual(order.estado, 'PENDIENTE')
        self.assertEqual(order.monto_total, Decimal('100.00'))
        self.assertEqual(audit.tabla, 'usuarios_usuario')
        self.assertEqual(Auditoria.objects.count(), audit_count)

    def test_product_admin_requires_both_authorities_and_ignores_stock_forgery(self):
        product = Producto.objects.create(
            nombre='Producto protegido',
            marca='Original',
            precio=Decimal('100.00'),
            stock_real=10,
            stock_comprometido=2,
            stock_minimo=3,
        )
        change_url = self.admin_url('gestion.producto', 'change', product)
        model_only_client = self.authenticated_client(self.staff_model_only)
        business_only_client = self.authenticated_client(self.staff_business_only)
        audit_count = Auditoria.objects.count()

        self.grant_model_permission(
            self.staff_model_only,
            'gestion.producto',
            'change',
        )
        model_only_response = model_only_client.post(
            change_url,
            {'nombre': 'Model only', 'stock_real': 999},
        )

        self.grant_business_permission(
            self.staff_business_only,
            BusinessPermission.MANAGE_PRODUCTS,
        )
        business_only_response = business_only_client.post(
            change_url,
            {'nombre': 'Business only', 'stock_real': 999},
        )

        self.assertEqual(model_only_response.status_code, 403)
        self.assertEqual(business_only_response.status_code, 403)
        product.refresh_from_db()
        self.assertEqual(product.nombre, 'Producto protegido')
        self.assertEqual(product.stock_real, 10)
        self.assertEqual(Auditoria.objects.count(), audit_count)

        editor = self.create_user(
            'admin-http-product-editor@test.com',
            is_staff=True,
        )
        self.grant_business_permission(editor, BusinessPermission.MANAGE_PRODUCTS)
        self.grant_model_permission(editor, 'gestion.producto', 'view')
        self.grant_model_permission(editor, 'gestion.producto', 'change')
        editor_client = self.authenticated_client(editor)
        self.assertEqual(editor_client.get(change_url).status_code, 200)

        accepted = editor_client.post(change_url, {
            'sku': product.sku,
            'nombre': 'Metadato autorizado',
            'marca': 'Actualizada',
            'categoria': '',
            'descripcion': 'Descripción segura',
            'precio': '9999.00',
            'stock_real': 999,
            'stock_comprometido': 500,
            'stock_minimo': 0,
            'imagen': '',
            'compatibilidad': 'TODO',
            'estado_publicacion': 'PUBLICADO',
            'activo': 'on',
            'imagenes-TOTAL_FORMS': '0',
            'imagenes-INITIAL_FORMS': '0',
            'imagenes-MIN_NUM_FORMS': '0',
            'imagenes-MAX_NUM_FORMS': '1000',
        })

        self.assertEqual(accepted.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.nombre, 'Metadato autorizado')
        self.assertEqual(product.precio, Decimal('100.00'))
        self.assertEqual(product.stock_real, 10)
        self.assertEqual(product.stock_comprometido, 2)
        self.assertEqual(product.stock_minimo, 3)

    def test_product_add_uses_model_and_business_permissions_but_not_stock(self):
        actor = self.staff_with_both
        self.grant_model_permission(actor, 'gestion.producto', 'add')
        add_url = self.admin_url('gestion.producto', 'add')
        client = self.authenticated_client(actor)

        response = client.post(add_url, {
            'sku': 'ADMIN-HTTP-NEW',
            'nombre': 'Producto creado de forma controlada',
            'marca': 'Marca',
            'categoria': '',
            'descripcion': '',
            'precio': '150.00',
            'stock_real': 900,
            'stock_comprometido': 800,
            'stock_minimo': 0,
            'imagen': '',
            'compatibilidad': 'TODO',
            'estado_publicacion': 'PUBLICADO',
            'activo': 'on',
            'imagenes-TOTAL_FORMS': '0',
            'imagenes-INITIAL_FORMS': '0',
            'imagenes-MIN_NUM_FORMS': '0',
            'imagenes-MAX_NUM_FORMS': '1000',
        })

        self.assertEqual(response.status_code, 302)
        product = Producto.objects.get(sku='ADMIN-HTTP-NEW')
        self.assertEqual(product.precio, Decimal('150.00'))
        self.assertEqual(product.stock_real, 0)
        self.assertEqual(product.stock_comprometido, 0)
        self.assertEqual(product.stock_minimo, 5)

    def test_mass_delete_action_is_disabled_for_writable_admins(self):
        actor = self.staff_with_both
        for operation in ('add', 'change', 'delete'):
            self.grant_model_permission(
                actor,
                'gestion.tipocabello',
                operation,
            )
            self.grant_model_permission(
                actor,
                'gestion.producto',
                operation,
            )
        hair_type = TipoCabello.objects.create(
            nombre='Tipo protegido de acción',
            puntaje_base=1,
        )
        product = Producto.objects.create(
            nombre='Producto protegido de acción',
            precio=Decimal('50.00'),
        )
        client = self.authenticated_client(actor)

        for label, obj in (
            ('gestion.tipocabello', hair_type),
            ('gestion.producto', product),
        ):
            response = client.post(
                self.admin_url(label, 'changelist'),
                {
                    'action': 'delete_selected',
                    '_selected_action': [obj.pk],
                },
            )
            with self.subTest(label=label):
                self.assertEqual(response.status_code, 200)
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())

    def test_authorized_catalog_crud_remains_available_without_bulk_actions(self):
        actor = self.staff_with_both
        for operation in ('add', 'change', 'delete'):
            self.grant_model_permission(
                actor,
                'gestion.tipocabello',
                operation,
            )
        client = self.authenticated_client(actor)
        add_url = self.admin_url('gestion.tipocabello', 'add')

        self.assertEqual(client.get(add_url).status_code, 200)
        created = client.post(add_url, {
            'nombre': 'Tipo HTTP',
            'descripcion': 'Creado por admin contenido',
            'activo': 'on',
            'puntaje_base': 3,
        })
        self.assertEqual(created.status_code, 302)
        hair_type = TipoCabello.objects.get(nombre='Tipo HTTP')

        changed = client.post(
            self.admin_url('gestion.tipocabello', 'change', hair_type),
            {
                'nombre': 'Tipo HTTP actualizado',
                'descripcion': 'Actualizado',
                'activo': 'on',
                'puntaje_base': 4,
            },
        )
        self.assertEqual(changed.status_code, 302)
        hair_type.refresh_from_db()
        self.assertEqual(hair_type.nombre, 'Tipo HTTP actualizado')

        deleted = client.post(
            self.admin_url('gestion.tipocabello', 'delete', hair_type),
            {'post': 'yes'},
        )
        self.assertEqual(deleted.status_code, 302)
        self.assertFalse(TipoCabello.objects.filter(pk=hair_type.pk).exists())

    def test_token_blacklist_admin_is_immutable_and_technical_only(self):
        refresh = RefreshToken.for_user(self.client_user)
        refresh.blacklist()
        outstanding = apps.get_model(
            'token_blacklist.outstandingtoken'
        ).objects.get(jti=refresh['jti'])
        blacklisted = apps.get_model(
            'token_blacklist.blacklistedtoken'
        ).objects.get(token=outstanding)
        regular = self.authenticated_client(self.staff_with_both)
        technical = self.authenticated_client(self.superuser)

        for label, obj in (
            ('token_blacklist.outstandingtoken', outstanding),
            ('token_blacklist.blacklistedtoken', blacklisted),
        ):
            change_url = self.admin_url(label, 'change', obj)
            delete_url = self.admin_url(label, 'delete', obj)
            with self.subTest(label=label, actor='regular'):
                self.assertEqual(regular.get(change_url).status_code, 403)
            with self.subTest(label=label, actor='superuser-get'):
                self.assertEqual(technical.get(change_url).status_code, 200)
            with self.subTest(label=label, actor='superuser-post'):
                self.assertEqual(
                    technical.post(change_url, {'token': outstanding.pk}).status_code,
                    403,
                )
            with self.subTest(label=label, actor='superuser-delete'):
                self.assertEqual(
                    technical.post(delete_url, {'post': 'yes'}).status_code,
                    403,
                )

        self.assertTrue(
            type(outstanding).objects.filter(pk=outstanding.pk).exists()
        )
        self.assertTrue(
            type(blacklisted).objects.filter(pk=blacklisted.pk).exists()
        )
