from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta, date
from .models import Turno, ReglaCuidado, AgendaCuidados, RutinaCliente, Producto, Promocion #PasoRutinaCliente
from usuarios.models import Usuario
from .models import Notificacion


#----------------------------------------------------
# 1. SISTEMA DE AGENDA DE CUIDADOS POST-SERVICIO
#----------------------------------------------------
@receiver(post_save, sender=Turno)
def generar_cuidados_post_servicio(sender, instance, created, **kwargs):
    """
    PROCESO AUTOMATIZADO:
    Disparador: El estado del turno cambia a 'REALIZADO'.
    Acción: El sistema genera la agenda de cuidados post-servicio para el cliente.
    """
    # Verificamos que sea un turno 'realizado' (ajusta el string según tus choices en Turno)
    if instance.estado == 'realizado': 
        print(f"[SISTEMA] Turno finalizado detectado para {instance.cliente}. Iniciando automatización...")
        
        # 1. Buscamos si el servicio realizado tiene reglas configuradas (ej: Alisado -> No lavar)
        reglas = ReglaCuidado.objects.filter(servicio=instance.servicio)
        
        if not reglas.exists():
            print("El servicio no tiene reglas automáticas asociadas.")
            return

        # 2. Preparamos las tareas para la agenda
        nuevos_items = []
        fecha_base = instance.fecha # Fecha en que se hizo el servicio
        
        for regla in reglas:
            # CASO A: RESTRICCIONES (Lo que NO debe hacer)
            if regla.tipo == 'RESTRICCION':
                # Generamos una entrada por cada día que dure la restricción
                duracion = regla.dias_duracion if regla.dias_duracion > 0 else 1
                for i in range(duracion):
                    fecha_bloqueo = fecha_base + timedelta(days=i)
                    nuevos_items.append(AgendaCuidados(
                        cliente=instance.cliente,
                        fecha=fecha_bloqueo,
                        titulo="RESTRICCIÓN",
                        descripcion=f"{regla.descripcion} (Día {i+1}/{duracion}) - Servicio: {instance.servicio.nombre}"
                    ))

            # CASO B: HÁBITOS (Lo que DEBE hacer)
            elif regla.tipo == 'HABITO':
                # Por defecto, sugerimos empezar el hábito al día siguiente
                fecha_inicio = fecha_base + timedelta(days=1)
                
                # Si es un hábito recurrente (ej: cada 7 días durante un mes)
                if regla.frecuencia_dias and regla.frecuencia_dias > 0:
                    # Generamos 4 repeticiones (ejemplo: un mes de tratamiento)
                    for i in range(0, 30, regla.frecuencia_dias):
                        nuevos_items.append(AgendaCuidados(
                            cliente=instance.cliente,
                            fecha=fecha_inicio + timedelta(days=i),
                            titulo="Hábito Sugerido",
                            descripcion=f"{regla.descripcion} - Servicio: {instance.servicio.nombre}"
                        ))
                else:
                    # Es un hábito de una sola vez
                    nuevos_items.append(AgendaCuidados(
                        cliente=instance.cliente,
                        fecha=fecha_inicio,
                        titulo="🧴 Hábito Sugerido",
                        descripcion=f"{regla.descripcion} - Servicio: {instance.servicio.nombre}"
                    ))

        # 3. Guardamos todo en la base de datos de una sola vez
        if nuevos_items:
            AgendaCuidados.objects.bulk_create(nuevos_items)
            print(f"Se generaron automáticamete {len(nuevos_items)} tareas en la agenda de {instance.cliente}.")


#----------------------------------------------------
# 2. SISTEMA DE NOTIFICACIONES IN-APP
#----------------------------------------------------

@receiver(post_save, sender=Turno)
def crear_notificacion_cambio_estado(sender, instance, created, **kwargs):
    """
    Genera notificaciones In-App respetando el nuevo modelo del diagrama.
    """
    # Obtener nombres de servicios del turno
    servicios_nombres = [d.servicio.nombre for d in instance.detalles.all()]
    servicios_str = ', '.join(servicios_nombres) if servicios_nombres else 'Servicios'
    
    # 1. NOTIFICACIÓN AL PROFESIONAL (Nuevo Turno)
    if created and instance.estado == 'solicitado':
        admins = Usuario.objects.filter(is_staff=True)
        for admin in admins:
            Notificacion.objects.create(
                usuario=admin,
                titulo="Nuevo Turno Solicitado",
                mensaje=f"{instance.cliente.usuario.first_name} solicitó {servicios_str} el {instance.fecha}.",
                tipo='alerta',
                canal='app',
                estado='pendiente',
                origen_entidad='Turno', 
                origen_id=instance.id    
            )

    # 2. NOTIFICACIÓN AL CLIENTE (Cambio de Estado)
    if not created:
        usuario_cliente = instance.cliente.usuario
        titulo = ""
        mensaje = ""
        tipo_notif = 'informativa'

        if instance.estado == 'esperando_sena':
            titulo = "Turno Aceptado"
            mensaje = f"Tu turno para {servicios_str} fue aceptado. ¡Sube tu seña!"
            tipo_notif = 'alerta' # Es importante, requiere acción
        
        elif instance.estado == 'confirmado':
            titulo = "Turno Confirmado"
            mensaje = "Seña recibida. Tu turno está confirmado. Te esperamos."
        
        elif instance.estado == 'cancelado':
            titulo = "Turno Cancelado"
            mensaje = f"El turno del {instance.fecha} ha sido cancelado."
            tipo_notif = 'alerta'

        elif instance.estado == 'realizado':
            titulo = "¡Servicio Finalizado!"
            mensaje = "Ya tienes disponible tu nueva Rutina de Cuidados en tu perfil."

        if titulo:
            Notificacion.objects.create(
                usuario=usuario_cliente,
                titulo=titulo,
                mensaje=mensaje,
                tipo=tipo_notif,
                canal='app',
                estado='pendiente',
                origen_entidad='Turno',
                origen_id=instance.id
            )

