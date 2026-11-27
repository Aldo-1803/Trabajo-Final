from datetime import time

from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Auditoria, HorarioLaboral, Personal
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class PersonalDeleteDisabledApiTests(APITestCase):
    def setUp(self):
        self.actor = Usuario.objects.create_superuser(
            email='personal-delete-actor@test.com',
            password='ActorPassword!2026',
            first_name='Technical',
            last_name='Admin',
        )
        self.client.force_authenticate(user=self.actor)

    def create_user(self, email, **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='TargetPassword!2026',
            **extra_fields,
        )

    def create_personal(self, suffix, **overrides):
        values = {
            'nombre': f'Nombre {suffix}',
            'apellido': 'Con trazabilidad',
            'rol': 'asistente',
            'activo': True,
        }
        values.update(overrides)
        return Personal.objects.create(**values)

    def delete_url(self, personal):
        return reverse('personal-detail', args=[personal.pk])

    def assert_delete_is_closed(self, personal):
        original_active = personal.activo
        audit_count = Auditoria.objects.count()
        history_count = personal.history.count()

        response = self.client.delete(self.delete_url(personal))

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertTrue(Personal.objects.filter(pk=personal.pk).exists())
        personal.refresh_from_db()
        self.assertEqual(personal.activo, original_active)
        self.assertEqual(Auditoria.objects.count(), audit_count)
        self.assertEqual(personal.history.count(), history_count)
        return response

    def test_active_personal_without_user_cannot_be_deleted(self):
        personal = self.create_personal('active-roleless')

        self.assert_delete_is_closed(personal)

        self.assertIsNone(personal.usuario_id)

    def test_inactive_personal_without_user_cannot_be_deleted(self):
        personal = self.create_personal('inactive-roleless', activo=False)

        self.assert_delete_is_closed(personal)

        self.assertFalse(personal.activo)
        self.assertIsNone(personal.usuario_id)

    def test_linked_user_state_and_business_role_are_unchanged(self):
        user = self.create_user('linked-delete-target@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.PROFESIONAL))
        personal = self.create_personal('linked', usuario=user)

        self.assert_delete_is_closed(personal)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(
            get_business_roles(user),
            (BusinessRole.PROFESIONAL,),
        )
        personal.refresh_from_db()
        self.assertEqual(personal.usuario, user)

    def test_personal_with_coexisting_client_profile_cannot_be_deleted(self):
        user = self.create_user('client-personal-delete@test.com')
        user.groups.add(Group.objects.get(name=BusinessRole.CLIENTE))
        cliente = Cliente.objects.create(usuario=user, zona='Centro')
        personal = self.create_personal('client-profile', usuario=user)

        self.assert_delete_is_closed(personal)

        self.assertTrue(Cliente.objects.filter(pk=cliente.pk).exists())
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))

    def test_personal_with_existing_schedule_cannot_be_deleted(self):
        personal = self.create_personal('schedule')
        schedule = HorarioLaboral.objects.create(
            personal=personal,
            dia_semana=0,
            hora_inicio=time(9, 0),
            hora_fin=time(17, 0),
        )

        self.assert_delete_is_closed(personal)

        self.assertTrue(
            HorarioLaboral.objects.filter(
                pk=schedule.pk,
                personal=personal,
            ).exists()
        )

    def test_business_administrator_also_receives_405(self):
        administrator = self.create_user('business-admin-delete@test.com')
        administrator.groups.add(
            Group.objects.get(name=BusinessRole.ADMINISTRADOR)
        )
        personal = self.create_personal('business-admin')
        self.client.force_authenticate(user=administrator)

        self.assert_delete_is_closed(personal)

    def test_status_actions_continue_working_after_rejected_delete(self):
        personal = self.create_personal('status-actions')
        self.assert_delete_is_closed(personal)

        deactivate = self.client.post(
            reverse('personal-desactivar', args=[personal.pk]),
            {'motivo': 'Baja laboral explícita'},
            format='json',
        )
        self.assertEqual(deactivate.status_code, status.HTTP_200_OK)
        personal.refresh_from_db()
        self.assertFalse(personal.activo)

        reactivate = self.client.post(
            reverse('personal-reactivar', args=[personal.pk]),
            {'motivo': 'Reactivación laboral explícita'},
            format='json',
        )
        self.assertEqual(reactivate.status_code, status.HTTP_200_OK)
        personal.refresh_from_db()
        self.assertTrue(personal.activo)
