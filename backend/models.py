from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(200), nullable=False)
    empresa = Column(String(200))
    rut = Column(String(20))
    rubro = Column(String(100))
    email = Column(String(200), unique=True, nullable=False)
    telefono = Column(String(30))
    password_hash = Column(String(200))
    num_empleados = Column(String(30))
    referido_por = Column(String(100))
    vendedor_asignado = Column(String(200))
    sitio_web = Column(String(300))
    role = Column(String(20), default="client")  # 'client' or 'admin'
    created_at = Column(DateTime, server_default=func.now())

    cotizaciones = relationship("Cotizacion", back_populates="cliente")


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
