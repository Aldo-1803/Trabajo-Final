from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta, date
from .models import Turno, ReglaCuidado, AgendaCuidados, RutinaCliente, Producto, Promocion, Auditoria, Configuracion #PasoRutinaCliente
from usuarios.models import Usuario
from .models import Notificacion
from .middleware import get_current_user, get_current_request
import json

# Cache para almacenar valores anteriores en pre_save
_valores_anteriores = {}


# ============================================================
# SISTEMA DE AUDITORÍA - Registra cambios en modelos
# ============================================================

def obtener_valores_modelo(instance, campos_excluidos=None):
    """
    Obtiene los valores de un modelo en formato JSON.
    Excluye campos que no se pueden serializar.
    """
    if campos_excluidos is None:
        campos_excluidos = ['password', 'refresh_token']
    
    valores = {}
    from django.db.models import FileField, ImageField, ForeignKey, OneToOneField
    from decimal import Decimal
    
    for field in instance._meta.fields:
        if field.name in campos_excluidos:
            continue
        
        valor = getattr(instance, field.name, None)
        
        # Convertir valores especiales
        if valor is None:
            # Los campos None se guardan como None
            valor = None
        elif isinstance(field, (FileField, ImageField)):
            # Convertir FileField/ImageField a string (la ruta del archivo)
            # Si está vacío, devolver None, si tiene contenido devolver el nombre
            valor = valor.name if valor else None
        elif isinstance(field, (ForeignKey, OneToOneField)):
            # ForeignKey: Guardar solo el ID/PK, no la instancia completa
            # Usar pk en lugar de id para soportar modelos con PKs especiales
            valor = valor.pk if valor else None
        elif hasattr(valor, 'isoformat'):  
            # datetime, date
            valor = valor.isoformat()
        elif isinstance(valor, (list, tuple)):
            valor = str(valor)
        elif isinstance(valor, Decimal):
            # Convertir Decimal a float
            valor = float(valor)
        
        valores[field.name] = valor
    
    return valores


def registrar_auditoria(tabla, registro_id, usuario, accion, valor_anterior=None, valor_nuevo=None, ip_address=None):
    """
    Registra una entrada de auditoría en la base de datos.
    """
    try:
        # Los JSONFields de Django se guardan como diccionarios, no como strings
        Auditoria.objects.create(
            tabla=tabla,
            registro_id=registro_id,
            usuario=usuario,
            accion=accion,
            valor_anterior=valor_anterior,  # Ya es un dict, JSONField lo maneja
            valor_nuevo=valor_nuevo,  # Ya es un dict, JSONField lo maneja
            ip_address=ip_address
        )
    except Exception as e:
        print(f"❌ Error registrando auditoría: {e}")


# ============================================================
# SEÑALES PARA AUDITORÍA - Pre Save y Post Save (ALTA y MODIFICACION)
# ============================================================
def crear_signal_auditoria(modelo):
    """
    Factory function que crea signals de auditoría para cualquier modelo.
    Usa pre_save para capturar valores anteriores y post_save para registrar.
    """
    @receiver(pre_save, sender=modelo)
    def capturar_valores_anteriores(sender, instance, **kwargs):
        """Captura valores anteriores antes de guardar"""
        tabla_modelo = modelo.__name__
        # Usar pk en lugar de id para soportar modelos con PKs especiales (como Cliente)
        clave = f"{tabla_modelo}_{instance.pk}"
        
        try:
            instance_anterior = modelo.objects.get(pk=instance.pk)
            valores = obtener_valores_modelo(instance_anterior)
            _valores_anteriores[clave] = valores
        except modelo.DoesNotExist:
            # Es un registro nuevo, no hay valores anteriores
            _valores_anteriores[clave] = None
        except Exception as e:
            print(f"⚠️  Error capturando valores anteriores en {tabla_modelo}: {e}")
            _valores_anteriores[clave] = None
    
    @receiver(post_save, sender=modelo)
    def registrar_cambios(sender, instance, created, **kwargs):
        usuario = get_current_user()
        request = get_current_request()
        ip_address = None
        
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        
        tabla = modelo.__name__
        # Usar pk en lugar de id para soportar modelos con PKs especiales
        registro_id = instance.pk
        
        # DEBUG: Registrar información de auditoría
        print(f"\n🔔 Signal post_save: {tabla}(id={registro_id})")
        print(f"   Usuario: {usuario}")
        print(f"   Created: {created}")
        
        # Recuperar valores anteriores capturados en pre_save
        clave = f"{tabla}_{instance.pk}"
        valor_anterior = _valores_anteriores.pop(clave, None)
        
        if created:
            # ALTA - Nuevo registro
            valor_nuevo = obtener_valores_modelo(instance)
            registrar_auditoria(
                tabla=tabla,
                registro_id=registro_id,
                usuario=usuario,
                accion='ALTA',
                valor_nuevo=valor_nuevo,
                ip_address=ip_address
            )
        else:
            # MODIFICACION - Registro existente
            if valor_anterior is not None:
                valor_nuevo = obtener_valores_modelo(instance)
                
                # Solo registrar si hubo cambios reales
                if valor_anterior != valor_nuevo:
                    print(f"📝 Cambios detectados en {tabla}(id={registro_id})")
                    registrar_auditoria(
                        tabla=tabla,
                        registro_id=registro_id,
                        usuario=usuario,
                        accion='MODIFICACION',
                        valor_anterior=valor_anterior,
                        valor_nuevo=valor_nuevo,
                        ip_address=ip_address
                    )
                else:
                    print(f"⏭️  Sin cambios reales en {tabla}(id={registro_id})")
            else:
                print(f"⚠️  No hay valores anteriores para {tabla}(id={registro_id})")
    
    return registrar_cambios, capturar_valores_anteriores


