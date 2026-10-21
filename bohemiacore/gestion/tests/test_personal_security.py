from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import Personal
from usuarios.models import Usuario


class PersonalPrivilegeEscalationTests(APITestCase):
    def setUp(self):
        self.client_user = Usuario.objects.create_user(
            email='cliente-personal@test.com',
            password='testpass123',
        )
        self.staff_user = Usuario.objects.create_user(
            email='staff-personal@test.com',
            password='testpass123',
            is_staff=True,
        )
        self.target_user = Usuario.objects.create_user(
            email='target-personal@test.com',
            password='testpass123',
        )
        self.list_url = reverse('personal-list')

    def personal_payload(self, **overrides):
        payload = {
            'nombre': 'Ana',
            'apellido': 'Prueba',
            'rol': 'asistente',
            'email': 'ana-personal@test.com',
            'telefono': '123456789',
            'activo': True,
            'color_calendario': '#E11D48',
            'realiza_diagnostico': False,
            'realiza_lavado': True,
            'realiza_color': False,
        }
        payload.update(overrides)
        return payload

    def privilege_snapshot(self, user):
        user.refresh_from_db()
        return {
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'groups': set(user.groups.values_list('pk', flat=True)),
            'user_permissions': set(
                user.user_permissions.values_list('pk', flat=True)
            ),
        }

    def grant_test_privileges(self, user, suffix):
        group = Group.objects.create(name=f'personal-security-{suffix}')
        permission = Permission.objects.get(
            content_type__app_label='gestion',
            codename='change_personal',
        )
        user.groups.add(group)
        user.user_permissions.add(permission)

    def test_client_cannot_create_personal_or_elevate_privileges(self):
        self.client.force_authenticate(user=self.client_user)

        response = self.client.post(
            self.list_url,
            self.personal_payload(usuario=self.client_user.pk),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Personal.objects.exists())
        self.client_user.refresh_from_db()
        self.assertFalse(self.client_user.is_staff)
        self.assertFalse(self.client_user.is_superuser)

    def test_usuario_payload_is_ignored_and_does_not_elevate_user(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.post(
            self.list_url,
            self.personal_payload(usuario=self.target_user.pk),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        personal = Personal.objects.get(pk=response.data['id'])
        self.assertIsNone(personal.usuario)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_staff)
        self.assertFalse(self.target_user.is_superuser)

    def test_staff_can_create_personal_without_usuario(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.post(
            self.list_url,
            self.personal_payload(),
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        personal = Personal.objects.get(pk=response.data['id'])
        self.assertIsNone(personal.usuario)

    def test_editing_personal_does_not_change_user_privileges(self):
        linked_user = Usuario.objects.create_user(
            email='linked-edit@test.com',
            password='testpass123',
            is_staff=True,
            is_superuser=True,
        )
        self.grant_test_privileges(linked_user, 'edit')
        personal = Personal.objects.create(
            usuario=linked_user,
            nombre='Antes',
            apellido='Editar',
            rol='colorista',
        )
        privileges_before = self.privilege_snapshot(linked_user)
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.patch(
            reverse('personal-detail', args=[personal.pk]),
            {
                'nombre': 'Despues',
                'usuario': self.target_user.pk,
                'is_staff': False,
                'is_superuser': False,
                'groups': [],
                'user_permissions': [],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        personal.refresh_from_db()
        self.assertEqual(personal.nombre, 'Despues')
        self.assertEqual(personal.usuario, linked_user)
        self.assertEqual(self.privilege_snapshot(linked_user), privileges_before)
        self.target_user.refresh_from_db()
        self.assertFalse(self.target_user.is_staff)

    def test_unlinking_or_deleting_personal_does_not_change_privileges(self):
        unlinked_user = Usuario.objects.create_user(
            email='linked-unlink@test.com',
            password='testpass123',
            is_staff=True,
        )
        deleted_user = Usuario.objects.create_user(
            email='linked-delete@test.com',
            password='testpass123',
            is_staff=True,
        )
        self.grant_test_privileges(unlinked_user, 'unlink')
        self.grant_test_privileges(deleted_user, 'delete')
        personal_to_unlink = Personal.objects.create(
            usuario=unlinked_user,
            nombre='Desvincular',
            apellido='Prueba',
            rol='asistente',
        )
        personal_to_delete = Personal.objects.create(
            usuario=deleted_user,
            nombre='Eliminar',
            apellido='Prueba',
            rol='asistente',
        )
        unlink_privileges = self.privilege_snapshot(unlinked_user)
        delete_privileges = self.privilege_snapshot(deleted_user)

        personal_to_unlink.usuario = None
        personal_to_unlink.save(update_fields=['usuario'])

        self.assertEqual(
            self.privilege_snapshot(unlinked_user),
            unlink_privileges,
        )

        self.client.force_authenticate(user=self.staff_user)
        response = self.client.delete(
            reverse('personal-detail', args=[personal_to_delete.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Personal.objects.filter(pk=personal_to_delete.pk).exists())
        self.assertEqual(
            self.privilege_snapshot(deleted_user),
            delete_privileges,
        )
