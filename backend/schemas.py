from pydantic import BaseModel
from typing import Optional, List
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
    empresa: Optional[str] = ""
    razon_social: Optional[str] = ""
    rut: Optional[str] = ""
    rubro: Optional[str] = ""
    email: str
    telefono: Optional[str] = ""
    num_empleados: Optional[str] = ""
    referido_por: Optional[str] = ""
    vendedor_asignado: Optional[str] = ""
    kam_responsable: Optional[str] = ""
    sitio_web: Optional[str] = ""
    ciudad: Optional[str] = ""
    direccion_despacho: Optional[str] = ""
    condicion_pago: Optional[str] = ""
    notas: Optional[str] = ""
    activo: Optional[str] = "true"
    role: Optional[str] = "client"
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
    proyecto_nombre: Optional[str] = ""
    proyecto_descripcion: Optional[str] = ""

class CotizacionUpdate(BaseModel):
    estado: Optional[str] = None
    producto: Optional[str] = None
    descripcion: Optional[str] = None
    cantidad: Optional[str] = None
    precio_objetivo: Optional[str] = None
    plazo: Optional[str] = None
    uso_final: Optional[str] = None
    personalizacion: Optional[str] = None
    proyecto_nombre: Optional[str] = None
    proyecto_descripcion: Optional[str] = None

class CotizacionOut(BaseModel):
    id: int
    cliente_id: int
    producto: str
    descripcion: Optional[str] = ""
    cantidad: Optional[str] = ""
    precio_objetivo: Optional[str] = ""
    plazo: Optional[str] = ""
    uso_final: Optional[str] = ""
    personalizacion: Optional[str] = ""
    proyecto_nombre: Optional[str] = ""
    proyecto_descripcion: Optional[str] = ""
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
    monto: float  # CLP
    moneda: str = "CLP"
    fecha: datetime
    estado: str = "pendiente"
    pedido_id: Optional[int] = None
    comprobante_url: str = ""
    pagado_por_socio_id: Optional[int] = None
    medio_pago: str = ""
    notas: str = ""
    split_socio_ids: List[int] = []  # socios entre los cuales se divide (split igual)

class MovimientoOut(BaseModel):
    id: int
    tipo: str
    categoria: Optional[str] = ""
    descripcion: Optional[str] = ""
    monto: float
    moneda: Optional[str] = "CLP"
    fecha: datetime
    estado: str
    pedido_id: Optional[int]
    comprobante_url: Optional[str] = ""
    pagado_por_socio_id: Optional[int] = None
    medio_pago: Optional[str] = ""
    notas: Optional[str] = ""
    created_at: datetime
    class Config:
        from_attributes = True


# --- Socios (Splitwise) ---
class SocioCreate(BaseModel):
    nombre: str
    email: Optional[str] = ""
    porcentaje_equity: float = 0
    activo: bool = True
    color: str = "#e8af43"
    notas: str = ""

class SocioOut(BaseModel):
    id: int
    nombre: str
    email: Optional[str] = ""
    porcentaje_equity: float
    activo: bool
    color: Optional[str] = "#e8af43"
    notas: Optional[str] = ""
    class Config:
        from_attributes = True

class GastoSplitOut(BaseModel):
    id: int
    movimiento_id: int
    socio_id: int
    monto_asumido: float
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
    razon_social: Optional[str] = None
    rut: Optional[str] = None
    rubro: Optional[str] = None
    telefono: Optional[str] = None
    num_empleados: Optional[str] = None
    referido_por: Optional[str] = None
    vendedor_asignado: Optional[str] = None
    kam_responsable: Optional[str] = None
    sitio_web: Optional[str] = None
    ciudad: Optional[str] = None
    direccion_despacho: Optional[str] = None
    condicion_pago: Optional[str] = None
    notas: Optional[str] = None
    activo: Optional[str] = None


# --- Actividades ---
class ActividadCreate(BaseModel):
    cliente_id: Optional[int] = None
    cotizacion_id: Optional[int] = None
    tipo: str = "nota"
    titulo: Optional[str] = ""
    descripcion: str = ""
    etapa_anterior: Optional[str] = None
    etapa_nueva: Optional[str] = None
    autor: Optional[str] = ""

class ActividadOut(BaseModel):
    id: int
    cliente_id: Optional[int]
    cotizacion_id: Optional[int]
    tipo: str
    titulo: Optional[str] = ""
    descripcion: Optional[str] = ""
    etapa_anterior: Optional[str] = ""
    etapa_nueva: Optional[str] = ""
    autor: Optional[str] = ""
    created_at: datetime
    class Config:
        from_attributes = True


