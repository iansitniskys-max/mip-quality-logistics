from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import relationship
from database import Base


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    empresa = Column(String(200))
    razon_social = Column(String(200))
    rut = Column(String(20))
    rubro = Column(String(100))
    email = Column(String(200), unique=True, nullable=False)
    telefono = Column(String(30))
    password_hash = Column(String(200))
    num_empleados = Column(String(30))
    referido_por = Column(String(100))
    vendedor_asignado = Column(String(200))
    kam_responsable = Column(String(200))
    sitio_web = Column(String(300))
    ciudad = Column(String(100))
    direccion_despacho = Column(String(300))
    condicion_pago = Column(String(100))
    notas = Column(Text)
    activo = Column(String(10), default="true")
    role = Column(String(20), default="client")  # 'client' or 'admin'
    created_at = Column(DateTime, server_default=func.now())

    cotizaciones = relationship("Cotizacion", back_populates="cliente")
    actividades = relationship("Actividad", back_populates="cliente", cascade="all, delete-orphan")


class Cotizacion(Base):
    __tablename__ = "cotizaciones"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    proyecto_nombre = Column(String(300))  # nombre del proyecto global (ej "Bichos-Emonk")
    proyecto_descripcion = Column(Text)  # descripcion del proyecto
    producto = Column(String(300), nullable=False)  # legacy: resumen de productos
    descripcion = Column(Text)
    cantidad = Column(String(100))
    precio_objetivo = Column(String(100))
    plazo = Column(String(50))
    uso_final = Column(String(100))
    personalizacion = Column(Text)
    estado = Column(String(30), default="pendiente")  # pendiente, cotizado, produccion, entregado
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cliente = relationship("Cliente", back_populates="cotizaciones")
    pedido = relationship("Pedido", back_populates="cotizacion", uselist=False)
    productos = relationship("ProductoCotizacion", back_populates="cotizacion", cascade="all, delete-orphan")
    actividades = relationship("Actividad", back_populates="cotizacion", cascade="all, delete-orphan")


class ProductoCotizacion(Base):
    __tablename__ = "productos_cotizacion"
    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=False)
    nombre = Column(String(300), nullable=False)
    categoria = Column(String(100))
    materialidad = Column(String(100))
    dimensiones = Column(String(100))
    colores = Column(String(100))
    cantidad = Column(String(100))
    precio_objetivo = Column(String(100))
    personalizacion = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    cotizacion = relationship("Cotizacion", back_populates="productos")


class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=False)
    precio_unitario = Column(Float)
    condiciones = Column(Text)
    monto_total = Column(Float)
    estado = Column(String(30), default="activo")  # activo, completado, cancelado
    etapa_actual = Column(Integer, default=1)  # 1-9 timeline stages
    created_at = Column(DateTime, server_default=func.now())

    cotizacion = relationship("Cotizacion", back_populates="pedido")
    facturas = relationship("Factura", back_populates="pedido")
    archivos = relationship("Archivo", back_populates="pedido")


class Factura(Base):
    __tablename__ = "facturas"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    tipo = Column(String(20), nullable=False)  # gasto, ingreso
    categoria = Column(String(100))
    descripcion = Column(String(300))
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime, nullable=False)
    estado = Column(String(20), default="pendiente")  # pagado, pendiente
    archivo_url = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())

    pedido = relationship("Pedido", back_populates="facturas")


class Archivo(Base):
    __tablename__ = "archivos"
    id = Column(Integer, primary_key=True, index=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=True)
    nombre = Column(String(300), nullable=False)
    url = Column(String(500), nullable=False)
    tipo = Column(String(50))  # pdf, jpg, xlsx, etc.
    categoria = Column(String(50))  # cotizacion_proveedor, cotizacion_formal, factura, comprobante_pago, especificacion, mix_productos, foto_referencia, reporte_qc, doc_logistico, video, otro
    subido_por = Column(String(20), default="admin")  # admin, client
    subido_por_email = Column(String(200))
    size = Column(Integer)  # bytes
    created_at = Column(DateTime, server_default=func.now())

    pedido = relationship("Pedido", back_populates="archivos")


