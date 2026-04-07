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

class ClienteOut(BaseModel):
    id: int
    nombre: str
    empresa: str
    rut: str
    rubro: str
    email: str
    telefono: str
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
