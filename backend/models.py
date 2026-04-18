from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func
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
    producto = Column(String(300), nullable=False)
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
    monto = Column(Float, nullable=False)
    fecha = Column(DateTime, nullable=False)
    estado = Column(String(20), default="pendiente")  # pagado, pendiente
    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=True)
    comprobante_url = Column(String(500))
    created_at = Column(DateTime, server_default=func.now())


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