# --- Feature Flags ---
class FeatureFlagOut(BaseModel):
    modulo: str
    activo: str
    config: Optional[str] = None
    class Config:
        from_attributes = True


# --- Proveedores ---
class ProveedorCreate(BaseModel):
    nombre: str
    ciudad_china: Optional[str] = ""
    contacto: Optional[str] = ""
    email: Optional[str] = ""
    whatsapp: Optional[str] = ""
    website: Optional[str] = ""
    certificaciones: Optional[str] = "[]"
    fortalezas: Optional[str] = "[]"
    categorias: Optional[str] = "[]"
    notas: Optional[str] = ""
    rating: int = 3

class ProveedorOut(BaseModel):
    id: int
    nombre: str
    ciudad_china: Optional[str] = ""
    contacto: Optional[str] = ""
    email: Optional[str] = ""
    whatsapp: Optional[str] = ""
    website: Optional[str] = ""
    certificaciones: Optional[str] = "[]"
    fortalezas: Optional[str] = "[]"
    categorias: Optional[str] = "[]"
    notas: Optional[str] = ""
    activo: Optional[str] = "true"
    rating: Optional[int] = 3
    created_at: datetime
    class Config:
        from_attributes = True


class ProductoProveedorCreate(BaseModel):
    proveedor_id: int
    sku: Optional[str] = ""
    nombre: str
    categoria: Optional[str] = ""
    precio_fob: float = 0
    moq: int = 0
    lead_time_dias: int = 45

class ProductoProveedorOut(BaseModel):
    id: int
    proveedor_id: int
    sku: Optional[str] = ""
    nombre: str
    categoria: Optional[str] = ""
    precio_fob: float
    moq: int
    lead_time_dias: int
    activo: Optional[str] = "true"
    class Config:
        from_attributes = True


# --- Prospects ---
class ProspectCreate(BaseModel):
    nombre: str
    empresa: Optional[str] = ""
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    sector: Optional[str] = ""
    fuente: str = "otro"
    notas: Optional[str] = ""

class ProspectOut(BaseModel):
    id: int
    nombre: str
    empresa: Optional[str] = ""
    email: Optional[str] = ""
    telefono: Optional[str] = ""
    sector: Optional[str] = ""
    fuente: Optional[str] = "otro"
    score_ia: Optional[int] = 50
    notas: Optional[str] = ""
    estado: str = "nuevo"
    convertido_a_cliente_id: Optional[int] = None
    created_at: datetime
    class Config:
        from_attributes = True


# --- Email Automation ---
class EmailSequenceCreate(BaseModel):
    nombre: str
    etapa_trigger: Optional[str] = ""
    delay_horas: int = 0
    asunto_template: str
    cuerpo_template: str
    activo: str = "true"

class EmailSequenceOut(BaseModel):
    id: int
    nombre: str
    etapa_trigger: Optional[str] = ""
    delay_horas: int
    asunto_template: str
    cuerpo_template: str
    activo: str
    class Config:
        from_attributes = True


class EmailLogOut(BaseModel):
    id: int
    cotizacion_id: Optional[int]
    sequence_id: Optional[int]
    destinatario: str
    asunto: Optional[str] = ""
    estado: str
    programado_para: Optional[datetime]
    enviado_at: Optional[datetime]
    created_at: datetime
    class Config:
        from_attributes = True


# --- Proyectos ---
class ProyectoCreate(BaseModel):
    cotizacion_id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = ""
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    color: Optional[str] = "#1d6fa5"

class ProyectoOut(BaseModel):
    id: int
    cotizacion_id: Optional[int]
    nombre: str
    descripcion: Optional[str] = ""
    estado: str
    fecha_inicio: Optional[datetime]
    fecha_fin: Optional[datetime]
    color: Optional[str] = "#1d6fa5"
    created_by: Optional[str] = ""
    created_at: datetime
    class Config:
        from_attributes = True


class TareaCreate(BaseModel):
    proyecto_id: int
    seccion_id: Optional[int] = None
    parent_id: Optional[int] = None
    nombre: str
    descripcion: Optional[str] = ""
    prioridad: str = "media"
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    asignado_a: Optional[str] = ""
    es_milestone: str = "false"

class TareaOut(BaseModel):
    id: int
    proyecto_id: int
    seccion_id: Optional[int]
    parent_id: Optional[int]
    nombre: str
    descripcion: Optional[str] = ""
    estado: str
    prioridad: str
    fecha_inicio: Optional[datetime]
    fecha_fin: Optional[datetime]
    progreso: int
    orden: int
    es_milestone: str
    asignado_a: Optional[str] = ""
    class Config:
        from_attributes = True


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