class MovimientoContable(Base):
    __tablename__ = "movimientos_contables"
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(20), nullable=False)  # gasto, ingreso
    categoria = Column(String(100))
    descripcion = Column(String(300))
    monto = Column(Float, nullable=False)  # monto en CLP
    moneda = Column(String(3), default="CLP")
    fecha = Column(DateTime, nullable=False)
    estado = Column(String(20), default="pendiente")  # pagado, pendiente
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    comprobante_url = Column(String(500))
    # Split Wise — quien pago y como se reparte (la empresa es la deudora)
    pagado_por_socio_id = Column(Integer, ForeignKey("socios.id"), nullable=True)
    medio_pago = Column(String(50))  # transferencia, tarjeta, efectivo, otro
    notas = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    splits = relationship("GastoSplit", cascade="all, delete-orphan", back_populates="movimiento")
    pagado_por = relationship("Socio", foreign_keys=[pagado_por_socio_id])


class Socio(Base):
    __tablename__ = "socios"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    email = Column(String(200))
    porcentaje_equity = Column(Float, default=0)  # % de participacion en la empresa
    activo = Column(Boolean, default=True)
    color = Column(String(7), default="#e8af43")  # hex para UI
    notas = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class GastoSplit(Base):
    """
    Detalla cuanto le toca asumir a cada socio de un gasto.
    Si 3 socios y split igual: cada uno asume monto/3.
    La empresa le debe al socio que pago: (monto_total - su parte).
    """
    __tablename__ = "gastos_splits"
    id = Column(Integer, primary_key=True, index=True)
    movimiento_id = Column(Integer, ForeignKey("movimientos_contables.id"), nullable=False)
    socio_id = Column(Integer, ForeignKey("socios.id"), nullable=False)
    monto_asumido = Column(Float, default=0)  # lo que este socio asume
    movimiento = relationship("MovimientoContable", back_populates="splits")
    socio = relationship("Socio")


class HistorialEvento(Base):
    __tablename__ = "historial_eventos"
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String(50), nullable=False)  # cotizacion, pedido, factura, movimiento, archivo, cliente
    accion = Column(String(50), nullable=False)  # creado, actualizado, estado_cambiado, archivo_subido
    entidad_id = Column(Integer)
    descripcion = Column(String(500))
    usuario = Column(String(200))
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(200), nullable=False)
    email = Column(String(200))
    urgencia = Column(String(20), nullable=False)  # baja, media, alta, critica
    tipo_error = Column(String(50), nullable=False)  # bug, ui, funcionalidad, rendimiento, otro
    seccion = Column(String(100), nullable=False)
    descripcion = Column(Text, nullable=False)
    screenshot_url = Column(String(500))
    estado = Column(String(20), default="abierto")  # abierto, en_progreso, resuelto
    respuesta_admin = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)


class SiteContent(Base):
    __tablename__ = "site_content"
    id = Column(Integer, primary_key=True, index=True)
    section = Column(String(50), nullable=False)  # hero, adn, process, sectors, testimonials, footer
    key = Column(String(100), nullable=False)
    value = Column(Text)
    content_type = Column(String(20), default="text")  # text, image, json
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Actividad(Base):
    __tablename__ = "actividades"
    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=True)
    tipo = Column(String(30), nullable=False, default="nota")  # nota, llamada, email, reunion, visita, cambio_etapa, otro
    titulo = Column(String(300))
    descripcion = Column(Text)
    etapa_anterior = Column(String(50))
    etapa_nueva = Column(String(50))
    autor = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())

    cliente = relationship("Cliente", back_populates="actividades")
    cotizacion = relationship("Cotizacion", back_populates="actividades")


