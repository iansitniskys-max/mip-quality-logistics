import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from database import engine, get_db, Base
from models import Cliente, Cotizacion, Pedido, Factura, Archivo, MovimientoContable
from schemas import (
    ClienteCreate, ClienteOut, CotizacionCreate, CotizacionUpdate, CotizacionOut,
    PedidoCreate, PedidoUpdate, PedidoOut, FacturaCreate, FacturaOut,
    MovimientoCreate, MovimientoOut, LoginRequest,
)

app = FastAPI(title="MIP Q&L API", version="1.0.0")

STATIC_DIR = os.getenv("STATIC_DIR", "/app/frontend")

# Serve uploaded files
os.makedirs("/app/uploads", exist_ok=True)


@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Warning: Could not create tables: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GCS_BUCKET = os.getenv("GCS_BUCKET", "mip-crm-files")


# ─── Health ───
@app.get("/api/health")
def health():
    return {"status": "ok"}


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


# ─── Auth ───
@app.post("/api/auth/google")
def google_login(request_body: dict, db: Session = Depends(get_db)):
    """Verify Google ID token and create/login user"""
    credential = request_body.get("credential", "")
    if not credential:
        raise HTTPException(400, "No credential provided")

    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as g_requests
        idinfo = id_token.verify_oauth2_token(credential, g_requests.Request(), GOOGLE_CLIENT_ID)
    except Exception as e:
        raise HTTPException(401, f"Invalid Google token: {str(e)}")

    email = idinfo.get("email", "")
    nombre = idinfo.get("name", "")
    picture = idinfo.get("picture", "")

    # Find or create user
    cliente = db.query(Cliente).filter(Cliente.email == email).first()
    if not cliente:
        cliente = Cliente(nombre=nombre, email=email, empresa="", rut="", rubro="", telefono="")
        db.add(cliente)
        db.commit()
        db.refresh(cliente)

    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "email": cliente.email,
        "empresa": cliente.empresa,
        "picture": picture,
        "role": "client",
    }