# --- Mateo AI Trainer ---
class MateoConfigOut(BaseModel):
    id: int
    nombre_bot: str
    tono: str
    longitud_respuesta: str
    system_prompt: Optional[str] = ""
    reglas_negocio: Optional[str] = ""
    flujo_conversacion: Optional[str] = ""
    precios_publicos: Optional[str] = ""
    auto_agendar_reuniones: bool
    calendar_email: Optional[str] = ""
    idioma: str
    max_tokens_respuesta: int
    modelo_ia: str
    activo: bool
    class Config:
        from_attributes = True


class MateoConversationOut(BaseModel):
    id: int
    session_id: str
    cliente_id: Optional[int] = None
    prospect_id: Optional[int] = None
    visitor_email: Optional[str] = ""
    visitor_nombre: Optional[str] = ""
    visitor_telefono: Optional[str] = ""
    visitor_empresa: Optional[str] = ""
    interes_detectado: Optional[str] = ""
    sentimiento: Optional[str] = ""
    tokens_input: int
    tokens_output: int
    mensajes_count: int
    convertido_a_prospect: bool
    proveedor_ia: Optional[str] = "gemini"
    duracion_seg: int
    inicio_at: datetime
    ultimo_mensaje_at: datetime
    class Config:
        from_attributes = True


# --- Agent Builder ---
class AgentBlockOut(BaseModel):
    id: int
    agent_id: int
    tipo: str
    categoria: str
    nombre: str
    contenido: str
    orden: int
    activo: bool
    sub_steps: Optional[str] = "[]"
    es_reusable: bool
    block_key: Optional[str] = ""
    class Config:
        from_attributes = True


class AgentBlockCreate(BaseModel):
    agent_id: Optional[int] = None
    tipo: str
    categoria: str = "identidad"
    nombre: str
    contenido: str
    orden: int = 0
    activo: bool = True
    sub_steps: str = "[]"
    es_reusable: bool = False
    block_key: Optional[str] = ""


class AgentConfigOut(BaseModel):
    id: int
    agent_type: str
    display_name: str
    descripcion: Optional[str] = ""
    avatar: Optional[str] = ""
    modelo: str
    activo: bool
    tools_allowed: str
    max_tool_calls: int
    kb_folder_ids: str
    stages: str
    temperatura: float
    max_tokens: int
    total_conversations: int
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    created_at: datetime
    class Config:
        from_attributes = True


class AgentConfigCreate(BaseModel):
    agent_type: str
    display_name: str
    descripcion: str = ""
    avatar: str = "🤖"
    modelo: str = "gemini-2.5-flash"
    activo: bool = True
    tools_allowed: str = "[]"
    max_tool_calls: int = 8
    kb_folder_ids: str = "[]"
    stages: str = "[]"
    temperatura: float = 0.7
    max_tokens: int = 800


class ToolOut(BaseModel):
    id: int
    name: str
    description: str
    categoria: str
    schema_input: str
    activo: bool
    peligroso: bool
    handler: Optional[str] = ""
    class Config:
        from_attributes = True


class KBFolderOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str] = ""
    color: str
    class Config:
        from_attributes = True


class KBDocOut(BaseModel):
    id: int
    folder_id: int
    nombre: str
    tokens_totales: int
    class Config:
        from_attributes = True


# --- Pipeline / Handoff / Integrations ---
class ConversationPipelineOut(BaseModel):
    id: int
    session_id: str
    current_stage: str
    current_agent_id: Optional[int] = None
    prospect_id: Optional[int] = None
    cliente_id: Optional[int] = None
    visitor_nombre: Optional[str] = ""
    visitor_email: Optional[str] = ""
    visitor_telefono: Optional[str] = ""
    visitor_empresa: Optional[str] = ""
    intent_detected: Optional[str] = ""
    intent_score: float = 0.0
    sentiment: Optional[str] = "neutral"
    requires_human: bool
    human_handoff_reason: Optional[str] = ""
    total_messages: int
    created_at: datetime
    class Config:
        from_attributes = True


class HumanHandoffOut(BaseModel):
    id: int
    session_id: str
    visitor_nombre: Optional[str] = ""
    visitor_email: Optional[str] = ""
    visitor_telefono: Optional[str] = ""
    motivo: Optional[str] = ""
    urgencia: str
    estado: str
    asignado_a: Optional[str] = ""
    notified_via: Optional[str] = ""
    whatsapp_sent: bool
    created_at: datetime
    class Config:
        from_attributes = True


class AgentIntegrationOut(BaseModel):
    id: int
    agent_id: int
    tipo: str
    nombre: Optional[str] = ""
    activo: bool
    config: Optional[str] = "{}"
    class Config:
        from_attributes = True