# ═══ FEATURE FLAGS ═══
class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    id = Column(Integer, primary_key=True, index=True)
    modulo = Column(String(50), unique=True, nullable=False)  # proyectos, pdf, emails, proveedores, prospects
    activo = Column(String(10), default="true")
    config = Column(Text)  # JSON opcional
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ═══ PROVEEDORES ═══
class Proveedor(Base):
    __tablename__ = "proveedores"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    ciudad_china = Column(String(100))
    contacto = Column(String(200))
    email = Column(String(200))
    whatsapp = Column(String(50))
    website = Column(String(300))
    certificaciones = Column(Text)  # JSON array
    fortalezas = Column(Text)  # JSON array
    categorias = Column(Text)  # JSON array
    notas = Column(Text)
    activo = Column(String(10), default="true")
    rating = Column(Integer, default=3)  # 1-5
    created_at = Column(DateTime, server_default=func.now())

    productos = relationship("ProductoProveedor", back_populates="proveedor", cascade="all, delete-orphan")


class ProductoProveedor(Base):
    __tablename__ = "productos_proveedor"
    id = Column(Integer, primary_key=True, index=True)
    proveedor_id = Column(Integer, ForeignKey("proveedores.id"), nullable=False)
    sku = Column(String(100))
    nombre = Column(String(300), nullable=False)
    categoria = Column(String(100))
    precio_fob = Column(Float, default=0)
    moq = Column(Integer, default=0)
    lead_time_dias = Column(Integer, default=45)
    activo = Column(String(10), default="true")
    created_at = Column(DateTime, server_default=func.now())

    proveedor = relationship("Proveedor", back_populates="productos")


# ═══ PROSPECTS ═══
class Prospect(Base):
    __tablename__ = "prospects"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    empresa = Column(String(200))
    email = Column(String(200))
    telefono = Column(String(50))
    sector = Column(String(100))
    fuente = Column(String(50), default="otro")  # web, referido, linkedin, evento, otro
    score_ia = Column(Integer, default=50)
    notas = Column(Text)
    estado = Column(String(30), default="nuevo")  # nuevo, contactado, calificado, convertido, descartado
    convertido_a_cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ═══ EMAIL AUTOMATION ═══
class EmailSequence(Base):
    __tablename__ = "email_sequences"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    etapa_trigger = Column(String(50))  # pendiente, cotizado, produccion, entregado
    delay_horas = Column(Integer, default=0)
    asunto_template = Column(String(300))
    cuerpo_template = Column(Text)
    activo = Column(String(10), default="true")
    created_at = Column(DateTime, server_default=func.now())


class EmailLog(Base):
    __tablename__ = "email_logs"
    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=True)
    sequence_id = Column(Integer, ForeignKey("email_sequences.id"), nullable=True)
    destinatario = Column(String(200), nullable=False)
    asunto = Column(String(300))
    cuerpo = Column(Text)
    estado = Column(String(20), default="pendiente")  # pendiente, enviado, cancelado, error
    programado_para = Column(DateTime)
    enviado_at = Column(DateTime)
    error_msg = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


# ═══ PROYECTOS ═══
class Proyecto(Base):
    __tablename__ = "proyectos"
    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=True)
    nombre = Column(String(300), nullable=False)
    descripcion = Column(Text)
    estado = Column(String(30), default="planificacion")  # planificacion, activo, pausado, completado, cancelado
    fecha_inicio = Column(DateTime)
    fecha_fin = Column(DateTime)
    color = Column(String(20), default="#1d6fa5")
    created_by = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())

    secciones = relationship("ProyectoSeccion", back_populates="proyecto", cascade="all, delete-orphan")
    tareas = relationship("Tarea", back_populates="proyecto", cascade="all, delete-orphan")


class ProyectoSeccion(Base):
    __tablename__ = "proyecto_secciones"
    id = Column(Integer, primary_key=True, index=True)
    proyecto_id = Column(Integer, ForeignKey("proyectos.id"), nullable=False)
    nombre = Column(String(200), nullable=False)
    orden = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    proyecto = relationship("Proyecto", back_populates="secciones")
    tareas = relationship("Tarea", back_populates="seccion")


