from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from gestion.models import (
    Configuracion,
    ConfiguracionDiagnostico,
    OrdenCompra,
    OrdenItem,
    Producto,
    ReglaDiagnostico,
    Turno,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole


class ConfigurationReportsAuthorizationTests(APITestCase):
    def setUp(self):
        self.manage_configuration = self.permission('manage_configuration')
        self.view_reports = self.permission('view_reports')
        self.view_financial_reports = self.permission(
            'view_financial_reports'
        )

        self.client_user, self.client_profile = self.create_client(
            'config-report-client@test.com',
            first_name='Clienta',
            last_name='Privada',
        )
        self.employee = self.user_with_role(
            'config-report-employee@test.com',
            BusinessRole.EMPLEADO,
        )
        self.professional = self.user_with_role(
            'config-report-professional@test.com',
            BusinessRole.PROFESIONAL,
        )
        self.administrator = self.user_with_role(
            'config-report-admin@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        self.staff_without_permission = self.create_user(
            'config-report-staff@test.com',
            is_staff=True,
        )
        self.configuration_actor = self.create_user(
            'config-only@test.com'
        )
        self.configuration_actor.user_permissions.add(
            self.manage_configuration
        )
        self.general_actor = self.create_user('general-report@test.com')
        self.general_actor.user_permissions.add(self.view_reports)
        self.financial_actor = self.create_user('financial-report@test.com')
        self.financial_actor.user_permissions.add(self.view_financial_reports)
        self.combined_actor = self.create_user('combined-report@test.com')
        self.combined_actor.user_permissions.add(
            self.view_reports,
            self.view_financial_reports,
        )
        self.inactive_actor = self.create_user(
            'inactive-report@test.com',
            is_active=False,
        )
        self.inactive_actor.user_permissions.add(
            self.manage_configuration,
            self.view_reports,
            self.view_financial_reports,
        )

        self.configuration, _ = Configuracion.objects.update_or_create(
            pk=1,
            defaults={
                'empresa_nombre': 'Empresa Privada BH0604',
                'comprobante_razon_social': 'Razón Reservada SA',
                'comprobante_cuil': '20-12345678-9',
                'monto_sena': Decimal('5000.00'),
            },
        )
        self.diagnosis_configuration = ConfiguracionDiagnostico.get_singleton()

        self.product = Producto.objects.create(
            nombre='Producto reporte BH0604',
            precio=Decimal('125.00'),
            stock_real=10,
        )
        self.order = OrdenCompra.objects.create(
            codigo='REPORT-BH0604',
            cliente=self.client_profile,
            estado='COMPLETADO',
            total=Decimal('250.00'),
        )
        OrdenItem.objects.create(
            orden=self.order,
            producto=self.product,
            cantidad=2,
            precio_historico=Decimal('125.00'),
        )
        self.turno = Turno.objects.create(
            cliente=self.client_profile,
            fecha=timezone.localdate() + timedelta(days=1),
            hora_inicio=time(10, 0),
            estado=Turno.Estado.CONFIRMADO,
        )

        self.configuration_list = reverse('configuracion-list')
        self.configuration_detail = reverse(
            'configuracion-detail',
            args=[self.configuration.pk],
        )
        self.public_configuration = reverse(
            'configuracion-configuracion-publica'
        )
        self.receipt_configuration = reverse(
            'configuracion-configuracion-comprobante'
        )
        self.diagnosis_configuration_list = reverse(
            'configuracion-diagnostico-list'
        )
        self.diagnosis_configuration_detail = reverse(
            'configuracion-diagnostico-detail',
            args=[self.diagnosis_configuration.pk],
        )
        self.rules_list = reverse('reglas-diagnostico-list')
        self.general_stats = reverse('dashboard-stats-list')
        self.admin_stats = reverse('admin-stats')

    @staticmethod
    def permission(codename):
        return Permission.objects.get(
            content_type__app_label='gestion',
            codename=codename,
        )

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(email=email, **extra_fields)

    def create_client(self, email, **extra_fields):
        user = self.create_user(email, **extra_fields)
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        return user, Cliente.objects.create(usuario=user, activo=True)

    def user_with_role(self, email, role):
        user = self.create_user(email)
        user.groups.add(Group.objects.get(name=role))
        return user

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def assert_forbidden_report_surfaces(self, actor):
        self.authenticate(actor)
        self.assertEqual(
            self.client.get(self.general_stats).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.get(self.admin_stats).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_public_configuration_is_minimal_and_does_not_create_singleton(self):
        Configuracion.objects.all().delete()

        response = self.client.get(self.public_configuration)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'empresa_nombre': 'Bohemia Hair'})
        self.assertNotIn('comprobante_cuil', response.data)
        self.assertNotIn('monto_sena', response.data)
        self.assertEqual(Configuracion.objects.count(), 0)

    def test_public_custom_action_does_not_accept_writes(self):
        original_name = self.configuration.empresa_nombre

        response = self.client.post(
            self.public_configuration,
            {'empresa_nombre': 'Inyectada'},
            format='json',
        )

        self.configuration.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.configuration.empresa_nombre, original_name)

    def test_anonymous_is_rejected_without_mutation(self):
        original_name = self.configuration.empresa_nombre
        original_threshold = self.diagnosis_configuration.umbral_critico
        original_rules = ReglaDiagnostico.objects.count()

        responses = (
            self.client.get(self.configuration_list),
            self.client.patch(
                self.configuration_detail,
                {'empresa_nombre': 'No autorizada'},
                format='json',
            ),
            self.client.patch(
                self.diagnosis_configuration_detail,
                {'umbral_critico': 99},
                format='json',
            ),
            self.client.post(
                self.rules_list,
                {
                    'prioridad': 1,
                    'mensaje_resultado': 'No autorizada',
                    'accion_resultado': 'DENIED',
                },
                format='json',
            ),
            self.client.get(self.admin_stats),
            self.client.get(self.general_stats),
        )

        self.assertTrue(all(
            response.status_code == status.HTTP_401_UNAUTHORIZED
            for response in responses
        ))
        self.configuration.refresh_from_db()
        self.diagnosis_configuration.refresh_from_db()
        self.assertEqual(self.configuration.empresa_nombre, original_name)
        self.assertEqual(
            self.diagnosis_configuration.umbral_critico,
            original_threshold,
        )
        self.assertEqual(ReglaDiagnostico.objects.count(), original_rules)

    def test_business_roles_do_not_replace_effective_permissions(self):
        for actor in (self.client_user, self.employee, self.professional):
            self.authenticate(actor)
            with self.subTest(actor=actor.email):
                self.assertEqual(
                    self.client.get(self.configuration_list).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(self.admin_stats).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(self.general_stats).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_administrator_group_grants_all_capabilities_without_staff(self):
        self.authenticate(self.administrator)

        configuration = self.client.get(self.configuration_list)
        dashboard = self.client.get(self.admin_stats)
        reports = self.client.get(self.general_stats)

        self.assertFalse(self.administrator.is_staff)
        self.assertEqual(configuration.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(reports.status_code, status.HTTP_200_OK)
        self.assertIn('productos', reports.data)
        self.assertIn('total_ingresos', reports.data)

    def test_staff_without_permissions_has_no_business_authority(self):
        self.authenticate(self.staff_without_permission)

        responses = (
            self.client.get(self.configuration_list),
            self.client.get(self.diagnosis_configuration_list),
            self.client.get(self.admin_stats),
            self.client.get(self.general_stats),
        )

        self.assertTrue(self.staff_without_permission.is_staff)
        self.assertTrue(all(
            response.status_code == status.HTTP_403_FORBIDDEN
            for response in responses
        ))

    def test_individual_configuration_grant_controls_all_configuration_routes(self):
        self.authenticate(self.configuration_actor)

        listing = self.client.get(self.configuration_list)
        update = self.client.patch(
            self.configuration_detail,
            {'empresa_nombre': 'Configuración autorizada'},
            format='json',
        )
        diagnosis_update = self.client.patch(
            self.diagnosis_configuration_detail,
            {'umbral_critico': 3},
            format='json',
        )
        rule_create = self.client.post(
            self.rules_list,
            {
                'prioridad': 7,
                'mensaje_resultado': 'Regla autorizada',
                'accion_resultado': 'AUTHORIZED',
            },
            format='json',
        )

        self.configuration.refresh_from_db()
        self.diagnosis_configuration.refresh_from_db()
        self.assertFalse(self.configuration_actor.is_staff)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(update.status_code, status.HTTP_200_OK)
        self.assertEqual(diagnosis_update.status_code, status.HTTP_200_OK)
        self.assertEqual(rule_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            self.configuration.empresa_nombre,
            'Configuración autorizada',
        )
        self.assertEqual(self.diagnosis_configuration.umbral_critico, 3)
        self.assertTrue(
            ReglaDiagnostico.objects.filter(
                accion_resultado='AUTHORIZED'
            ).exists()
        )

    def test_configuration_permission_does_not_grant_reports(self):
        self.assert_forbidden_report_surfaces(self.configuration_actor)

    def test_report_permission_does_not_grant_configuration_or_mutation(self):
        original_name = self.configuration.empresa_nombre
        original_threshold = self.diagnosis_configuration.umbral_alerta
        original_rules = ReglaDiagnostico.objects.count()
        self.authenticate(self.general_actor)

        responses = (
            self.client.get(self.configuration_list),
            self.client.post(
                self.configuration_list,
                {'empresa_nombre': 'No autorizada'},
                format='json',
            ),
            self.client.patch(
                self.configuration_detail,
                {'empresa_nombre': 'No autorizada'},
                format='json',
            ),
            self.client.delete(self.configuration_detail),
            self.client.patch(
                self.diagnosis_configuration_detail,
                {'umbral_alerta': 100},
                format='json',
            ),
            self.client.post(
                self.rules_list,
                {
                    'prioridad': 1,
                    'mensaje_resultado': 'No autorizada',
                    'accion_resultado': 'DENIED',
                },
                format='json',
            ),
        )

        self.assertTrue(all(
            response.status_code == status.HTTP_403_FORBIDDEN
            for response in responses
        ))
        self.configuration.refresh_from_db()
        self.diagnosis_configuration.refresh_from_db()
        self.assertEqual(self.configuration.empresa_nombre, original_name)
        self.assertEqual(
            self.diagnosis_configuration.umbral_alerta,
            original_threshold,
        )
        self.assertEqual(ReglaDiagnostico.objects.count(), original_rules)

    def test_inactive_account_cannot_use_effective_grants(self):
        self.authenticate(self.inactive_actor)
        original_name = self.configuration.empresa_nombre

        responses = (
            self.client.get(self.configuration_list),
            self.client.patch(
                self.configuration_detail,
                {'empresa_nombre': 'No autorizada'},
                format='json',
            ),
            self.client.get(self.admin_stats),
            self.client.get(self.general_stats),
            self.client.get(self.receipt_configuration),
        )

        self.assertTrue(all(
            response.status_code == status.HTTP_403_FORBIDDEN
            for response in responses
        ))
        self.configuration.refresh_from_db()
        self.assertEqual(self.configuration.empresa_nombre, original_name)

    def test_general_report_grant_excludes_financial_data(self):
        self.authenticate(self.general_actor)

        dashboard = self.client.get(self.admin_stats)
        report = self.client.get(self.general_stats)
        receipt = self.client.get(self.receipt_configuration)

        self.assertFalse(self.general_actor.is_staff)
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(report.status_code, status.HTTP_200_OK)
        self.assertEqual(receipt.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('productos', report.data)
        self.assertIn('rutinas', report.data)
        self.assertIn('ordenes_count', report.data)
        self.assertIn('cliente_mes', report.data)
        self.assertNotIn('servicios', report.data)
        self.assertNotIn('total_ingresos', report.data)
        self.assertNotIn('email', report.data['cliente_mes'])
        self.assertNotIn(self.client_user.email, str(report.data))

    def test_financial_report_grant_excludes_general_and_identity_data(self):
        self.authenticate(self.financial_actor)

        report = self.client.get(self.general_stats)
        dashboard = self.client.get(self.admin_stats)
        receipt = self.client.get(self.receipt_configuration)

        self.assertFalse(self.financial_actor.is_staff)
        self.assertEqual(report.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(receipt.status_code, status.HTTP_200_OK)
        self.assertIn('servicios', report.data)
        self.assertEqual(report.data['total_ingresos'], 250.0)
        self.assertNotIn('productos', report.data)
        self.assertNotIn('rutinas', report.data)
        self.assertNotIn('ordenes_count', report.data)
        self.assertNotIn('cliente_mes', report.data)
        self.assertNotIn(self.client_user.email, str(report.data))
        self.assertEqual(set(receipt.data), {
            'empresa_nombre',
            'comprobante_razon_social',
            'comprobante_cuil',
            'comprobante_fecha_inicio_actividad',
        })

    def test_combined_report_grants_preserve_combined_contract(self):
        self.authenticate(self.combined_actor)

        report = self.client.get(self.general_stats)

        self.assertEqual(report.status_code, status.HTTP_200_OK)
        self.assertIn('servicios', report.data)
        self.assertIn('total_ingresos', report.data)
        self.assertIn('productos', report.data)
        self.assertIn('rutinas', report.data)
        self.assertIn('ordenes_count', report.data)
        self.assertIn('cliente_mes', report.data)
        self.assertEqual(report.data['ordenes_count'], 1)

    def test_report_reads_do_not_mutate_domain_data(self):
        counts_before = {
            'configurations': Configuracion.objects.count(),
            'diagnosis_configurations': ConfiguracionDiagnostico.objects.count(),
            'orders': OrdenCompra.objects.count(),
            'items': OrdenItem.objects.count(),
            'turnos': Turno.objects.count(),
        }
        self.authenticate(self.combined_actor)

        self.client.get(self.general_stats)
        self.client.get(self.admin_stats)
        self.client.get(self.receipt_configuration)

        self.assertEqual(counts_before, {
            'configurations': Configuracion.objects.count(),
            'diagnosis_configurations': ConfiguracionDiagnostico.objects.count(),
            'orders': OrdenCompra.objects.count(),
            'items': OrdenItem.objects.count(),
            'turnos': Turno.objects.count(),
        })

    def test_admin_dashboard_contains_no_financial_amounts_or_email(self):
        self.authenticate(self.general_actor)

        response = self.client.get(self.admin_stats)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('total_ingresos', response.data)
        self.assertNotIn('monto', response.data)
        self.assertNotIn(self.client_user.email, str(response.data))
        self.assertEqual(
            response.data['proximos_turnos'][0]['cliente'],
            'Clienta Privada',
        )
