from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# --- Clientes ---
class ClienteCreate(BaseModel):
    nombre: str
    empresa: str = ""
    rut: str = ""
    rubro: str = ""
    email: str
    telefono: str = ""
    password: str = ""
    num_empleados: str = ""
    referido_por: str = ""
    vendedor_contacto: str = ""
    sitio_web: str = ""

class ClienteOut(BaseModel):
    id: int
    nombre: str
    empresa: str
    rut: str
    rubro: str
    email: str
    telefono: str
    num_empleados: Optional[str] = ""
    referido_por: Optional[str] = ""
    vendedor_asignado: Optional[str] = ""
    sitio_web: Optional[str] = ""
    created_at: datetime
    class Config:
        from_attributes = True


# --- Cotizaciones ---
class CotizacionCreate(BaseModel):
    cliente_id: int
    producto: str
    descripcion: str = ""
    cantidad: str = ""
    precio_objetivo: str = ""
    plazo: str = ""
    uso_final: str = ""
    personalizacion: str = ""

class CotizacionUpdate(BaseModel):
    estado: Optional[str] = None
    producto: Optional[str] = None
    descripcion: Optional[str] = None

class CotizacionOut(BaseModel):
    id: int
    cliente_id: int
    producto: str
    descripcion: str
    cantidad: str
    precio_objetivo: str
    plazo: str
    uso_final: str
    personalizacion: str
    estado: str
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True


# --- Pedidos ---
class PedidoCreate(BaseModel):
    cotizacion_id: int
    precio_unitario: float = 0
    condiciones: str = ""
    monto_total: float = 0

class PedidoUpdate(BaseModel):
    estado: Optional[str] = None
    etapa_actual: Optional[int] = None
    precio_unitario: Optional[float] = None
    condiciones: Optional[str] = None
    monto_total: Optional[float] = None

class PedidoOut(BaseModel):
    id: int
    cotizacion_id: int
    precio_unitario: float
    condiciones: str
    monto_total: float
    estado: str
    etapa_actual: int
    created_at: datetime
    class Config:
        from_attributes = True


# --- Facturas ---
class FacturaCreate(BaseModel):
    pedido_id: Optional[int] = None
    tipo: str  # gasto, ingreso
    categoria: str = ""
    descripcion: str = ""
    monto: float
    fecha: datetime
    estado: str = "pendiente"
    archivo_url: str = ""

class FacturaOut(BaseModel):
    id: int
    pedido_id: Optional[int]
    tipo: str
    categoria: str
    descripcion: str
    monto: float
    fecha: datetime
    estado: str
    archivo_url: str
    created_at: datetime
    class Config:
        from_attributes = True


# --- Movimientos Contables ---
class MovimientoCreate(BaseModel):
    tipo: str
    categoria: str = ""
    descripcion: str = ""
    monto: float
    fecha: datetime
    estado: str = "pendiente"
    pedido_id: Optional[int] = None
    comprobante_url: str = ""

class MovimientoOut(BaseModel):
    id: int
    tipo: str
    categoria: str
    descripcion: str
    monto: float
    fecha: datetime
    estado: str
    pedido_id: Optional[int]
    comprobante_url: str
    created_at: datetime
    class Config:
        from_attributes = True


# --- Auth ---
class LoginRequest(BaseModel):
    email: str
    password: str


# --- Clientes Update ---
class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    empresa: Optional[str] = None
    rut: Optional[str] = None
    rubro: Optional[str] = None
    telefono: Optional[str] = None
    num_empleados: Optional[str] = None
    referido_por: Optional[str] = None
    vendedor_asignado: Optional[str] = None
    sitio_web: Optional[str] = None


# --- Historial ---
class HistorialOut(BaseModel):
    id: int
    tipo: str
    accion: str
    entidad_id: Optional[int]
    descripcion: str
    usuario: Optional[str]
    cliente_id: Optional[int]
    created_at: datetime
    class Config:
        from_attributes = True


# --- Site Content ---
class SiteContentUpdate(BaseModel):
    section: str
    key: str
    value: str
    content_type: str = "text"

class SiteContentOut(BaseModel):
    id: int
    section: str
    key: str
    value: str
    content_type: str
    updated_at: datetime
    class Config:
        from_attributes = True
