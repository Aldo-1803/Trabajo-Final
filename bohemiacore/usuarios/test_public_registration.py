import json
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    Auditoria,
    DiagnosticoCapilar,
    GrosorCabello,
    TipoCabello,
)
from usuarios.access_services import (
    INITIAL_CLIENT_ROLE_AUDIT_EVENT,
    INITIAL_CLIENT_ROLE_AUDIT_TABLE,
    InitialBusinessRoleAlreadyAssigned,
    InvalidBusinessRole,
    MissingClientProfile,
    assign_initial_client_role,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessRole, get_business_roles


class InitialClientRoleAssignmentTests(TestCase):
    def create_user(self, email='initial-client@test.com', **extra_fields):
        return Usuario.objects.create_user(
            email=email,
            password='PublicRegistration!2026',
            **extra_fields,
        )

    def test_assigns_exactly_client_and_audits_without_actor(self):
        user = self.create_user(is_active=False, is_staff=True)
        cliente = Cliente.objects.create(usuario=user)

        result = assign_initial_client_role(user, 'public_registration')

        user.refresh_from_db()
        self.assertTrue(result.changed)
        self.assertEqual(result.user_id, user.pk)
        self.assertEqual(result.cliente_id, cliente.pk)
        self.assertEqual(result.role, BusinessRole.CLIENTE)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertFalse(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        audit = Auditoria.objects.get(pk=result.audit_id)
        self.assertEqual(audit.tabla, INITIAL_CLIENT_ROLE_AUDIT_TABLE)
        self.assertIsNone(audit.usuario)
        self.assertEqual(
            audit.valor_nuevo['event'],
            INITIAL_CLIENT_ROLE_AUDIT_EVENT,
        )
        self.assertEqual(audit.valor_nuevo['source'], 'public_registration')
        self.assertIsNone(audit.valor_nuevo['actor_id'])
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['cliente_id'], cliente.pk)
        self.assertEqual(
            audit.valor_nuevo['business_role'],
            BusinessRole.CLIENTE,
        )

    def test_requires_client_profile(self):
        user = self.create_user()

        with self.assertRaises(MissingClientProfile):
            assign_initial_client_role(user, 'public_registration')

        self.assertEqual(get_business_roles(user), ())

    def test_rejects_non_client_target_role(self):
        user = self.create_user()
        Cliente.objects.create(usuario=user)

        with self.assertRaises(InvalidBusinessRole):
            assign_initial_client_role(
                user,
                'public_registration',
                target_role=BusinessRole.ADMINISTRADOR,
            )

        self.assertEqual(get_business_roles(user), ())

    def test_rejects_an_existing_different_business_role(self):
        user = self.create_user()
        Cliente.objects.create(usuario=user)
        user.groups.add(Group.objects.get(name=BusinessRole.EMPLEADO))

        with self.assertRaises(InitialBusinessRoleAlreadyAssigned):
            assign_initial_client_role(user, 'public_registration')

        self.assertEqual(get_business_roles(user), (BusinessRole.EMPLEADO,))


class PublicRegistrationApiTests(APITestCase):
    password = 'PublicRegistration!2026'

    def setUp(self):
        self.url = reverse('registro')

    def payload(self, **overrides):
        values = {
            'email': 'public-client@test.com',
            'first_name': 'Ana',
            'last_name': 'Pérez',
            'password': self.password,
            'password2': self.password,
            'zona': 'Centro',
            'numero': '1122334455',
        }
        values.update(overrides)
        return values

    def post(self, payload=None):
        return self.client.post(
            self.url,
            payload if payload is not None else self.payload(),
            format='json',
        )

    def semantic_audits(self):
        return Auditoria.objects.filter(
            tabla=INITIAL_CLIENT_ROLE_AUDIT_TABLE,
            valor_nuevo__event=INITIAL_CLIENT_ROLE_AUDIT_EVENT,
        )

    def test_valid_registration_creates_client_with_exact_role_and_audit(self):
        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data,
            {'mensaje': 'Usuario registrado exitosamente.'},
        )
        user = Usuario.objects.get(email='public-client@test.com')
        cliente = Cliente.objects.get(usuario=user)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(hasattr(user, 'es_cliente'))
        self.assertTrue(user.check_password(self.password))
        self.assertNotEqual(user.password, self.password)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        self.assertNotIn(BusinessRole.EMPLEADO, get_business_roles(user))
        self.assertNotIn(BusinessRole.PROFESIONAL, get_business_roles(user))
        self.assertNotIn(BusinessRole.ADMINISTRADOR, get_business_roles(user))
        self.assertFalse(
            DiagnosticoCapilar.objects.filter(cliente=cliente).exists()
        )

        audit = self.semantic_audits().get()
        self.assertIsNone(audit.usuario)
        self.assertEqual(audit.valor_nuevo['user_id'], user.pk)
        self.assertEqual(audit.valor_nuevo['cliente_id'], cliente.pk)
        self.assertEqual(audit.valor_nuevo['source'], 'public_registration')
        serialized_audit = json.dumps({
            'before': audit.valor_anterior,
            'after': audit.valor_nuevo,
        })
        self.assertNotIn(self.password, serialized_audit)
        self.assertNotIn(user.password, serialized_audit)
        self.assertNotIn('token', serialized_audit.lower())

    @patch(
        'gestion.views.DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico'
    )
    def test_optional_diagnosis_and_public_aliases_still_work(self, engine):
        tipo = TipoCabello.objects.create(nombre='Ondulado')
        grosor = GrosorCabello.objects.create(nombre='Medio')

        response = self.post(self.payload(
            email='diagnosis-client@test.com',
            tipo_cabello=tipo.pk,
            grosor=grosor.pk,
        ))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = Usuario.objects.get(email='diagnosis-client@test.com')
        cliente = Cliente.objects.get(usuario=user)
        diagnosis = DiagnosticoCapilar.objects.get(cliente=cliente)
        self.assertEqual(diagnosis.tipo_cabello, tipo)
        self.assertEqual(diagnosis.grosor_cabello, grosor)
        self.assertEqual(get_business_roles(user), (BusinessRole.CLIENTE,))
        engine.assert_called_once_with(diagnosis)

    @patch(
        'gestion.views.DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico'
    )
    @patch(
        'usuarios.serializers.assign_initial_client_role',
        side_effect=RuntimeError('forced role failure'),
    )
    def test_role_failure_rolls_back_user_client_and_diagnosis(
        self,
        _assign_role,
        _engine,
    ):
        tipo = TipoCabello.objects.create(nombre='Rizado')

        with self.assertRaises(RuntimeError):
            self.post(self.payload(tipo_cabello=tipo.pk))

        self.assertFalse(
            Usuario.objects.filter(email='public-client@test.com').exists()
        )
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(self.semantic_audits().exists())

    @patch(
        'gestion.views.DiagnosticoCapilarViewSet._ejecutar_motor_diagnostico'
    )
    def test_semantic_audit_failure_rolls_back_complete_registration(
        self,
        _engine,
    ):
        tipo = TipoCabello.objects.create(nombre='Lacio')
        original_create = Auditoria.objects.create

        def fail_semantic_audit(**kwargs):
            if kwargs.get('tabla') == INITIAL_CLIENT_ROLE_AUDIT_TABLE and (
                kwargs.get('valor_nuevo', {}).get('event')
                == INITIAL_CLIENT_ROLE_AUDIT_EVENT
            ):
                raise RuntimeError('forced audit failure')
            return original_create(**kwargs)

        with patch(
            'usuarios.access_services.Auditoria.objects.create',
            side_effect=fail_semantic_audit,
        ):
            with self.assertRaises(RuntimeError):
                self.post(self.payload(tipo_cabello=tipo.pk))

        self.assertFalse(
            Usuario.objects.filter(email='public-client@test.com').exists()
        )
        self.assertFalse(Cliente.objects.exists())
        self.assertFalse(DiagnosticoCapilar.objects.exists())
        self.assertFalse(self.semantic_audits().exists())

    def test_duplicate_email_keeps_current_validation_contract(self):
        Usuario.objects.create_user(
            email='public-client@test.com',
            password='ExistingAccount!2026',
        )

        response = self.post()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertEqual(
            Usuario.objects.filter(email='public-client@test.com').count(),
            1,
        )

    def test_password_validation_is_preserved(self):
        response = self.post(self.payload(password='weak', password2='weak'))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertFalse(
            Usuario.objects.filter(email='public-client@test.com').exists()
        )

    def test_privilege_and_role_fields_are_rejected(self):
        forbidden_fields = (
            ('role', BusinessRole.ADMINISTRADOR),
            ('business_role', BusinessRole.ADMINISTRADOR),
            ('groups', [1]),
            ('user_permissions', [1]),
            ('is_staff', True),
            ('is_superuser', True),
            ('is_active', False),
        )

        for index, (field, value) in enumerate(forbidden_fields):
            with self.subTest(field=field):
                payload = self.payload(
                    email=f'forbidden-{index}@test.com'
                )
                payload[field] = value

                response = self.post(payload)

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
                self.assertIn(field, response.data)

        self.assertFalse(
            Usuario.objects.filter(email__startswith='forbidden-').exists()
        )
