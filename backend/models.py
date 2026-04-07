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
    nombre = Column(String(300), nullable=False)
    url = Column(String(500), nullable=False)
    tipo = Column(String(50))  # pdf, jpg, xlsx, etc.
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
