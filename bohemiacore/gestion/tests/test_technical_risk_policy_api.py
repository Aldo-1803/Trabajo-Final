from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    FamiliaProcesoTecnico,
    PerfilTecnicoServicio,
    PoliticaRiesgoTecnico,
    ReglaDiagnosticoTecnico,
    ReglaFrecuenciaTecnica,
    ReglaIntervaloTecnico,
    Servicio,
)
from usuarios.models import Usuario
from usuarios.roles import BusinessRole


class TechnicalRiskPolicyApiTests(APITestCase):
    def setUp(self):
        self.permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='manage_technical_risk_policy',
        )
        self.manager = self.create_user('policy-api-manager@test.com')
        self.manager.user_permissions.add(self.permission)
        self.service_a = Servicio.objects.create(nombre='API service A')
        self.service_b = Servicio.objects.create(nombre='API service B')

    @staticmethod
    def create_user(email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='testpass123',
            **extra_fields,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user=user or self.manager)

    def test_all_endpoints_require_specific_permission(self):
        endpoints = [
            reverse('familia-proceso-tecnico-list'),
            reverse('perfil-tecnico-servicio-list'),
            reverse('politica-riesgo-tecnico-list'),
            reverse('regla-intervalo-tecnico-list'),
            reverse('regla-diagnostico-tecnico-list'),
            reverse('regla-frecuencia-tecnica-list'),
        ]
        denied_users = [
            self.create_user('ordinary-policy-api@test.com'),
            self.create_user('staff-policy-api@test.com', is_staff=True),
        ]
        role_name_only = self.create_user('role-name-policy-api@test.com')
        administrator_group = Group.objects.get(name=BusinessRole.ADMINISTRADOR)
        administrator_group.permissions.remove(self.permission)
        role_name_only.groups.add(administrator_group)
        denied_users.append(role_name_only)

        for user in denied_users:
            self.authenticate(user)
            for endpoint in endpoints:
                with self.subTest(user=user.email, endpoint=endpoint):
                    response = self.client.get(endpoint)
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_individual_permission_allows_metadata_management(self):
        self.authenticate()
        family_response = self.client.post(
            reverse('familia-proceso-tecnico-list'),
            {
                'code': 'API_FAMILY',
                'nombre': 'API family',
                'descripcion': '',
                'activa': True,
            },
            format='json',
        )
        self.assertEqual(family_response.status_code, status.HTTP_201_CREATED)

        profile_response = self.client.post(
            reverse('perfil-tecnico-servicio-list'),
            {
                'servicio': self.service_a.pk,
                'familia': family_response.data['id'],
                'estado_clasificacion': 'CLASIFICADO',
                'nivel_riesgo': 'ALTO',
                'activa': True,
            },
            format='json',
        )
        self.assertEqual(profile_response.status_code, status.HTTP_201_CREATED)
        profile = PerfilTecnicoServicio.objects.get(servicio=self.service_a)
        self.assertEqual(profile.familia.code, 'API_FAMILY')

    def test_create_draft_and_manage_all_rule_families(self):
        self.authenticate()
        family = FamiliaProcesoTecnico.objects.create(
            code='RULE_API_FAMILY', nombre='Rule API family'
        )
        policy_response = self.client.post(
            reverse('politica-riesgo-tecnico-list'),
            {'version': 'API-V1'},
            format='json',
        )
        self.assertEqual(policy_response.status_code, status.HTTP_201_CREATED)
        policy_id = policy_response.data['id']
        self.assertEqual(policy_response.data['estado'], 'BORRADOR')

        interval_response = self.client.post(
            reverse('regla-intervalo-tecnico-list'),
            {
                'politica': policy_id,
                'code': 'API_INTERVAL',
                'servicio_origen': self.service_a.pk,
                'servicio_destino': self.service_b.pk,
                'dias_minimos': 12,
                'outcome': 'ADVERTENCIA',
                'severidad': 1,
                'prioridad': 10,
                'mensaje_cliente': 'Mensaje cliente',
                'mensaje_profesional': 'Mensaje profesional',
                'activa': True,
            },
            format='json',
        )
        diagnosis_response = self.client.post(
            reverse('regla-diagnostico-tecnico-list'),
            {
                'politica': policy_id,
                'code': 'API_DIAGNOSIS',
                'familia_destino': family.pk,
                'requiere_diagnostico': True,
                'antiguedad_maxima_dias': 15,
                'outcome_si_falta': 'REQUIERE_REVISION',
                'outcome_si_vencido': 'ADVERTENCIA',
                'outcome_si_incompleto': 'REQUIERE_REVISION',
                'outcome_si_procedencia_no_confiable': 'REQUIERE_REVISION',
                'severidad': 2,
                'prioridad': 5,
                'activa': True,
            },
            format='json',
        )
        frequency_response = self.client.post(
            reverse('regla-frecuencia-tecnica-list'),
            {
                'politica': policy_id,
                'code': 'API_FREQUENCY',
                'servicio': self.service_a.pk,
                'ventana_dias': 20,
                'cantidad_maxima': 2,
                'outcome': 'ADVERTENCIA',
                'severidad': 1,
                'prioridad': 1,
                'activa': True,
            },
            format='json',
        )

        self.assertEqual(interval_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(diagnosis_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(frequency_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ReglaIntervaloTecnico.objects.count(), 1)
        self.assertEqual(ReglaDiagnosticoTecnico.objects.count(), 1)
        self.assertEqual(ReglaFrecuenciaTecnica.objects.count(), 1)

    def test_invalid_selectors_are_rejected_by_api(self):
        self.authenticate()
        family = FamiliaProcesoTecnico.objects.create(
            code='INVALID_SELECTOR_FAMILY', nombre='Invalid selector family'
        )
        policy = PoliticaRiesgoTecnico.objects.create(version='API-INVALID')

        response = self.client.post(
            reverse('regla-intervalo-tecnico-list'),
            {
                'politica': policy.pk,
                'code': 'INVALID_SELECTORS',
                'servicio_origen': self.service_a.pk,
                'familia_origen': family.pk,
                'servicio_destino': self.service_b.pk,
                'dias_minimos': 1,
                'outcome': 'NO_APTO',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('origen', response.data)

    def test_publish_action_and_published_resources_are_immutable(self):
        self.authenticate()
        policy = PoliticaRiesgoTecnico.objects.create(version='API-PUBLISH')
        rule = ReglaFrecuenciaTecnica.objects.create(
            politica=policy,
            code='API_PUBLISH_FREQUENCY',
            servicio=self.service_a,
            ventana_dias=20,
            cantidad_maxima=2,
            outcome='ADVERTENCIA',
        )

        publish_response = self.client.post(
            reverse(
                'politica-riesgo-tecnico-publicar',
                kwargs={'pk': policy.pk},
            ),
            {},
            format='json',
        )
        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(publish_response.data['estado'], 'PUBLICADA')

        policy_patch = self.client.patch(
            reverse('politica-riesgo-tecnico-detail', kwargs={'pk': policy.pk}),
            {'version': 'CHANGED'},
            format='json',
        )
        policy_delete = self.client.delete(
            reverse('politica-riesgo-tecnico-detail', kwargs={'pk': policy.pk})
        )
        rule_patch = self.client.patch(
            reverse('regla-frecuencia-tecnica-detail', kwargs={'pk': rule.pk}),
            {'prioridad': 99},
            format='json',
        )
        rule_delete = self.client.delete(
            reverse('regla-frecuencia-tecnica-detail', kwargs={'pk': rule.pk})
        )
        new_rule = self.client.post(
            reverse('regla-frecuencia-tecnica-list'),
            {
                'politica': policy.pk,
                'code': 'LATE_RULE',
                'servicio': self.service_b.pk,
                'ventana_dias': 5,
                'cantidad_maxima': 1,
                'outcome': 'NO_APTO',
            },
            format='json',
        )

        self.assertEqual(
            policy_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(
            policy_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED
        )
        self.assertEqual(rule_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(rule_delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(new_rule.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_without_permission_is_forbidden_even_for_staff(self):
        policy = PoliticaRiesgoTecnico.objects.create(version='API-DENIED')
        staff_only = self.create_user(
            'publish-staff-only@test.com', is_staff=True
        )
        self.authenticate(staff_only)

        response = self.client.post(
            reverse(
                'politica-riesgo-tecnico-publicar',
                kwargs={'pk': policy.pk},
            ),
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        policy.refresh_from_db()
        self.assertEqual(policy.estado, PoliticaRiesgoTecnico.Estado.BORRADOR)