class Tarea(Base):
    __tablename__ = "tareas"
    id = Column(Integer, primary_key=True, index=True)
    proyecto_id = Column(Integer, ForeignKey("proyectos.id"), nullable=False)
    seccion_id = Column(Integer, ForeignKey("proyecto_secciones.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("tareas.id"), nullable=True)
    nombre = Column(String(300), nullable=False)
    descripcion = Column(Text)
    estado = Column(String(30), default="pendiente")  # pendiente, en_progreso, completada, bloqueada
    prioridad = Column(String(20), default="media")  # baja, media, alta, critica
    fecha_inicio = Column(DateTime)
    fecha_fin = Column(DateTime)
    progreso = Column(Integer, default=0)
    orden = Column(Integer, default=0)
    es_milestone = Column(String(10), default="false")
    asignado_a = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())

    proyecto = relationship("Proyecto", back_populates="tareas")
    seccion = relationship("ProyectoSeccion", back_populates="tareas")
    comentarios = relationship("ComentarioTarea", back_populates="tarea", cascade="all, delete-orphan")


class ComentarioTarea(Base):
    __tablename__ = "comentario_tarea"
    id = Column(Integer, primary_key=True, index=True)
    tarea_id = Column(Integer, ForeignKey("tareas.id"), nullable=False)
    texto = Column(Text, nullable=False)
    autor = Column(String(200))
    created_at = Column(DateTime, server_default=func.now())

    tarea = relationship("Tarea", back_populates="comentarios")


# ═══ COTIZACIONES FORMALES (PDF) ═══
class CotizacionFormal(Base):
    __tablename__ = "cotizaciones_formales"
    id = Column(Integer, primary_key=True, index=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=False)
    numero = Column(String(50), unique=True)
    fecha_emision = Column(DateTime, server_default=func.now())
    valido_hasta = Column(DateTime)
    precio_unitario_fob = Column(Float, default=0)
    costo_cif = Column(Float, default=0)
    margen_mip = Column(Float, default=15)
    total_clp = Column(Float, default=0)
    condiciones_pago = Column(String(200), default="50% anticipo + 50% pre-embarque")
    flete_tipo = Column(String(30), default="maritimo")  # maritimo, aereo
    plazo_produccion_dias = Column(Integer, default=45)
    notas = Column(Text)
    pdf_url = Column(String(500))
    estado = Column(String(30), default="borrador")  # borrador, enviada, aceptada, rechazada
    created_at = Column(DateTime, server_default=func.now())


# ═══ MATEO AI TRAINER ═══
class MateoConfig(Base):
    """Configuracion del chatbot Mateo - editable desde UI."""
    __tablename__ = "mateo_config"
    id = Column(Integer, primary_key=True, index=True)
    nombre_bot = Column(String(100), default="Mateo")
    tono = Column(String(50), default="profesional_cercano")  # profesional_cercano, formal, casual, agresivo_ventas
    longitud_respuesta = Column(String(30), default="media")  # corta, media, larga
    system_prompt = Column(Text)
    reglas_negocio = Column(Text)  # reglas custom del admin
    flujo_conversacion = Column(Text)  # pasos y decisiones
    precios_publicos = Column(Text)  # JSON de precios que puede mencionar
    auto_agendar_reuniones = Column(Boolean, default=False)
    calendar_email = Column(String(200))  # email para Google Calendar
    idioma = Column(String(10), default="es")
    max_tokens_respuesta = Column(Integer, default=500)
    modelo_ia = Column(String(50), default="gemini-2.5-flash")
    activo = Column(Boolean, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MateoConversation(Base):
    """Historial de conversaciones completas con Mateo."""
    __tablename__ = "mateo_conversations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), index=True)  # ID unico por sesion de chat
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=True)
    visitor_email = Column(String(200))  # email si no es cliente logueado
    visitor_nombre = Column(String(200))
    visitor_telefono = Column(String(50))
    visitor_empresa = Column(String(200))
    interes_detectado = Column(String(200))  # "cotizar", "info_general", "agendar_reunion"
    sentimiento = Column(String(30))  # positivo, neutral, negativo
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    mensajes_count = Column(Integer, default=0)
    convertido_a_prospect = Column(Boolean, default=False)
    proveedor_ia = Column(String(30), default="gemini")
    duracion_seg = Column(Integer, default=0)
    inicio_at = Column(DateTime, server_default=func.now())
    ultimo_mensaje_at = Column(DateTime, server_default=func.now())


class MateoMessage(Base):
    """Mensajes individuales dentro de una conversacion."""
    __tablename__ = "mateo_messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("mateo_conversations.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    tokens_usados = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class MateoCalendarBooking(Base):
    """Reuniones agendadas por Mateo via Google Calendar."""
    __tablename__ = "mateo_calendar_bookings"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("mateo_conversations.id"), nullable=True)
    calendar_event_id = Column(String(200))  # ID del evento en Google Calendar
    visitor_email = Column(String(200))
    visitor_nombre = Column(String(200))
    fecha_reunion = Column(DateTime)
    duracion_min = Column(Integer, default=30)
    motivo = Column(Text)
    estado = Column(String(30), default="confirmada")  # confirmada, cancelada, completada
    meet_link = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════════════