@app.post("/api/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email == data.email).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    return {"id": cliente.id, "nombre": cliente.nombre, "email": cliente.email, "empresa": cliente.empresa, "role": "client"}


@app.post("/api/auth/register")
def register(data: ClienteCreate, db: Session = Depends(get_db)):
    existing = db.query(Cliente).filter(Cliente.email == data.email).first()
    if existing:
        raise HTTPException(400, "Email ya registrado")
    cliente = Cliente(
        nombre=data.nombre, empresa=data.empresa, rut=data.rut,
        rubro=data.rubro, email=data.email, telefono=data.telefono,
        password_hash=data.password,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return {"id": cliente.id, "nombre": cliente.nombre, "email": cliente.email}


# ─── Clientes ───
@app.get("/api/clientes", response_model=list[ClienteOut])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(Cliente).order_by(Cliente.created_at.desc()).all()


@app.get("/api/clientes/{id}", response_model=ClienteOut)
def get_cliente(id: int, db: Session = Depends(get_db)):
    c = db.query(Cliente).get(id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


# ─── Cotizaciones ───
@app.get("/api/cotizaciones", response_model=list[CotizacionOut])
def listar_cotizaciones(
    estado: Optional[str] = None,
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Cotizacion)
    if estado:
        q = q.filter(Cotizacion.estado == estado)
    if cliente_id:
        q = q.filter(Cotizacion.cliente_id == cliente_id)
    return q.order_by(Cotizacion.created_at.desc()).all()


@app.post("/api/cotizaciones", response_model=CotizacionOut)
def crear_cotizacion(data: CotizacionCreate, db: Session = Depends(get_db)):
    cot = Cotizacion(**data.model_dump())
    db.add(cot)
    db.commit()
    db.refresh(cot)
    return cot


@app.get("/api/cotizaciones/{id}", response_model=CotizacionOut)
def get_cotizacion(id: int, db: Session = Depends(get_db)):
    c = db.query(Cotizacion).get(id)
    if not c:
        raise HTTPException(404, "Cotización no encontrada")
    return c


@app.put("/api/cotizaciones/{id}", response_model=CotizacionOut)
def update_cotizacion(id: int, data: CotizacionUpdate, db: Session = Depends(get_db)):
    c = db.query(Cotizacion).get(id)
    if not c:
        raise HTTPException(404, "Cotización no encontrada")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


# ─── Pedidos ───
@app.get("/api/pedidos", response_model=list[PedidoOut])
def listar_pedidos(db: Session = Depends(get_db)):
    return db.query(Pedido).order_by(Pedido.created_at.desc()).all()


@app.post("/api/pedidos", response_model=PedidoOut)
def crear_pedido(data: PedidoCreate, db: Session = Depends(get_db)):
    pedido = Pedido(**data.model_dump())
    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return pedido


@app.put("/api/pedidos/{id}", response_model=PedidoOut)
def update_pedido(id: int, data: PedidoUpdate, db: Session = Depends(get_db)):
    p = db.query(Pedido).get(id)
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


# ─── Facturas ───
@app.get("/api/facturas", response_model=list[FacturaOut])
def listar_facturas(
    pedido_id: Optional[int] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Factura)
    if pedido_id:
        q = q.filter(Factura.pedido_id == pedido_id)
    if tipo:
        q = q.filter(Factura.tipo == tipo)
    return q.order_by(Factura.fecha.desc()).all()


@app.post("/api/facturas", response_model=FacturaOut)
def crear_factura(data: FacturaCreate, db: Session = Depends(get_db)):
    f = Factura(**data.model_dump())
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ─── Archivos ───
@app.post("/api/archivos/upload")
async def upload_archivo(
    file: UploadFile = File(...),
    pedido_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    content = await file.read()
    filename = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

    # Try GCS upload, fallback to local
    url = ""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(content, content_type=file.content_type)
        url = f"https://storage.googleapis.com/{GCS_BUCKET}/{filename}"
    except Exception:
        # Fallback: store locally
        os.makedirs("uploads", exist_ok=True)
        local_path = f"uploads/{file.filename}"
        with open(local_path, "wb") as f:
            f.write(content)
        url = f"/uploads/{file.filename}"

    archivo = Archivo(
        pedido_id=pedido_id,
        nombre=file.filename,
        url=url,
        tipo=file.filename.rsplit(".", 1)[-1] if "." in file.filename else "unknown",
        size=len(content),
    )
    db.add(archivo)
    db.commit()
    db.refresh(archivo)
    return {"id": archivo.id, "nombre": archivo.nombre, "url": archivo.url, "size": archivo.size}


@app.get("/api/archivos")
def listar_archivos(pedido_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Archivo)
    if pedido_id:
        q = q.filter(Archivo.pedido_id == pedido_id)
    return q.order_by(Archivo.created_at.desc()).all()


# ─── Contabilidad ───
@app.get("/api/contabilidad", response_model=list[MovimientoOut])
def listar_movimientos(
    tipo: Optional[str] = None,
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(MovimientoContable)
    if tipo:
        q = q.filter(MovimientoContable.tipo == tipo)
    if mes:
        q = q.filter(extract("month", MovimientoContable.fecha) == mes)
    if anio:
        q = q.filter(extract("year", MovimientoContable.fecha) == anio)
    return q.order_by(MovimientoContable.fecha.desc()).all()


@app.post("/api/contabilidad", response_model=MovimientoOut)
def crear_movimiento(data: MovimientoCreate, db: Session = Depends(get_db)):
    m = MovimientoContable(**data.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@app.get("/api/contabilidad/resumen")
def resumen_contable(
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(MovimientoContable)
    if mes:
        q = q.filter(extract("month", MovimientoContable.fecha) == mes)
    if anio:
        q = q.filter(extract("year", MovimientoContable.fecha) == anio)

    ingresos = q.filter(MovimientoContable.tipo == "ingreso").with_entities(func.coalesce(func.sum(MovimientoContable.monto), 0)).scalar()
    gastos = q.filter(MovimientoContable.tipo == "gasto").with_entities(func.coalesce(func.sum(MovimientoContable.monto), 0)).scalar()
    pendientes = q.filter(MovimientoContable.estado == "pendiente").count()

    return {
        "ingresos": float(ingresos),
        "gastos": float(gastos),
        "utilidad_neta": float(ingresos) - float(gastos),
        "margen": round((float(ingresos) - float(gastos)) / float(ingresos) * 100, 1) if ingresos > 0 else 0,
        "facturas_pendientes": pendientes,
    }


# ─── Dashboard Stats ───
@app.get("/api/dashboard/stats")
def dashboard_stats(cliente_id: Optional[int] = None, db: Session = Depends(get_db)):
    cot_q = db.query(Cotizacion)
    ped_q = db.query(Pedido)
    if cliente_id:
        cot_q = cot_q.filter(Cotizacion.cliente_id == cliente_id)
        ped_q = ped_q.join(Cotizacion).filter(Cotizacion.cliente_id == cliente_id)

    activas = cot_q.filter(Cotizacion.estado.in_(["pendiente", "cotizado"])).count()
    en_curso = ped_q.filter(Pedido.estado == "activo").count()
    completados = ped_q.filter(Pedido.estado == "completado").count()
    total_monto = ped_q.filter(Pedido.estado == "completado").with_entities(
        func.coalesce(func.sum(Pedido.monto_total), 0)
    ).scalar()

    return {
        "cotizaciones_activas": activas,
        "pedidos_en_curso": en_curso,
        "completados": completados,
        "total_importado": float(total_monto),
    }


# ─── Serve Frontend ───
@app.get("/health")
def health_nginx():
    return {"status": "ok"}


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, media_type="text/html")
    return {"error": "Frontend not found"}
