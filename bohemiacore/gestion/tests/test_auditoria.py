"""
Tests para el sistema de auditoría.
"""
from django.test import TestCase
from gestion.models import Servicio, Auditoria
from usuarios.models import Usuario
from gestion.middleware import _thread_locals
from decimal import Decimal


class AuditoriaTestCase(TestCase):
    """
    Tests para verificar que el sistema de auditoría funciona correctamente.
    """
    
    def setUp(self):
        """Preparar datos de prueba"""
        # Crear usuario admin
        self.usuario_admin = Usuario.objects.create_user(
            email='test_admin@test.com',
            password='testpass123',
            is_staff=True
        )
        
        # Simular que el usuario está autenticado
        _thread_locals.user = self.usuario_admin
        _thread_locals.request = None
    
    def test_auditoria_modificacion_servicio(self):
        """
        Test: Verificar que se registra auditoría al modificar un servicio
        """
        # Crear un servicio
        servicio = Servicio.objects.create(
            nombre='Test Service',
            precio_base=Decimal('100.00'),
            duracion_estimada=60
        )
        
        # Contar auditorías antes
        audit_antes = Auditoria.objects.count()
        
        # Modificar el precio
        servicio.precio_base = Decimal('200.00')
        servicio.save()
        
        # Verificar que se creó una auditoría
        audit_despues = Auditoria.objects.count()
        self.assertEqual(audit_despues, audit_antes + 1, "Debería haberse creado una auditoría")
        
        # Verificar detalles de la auditoría
        auditoria = Auditoria.objects.last()
        self.assertEqual(auditoria.tabla, 'Servicio')
        self.assertEqual(auditoria.accion, 'MODIFICACION')
        self.assertEqual(auditoria.usuario, self.usuario_admin)
        self.assertEqual(auditoria.registro_id, servicio.id)
        self.assertIsNotNone(auditoria.valor_anterior)
        self.assertIsNotNone(auditoria.valor_nuevo)
    
    def test_auditoria_creacion_servicio(self):
        """
        Test: Verificar que se registra auditoría al crear un servicio
        """
        audit_antes = Auditoria.objects.count()
        
        # Crear un servicio
        servicio = Servicio.objects.create(
            nombre='New Service',
            precio_base=Decimal('150.00'),
            duracion_estimada=45
        )
        
        # Verificar que se creó una auditoría
        audit_despues = Auditoria.objects.count()
        self.assertEqual(audit_despues, audit_antes + 1, "Debería haberse creado una auditoría")
        
        # Verificar detalles de la auditoría
        auditoria = Auditoria.objects.last()
        self.assertEqual(auditoria.tabla, 'Servicio')
        self.assertEqual(auditoria.accion, 'ALTA')
        self.assertEqual(auditoria.usuario, self.usuario_admin)
        self.assertEqual(auditoria.registro_id, servicio.id)
    
    def test_auditoria_eliminacion_servicio(self):
        """
        Test: Verificar que se registra auditoría al eliminar un servicio
        """
        # Crear un servicio
        servicio = Servicio.objects.create(
            nombre='Delete Service',
            precio_base=Decimal('100.00'),
            duracion_estimada=60
        )
        servicio_id = servicio.id
        
        audit_antes = Auditoria.objects.count()
        
        # Eliminar el servicio
        servicio.delete()
        
        # Verificar que se creó una auditoría
        audit_despues = Auditoria.objects.count()
        self.assertEqual(audit_despues, audit_antes + 1, "Debería haberse creado una auditoría de eliminación")
        
        # Verificar detalles de la auditoría
        auditoria = Auditoria.objects.last()
        self.assertEqual(auditoria.tabla, 'Servicio')
        self.assertEqual(auditoria.accion, 'BAJA')
        self.assertEqual(auditoria.usuario, self.usuario_admin)
        self.assertEqual(auditoria.registro_id, servicio_id)