# ============================================================
# SEÑALES PARA AUDITORÍA - Pre Delete (BAJA)
# ============================================================

def crear_signal_baja_auditoria(modelo):
    """
    Factory function que crea signals de auditoría para eliminación.
    """
    @receiver(pre_delete, sender=modelo)
    def registrar_baja(sender, instance, **kwargs):
        usuario = get_current_user()
        request = get_current_request()
        ip_address = None
        
        if request:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            ip_address = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
        
        tabla = modelo.__name__
        # Usar pk en lugar de id para soportar modelos con PKs especiales
        registro_id = instance.pk
        
        # BAJA - Registro eliminado
        valor_anterior = obtener_valores_modelo(instance)
        registrar_auditoria(
            tabla=tabla,
            registro_id=registro_id,
            usuario=usuario,
            accion='BAJA',
            valor_anterior=valor_anterior,
            ip_address=ip_address
        )
    
    return registrar_baja


# ============================================================
# REGISTRAR SEÑALES PARA MODELOS PRINCIPALES
# ============================================================

# Importar modelos necesarios
from .models import (
    Servicio, Turno, Equipamiento, Personal,
    DiagnosticoCapilar, Rutina, RutinaCliente, Promocion, Notificacion,
    # Catálogos de Sistema
    TipoCabello, GrosorCabello, PorosidadCabello, CueroCabelludo, EstadoGeneral,
    CategoriaProducto, CategoriaServicio, Producto, Configuracion, TipoEquipamiento,
    ReglaDiagnostico
)
from usuarios.models import Usuario, Cliente

# Registrar signals de auditoría para cada modelo

# --- MODELOS DE USUARIO Y CLIENTE ---
crear_signal_auditoria(Usuario)
crear_signal_baja_auditoria(Usuario)

crear_signal_auditoria(Cliente)
crear_signal_baja_auditoria(Cliente)

# --- MODELOS DE OPERACIÓN ---
crear_signal_auditoria(Personal)
crear_signal_baja_auditoria(Personal)

crear_signal_auditoria(Turno)
crear_signal_baja_auditoria(Turno)

crear_signal_auditoria(Servicio)
crear_signal_baja_auditoria(Servicio)

crear_signal_auditoria(Equipamiento)
crear_signal_baja_auditoria(Equipamiento)

crear_signal_auditoria(DiagnosticoCapilar)
crear_signal_baja_auditoria(DiagnosticoCapilar)

crear_signal_auditoria(ReglaDiagnostico)
crear_signal_baja_auditoria(ReglaDiagnostico)

# --- MODELOS DE CONTENIDO ---
crear_signal_auditoria(Rutina)
crear_signal_baja_auditoria(Rutina)

crear_signal_auditoria(Promocion)
crear_signal_baja_auditoria(Promocion)

# --- CATÁLOGOS DEL SISTEMA (Tipos, Grosores, etc.) ---
crear_signal_auditoria(TipoCabello)
crear_signal_baja_auditoria(TipoCabello)

crear_signal_auditoria(GrosorCabello)
crear_signal_baja_auditoria(GrosorCabello)

crear_signal_auditoria(PorosidadCabello)
crear_signal_baja_auditoria(PorosidadCabello)

crear_signal_auditoria(CueroCabelludo)
crear_signal_baja_auditoria(CueroCabelludo)

crear_signal_auditoria(EstadoGeneral)
crear_signal_baja_auditoria(EstadoGeneral)

# --- CATÁLOGOS DE PRODUCTOS Y SERVICIOS ---
crear_signal_auditoria(CategoriaProducto)
crear_signal_baja_auditoria(CategoriaProducto)

crear_signal_auditoria(CategoriaServicio)
crear_signal_baja_auditoria(CategoriaServicio)

crear_signal_auditoria(Producto)
crear_signal_baja_auditoria(Producto)

crear_signal_auditoria(TipoEquipamiento)
crear_signal_baja_auditoria(TipoEquipamiento)