@receiver(post_save, sender=Turno)
def automatizacion_post_servicio(sender, instance, created, **kwargs):
    """
    Gestiona el Flujo Post-Servicio:
    1. Actualiza el Diagnóstico (Perfil) basado en el Impacto.
    2. Asigna la Rutina Recomendada en la Agenda.
    """
    if instance.estado == 'realizado':
        print(f"[SISTEMA] Finalizando turno {instance.id}. Iniciando automatización...")
        
        cliente = instance.cliente
        servicio = instance.servicio
        fecha_base = instance.fecha

        # --- PASO 1: ACTUALIZACIÓN DE DIAGNÓSTICO (Impacto) ---
        cambio_perfil = False
        
        if servicio.impacto_porosidad:
            print(f"   Diagnóstico: Porosidad cambia a {servicio.impacto_porosidad}")
            cliente.porosidad_cabello = servicio.impacto_porosidad
            cambio_perfil = True
            
        if servicio.impacto_estado:
            print(f"   Diagnóstico: Estado cambia a {servicio.impacto_estado}")
            cliente.estado_general = servicio.impacto_estado
            cambio_perfil = True
            
        if cambio_perfil:
            cliente.save()

        # --- PASO 2: ASIGNACIÓN DE RUTINA ---
        nuevos_items = []

        # A. Si el servicio tiene Rutina Recomendada (Prioridad Alta)
        if servicio.rutina_recomendada:
            rutina = servicio.rutina_recomendada
            print(f"   📘 Asignando Rutina: {rutina.nombre}")
            
            # 1. Crear RutinaCliente (copia personalizada para el cliente)
            rutina_cliente, created = RutinaCliente.objects.get_or_create(
                cliente=cliente,
                rutina_original=rutina,
                defaults={
                    'nombre': rutina.nombre,
                    'objetivo': rutina.objetivo,
                    'descripcion': rutina.descripcion,
                    'version_asignada': 1,  # Versión inicial
                    'estado': 'activa'
                }
            )
            
            if created:
                print(f"    RutinaCliente creada: {rutina_cliente.nombre}")
            else:
                print(f"    RutinaCliente ya existía: {rutina_cliente.nombre}")
            
            # 2. Verificar y copiar los pasos (tanto para nuevas como existentes)
            """
            pasos_existentes = rutina_cliente.pasos.count()
            if pasos_existentes == 0:
                print(f"    🔄 Copiando pasos de la rutina original...")
                
                pasos_originales = rutina.pasos.all().order_by('orden')
                pasos_cliente = []
                for paso_original in pasos_originales:
                    pasos_cliente.append(PasoRutinaCliente(
                        rutina_cliente=rutina_cliente,
                        orden=paso_original.orden,
                        descripcion=paso_original.descripcion,
                        frecuencia=paso_original.frecuencia
                    ))
                
                # Crear todos los pasos de una vez
                if pasos_cliente:
                    PasoRutinaCliente.objects.bulk_create(pasos_cliente)
                    print(f"    ✅ {len(pasos_cliente)} pasos copiados a la rutina del cliente")
                else:
                    print(f"    ⚠️  La rutina original no tiene pasos definidos")
            else:
                print(f"    ℹ️  La rutina ya tiene {pasos_existentes} pasos")
            
            print(f"   ✅ Rutina asignada correctamente. Disponible en 'Mis Rutinas'")
            """

        # B. Restricciones puntuales (Si las hay)
        # (Ej: "No lavar por 48hs" - Esto es independiente de la rutina)
        restricciones = ReglaCuidado.objects.filter(servicio=servicio, tipo='RESTRICCION')
        for regla in restricciones:
            nuevos_items.append(AgendaCuidados(
                cliente=cliente,
                fecha=fecha_base,
                titulo="RESTRICCIÓN",
                descripcion=f"{regla.descripcion} - Servicio: {servicio.nombre}"
            ))

        # Guardamos todo en la agenda
        if nuevos_items:
            AgendaCuidados.objects.bulk_create(nuevos_items)
            print(f" Se generaron {len(nuevos_items)} items en la agenda.")


#----------------------------------------------------
# 3. SISTEMA DE COMBOS AUTOMÁTICOS POR PRODUCTOS
#----------------------------------------------------

@receiver(post_save, sender=Producto)
def crear_combo_automatico(sender, instance, created, **kwargs):
    """
    Crea automáticamente un combo de lanzamiento cuando se agrega un nuevo producto.
    Busca otros productos de la misma categoría y genera un pack promocional.
    """
    if created:  # Solo si es un producto nuevo
        # Buscamos 2 productos de la misma categoría para armar un combo
        otros = Producto.objects.filter(
            categoria=instance.categoria
        ).exclude(id=instance.id)[:2]
        
        if otros.count() >= 1:
            promo = Promocion.objects.create(
                nombre=f"Combo Lanzamiento: {instance.nombre}",
                descripcion=f"Pack especial de {instance.categoria.nombre}",
                tipo='COMBO',
                descuento_porcentaje=15,
                fecha_inicio=date.today(),
                fecha_fin=date.today() + timedelta(days=15)
            )
            promo.productos.add(instance, *otros)
            # Aquí podrías disparar la notificación a las clientas interesadas
            print(f"DEBUG: Combo creado automáticamente para {instance.nombre}")