# AGENT BUILDER (Vambe-style)
# Permite crear/editar/desplegar agentes IA desde UI
# sin tocar codigo ni redeployar.
# ═══════════════════════════════════════════════════

class AgentConfig(Base):
    """Configuracion de un agente IA completo."""
    __tablename__ = "agent_configs"
    id = Column(Integer, primary_key=True, index=True)
    agent_type = Column(String(100), unique=True, nullable=False, index=True)  # identificador legible (ej: "mateo-sdr")
    display_name = Column(String(200), nullable=False)
    descripcion = Column(Text)
    avatar = Column(String(500))  # emoji o URL
    modelo = Column(String(100), default="gemini-2.5-flash")
    activo = Column(Boolean, default=True)
    tools_allowed = Column(Text, default="[]")  # JSON array de tool names
    max_tool_calls = Column(Integer, default=8)
    kb_folder_ids = Column(Text, default="[]")  # JSON array de folder ids
    stages = Column(Text, default="[]")  # etapas de embudo donde opera
    temperatura = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=800)
    # Metricas agregadas
    total_conversations = Column(Integer, default=0)
    total_tokens_in = Column(Integer, default=0)
    total_tokens_out = Column(Integer, default=0)
    total_cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    blocks = relationship("AgentBlock", cascade="all, delete-orphan", back_populates="agent", order_by="AgentBlock.orden")


class AgentBlock(Base):
    """Bloque modular del prompt de un agente.
    El prompt final se compone concatenando blocks activos en orden.

    Categorias:
      - identidad: personificacion, objetivo, formato
      - instrucciones: pasos, casos
      - info_clave: info_empresa, info_precios, info_productos, info_despachos, etc.
    """
    __tablename__ = "agent_blocks"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(50), nullable=False)  # personificacion, objetivo, formato, pasos, casos, info_*
    categoria = Column(String(30), default="identidad")  # identidad, instrucciones, info_clave
    nombre = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=False)
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    sub_steps = Column(Text, default="[]")  # JSON: [{orden:"1.1", texto:"...", tool_assigned:"calendar_create"}]
    # Para bloques info_clave reusables entre agentes
    es_reusable = Column(Boolean, default=False)
    block_key = Column(String(200))  # si es reusable, identificador global
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    agent = relationship("AgentConfig", back_populates="blocks")


class Tool(Base):
    """Funciones/tools que los agentes pueden invocar."""
    __tablename__ = "agent_tools"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)  # descripcion que lee el LLM
    categoria = Column(String(50), default="utility")  # calendar, shopify, kb, webhook, crm, utility
    schema_input = Column(Text, default="{}")  # JSONSchema del input
    activo = Column(Boolean, default=True)
    peligroso = Column(Boolean, default=False)  # requiere confirmacion humana
    handler = Column(String(100))  # nombre del handler interno a invocar
    created_at = Column(DateTime, server_default=func.now())


class KnowledgeFolder(Base):
    __tablename__ = "kb_folders"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), unique=True, nullable=False)
    descripcion = Column(Text)
    color = Column(String(10), default="#0A6FE0")
    created_at = Column(DateTime, server_default=func.now())

    docs = relationship("KnowledgeDoc", cascade="all, delete-orphan", back_populates="folder")


