from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from usuarios.models import Usuario, Cliente
from gestion.models import Servicio, Turno, ReglaCuidado, AgendaCuidados

class ProcesoInteligenteTest(TestCase):
    
    def setUp(self):
        # 1. PRECONDICIÓN: Crear Datos Base (Simulamos lo que ya existe en BD)
        print("\n--- INICIO TEST PROCESO INTELIGENTE: GENERACIÓN DE RUTINA ---")
        
        # Crear Usuario y Cliente
        self.user = Usuario.objects.create_user(email='test@client.com', password='password123')
        self.cliente = Cliente.objects.create(usuario=self.user)
        print(f"1. Cliente creado: {self.user.email}")

        # Crear Servicio
        self.servicio = Servicio.objects.create(nombre="Alisado Definitivo", duracion_estimada=120)
        print(f"2. Servicio creado: {self.servicio.nombre}")

        # Crear Regla (El 'Cerebro' del sistema)
        self.regla = ReglaCuidado.objects.create(
            servicio=self.servicio,
            tipo='RESTRICCION',
            descripcion='No lavar el cabello por 48hs',
            dias_duracion=2
        )
        print(f"3. Regla configurada: Si se hace {self.servicio.nombre} -> {self.regla.descripcion}")

    def test_generacion_automatica_rutina(self):
        """
        Prueba que al finalizar un turno, el sistema genere automáticamente
        la agenda de cuidados sin intervención humana.
        """
        
        # 1. Crear Turno (Estado Solicitado)
        turno = Turno.objects.create(
            cliente=self.cliente,
            servicio=self.servicio,
            fecha=timezone.now().date(),
            hora_inicio=timezone.now().time(),
            estado='solicitado'
        )
        print(f" 4. Turno solicitado para hoy. Estado actual: {turno.estado}")

        # 2. ACCIÓN: Simular que Yani finaliza el trabajo
        print("... Realizando servicio ...")
        turno.estado = 'realizado' # Cambio de estado
        turno.save() # Al guardar, se dispara el SIGNAL (Proceso Automático)
        print(f" 5. Turno finalizado. Estado nuevo: {turno.estado}")

        # 3. VERIFICACIÓN: ¿El sistema creó la agenda solo?
        agenda_items = AgendaCuidados.objects.filter(cliente=self.cliente)
        cantidad = agenda_items.count()
        
        print(f" 6. Verificando agenda del cliente... Items encontrados: {cantidad}")
        
        self.assertTrue(cantidad > 0, "FALLO: El sistema no generó la rutina automáticamente.")
        
        for item in agenda_items:
            print(f" ITEM GENERADO: Día {item.fecha} -> {item.titulo}: {item.descripcion}")

        print("--- FIN TEST EXITOSO ---")