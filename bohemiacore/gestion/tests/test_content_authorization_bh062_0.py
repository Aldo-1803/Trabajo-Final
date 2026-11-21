from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from gestion.models import (
    ContenidoEducativo,
    ContenidoGuardado,
    MeGusta,
    Personal,
)
from usuarios.models import Cliente, Usuario
from usuarios.roles import BusinessPermission, BusinessRole


class ContentAuthorizationBH062Tests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_user = cls.create_user_with_role(
            'cliente-contenido@test.com',
            BusinessRole.CLIENTE,
        )
        cls.cliente = Cliente.objects.create(usuario=cls.client_user)

        cls.no_personal = cls.create_user_with_role(
            'sin-personal-contenido@test.com',
            BusinessRole.EMPLEADO,
        )
        cls.author_user, cls.author = cls.create_personal_user(
            'autor-contenido@test.com',
            'Autor',
        )
        cls.other_user, cls.other = cls.create_personal_user(
            'ajeno-contenido@test.com',
            'Ajeno',
        )
        cls.inactive_user, cls.inactive_personal = cls.create_personal_user(
            'personal-inactivo-contenido@test.com',
            'Inactivo',
            activo=False,
        )

        cls.global_manager = cls.create_user_with_role(
            'gestor-global-contenido@test.com',
            BusinessRole.ADMINISTRADOR,
        )
        cls.staff_only = Usuario.objects.create_user(
            email='staff-sin-permiso-contenido@test.com',
            is_staff=True,
        )
        cls.effective_manager, cls.manager_personal = cls.create_personal_user(
            'empleado-grant-contenido@test.com',
            'Grant',
            role=BusinessRole.EMPLEADO,
        )
        cls.effective_manager.user_permissions.add(
            Permission.objects.get(
                content_type__app_label='gestion',
                codename='manage_content',
            )
        )

        cls.own_draft = cls.create_content(
            'Borrador propio', cls.author, 'BORRADOR'
        )
        cls.own_archived = cls.create_content(
            'Archivado propio', cls.author, 'ARCHIVADO'
        )
        cls.other_draft = cls.create_content(
            'Borrador ajeno', cls.other, 'BORRADOR'
        )
        cls.published = cls.create_content(
            'Publicado', cls.other, 'PUBLICADO'
        )
        cls.inactive_draft = cls.create_content(
            'Borrador de Personal inactivo',
            cls.inactive_personal,
            'BORRADOR',
        )
        cls.soft_deleted = cls.create_content(
            'Eliminado lógico', cls.other, 'PUBLICADO', activo=False
        )

    @staticmethod
    def create_user_with_role(email, role):
        user = Usuario.objects.create_user(email=email)
        user.groups.add(Group.objects.get(name=role))
        return user

    @classmethod
    def create_personal_user(
        cls,
        email,
        name,
        *,
        activo=True,
        role=BusinessRole.PROFESIONAL,
    ):
        user = cls.create_user_with_role(email, role)
        personal = Personal.objects.create(
            usuario=user,
            nombre=name,
            apellido='Contenido',
            rol='colorista',
            activo=activo,
        )
        return user, personal

    @staticmethod
    def create_content(title, author, state, *, activo=True):
        return ContenidoEducativo.objects.create(
            titulo=title,
            descripcion=f'Descripción {title}',
            tipo='TEXTO',
            contenido_texto=f'Texto {title}',
            estado=state,
            autor=author,
            activo=activo,
        )

    @staticmethod
    def payload(title='Contenido nuevo', state='BORRADOR', **extra):
        data = {
            'titulo': title,
            'descripcion': f'Descripción {title}',
            'tipo': 'TEXTO',
            'contenido_texto': f'Texto {title}',
            'estado': state,
            'tags': 'bh062',
        }
        data.update(extra)
        return data

    @staticmethod
    def response_ids(response):
        data = response.data.get('results', response.data)
        return {item['id'] for item in data}

    def authenticate(self, user):
        self.client.force_authenticate(user)

    def test_unauthenticated_request_is_401(self):
        response = self.client.get(reverse('contenido-educativo-list'))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_client_and_users_without_active_personal_list_only_published(self):
        for actor in (
            self.client_user,
            self.no_personal,
            self.inactive_user,
            self.staff_only,
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.get(reverse('contenido-educativo-list'))

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertSetEqual(
                    self.response_ids(response),
                    {self.published.pk},
                )

    def test_active_author_lists_published_and_only_owned_non_public_content(self):
        self.authenticate(self.author_user)

        response = self.client.get(reverse('contenido-educativo-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertSetEqual(
            self.response_ids(response),
            {self.published.pk, self.own_draft.pk, self.own_archived.pk},
        )

    def test_effective_global_permission_lists_all_active_content(self):
        expected = {
            self.published.pk,
            self.own_draft.pk,
            self.own_archived.pk,
            self.other_draft.pk,
            self.inactive_draft.pk,
        }
        for actor in (self.global_manager, self.effective_manager):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.get(reverse('contenido-educativo-list'))

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertSetEqual(self.response_ids(response), expected)
                self.assertNotIn(self.soft_deleted.pk, self.response_ids(response))

    def test_detail_hides_foreign_drafts_but_preserves_public_read(self):
        hidden_url = reverse(
            'contenido-educativo-detail', args=[self.other_draft.pk]
        )
        public_url = reverse(
            'contenido-educativo-detail', args=[self.published.pk]
        )
        for actor in (
            self.client_user,
            self.no_personal,
            self.author_user,
            self.inactive_user,
            self.staff_only,
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                self.assertEqual(
                    self.client.get(hidden_url).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                self.assertEqual(
                    self.client.get(public_url).status_code,
                    status.HTTP_200_OK,
                )

    def test_author_and_global_manager_retrieve_authorized_drafts(self):
        cases = (
            (self.author_user, self.own_draft),
            (self.global_manager, self.other_draft),
            (self.effective_manager, self.other_draft),
        )
        for actor, content in cases:
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.get(reverse(
                    'contenido-educativo-detail', args=[content.pk]
                ))
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_creation_requires_active_personal_and_never_accepts_payload_author(self):
        list_url = reverse('contenido-educativo-list')
        initial_count = ContenidoEducativo.objects.count()
        rejected = (
            self.client_user,
            self.no_personal,
            self.inactive_user,
            self.staff_only,
            self.global_manager,
        )
        for actor in rejected:
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.post(
                    list_url,
                    self.payload(autor=self.other.pk),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(ContenidoEducativo.objects.count(), initial_count)

        self.authenticate(self.client_user)
        malformed_response = self.client.post(list_url, {}, format='json')
        self.assertEqual(
            malformed_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(ContenidoEducativo.objects.count(), initial_count)

        for actor, expected_author in (
            (self.author_user, self.author),
            (self.effective_manager, self.manager_personal),
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.post(
                    list_url,
                    self.payload(
                        title=f'Creado por {actor.email}',
                        autor=self.other.pk,
                    ),
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                created = ContenidoEducativo.objects.get(pk=response.data['id'])
                self.assertEqual(created.autor, expected_author)

    def test_author_put_preserves_author_and_can_publish_then_archive(self):
        self.authenticate(self.author_user)
        url = reverse('contenido-educativo-detail', args=[self.own_draft.pk])

        update_response = self.client.put(
            url,
            self.payload(
                title='Título editado',
                autor=self.other.pk,
            ),
            format='json',
        )
        publish_response = self.client.patch(
            url,
            {'estado': 'PUBLICADO'},
            format='json',
        )
        archive_response = self.client.patch(
            url,
            {'estado': 'ARCHIVADO'},
            format='json',
        )

        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(publish_response.status_code, status.HTTP_200_OK)
        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        self.own_draft.refresh_from_db()
        self.assertEqual(self.own_draft.autor, self.author)
        self.assertEqual(self.own_draft.titulo, 'Título editado')
        self.assertEqual(self.own_draft.estado, 'ARCHIVADO')

    def test_rejected_edits_do_not_mutate_author_title_or_state(self):
        original = {
            'autor_id': self.published.autor_id,
            'titulo': self.published.titulo,
            'estado': self.published.estado,
        }
        url = reverse('contenido-educativo-detail', args=[self.published.pk])
        for actor in (
            self.client_user,
            self.no_personal,
            self.author_user,
            self.inactive_user,
            self.staff_only,
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.patch(
                    url,
                    {
                        'titulo': 'Mutación rechazada',
                        'estado': 'ARCHIVADO',
                        'autor': self.author.pk,
                    },
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.published.refresh_from_db()
                self.assertEqual(
                    {
                        'autor_id': self.published.autor_id,
                        'titulo': self.published.titulo,
                        'estado': self.published.estado,
                    },
                    original,
                )

        self.authenticate(self.client_user)
        malformed_response = self.client.put(url, {}, format='json')
        self.assertEqual(
            malformed_response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_foreign_and_inactive_author_drafts_are_404_without_mutation(self):
        cases = (
            (self.author_user, self.other_draft),
            (self.inactive_user, self.inactive_draft),
        )
        for actor, content in cases:
            with self.subTest(actor=actor.email):
                original = (content.titulo, content.estado, content.autor_id)
                self.authenticate(actor)
                response = self.client.patch(
                    reverse('contenido-educativo-detail', args=[content.pk]),
                    {'titulo': 'No aplicar', 'estado': 'PUBLICADO'},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                content.refresh_from_db()
                self.assertEqual(
                    (content.titulo, content.estado, content.autor_id),
                    original,
                )

    def test_global_permission_edits_foreign_draft_for_any_business_role(self):
        for actor, title in (
            (self.global_manager, 'Editado por administrador'),
            (self.effective_manager, 'Editado por grant empleado'),
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.patch(
                    reverse(
                        'contenido-educativo-detail',
                        args=[self.other_draft.pk],
                    ),
                    {'titulo': title},
                    format='json',
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.other_draft.refresh_from_db()
                self.assertEqual(self.other_draft.titulo, title)
                self.assertEqual(self.other_draft.autor, self.other)

    def test_author_and_global_manager_can_soft_delete(self):
        self.authenticate(self.author_user)
        author_response = self.client.delete(reverse(
            'contenido-educativo-detail', args=[self.own_archived.pk]
        ))
        self.authenticate(self.global_manager)
        manager_response = self.client.delete(reverse(
            'contenido-educativo-detail', args=[self.other_draft.pk]
        ))

        self.assertEqual(author_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(manager_response.status_code, status.HTTP_204_NO_CONTENT)
        self.own_archived.refresh_from_db()
        self.other_draft.refresh_from_db()
        self.assertFalse(self.own_archived.activo)
        self.assertFalse(self.other_draft.activo)
        self.assertTrue(ContenidoEducativo.objects.filter(
            pk=self.own_archived.pk
        ).exists())

    def test_unauthorized_delete_is_403_and_has_zero_mutations(self):
        url = reverse('contenido-educativo-detail', args=[self.published.pk])
        for actor in (
            self.client_user,
            self.no_personal,
            self.author_user,
            self.inactive_user,
            self.staff_only,
        ):
            with self.subTest(actor=actor.email):
                self.authenticate(actor)
                response = self.client.delete(url)
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.published.refresh_from_db()
                self.assertTrue(self.published.activo)
                self.assertEqual(self.published.estado, 'PUBLICADO')
                self.assertEqual(self.published.autor, self.other)

    def test_like_and_save_actions_accept_only_active_published_content(self):
        self.authenticate(self.client_user)
        like_url = reverse(
            'contenido-educativo-toggle-like', args=[self.published.pk]
        )
        save_url = reverse(
            'contenido-educativo-toggle-guardar', args=[self.published.pk]
        )

        like_response = self.client.post(like_url, {}, format='json')
        save_response = self.client.post(save_url, {}, format='json')

        self.assertEqual(like_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(save_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(MeGusta.objects.filter(
            cliente=self.cliente, contenido=self.published
        ).exists())
        self.assertTrue(ContenidoGuardado.objects.filter(
            cliente=self.cliente, contenido=self.published
        ).exists())

        for content in (self.other_draft, self.soft_deleted):
            with self.subTest(content=content.pk):
                self.assertEqual(
                    self.client.post(reverse(
                        'contenido-educativo-toggle-like', args=[content.pk]
                    )).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
                self.assertEqual(
                    self.client.post(reverse(
                        'contenido-educativo-toggle-guardar', args=[content.pk]
                    )).status_code,
                    status.HTTP_404_NOT_FOUND,
                )
        self.assertEqual(MeGusta.objects.count(), 1)
        self.assertEqual(ContenidoGuardado.objects.count(), 1)

    def test_saved_and_liked_lists_hide_archived_or_deleted_content(self):
        for content in (self.published, self.own_archived, self.soft_deleted):
            MeGusta.objects.create(cliente=self.cliente, contenido=content)
            ContenidoGuardado.objects.create(
                cliente=self.cliente,
                contenido=content,
            )
        self.authenticate(self.client_user)

        saved_action = self.client.get(reverse(
            'contenido-educativo-mis-guardados'
        ))
        likes = self.client.get(reverse('me-gusta-list'))
        saved = self.client.get(reverse('contenido-guardado-list'))

        self.assertEqual(saved_action.status_code, status.HTTP_200_OK)
        self.assertSetEqual(self.response_ids(saved_action), {self.published.pk})
        self.assertEqual(likes.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item['contenido'] for item in likes.data['results']},
            {self.published.pk},
        )
        self.assertEqual(saved.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {item['contenido'] for item in saved.data['results']},
            {self.published.pk},
        )

    def test_direct_related_mutation_routes_are_closed(self):
        like = MeGusta.objects.create(
            cliente=self.cliente,
            contenido=self.published,
        )
        saved = ContenidoGuardado.objects.create(
            cliente=self.cliente,
            contenido=self.published,
        )
        self.authenticate(self.client_user)
        initial_likes = MeGusta.objects.count()
        initial_saved = ContenidoGuardado.objects.count()

        like_response = self.client.post(
            reverse('me-gusta-list'),
            {'contenido': self.published.pk, 'cliente': self.cliente.pk},
            format='json',
        )
        saved_response = self.client.post(
            reverse('contenido-guardado-list'),
            {'contenido': self.published.pk, 'cliente': self.cliente.pk},
            format='json',
        )
        like_delete_response = self.client.delete(
            reverse('me-gusta-detail', args=[like.pk])
        )
        saved_delete_response = self.client.delete(
            reverse('contenido-guardado-detail', args=[saved.pk])
        )

        self.assertEqual(
            like_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            saved_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            like_delete_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            saved_delete_response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(MeGusta.objects.count(), initial_likes)
        self.assertEqual(ContenidoGuardado.objects.count(), initial_saved)