class KnowledgeDoc(Base):
    __tablename__ = "kb_docs"
    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("kb_folders.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(300), nullable=False)
    contenido = Column(Text, nullable=False)
    tokens_totales = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    folder = relationship("KnowledgeFolder", back_populates="docs")
    chunks = relationship("KnowledgeChunk", cascade="all, delete-orphan", back_populates="doc", order_by="KnowledgeChunk.orden")


class KnowledgeChunk(Base):
    __tablename__ = "kb_chunks"
    id = Column(Integer, primary_key=True, index=True)
    doc_id = Column(Integer, ForeignKey("kb_docs.id", ondelete="CASCADE"), nullable=False, index=True)
    contenido = Column(Text, nullable=False)
    embedding = Column(Text)  # JSON array de floats (768d para Gemini text-embedding-004)
    dim = Column(Integer, default=768)
    orden = Column(Integer, default=0)
    tokens = Column(Integer, default=0)

    doc = relationship("KnowledgeDoc", back_populates="chunks")


class AgentTrace(Base):
    """Observability: cada llamada al LLM se registra aqui."""
    __tablename__ = "agent_traces"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), index=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id"), index=True)
    prompt_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    tool_calls = Column(Text, default="[]")  # JSON array
    input_summary = Column(Text)
    output_summary = Column(Text)
    error = Column(Text)
    provider = Column(String(30))  # gemini, claude, openai
    created_at = Column(DateTime, server_default=func.now(), index=True)


# ═══════════════════════════════════════════════════
# PIPELINE DE CONVERSACIONES + HANDOFF HUMANO
# ═══════════════════════════════════════════════════

class ConversationPipeline(Base):
    """Pipeline que lleva una conversacion desde lead a cliente.
    Tracks el stage actual + agente asignado + datos del cliente capturados.
    """
    __tablename__ = "conversation_pipelines"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, index=True)  # ID de la conversacion
    current_stage = Column(String(50), default="lead_inicial", index=True)
    # Stages: lead_inicial, calificando, cotizando, cerrando, cliente_activo, cliente_perdido, soporte_post_venta
    current_agent_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    prospect_id = Column(Integer, ForeignKey("prospects.id"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cotizacion_id = Column(Integer, ForeignKey("cotizaciones.id"), nullable=True)
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    # Datos capturados
    visitor_nombre = Column(String(200))
    visitor_email = Column(String(200), index=True)
    visitor_telefono = Column(String(50))
    visitor_empresa = Column(String(200))
    # Clasificacion de intent
    intent_detected = Column(String(100))  # intencion_compra, info_general, soporte, queja, despedida
    intent_score = Column(Float, default=0.0)  # 0-1
    sentiment = Column(String(30), default="neutral")  # positivo, neutral, negativo
    # Handoff humano
    requires_human = Column(Boolean, default=False)
    human_handoff_reason = Column(Text)
    handoff_at = Column(DateTime)
    handled_by_admin = Column(String(200))
    # Metadata
    notes = Column(Text)
    total_messages = Column(Integer, default=0)
    last_message_at = Column(DateTime, server_default=func.now())
    # Live conversation control
    control_mode = Column(String(20), default="ai")  # ai | human | mixed
    taken_over_by = Column(String(200))  # email del admin que tomo control
    taken_over_at = Column(DateTime)
    last_client_activity_at = Column(DateTime)  # ultima vez que el CLIENTE escribio
    widget_is_open = Column(Boolean, default=True)  # cliente tiene el widget abierto
    pending_admin_messages = Column(Text, default="[]")  # cola de mensajes del admin esperando ser entregados al cliente
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    stage_history = relationship("PipelineStageLog", cascade="all, delete-orphan", back_populates="pipeline", order_by="PipelineStageLog.created_at")


class PipelineStageLog(Base):
    """Log de cambios de stage para auditar el movimiento del lead."""
    __tablename__ = "pipeline_stage_logs"
    id = Column(Integer, primary_key=True, index=True)
    pipeline_id = Column(Integer, ForeignKey("conversation_pipelines.id", ondelete="CASCADE"), index=True)
    from_stage = Column(String(50))
    to_stage = Column(String(50))
    from_agent_id = Column(Integer)
    to_agent_id = Column(Integer)
    trigger_type = Column(String(50))  # intent_detected, manual, timeout, escalation
    trigger_data = Column(Text)  # JSON con detalles
    created_at = Column(DateTime, server_default=func.now())
    pipeline = relationship("ConversationPipeline", back_populates="stage_history")


# ═══════════════════════════════════════════════════
# INTEGRACIONES POR AGENTE
# ═══════════════════════════════════════════════════

class AgentIntegration(Base):
    """Credenciales/config de integracion especificas por agente.
    Ej: un agente conecta a GCal del admin X, otro agente a WhatsApp Y."""
    __tablename__ = "agent_integrations"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), index=True)
    tipo = Column(String(50), nullable=False)  # google_calendar, whatsapp, slack, email, custom_webhook
    nombre = Column(String(200))
    activo = Column(Boolean, default=True)
    # Credenciales - JSON encriptado idealmente. Por ahora plain JSON.
    credentials = Column(Text)  # JSON: {access_token, refresh_token, expires_at, metadata}
    config = Column(Text)  # JSON: config especifica (ej: {calendar_id, whatsapp_from_number})
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class HumanHandoff(Base):
    """Eventos de derivacion a humano, con seguimiento."""
    __tablename__ = "human_handoffs"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), index=True)
    pipeline_id = Column(Integer, ForeignKey("conversation_pipelines.id"), nullable=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id"), nullable=True)
    visitor_nombre = Column(String(200))
    visitor_email = Column(String(200))
    visitor_telefono = Column(String(50))
    motivo = Column(Text)
    urgencia = Column(String(20), default="media")  # baja, media, alta, critica
    estado = Column(String(30), default="pendiente", index=True)  # pendiente, asignado, resuelto
    asignado_a = Column(String(200))
    resuelto_at = Column(DateTime)
    notas_resolucion = Column(Text)
    notified_via = Column(String(50))  # whatsapp, email, none
    whatsapp_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now(), index=True)