# --- CONFIGURACIÓN GLOBAL ---
crear_signal_auditoria(Configuracion)
crear_signal_baja_auditoria(Configuracion)


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
        
        # 1. Obtener los servicios del turno desde detalles (ahora es relación M2M)
        detalles_turno = instance.detalles.all()
        servicios = [detalle.servicio for detalle in detalles_turno]
        
        if not servicios:
            print("El turno no tiene servicios asociados.")
            return

        # 2. Buscamos reglas para los servicios realizados
        reglas = ReglaCuidado.objects.filter(servicio__in=servicios)
        
        if not reglas.exists():
            print("Los servicios no tienen reglas automáticas asociadas.")
            return

        # 3. Preparamos las tareas para la agenda
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
                        descripcion=f"{regla.descripcion} (Día {i+1}/{duracion}) - Servicio: {regla.servicio.nombre}"
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
                            descripcion=f"{regla.descripcion} - Servicio: {regla.servicio.nombre}"
                        ))
                else:
                    # Es un hábito de una sola vez
                    nuevos_items.append(AgendaCuidados(
                        cliente=instance.cliente,
                        fecha=fecha_inicio,
                        titulo="🧴 Hábito Sugerido",
                        descripcion=f"{regla.descripcion} - Servicio: {regla.servicio.nombre}"
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
        # Obtener servicios desde detalles
        servicios = [detalle.servicio for detalle in instance.detalles.all()]
        fecha_base = instance.fecha

        if not servicios:
            print("El turno no tiene servicios asociados.")
            return

        # --- PASO 1: ACTUALIZACIÓN DE DIAGNÓSTICO (Impacto) ---
        cambio_perfil = False
        
        # Procesar impactos de todos los servicios
        for servicio in servicios:
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

        # Procesar rutinas de todos los servicios
        for servicio in servicios:
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
    if not created:
        return

    config, _ = Configuracion.objects.get_or_create(pk=1)
    if not config.combo_auto_activo:
        return

    if not instance.activo or not instance.categoria:
        return

    if instance.stock_disponible < config.combo_min_stock:
        return

    def puntaje_similitud(base, candidato):
        score = 0
        if base.categoria_id == candidato.categoria_id:
            score += 1
        if config.combo_usar_marca and base.marca and candidato.marca and base.marca == candidato.marca:
            score += 1
        if config.combo_usar_proposito and base.proposito_uso and candidato.proposito_uso and base.proposito_uso == candidato.proposito_uso:
            score += 1
        if config.combo_usar_material and base.material_principal and candidato.material_principal and base.material_principal == candidato.material_principal:
            score += 1
        if config.combo_usar_compatibilidad and base.compatibilidad and candidato.compatibilidad and base.compatibilidad == candidato.compatibilidad:
            score += 1
        return score

    candidatos = Producto.objects.filter(
        categoria=instance.categoria,
        activo=True
    ).exclude(id=instance.id)

    candidatos = [
        p for p in candidatos
        if p.stock_disponible >= config.combo_min_stock
    ]

    candidatos = sorted(
        candidatos,
        key=lambda p: puntaje_similitud(instance, p),
        reverse=True
    )

    candidatos = [
        p for p in candidatos
        if puntaje_similitud(instance, p) >= config.combo_min_similitud
    ]

    if not candidatos:
        return

    max_productos = max(2, config.combo_max_productos)
    productos_combo = [instance] + candidatos[: max_productos - 1]
    combo_size = len(productos_combo)

    descuento = config.promo_descuento_combo_x2 if combo_size == 2 else config.promo_descuento_combo_x3

    def existe_combo_identico(productos):
        promos = Promocion.objects.filter(tipo='COMBO', is_active=True, productos__in=productos).distinct()
        ids_objetivo = {p.id for p in productos}
        for promo in promos:
            ids_promo = set(promo.productos.values_list('id', flat=True))
            if ids_promo == ids_objetivo:
                return True
        return False

    if existe_combo_identico(productos_combo):
        return

    stock_combo = min(
        (p.stock_disponible for p in productos_combo)
    )

    promo = Promocion.objects.create(
        nombre=f"Combo Sugerido: {instance.nombre}",
        descripcion=f"Pack especial de {instance.categoria.nombre}",
        tipo='COMBO',
        descuento_porcentaje=descuento,
        stock_combo=stock_combo,
        fecha_inicio=date.today(),
        fecha_fin=date.today() + timedelta(days=config.combo_dias_vigencia),
        is_active=False,
        es_sugerencia_automatica=True,
        estado_sugerencia='PENDIENTE'
    )
    promo.productos.add(*productos_combo)

    admins = Usuario.objects.filter(is_staff=True)
    for admin in admins:
        Notificacion.objects.create(
            usuario=admin,
            titulo="Nueva sugerencia de combo",
            mensaje=(
                f"Detectamos un combo sugerido con {combo_size} productos de "
                f"{instance.categoria.nombre}."
            ),
            tipo='alerta',
            canal='app',
            estado='pendiente',
            origen_entidad='Promocion',
            origen_id=promo.id,
            datos_extra={
                'promo_id': promo.id,
                'tipo': 'COMBO'
            }
        )

    print(f"DEBUG: Combo sugerido automáticamente para {instance.nombre}")