# ═══════════════════════════════════════════════════
# STAGE ASSIGNMENTS - quien atiende cada etapa del embudo
# ═══════════════════════════════════════════════════

class StageAssignment(Base):
    """Asigna un agente IA o humano a una etapa del embudo CRM.
    Tipos de stage: del embudo de Prospects (nuevo/contactado/calificado/convertido)
    o del ConversationPipeline (lead_inicial/calificando/cotizando/cerrando/etc).
    """
    __tablename__ = "stage_assignments"
    id = Column(Integer, primary_key=True, index=True)
    stage_type = Column(String(30), default="prospect")  # prospect | pipeline
    stage_key = Column(String(50), nullable=False, index=True)  # nuevo, contactado, calificado, etc
    # Puede ser un agente IA o un humano, solo uno
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="SET NULL"), nullable=True)
    human_email = Column(String(200))  # email del admin/humano asignado
    human_nombre = Column(String(200))
    # Si hay fallback
    fallback_to_human = Column(Boolean, default=False)  # si el agente no contesta o error
    notify_on_entry = Column(Boolean, default=True)  # notificar al responsable cuando un prospect entra
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ═══════════════════════════════════════════════════
# AGENT AUTO RULES - triggers que disparan acciones
# ═══════════════════════════════════════════════════

class AgentAutoRule(Base):
    """Reglas que se evaluan en cada mensaje del usuario.
    Si match, ejecuta la accion (mover de stage, cambiar agente, escalar).
    """
    __tablename__ = "agent_auto_rules"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text)
    # Tipo de trigger
    trigger_type = Column(String(50), nullable=False)  # keyword, intent, sentiment, message_count, lead_data
    # Config del trigger (JSON)
    trigger_config = Column(Text, default="{}")  # ej: {"keywords":["comprar","cotizar"], "match_any":true}
    # Accion a ejecutar
    action_type = Column(String(50), nullable=False)  # move_stage, switch_agent, escalate_human, tag_prospect
    action_config = Column(Text, default="{}")  # ej: {"target_stage":"cerrando"} o {"target_agent_id":2}
    prioridad = Column(Integer, default=100)  # lower = mayor prioridad
    activo = Column(Boolean, default=True)
    # Stats
    total_triggered = Column(Integer, default=0)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
