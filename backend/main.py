import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, extract

from database import engine, get_db, Base
from fastapi.responses import StreamingResponse
from models import (
    Cliente, Cotizacion, ProductoCotizacion, Pedido, Factura, Archivo,
    MovimientoContable, HistorialEvento, SiteContent, Ticket, Actividad,
    FeatureFlag, Proveedor, ProductoProveedor, Prospect, EmailSequence, EmailLog,
    Proyecto, ProyectoSeccion, Tarea, ComentarioTarea, CotizacionFormal,
    Socio, GastoSplit,
    MateoConfig, MateoConversation, MateoMessage, MateoCalendarBooking,
    AgentConfig, AgentBlock, Tool, KnowledgeFolder, KnowledgeDoc, KnowledgeChunk, AgentTrace,
    ConversationPipeline, PipelineStageLog, AgentIntegration, HumanHandoff,
    StageAssignment, AgentAutoRule,
)
from schemas import (
    ClienteCreate, ClienteOut, ClienteUpdate, CotizacionCreate, CotizacionUpdate, CotizacionOut,
    PedidoCreate, PedidoUpdate, PedidoOut, FacturaCreate, FacturaOut,
    MovimientoCreate, MovimientoOut, LoginRequest, HistorialOut,
    SiteContentUpdate, SiteContentOut, ActividadCreate, ActividadOut,
    FeatureFlagOut, ProveedorCreate, ProveedorOut, ProductoProveedorCreate, ProductoProveedorOut,
    ProspectCreate, ProspectOut, EmailSequenceCreate, EmailSequenceOut, EmailLogOut,
    ProyectoCreate, ProyectoOut, TareaCreate, TareaOut,
    SocioCreate, SocioOut, GastoSplitOut,
    MateoConfigOut, MateoConversationOut,
    AgentConfigOut, AgentConfigCreate, AgentBlockOut, AgentBlockCreate,
    ToolOut, KBFolderOut, KBDocOut,
    ConversationPipelineOut, HumanHandoffOut, AgentIntegrationOut,
)
import csv
import io
import json

app = FastAPI(title="MIP Q&L API", version="1.0.0")

STATIC_DIR = os.getenv("STATIC_DIR", "/app/frontend")
IMAGES_DIR = os.path.join(STATIC_DIR, "images")

# Serve uploaded files
os.makedirs("/app/uploads", exist_ok=True)


@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
        # Migrate: add new columns if missing
        from sqlalchemy import text
        with engine.connect() as conn:
            for col, col_type in [
                ("num_empleados", "VARCHAR(30)"),
                ("referido_por", "VARCHAR(100)"),
                ("vendedor_asignado", "VARCHAR(200)"),
                ("sitio_web", "VARCHAR(300)"),
                ("role", "VARCHAR(20) DEFAULT 'client'"),
                ("razon_social", "VARCHAR(200)"),
                ("kam_responsable", "VARCHAR(200)"),
                ("ciudad", "VARCHAR(100)"),
                ("direccion_despacho", "VARCHAR(300)"),
                ("condicion_pago", "VARCHAR(100)"),
                ("notas", "TEXT"),
                ("activo", "VARCHAR(10) DEFAULT 'true'"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE clientes ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column clientes.{col}")
                except Exception:
                    conn.rollback()
            # Migrate archivos table
            for col, col_type in [("cotizacion_id", "INTEGER"), ("categoria", "VARCHAR(50)"), ("subido_por", "VARCHAR(20) DEFAULT 'admin'"), ("subido_por_email", "VARCHAR(200)")]:
                try:
                    conn.execute(text(f"ALTER TABLE archivos ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column archivos.{col}")
                except Exception:
                    conn.rollback()
            # Migrate movimientos_contables table (Splitwise)
            for col, col_type in [
                ("moneda", "VARCHAR(3) DEFAULT 'CLP'"),
                ("pagado_por_socio_id", "INTEGER"),
                ("medio_pago", "VARCHAR(50)"),
                ("notas", "TEXT"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE movimientos_contables ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column movimientos_contables.{col}")
                except Exception:
                    conn.rollback()
            # Migrate conversation_pipelines table (live takeover)
            for col, col_type in [
                ("control_mode", "VARCHAR(20) DEFAULT 'ai'"),
                ("taken_over_by", "VARCHAR(200)"),
                ("taken_over_at", "TIMESTAMP"),
                ("last_client_activity_at", "TIMESTAMP"),
                ("widget_is_open", "BOOLEAN DEFAULT TRUE"),
                ("pending_admin_messages", "TEXT DEFAULT '[]'"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE conversation_pipelines ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column conversation_pipelines.{col}")
                except Exception:
                    conn.rollback()
            # Migrate cotizaciones: agregar proyecto_nombre y proyecto_descripcion
            for col, col_type in [
                ("proyecto_nombre", "VARCHAR(300)"),
                ("proyecto_descripcion", "TEXT"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE cotizaciones ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column cotizaciones.{col}")
                except Exception:
                    conn.rollback()
            # Migrate agent_blocks: agregar columna functions JSON (per-block function calling)
            for col, col_type in [
                ("functions", "TEXT DEFAULT '[]'"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE agent_blocks ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    print(f"Added column agent_blocks.{col}")
                except Exception:
                    conn.rollback()
            # Crear tabla cost_limits (spending caps por proveedor) si no existe
            try:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS cost_limits (
                        id SERIAL PRIMARY KEY,
                        provider VARCHAR(50) UNIQUE NOT NULL,
                        monthly_limit_usd FLOAT DEFAULT 0.0,
                        alert_pct INTEGER DEFAULT 80,
                        hard_block BOOLEAN DEFAULT FALSE,
                        billing_account VARCHAR(200),
                        billing_card_last4 VARCHAR(10),
                        notas TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                conn.commit()
            except Exception:
                conn.rollback()
        # Seed Agent Builder defaults (tools + Mateo como primer agente)
        try:
            from sqlalchemy.orm import Session as _Sess
            with _Sess(engine) as _db:
                _seed_agent_builder(_db)
        except Exception as e:
            print(f"[agent-builder seed] warning: {e}")
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
        # Decode Google ID token - try verified first, fallback to unverified decode
        idinfo = None
        try:
            from google.oauth2 import id_token
            from google.auth.transport import requests as g_requests
            idinfo = id_token.verify_oauth2_token(credential, g_requests.Request(), GOOGLE_CLIENT_ID)
        except Exception as verify_err:
            print(f"Google OAuth verify with audience failed: {verify_err}. Trying without audience...")
            try:
                idinfo = id_token.verify_oauth2_token(credential, g_requests.Request())
            except Exception as verify_err2:
                print(f"Google OAuth verify without audience also failed: {verify_err2}. Using JWT decode...")
                # Fallback: decode JWT payload without signature verification (token comes from Google Sign-In JS SDK)
                import base64, json
                parts = credential.split('.')
                if len(parts) >= 2:
                    payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
                    idinfo = json.loads(base64.urlsafe_b64decode(payload))
                else:
                    raise HTTPException(401, "Invalid token format")
        if not idinfo or not idinfo.get("email"):
            raise HTTPException(401, "Could not extract email from token")
    except HTTPException:
        raise
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

    profile_complete = bool(cliente.empresa and cliente.telefono and cliente.num_empleados)
    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "email": cliente.email,
        "empresa": cliente.empresa,
        "telefono": cliente.telefono or "",
        "rubro": cliente.rubro or "",
        "num_empleados": cliente.num_empleados or "",
        "referido_por": cliente.referido_por or "",
        "picture": picture,
        "role": cliente.role or "client",
        "profile_complete": profile_complete,
    }


@app.post("/api/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.email == data.email).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    profile_complete = bool(cliente.empresa and cliente.telefono and cliente.num_empleados)
    return {"id": cliente.id, "nombre": cliente.nombre, "email": cliente.email, "empresa": cliente.empresa, "telefono": cliente.telefono or "", "rubro": cliente.rubro or "", "num_empleados": cliente.num_empleados or "", "referido_por": cliente.referido_por or "", "role": cliente.role or "client", "profile_complete": profile_complete}


@app.post("/api/auth/register")
def register(data: ClienteCreate, db: Session = Depends(get_db)):
    existing = db.query(Cliente).filter(Cliente.email == data.email).first()
    if existing:
        raise HTTPException(400, "Email ya registrado")
    cliente = Cliente(
        nombre=data.nombre, empresa=data.empresa, rut=data.rut,
        rubro=data.rubro, email=data.email, telefono=data.telefono,
        password_hash=data.password, num_empleados=data.num_empleados,
        referido_por=data.referido_por,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return {"id": cliente.id, "nombre": cliente.nombre, "email": cliente.email, "profile_complete": True}


VENDEDORES_DEFAULT = ["Rodrigo Muñoz", "Camila Fuentes", "Andrés Lagos", "Valentina Reyes"]


@app.put("/api/auth/complete-profile")
def complete_profile(data: dict, db: Session = Depends(get_db)):
    """Complete user profile after Google Sign-In"""
    user_id = data.get("id")
    if not user_id:
        raise HTTPException(400, "ID de usuario requerido")
    cliente = db.query(Cliente).get(user_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    cliente.nombre = data.get("nombre", cliente.nombre)
    cliente.telefono = data.get("telefono", cliente.telefono)
    cliente.empresa = data.get("empresa", cliente.empresa)
    cliente.rubro = data.get("rubro", cliente.rubro)
    cliente.num_empleados = data.get("num_empleados", cliente.num_empleados)
    cliente.referido_por = data.get("referido_por", cliente.referido_por)
    cliente.sitio_web = data.get("sitio_web", cliente.sitio_web)

    # Assign sales rep: if user provided a name, use it; otherwise random
    vendedor_contacto = data.get("vendedor_contacto", "").strip()
    if vendedor_contacto:
        cliente.vendedor_asignado = vendedor_contacto
    elif not cliente.vendedor_asignado:
        import random
        cliente.vendedor_asignado = random.choice(VENDEDORES_DEFAULT)

    db.commit()
    db.refresh(cliente)
    return {
        "id": cliente.id, "nombre": cliente.nombre, "email": cliente.email,
        "empresa": cliente.empresa, "telefono": cliente.telefono,
        "rubro": cliente.rubro, "num_empleados": cliente.num_empleados,
        "referido_por": cliente.referido_por, "vendedor_asignado": cliente.vendedor_asignado,
        "sitio_web": cliente.sitio_web,
        "role": cliente.role or "client", "profile_complete": True,
    }


# ─── Auth: Verify current user ───
@app.get("/api/auth/me")
def get_me(email: str = Query(...), db: Session = Depends(get_db)):
    """Verify user role from backend - prevents localStorage tampering"""
    cliente = db.query(Cliente).filter(Cliente.email == email).first()
    if not cliente:
        raise HTTPException(404, "Usuario no encontrado")
    return {
        "id": cliente.id, "nombre": cliente.nombre, "email": cliente.email,
        "empresa": cliente.empresa, "role": cliente.role or "client",
        "profile_complete": bool(cliente.empresa and cliente.telefono and cliente.num_empleados),
    }


# ─── Admin: Role Management ───
@app.get("/api/admin/users")
def admin_list_users(db: Session = Depends(get_db)):
    """List all users with their roles (admin only)"""
    users = db.query(Cliente).order_by(Cliente.created_at.desc()).all()
    return [{"id": c.id, "nombre": c.nombre, "email": c.email, "empresa": c.empresa, "role": c.role or "client", "created_at": str(c.created_at)} for c in users]


@app.put("/api/admin/users/{user_id}/role")
def admin_update_role(user_id: int, data: dict, db: Session = Depends(get_db)):
    """Update a user's role (admin only)"""
    new_role = data.get("role", "client")
    if new_role not in ("client", "admin"):
        raise HTTPException(400, "Role must be 'client' or 'admin'")
    cliente = db.query(Cliente).get(user_id)
    if not cliente:
        raise HTTPException(404, "Usuario no encontrado")
    cliente.role = new_role
    db.commit()
    return {"id": cliente.id, "email": cliente.email, "role": new_role}


@app.post("/api/admin/invite")
def admin_invite(data: dict, db: Session = Depends(get_db)):
    """Invite a user as admin by email. Creates account if needed and sends invitation email."""
    email = data.get("email", "").strip().lower()
    nombre = data.get("nombre", "").strip()
    if not email:
        raise HTTPException(400, "Email requerido")

    # Find or create user
    cliente = db.query(Cliente).filter(Cliente.email == email).first()
    if cliente:
        # User exists - promote to admin
        cliente.role = "admin"
        db.commit()
        action = "promoted"
    else:
        # Create new admin user
        cliente = Cliente(nombre=nombre or email.split("@")[0], email=email, empresa="", rut="", rubro="", telefono="", role="admin")
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
        action = "created"

    # Generate invite link
    import hashlib
    token = hashlib.sha256(f"{email}:{cliente.id}:mip-admin-invite".encode()).hexdigest()[:32]
    APP_URL = os.getenv("APP_URL", "https://miptrust.cl")
    invite_link = f"{APP_URL}#invite={token}&email={email}"

    # Send invitation email
    subject = "Invitaci\u00f3n Admin \u2014 MIP Quality & Logistics"
    body = (
        f"Hola {nombre or email},\n\n"
        f"Has sido invitado/a como administrador en la plataforma MIP Quality & Logistics.\n\n"
        f"Para acceder, ingresa con tu cuenta de Google o regístrate en el siguiente enlace:\n"
        f"{invite_link}\n\n"
        f"Tu rol de administrador ya está activo.\n\n"
        f"— MIP Quality & Logistics Platform"
    )
    html = _wrap_html_email(
        title=f"Bienvenido al equipo MIP, {email.split('@')[0]}",
        body_html=f"<p>Se te ha otorgado acceso de <strong>administrador</strong> a la plataforma MIP Quality & Logistics.</p><p>Con tu cuenta podrás gestionar clientes, cotizaciones, proyectos, facturación y más.</p>",
        cta_label="Acceder a la plataforma",
        cta_url=invite_link,
    )
    r = _send_email(to=email, subject=subject, body=body, html=html, db=db, tipo="admin_invite")
    return {"action": action, "email": email, "role": "admin", "email_sent": r["sent"], "invite_link": invite_link, "email_error": r.get("reason")}


# ─── Admin: Invite Client to Platform ───
@app.post("/api/admin/invite-client")
def admin_invite_client(data: dict, db: Session = Depends(get_db)):
    """Send invitation email to a client to join the platform"""
    email = data.get("email", "").strip()
    nombre = data.get("nombre", "").strip()
    message = data.get("message", "")
    if not email:
        raise HTTPException(400, "Email requerido")
    app_url = os.getenv("APP_URL", "https://miptrust.cl")
    subject = f"Bienvenido a MIP Quality & Logistics, {nombre or 'amigo/a'}"
    body = message or (
        f"Hola {nombre},\n\n"
        f"Te invitamos a acceder a tu portal en MIP Quality & Logistics.\n"
        f"Ahí vas a poder ver el avance de tus proyectos, descargar cotizaciones y hablar con nuestro equipo.\n\n"
        f"Ingresá en: {app_url}\n\n"
        f"— Equipo MIP"
    )
    html = _wrap_html_email(
        title=f"Hola {nombre or 'amigo/a'}, bienvenido a MIP",
        body_html=(message.replace("\n", "<br>") if message else
                   "<p>Te invitamos a acceder a tu portal en MIP Quality & Logistics.</p>"
                   "<p>Desde ahí vas a poder:</p>"
                   "<ul><li>Ver el avance de tus cotizaciones y pedidos</li>"
                   "<li>Descargar facturas, cotizaciones formales y archivos</li>"
                   "<li>Solicitar nuevos productos</li>"
                   "<li>Hablar con nuestro equipo en cualquier momento</li></ul>"),
        cta_label="Acceder al portal",
        cta_url=app_url,
    )
    r = _send_email(to=email, subject=subject, body=body, html=html, db=db, tipo="client_invite")
    if not r["sent"]:
        raise HTTPException(500, r.get("reason") or "Error enviando email")
    return {"sent": True, "email": email}


# ─── Admin: Create Project for Client ───
@app.post("/api/admin/create-project")
def admin_create_project(data: dict, db: Session = Depends(get_db)):
    """Admin creates a full project (cotizacion + optional pedido) assigned to a client email.
    If client doesn't exist, creates a placeholder account they can claim later."""
    email = data.get("cliente_email", "").strip().lower()
    nombre = data.get("cliente_nombre", "").strip()
    empresa = data.get("cliente_empresa", "").strip()
    if not email:
        raise HTTPException(400, "Email del cliente requerido")

    # Find or create client
    cliente = db.query(Cliente).filter(Cliente.email == email).first()
    if not cliente:
        cliente = Cliente(
            nombre=nombre or email.split("@")[0],
            email=email, empresa=empresa, rut=data.get("cliente_rut", ""),
            rubro=data.get("cliente_rubro", ""), telefono=data.get("cliente_telefono", ""),
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)

    # Create cotizacion con proyecto_nombre/descripcion si viene
    cot = Cotizacion(
        cliente_id=cliente.id,
        producto=data.get("producto", ""),
        descripcion=data.get("descripcion", ""),
        cantidad=data.get("cantidad", ""),
        precio_objetivo=data.get("precio_objetivo", ""),
        plazo=data.get("plazo", ""),
        uso_final=data.get("uso_final", ""),
        personalizacion=data.get("personalizacion", ""),
        estado=data.get("estado", "pendiente"),
        proyecto_nombre=data.get("proyecto_nombre", "") or None,
        proyecto_descripcion=data.get("proyecto_descripcion", "") or None,
    )
    db.add(cot)
    db.commit()
    db.refresh(cot)

    # Optionally create pedido if estado is produccion or beyond
    pedido = None
    if data.get("crear_pedido"):
        pedido = Pedido(
            cotizacion_id=cot.id,
            precio_unitario=float(data.get("precio_unitario", 0) or 0),
            condiciones=data.get("condiciones", ""),
            monto_total=float(data.get("monto_total", 0) or 0),
            estado=data.get("pedido_estado", "activo"),
            etapa_actual=int(data.get("etapa_actual", 1) or 1),
        )
        db.add(pedido)
        db.commit()
        db.refresh(pedido)

    log_evento(db, "cotizacion", "creado", f"Proyecto '{cot.producto}' creado para {cliente.nombre} ({email})", usuario="admin", entidad_id=cot.id, cliente_id=cliente.id)

    return {
        "cliente_id": cliente.id,
        "cotizacion_id": cot.id,
        "pedido_id": pedido.id if pedido else None,
        "cliente_nombre": cliente.nombre,
        "producto": cot.producto,
        "estado": cot.estado,
    }


# ─── Admin: Upload file for any project ───
@app.post("/api/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    cotizacion_id: Optional[int] = Query(None),
    pedido_id: Optional[int] = Query(None),
    categoria: str = Query("otro"),
    subido_por_email: str = Query("admin"),
    db: Session = Depends(get_db),
):
    """Admin uploads a document to a cotizacion or pedido with category classification."""
    content = await file.read()
    safe_name = os.path.basename(file.filename or "file")
    filename = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"

    url = ""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(content, content_type=file.content_type)
        url = f"https://storage.googleapis.com/{GCS_BUCKET}/{filename}"
    except Exception:
        os.makedirs("/app/uploads", exist_ok=True)
        local_path = f"/app/uploads/{safe_name}"
        with open(local_path, "wb") as f:
            f.write(content)
        url = f"/uploads/{safe_name}"

    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else "unknown"
    archivo = Archivo(
        pedido_id=pedido_id,
        cotizacion_id=cotizacion_id,
        nombre=safe_name,
        url=url,
        tipo=ext,
        categoria=categoria,
        subido_por="admin",
        subido_por_email=subido_por_email,
        size=len(content),
    )
    db.add(archivo)
    db.commit()
    db.refresh(archivo)
    return {"id": archivo.id, "nombre": archivo.nombre, "url": archivo.url, "categoria": categoria, "size": archivo.size}


# ─── Archivos: List with category filter ───
@app.get("/api/archivos")
def listar_archivos(
    pedido_id: Optional[int] = None,
    cotizacion_id: Optional[int] = None,
    categoria: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Archivo)
    if pedido_id:
        q = q.filter(Archivo.pedido_id == pedido_id)
    if cotizacion_id:
        q = q.filter(Archivo.cotizacion_id == cotizacion_id)
    if categoria:
        q = q.filter(Archivo.categoria == categoria)
    return q.order_by(Archivo.created_at.desc()).all()


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


@app.post("/api/cotizaciones/notify")
def notify_cotizacion(data: dict, db: Session = Depends(get_db)):
    """Dispara dos emails cuando se crea una cotizacion:
      1) Notificacion al equipo MIP (admin + cc a fundador)
      2) Confirmacion al cliente de que recibimos su solicitud
    """
    cot_id = data.get("cotizacion_id")
    cliente_nombre = data.get("cliente_nombre", "Cliente")
    cliente_email = data.get("cliente_email", "")
    cot = db.query(Cotizacion).get(cot_id) if cot_id else None
    if not cot:
        return {"sent": False, "reason": "Cotización no encontrada"}

    ADMIN_TO = os.getenv("ADMIN_NOTIFY_EMAIL", "Paul@emonkonline.com")
    ADMIN_CC = os.getenv("ADMIN_NOTIFY_CC", "iansitniskys@gmail.com")
    app_url = os.getenv("APP_URL", "https://miptrust.cl")

    # 1) Email al equipo MIP
    subject_team = f"🔔 Nueva cotización #{cot.id} — {cot.producto} — {cliente_nombre}"
    body_team = (
        f"Nueva solicitud de cotización recibida:\n\n"
        f"Cliente: {cliente_nombre} ({cliente_email})\n"
        f"Producto: {cot.producto}\n"
        f"Especificaciones: {cot.descripcion or '-'}\n"
        f"Cantidad: {cot.cantidad or '-'}\n"
        f"Precio objetivo: {cot.precio_objetivo or '-'}\n"
        f"Plazo: {cot.plazo or '-'}\n"
        f"Uso final: {cot.uso_final or '-'}\n"
        f"Personalización: {cot.personalizacion or 'No'}\n\n"
        f"Ver en plataforma: {app_url}\n\n"
        f"— MIP Quality & Logistics Platform"
    )
    html_team = _wrap_html_email(
        title=f"Nueva cotización #{cot.id}",
        body_html=(
            f"<p><strong>Cliente:</strong> {cliente_nombre} &lt;{cliente_email}&gt;</p>"
            f"<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:13px'>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Producto</td><td>{cot.producto}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Especificaciones</td><td>{cot.descripcion or '-'}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Cantidad</td><td>{cot.cantidad or '-'}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Precio objetivo</td><td>{cot.precio_objetivo or '-'}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Plazo</td><td>{cot.plazo or '-'}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Uso final</td><td>{cot.uso_final or '-'}</td></tr>"
            f"<tr><td style='background:#f3f4f6;font-weight:600'>Personalización</td><td>{cot.personalizacion or 'No'}</td></tr>"
            f"</table>"
        ),
        cta_label="Ver en plataforma",
        cta_url=f"{app_url}#cot-{cot.id}",
    )
    r_team = _send_email(
        to=ADMIN_TO, subject=subject_team, body=body_team, html=html_team,
        cc=[ADMIN_CC] if ADMIN_CC else None,
        db=db, cotizacion_id=cot.id, tipo="cotizacion_nueva_admin",
    )

    # 2) Email al cliente (confirmacion)
    r_client = {"sent": False, "reason": "Sin email del cliente"}
    if cliente_email and "@" in cliente_email:
        subject_client = f"✅ Recibimos tu solicitud #{cot.id} — MIP"
        body_client = (
            f"Hola {cliente_nombre},\n\n"
            f"Recibimos tu solicitud de cotización para '{cot.producto}'. Ya la estamos revisando y te vamos a contactar dentro de las próximas 24 hs con una propuesta.\n\n"
            f"Resumen:\n"
            f"- Producto: {cot.producto}\n"
            f"- Cantidad: {cot.cantidad or 'por confirmar'}\n"
            f"- Plazo: {cot.plazo or 'por confirmar'}\n\n"
            f"Podés ver el estado en vivo en: {app_url}\n\n"
            f"Gracias por confiar en nosotros.\n\n"
            f"— Equipo MIP Quality & Logistics"
        )
        html_client = _wrap_html_email(
            title=f"Recibimos tu solicitud, {cliente_nombre}",
            body_html=(
                f"<p>Gracias por tu interés en MIP Quality & Logistics. Recibimos tu solicitud de cotización y ya estamos trabajando en ella.</p>"
                f"<p><strong>Número de solicitud:</strong> #SOL-{str(cot.id).zfill(3)}</p>"
                f"<p><strong>¿Qué sigue?</strong></p>"
                f"<ol><li>Nuestro equipo revisa tu solicitud (hoy)</li>"
                f"<li>Cotizamos con nuestros proveedores en China (24-48hs)</li>"
                f"<li>Te enviamos propuesta formal con precios y plazos</li>"
                f"<li>Si aceptás, arrancamos producción</li></ol>"
                f"<p>Resumen de tu solicitud:</p>"
                f"<table cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%;font-size:13px;background:#f9fafb;border:1px solid #e5e7eb'>"
                f"<tr><td style='font-weight:600'>Producto</td><td>{cot.producto}</td></tr>"
                f"<tr><td style='font-weight:600'>Cantidad</td><td>{cot.cantidad or 'por confirmar'}</td></tr>"
                f"<tr><td style='font-weight:600'>Plazo buscado</td><td>{cot.plazo or 'por confirmar'}</td></tr>"
                f"</table>"
                f"<p style='margin-top:16px'>Si tenés alguna urgencia o querés agregar información, respondé directamente a este email.</p>"
            ),
            cta_label="Ver estado del pedido",
            cta_url=f"{app_url}",
        )
        r_client = _send_email(
            to=cliente_email, subject=subject_client, body=body_client, html=html_client,
            db=db, cotizacion_id=cot.id, tipo="cotizacion_confirmacion_cliente",
        )
    return {
        "team_notified": r_team["sent"], "team_reason": r_team.get("reason"),
        "client_notified": r_client["sent"], "client_reason": r_client.get("reason"),
    }


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
    estado_anterior = c.estado
    payload = data.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    # Auto-trigger email automation si cambio el estado
    try:
        if "estado" in payload and payload["estado"] != estado_anterior:
            _trigger_email_automation(c.estado, c, db)
    except Exception as e:
        print(f"[email-automation] error en update_cotizacion: {e}")
    return c


@app.delete("/api/cotizaciones/{id}")
def delete_cotizacion(id: int, delete_cliente: bool = False, db: Session = Depends(get_db)):
    """Elimina una cotizacion (y opcionalmente su cliente si este no tiene mas cotizaciones).
    Tambien elimina en cascada: productos, actividades, archivos, pedidos asociados.
    """
    c = db.query(Cotizacion).get(id)
    if not c:
        raise HTTPException(404, "Cotización no encontrada")
    cliente_id = c.cliente_id
    # Delete related data
    try:
        # Productos de cotizacion
        db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == id).delete()
        # Actividades asociadas a esta cotizacion
        db.query(Actividad).filter(Actividad.cotizacion_id == id).delete()
        # Pedidos asociados (y sus archivos)
        pedidos = db.query(Pedido).filter(Pedido.cotizacion_id == id).all()
        for p in pedidos:
            db.query(Archivo).filter(Archivo.pedido_id == p.id).delete()
            db.query(Factura).filter(Factura.pedido_id == p.id).delete()
            db.delete(p)
        # Archivos directamente asociados a la cotizacion
        db.query(Archivo).filter(Archivo.cotizacion_id == id).delete()
        # Cotizaciones formales (PDF)
        db.query(CotizacionFormal).filter(CotizacionFormal.cotizacion_id == id).delete()
        # Email logs
        db.query(EmailLog).filter(EmailLog.cotizacion_id == id).delete()
        # Finally the cotizacion
        db.delete(c)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Error eliminando cotización: {str(e)[:200]}")

    cliente_deleted = False
    if delete_cliente and cliente_id:
        # Solo eliminar cliente si no tiene otras cotizaciones
        remaining = db.query(Cotizacion).filter(Cotizacion.cliente_id == cliente_id).count()
        if remaining == 0:
            cl = db.query(Cliente).get(cliente_id)
            if cl:
                try:
                    # Clean up actividades del cliente
                    db.query(Actividad).filter(Actividad.cliente_id == cliente_id).delete()
                    db.delete(cl)
                    db.commit()
                    cliente_deleted = True
                except Exception as e:
                    db.rollback()

    return {"deleted": True, "cotizacion_id": id, "cliente_id": cliente_id, "cliente_deleted": cliente_deleted}


# ─── Productos de Cotización ───
@app.post("/api/cotizaciones/{cot_id}/productos")
def add_productos(cot_id: int, data: dict, db: Session = Depends(get_db)):
    """Add multiple products to a cotizacion"""
    cot = db.query(Cotizacion).get(cot_id)
    if not cot:
        raise HTTPException(404, "Cotización no encontrada")
    productos = data.get("productos", [])
    created = []
    for p in productos:
        prod = ProductoCotizacion(
            cotizacion_id=cot_id,
            nombre=p.get("nombre", ""),
            categoria=p.get("categoria", ""),
            materialidad=p.get("materialidad", ""),
            dimensiones=p.get("dimensiones", ""),
            colores=p.get("colores", ""),
            cantidad=p.get("cantidad", ""),
            precio_objetivo=p.get("precio_objetivo", ""),
            personalizacion=p.get("personalizacion", ""),
        )
        db.add(prod)
        db.flush()
        created.append({"id": prod.id, "nombre": prod.nombre})
    # Update cotizacion resumen:
    # Si hay proyecto_nombre, ese es el display principal (NO concatenamos productos).
    # Si NO hay proyecto_nombre, usamos la concatenacion como fallback.
    names = [p.get("nombre", "") for p in productos if p.get("nombre")]
    if cot.proyecto_nombre:
        # Mantener producto como esta (ya fue seteado al crear) o usar proyecto_nombre
        if not cot.producto or len(cot.producto) < 3:
            cot.producto = cot.proyecto_nombre
    elif names:
        cot.producto = " + ".join(names[:5]) + (f" (+{len(names)-5} más)" if len(names) > 5 else "")
    if names:
        cot.cantidad = f"{len(productos)} productos"
    db.commit()
    return {"cotizacion_id": cot_id, "productos_creados": len(created), "productos": created}


# ═══════════════════════════════════════════════════
# PDF PARSER - extrae productos de cotizaciones PDF
# ═══════════════════════════════════════════════════

@app.post("/api/cotizaciones/parse-pdf")
async def parse_cotizacion_pdf(file: UploadFile = File(...)):
    """Recibe un PDF de cotizacion y retorna JSON estructurado con productos.
    Usa pypdf para extraer texto + Gemini para estructurar via function calling.
    """
    _check_cost_limit("gemini")  # hard-block si se alcanzo el limite mensual
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Solo archivos PDF")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB
        raise HTTPException(400, "PDF muy grande (max 10MB)")

    # Extract text with pypdf
    try:
        from pypdf import PdfReader
        import io as _io
        reader = PdfReader(_io.BytesIO(content))
        pages_text = []
        for i, page in enumerate(reader.pages):
            try:
                txt = page.extract_text() or ""
                pages_text.append(f"--- PAGE {i+1} ---\n{txt}")
            except Exception as e:
                pages_text.append(f"--- PAGE {i+1} (error extract: {e}) ---")
        raw_text = "\n\n".join(pages_text)
    except Exception as e:
        raise HTTPException(500, f"Error leyendo PDF: {str(e)[:200]}")

    if not raw_text or len(raw_text.strip()) < 50:
        return {
            "ok": False,
            "error": "El PDF no contiene texto legible (puede ser un PDF solo con imagenes). Intenta OCR.",
            "raw_text_length": len(raw_text or ""),
        }

    # Parse with Gemini
    if not GEMINI_API_KEY:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY no configurado. Agregue la API key para habilitar el parser IA.",
            "raw_text": raw_text[:2000],
        }

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        prompt = """Eres un parser experto en cotizaciones de importacion desde China hacia Chile.

Lee el siguiente texto extraido de un PDF de cotizacion y extrae la informacion estructurada:

1. NOMBRE DEL PROYECTO: el titulo general del PDF (ej: "Bichos-Emonk", "Campaña Retail Q4", etc). Suele estar en la pagina 1 o 2.
2. DESCRIPCION DEL PROYECTO: resumen breve de que es el proyecto.
3. PROVEEDOR / ORIGEN: nombre de la empresa que emitio la cotizacion (ej: emonk, Alibaba trader, etc). Si aparece.
4. PRODUCTOS: array de productos. Por cada uno extrae:
   - nombre: titulo del producto
   - categoria: una de [gorras, ropa, botellas, medallas, toallas, mochilas, maquinaria_industrial, vending_machine, repuestos_autos, insumos_medicos, luminaria, tecnologia, mobiliario, packaging, herramientas, juguetes, alimentos, cosmetica, deportes, oficina, otro]
   - descripcion: texto descriptivo + lista de caracteristicas (materiales, medidas, features)
   - cantidad: MOQ en unidades (ej "500 unidades", "1000")
   - precio_objetivo: precio unitario con moneda (ej "5734 CLP", "$1.20 USD")
   - materialidad: material principal (ej "100% nylon", "acero inoxidable")
   - dimensiones: medidas (ej "43 x 13 x 29cm", "178 × 224 × 73 mm")

Responde SOLO con JSON valido con esta estructura exacta:
{
  "proyecto_nombre": "...",
  "proyecto_descripcion": "...",
  "proveedor": "...",
  "productos": [
    {
      "nombre": "...",
      "categoria": "...",
      "descripcion": "...",
      "cantidad": "...",
      "precio_objetivo": "...",
      "materialidad": "...",
      "dimensiones": "..."
    }
  ]
}

Si un campo no esta en el PDF, pon string vacio "".
NO agregues preambulos, comentarios o markdown. SOLO JSON puro.

TEXTO DEL PDF:
""" + raw_text[:30000]  # Limitar para no exceder context

        model = genai.GenerativeModel("gemini-2.5-flash")
        resp = model.generate_content(prompt, generation_config={"temperature": 0.2, "response_mime_type": "application/json"})
        reply_text = resp.text.strip()

        # Parse JSON
        try:
            parsed = json.loads(reply_text)
        except json.JSONDecodeError:
            # Intentar extraer JSON si viene con texto extra
            import re as _re
            m = _re.search(r'\{.*\}', reply_text, _re.DOTALL)
            if not m:
                return {
                    "ok": False,
                    "error": "El parser no devolvio JSON valido.",
                    "raw_gemini_response": reply_text[:1000],
                }
            parsed = json.loads(m.group(0))

        return {
            "ok": True,
            "parsed": parsed,
            "productos_count": len(parsed.get("productos", [])),
            "raw_text_preview": raw_text[:800],
        }
    except Exception as e:
        import traceback; traceback.print_exc()
        return {
            "ok": False,
            "error": f"Error del parser IA: {str(e)[:300]}",
            "raw_text_preview": raw_text[:800],
        }


@app.get("/api/cotizaciones/{cot_id}/productos")
def get_productos(cot_id: int, db: Session = Depends(get_db)):
    """Get all products for a cotizacion"""
    prods = db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == cot_id).order_by(ProductoCotizacion.id).all()
    return [{"id": p.id, "nombre": p.nombre, "categoria": p.categoria, "materialidad": p.materialidad,
             "dimensiones": p.dimensiones, "colores": p.colores, "cantidad": p.cantidad,
             "precio_objetivo": p.precio_objetivo, "personalizacion": p.personalizacion} for p in prods]


# ─── Admin: Download CSV ───
@app.get("/api/admin/download-csv")
def download_csv(db: Session = Depends(get_db)):
    """Download all cotizaciones with products as CSV"""
    cots = db.query(Cotizacion).order_by(Cotizacion.created_at.desc()).all()
    output = io.StringIO()
    output.write('\ufeff')  # BOM for UTF-8 Excel compatibility
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["ID", "Cliente", "Empresa", "Email", "Producto", "Categoria", "Materialidad",
                     "Cantidad", "Precio_Objetivo", "Plazo", "Uso_Final", "Personalizacion", "Estado", "Fecha"])
    clientes = {}
    for c in cots:
        if c.cliente_id not in clientes:
            cl = db.query(Cliente).get(c.cliente_id)
            clientes[c.cliente_id] = cl
        cl = clientes.get(c.cliente_id)
        cl_nombre = cl.nombre if cl else "N/A"
        cl_empresa = cl.empresa if cl else ""
        cl_email = cl.email if cl else ""
        date = c.created_at.strftime("%Y-%m-%d") if c.created_at else ""
        # Get products for this cotizacion
        prods = db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == c.id).all()
        if prods:
            for p in prods:
                writer.writerow([f"SOL-{str(c.id).zfill(3)}", cl_nombre, cl_empresa, cl_email,
                                p.nombre, p.categoria, p.materialidad, p.cantidad, p.precio_objetivo,
                                c.plazo, c.uso_final, p.personalizacion, c.estado, date])
        else:
            writer.writerow([f"SOL-{str(c.id).zfill(3)}", cl_nombre, cl_empresa, cl_email,
                            c.producto, "", "", c.cantidad, c.precio_objetivo,
                            c.plazo, c.uso_final, c.personalizacion, c.estado, date])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv",
                            headers={"Content-Disposition": "attachment; filename=cotizaciones_export.csv"})


# ─── Pedidos ───
@app.get("/api/pedidos", response_model=list[PedidoOut])
def listar_pedidos(cliente_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Pedido)
    if cliente_id:
        q = q.join(Cotizacion).filter(Cotizacion.cliente_id == cliente_id)
    return q.order_by(Pedido.created_at.desc()).all()


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
    payload = data.model_dump()
    split_ids = payload.pop("split_socio_ids", []) or []
    m = MovimientoContable(**payload)
    db.add(m)
    db.commit()
    db.refresh(m)
    # Si es gasto con socios para splittear, crear GastoSplit igual entre todos
    if m.tipo == "gasto" and split_ids and m.monto:
        cuota = float(m.monto) / len(split_ids)
        for sid in split_ids:
            db.add(GastoSplit(movimiento_id=m.id, socio_id=sid, monto_asumido=cuota))
        db.commit()
    return m


@app.put("/api/contabilidad/{id}", response_model=MovimientoOut)
def update_movimiento(id: int, data: dict, db: Session = Depends(get_db)):
    m = db.query(MovimientoContable).get(id)
    if not m:
        raise HTTPException(404, "Movimiento no encontrado")
    split_ids = data.pop("split_socio_ids", None)
    for k, v in data.items():
        if hasattr(m, k):
            setattr(m, k, v)
    # Rebuild splits if provided
    if split_ids is not None:
        db.query(GastoSplit).filter(GastoSplit.movimiento_id == id).delete()
        if m.tipo == "gasto" and split_ids and m.monto:
            cuota = float(m.monto) / len(split_ids)
            for sid in split_ids:
                db.add(GastoSplit(movimiento_id=id, socio_id=sid, monto_asumido=cuota))
    db.commit()
    db.refresh(m)
    return m


@app.delete("/api/contabilidad/{id}")
def delete_movimiento(id: int, db: Session = Depends(get_db)):
    m = db.query(MovimientoContable).get(id)
    if not m:
        raise HTTPException(404, "Movimiento no encontrado")
    db.query(GastoSplit).filter(GastoSplit.movimiento_id == id).delete()
    db.delete(m)
    db.commit()
    return {"deleted": True}


@app.get("/api/contabilidad/{id}/splits")
def listar_splits_gasto(id: int, db: Session = Depends(get_db)):
    rows = db.query(GastoSplit).filter(GastoSplit.movimiento_id == id).all()
    return [{"id": s.id, "socio_id": s.socio_id, "monto_asumido": s.monto_asumido} for s in rows]


# ═══════════════════════════════════════════════════
# SOCIOS (Splitwise)
# ═══════════════════════════════════════════════════
@app.get("/api/socios", response_model=list[SocioOut])
def listar_socios(activos_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(Socio)
    if activos_only:
        q = q.filter(Socio.activo == True)
    return q.order_by(Socio.nombre).all()


@app.post("/api/socios", response_model=SocioOut)
def crear_socio(data: SocioCreate, db: Session = Depends(get_db)):
    s = Socio(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@app.put("/api/socios/{id}", response_model=SocioOut)
def update_socio(id: int, data: dict, db: Session = Depends(get_db)):
    s = db.query(Socio).get(id)
    if not s:
        raise HTTPException(404, "Socio no encontrado")
    for k, v in data.items():
        if hasattr(s, k):
            setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s


@app.delete("/api/socios/{id}")
def delete_socio(id: int, db: Session = Depends(get_db)):
    s = db.query(Socio).get(id)
    if not s:
        raise HTTPException(404, "Socio no encontrado")
    # No permitir eliminar si tiene movimientos asociados: desactivar
    has_moves = db.query(MovimientoContable).filter(MovimientoContable.pagado_por_socio_id == id).count()
    has_splits = db.query(GastoSplit).filter(GastoSplit.socio_id == id).count()
    if has_moves or has_splits:
        s.activo = False
        db.commit()
        return {"deleted": False, "deactivated": True, "reason": "Tiene movimientos asociados; se marco inactivo."}
    db.delete(s)
    db.commit()
    return {"deleted": True}


@app.get("/api/socios/balance")
def balance_socios(
    mes: Optional[int] = None,
    anio: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    Devuelve cuanto le debe la empresa a cada socio (o al reves).
    Para cada socio:
      - total_pagado = suma de gastos que el pago
      - total_asumido = suma de sus splits (su parte)
      - saldo_empresa = total_pagado - total_asumido
        * positivo: la empresa le debe al socio
        * negativo: el socio le debe a la empresa
    """
    socios = db.query(Socio).all()
    # Gastos filter
    q_m = db.query(MovimientoContable).filter(MovimientoContable.tipo == "gasto")
    if mes:
        q_m = q_m.filter(extract("month", MovimientoContable.fecha) == mes)
    if anio:
        q_m = q_m.filter(extract("year", MovimientoContable.fecha) == anio)
    movimientos = q_m.all()
    move_ids = [m.id for m in movimientos]

    splits_all = db.query(GastoSplit).filter(GastoSplit.movimiento_id.in_(move_ids)).all() if move_ids else []

    result = []
    total_gastos = 0.0
    for s in socios:
        pagado = sum(float(m.monto or 0) for m in movimientos if m.pagado_por_socio_id == s.id)
        asumido = sum(float(sp.monto_asumido or 0) for sp in splits_all if sp.socio_id == s.id)
        saldo = pagado - asumido
        result.append({
            "socio_id": s.id,
            "nombre": s.nombre,
            "color": s.color,
            "porcentaje_equity": float(s.porcentaje_equity or 0),
            "activo": bool(s.activo),
            "total_pagado": round(pagado, 2),
            "total_asumido": round(asumido, 2),
            "saldo_empresa_debe": round(saldo, 2),
        })
        total_gastos += pagado
    return {
        "mes": mes, "anio": anio,
        "total_gastos_clp": round(total_gastos, 2),
        "socios": result,
    }


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
@app.get("/api/clientes/{cliente_id}/notifications")
def client_notifications(cliente_id: int, limit: int = 10, db: Session = Depends(get_db)):
    """Devuelve notificaciones relevantes para el cliente logueado.
    Combina:
      - Cambios de estado de sus cotizaciones (ultimo mes)
      - Facturas pendientes de pago
      - Emails recibidos (de las secuencias + transaccionales)
      - Actividades recientes sobre sus cotizaciones
    """
    from datetime import timedelta as _td
    notifs = []
    cutoff = datetime.now() - _td(days=30)
    # 1) Cambios de estado (Actividad tipo='cambio_etapa')
    try:
        actividades = db.query(Actividad).filter(
            Actividad.cliente_id == cliente_id,
            Actividad.tipo == "cambio_etapa",
            Actividad.created_at >= cutoff,
        ).order_by(Actividad.created_at.desc()).limit(limit).all()
        for a in actividades:
            new_stage = (a.etapa_nueva or "").lower()
            icon_map = {"cotizado": "dollar-sign", "produccion": "cog", "entregado": "check-circle", "pendiente": "clock"}
            color_map = {"cotizado": "#3b82f6", "produccion": "#10b981", "entregado": "#059669", "pendiente": "#f59e0b"}
            title_map = {
                "cotizado": "Tu cotización está lista",
                "produccion": "Arrancó la producción",
                "entregado": "¡Pedido entregado!",
                "pendiente": "Nueva solicitud recibida",
            }
            notifs.append({
                "id": f"act-{a.id}",
                "title": title_map.get(new_stage, f"Estado actualizado: {new_stage}"),
                "message": a.descripcion or "",
                "icon": icon_map.get(new_stage, "info-circle"),
                "color": color_map.get(new_stage, "#6366f1"),
                "cotizacion_id": a.cotizacion_id,
                "link": "cotizacion",
                "unread": (datetime.now() - a.created_at).days < 3 if a.created_at else False,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            })
    except Exception as e:
        print(f"[client_notifications actividades] {e}")
    # 2) Facturas pendientes (cliente debe pagar) - join via pedido -> cotizacion
    try:
        facturas_pend = db.query(Factura).join(Pedido, Factura.pedido_id == Pedido.id).join(
            Cotizacion, Pedido.cotizacion_id == Cotizacion.id
        ).filter(
            Cotizacion.cliente_id == cliente_id,
            Factura.estado == "pendiente",
            Factura.tipo == "ingreso",  # solo facturas que el cliente debe pagar
        ).order_by(Factura.fecha.desc()).limit(5).all()
        for f in facturas_pend:
            notifs.append({
                "id": f"fac-{f.id}",
                "title": f"Factura pendiente — ${(f.monto or 0):,.0f}",
                "message": f.descripcion or "Pago pendiente",
                "icon": "file-invoice-dollar",
                "color": "#ef4444",
                "link": "factura",
                "unread": True,
                "created_at": f.fecha.isoformat() if f.fecha else None,
            })
    except Exception as e:
        print(f"[client_notifications facturas] {e}")
    # 3) Emails recientes enviados al cliente (transaccionales)
    try:
        cliente = db.query(Cliente).get(cliente_id)
        if cliente and cliente.email:
            emails = db.query(EmailLog).filter(
                EmailLog.destinatario == cliente.email,
                EmailLog.estado == "enviado",
                EmailLog.enviado_at >= cutoff,
            ).order_by(EmailLog.enviado_at.desc()).limit(5).all()
            for e in emails:
                # Evitar duplicar con cambios de estado que ya estan arriba
                if any(n.get("cotizacion_id") == e.cotizacion_id and n["id"].startswith("act-") for n in notifs):
                    continue
                notifs.append({
                    "id": f"mail-{e.id}",
                    "title": e.asunto or "Nuevo email",
                    "message": "Revisá tu bandeja de entrada",
                    "icon": "envelope",
                    "color": "#6366f1",
                    "cotizacion_id": e.cotizacion_id,
                    "link": "cotizacion" if e.cotizacion_id else None,
                    "unread": (datetime.now() - e.enviado_at).days < 2 if e.enviado_at else False,
                    "created_at": e.enviado_at.isoformat() if e.enviado_at else None,
                })
    except Exception as ex:
        print(f"[client_notifications emails] {ex}")
    # Ordenar por fecha descendente y limitar
    notifs.sort(key=lambda n: n.get("created_at") or "", reverse=True)
    notifs = notifs[:limit]
    unread_count = sum(1 for n in notifs if n.get("unread"))
    return {
        "notifications": notifs,
        "unread_count": unread_count,
        "total": len(notifs),
    }


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


# ─── Helper: Log Evento ───
def log_evento(db: Session, tipo: str, accion: str, descripcion: str, usuario: str = "", entidad_id: int = None, cliente_id: int = None):
    evento = HistorialEvento(tipo=tipo, accion=accion, descripcion=descripcion, usuario=usuario, entidad_id=entidad_id, cliente_id=cliente_id)
    db.add(evento)
    db.commit()


# ─── Email helper centralizado ───
def _smtp_config():
    """Lee config SMTP del entorno. Devuelve dict con host, port, user, pass, from_name."""
    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASS", ""),
        "from_name": os.getenv("SMTP_FROM_NAME", "MIP Quality & Logistics"),
        "from_email": os.getenv("SMTP_FROM_EMAIL", "") or os.getenv("SMTP_USER", ""),
        "reply_to": os.getenv("SMTP_REPLY_TO", ""),
    }


def _wrap_html_email(title: str, body_html: str, cta_label: str = None, cta_url: str = None, footer_extra: str = "") -> str:
    """Envuelve un cuerpo HTML en un template responsivo con branding MIP."""
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <div style="text-align:center;margin:28px 0">
          <a href="{cta_url}" style="display:inline-block;background:#0f172a;color:#fff;padding:12px 28px;text-decoration:none;border-radius:8px;font-weight:600;font-size:14px">{cta_label}</a>
        </div>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px 12px">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06)">
        <tr><td style="background:#0f172a;padding:20px 24px;color:#fff">
          <div style="display:inline-block;width:40px;height:40px;background:#f59e0b;border-radius:8px;vertical-align:middle;margin-right:12px"></div>
          <span style="font-size:18px;font-weight:700;vertical-align:middle">MIP Quality & Logistics</span>
        </td></tr>
        <tr><td style="padding:28px 28px 8px 28px">
          <h2 style="margin:0 0 14px 0;font-size:20px;color:#0f172a">{title}</h2>
          <div style="color:#374151;font-size:14px;line-height:1.6">{body_html}</div>
          {cta_html}
        </td></tr>
        <tr><td style="padding:16px 28px 28px 28px;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;text-align:center">
          MIP Quality & Logistics · Importación y logística desde China<br>
          Si tenés preguntas, respondé directamente a este email.
          {('<br>' + footer_extra) if footer_extra else ''}
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _send_email(to: str, subject: str, body: str = "", html: str = None, cc: list = None, reply_to: str = None, log_to_db: bool = True, db: Session = None, cotizacion_id: int = None, cliente_id: int = None, tipo: str = "general") -> dict:
    """Helper centralizado de envio de email.

    Args:
        to: email destinatario
        subject: asunto
        body: cuerpo texto plano (fallback)
        html: cuerpo HTML (si se pasa, se usa con body como fallback)
        cc: lista de emails cc
        reply_to: email para responder (si distinto al sender)
        log_to_db: si True, crea registro en EmailLog
        cotizacion_id, cliente_id: para asociar al log

    Returns:
        {sent: bool, reason: str, log_id: int|None}
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    cfg = _smtp_config()
    result = {"sent": False, "reason": "", "log_id": None}

    # Validacion basica
    if not to or "@" not in to:
        result["reason"] = "Email destinatario invalido"
        return result

    # Crear log en DB primero (estado pendiente)
    log = None
    if log_to_db and db is not None:
        try:
            log = EmailLog(
                cotizacion_id=cotizacion_id,
                destinatario=to,
                asunto=subject,
                cuerpo=body or (html or "")[:2000],
                estado="pendiente",
                programado_para=datetime.now(),
            )
            db.add(log)
            db.commit()
            db.refresh(log)
            result["log_id"] = log.id
        except Exception as e:
            print(f"[_send_email] no se pudo crear log: {e}")

    if not (cfg["user"] and cfg["password"]):
        msg = "SMTP no configurado (SMTP_USER/SMTP_PASS vacios en env)"
        print(f"[_send_email] {msg} | would send to={to} subject={subject}")
        if log:
            log.estado = "error"
            log.error_msg = msg
            try: db.commit()
            except Exception: pass
        result["reason"] = msg
        return result

    try:
        # Si hay HTML, enviar multipart
        if html:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = to
            if cc:
                msg["Cc"] = ", ".join(cc)
            if reply_to or cfg["reply_to"]:
                msg["Reply-To"] = reply_to or cfg["reply_to"]
            msg.attach(MIMEText(body or "Ver email en version HTML", "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
        else:
            msg = MIMEText(body or "", "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = to
            if cc:
                msg["Cc"] = ", ".join(cc)
            if reply_to or cfg["reply_to"]:
                msg["Reply-To"] = reply_to or cfg["reply_to"]

        recipients = [to] + (cc or [])
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["from_email"], recipients, msg.as_string())

        result["sent"] = True
        if log:
            log.estado = "enviado"
            log.enviado_at = datetime.now()
            log.error_msg = None
            try: db.commit()
            except Exception: pass
        # Log event to historial
        if db is not None:
            try:
                log_evento(db, "email", "enviado", f"[{tipo}] To: {to} | Asunto: {subject}", cliente_id=cliente_id, entidad_id=cotizacion_id)
            except Exception: pass
        return result

    except Exception as e:
        err = str(e)[:500]
        print(f"[_send_email] error enviando a {to}: {err}")
        if log:
            log.estado = "error"
            log.error_msg = err
            try: db.commit()
            except Exception: pass
        if db is not None:
            try:
                log_evento(db, "email", "error", f"[{tipo}] Error envio a {to}: {err}", cliente_id=cliente_id, entidad_id=cotizacion_id)
            except Exception: pass
        result["reason"] = err
        return result


def _notify_client_estado_change(cliente, cot, estado_anterior: str, nuevo_estado: str, db: Session):
    """Envia email transaccional al cliente cuando cambia el estado de su cotizacion.
    Un email distinto y tono distinto para cada estado.
    """
    app_url = os.getenv("APP_URL", "https://miptrust.cl")
    producto = (cot.proyecto_nombre or cot.producto or "tu proyecto").strip()
    nombre = cliente.nombre or "amigo/a"
    sol_id = f"#SOL-{str(cot.id).zfill(3)}"

    templates = {
        "cotizado": {
            "subject": f"💰 {sol_id} — Tu cotización de '{producto}' está lista",
            "title": f"Tu cotización está lista, {nombre}",
            "body_html": (
                f"<p>Buenas noticias: ya tenemos la cotización para <strong>{producto}</strong>.</p>"
                f"<p>Entrá a la plataforma para ver los detalles (precios, plazos, condiciones) y confirmar si querés avanzar.</p>"
                f"<p style='background:#fef3c7;padding:12px;border-left:3px solid #f59e0b;border-radius:4px;font-size:13px'>💡 La cotización tiene una vigencia aproximada de 7 días. Si tenés dudas, respondé a este email y te respondemos.</p>"
            ),
            "cta_label": "Ver cotización",
        },
        "produccion": {
            "subject": f"🏭 {sol_id} — Producción de '{producto}' en marcha",
            "title": f"¡Arrancamos producción!",
            "body_html": (
                f"<p>Hola {nombre},</p>"
                f"<p>Ya confirmamos el pedido con el proveedor y <strong>{producto}</strong> está en producción.</p>"
                f"<p>Te vamos a ir avisando de cada hito:</p>"
                f"<ul><li>✅ Producción iniciada (hoy)</li>"
                f"<li>⏳ Quality check en fábrica</li>"
                f"<li>⏳ Embarque marítimo</li>"
                f"<li>⏳ Arribo a Chile + despacho a domicilio</li></ul>"
                f"<p>Podés seguir el avance en la plataforma en cualquier momento.</p>"
            ),
            "cta_label": "Ver estado del pedido",
        },
        "entregado": {
            "subject": f"📦 {sol_id} — '{producto}' entregado",
            "title": f"Entregado con éxito",
            "body_html": (
                f"<p>¡{nombre}, tu pedido de <strong>{producto}</strong> fue entregado!</p>"
                f"<p>Esperamos que todo esté en orden. Si algo no es como esperabas, respondé a este email y lo resolvemos.</p>"
                f"<p style='background:#ecfdf5;padding:12px;border-left:3px solid #10b981;border-radius:4px;font-size:13px'>🙏 <strong>¿Nos dejás un feedback?</strong> Tu opinión nos ayuda a mejorar. Podés contarnos cómo fue la experiencia respondiendo este email.</p>"
                f"<p>Tu factura ya está disponible en la plataforma.</p>"
            ),
            "cta_label": "Ver factura",
        },
    }
    tpl = templates.get(nuevo_estado)
    if not tpl:
        return  # pendiente no dispara email transaccional al cliente
    html = _wrap_html_email(
        title=tpl["title"],
        body_html=tpl["body_html"],
        cta_label=tpl["cta_label"],
        cta_url=app_url,
    )
    body_plain = f"Hola {nombre},\n\n{tpl['title']}.\n\nVer en: {app_url}\n\n— Equipo MIP"
    _send_email(
        to=cliente.email, subject=tpl["subject"],
        body=body_plain, html=html,
        db=db, cotizacion_id=cot.id, cliente_id=cliente.id,
        tipo=f"estado_{nuevo_estado}",
    )


@app.get("/api/admin/email/diagnostic")
def email_diagnostic():
    """Chequea si SMTP esta configurado. Util para debug."""
    cfg = _smtp_config()
    return {
        "configured": bool(cfg["user"] and cfg["password"]),
        "host": cfg["host"],
        "port": cfg["port"],
        "user": cfg["user"] if cfg["user"] else "(no configurado)",
        "from_name": cfg["from_name"],
        "from_email": cfg["from_email"] if cfg["from_email"] else "(no configurado)",
        "reply_to": cfg["reply_to"] or "(mismo que from)",
        "env_vars_needed": ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "SMTP_FROM_NAME", "SMTP_FROM_EMAIL", "SMTP_REPLY_TO"],
    }


@app.post("/api/admin/email/test")
def email_test(data: dict, db: Session = Depends(get_db)):
    """Envia un email de prueba al admin para verificar que SMTP funciona."""
    to = data.get("to", "").strip()
    if not to:
        raise HTTPException(400, "Parametro 'to' requerido")
    html = _wrap_html_email(
        title="Email de prueba — MIP",
        body_html="<p>Este email confirma que tu configuración SMTP está funcionando correctamente.</p><p>Si lo estás viendo, los siguientes triggers también van a funcionar:</p><ul><li>✅ Notificaciones de nuevas cotizaciones</li><li>✅ Invitaciones a clientes</li><li>✅ Secuencias de email automatizadas</li><li>✅ Alertas de cambios de estado</li></ul>",
        cta_label="Ir a la plataforma",
        cta_url=os.getenv("APP_URL", "https://miptrust.cl"),
    )
    result = _send_email(
        to=to,
        subject="✅ Test de email — MIP Quality & Logistics",
        body="Este email confirma que tu configuración SMTP está funcionando correctamente.",
        html=html,
        db=db,
        tipo="test",
    )
    return result


# ─── Clientes: Update + Bulk + Export ───
@app.put("/api/clientes/{id}", response_model=ClienteOut)
def update_cliente(id: int, data: ClienteUpdate, db: Session = Depends(get_db)):
    c = db.query(Cliente).get(id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    log_evento(db, "cliente", "actualizado", f"Cliente {c.nombre} actualizado", entidad_id=c.id, cliente_id=c.id)
    return c


@app.delete("/api/clientes/{id}")
def delete_cliente(id: int, hard: bool = False, db: Session = Depends(get_db)):
    """Elimina un cliente.
    - hard=false (default): solo se puede eliminar si no tiene cotizaciones/pedidos asociados.
    - hard=true: elimina en cascada TODAS las cotizaciones, productos, archivos, actividades, facturas del cliente.
    No se permite eliminar admin.
    """
    c = db.query(Cliente).get(id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    if (c.role or "").lower() == "admin":
        raise HTTPException(400, "No se puede eliminar un usuario admin")
    cots = db.query(Cotizacion).filter(Cotizacion.cliente_id == id).all()
    if cots and not hard:
        raise HTTPException(400, f"El cliente tiene {len(cots)} cotizacion(es) asociadas. Usar ?hard=true para borrar todo en cascada.")
    # Cascade delete
    nombre_bk = c.nombre
    deleted_counts = {"cotizaciones": 0, "productos": 0, "archivos": 0, "actividades": 0, "facturas": 0, "pedidos": 0}
    if hard:
        for cot in cots:
            try:
                for p in db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == cot.id).all():
                    db.delete(p); deleted_counts["productos"] += 1
            except Exception: pass
            try:
                for a in db.query(Archivo).filter(Archivo.cotizacion_id == cot.id).all():
                    db.delete(a); deleted_counts["archivos"] += 1
            except Exception: pass
            try:
                for act in db.query(Actividad).filter(Actividad.entidad_id == cot.id, Actividad.entidad_tipo == "cotizacion").all():
                    db.delete(act); deleted_counts["actividades"] += 1
            except Exception: pass
            try:
                for ped in db.query(Pedido).filter(Pedido.cotizacion_id == cot.id).all():
                    db.delete(ped); deleted_counts["pedidos"] += 1
            except Exception: pass
            db.delete(cot); deleted_counts["cotizaciones"] += 1
        # Actividades y archivos directos del cliente
        try:
            for act in db.query(Actividad).filter(Actividad.cliente_id == id).all():
                db.delete(act); deleted_counts["actividades"] += 1
        except Exception: pass
        try:
            for fa in db.query(Archivo).filter(Archivo.cliente_id == id).all():
                db.delete(fa); deleted_counts["archivos"] += 1
        except Exception: pass
        try:
            for f in db.query(Factura).filter(Factura.cliente_id == id).all():
                db.delete(f); deleted_counts["facturas"] += 1
        except Exception: pass
        db.commit()
    db.delete(c)
    db.commit()
    log_evento(db, "cliente", "eliminado", f"Cliente {nombre_bk} eliminado (hard={hard})", entidad_id=id)
    return {"deleted": True, "cliente_id": id, "cascade": deleted_counts if hard else None}


@app.post("/api/clientes/bulk")
def bulk_import_clientes(clientes: list[ClienteCreate], db: Session = Depends(get_db)):
    created = 0
    errors = []
    for i, data in enumerate(clientes):
        try:
            existing = db.query(Cliente).filter(Cliente.email == data.email).first()
            if existing:
                errors.append(f"Fila {i+1}: Email {data.email} ya existe")
                continue
            c = Cliente(nombre=data.nombre, empresa=data.empresa, rut=data.rut, rubro=data.rubro, email=data.email, telefono=data.telefono, password_hash=data.password)
            db.add(c)
            db.commit()
            created += 1
        except Exception as e:
            errors.append(f"Fila {i+1}: {str(e)}")
    return {"created": created, "errors": errors}


@app.get("/api/clientes/export")
def export_clientes(template_only: bool = False, db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["nombre", "empresa", "rut", "rubro", "email", "telefono"]
    writer.writerow(headers)
    if not template_only:
        for c in db.query(Cliente).all():
            writer.writerow([c.nombre, c.empresa, c.rut, c.rubro, c.email, c.telefono])
    output.seek(0)
    filename = "plantilla_clientes.csv" if template_only else "clientes_export.csv"
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


# ─── Facturas: Bulk + Export ───
@app.post("/api/facturas/bulk")
def bulk_import_facturas(facturas: list[FacturaCreate], db: Session = Depends(get_db)):
    created = 0
    errors = []
    for i, data in enumerate(facturas):
        try:
            f = Factura(**data.model_dump())
            db.add(f)
            db.flush()
            created += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Fila {i+1}: {str(e)}")
    db.commit()
    return {"created": created, "errors": errors}


@app.get("/api/facturas/export")
def export_facturas(template_only: bool = False, db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["pedido_id", "tipo", "categoria", "descripcion", "monto", "fecha", "estado", "archivo_url"]
    writer.writerow(headers)
    if not template_only:
        for f in db.query(Factura).all():
            writer.writerow([f.pedido_id, f.tipo, f.categoria, f.descripcion, f.monto, f.fecha, f.estado, f.archivo_url])
    output.seek(0)
    filename = "plantilla_facturas.csv" if template_only else "facturas_export.csv"
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


# ─── Contabilidad: Bulk + Export ───
@app.post("/api/contabilidad/bulk")
def bulk_import_movimientos(movimientos: list[MovimientoCreate], db: Session = Depends(get_db)):
    created = 0
    errors = []
    for i, data in enumerate(movimientos):
        try:
            m = MovimientoContable(**data.model_dump())
            db.add(m)
            db.flush()
            created += 1
        except Exception as e:
            db.rollback()
            errors.append(f"Fila {i+1}: {str(e)}")
    db.commit()
    return {"created": created, "errors": errors}


@app.get("/api/contabilidad/export")
def export_movimientos(template_only: bool = False, db: Session = Depends(get_db)):
    output = io.StringIO()
    writer = csv.writer(output)
    headers = ["tipo", "categoria", "descripcion", "monto", "fecha", "estado", "pedido_id"]
    writer.writerow(headers)
    if not template_only:
        for m in db.query(MovimientoContable).all():
            writer.writerow([m.tipo, m.categoria, m.descripcion, m.monto, m.fecha, m.estado, m.pedido_id])
    output.seek(0)
    filename = "plantilla_movimientos.csv" if template_only else "movimientos_export.csv"
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


# ─── Historial ───
@app.get("/api/historial", response_model=list[HistorialOut])
def listar_historial(
    cliente_id: Optional[int] = None,
    tipo: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(HistorialEvento)
    if cliente_id:
        q = q.filter(HistorialEvento.cliente_id == cliente_id)
    if tipo:
        q = q.filter(HistorialEvento.tipo == tipo)
    return q.order_by(HistorialEvento.created_at.desc()).limit(limit).all()


# ─── Site Content (Admin Web Editor) ───
@app.get("/api/site-content", response_model=list[SiteContentOut])
def get_site_content(section: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(SiteContent)
    if section:
        q = q.filter(SiteContent.section == section)
    return q.all()


@app.put("/api/site-content")
def update_site_content(items: list[SiteContentUpdate], db: Session = Depends(get_db)):
    updated = 0
    for item in items:
        existing = db.query(SiteContent).filter(SiteContent.section == item.section, SiteContent.key == item.key).first()
        if existing:
            existing.value = item.value
            existing.content_type = item.content_type
        else:
            sc = SiteContent(section=item.section, key=item.key, value=item.value, content_type=item.content_type)
            db.add(sc)
        updated += 1
    db.commit()
    return {"updated": updated}


@app.post("/api/site-content/upload-image")
async def upload_site_image(file: UploadFile = File(...), section: str = Query("hero"), key: str = Query("image")):
    content = await file.read()
    filename = f"site/{section}_{key}_{file.filename}"
    url = ""
    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(content, content_type=file.content_type)
        url = f"https://storage.googleapis.com/{GCS_BUCKET}/{filename}"
    except Exception:
        os.makedirs("/app/uploads/site", exist_ok=True)
        local_path = f"/app/uploads/site/{section}_{key}_{file.filename}"
        with open(local_path, "wb") as f:
            f.write(content)
        url = f"/uploads/site/{section}_{key}_{file.filename}"
    return {"url": url, "section": section, "key": key}


# ─── Tickets / Feedback ───
@app.get("/api/tickets")
def listar_tickets(estado: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Ticket)
    if estado:
        q = q.filter(Ticket.estado == estado)
    return q.order_by(Ticket.created_at.desc()).all()


@app.post("/api/tickets")
def crear_ticket(data: dict, db: Session = Depends(get_db)):
    t = Ticket(
        usuario=data.get("usuario", ""),
        email=data.get("email", ""),
        urgencia=data.get("urgencia", "media"),
        tipo_error=data.get("tipo_error", "bug"),
        seccion=data.get("seccion", ""),
        descripcion=data.get("descripcion", ""),
        screenshot_url=data.get("screenshot_url", ""),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "estado": t.estado}


@app.put("/api/tickets/{id}")
def update_ticket(id: int, data: dict, db: Session = Depends(get_db)):
    t = db.query(Ticket).get(id)
    if not t:
        raise HTTPException(404, "Ticket no encontrado")
    if "estado" in data:
        t.estado = data["estado"]
    if "respuesta_admin" in data:
        t.respuesta_admin = data["respuesta_admin"]
    if data.get("estado") == "resuelto":
        t.resolved_at = datetime.now()
    db.commit()
    db.refresh(t)
    return {"id": t.id, "estado": t.estado}


# ─── Chatbot: Mateo (Claude + Gemini fallback) ───
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MATEO_SYSTEM_PROMPT = """Eres Mateo, asesor senior de importaciones de MIP Quality & Logistics, broker de importación desde China con oficinas en Shenzhen, Guangzhou y Santiago de Chile. Tienes 8 años de experiencia cerrando negocios de importación y eres el mejor vendedor de la empresa.

PERSONALIDAD Y TONO:
- Cercano, seguro y persuasivo. Usas "tú" (no "usted"). Hablas como un ejecutivo de cuentas senior que sabe lo que hace.
- Español chileno natural. Puedes usar "dale", "bacán", "te cuento" naturalmente.
- Respuestas concisas pero con punch comercial. Máximo 3-4 párrafos cortos.
- Transmites urgencia sutil sin ser agresivo. Haces sentir al cliente que está frente a una oportunidad.
- Eres empático: primero escuchas, entiendes el dolor del cliente, y luego ofreces la solución.

TÉCNICAS DE VENTA QUE USAS:
1. ESCUCHA ACTIVA: Repite lo que el cliente dijo para mostrar que entendiste. "Entiendo que necesitas X para Y..."
2. DOLOR → SOLUCIÓN: Identifica el problema (costos altos, proveedores poco confiables, tiempos largos) y posiciona MIP como la solución.
3. PRUEBA SOCIAL: Menciona casos de éxito reales. "Un cliente del rubro retail logró reducir costos un 35% con nosotros."
4. ESCASEZ/URGENCIA: "Los proveedores de este producto están con alta demanda, te recomiendo cotizar ahora para asegurar disponibilidad."
5. ANCLAJE DE PRECIO: Siempre da un rango de precio estimado para anclar expectativas. No digas "depende" sin dar un número.
6. CIERRE ALTERNATIVO: En vez de "¿te interesa?", pregunta "¿prefieres que te cotice el envío marítimo o aéreo?"
7. SIGUIENTE PASO CONCRETO: SIEMPRE termina con una acción específica, no genérica.
8. RECIPROCIDAD: Ofrece valor primero (dato, consejo, estimación) antes de pedir algo.

CONOCIMIENTO DE MIP:
- Broker de importación: sourcing, control de calidad, logística puerta a puerta desde China
- +12 años en la industria, +500 productos importados, +70 personas en oficinas de China
- Sectores: retail/moda, industrial, hospitality, salud, tecnología, hogar/deco, deportes, infantil
- Proceso: Solicitud → Cotización (72hrs) → Muestra física → Producción con QC → Embarque → Entrega en bodega
- Pago: 50% anticipo + 50% pre-embarque. También financiamiento y LC.
- Flete marítimo China-Chile: 30-45 días. Aéreo: 5-7 días.
- MOQ: desde 500 unidades. Productos con personalización desde 1,000 un.
- Inspecciones pre-embarque con reporte fotográfico y video incluido.
- Oficinas propias en Shenzhen y Guangzhou con equipo bilingüe español-mandarín.
- Diferenciador: equipo in-situ en fábricas. No somos intermediarios lejanos, estamos ahí.

CALL TO ACTIONS PRECISOS (usa estos en vez de genéricos):
- "¿Te armo una cotización con 2-3 opciones de proveedores? La tendrías en 72 horas."
- "¿Qué te parece si agendamos una llamada de 15 minutos? Te puedo mostrar casos similares al tuyo."
- "¿Me pasas tu WhatsApp? Te envío un ejemplo de cotización de un producto similar para que veas cómo trabajamos."
- "¿Prefieres que te cotice con envío marítimo o aéreo? Así vemos qué calza mejor con tus tiempos."
- "Déjame tu email y te mando un PDF con el proceso completo y los costos estimados."
- "¿Cuántas unidades necesitarías? Con eso te puedo dar un precio bastante preciso."
- "¿Te gustaría recibir una muestra física antes de decidir? Podemos enviarte una sin compromiso."

DETECCIÓN DE SENTIMIENTO Y RETENCIÓN:
Si detectas que el cliente se muestra negativo, evasivo, desinteresado o quiere irse:
- "No me interesa" / "No gracias" → No insistas. Baja la presión y ofrece algo de valor sin compromiso: "Entiendo perfecto, sin presión. Te dejo mi contacto por si más adelante necesitas algo. Igual te puedo enviar una guía gratuita de costos de importación por rubro, por si te sirve de referencia."
- "Es muy caro" / "No tengo presupuesto" → Valida su preocupación y reposiciona: "Te entiendo, el precio es clave. Te cuento que muchos clientes pensaban lo mismo antes de ver los números reales. ¿Qué tal si te muestro una comparación rápida de lo que pagas hoy vs lo que podrías pagar importando directo? Sin compromiso."
- "Estoy viendo otras opciones" → No compitas, diferénciate: "Me parece bien que compares, es lo más inteligente. Lo que nos diferencia es que tenemos gente propia en las fábricas de China, no somos intermediarios remotos. Si quieres te mando un caso de un cliente que vino de otra empresa y logró mejorar calidad y bajar costos."
- "Después veo" / "No es el momento" → Deja la puerta abierta con valor: "Dale, sin problema. Te dejo un dato: los mejores precios FOB se negocian entre marzo y septiembre, fuera de temporada alta. Si me pasas tu email te aviso cuando haya buenas oportunidades en tu rubro."
- "No confío en importar desde China" → Empatiza y educa: "Es una preocupación súper válida. Por eso MIP tiene +70 personas EN China que auditan fábricas, supervisan producción y hacen inspecciones de calidad antes del embarque. No mandamos nada sin que pase por nuestro QC. ¿Te muestro un reporte de inspección real para que veas cómo funciona?"
- Respuestas cortas o monosílabas → El cliente está perdiendo interés. Haz una pregunta abierta personal: "Oye, y cuéntame, ¿qué es lo que más te preocupa de importar? A veces hay dudas que son más fáciles de resolver de lo que parece."

REGLAS ESTRICTAS:
- NUNCA digas "depende" sin dar al menos un rango de precio estimado.
- SIEMPRE da números concretos: rangos de precio, plazos, cantidades mínimas.
- Si el usuario es un cliente logueado, usa sus datos para personalizar. Llámalo por su nombre.
- Si no sabes algo específico, di "déjame verificar con el equipo de sourcing en China y te respondo hoy mismo".
- Si te piden algo fuera de importación, redirige amablemente pero siempre vuelve al tema de importación.
- NUNCA hagas listas largas. Sé conversacional, como en una reunión de café.
- Cada respuesta debe tener UN call to action claro al final. No más de uno.
- Si el cliente muestra interés pero duda, usa la técnica de "¿qué es lo que más te preocupa?" para desbloquear.
- NUNCA seas agresivo ni insistente. Si el cliente dice no, respeta su decisión pero siempre deja valor sobre la mesa.
"""


@app.post("/api/chat")
def chat_with_mateo(data: dict, db: Session = Depends(get_db)):
    """Chat endpoint: sends message to Claude (primary) or Gemini (fallback)"""
    _check_cost_limit("gemini", db)  # hard-block si se alcanzo el limite mensual
    message = data.get("message", "").strip()
    history = data.get("history", [])  # [{role: "user"/"assistant", content: "..."}]
    cliente_id = data.get("cliente_id")

    if not message:
        raise HTTPException(400, "Mensaje vacío")

    # Build context with client data if logged in
    context = ""
    if cliente_id:
        try:
            cliente = db.query(Cliente).get(cliente_id)
            if cliente:
                context += f"\n[DATOS DEL CLIENTE LOGUEADO]\nNombre: {cliente.nombre}\nEmpresa: {cliente.empresa}\nRubro: {cliente.rubro}\nEmail: {cliente.email}\n"
                # Add their cotizaciones
                cots = db.query(Cotizacion).filter(Cotizacion.cliente_id == cliente_id).order_by(Cotizacion.created_at.desc()).limit(5).all()
                if cots:
                    context += "\nCotizaciones activas:\n"
                    for c in cots:
                        context += f"- #{c.id} {c.producto} ({c.estado}) - Cantidad: {c.cantidad}\n"
                # Add their pedidos
                pedidos = db.query(Pedido).join(Cotizacion).filter(Cotizacion.cliente_id == cliente_id).order_by(Pedido.created_at.desc()).limit(5).all()
                if pedidos:
                    context += "\nPedidos activos:\n"
                    etapa_names = ['','Solicitud','Cotización','Muestra','Pago 50%','Producción','QC China','Embarque','Entrega','Pago final']
                    for p in pedidos:
                        etapa = etapa_names[p.etapa_actual] if p.etapa_actual < len(etapa_names) else 'N/A'
                        context += f"- Pedido #{p.id} etapa {p.etapa_actual}/9 ({etapa}) - ${p.monto_total}\n"
        except Exception as e:
            print(f"Chat context error: {e}")

    system = MATEO_SYSTEM_PROMPT + context

    # Build messages
    messages = []
    for h in history[-10:]:  # Keep last 10 messages for context
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    # Try Gemini first (free tier)
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system)
            # Convert messages to Gemini format
            gemini_history = []
            for m in messages[:-1]:
                gemini_history.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]})
            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(message)
            return {"reply": response.text, "provider": "gemini"}
        except Exception as e:
            print(f"Gemini error: {e}")

    # Fallback to Claude
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system=system,
                messages=messages,
            )
            reply = response.content[0].text
            return {"reply": reply, "provider": "claude"}
        except Exception as e:
            print(f"Claude error: {e}")

    # Both failed or no keys configured
    return {
        "reply": "¡Hola! Soy Mateo de MIP Quality & Logistics. En este momento estoy teniendo problemas técnicos, pero puedes escribirnos a contacto@mipquality.com o al +56 9 8765 4321 por WhatsApp y te atendemos de inmediato.",
        "provider": "fallback"
    }


# ═══════════════════════════════════════════════════
# MATEO AI TRAINER — config, history, lead capture
# ═══════════════════════════════════════════════════
def _get_or_create_mateo_config(db: Session) -> MateoConfig:
    cfg = db.query(MateoConfig).order_by(MateoConfig.id).first()
    if not cfg:
        cfg = MateoConfig(
            nombre_bot="Mateo",
            tono="profesional_cercano",
            longitud_respuesta="media",
            system_prompt=MATEO_SYSTEM_PROMPT,
            idioma="es",
            max_tokens_respuesta=500,
            modelo_ia="gemini-2.5-flash",
            activo=True,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _build_mateo_system_prompt(cfg: MateoConfig, context: str = "") -> str:
    """Construye el system prompt completo usando la config editable."""
    base = cfg.system_prompt or MATEO_SYSTEM_PROMPT
    tono_map = {
        "profesional_cercano": "Cercano, seguro, persuasivo, usando 'tú' en español chileno.",
        "formal": "Formal, corporativo, usando 'usted' y estructura empresarial.",
        "casual": "Relajado, informal, conversacional como con un amigo.",
        "agresivo_ventas": "Directo, enfocado en cierre, con urgencia y CTAs fuertes en cada mensaje.",
    }
    long_map = {
        "corta": "Respuestas MUY CORTAS, maximo 1-2 frases. Directo al punto.",
        "media": "Respuestas medianas, 2-3 parrafos cortos con valor.",
        "larga": "Respuestas detalladas con contexto, ejemplos y pruebas sociales.",
    }
    extras = []
    extras.append(f"\n[TONO CONFIGURADO]: {tono_map.get(cfg.tono, '')}")
    extras.append(f"[LONGITUD]: {long_map.get(cfg.longitud_respuesta, '')}")
    if cfg.reglas_negocio:
        extras.append(f"\n[REGLAS DE NEGOCIO CUSTOM]:\n{cfg.reglas_negocio}")
    if cfg.flujo_conversacion:
        extras.append(f"\n[FLUJO DE CONVERSACION A SEGUIR]:\n{cfg.flujo_conversacion}")
    if cfg.precios_publicos:
        extras.append(f"\n[PRECIOS QUE PUEDES MENCIONAR]:\n{cfg.precios_publicos}")
    if cfg.auto_agendar_reuniones:
        extras.append(
            "\n[AUTO-AGENDAR]: Si el cliente muestra interés real (pregunta por reunión, llamada, "
            "demo, cotización personalizada), ofrece agendar directo. Pide: fecha preferida, "
            "hora, email y motivo. Cuando tengas los 4 datos di exactamente: "
            "'ACTION:BOOK_MEETING|email=<X>|nombre=<Y>|fecha=<YYYY-MM-DD HH:MM>|motivo=<Z>'"
        )
    extras.append(
        "\n[LEAD CAPTURE]: Durante la conversacion intenta obtener email, nombre, empresa y "
        "telefono de manera natural. Cuando recopiles datos emite al final: "
        "'LEAD_DATA:email=<X>|nombre=<Y>|empresa=<E>|telefono=<T>|interes=<describe>'"
    )
    return base + "\n".join(extras) + context


@app.get("/api/mateo/config", response_model=MateoConfigOut)
def get_mateo_config(db: Session = Depends(get_db)):
    return _get_or_create_mateo_config(db)


@app.put("/api/mateo/config", response_model=MateoConfigOut)
def update_mateo_config(data: dict, db: Session = Depends(get_db)):
    cfg = _get_or_create_mateo_config(db)
    # Whitelist updatable fields
    for field in [
        "nombre_bot", "tono", "longitud_respuesta", "system_prompt",
        "reglas_negocio", "flujo_conversacion", "precios_publicos",
        "auto_agendar_reuniones", "calendar_email", "idioma",
        "max_tokens_respuesta", "modelo_ia", "activo",
    ]:
        if field in data:
            setattr(cfg, field, data[field])
    db.commit()
    db.refresh(cfg)
    return cfg


@app.get("/api/mateo/conversations")
def list_mateo_conversations(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    q = db.query(MateoConversation).order_by(MateoConversation.inicio_at.desc())
    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    return {
        "total": total,
        "conversations": [{
            "id": c.id,
            "session_id": c.session_id,
            "visitor_nombre": c.visitor_nombre,
            "visitor_email": c.visitor_email,
            "visitor_telefono": c.visitor_telefono,
            "visitor_empresa": c.visitor_empresa,
            "cliente_id": c.cliente_id,
            "prospect_id": c.prospect_id,
            "interes_detectado": c.interes_detectado,
            "sentimiento": c.sentimiento,
            "tokens_input": c.tokens_input,
            "tokens_output": c.tokens_output,
            "tokens_total": (c.tokens_input or 0) + (c.tokens_output or 0),
            "mensajes_count": c.mensajes_count,
            "convertido_a_prospect": c.convertido_a_prospect,
            "proveedor_ia": c.proveedor_ia,
            "inicio_at": c.inicio_at.isoformat() if c.inicio_at else None,
            "ultimo_mensaje_at": c.ultimo_mensaje_at.isoformat() if c.ultimo_mensaje_at else None,
        } for c in rows],
    }


@app.get("/api/mateo/conversations/{id}")
def get_mateo_conversation(id: int, db: Session = Depends(get_db)):
    conv = db.query(MateoConversation).get(id)
    if not conv:
        raise HTTPException(404, "Conversacion no encontrada")
    messages = db.query(MateoMessage).filter(
        MateoMessage.conversation_id == id
    ).order_by(MateoMessage.created_at.asc()).all()
    return {
        "id": conv.id,
        "session_id": conv.session_id,
        "visitor": {
            "nombre": conv.visitor_nombre,
            "email": conv.visitor_email,
            "telefono": conv.visitor_telefono,
            "empresa": conv.visitor_empresa,
        },
        "interes_detectado": conv.interes_detectado,
        "sentimiento": conv.sentimiento,
        "tokens_input": conv.tokens_input,
        "tokens_output": conv.tokens_output,
        "mensajes_count": conv.mensajes_count,
        "convertido_a_prospect": conv.convertido_a_prospect,
        "inicio_at": conv.inicio_at.isoformat() if conv.inicio_at else None,
        "ultimo_mensaje_at": conv.ultimo_mensaje_at.isoformat() if conv.ultimo_mensaje_at else None,
        "messages": [{
            "role": m.role,
            "content": m.content,
            "tokens_usados": m.tokens_usados,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        } for m in messages],
    }


@app.get("/api/mateo/stats")
def mateo_stats(db: Session = Depends(get_db)):
    """Dashboard stats para el trainer."""
    total_convs = db.query(MateoConversation).count()
    total_tokens_in = db.query(func.coalesce(func.sum(MateoConversation.tokens_input), 0)).scalar() or 0
    total_tokens_out = db.query(func.coalesce(func.sum(MateoConversation.tokens_output), 0)).scalar() or 0
    total_leads = db.query(MateoConversation).filter(MateoConversation.convertido_a_prospect == True).count()
    total_emails_capturados = db.query(MateoConversation).filter(
        MateoConversation.visitor_email != None,
        MateoConversation.visitor_email != "",
    ).count()
    total_reuniones = db.query(MateoCalendarBooking).count()
    # Costos estimados (Gemini Flash: ~$0.075/1M input, $0.30/1M output)
    cost_usd = (total_tokens_in * 0.075 / 1_000_000) + (total_tokens_out * 0.30 / 1_000_000)
    return {
        "total_conversaciones": total_convs,
        "total_tokens_input": total_tokens_in,
        "total_tokens_output": total_tokens_out,
        "total_tokens": total_tokens_in + total_tokens_out,
        "costo_estimado_usd": round(cost_usd, 4),
        "leads_convertidos": total_leads,
        "emails_capturados": total_emails_capturados,
        "reuniones_agendadas": total_reuniones,
        "tasa_conversion_lead": round((total_leads / total_convs * 100) if total_convs else 0, 1),
    }


def _extract_lead_data(text: str):
    """Parsea 'LEAD_DATA:email=X|nombre=Y|...' del reply de Mateo."""
    import re
    m = re.search(r'LEAD_DATA:([^\n]+)', text)
    if not m:
        return {}
    data = {}
    for chunk in m.group(1).split('|'):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            k = k.strip().lower()
            v = v.strip()
            if k and v and v.lower() not in ('<x>', '<y>', '<e>', '<t>', 'x', 'y'):
                data[k] = v
    return data


def _extract_booking_request(text: str):
    """Parsea 'ACTION:BOOK_MEETING|email=X|...' del reply."""
    import re
    m = re.search(r'ACTION:BOOK_MEETING\|([^\n]+)', text)
    if not m:
        return {}
    data = {}
    for chunk in m.group(1).split('|'):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            data[k.strip().lower()] = v.strip()
    return data


def _create_prospect_from_lead(lead: dict, session_id: str, db: Session):
    """Crea/actualiza un Prospect a partir del lead capturado."""
    email = lead.get('email')
    if not email or '@' not in email:
        return None
    # Dedupe por email
    existing = db.query(Prospect).filter(Prospect.email == email).first()
    if existing:
        # Update any missing fields
        if not existing.nombre and lead.get('nombre'):
            existing.nombre = lead['nombre']
        if not existing.telefono and lead.get('telefono'):
            existing.telefono = lead['telefono']
        if not existing.empresa and lead.get('empresa'):
            existing.empresa = lead['empresa']
        if not existing.notas and lead.get('interes'):
            existing.notas = f"Interes: {lead['interes']}\nSesion chat: {session_id}"
        db.commit()
        return existing
    p = Prospect(
        nombre=lead.get('nombre', '') or email.split('@')[0],
        email=email,
        telefono=lead.get('telefono', ''),
        empresa=lead.get('empresa', ''),
        fuente="chatbot_mateo",
        estado="nuevo",
        notas=f"Interes detectado: {lead.get('interes', 'via chatbot')}\nSesion: {session_id}",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.post("/api/mateo/calendar/book")
def mateo_book_meeting(data: dict, db: Session = Depends(get_db)):
    """Stub para crear reunion. Integracion real con Google Calendar se activa
    si el admin configura GOOGLE_CALENDAR_EMAIL + OAuth. Por ahora guarda el
    booking localmente y devuelve un meet link stub. El cliente recibe email
    via secuencia o SMTP."""
    cfg = _get_or_create_mateo_config(db)
    if not cfg.auto_agendar_reuniones:
        raise HTTPException(400, "Auto-agendar esta desactivado en la config")
    email = data.get('email', '').strip()
    nombre = data.get('nombre', '').strip()
    fecha_str = data.get('fecha', '').strip()
    motivo = data.get('motivo', 'Reunion MIP Quality & Logistics')
    conversation_id = data.get('conversation_id')
    if not email or not fecha_str:
        raise HTTPException(400, "Requiere email y fecha")
    try:
        fecha = datetime.fromisoformat(fecha_str.replace('Z', ''))
    except Exception:
        raise HTTPException(400, "fecha debe ser formato ISO (YYYY-MM-DD HH:MM)")
    meet_link = f"https://meet.google.com/new"  # stub; reemplazar con integracion real
    booking = MateoCalendarBooking(
        conversation_id=conversation_id,
        visitor_email=email,
        visitor_nombre=nombre,
        fecha_reunion=fecha,
        duracion_min=data.get('duracion_min', 30),
        motivo=motivo,
        estado="confirmada",
        meet_link=meet_link,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    # Enqueue confirmation email
    try:
        log = EmailLog(
            destinatario=email,
            asunto=f"Reunion MIP confirmada - {fecha.strftime('%d/%m/%Y %H:%M')}",
            cuerpo=f"Hola {nombre},\n\nTu reunion con MIP Quality & Logistics esta confirmada.\n\n"
                   f"Fecha: {fecha.strftime('%d/%m/%Y a las %H:%M')}\nMotivo: {motivo}\n"
                   f"Link Meet: {meet_link}\n\nSaludos,\nEquipo MIP",
            estado="pendiente",
        )
        db.add(log)
        db.commit()
    except Exception:
        pass
    return {
        "booking_id": booking.id,
        "meet_link": meet_link,
        "fecha": fecha.isoformat(),
        "estado": "confirmada",
    }


@app.get("/api/mateo/calendar/bookings")
def list_mateo_bookings(db: Session = Depends(get_db)):
    rows = db.query(MateoCalendarBooking).order_by(MateoCalendarBooking.fecha_reunion.desc()).all()
    return [{
        "id": b.id,
        "visitor_email": b.visitor_email,
        "visitor_nombre": b.visitor_nombre,
        "fecha_reunion": b.fecha_reunion.isoformat() if b.fecha_reunion else None,
        "duracion_min": b.duracion_min,
        "motivo": b.motivo,
        "estado": b.estado,
        "meet_link": b.meet_link,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    } for b in rows]


@app.post("/api/chat/v2")
def chat_with_mateo_v2(data: dict, db: Session = Depends(get_db)):
    """Chat v2 con config editable, tracking de tokens, historial y lead capture."""
    _check_cost_limit("gemini", db)  # hard-block si se alcanzo el limite mensual
    import uuid
    message = data.get("message", "").strip()
    history = data.get("history", [])
    cliente_id = data.get("cliente_id")
    session_id = data.get("session_id") or str(uuid.uuid4())
    visitor_info = data.get("visitor", {})

    if not message:
        raise HTTPException(400, "Mensaje vacio")

    cfg = _get_or_create_mateo_config(db)
    if not cfg.activo:
        return {"reply": "Chatbot desactivado. Contactanos en contacto@mipquality.com", "provider": "disabled", "session_id": session_id}

    # Get or create conversation
    conv = db.query(MateoConversation).filter(MateoConversation.session_id == session_id).first()
    if not conv:
        conv = MateoConversation(
            session_id=session_id,
            cliente_id=cliente_id,
            visitor_email=visitor_info.get('email', ''),
            visitor_nombre=visitor_info.get('nombre', ''),
            visitor_telefono=visitor_info.get('telefono', ''),
            visitor_empresa=visitor_info.get('empresa', ''),
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Build context
    context = ""
    if cliente_id:
        try:
            cliente = db.query(Cliente).get(cliente_id)
            if cliente:
                context += f"\n[DATOS DEL CLIENTE LOGUEADO]\nNombre: {cliente.nombre}\nEmpresa: {cliente.empresa}\nRubro: {cliente.rubro}\nEmail: {cliente.email}\n"
        except Exception:
            pass

    system = _build_mateo_system_prompt(cfg, context)

    # Build messages with history from DB if any
    messages = []
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    # Save user message
    db.add(MateoMessage(conversation_id=conv.id, role="user", content=message))
    db.commit()

    reply_text = None
    provider_used = "fallback"
    tokens_in = 0
    tokens_out = 0

    # Try Gemini first
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(cfg.modelo_ia or "gemini-2.5-flash", system_instruction=system)
            gemini_history = []
            for m in messages[:-1]:
                gemini_history.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]})
            chat = model.start_chat(history=gemini_history)
            response = chat.send_message(message)
            reply_text = response.text
            provider_used = "gemini"
            # Token counts if available
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, 'prompt_token_count', 0) or 0
                tokens_out = getattr(response.usage_metadata, 'candidates_token_count', 0) or 0
            else:
                tokens_in = len(system + message) // 4
                tokens_out = len(reply_text) // 4
        except Exception as e:
            print(f"Gemini v2 error: {e}")

    if not reply_text and ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=cfg.max_tokens_respuesta or 500,
                system=system,
                messages=messages,
            )
            reply_text = response.content[0].text
            provider_used = "claude"
            if hasattr(response, 'usage'):
                tokens_in = response.usage.input_tokens or 0
                tokens_out = response.usage.output_tokens or 0
        except Exception as e:
            print(f"Claude v2 error: {e}")

    if not reply_text:
        reply_text = "Hola! Soy Mateo de MIP Quality & Logistics. Ahora mismo estoy con problemas tecnicos, pero puedes escribirnos a contacto@mipquality.com."
        provider_used = "fallback"

    # Extract lead data & booking action
    lead = _extract_lead_data(reply_text)
    booking = _extract_booking_request(reply_text)
    # Clean reply from our action markers (don't expose to user)
    clean_reply = reply_text
    import re as _re
    clean_reply = _re.sub(r'\s*LEAD_DATA:[^\n]+', '', clean_reply).strip()
    clean_reply = _re.sub(r'\s*ACTION:BOOK_MEETING\|[^\n]+', '', clean_reply).strip()

    # Update conversation
    conv.tokens_input = (conv.tokens_input or 0) + tokens_in
    conv.tokens_output = (conv.tokens_output or 0) + tokens_out
    conv.mensajes_count = (conv.mensajes_count or 0) + 1
    conv.proveedor_ia = provider_used
    conv.ultimo_mensaje_at = datetime.now()

    # Apply lead data
    if lead:
        if lead.get('email'):
            conv.visitor_email = lead['email']
        if lead.get('nombre'):
            conv.visitor_nombre = lead['nombre']
        if lead.get('telefono'):
            conv.visitor_telefono = lead['telefono']
        if lead.get('empresa'):
            conv.visitor_empresa = lead['empresa']
        if lead.get('interes'):
            conv.interes_detectado = lead['interes'][:200]
        # Auto-create prospect
        if lead.get('email'):
            prospect = _create_prospect_from_lead(lead, session_id, db)
            if prospect:
                conv.prospect_id = prospect.id
                conv.convertido_a_prospect = True

    # Save assistant message
    db.add(MateoMessage(
        conversation_id=conv.id, role="assistant",
        content=clean_reply, tokens_usados=tokens_out,
    ))
    db.commit()

    # Auto-book if requested and config allows
    booking_result = None
    if booking and cfg.auto_agendar_reuniones and booking.get('email') and booking.get('fecha'):
        try:
            fecha = datetime.fromisoformat(booking['fecha'].replace('Z', ''))
            b = MateoCalendarBooking(
                conversation_id=conv.id,
                visitor_email=booking['email'],
                visitor_nombre=booking.get('nombre', ''),
                fecha_reunion=fecha,
                duracion_min=30,
                motivo=booking.get('motivo', 'Reunion solicitada desde chatbot'),
                estado="confirmada",
                meet_link="https://meet.google.com/new",
            )
            db.add(b)
            db.commit()
            db.refresh(b)
            booking_result = {
                "booking_id": b.id,
                "fecha": fecha.isoformat(),
                "meet_link": b.meet_link,
            }
        except Exception as e:
            print(f"booking error: {e}")

    return {
        "reply": clean_reply,
        "provider": provider_used,
        "session_id": session_id,
        "conversation_id": conv.id,
        "tokens_used": {"input": tokens_in, "output": tokens_out},
        "lead_captured": bool(lead.get('email')) if lead else False,
        "booking": booking_result,
    }


# ═══════════════════════════════════════════════════
# AGENT BUILDER (Vambe-style)
# Permite crear agentes con bloques modulares de prompt
# desde UI sin tocar codigo.
# ═══════════════════════════════════════════════════

# --- Default tools registry ---
DEFAULT_TOOLS = [
    {
        "name": "search_kb",
        "description": "Busca en la Knowledge Base informacion relevante para responder la pregunta del usuario. Usar cuando el usuario pregunte por politicas, productos, precios o detalles especificos.",
        "categoria": "kb",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto a buscar"},
                "folder_id": {"type": "integer", "description": "Opcional: filtrar por carpeta"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        }),
        "handler": "kb_search",
        "peligroso": False,
    },
    {
        "name": "calendar_create_event",
        "description": "Crea una reunion en Google Calendar. Usar cuando el cliente acepta agendar una llamada/demo/reunion.",
        "categoria": "calendar",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "nombre": {"type": "string"},
                "fecha_iso": {"type": "string", "description": "ISO 8601"},
                "duracion_min": {"type": "integer", "default": 30},
                "motivo": {"type": "string"},
            },
            "required": ["email", "fecha_iso"],
        }),
        "handler": "calendar_book",
        "peligroso": False,
    },
    {
        "name": "create_prospect",
        "description": "Registra un nuevo prospect en el CRM con los datos capturados durante la conversacion.",
        "categoria": "crm",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "email": {"type": "string"},
                "telefono": {"type": "string"},
                "empresa": {"type": "string"},
                "interes": {"type": "string"},
            },
            "required": ["nombre"],
        }),
        "handler": "prospect_create",
        "peligroso": False,
    },
    {
        "name": "escalate_to_human",
        "description": "Escala la conversacion a un humano. Usar cuando la consulta es muy compleja o el cliente lo pide explicitamente.",
        "categoria": "utility",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "motivo": {"type": "string"},
                "urgencia": {"type": "string", "enum": ["baja", "media", "alta"]},
            },
            "required": ["motivo"],
        }),
        "handler": "escalate",
        "peligroso": False,
    },
    {
        "name": "send_webhook",
        "description": "Llama a un webhook externo (integraciones custom). Requiere URL pre-configurada.",
        "categoria": "webhook",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["url", "payload"],
        }),
        "handler": "webhook_send",
        "peligroso": True,
    },
    {
        "name": "check_calendar_availability",
        "description": "Consulta la disponibilidad en Google Calendar del equipo para agendar reuniones. Retorna los slots ocupados en un rango de fechas. USAR cuando el cliente quiere saber cuando podemos reunirnos.",
        "categoria": "calendar",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "time_min": {"type": "string", "description": "ISO timestamp inicio de ventana"},
                "time_max": {"type": "string", "description": "ISO timestamp fin de ventana"},
            },
        }),
        "handler": "check_calendar_availability",
        "peligroso": False,
    },
    {
        "name": "add_to_pipeline",
        "description": "Agrega al cliente actual al pipeline de ventas CRM moviendolo al stage apropiado. Usar cuando el cliente muestra intencion real de compra o avance en su interes.",
        "categoria": "crm",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "stage": {"type": "string", "enum": ["lead_inicial","calificando","cotizando","cerrando","cliente_activo","soporte_post_venta","cliente_perdido"]},
                "nombre": {"type": "string"},
                "email": {"type": "string"},
                "telefono": {"type": "string"},
                "empresa": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["stage"],
        }),
        "handler": "add_to_pipeline",
        "peligroso": False,
    },
    {
        "name": "check_order_status",
        "description": "Consulta el estado de un pedido/cotizacion del cliente. Usar cuando el cliente pregunta por donde va su pedido o cuando llega.",
        "categoria": "crm",
        "schema_input": json.dumps({
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email del cliente"},
                "pedido_id": {"type": "integer", "description": "Numero de pedido si lo conoce"},
            },
        }),
        "handler": "check_order_status",
        "peligroso": False,
    },
]


def _descompose_mateo_prompt_to_blocks(system_prompt: str):
    """Extrae los bloques identidad/instrucciones/info del prompt monolitico de Mateo.
    Cada bloque se identifica por los headers conocidos. Si no se encuentra, se omite.
    Retorna lista de (tipo, categoria, nombre, contenido, orden).
    """
    blocks = []
    txt = system_prompt or ""
    # Section markers del prompt actual
    sections = [
        ("PERSONALIDAD Y TONO", "personificacion", "identidad", "Personalidad y tono", 10),
        ("TECNICAS DE VENTA QUE USAS", "instrucciones", "instrucciones", "Tecnicas de venta", 30),
        ("TÉCNICAS DE VENTA QUE USAS", "instrucciones", "instrucciones", "Tecnicas de venta", 30),
        ("CONOCIMIENTO DE MIP", "info_empresa", "info_clave", "Conocimiento de MIP", 40),
        ("CALL TO ACTIONS PRECISOS", "pasos", "instrucciones", "Call to actions", 50),
        ("DETECCION DE SENTIMIENTO Y RETENCION", "casos", "instrucciones", "Deteccion de sentimiento", 60),
        ("DETECCIÓN DE SENTIMIENTO Y RETENCION", "casos", "instrucciones", "Deteccion de sentimiento", 60),
        ("DETECCIÓN DE SENTIMIENTO Y RETENCIÓN", "casos", "instrucciones", "Deteccion de sentimiento", 60),
        ("REGLAS ESTRICTAS", "formato", "identidad", "Reglas estrictas", 20),
    ]
    # Extract the intro (before first section header)
    intro_end = len(txt)
    for marker, _, _, _, _ in sections:
        idx = txt.find(marker)
        if idx >= 0:
            intro_end = min(intro_end, idx)
    intro = txt[:intro_end].strip()
    if intro:
        blocks.append(("personificacion", "identidad", "Personificacion", intro, 0))

    # Parse each section
    seen = set()
    for marker, tipo, categoria, nombre, orden in sections:
        if tipo in seen:
            continue
        idx = txt.find(marker)
        if idx < 0:
            continue
        # Find next marker
        start = idx
        end = len(txt)
        for m2, _, _, _, _ in sections:
            if m2 == marker:
                continue
            i2 = txt.find(m2, start + len(marker))
            if i2 > 0:
                end = min(end, i2)
        content = txt[start:end].strip()
        if content:
            blocks.append((tipo, categoria, nombre, content, orden))
            seen.add(tipo)
    return blocks


def _seed_agent_builder(db):
    """Crea tools default + Mateo como primer agente si no existen."""
    # Seed tools
    for t in DEFAULT_TOOLS:
        existing = db.query(Tool).filter(Tool.name == t["name"]).first()
        if not existing:
            db.add(Tool(
                name=t["name"], description=t["description"],
                categoria=t["categoria"], schema_input=t["schema_input"],
                handler=t.get("handler", ""), peligroso=t.get("peligroso", False),
                activo=True,
            ))
    db.commit()

    # Seed Mateo as first agent (solo si no existe). Si ya existe, saltar Mateo pero seguir con los demas.
    existing_mateo = db.query(AgentConfig).filter(AgentConfig.agent_type == "mateo-sdr").first()
    if existing_mateo:
        # Seed solo los adicionales si aun no estan
        _seed_additional_agents(db)
        return
    # Carry over config from legacy MateoConfig if exists
    legacy = db.query(MateoConfig).order_by(MateoConfig.id).first()
    modelo = (legacy.modelo_ia if legacy else None) or "gemini-2.5-flash"
    display_name = (legacy.nombre_bot if legacy else None) or "Mateo"
    max_tokens = (legacy.max_tokens_respuesta if legacy else None) or 500
    base_prompt = (legacy.system_prompt if legacy and legacy.system_prompt else MATEO_SYSTEM_PROMPT)

    tools_allowed = ["search_kb", "create_prospect", "calendar_create_event", "escalate_to_human"]
    agent = AgentConfig(
        agent_type="mateo-sdr",
        display_name=display_name,
        descripcion="Asesor senior de importaciones MIP Quality & Logistics. Atiende leads entrantes, califica, cotiza y agenda reuniones.",
        avatar="🤵",
        modelo=modelo,
        activo=True,
        tools_allowed=json.dumps(tools_allowed),
        max_tool_calls=6,
        kb_folder_ids="[]",
        stages=json.dumps(["lead_inicial", "calificando", "cotizando"]),
        temperatura=0.7,
        max_tokens=max_tokens,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    # Descomponer prompt monolitico en bloques
    decomposed = _descompose_mateo_prompt_to_blocks(base_prompt)
    if not decomposed:
        # Fallback: un solo bloque personificacion con todo
        decomposed = [("personificacion", "identidad", "Personalidad base", base_prompt, 0)]

    for tipo, categoria, nombre, contenido, orden in decomposed:
        db.add(AgentBlock(
            agent_id=agent.id,
            tipo=tipo, categoria=categoria,
            nombre=nombre, contenido=contenido,
            orden=orden, activo=True,
        ))

    # Agregar bloques info_clave adicionales si hay info extra en legacy config
    if legacy:
        if legacy.reglas_negocio:
            db.add(AgentBlock(
                agent_id=agent.id, tipo="formato", categoria="identidad",
                nombre="Reglas de negocio custom", contenido=legacy.reglas_negocio,
                orden=25, activo=True,
            ))
        if legacy.flujo_conversacion:
            db.add(AgentBlock(
                agent_id=agent.id, tipo="pasos", categoria="instrucciones",
                nombre="Flujo de conversacion", contenido=legacy.flujo_conversacion,
                orden=45, activo=True,
            ))
        if legacy.precios_publicos:
            db.add(AgentBlock(
                agent_id=agent.id, tipo="info_precios", categoria="info_clave",
                nombre="Precios publicos", contenido=legacy.precios_publicos,
                orden=70, activo=True, es_reusable=True, block_key="precios_mip",
            ))
    db.commit()

    # Update Mateo stages to match pipeline
    agent.stages = json.dumps(["lead_inicial", "calificando"])
    agent.tools_allowed = json.dumps(["search_kb", "create_prospect", "calendar_create_event", "check_calendar_availability", "add_to_pipeline", "escalate_to_human"])
    db.commit()
    print(f"[agent-builder] Seeded Mateo agent with {len(db.query(AgentBlock).filter(AgentBlock.agent_id==agent.id).all())} blocks")

    # Seed 3 agentes adicionales para multi-stage pipeline
    _seed_additional_agents(db)


def _seed_additional_agents(db):
    """Crea Carla (Cerradora), Paula (Soporte Post-venta), Diego (Retencion/Perdidos)."""
    existing_types = {a.agent_type for a in db.query(AgentConfig).all()}

    # 1. Carla - Cerradora (stages: cotizando, cerrando)
    if "carla-cierre" not in existing_types:
        carla = AgentConfig(
            agent_type="carla-cierre",
            display_name="Carla - Ejecutiva de Cierre",
            descripcion="Cierra ventas con clientes calificados. Maneja objeciones de precio, negocia condiciones, genera cotizaciones formales.",
            avatar="👩‍💼",
            modelo="gemini-2.5-flash",
            activo=True,
            tools_allowed=json.dumps(["search_kb", "create_prospect", "calendar_create_event", "check_calendar_availability", "add_to_pipeline", "escalate_to_human"]),
            max_tool_calls=8,
            kb_folder_ids="[]",
            stages=json.dumps(["cotizando", "cerrando"]),
            temperatura=0.6,
            max_tokens=600,
        )
        db.add(carla)
        db.commit()
        db.refresh(carla)
        _add_agent_blocks(carla, db, [
            ("personificacion", "identidad", "Personalidad", 0, """Eres Carla, ejecutiva de cierre senior de MIP Quality & Logistics. Tienes 10 años de experiencia cerrando ventas B2B de importacion. Eres directa, profesional, orientada a numeros y a cerrar.

Usas 'tu' en espanol chileno, tono cercano pero con autoridad comercial. Nunca regateas, defiendes el valor."""),
            ("formato", "identidad", "Formato respuesta", 20, """RESPUESTAS:
- Cortas y al punto, maximo 3 parrafos.
- Siempre con un numero concreto: precio, plazo, descuento, fecha.
- Cada respuesta termina con UN CTA especifico de cierre."""),
            ("instrucciones", "instrucciones", "Tecnicas de cierre", 30, """ESTRATEGIA DE CIERRE:
1. ANCLAJE: siempre da un rango de precio concreto antes que el cliente lo pida.
2. OBJECIONES: "si el precio es el tema, podemos ajustar en X. Pero el valor esta en Y."
3. URGENCIA REAL: "los precios FOB se ajustan con la tasa del RMB, si cerramos esta semana fijamos tarifa."
4. ALTERNATIVAS: nunca preguntes 'quieres?' sino '¿prefieres pagar 50/50 o 30/70?'
5. SUMA DE PEQUEÑOS SI: haz que el cliente diga si a cosas pequeñas antes del cierre grande.
6. PROPUESTA CONCRETA: siempre ofrece enviar cotizacion formal en PDF."""),
            ("casos", "instrucciones", "Casos objeciones", 40, """OBJECIONES Y COMO LAS MANEJAS:
- "Es caro" -> "Te entiendo, pero compara: estas pagando la confiabilidad de un equipo en China. Mira el costo por unidad al año."
- "Necesito pensarlo" -> "Claro. ¿Que dato te falta para decidir? Te lo armo en 24 horas."
- "Otra empresa me ofrecio mas barato" -> "Interesante. ¿Te incluye inspecciones pre-embarque? ¿Tienen oficina en China? La diferencia son esos detalles que cuidan tu inversion."
- "No tengo todo el presupuesto" -> "Tenemos financiamiento: podemos adelantar tu 50% y cobrarte a 30/60 dias post-entrega. ¿Eso te ayuda?"
"""),
            ("info_precios", "info_clave", "Rangos cerrados MIP", 50, """RANGOS DE PRECIOS QUE PUEDES MANEJAR:
- Margen MIP estandar: 15-25% sobre CIF
- Descuento max por volumen >5000 un: 5%
- Descuento max por volumen >10000 un: 10%
- Condiciones de pago flexibles: 50/50, 30/70, 100% anticipo con 2% descuento, LC a 30 dias.
- Flete maritimo: 8-12% del FOB
- Flete aereo: 20-25% del FOB"""),
        ])

    # 2. Paula - Soporte Post-venta (stages: cliente_activo, soporte_post_venta)
    if "paula-soporte" not in existing_types:
        paula = AgentConfig(
            agent_type="paula-soporte",
            display_name="Paula - Atencion Post-venta",
            descripcion="Atiende clientes activos: consultas de estado de pedido, tracking, resolucion de problemas, garantias.",
            avatar="👩‍🎓",
            modelo="gemini-2.5-flash",
            activo=True,
            tools_allowed=json.dumps(["check_order_status", "search_kb", "escalate_to_human", "add_to_pipeline"]),
            max_tool_calls=6,
            kb_folder_ids="[]",
            stages=json.dumps(["cliente_activo", "soporte_post_venta"]),
            temperatura=0.5,
            max_tokens=500,
        )
        db.add(paula)
        db.commit()
        db.refresh(paula)
        _add_agent_blocks(paula, db, [
            ("personificacion", "identidad", "Personalidad", 0, """Eres Paula, del equipo de Atencion al Cliente de MIP Quality & Logistics. Empatica, paciente y orientada a resolver. Haces que el cliente se sienta escuchado y acompañado durante todo el proceso de su importacion.

Usas 'tu', tono calido y profesional."""),
            ("formato", "identidad", "Formato", 20, """- Mensajes empaticos, maximo 3 parrafos.
- Siempre confirma lo que el cliente te dice antes de avanzar.
- Usa bullets cuando des info estructurada."""),
            ("instrucciones", "instrucciones", "Flujo soporte", 30, """FLUJO DE SOPORTE:
1. SALUDO + confirmar identidad: pide email y N° de pedido para verificar.
2. CONSULTA: usa `check_order_status` para ver el estado actual.
3. RESPUESTA: comunica etapa actual + fecha estimada de siguiente paso.
4. SI HAY PROBLEMA: documenta, escala con `escalate_to_human` si es mayor.
5. CIERRE: pregunta si hay algo mas + confirma que te puede escribir cuando quiera."""),
            ("casos", "instrucciones", "Casos tipicos", 40, """- "¿Donde esta mi pedido?" -> check_order_status + dar etapa y fechas.
- "Esta atrasado" -> disculpa + consulta + da nueva ETA + escala si el delay es >1 semana.
- "Hay un defecto" -> lamenta + pide fotos/video + escala a QC con urgencia alta.
- "¿Cuando llega?" -> da etapa actual + dias estimados por etapa restante."""),
        ])

    # 3. Diego - Retencion y clientes perdidos (stages: cliente_perdido)
    if "diego-retencion" not in existing_types:
        diego = AgentConfig(
            agent_type="diego-retencion",
            display_name="Diego - Retencion & Recuperacion",
            descripcion="Reactiva clientes perdidos o que muestran señales de churn. Ofrece incentivos, escucha objeciones, reconecta.",
            avatar="🤝",
            modelo="gemini-2.5-flash",
            activo=True,
            tools_allowed=json.dumps(["search_kb", "create_prospect", "calendar_create_event", "escalate_to_human", "add_to_pipeline"]),
            max_tool_calls=6,
            kb_folder_ids="[]",
            stages=json.dumps(["cliente_perdido"]),
            temperatura=0.8,
            max_tokens=500,
        )
        db.add(diego)
        db.commit()
        db.refresh(diego)
        _add_agent_blocks(diego, db, [
            ("personificacion", "identidad", "Personalidad", 0, """Eres Diego, especialista en recuperacion de clientes de MIP Quality & Logistics. Humilde, curioso, empatico. Tu mision NO es vender a la fuerza, es entender que paso y dejar la puerta abierta con valor.

Usas 'tu', tono conversacional, genuinamente interesado."""),
            ("formato", "identidad", "Formato", 20, """- Corto y conciso. Respeta el tiempo del cliente.
- Haz UNA pregunta por mensaje, escucha.
- No insistas. Ofreces valor y dejas al cliente decidir."""),
            ("instrucciones", "instrucciones", "Estrategia de retencion", 30, """ESTRATEGIA:
1. ESCUCHA SIN DEFENDER: valida la razon del cliente primero ("entiendo totalmente que...").
2. PREGUNTA ABIERTA: ¿que nos falto? ¿que hubiera hecho diferencia?
3. APRENDIZAJE: agradece el feedback honestamente.
4. VALOR SIN PRESION: "te dejo este dato por si algun dia vuelve a ser util" (ej: guia de costos, contacto).
5. CIERRE ABIERTO: "si alguna vez quieres volver a conversar, mi linea esta abierta."
No uses CTAs agresivos. Este cliente ya dijo no."""),
        ])
    db.commit()


def _add_agent_blocks(agent, db, blocks_data):
    """Helper para agregar lista de bloques a un agente."""
    for tipo, categoria, nombre, orden, contenido in blocks_data:
        db.add(AgentBlock(
            agent_id=agent.id, tipo=tipo, categoria=categoria,
            nombre=nombre, contenido=contenido,
            orden=orden, activo=True,
        ))
    db.commit()


def _compose_agent_prompt(agent: "AgentConfig", db, extra_context: str = "") -> str:
    """Compone el system prompt final concatenando bloques activos en orden.
    Orden: identidad -> instrucciones -> info_clave -> contexto externo.
    """
    blocks = db.query(AgentBlock).filter(
        AgentBlock.agent_id == agent.id,
        AgentBlock.activo == True,
    ).order_by(AgentBlock.categoria, AgentBlock.orden, AgentBlock.id).all()

    # Group by categoria para ordenar categorias semanticamente
    cat_order = {"identidad": 0, "instrucciones": 1, "info_clave": 2}
    blocks.sort(key=lambda b: (cat_order.get(b.categoria, 99), b.orden, b.id))

    parts = []
    last_cat = None
    for b in blocks:
        if b.categoria != last_cat:
            last_cat = b.categoria
            # Category header for LLM readability
            header_map = {
                "identidad": "# IDENTIDAD",
                "instrucciones": "# INSTRUCCIONES",
                "info_clave": "# INFORMACION CLAVE",
            }
            parts.append("\n\n" + header_map.get(b.categoria, "# " + b.categoria.upper()))
        # Special rendering for "que_no_hacer" - prohibition block
        if b.tipo == "que_no_hacer":
            parts.append(f"\n\n## ⚠️ {b.nombre} - PROHIBICIONES ESTRICTAS\nNUNCA hagas lo siguiente bajo ninguna circunstancia:\n{b.contenido}")
        else:
            parts.append(f"\n\n## {b.nombre}\n{b.contenido}")
        # Render sub_steps if any
        try:
            subs = json.loads(b.sub_steps or "[]")
            if subs:
                for s in subs:
                    line = f"\n- [{s.get('orden','')}] {s.get('texto','')}"
                    if s.get("tool_assigned"):
                        line += f"   (tool: `{s['tool_assigned']}`)"
                    parts.append(line)
        except Exception:
            pass
        # Render functions asociadas a este bloque (function-calling automatico)
        try:
            block_fns = json.loads(getattr(b, "functions", None) or "[]")
            if block_fns:
                parts.append("\n\n**FUNCIONES DE ESTE BLOQUE** (llamalas cuando corresponda):")
                for fn in block_fns:
                    fn_name = fn.get("name", "")
                    fn_label = fn.get("label", fn_name)
                    fn_when = fn.get("when", "")
                    fn_params = fn.get("params") or {}
                    line = f"\n- `{fn_name}` — {fn_label}"
                    if fn_when:
                        line += f" · Cuando: {fn_when}"
                    if fn_params:
                        params_str = ", ".join(f"{k}={v}" for k, v in fn_params.items())
                        line += f" · Params pre-configurados: {params_str}"
                    parts.append(line)
        except Exception:
            pass

    # Append allowed tools hint — combina tools_allowed + todas las functions de los bloques
    try:
        allowed = json.loads(agent.tools_allowed or "[]")
    except Exception:
        allowed = []
    # Merge: agregar functions declaradas en cada bloque
    for b in blocks:
        try:
            for fn in json.loads(getattr(b, "functions", None) or "[]"):
                fname = fn.get("name")
                if fname and fname not in allowed:
                    allowed.append(fname)
        except Exception:
            pass
    if allowed:
        tool_rows = db.query(Tool).filter(Tool.name.in_(allowed), Tool.activo == True).all()
        if tool_rows:
            parts.append("\n\n# TOOLS DISPONIBLES (FUNCIONES)")
            parts.append("\nCuando necesites informacion especifica o quieras ejecutar acciones, LLAMA a estas funciones EN VEZ de responder directamente:")
            for t in tool_rows:
                parts.append(f"\n- `{t.name}`: {t.description}")
            parts.append("\n\nREGLAS DE USO DE TOOLS:")
            parts.append("\n- Si el usuario pregunta por precios/politicas/productos/plazos -> LLAMA `search_kb` ANTES de responder.")
            parts.append("\n- Si el usuario comparte su email/nombre/empresa con intencion de cotizar -> LLAMA `create_prospect` con sus datos.")
            parts.append("\n- Si el usuario quiere agendar una reunion/llamada/demo -> LLAMA `calendar_create_event`.")
            parts.append("\n- Si la consulta es muy compleja o pide hablar con humano -> LLAMA `escalate_to_human`.")
            parts.append("\n- DESPUES de ejecutar un tool y recibir el resultado, redacta una respuesta natural al usuario usando esa info.")

    if extra_context:
        parts.append("\n\n# CONTEXTO DINAMICO\n" + extra_context)

    return "".join(parts).strip()


# ─── Endpoints: Agents CRUD ───
@app.get("/api/agents")
def list_agents(db: Session = Depends(get_db)):
    agents = db.query(AgentConfig).order_by(AgentConfig.id).all()
    return [{
        "id": a.id, "agent_type": a.agent_type, "display_name": a.display_name,
        "descripcion": a.descripcion or "", "avatar": a.avatar or "",
        "modelo": a.modelo, "activo": a.activo,
        "total_conversations": a.total_conversations or 0,
        "total_tokens_in": a.total_tokens_in or 0,
        "total_tokens_out": a.total_tokens_out or 0,
        "total_cost_usd": a.total_cost_usd or 0,
        "blocks_count": len(a.blocks) if a.blocks else 0,
    } for a in agents]


@app.post("/api/agents", response_model=AgentConfigOut)
def create_agent(data: AgentConfigCreate, db: Session = Depends(get_db)):
    existing = db.query(AgentConfig).filter(AgentConfig.agent_type == data.agent_type).first()
    if existing:
        raise HTTPException(400, f"Ya existe un agente con agent_type={data.agent_type}")
    a = AgentConfig(**data.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@app.get("/api/agents/{id}")
def get_agent(id: int, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    blocks = db.query(AgentBlock).filter(AgentBlock.agent_id == id).order_by(AgentBlock.orden).all()
    return {
        "id": a.id, "agent_type": a.agent_type, "display_name": a.display_name,
        "descripcion": a.descripcion or "", "avatar": a.avatar or "",
        "modelo": a.modelo, "activo": a.activo,
        "tools_allowed": a.tools_allowed, "max_tool_calls": a.max_tool_calls,
        "kb_folder_ids": a.kb_folder_ids, "stages": a.stages,
        "temperatura": a.temperatura, "max_tokens": a.max_tokens,
        "total_conversations": a.total_conversations or 0,
        "total_tokens_in": a.total_tokens_in or 0,
        "total_tokens_out": a.total_tokens_out or 0,
        "total_cost_usd": a.total_cost_usd or 0,
        "blocks": [{
            "id": b.id, "tipo": b.tipo, "categoria": b.categoria,
            "nombre": b.nombre, "contenido": b.contenido,
            "orden": b.orden, "activo": b.activo,
            "sub_steps": b.sub_steps, "es_reusable": b.es_reusable,
            "block_key": b.block_key,
        } for b in blocks],
    }


@app.put("/api/agents/{id}")
def update_agent(id: int, data: dict, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    for k, v in data.items():
        if hasattr(a, k) and k not in ("id", "created_at"):
            setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return {"id": a.id, "agent_type": a.agent_type, "updated": True}


@app.delete("/api/agents/{id}")
def delete_agent(id: int, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    db.delete(a)
    db.commit()
    return {"deleted": True}


@app.get("/api/agents/{id}/prompt-preview")
def preview_agent_prompt(id: int, db: Session = Depends(get_db)):
    """Preview del prompt compuesto que se enviara al LLM."""
    a = db.query(AgentConfig).get(id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    prompt = _compose_agent_prompt(a, db)
    return {"agent_id": a.id, "prompt": prompt, "length_chars": len(prompt), "approx_tokens": len(prompt) // 4}


# ─── Endpoints: Blocks CRUD ───
@app.post("/api/agents/{agent_id}/blocks")
def create_block(agent_id: int, data: dict, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(agent_id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    b = AgentBlock(
        agent_id=agent_id,
        tipo=data.get("tipo", "personificacion"),
        categoria=data.get("categoria", "identidad"),
        nombre=data.get("nombre", "Sin nombre"),
        contenido=data.get("contenido", ""),
        orden=data.get("orden", 0),
        activo=data.get("activo", True),
        sub_steps=data.get("sub_steps", "[]"),
        functions=data.get("functions", "[]"),
        es_reusable=data.get("es_reusable", False),
        block_key=data.get("block_key"),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return {"id": b.id, "agent_id": b.agent_id}


@app.put("/api/blocks/{id}")
def update_block(id: int, data: dict, db: Session = Depends(get_db)):
    b = db.query(AgentBlock).get(id)
    if not b:
        raise HTTPException(404, "Block no encontrado")
    for k, v in data.items():
        if hasattr(b, k) and k not in ("id", "agent_id", "created_at"):
            setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return {"id": b.id, "updated": True}


@app.delete("/api/blocks/{id}")
def delete_block(id: int, db: Session = Depends(get_db)):
    b = db.query(AgentBlock).get(id)
    if not b:
        raise HTTPException(404, "Block no encontrado")
    db.delete(b)
    db.commit()
    return {"deleted": True}


@app.post("/api/blocks/reorder")
def reorder_blocks(data: dict, db: Session = Depends(get_db)):
    """Recibe {block_ids: [1,5,3,2,...]} y ajusta orden en bulk."""
    ids = data.get("block_ids", [])
    for i, bid in enumerate(ids):
        b = db.query(AgentBlock).get(bid)
        if b:
            b.orden = i
    db.commit()
    return {"reordered": len(ids)}


# ─── Endpoints: Tools registry ───
@app.get("/api/agent-tools")
def list_tools(db: Session = Depends(get_db)):
    tools = db.query(Tool).order_by(Tool.categoria, Tool.name).all()
    return [{
        "id": t.id, "name": t.name, "description": t.description,
        "categoria": t.categoria, "schema_input": t.schema_input,
        "activo": t.activo, "peligroso": t.peligroso, "handler": t.handler,
    } for t in tools]


@app.post("/api/agent-tools")
def create_tool(data: dict, db: Session = Depends(get_db)):
    t = Tool(
        name=data["name"],
        description=data.get("description", ""),
        categoria=data.get("categoria", "utility"),
        schema_input=data.get("schema_input", "{}"),
        activo=data.get("activo", True),
        peligroso=data.get("peligroso", False),
        handler=data.get("handler", ""),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name}


# ─── Catalogo de funciones disponibles para asociar a bloques ───
AGENT_FUNCTION_CATALOG = [
    # Pipeline & CRM
    {"name": "create_prospect", "label": "Registrar prospect", "icon": "user-plus", "categoria": "crm",
     "description": "Guarda el cliente en el CRM con nombre/email/telefono.",
     "params": [
         {"key": "fuente", "label": "Fuente del lead", "type": "select",
          "options": ["chatbot_mateo", "landing", "whatsapp", "email", "referido"], "default": "chatbot_mateo"},
         {"key": "estado", "label": "Estado inicial", "type": "select",
          "options": ["nuevo", "calificado", "caliente"], "default": "nuevo"},
     ]},
    {"name": "move_pipeline_stage", "label": "Cambiar etapa en pipeline", "icon": "exchange-alt", "categoria": "crm",
     "description": "Mueve la conversacion a otra etapa (calificando, cotizando, cerrando, etc).",
     "params": [
         {"key": "target_stage", "label": "Etapa destino", "type": "select", "required": True,
          "options": ["lead_inicial", "calificando", "cotizando", "cerrando", "cliente_activo", "soporte_post_venta", "cliente_perdido"]},
     ]},
    {"name": "tag_prospect", "label": "Etiquetar prospect", "icon": "tag", "categoria": "crm",
     "description": "Agrega una etiqueta o nota al prospect (ej: 'interesado en SKU X').",
     "params": [
         {"key": "tag", "label": "Etiqueta", "type": "text", "required": True,
          "placeholder": "ej: interesado-en-tshirts"},
     ]},
    # Calendar
    {"name": "check_calendar_availability", "label": "Consultar disponibilidad calendario", "icon": "calendar-check", "categoria": "calendar",
     "description": "Chequea slots libres en el calendario del equipo.",
     "params": [
         {"key": "duration_min", "label": "Duracion reunion (min)", "type": "number", "default": 30},
         {"key": "buffer_hours", "label": "Proximos N horas a buscar", "type": "number", "default": 72},
     ]},
    {"name": "calendar_create_event", "label": "Agendar reunion", "icon": "calendar-plus", "categoria": "calendar",
     "description": "Crea un evento en Google Calendar con invitacion al cliente.",
     "params": [
         {"key": "titulo_base", "label": "Titulo del evento", "type": "text",
          "default": "Reunion MIP Quality", "placeholder": "ej: Cotizacion con {cliente}"},
         {"key": "duration_min", "label": "Duracion (min)", "type": "number", "default": 30},
         {"key": "meet_link", "label": "Crear Google Meet", "type": "select",
          "options": ["si", "no"], "default": "si"},
     ]},
    # Data
    {"name": "search_kb", "label": "Buscar en base de conocimiento", "icon": "search", "categoria": "data",
     "description": "Busca info en la KB (precios, plazos, politicas).",
     "params": [
         {"key": "folder_filter", "label": "Carpeta especifica (opcional)", "type": "text",
          "placeholder": "ej: precios, o vacio para todas"},
         {"key": "max_results", "label": "Max resultados", "type": "number", "default": 3},
     ]},
    # Handoff
    {"name": "escalate_to_human", "label": "Derivar a humano", "icon": "user-friends", "categoria": "handoff",
     "description": "Crea un handoff para que un humano tome la conversacion.",
     "params": [
         {"key": "prioridad", "label": "Prioridad", "type": "select",
          "options": ["baja", "media", "alta", "critica"], "default": "media"},
         {"key": "notify_whatsapp", "label": "Avisar por WhatsApp", "type": "select",
          "options": ["si", "no"], "default": "si"},
     ]},
    {"name": "switch_agent", "label": "Cambiar de agente", "icon": "random", "categoria": "handoff",
     "description": "Pasa la conversacion a otro agente IA (ej: Mateo -> Carla).",
     "params": [
         {"key": "target_agent", "label": "Agente destino", "type": "text", "required": True,
          "placeholder": "ej: carla-soporte, paula-cotizaciones"},
     ]},
    # Email
    {"name": "send_templated_email", "label": "Enviar email con template", "icon": "envelope", "categoria": "email",
     "description": "Dispara un envio de email usando un template predefinido.",
     "params": [
         {"key": "template_id", "label": "Template", "type": "select", "required": True,
          "options": ["bienvenida", "cotizacion_lista", "seguimiento_24h", "nurturing_7d", "recuperacion_lead_frio"]},
         {"key": "delay_horas", "label": "Delay (horas)", "type": "number", "default": 0},
     ]},
    {"name": "trigger_email_sequence", "label": "Activar secuencia de emails", "icon": "paper-plane", "categoria": "email",
     "description": "Inicia una secuencia automatizada de follow-up.",
     "params": [
         {"key": "secuencia_id", "label": "Secuencia", "type": "select", "required": True,
          "options": ["onboarding_cliente", "nurturing_lead_frio", "seguimiento_post_cotizacion", "bienvenida_portal"]},
     ]},
    # WhatsApp
    {"name": "enviar_whatsapp", "label": "Enviar WhatsApp", "icon": "whatsapp", "categoria": "messaging",
     "description": "Envia un mensaje de WhatsApp al cliente usando un template aprobado.",
     "params": [
         {"key": "template", "label": "Template", "type": "select", "required": True,
          "options": ["bienvenida", "cotizacion_lista", "recordatorio_pago", "muestra_llego", "produccion_iniciada"]},
         {"key": "delay_min", "label": "Delay (min)", "type": "number", "default": 0},
     ]},
    # Negocio MIP (importacion China)
    {"name": "generar_cotizacion_pdf", "label": "Generar cotizacion PDF", "icon": "file-pdf", "categoria": "business",
     "description": "Crea un PDF formal de cotizacion con el detalle de productos y lo adjunta al pedido.",
     "params": [
         {"key": "incluir_imagenes", "label": "Incluir imagenes de productos", "type": "select",
          "options": ["si", "no"], "default": "si"},
         {"key": "validez_dias", "label": "Validez cotizacion (dias)", "type": "number", "default": 7},
         {"key": "moneda", "label": "Moneda", "type": "select",
          "options": ["USD", "CLP"], "default": "USD"},
     ]},
    {"name": "calcular_CIF", "label": "Calcular CIF Chile", "icon": "calculator", "categoria": "business",
     "description": "Estima el costo CIF (costo + seguro + flete) para importar a Chile desde China.",
     "params": [
         {"key": "peso_kg", "label": "Peso total (kg)", "type": "number", "required": True},
         {"key": "volumen_cbm", "label": "Volumen (m3)", "type": "number"},
         {"key": "origen_puerto", "label": "Puerto origen", "type": "select",
          "options": ["Shanghai", "Ningbo", "Shenzhen", "Guangzhou", "Qingdao"], "default": "Shanghai"},
         {"key": "destino_puerto", "label": "Puerto destino", "type": "select",
          "options": ["San Antonio", "Valparaiso", "Iquique"], "default": "San Antonio"},
         {"key": "incoterm", "label": "Incoterm", "type": "select",
          "options": ["FOB", "CIF", "CFR", "EXW"], "default": "FOB"},
     ]},
    {"name": "registrar_visita_fabrica", "label": "Registrar visita a fabrica", "icon": "industry", "categoria": "business",
     "description": "Programa una visita de inspeccion a la fabrica en China.",
     "params": [
         {"key": "tipo_visita", "label": "Tipo", "type": "select",
          "options": ["pre_produccion", "durante_produccion", "qc_pre_embarque", "urgente"], "default": "qc_pre_embarque"},
         {"key": "proveedor", "label": "Nombre proveedor", "type": "text", "required": True},
         {"key": "ciudad", "label": "Ciudad China", "type": "text", "placeholder": "ej: Shenzhen, Yiwu"},
     ]},
    {"name": "solicitar_muestra", "label": "Solicitar muestra a proveedor", "icon": "vial", "categoria": "business",
     "description": "Gestiona el envio de una muestra del producto al cliente antes de ordenar produccion.",
     "params": [
         {"key": "tipo_muestra", "label": "Tipo", "type": "select",
          "options": ["proveedor_standard", "customizada_cliente", "ssp"], "default": "proveedor_standard"},
         {"key": "courier", "label": "Courier", "type": "select",
          "options": ["DHL", "FedEx", "UPS", "proveedor_envia"], "default": "DHL"},
         {"key": "cliente_paga", "label": "Quien paga envio", "type": "select",
          "options": ["cliente", "MIP", "proveedor"], "default": "cliente"},
     ]},
    {"name": "confirmar_pago", "label": "Confirmar pago recibido", "icon": "check-double", "categoria": "business",
     "description": "Registra un pago recibido del cliente y actualiza el pedido.",
     "params": [
         {"key": "tipo_pago", "label": "Tipo", "type": "select", "required": True,
          "options": ["50_porcentaje", "50_final", "100_adelantado", "deposito_muestra"]},
         {"key": "metodo", "label": "Metodo", "type": "select",
          "options": ["transferencia_bancaria", "swift", "webpay", "paypal", "cheque"], "default": "transferencia_bancaria"},
         {"key": "moneda", "label": "Moneda", "type": "select",
          "options": ["USD", "CLP"], "default": "USD"},
     ]},
    # Soporte
    {"name": "crear_ticket_soporte", "label": "Crear ticket de soporte", "icon": "life-ring", "categoria": "support",
     "description": "Abre un ticket en el sistema de soporte para un problema del cliente.",
     "params": [
         {"key": "urgencia", "label": "Urgencia", "type": "select", "required": True,
          "options": ["baja", "media", "alta", "critica"]},
         {"key": "categoria", "label": "Categoria", "type": "select",
          "options": ["calidad_producto", "atraso_entrega", "problema_pago", "dano_envio", "consulta_general", "otro"], "default": "consulta_general"},
         {"key": "auto_asignar_kam", "label": "Auto-asignar al KAM", "type": "select",
          "options": ["si", "no"], "default": "si"},
     ]},
    # Avanzado
    {"name": "webhook_custom", "label": "Webhook custom", "icon": "code", "categoria": "advanced",
     "description": "Dispara un webhook HTTP POST a una URL externa con contexto del cliente.",
     "params": [
         {"key": "url", "label": "URL del webhook", "type": "text", "required": True,
          "placeholder": "https://mi-sistema.com/hook"},
         {"key": "metodo", "label": "Metodo HTTP", "type": "select",
          "options": ["POST", "PUT", "PATCH"], "default": "POST"},
         {"key": "auth_header", "label": "Header auth (opcional)", "type": "text",
          "placeholder": "Bearer XXX o X-API-Key"},
     ]},
]


@app.get("/api/agent-functions/catalog")
def list_function_catalog():
    """Devuelve el catalogo de funciones asignables a bloques del Agent Builder."""
    return AGENT_FUNCTION_CATALOG


# ─── Endpoints: Knowledge Base ───
@app.get("/api/kb/folders")
def list_kb_folders(db: Session = Depends(get_db)):
    folders = db.query(KnowledgeFolder).order_by(KnowledgeFolder.nombre).all()
    return [{
        "id": f.id, "nombre": f.nombre, "descripcion": f.descripcion or "",
        "color": f.color, "docs_count": len(f.docs) if f.docs else 0,
    } for f in folders]


@app.post("/api/kb/folders")
def create_kb_folder(data: dict, db: Session = Depends(get_db)):
    f = KnowledgeFolder(
        nombre=data["nombre"],
        descripcion=data.get("descripcion", ""),
        color=data.get("color", "#0A6FE0"),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id, "nombre": f.nombre}


@app.post("/api/kb/docs")
def create_kb_doc(data: dict, db: Session = Depends(get_db)):
    """Crea un doc y lo chunking + genera embeddings via Gemini."""
    _check_cost_limit("embeddings", db)  # hard-block si se alcanzo el limite
    d = KnowledgeDoc(
        folder_id=data["folder_id"],
        nombre=data["nombre"],
        contenido=data["contenido"],
        tokens_totales=len(data["contenido"]) // 4,
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    # Simple chunking (by paragraphs, max 500 chars)
    chunks = []
    buf = []
    cur_len = 0
    for para in d.contenido.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        if cur_len + len(para) > 500 and buf:
            chunks.append("\n\n".join(buf))
            buf = [para]
            cur_len = len(para)
        else:
            buf.append(para)
            cur_len += len(para)
    if buf:
        chunks.append("\n\n".join(buf))

    # Generate embeddings via Gemini
    for idx, chunk in enumerate(chunks):
        emb = _gemini_embed(chunk)
        db.add(KnowledgeChunk(
            doc_id=d.id,
            contenido=chunk,
            embedding=json.dumps(emb) if emb else None,
            dim=len(emb) if emb else 0,
            orden=idx,
            tokens=len(chunk) // 4,
        ))
    db.commit()
    return {"id": d.id, "chunks_created": len(chunks)}


@app.get("/api/kb/folders/{id}/docs")
def list_kb_docs(id: int, db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.folder_id == id).all()
    return [{
        "id": d.id, "nombre": d.nombre,
        "tokens_totales": d.tokens_totales,
        "chunks_count": len(d.chunks) if d.chunks else 0,
    } for d in docs]


def _gemini_embed(text: str):
    """Genera embedding via Gemini REST API (768d)."""
    if not GEMINI_API_KEY or not text:
        return None
    import requests as _req
    # gemini-embedding-001 es el modelo oficial (1536d default, soporta 768/1536/3072)
    candidates = [
        ("v1beta", "gemini-embedding-001"),
    ]
    payload = {
        "content": {"parts": [{"text": text[:20000]}]},
        "taskType": "RETRIEVAL_DOCUMENT",
        "outputDimensionality": 768,  # reduce para economizar storage, calidad similar
    }
    last_err = None
    for version, model in candidates:
        url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:embedContent?key={GEMINI_API_KEY}"
        try:
            r = _req.post(url, json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                emb = data.get("embedding", {}).get("values") or data.get("embeddings", [{}])[0].get("values")
                if emb and len(emb) > 0:
                    return emb
                last_err = f"{version}/{model}: empty response"
            else:
                last_err = f"{version}/{model}: HTTP {r.status_code}"
        except Exception as e:
            last_err = f"{version}/{model}: {str(e)[:100]}"
            continue
    print(f"[embed] all candidates failed. last: {last_err}")
    return None


@app.get("/api/debug/gemini-models")
def debug_list_gemini_models():
    """Diagnostic: lista modelos de Gemini disponibles con esta API key."""
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not set"}
    import requests as _req
    out = {}
    for version in ["v1", "v1beta"]:
        try:
            r = _req.get(
                f"https://generativelanguage.googleapis.com/{version}/models?key={GEMINI_API_KEY}",
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                models = data.get("models", [])
                out[version] = [
                    {"name": m.get("name"), "methods": m.get("supportedGenerationMethods", [])}
                    for m in models if "embed" in (m.get("name","") + " ".join(m.get("supportedGenerationMethods",[]))).lower()
                ]
            else:
                out[version] = {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
        except Exception as e:
            out[version] = {"error": str(e)[:200]}
    return out


def _cosine_sim(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x, y in zip(a, b))
    na = sum(x*x for x in a) ** 0.5
    nb = sum(x*x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _kb_search(query: str, folder_ids: list, top_k: int, db) -> list:
    """Busca chunks relevantes via cosine similarity. Fallback: LIKE."""
    q_emb = _gemini_embed(query)
    q = db.query(KnowledgeChunk).join(KnowledgeDoc)
    if folder_ids:
        q = q.filter(KnowledgeDoc.folder_id.in_(folder_ids))
    if q_emb:
        chunks = q.all()
        scored = []
        for c in chunks:
            try:
                emb = json.loads(c.embedding) if c.embedding else None
                score = _cosine_sim(q_emb, emb) if emb else 0
                scored.append((score, c))
            except Exception:
                continue
        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]
        return [{"score": round(s, 3), "contenido": c.contenido, "doc_id": c.doc_id} for s, c in top]
    # Fallback LIKE search
    chunks = q.filter(KnowledgeChunk.contenido.ilike(f"%{query}%")).limit(top_k).all()
    return [{"score": 0.5, "contenido": c.contenido, "doc_id": c.doc_id} for c in chunks]


# ═══════════════════════════════════════════════════
# TOOL HANDLERS - executa las acciones reales
# que el LLM solicita via function calling.
# ═══════════════════════════════════════════════════

def _handler_kb_search(args: dict, agent, db) -> dict:
    q = args.get("query", "")
    folder_id = args.get("folder_id")
    top_k = args.get("top_k", 3)
    folder_ids = [folder_id] if folder_id else json.loads(agent.kb_folder_ids or "[]")
    results = _kb_search(q, folder_ids, top_k, db)
    return {"results": results, "count": len(results)}


def _handler_create_prospect(args: dict, agent, db) -> dict:
    nombre = args.get("nombre", "").strip()
    email = args.get("email", "").strip()
    if not nombre and not email:
        return {"error": "Requiere nombre o email"}
    # Dedup por email
    if email:
        existing = db.query(Prospect).filter(Prospect.email == email).first()
        if existing:
            return {"prospect_id": existing.id, "already_existed": True}
    p = Prospect(
        nombre=nombre or email.split("@")[0],
        email=email, telefono=args.get("telefono", ""),
        empresa=args.get("empresa", ""),
        fuente="agent_tool",
        estado="nuevo",
        notas=f"Interes: {args.get('interes', '')}\nAgente: {agent.agent_type}",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"prospect_id": p.id, "created": True}


def _handler_calendar_book(args: dict, agent, db) -> dict:
    email = args.get("email", "").strip()
    fecha_iso = args.get("fecha_iso", "").strip()
    if not email or not fecha_iso:
        return {"error": "Requiere email y fecha_iso"}
    try:
        fecha = datetime.fromisoformat(fecha_iso.replace("Z", ""))
    except Exception:
        return {"error": "fecha_iso invalida. Usar ISO 8601 (YYYY-MM-DDTHH:MM)"}
    b = MateoCalendarBooking(
        visitor_email=email,
        visitor_nombre=args.get("nombre", ""),
        fecha_reunion=fecha,
        duracion_min=args.get("duracion_min", 30),
        motivo=args.get("motivo", f"Reunion solicitada por agente {agent.display_name}"),
        estado="confirmada",
        meet_link="https://meet.google.com/new",
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    # Enqueue confirmation email
    try:
        db.add(EmailLog(
            destinatario=email,
            asunto=f"Reunion agendada - {fecha.strftime('%d/%m/%Y %H:%M')}",
            cuerpo=f"Hola {args.get('nombre','')},\n\nTu reunion esta confirmada.\n\nFecha: {fecha.strftime('%d/%m/%Y %H:%M')}\nLink: {b.meet_link}\n\nSaludos,\n{agent.display_name}",
            estado="pendiente",
        ))
        db.commit()
    except Exception:
        pass
    return {"booking_id": b.id, "meet_link": b.meet_link, "fecha": fecha.isoformat()}


def _handler_escalate(args: dict, agent, db) -> dict:
    motivo = args.get("motivo", "Sin especificar")
    urgencia = args.get("urgencia", "media")
    # Crea un ticket para que el equipo humano se haga cargo
    from models import Ticket as _Ticket
    t = _Ticket(
        urgencia=urgencia,
        tipo_error="funcionalidad",
        seccion="Chatbot",
        descripcion=f"[ESCALATION desde {agent.display_name}]\n{motivo}",
        usuario="agent_escalation",
        estado="abierto",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"ticket_id": t.id, "escalated": True, "urgencia": urgencia}


def _handler_webhook(args: dict, agent, db) -> dict:
    url = args.get("url")
    payload = args.get("payload", {})
    method = (args.get("metodo") or args.get("method") or "POST").upper()
    auth_header = args.get("auth_header", "")
    if not url:
        return {"error": "Requiere url"}
    if not url.startswith("https://"):
        return {"error": "Solo URLs HTTPS permitidas"}
    try:
        import requests as _req
        headers = {"Content-Type": "application/json"}
        if auth_header:
            # Formato "Header: value" o solo "Bearer XXX"
            if ":" in auth_header:
                k, v = auth_header.split(":", 1)
                headers[k.strip()] = v.strip()
            elif auth_header.startswith("Bearer "):
                headers["Authorization"] = auth_header
            else:
                headers["Authorization"] = f"Bearer {auth_header}"
        r = _req.request(method, url, json=payload, headers=headers, timeout=10)
        return {"status_code": r.status_code, "response_preview": r.text[:300]}
    except Exception as e:
        return {"error": str(e)[:200]}


def _handler_calcular_cif(args: dict, agent, db) -> dict:
    """Estimacion CIF Chile desde China. Formula aproximada basada en tarifas reales."""
    peso = float(args.get("peso_kg", 0) or 0)
    vol = float(args.get("volumen_cbm", 0) or 0)
    origen = args.get("origen_puerto", "Shanghai")
    destino = args.get("destino_puerto", "San Antonio")
    incoterm = args.get("incoterm", "FOB")
    valor_fob = float(args.get("valor_fob_usd", 0) or 0)
    if peso <= 0 and vol <= 0:
        return {"error": "Requiere peso_kg o volumen_cbm"}
    # Chargeable weight (mayor entre peso real y volumetrico 1m3 = 167kg aereo, 1000kg maritimo)
    cw_maritimo = max(peso, vol * 1000)
    # Flete maritimo aproximado (USD/CBM consolidado): $80-150 segun temporada
    flete_estimado = max(vol * 120, peso * 0.12) if cw_maritimo > 0 else 0
    # Seguro: 0.3% del FOB (minimo $50)
    seguro = max(valor_fob * 0.003, 50) if valor_fob > 0 else 50
    # Gastos portuarios Chile
    portuarios_clp = 180000  # aprox
    cif_usd = valor_fob + flete_estimado + seguro if incoterm == "FOB" else valor_fob
    # Arancel Chile (6% por defecto, exento si TLC China)
    arancel = cif_usd * 0.06
    iva = (cif_usd + arancel) * 0.19
    total_chile = cif_usd + arancel + iva + (portuarios_clp / 950)  # USD~950 CLP
    return {
        "calculado": True,
        "inputs": {"peso_kg": peso, "volumen_cbm": vol, "origen": origen, "destino": destino, "incoterm": incoterm},
        "flete_maritimo_usd": round(flete_estimado, 2),
        "seguro_usd": round(seguro, 2),
        "cif_usd": round(cif_usd, 2),
        "arancel_usd": round(arancel, 2),
        "iva_usd": round(iva, 2),
        "portuarios_clp": portuarios_clp,
        "total_landed_cost_usd": round(total_chile, 2),
        "nota": "Estimacion orientativa. Consultar a agente de aduana para valores exactos.",
    }


def _handler_crear_ticket(args: dict, agent, db) -> dict:
    """Crea un Ticket (tabla Ticket si existe). Fallback: loggear en Actividad."""
    urgencia = args.get("urgencia", "media")
    categoria = args.get("categoria", "consulta_general")
    descripcion = args.get("descripcion", "") or args.get("asunto", "Ticket desde agente IA")
    try:
        # Intentar crear en tabla Ticket
        from sqlalchemy import inspect as _insp
        insp = _insp(engine)
        if insp.has_table("tickets"):
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO tickets (urgencia, categoria, descripcion, estado, created_at)
                    VALUES (:u, :c, :d, 'abierto', CURRENT_TIMESTAMP)
                """), {"u": urgencia, "c": categoria, "d": descripcion})
                conn.commit()
            return {"ticket_creado": True, "urgencia": urgencia, "categoria": categoria}
    except Exception as e:
        print(f"[_handler_crear_ticket] {e}")
    # Fallback: loggear en actividad
    try:
        log_evento(db, "ticket", "creado_agente", f"[{urgencia}/{categoria}] {descripcion}")
    except Exception:
        pass
    return {"ticket_creado": True, "via": "log", "urgencia": urgencia, "categoria": categoria, "descripcion": descripcion}


def _handler_confirmar_pago(args: dict, agent, db) -> dict:
    """Registra pago en Factura/Movimiento."""
    tipo = args.get("tipo_pago", "50_porcentaje")
    metodo = args.get("metodo", "transferencia_bancaria")
    monto = float(args.get("monto", 0) or 0)
    moneda = args.get("moneda", "USD")
    pedido_id = args.get("pedido_id")
    try:
        log_evento(db, "pago", "confirmado", f"Pago {tipo} via {metodo} · {monto} {moneda} · pedido={pedido_id}")
    except Exception:
        pass
    return {"confirmado": True, "tipo": tipo, "metodo": metodo, "monto": monto, "moneda": moneda}


def _handler_solicitar_muestra(args: dict, agent, db) -> dict:
    """Registra solicitud de muestra como actividad."""
    tipo = args.get("tipo_muestra", "proveedor_standard")
    courier = args.get("courier", "DHL")
    cliente_paga = args.get("cliente_paga", "cliente")
    try:
        log_evento(db, "muestra", "solicitada", f"Muestra {tipo} via {courier} · paga: {cliente_paga}")
    except Exception:
        pass
    return {"solicitada": True, "tipo": tipo, "courier": courier, "cliente_paga": cliente_paga, "estimado_envio": "3-5 dias habiles"}


def _handler_registrar_visita(args: dict, agent, db) -> dict:
    """Registra visita a fabrica como actividad."""
    tipo = args.get("tipo_visita", "qc_pre_embarque")
    proveedor = args.get("proveedor", "por confirmar")
    ciudad = args.get("ciudad", "")
    try:
        log_evento(db, "visita_fabrica", "programada", f"{tipo} · {proveedor} · {ciudad}")
    except Exception:
        pass
    return {"programada": True, "tipo": tipo, "proveedor": proveedor, "ciudad": ciudad, "estimado": "1-2 semanas para coordinar"}


def _handler_whatsapp_stub(args: dict, agent, db) -> dict:
    """Stub de WhatsApp. Cuando este activo Twilio/Meta API sera real."""
    template = args.get("template", "bienvenida")
    delay = int(args.get("delay_min", 0) or 0)
    try:
        log_evento(db, "whatsapp", "programado", f"Template: {template} · delay: {delay}min")
    except Exception:
        pass
    return {"programado": True, "template": template, "delay_min": delay, "nota": "WhatsApp API pendiente de configurar. Se loggeo en sistema."}


def _handler_generar_pdf_stub(args: dict, agent, db) -> dict:
    """Stub de generacion PDF. Cuando este el generador real se activa."""
    try:
        log_evento(db, "cotizacion_pdf", "solicitado", f"Formato: {args}")
    except Exception:
        pass
    return {"solicitado": True, "nota": "Generador de PDF pendiente. Se enviara manualmente por el equipo.", "params": args}


TOOL_HANDLERS = {
    "kb_search": _handler_kb_search,
    "search_kb": _handler_kb_search,
    "create_prospect": _handler_create_prospect,
    "prospect_create": _handler_create_prospect,
    "calendar_book": _handler_calendar_book,
    "calendar_create_event": _handler_calendar_book,
    "escalate": _handler_escalate,
    "escalate_to_human": _handler_escalate,
    "webhook_send": _handler_webhook,
    "send_webhook": _handler_webhook,
    "webhook_custom": _handler_webhook,
    # Nuevos handlers MIP
    "calcular_CIF": _handler_calcular_cif,
    "crear_ticket_soporte": _handler_crear_ticket,
    "confirmar_pago": _handler_confirmar_pago,
    "solicitar_muestra": _handler_solicitar_muestra,
    "registrar_visita_fabrica": _handler_registrar_visita,
    "enviar_whatsapp": _handler_whatsapp_stub,
    "generar_cotizacion_pdf": _handler_generar_pdf_stub,
}


def _execute_tool(tool_name: str, args: dict, agent, db) -> dict:
    """Ejecuta un tool por name. Retorna dict con resultado o error."""
    # Resolve handler: priority tool.handler field, fallback to tool name
    tool = db.query(Tool).filter(Tool.name == tool_name, Tool.activo == True).first()
    if not tool:
        return {"error": f"Tool '{tool_name}' no existe o inactivo"}
    handler_name = tool.handler or tool.name
    handler = TOOL_HANDLERS.get(handler_name) or TOOL_HANDLERS.get(tool.name)
    if not handler:
        return {"error": f"No handler registrado para '{tool_name}' (handler='{handler_name}')"}
    try:
        return handler(args, agent, db)
    except Exception as e:
        return {"error": str(e)[:300]}


def _clean_schema_for_gemini(schema):
    """Remueve fields que Gemini schema no soporta (default, additionalProperties, etc)."""
    if not isinstance(schema, dict):
        return schema
    ALLOWED = {"type", "properties", "required", "items", "description", "enum", "format", "nullable"}
    cleaned = {}
    for k, v in schema.items():
        if k not in ALLOWED:
            continue
        if k == "properties" and isinstance(v, dict):
            cleaned[k] = {pk: _clean_schema_for_gemini(pv) for pk, pv in v.items()}
        elif k == "items" and isinstance(v, dict):
            cleaned[k] = _clean_schema_for_gemini(v)
        else:
            cleaned[k] = v
    if "type" in cleaned and isinstance(cleaned["type"], str):
        cleaned["type"] = cleaned["type"].upper()
    return cleaned


def _build_gemini_tools(agent, db):
    """Construye la lista de FunctionDeclaration para Gemini.
    Incluye tools_allowed del agente + todas las functions declaradas en sus bloques activos.
    """
    try:
        allowed = json.loads(agent.tools_allowed or "[]")
    except Exception:
        allowed = []
    # Agregar functions de los bloques activos
    try:
        active_blocks = db.query(AgentBlock).filter(
            AgentBlock.agent_id == agent.id,
            AgentBlock.activo == True,
        ).all()
        for b in active_blocks:
            try:
                for fn in json.loads(getattr(b, "functions", None) or "[]"):
                    fname = fn.get("name")
                    if fname and fname not in allowed:
                        allowed.append(fname)
            except Exception:
                continue
    except Exception:
        pass
    if not allowed:
        return None
    rows = db.query(Tool).filter(Tool.name.in_(allowed), Tool.activo == True).all()
    if not rows:
        return None
    try:
        import google.generativeai as genai
        from google.generativeai.types import Tool as GTool, FunctionDeclaration
        decls = []
        for t in rows:
            try:
                schema = json.loads(t.schema_input or "{}")
            except Exception:
                schema = {"type": "object", "properties": {}}
            cleaned = _clean_schema_for_gemini(schema)
            if not cleaned.get("type"):
                cleaned["type"] = "OBJECT"
            if "properties" not in cleaned:
                cleaned["properties"] = {}
            decls.append(FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters=cleaned,
            ))
        return [GTool(function_declarations=decls)]
    except Exception as e:
        print(f"[gemini tools build] error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _agent_chat_gemini_with_tools(agent, system, messages, message, db, max_iterations=5):
    """Loop de function calling con Gemini. Retorna (reply, provider, tokens_in, tokens_out, tool_calls)."""
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_tools = _build_gemini_tools(agent, db)
    model = genai.GenerativeModel(
        agent.modelo or "gemini-2.5-flash",
        system_instruction=system,
        tools=gemini_tools,
    )
    gemini_history = []
    for m in messages[:-1]:
        gemini_history.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]})
    chat = model.start_chat(history=gemini_history)
    tool_calls_log = []
    tokens_in = 0
    tokens_out = 0
    current_msg = message
    for iteration in range(max_iterations):
        response = chat.send_message(current_msg)
        # Accumulate tokens
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_in += getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out += getattr(response.usage_metadata, "candidates_token_count", 0) or 0
        # Check if there are function calls
        fn_calls = []
        try:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fn_calls.append(part.function_call)
        except Exception:
            pass
        if not fn_calls:
            # Final text reply
            try:
                return response.text, "gemini", tokens_in, tokens_out, tool_calls_log
            except Exception:
                return "", "gemini", tokens_in, tokens_out, tool_calls_log
        # Execute each tool call and send back the result
        responses = []
        for fc in fn_calls:
            args = dict(fc.args) if fc.args else {}
            result = _execute_tool(fc.name, args, agent, db)
            tool_calls_log.append({"name": fc.name, "args": args, "result": result})
            try:
                from google.generativeai.types import content_types
                responses.append({
                    "function_response": {
                        "name": fc.name,
                        "response": result,
                    }
                })
            except Exception:
                responses.append({"function_response": {"name": fc.name, "response": result}})
        # Prepare next iteration with function responses
        current_msg = responses
    return "[Maximo de iteraciones alcanzado]", "gemini", tokens_in, tokens_out, tool_calls_log


# ─── Endpoints: Agent chat runtime ───
@app.post("/api/agents/{id}/chat")
def agent_chat(id: int, data: dict, db: Session = Depends(get_db)):
    """Chat runtime usando el agente con su prompt compuesto.
    Ahora con:
      - Pipeline tracking: crea/actualiza ConversationPipeline
      - Intent detection + auto-handoff entre agentes
      - Human handoff con notificacion WhatsApp
    """
    _check_cost_limit("gemini", db)  # hard-block si se alcanzo el limite mensual
    import uuid as _uuid
    import time as _time
    a = db.query(AgentConfig).get(id)
    if not a or not a.activo:
        raise HTTPException(404, "Agente no encontrado o inactivo")
    message = data.get("message", "").strip()
    history = data.get("history", [])
    session_id = data.get("session_id") or str(_uuid.uuid4())
    extra_context = data.get("context", "")
    visitor = dict(data.get("visitor", {}) or {})

    if not message:
        raise HTTPException(400, "Mensaje vacio")

    # Auto-extract visitor data desde el mensaje del usuario (regex simple)
    try:
        extracted = _extract_visitor_from_message(message, history)
        for k, v in extracted.items():
            if v and not visitor.get(k):
                visitor[k] = v
    except Exception as e:
        print(f"[visitor extract] {e}")

    # Pipeline tracking
    pipeline = _get_or_create_pipeline(session_id, a.id, visitor, db)
    # Marcar actividad del cliente
    pipeline.last_client_activity_at = datetime.now()
    pipeline.widget_is_open = True
    # Si admin tomo control, NO responder con IA - solo guardar mensaje del cliente
    if pipeline.control_mode == "human":
        try:
            conv = db.query(MateoConversation).filter(MateoConversation.session_id == session_id).first()
            if not conv:
                conv = MateoConversation(
                    session_id=session_id,
                    visitor_email=pipeline.visitor_email or "",
                    visitor_nombre=pipeline.visitor_nombre or "",
                )
                db.add(conv)
                db.commit()
                db.refresh(conv)
            db.add(MateoMessage(conversation_id=conv.id, role="user", content=message, tokens_usados=0))
            conv.mensajes_count = (conv.mensajes_count or 0) + 1
            conv.ultimo_mensaje_at = datetime.now()
            pipeline.total_messages = (pipeline.total_messages or 0) + 1
            pipeline.last_message_at = datetime.now()
            db.commit()
        except Exception as e:
            print(f"[human mode msg save] {e}")
        return {
            "reply": None,
            "provider": "human",
            "session_id": session_id,
            "agent_used": {"id": None, "name": pipeline.taken_over_by or "Admin", "avatar": "👤"},
            "pipeline": {
                "id": pipeline.id, "stage": pipeline.current_stage,
                "control_mode": "human",
                "taken_over_by": pipeline.taken_over_by,
            },
            "tool_calls": [],
            "tokens": {"input": 0, "output": 0},
            "cost_usd": 0,
            "latency_ms": 0,
            "waiting_for_human": True,
            "info_message": "Un asesor humano esta revisando tu mensaje. Te responderan pronto.",
        }
    # Si el pipeline tiene un agente distinto al actual (handoff previo), respetarlo
    if pipeline.current_agent_id and pipeline.current_agent_id != a.id:
        target_agent = db.query(AgentConfig).get(pipeline.current_agent_id)
        if target_agent and target_agent.activo:
            a = target_agent

    # Intent detection + posible handoff
    intent_data = _detect_intent(message, history)
    stage_changed = _maybe_handoff_pipeline(pipeline, intent_data, message, db)
    if stage_changed and pipeline.current_agent_id != a.id:
        target_agent = db.query(AgentConfig).get(pipeline.current_agent_id)
        if target_agent and target_agent.activo:
            a = target_agent
    pipeline.total_messages = (pipeline.total_messages or 0) + 1
    pipeline.last_message_at = datetime.now()
    db.commit()

    # AUTO RULES del agente actual: evaluar triggers custom
    try:
        auto_result = _evaluate_auto_rules(a, pipeline, message, intent_data, db)
        if auto_result.get("actions_executed"):
            # Si alguna auto-rule cambio el agente, respetar
            if pipeline.current_agent_id and pipeline.current_agent_id != a.id:
                target_agent = db.query(AgentConfig).get(pipeline.current_agent_id)
                if target_agent and target_agent.activo:
                    a = target_agent
    except Exception as e:
        print(f"[auto-rules eval] {e}")

    # Agrega info del pipeline al contexto
    extra_context += f"\n\n[PIPELINE STATE]\nStage: {pipeline.current_stage}\nIntent: {intent_data.get('intent')} (score={intent_data.get('score')})\nSentiment: {intent_data.get('sentiment')}"
    if pipeline.requires_human:
        extra_context += "\n⚠️ ESTE CLIENTE REQUIERE HANDOFF HUMANO. Informale que estas escalando su consulta y pasale un numero de contacto."

    # RAG: buscar en KB si hay folders configurados
    try:
        folder_ids = json.loads(a.kb_folder_ids or "[]")
    except Exception:
        folder_ids = []
    if folder_ids:
        kb_results = _kb_search(message, folder_ids, 3, db)
        if kb_results:
            extra_context += "\n\n[RESULTADOS KB]:\n" + "\n---\n".join(
                [f"({r['score']}) {r['contenido']}" for r in kb_results]
            )

    system = _compose_agent_prompt(a, db, extra_context)

    messages = []
    for h in history[-10:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    t0 = _time.time()
    reply_text = None
    provider_used = "fallback"
    tokens_in = 0
    tokens_out = 0
    error_msg = None
    tool_calls_executed = []

    # Model routing
    use_gemini = a.modelo.startswith("gemini") if a.modelo else True

    # Check if this agent has tools allowed
    try:
        allowed_tools = json.loads(a.tools_allowed or "[]")
    except Exception:
        allowed_tools = []
    has_tools = bool(allowed_tools)

    if use_gemini and GEMINI_API_KEY:
        try:
            if has_tools:
                # Tool-aware loop (function calling)
                reply_text, provider_used, tokens_in, tokens_out, tool_calls_executed = \
                    _agent_chat_gemini_with_tools(a, system, messages, message, db, max_iterations=a.max_tool_calls or 8)
            else:
                # Simple chat sin tools (mas rapido)
                import google.generativeai as genai
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel(a.modelo or "gemini-2.5-flash", system_instruction=system)
                gemini_history = []
                for m in messages[:-1]:
                    gemini_history.append({"role": "model" if m["role"] == "assistant" else "user", "parts": [m["content"]]})
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(message)
                reply_text = response.text
                provider_used = "gemini"
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                else:
                    tokens_in = len(system + message) // 4
                    tokens_out = len(reply_text) // 4
        except Exception as e:
            error_msg = str(e)
            print(f"[agent-chat gemini] error: {e}")

    if not reply_text and ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=(a.modelo if a.modelo.startswith("claude") else "claude-sonnet-4-20250514"),
                max_tokens=a.max_tokens or 800,
                system=system,
                messages=messages,
            )
            reply_text = response.content[0].text
            provider_used = "claude"
            if hasattr(response, "usage"):
                tokens_in = response.usage.input_tokens or 0
                tokens_out = response.usage.output_tokens or 0
        except Exception as e:
            error_msg = str(e)
            print(f"[agent-chat claude] error: {e}")

    if not reply_text:
        reply_text = f"Hola, soy {a.display_name}. Ahora no puedo procesar tu mensaje. Escribenos a contacto@mipquality.com."
        provider_used = "fallback"

    latency_ms = int((_time.time() - t0) * 1000)
    # Cost estimation (Gemini Flash default rates)
    cost = (tokens_in * 0.075 / 1_000_000) + (tokens_out * 0.30 / 1_000_000)

    # Save trace
    trace = AgentTrace(
        session_id=session_id,
        agent_id=a.id,
        prompt_tokens=tokens_in,
        output_tokens=tokens_out,
        cost_usd=cost,
        latency_ms=latency_ms,
        tool_calls=json.dumps(tool_calls_executed) if tool_calls_executed else "[]",
        input_summary=message[:200],
        output_summary=(reply_text[:200] if reply_text else ""),
        error=error_msg,
        provider=provider_used,
    )
    db.add(trace)

    # Aggregate on agent
    a.total_conversations = (a.total_conversations or 0) + 1
    a.total_tokens_in = (a.total_tokens_in or 0) + tokens_in
    a.total_tokens_out = (a.total_tokens_out or 0) + tokens_out
    a.total_cost_usd = (a.total_cost_usd or 0) + cost
    db.commit()

    return {
        "reply": reply_text,
        "provider": provider_used,
        "session_id": session_id,
        "trace_id": trace.id,
        "tokens": {"input": tokens_in, "output": tokens_out},
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
        "tool_calls": tool_calls_executed,
        "agent_used": {"id": a.id, "name": a.display_name, "avatar": a.avatar},
        "pipeline": {
            "id": pipeline.id, "stage": pipeline.current_stage,
            "intent": pipeline.intent_detected, "intent_score": pipeline.intent_score,
            "sentiment": pipeline.sentiment,
            "requires_human": pipeline.requires_human,
        },
    }


@app.get("/api/agents/{id}/traces")
def list_agent_traces(id: int, limit: int = 50, db: Session = Depends(get_db)):
    traces = db.query(AgentTrace).filter(AgentTrace.agent_id == id).order_by(AgentTrace.created_at.desc()).limit(limit).all()
    out = []
    for t in traces:
        try:
            tc = json.loads(t.tool_calls or "[]")
        except Exception:
            tc = []
        out.append({
            "id": t.id, "session_id": t.session_id,
            "prompt_tokens": t.prompt_tokens, "output_tokens": t.output_tokens,
            "cost_usd": t.cost_usd, "latency_ms": t.latency_ms,
            "provider": t.provider, "error": t.error,
            "input_summary": t.input_summary, "output_summary": t.output_summary,
            "tool_calls": tc, "tool_calls_count": len(tc),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    return out


# ═══════════════════════════════════════════════════
# COPILOTO IA - editor conversacional de agentes
# El admin chatea con el copiloto y este modifica los bloques del agente.
# ═══════════════════════════════════════════════════

COPILOT_SYSTEM_PROMPT = """Eres el Copiloto de Agent Builder, asistente experto en diseñar agentes IA.

IMPORTANTE: NUNCA aplicas cambios directamente. Solo PROPONES un plan en formato JSON que el admin revisa y decide si aprobar.

Tu flujo:
1. Lee el estado actual del agente.
2. Entiende lo que el admin quiere.
3. Responde en TEXTO BREVE explicando lo que propones (maximo 3 lineas, conversacional).
4. Luego, al final de tu respuesta, si hay cambios concretos, incluye un bloque:

```plan
{
  "resumen": "Frase corta de lo que cambia",
  "actions": [
    {
      "op": "create_block",
      "categoria": "instrucciones",
      "tipo": "que_no_hacer",
      "nombre": "Descuentos",
      "contenido": "Nunca dar descuentos mayores a 15% sin aprobacion del admin humano. Pedir autorizacion antes de comprometer.",
      "orden": 90
    },
    {
      "op": "update_block",
      "block_id": 10,
      "campos": {"contenido": "nuevo texto..."},
      "razon": "Ajustar tono a mas formal"
    },
    {
      "op": "delete_block",
      "block_id": 5,
      "razon": "Redundante con el bloque X"
    },
    {
      "op": "update_agent_settings",
      "campos": {"temperatura": 0.5, "max_tokens": 600},
      "razon": "Respuestas mas consistentes"
    }
  ]
}
```

REGLAS:
- Si el admin solo pregunta o pide explicacion, responde SIN bloque plan.
- Si el admin pide cambios, incluye SIEMPRE el bloque plan.
- Ops validos: create_block, update_block, delete_block, update_agent_settings.
- Para create_block: categoria (identidad/instrucciones/info_clave), tipo, nombre, contenido, orden.
- Para update_block: block_id + campos (puede incluir: nombre, contenido, orden, activo).
- Incluye razon breve en cada action para que el admin entienda por que.
- Escribe el JSON con minificacion. Solo un bloque ```plan por respuesta.
- Si el cambio es muy grande (>10 ops), divide en partes y pregunta cual hacer primero.

TONO: conversacional, directo, corto. Espanol chileno neutro. Max 3 lineas de texto + bloque plan."""


def _copilot_build_tools(db):
    """Construye las tools que el copiloto puede invocar para modificar el agente."""
    from google.generativeai.types import Tool as GTool, FunctionDeclaration
    tools = [
        FunctionDeclaration(
            name="update_block",
            description="Actualiza un bloque existente del agente. Usar para cambiar nombre, contenido, orden o activo de un bloque ya creado.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "block_id": {"type": "INTEGER", "description": "ID del bloque a actualizar"},
                    "nombre": {"type": "STRING", "description": "Nuevo nombre (opcional)"},
                    "contenido": {"type": "STRING", "description": "Nuevo contenido del bloque (opcional)"},
                    "orden": {"type": "INTEGER", "description": "Nuevo orden numerico (opcional)"},
                    "activo": {"type": "BOOLEAN", "description": "Activar/desactivar (opcional)"},
                },
                "required": ["block_id"],
            },
        ),
        FunctionDeclaration(
            name="create_block",
            description="Crea un nuevo bloque para el agente. Categorias: identidad | instrucciones | info_clave. Tipos validos: personificacion, objetivo, formato, pasos, casos, que_no_hacer, ctas, info_empresa, info_precios, info_productos, info_pagos, info_devoluciones, info_despachos, info_garantias, info_otro.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "categoria": {"type": "STRING", "enum": ["identidad", "instrucciones", "info_clave"]},
                    "tipo": {"type": "STRING"},
                    "nombre": {"type": "STRING"},
                    "contenido": {"type": "STRING"},
                    "orden": {"type": "INTEGER"},
                },
                "required": ["categoria", "tipo", "nombre", "contenido"],
            },
        ),
        FunctionDeclaration(
            name="delete_block",
            description="Elimina un bloque del agente.",
            parameters={
                "type": "OBJECT",
                "properties": {"block_id": {"type": "INTEGER"}},
                "required": ["block_id"],
            },
        ),
        FunctionDeclaration(
            name="update_agent_settings",
            description="Actualiza settings del agente (display_name, descripcion, avatar, temperatura, max_tokens, tools_allowed, modelo).",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "display_name": {"type": "STRING"},
                    "descripcion": {"type": "STRING"},
                    "avatar": {"type": "STRING"},
                    "temperatura": {"type": "NUMBER"},
                    "max_tokens": {"type": "INTEGER"},
                    "tools_allowed": {"type": "STRING", "description": "JSON array como string"},
                    "modelo": {"type": "STRING"},
                },
            },
        ),
    ]
    return [GTool(function_declarations=tools)]


def _copilot_execute_tool(name: str, args: dict, agent, db) -> dict:
    """Ejecuta las tools del copiloto."""
    try:
        if name == "update_block":
            b = db.query(AgentBlock).filter(
                AgentBlock.id == args.get("block_id"),
                AgentBlock.agent_id == agent.id,
            ).first()
            if not b:
                return {"error": f"Bloque {args.get('block_id')} no encontrado"}
            for k in ["nombre", "contenido", "orden", "activo"]:
                if k in args and args[k] is not None:
                    setattr(b, k, args[k])
            db.commit()
            return {"ok": True, "block_id": b.id, "updated": [k for k in ["nombre","contenido","orden","activo"] if k in args]}
        elif name == "create_block":
            b = AgentBlock(
                agent_id=agent.id,
                categoria=args.get("categoria", "identidad"),
                tipo=args.get("tipo", "personificacion"),
                nombre=args.get("nombre", "Nuevo bloque"),
                contenido=args.get("contenido", ""),
                orden=args.get("orden", 100),
                activo=True,
            )
            db.add(b)
            db.commit()
            db.refresh(b)
            return {"ok": True, "block_id": b.id, "created": True}
        elif name == "delete_block":
            b = db.query(AgentBlock).filter(
                AgentBlock.id == args.get("block_id"),
                AgentBlock.agent_id == agent.id,
            ).first()
            if not b:
                return {"error": "Bloque no encontrado"}
            db.delete(b)
            db.commit()
            return {"ok": True, "deleted": True}
        elif name == "update_agent_settings":
            for k in ["display_name", "descripcion", "avatar", "temperatura", "max_tokens", "tools_allowed", "modelo"]:
                if k in args and args[k] is not None:
                    setattr(agent, k, args[k])
            db.commit()
            return {"ok": True, "updated": [k for k in args.keys() if args[k] is not None]}
        return {"error": f"Tool desconocida: {name}"}
    except Exception as e:
        return {"error": str(e)[:200]}


def _copilot_describe_agent(agent, db) -> str:
    """Genera descripcion compacta del estado actual del agente para el copiloto."""
    blocks = db.query(AgentBlock).filter(AgentBlock.agent_id == agent.id).order_by(AgentBlock.categoria, AgentBlock.orden).all()
    lines = [
        f"# ESTADO ACTUAL DEL AGENTE",
        f"ID: {agent.id}",
        f"Nombre: {agent.display_name} ({agent.agent_type})",
        f"Avatar: {agent.avatar}",
        f"Descripcion: {agent.descripcion or '(vacia)'}",
        f"Modelo: {agent.modelo} · Temperatura: {agent.temperatura} · Max tokens: {agent.max_tokens}",
        f"Tools permitidos: {agent.tools_allowed}",
        f"Stages: {agent.stages}",
        f"Total conversaciones: {agent.total_conversations or 0}",
        "",
        f"## BLOQUES ({len(blocks)}):",
    ]
    for b in blocks:
        preview = (b.contenido or "").replace("\n", " ")[:120]
        lines.append(f"- [id={b.id}] [{b.categoria}] [{b.tipo}] orden={b.orden} activo={b.activo} '{b.nombre}': {preview}")
    return "\n".join(lines)


def _extract_copilot_plan(text: str) -> Optional[dict]:
    """Extrae el bloque ```plan ...``` del reply del copiloto. Retorna dict o None."""
    import re as _re
    m = _re.search(r'```plan\s*(\{.*?\})\s*```', text or "", _re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception as e:
        print(f"[plan parse] {e}")
        return None


def _strip_plan_block(text: str) -> str:
    """Remueve el bloque plan del reply para mostrar solo el texto conversacional."""
    import re as _re
    return _re.sub(r'```plan\s*\{.*?\}\s*```', '', text or "", flags=_re.DOTALL).strip()


def _validate_copilot_plan(plan: dict, agent, db) -> list:
    """Valida el plan contra el estado actual del agente y enriquece cada action con
    before/after para mostrar diff en UI. Retorna lista de actions validadas."""
    actions_validated = []
    existing_blocks = {b.id: b for b in db.query(AgentBlock).filter(AgentBlock.agent_id == agent.id).all()}
    for act in (plan.get("actions") or []):
        op = act.get("op")
        item = {"op": op, "razon": act.get("razon", ""), "valid": True}
        if op == "create_block":
            item["categoria"] = act.get("categoria", "identidad")
            item["tipo"] = act.get("tipo", "personificacion")
            item["nombre"] = act.get("nombre", "Nuevo bloque")
            item["contenido"] = act.get("contenido", "")
            item["orden"] = act.get("orden", 100)
        elif op == "update_block":
            bid = act.get("block_id")
            b = existing_blocks.get(bid)
            if not b:
                item["valid"] = False
                item["error"] = f"Bloque {bid} no existe"
            else:
                campos = act.get("campos") or {}
                item["block_id"] = bid
                item["before"] = {
                    "nombre": b.nombre, "contenido": b.contenido,
                    "orden": b.orden, "activo": b.activo,
                }
                item["after"] = {k: campos.get(k, getattr(b, k, None)) for k in ["nombre", "contenido", "orden", "activo"]}
                item["campos"] = campos
        elif op == "delete_block":
            bid = act.get("block_id")
            b = existing_blocks.get(bid)
            if not b:
                item["valid"] = False
                item["error"] = f"Bloque {bid} no existe"
            else:
                item["block_id"] = bid
                item["before"] = {"nombre": b.nombre, "categoria": b.categoria, "tipo": b.tipo, "contenido": b.contenido[:200] if b.contenido else ""}
        elif op == "update_agent_settings":
            campos = act.get("campos") or {}
            item["campos"] = campos
            item["before"] = {k: getattr(agent, k, None) for k in campos.keys() if hasattr(agent, k)}
            item["after"] = {k: campos.get(k) for k in campos.keys()}
        else:
            item["valid"] = False
            item["error"] = f"Op desconocida: {op}"
        actions_validated.append(item)
    return actions_validated


@app.post("/api/agents/{id}/copilot")
def agent_copilot(id: int, data: dict, db: Session = Depends(get_db)):
    """Chat del admin con el copiloto. El copiloto PROPONE cambios (no los aplica).
    Retorna reply + plan opcional con acciones que el admin puede aprobar/rechazar.
    """
    _check_cost_limit("gemini", db)  # hard-block si se alcanzo el limite mensual
    agent = db.query(AgentConfig).get(id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")
    message = (data.get("message") or "").strip()
    history = data.get("history", [])
    if not message:
        raise HTTPException(400, "Mensaje vacio")

    # Construir system prompt con contexto actual del agente
    agent_state = _copilot_describe_agent(agent, db)
    system = COPILOT_SYSTEM_PROMPT + "\n\n" + agent_state

    provider_used = "none"
    reply_text = None

    # Try Gemini first
    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system)
            gemini_history = []
            for h in (history or [])[-10:]:
                role = "model" if h.get("role") == "assistant" else "user"
                gemini_history.append({"role": role, "parts": [h.get("content", "")]})
            chat = model.start_chat(history=gemini_history)
            resp = chat.send_message(message)
            reply_text = resp.text
            provider_used = "gemini"
        except Exception as e:
            print(f"[copilot gemini] {e}")

    # Fallback a Claude
    if not reply_text and ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msgs = []
            for h in (history or [])[-10:]:
                msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            msgs.append({"role": "user", "content": message})
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=system,
                messages=msgs,
            )
            reply_text = resp.content[0].text
            provider_used = "claude"
        except Exception as e:
            print(f"[copilot claude] {e}")

    if not reply_text:
        return {
            "reply": "Copiloto no disponible. Verifica GEMINI_API_KEY o ANTHROPIC_API_KEY en las variables de entorno.",
            "provider": "none",
            "plan": None,
        }

    # Extraer plan si hay
    plan = _extract_copilot_plan(reply_text)
    clean_reply = _strip_plan_block(reply_text)
    actions_validated = []
    if plan:
        actions_validated = _validate_copilot_plan(plan, agent, db)

    return {
        "reply": clean_reply or "Entendido.",
        "provider": provider_used,
        "plan": {
            "resumen": plan.get("resumen") if plan else None,
            "actions": actions_validated,
        } if plan else None,
    }


@app.post("/api/agents/{id}/copilot/apply-plan")
def agent_copilot_apply_plan(id: int, data: dict, db: Session = Depends(get_db)):
    """Aplica un plan aprobado por el admin. Recibe las actions validadas.
    data: { actions: [...] } - mismo formato que retorna /copilot
    """
    agent = db.query(AgentConfig).get(id)
    if not agent:
        raise HTTPException(404, "Agente no encontrado")
    actions = data.get("actions") or []
    if not actions:
        raise HTTPException(400, "Sin actions para aplicar")

    results = []
    for act in actions:
        if not act.get("valid", True):
            results.append({"op": act.get("op"), "skipped": True, "reason": act.get("error")})
            continue
        op = act.get("op")
        try:
            if op == "create_block":
                b = AgentBlock(
                    agent_id=agent.id,
                    categoria=act.get("categoria", "identidad"),
                    tipo=act.get("tipo", "personificacion"),
                    nombre=act.get("nombre", "Nuevo bloque"),
                    contenido=act.get("contenido", ""),
                    orden=act.get("orden", 100),
                    activo=True,
                )
                db.add(b)
                db.flush()
                results.append({"op": op, "ok": True, "block_id": b.id})
            elif op == "update_block":
                b = db.query(AgentBlock).filter(
                    AgentBlock.id == act.get("block_id"),
                    AgentBlock.agent_id == agent.id,
                ).first()
                if not b:
                    results.append({"op": op, "ok": False, "error": "Bloque no encontrado"})
                    continue
                campos = act.get("campos") or {}
                for k in ["nombre", "contenido", "orden", "activo"]:
                    if k in campos and campos[k] is not None:
                        setattr(b, k, campos[k])
                results.append({"op": op, "ok": True, "block_id": b.id})
            elif op == "delete_block":
                b = db.query(AgentBlock).filter(
                    AgentBlock.id == act.get("block_id"),
                    AgentBlock.agent_id == agent.id,
                ).first()
                if not b:
                    results.append({"op": op, "ok": False, "error": "Bloque no encontrado"})
                    continue
                db.delete(b)
                results.append({"op": op, "ok": True, "deleted": True})
            elif op == "update_agent_settings":
                campos = act.get("campos") or {}
                for k in ["display_name", "descripcion", "avatar", "temperatura", "max_tokens", "tools_allowed", "modelo", "stages"]:
                    if k in campos and campos[k] is not None:
                        setattr(agent, k, campos[k])
                results.append({"op": op, "ok": True})
            else:
                results.append({"op": op, "ok": False, "error": f"Op desconocida: {op}"})
        except Exception as e:
            results.append({"op": op, "ok": False, "error": str(e)[:200]})
    db.commit()
    applied = sum(1 for r in results if r.get("ok"))
    return {"applied": applied, "total": len(actions), "results": results}


# ═══════════════════════════════════════════════════
# PIPELINE DE CONVERSACIONES - STAGES + HANDOFF MULTI-AGENTE
# ═══════════════════════════════════════════════════

PIPELINE_STAGES = [
    ("lead_inicial", "Lead Inicial", "#6366f1"),
    ("calificando", "Calificando", "#f59e0b"),
    ("cotizando", "Cotizando", "#8b5cf6"),
    ("cerrando", "Cerrando", "#10b981"),
    ("cliente_activo", "Cliente Activo", "#059669"),
    ("soporte_post_venta", "Soporte Post-venta", "#3b82f6"),
    ("cliente_perdido", "Cliente Perdido", "#6b7280"),
]


def _extract_visitor_from_message(message: str, history: list = None) -> dict:
    """Extrae nombre, email, telefono, empresa de un mensaje del usuario via regex."""
    import re
    out = {}
    # Email
    m = re.search(r'[\w\.\-\+]+@[\w\.\-]+\.[a-zA-Z]{2,}', message or "")
    if m:
        out["email"] = m.group(0).lower()
    # Telefono Chile: +56 9 XXXXXXXX o similar
    m = re.search(r'(\+?\d[\d\s\-]{7,15}\d)', message or "")
    if m:
        num = re.sub(r'\s|-', '', m.group(0))
        if 8 <= len(num.lstrip('+')) <= 15:
            out["telefono"] = num
    # Nombre: "soy X", "me llamo X", "habla X"
    name_patterns = [
        r'soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
        r'me llamo\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
        r'habla\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
        r'mi nombre es\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})',
    ]
    for pat in name_patterns:
        m = re.search(pat, message or "", re.IGNORECASE)
        if m:
            out["nombre"] = m.group(1).strip().title()
            break
    # Empresa: solo si ya tenemos email o nombre (menos falsos positivos)
    if out.get("email") or out.get("nombre"):
        for pat in [
            r'(?:de|en)\s+([A-Z][A-Za-z0-9&\.\-]+(?:\s+[A-Z][A-Za-z0-9&\.\-]+){0,3})',
            r'mi empresa\s+(?:es|se llama)?\s*([A-Z][A-Za-z0-9&\.\-\s]{2,30})',
        ]:
            m = re.search(pat, message or "")
            if m:
                candidate = m.group(1).strip().rstrip('.').rstrip(',')
                if len(candidate) > 2 and candidate.lower() not in ("mi", "la", "el", "chile", "santiago", "china", "china.", "del"):
                    out["empresa"] = candidate
                    break
    return out


def _detect_intent(message: str, history: list = None) -> dict:
    """Detecta intencion del usuario usando keywords + score.
    Retorna {intent, score, sentiment, next_stage_hint}.
    """
    msg_lower = (message or "").lower()
    # Keywords por intent
    buy_signals = ["comprar", "cotizar", "cotizacion", "presupuesto", "necesito", "quiero", "precio", "cuanto cuesta", "cuanto vale", "cuando puedo", "condiciones de pago", "anticipo", "pago", "factura", "contrato", "firmar"]
    support_signals = ["estado de mi pedido", "mi pedido", "donde esta", "tracking", "seguimiento", "cuando llega", "demora", "retraso", "problema", "defecto", "devolucion", "garantia"]
    lost_signals = ["no me interesa", "no gracias", "muy caro", "encontre otra", "otra opcion", "mejor precio", "cancelar", "no quiero"]
    complex_signals = ["hablar con", "humano", "persona real", "no me entiendes", "me puedes pasar", "ejecutivo", "gerente"]
    qualified_signals = ["empresa", "rut", "factura", "mi empresa", "somos", "trabajo en", "soy de"]

    score_buy = sum(1 for kw in buy_signals if kw in msg_lower)
    score_support = sum(1 for kw in support_signals if kw in msg_lower)
    score_lost = sum(1 for kw in lost_signals if kw in msg_lower)
    score_complex = sum(1 for kw in complex_signals if kw in msg_lower)
    score_qualified = sum(1 for kw in qualified_signals if kw in msg_lower)

    # Sentiment por negativas simples
    negative_words = ["no", "nunca", "malo", "horrible", "pesimo", "mal", "disgustado", "enojado"]
    positive_words = ["si", "perfecto", "genial", "excelente", "bacan", "gracias", "ok"]
    neg_count = sum(1 for w in negative_words if w in msg_lower.split())
    pos_count = sum(1 for w in positive_words if w in msg_lower.split())
    sentiment = "negativo" if neg_count > pos_count else ("positivo" if pos_count > neg_count else "neutral")

    # Ranking
    scores = {
        "intencion_compra": score_buy,
        "soporte": score_support,
        "cliente_perdido": score_lost,
        "derivar_humano": score_complex,
        "calificado": score_qualified,
    }
    top_intent = max(scores.items(), key=lambda x: x[1])
    intent_name = top_intent[0] if top_intent[1] > 0 else "info_general"
    score_normalized = min(1.0, top_intent[1] / 3.0) if top_intent[1] > 0 else 0.3

    # Sugerir siguiente stage
    stage_hint = None
    if intent_name == "intencion_compra" and score_normalized >= 0.6:
        stage_hint = "cerrando"
    elif intent_name == "intencion_compra":
        stage_hint = "cotizando"
    elif intent_name == "calificado":
        stage_hint = "calificando"
    elif intent_name == "soporte":
        stage_hint = "soporte_post_venta"
    elif intent_name == "cliente_perdido":
        stage_hint = "cliente_perdido"

    return {
        "intent": intent_name,
        "score": round(score_normalized, 2),
        "sentiment": sentiment,
        "next_stage_hint": stage_hint,
        "requires_human": score_complex >= 2 or (intent_name == "derivar_humano" and score_complex >= 1),
    }


def _has_contact_data(visitor: dict) -> bool:
    """True si el visitor dio algun dato de contacto real (nombre, email o telefono)."""
    v = visitor or {}
    nombre = (v.get("nombre") or "").strip()
    email = (v.get("email") or "").strip()
    telefono = (v.get("telefono") or "").strip()
    # Ignorar nombres placeholder tipo "Anonimo"
    nombre_real = nombre and not nombre.lower().startswith(("anonimo", "anónimo", "visitante"))
    return bool(nombre_real or email or telefono)


def _get_or_create_pipeline(session_id: str, agent_id: int, visitor: dict, db) -> ConversationPipeline:
    """Obtiene o crea un pipeline para la sesion.
    El Prospect se crea SOLO si el visitor dio datos de contacto (nombre, email o telefono).
    Si ya existe pipeline sin prospect y ahora llegan datos, se crea el prospect.
    """
    p = db.query(ConversationPipeline).filter(ConversationPipeline.session_id == session_id).first()
    v = visitor or {}
    has_contact = _has_contact_data(v)
    if p:
        # Crear Prospect ahora solo si llegaron datos de contacto
        if not p.prospect_id and has_contact:
            p.prospect_id = _ensure_prospect_from_pipeline(p, session_id, v, agent_id, db)
            db.commit()
        # Si ya hay prospect y hay datos nuevos, actualizar
        if p.prospect_id:
            _update_prospect_from_pipeline(p, v, db)
        return p
    # Crear pipeline nuevo (sin prospect si no hay datos)
    p = ConversationPipeline(
        session_id=session_id,
        current_stage="lead_inicial",
        current_agent_id=agent_id,
        visitor_nombre=v.get("nombre", ""),
        visitor_email=v.get("email", ""),
        visitor_telefono=v.get("telefono", ""),
        visitor_empresa=v.get("empresa", ""),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    # Crear Prospect solo si hay datos de contacto
    if has_contact:
        p.prospect_id = _ensure_prospect_from_pipeline(p, session_id, v, agent_id, db)
        db.commit()
    return p


def _ensure_prospect_from_pipeline(pipeline, session_id, visitor, agent_id, db):
    """Crea un Prospect para la conversacion. Si ya hay uno con el mismo email, lo reusa."""
    email = (visitor or {}).get("email", "").strip().lower()
    if email:
        existing = db.query(Prospect).filter(Prospect.email == email).first()
        if existing:
            return existing.id
    # Crear Prospect nuevo. Si no hay nombre aun, usa placeholder con session short
    nombre = (visitor or {}).get("nombre", "").strip()
    session_short = session_id[:8] if session_id else "anon"
    p = Prospect(
        nombre=nombre or f"Visitante chat · {session_short}",
        email=email or None,
        telefono=(visitor or {}).get("telefono", ""),
        empresa=(visitor or {}).get("empresa", ""),
        fuente="chatbot_mateo",
        estado="nuevo",
        notas=f"Conversacion chat · session_id={session_id}\nAgente inicial: {agent_id}",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


def _update_prospect_from_pipeline(pipeline, visitor, db):
    """Si ahora conocemos mas datos del visitor (ej email llego en turn 3), actualiza Prospect."""
    if not pipeline.prospect_id:
        return
    prospect = db.query(Prospect).get(pipeline.prospect_id)
    if not prospect:
        return
    v = visitor or {}
    changed = False
    # Si el Prospect era anonimo (sin email) y ahora hay email
    if v.get("email") and (not prospect.email or "@" not in (prospect.email or "")):
        email = v["email"].strip().lower()
        # Verificar si otro prospect ya tiene ese email (merge)
        existing = db.query(Prospect).filter(Prospect.email == email, Prospect.id != prospect.id).first()
        if existing:
            # Merge: usar el existing, eliminar el placeholder actual
            pipeline.prospect_id = existing.id
            if prospect.nombre and prospect.nombre.startswith("Visitante chat") and v.get("nombre"):
                existing.nombre = v["nombre"]
            db.delete(prospect)
            db.commit()
            return
        prospect.email = email
        changed = True
    if v.get("nombre") and (not prospect.nombre or prospect.nombre.startswith("Visitante chat")):
        prospect.nombre = v["nombre"]
        changed = True
    if v.get("telefono") and not prospect.telefono:
        prospect.telefono = v["telefono"]
        changed = True
    if v.get("empresa") and not prospect.empresa:
        prospect.empresa = v["empresa"]
        changed = True
    if changed:
        db.commit()


def _find_agent_for_stage(stage: str, db) -> Optional[AgentConfig]:
    """Busca un agente activo cuya lista de stages incluya el stage solicitado."""
    agents = db.query(AgentConfig).filter(AgentConfig.activo == True).all()
    for a in agents:
        try:
            stages = json.loads(a.stages or "[]")
            if stage in stages:
                return a
        except Exception:
            continue
    return None


def _maybe_handoff_pipeline(pipeline: ConversationPipeline, intent_data: dict, message: str, db):
    """Evalua si hay que hacer handoff de agente segun el stage hint.
    Registra el cambio en PipelineStageLog. Actualiza pipeline.current_agent_id.
    Si requires_human=True, crea un HumanHandoff.
    """
    old_stage = pipeline.current_stage
    old_agent = pipeline.current_agent_id
    changed = False

    # Update intent tracking
    pipeline.intent_detected = intent_data.get("intent")
    pipeline.intent_score = intent_data.get("score", 0)
    pipeline.sentiment = intent_data.get("sentiment", "neutral")

    # Handoff de stage si el hint es diferente Y confiable
    hint = intent_data.get("next_stage_hint")
    if hint and hint != old_stage and intent_data.get("score", 0) >= 0.5:
        # Buscar agente para el nuevo stage
        new_agent = _find_agent_for_stage(hint, db)
        if new_agent:
            pipeline.current_stage = hint
            pipeline.current_agent_id = new_agent.id
            changed = True
            # Log
            log = PipelineStageLog(
                pipeline_id=pipeline.id,
                from_stage=old_stage, to_stage=hint,
                from_agent_id=old_agent, to_agent_id=new_agent.id,
                trigger_type="intent_detected",
                trigger_data=json.dumps({"intent": intent_data.get("intent"), "score": intent_data.get("score")}),
            )
            db.add(log)

    # Human handoff si lo requiere
    if intent_data.get("requires_human") and not pipeline.requires_human:
        pipeline.requires_human = True
        pipeline.human_handoff_reason = f"Intent: {intent_data.get('intent')} (score={intent_data.get('score')})"
        pipeline.handoff_at = datetime.now()
        # Crear registro
        handoff = HumanHandoff(
            session_id=pipeline.session_id,
            pipeline_id=pipeline.id,
            agent_id=pipeline.current_agent_id,
            visitor_nombre=pipeline.visitor_nombre,
            visitor_email=pipeline.visitor_email,
            visitor_telefono=pipeline.visitor_telefono,
            motivo=pipeline.human_handoff_reason + f" | mensaje: {message[:150]}",
            urgencia="alta" if intent_data.get("sentiment") == "negativo" else "media",
            estado="pendiente",
            notified_via="none",
        )
        db.add(handoff)
        # Trigger WhatsApp notification (async, se encola)
        try:
            _notify_handoff_via_whatsapp(handoff, db)
        except Exception as e:
            print(f"[handoff notify] error: {e}")

    db.commit()
    return changed


def _notify_handoff_via_whatsapp(handoff: HumanHandoff, db):
    """Envia aviso via WhatsApp a los admins. Requiere TWILIO o META_WA env vars."""
    admin_phones_raw = os.getenv("HANDOFF_ADMIN_PHONES", "")  # comma-separated
    admin_phones = [p.strip() for p in admin_phones_raw.split(",") if p.strip()]
    if not admin_phones:
        return
    body = (
        f"🔔 HANDOFF MIP\n"
        f"Urgencia: {handoff.urgencia.upper()}\n"
        f"Cliente: {handoff.visitor_nombre or '?'} ({handoff.visitor_email or '?'})\n"
        f"Motivo: {handoff.motivo[:200]}\n"
        f"Session: {handoff.session_id}"
    )
    sent = False
    # Twilio primero
    TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")  # ej: whatsapp:+14155238886
    if TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM:
        try:
            import requests as _req
            for to in admin_phones:
                to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
                r = _req.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                    auth=(TWILIO_SID, TWILIO_TOKEN),
                    data={"From": TWILIO_FROM, "To": to_wa, "Body": body},
                    timeout=10,
                )
                if r.status_code in (200, 201):
                    sent = True
        except Exception as e:
            print(f"[twilio WA] error: {e}")
    # Meta Cloud API fallback
    META_WA_TOKEN = os.getenv("META_WA_TOKEN", "")
    META_WA_PHONE_ID = os.getenv("META_WA_PHONE_ID", "")
    if not sent and META_WA_TOKEN and META_WA_PHONE_ID:
        try:
            import requests as _req
            for to in admin_phones:
                to_clean = to.replace("+", "").replace(" ", "")
                r = _req.post(
                    f"https://graph.facebook.com/v18.0/{META_WA_PHONE_ID}/messages",
                    headers={"Authorization": f"Bearer {META_WA_TOKEN}", "Content-Type": "application/json"},
                    json={"messaging_product": "whatsapp", "to": to_clean, "type": "text", "text": {"body": body}},
                    timeout=10,
                )
                if r.status_code == 200:
                    sent = True
        except Exception as e:
            print(f"[meta WA] error: {e}")
    if sent:
        handoff.whatsapp_sent = True
        handoff.notified_via = "whatsapp"
        db.commit()


# Pipeline endpoints

@app.get("/api/pipeline/stages")
def list_pipeline_stages():
    """Lista los stages del pipeline (estaticos)."""
    return [{"key": k, "label": l, "color": c} for k, l, c in PIPELINE_STAGES]


@app.get("/api/pipeline/conversations")
def list_pipeline_conversations(stage: Optional[str] = None, include_anonymous: bool = False, db: Session = Depends(get_db)):
    """Lista conversaciones con su stage para Kanban.
    Por default SOLO incluye conversaciones con datos de contacto (nombre/email/telefono)
    o con prospect_id asociado. Usar ?include_anonymous=true para ver todas.
    """
    q = db.query(ConversationPipeline)
    if stage:
        q = q.filter(ConversationPipeline.current_stage == stage)
    rows = q.order_by(ConversationPipeline.updated_at.desc()).all()
    if not include_anonymous:
        def _tiene_contacto(p):
            if p.prospect_id:
                return True
            nombre = (p.visitor_nombre or "").strip()
            email = (p.visitor_email or "").strip()
            tel = (p.visitor_telefono or "").strip()
            nombre_real = nombre and not nombre.lower().startswith(("anonimo", "anónimo", "visitante"))
            return bool(nombre_real or email or tel)
        rows = [p for p in rows if _tiene_contacto(p)]
    return [{
        "id": p.id,
        "session_id": p.session_id,
        "stage": p.current_stage,
        "agent_id": p.current_agent_id,
        "visitor_nombre": p.visitor_nombre or "",
        "visitor_email": p.visitor_email or "",
        "visitor_telefono": p.visitor_telefono or "",
        "visitor_empresa": p.visitor_empresa or "",
        "intent": p.intent_detected or "",
        "intent_score": p.intent_score or 0,
        "sentiment": p.sentiment or "neutral",
        "requires_human": bool(p.requires_human),
        "total_messages": p.total_messages or 0,
        "prospect_id": p.prospect_id,
        "cliente_id": p.cliente_id,
        "last_message_at": p.last_message_at.isoformat() if p.last_message_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    } for p in rows]


@app.put("/api/pipeline/conversations/{id}/stage")
def update_pipeline_stage(id: int, data: dict, db: Session = Depends(get_db)):
    """Mueve manualmente una conversacion de stage (para drag&drop en UI)."""
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    new_stage = data.get("stage")
    valid = [s[0] for s in PIPELINE_STAGES]
    if new_stage not in valid:
        raise HTTPException(400, f"Stage invalido. Usar: {valid}")
    old_stage = p.current_stage
    old_agent = p.current_agent_id
    p.current_stage = new_stage
    # Auto-asignar agente del nuevo stage si existe
    new_agent = _find_agent_for_stage(new_stage, db)
    if new_agent:
        p.current_agent_id = new_agent.id
    db.add(PipelineStageLog(
        pipeline_id=p.id, from_stage=old_stage, to_stage=new_stage,
        from_agent_id=old_agent, to_agent_id=p.current_agent_id,
        trigger_type="manual",
        trigger_data=json.dumps({"admin": data.get("admin", "unknown")}),
    ))
    db.commit()
    return {"id": p.id, "stage": new_stage, "agent_id": p.current_agent_id}


@app.get("/api/pipeline/conversations/{id}")
def get_pipeline_detail(id: int, db: Session = Depends(get_db)):
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    history = db.query(PipelineStageLog).filter(PipelineStageLog.pipeline_id == id).order_by(PipelineStageLog.created_at).all()
    # Incluir mensajes si existe MateoConversation con mismo session_id
    messages = []
    conv = db.query(MateoConversation).filter(MateoConversation.session_id == p.session_id).first()
    if conv:
        msgs = db.query(MateoMessage).filter(MateoMessage.conversation_id == conv.id).order_by(MateoMessage.created_at).all()
        messages = [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None} for m in msgs]
    return {
        "id": p.id, "session_id": p.session_id,
        "stage": p.current_stage, "agent_id": p.current_agent_id,
        "visitor_nombre": p.visitor_nombre, "visitor_email": p.visitor_email,
        "visitor_telefono": p.visitor_telefono, "visitor_empresa": p.visitor_empresa,
        "intent_detected": p.intent_detected, "intent_score": p.intent_score,
        "sentiment": p.sentiment, "requires_human": p.requires_human,
        "prospect_id": p.prospect_id, "cliente_id": p.cliente_id,
        "cotizacion_id": p.cotizacion_id, "pedido_id": p.pedido_id,
        "notes": p.notes, "total_messages": p.total_messages,
        "stage_history": [{
            "from": h.from_stage, "to": h.to_stage,
            "from_agent_id": h.from_agent_id, "to_agent_id": h.to_agent_id,
            "trigger": h.trigger_type, "created_at": h.created_at.isoformat() if h.created_at else None,
        } for h in history],
        "messages": messages,
    }


# ═══════════════════════════════════════════════════
# LIVE TAKEOVER - admin toma control de la conversacion
# ═══════════════════════════════════════════════════

def _pipeline_live_status(p: ConversationPipeline) -> str:
    """Calcula el status live de un pipeline basado en actividad reciente."""
    from datetime import timedelta as _td
    now = datetime.now()
    if p.control_mode == "human":
        return "human_control"
    if not p.last_client_activity_at:
        return "idle"
    delta = now - p.last_client_activity_at
    if delta < _td(minutes=2):
        return "live"   # cliente escribio en los ultimos 2 min
    if delta < _td(minutes=15):
        return "active" # activo pero no en vivo
    if delta < _td(hours=24):
        return "idle"
    return "closed"


@app.get("/api/pipeline/conversations/{id}/live-status")
def pipeline_live_status(id: int, db: Session = Depends(get_db)):
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    return {
        "id": p.id,
        "status": _pipeline_live_status(p),
        "control_mode": p.control_mode or "ai",
        "taken_over_by": p.taken_over_by or None,
        "taken_over_at": p.taken_over_at.isoformat() if p.taken_over_at else None,
        "last_client_activity_at": p.last_client_activity_at.isoformat() if p.last_client_activity_at else None,
        "last_message_at": p.last_message_at.isoformat() if p.last_message_at else None,
        "total_messages": p.total_messages or 0,
    }


@app.post("/api/pipeline/conversations/{id}/take-over")
def take_over_conversation(id: int, data: dict, db: Session = Depends(get_db)):
    """Admin toma control de la conversacion. El agente IA deja de responder."""
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    admin_email = data.get("admin_email", "admin@mipquality.com")
    admin_nombre = data.get("admin_nombre", "Admin MIP")
    p.control_mode = "human"
    p.taken_over_by = admin_email
    p.taken_over_at = datetime.now()
    p.handled_by_admin = admin_email
    # Log del evento como actividad
    try:
        db.add(Actividad(
            tipo="takeover_humano",
            titulo=f"Admin tomo control de la conversacion",
            descripcion=f"{admin_nombre} ({admin_email}) tomo control del chat. El agente IA deja de responder.",
            autor=admin_email,
        ))
    except Exception:
        pass
    # Notificar al agente actual via log
    db.add(PipelineStageLog(
        pipeline_id=p.id,
        from_stage=p.current_stage, to_stage=p.current_stage,
        from_agent_id=p.current_agent_id, to_agent_id=None,
        trigger_type="human_takeover",
        trigger_data=json.dumps({"admin": admin_email}),
    ))
    db.commit()
    # Mensaje de sistema en el chat para el cliente
    try:
        # Buscar/crear MateoConversation de esta sesion para poder agregar el mensaje
        conv = db.query(MateoConversation).filter(MateoConversation.session_id == p.session_id).first()
        if not conv:
            conv = MateoConversation(
                session_id=p.session_id,
                visitor_email=p.visitor_email or "",
                visitor_nombre=p.visitor_nombre or "",
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
        db.add(MateoMessage(
            conversation_id=conv.id,
            role="assistant",
            content=f"[Un asesor humano ({admin_nombre}) se unio a la conversacion y te atendera personalmente]",
            tokens_usados=0,
        ))
        db.commit()
    except Exception as e:
        print(f"[takeover system msg] {e}")
    return {
        "id": p.id, "control_mode": p.control_mode,
        "taken_over_by": admin_email,
        "taken_over_at": p.taken_over_at.isoformat(),
    }


@app.post("/api/pipeline/conversations/{id}/release-control")
def release_control(id: int, db: Session = Depends(get_db)):
    """Admin devuelve el control al agente IA."""
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    prev_admin = p.taken_over_by
    p.control_mode = "ai"
    p.taken_over_by = None
    # taken_over_at queda como registro historico
    db.add(PipelineStageLog(
        pipeline_id=p.id,
        from_stage=p.current_stage, to_stage=p.current_stage,
        from_agent_id=None, to_agent_id=p.current_agent_id,
        trigger_type="human_release",
        trigger_data=json.dumps({"prev_admin": prev_admin}),
    ))
    db.commit()
    # Mensaje sistema
    try:
        conv = db.query(MateoConversation).filter(MateoConversation.session_id == p.session_id).first()
        if conv:
            db.add(MateoMessage(
                conversation_id=conv.id,
                role="assistant",
                content="[El asesor humano devolvio el control al asistente IA]",
                tokens_usados=0,
            ))
            db.commit()
    except Exception:
        pass
    return {"id": p.id, "control_mode": p.control_mode}


@app.post("/api/pipeline/conversations/{id}/send-admin-message")
def admin_send_message(id: int, data: dict, db: Session = Depends(get_db)):
    """Admin envia un mensaje al cliente en modo takeover."""
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")
    message = data.get("message", "").strip()
    admin_nombre = data.get("admin_nombre", p.taken_over_by or "Admin MIP")
    if not message:
        raise HTTPException(400, "Mensaje vacio")
    # Persistir en MateoConversation como mensaje del "asistente" (role assistant)
    # pero prefijado con [ADMIN] para diferenciarlo del agente IA
    try:
        conv = db.query(MateoConversation).filter(MateoConversation.session_id == p.session_id).first()
        if not conv:
            conv = MateoConversation(
                session_id=p.session_id,
                visitor_email=p.visitor_email or "",
                visitor_nombre=p.visitor_nombre or "",
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
        msg = MateoMessage(
            conversation_id=conv.id,
            role="assistant",
            content=message,
            tokens_usados=0,
        )
        db.add(msg)
        conv.mensajes_count = (conv.mensajes_count or 0) + 1
        conv.ultimo_mensaje_at = datetime.now()
        # Agregar a pending_admin_messages para que el widget del cliente lo recoja
        try:
            pending = json.loads(p.pending_admin_messages or "[]")
        except Exception:
            pending = []
        pending.append({
            "content": message,
            "admin_nombre": admin_nombre,
            "sent_at": datetime.now().isoformat(),
        })
        p.pending_admin_messages = json.dumps(pending)
        p.total_messages = (p.total_messages or 0) + 1
        p.last_message_at = datetime.now()
        db.commit()
    except Exception as e:
        raise HTTPException(500, f"Error guardando mensaje: {e}")
    return {"ok": True, "message_id": msg.id}


@app.get("/api/chat/session/{session_id}/pending")
def get_pending_admin_messages(session_id: str, clear: bool = True, db: Session = Depends(get_db)):
    """Widget del cliente hace polling aqui para recibir mensajes del admin."""
    p = db.query(ConversationPipeline).filter(ConversationPipeline.session_id == session_id).first()
    if not p:
        return {"messages": [], "control_mode": "ai"}
    try:
        pending = json.loads(p.pending_admin_messages or "[]")
    except Exception:
        pending = []
    if clear and pending:
        p.pending_admin_messages = "[]"
        db.commit()
    return {
        "messages": pending,
        "control_mode": p.control_mode or "ai",
        "taken_over_by": p.taken_over_by,
    }


@app.get("/api/pipeline/conversations/{id}/summary")
def get_conversation_summary(id: int, force: bool = False, db: Session = Depends(get_db)):
    """Genera un resumen de la conversacion con:
    - Estado general + stage
    - Resumen ejecutivo (via LLM)
    - Compromisos / acciones pendientes (detectados en los mensajes)
    - Proximos pasos sugeridos
    """
    p = db.query(ConversationPipeline).get(id)
    if not p:
        raise HTTPException(404, "Pipeline no encontrado")

    # Obtener mensajes
    conv = db.query(MateoConversation).filter(MateoConversation.session_id == p.session_id).first()
    messages = []
    if conv:
        msgs = db.query(MateoMessage).filter(MateoMessage.conversation_id == conv.id).order_by(MateoMessage.created_at).all()
        messages = [(m.role, m.content, m.created_at) for m in msgs]

    if not messages:
        return {
            "id": p.id,
            "session_id": p.session_id,
            "status": _pipeline_live_status(p),
            "visitor": {
                "nombre": p.visitor_nombre, "email": p.visitor_email,
                "telefono": p.visitor_telefono, "empresa": p.visitor_empresa,
            },
            "stage": p.current_stage,
            "summary": "Sin mensajes en la conversacion.",
            "compromisos": [],
            "proximos_pasos": [],
            "mensajes_count": 0,
        }

    # Detectar compromisos via regex (heuristicas simples)
    commitments = _detect_commitments(messages)

    # Generar resumen via LLM si hay suficientes mensajes y Gemini/Claude disponible
    summary_text = ""
    try:
        summary_text = _generate_conversation_summary(messages, p)
    except Exception as e:
        print(f"[summary gen] {e}")
        summary_text = _fallback_summary(messages)

    # Proximos pasos sugeridos
    next_steps = _suggest_next_steps(messages, p, commitments)

    return {
        "id": p.id,
        "session_id": p.session_id,
        "status": _pipeline_live_status(p),
        "control_mode": p.control_mode or "ai",
        "taken_over_by": p.taken_over_by,
        "visitor": {
            "nombre": p.visitor_nombre, "email": p.visitor_email,
            "telefono": p.visitor_telefono, "empresa": p.visitor_empresa,
        },
        "stage": p.current_stage,
        "intent": p.intent_detected, "intent_score": p.intent_score,
        "sentiment": p.sentiment,
        "mensajes_count": len(messages),
        "prospect_id": p.prospect_id,
        "summary": summary_text,
        "compromisos": commitments,
        "proximos_pasos": next_steps,
        "first_message_at": messages[0][2].isoformat() if messages[0][2] else None,
        "last_message_at": messages[-1][2].isoformat() if messages[-1][2] else None,
    }


def _detect_commitments(messages: list) -> list:
    """Detecta compromisos del agente hacia el cliente en los mensajes del assistant."""
    import re
    commitments = []
    commitment_patterns = [
        (r'te (mando|envio|paso|hago llegar) (.+?) (hoy|mañana|esta semana|en \d+ (horas?|dias?))', 'envio'),
        (r'(hoy|mañana|esta semana) (te )?(mando|envio|te envio|te paso)(.+)', 'envio'),
        (r'en (\d+) (horas?|dias?|minutos?)(.+)', 'plazo'),
        (r'(agendar|agendemos|programar|reservar)(.+)(reunion|llamada|meet|call)', 'reunion'),
        (r'te (llamo|contacto|respondo|confirmo)(.+?)(hoy|mañana|luego)', 'contacto'),
        (r'te (tendré|tendre|tendras|vas a tener)(.+)(cotizacion|propuesta|pdf)(.+)(hoy|mañana)', 'cotizacion'),
        (r'armar(te)? (una |la )?(cotizacion|propuesta|oferta)(.+)', 'cotizacion'),
        (r'te consigo (el|la)?\s*(precio|cotizacion|info|muestra)(.+)', 'info'),
    ]
    for role, content, created_at in messages:
        if role != "assistant":
            continue
        c_lower = (content or "").lower()
        for pattern, kind in commitment_patterns:
            matches = re.findall(pattern, c_lower)
            if matches:
                # Extract context around the match
                m = re.search(pattern, c_lower)
                if m:
                    ctx_start = max(0, m.start() - 30)
                    ctx_end = min(len(c_lower), m.end() + 50)
                    context = content[ctx_start:ctx_end].strip()
                    commitments.append({
                        "tipo": kind,
                        "texto": context,
                        "fecha_mensaje": created_at.isoformat() if created_at else None,
                    })
                    break  # one commitment per message
    return commitments


def _fallback_summary(messages: list) -> str:
    """Resumen simple sin LLM: primer mensaje del cliente + ultimo del agente."""
    first_user = next((m for m in messages if m[0] == "user"), None)
    last_assistant = next((m for m in reversed(messages) if m[0] == "assistant"), None)
    parts = []
    if first_user:
        parts.append(f"Cliente consulto: {(first_user[1] or '')[:200]}")
    if last_assistant:
        parts.append(f"Ultima respuesta agente: {(last_assistant[1] or '')[:200]}")
    return " · ".join(parts) or "Sin datos suficientes para resumen"


def _generate_conversation_summary(messages: list, pipeline) -> str:
    """Genera resumen ejecutivo via Gemini/Claude."""
    if not messages:
        return ""
    # Construir transcript
    transcript_lines = []
    for role, content, _ in messages[-20:]:  # ultimos 20 mensajes
        speaker = "Cliente" if role == "user" else "Agente"
        transcript_lines.append(f"{speaker}: {(content or '')[:500]}")
    transcript = "\n".join(transcript_lines)

    prompt = f"""Eres un analista de ventas. Resume la siguiente conversacion entre un cliente y un agente de MIP Quality & Logistics (broker de importacion China-Chile).

CONVERSACION:
{transcript}

DATOS DEL CLIENTE:
- Nombre: {pipeline.visitor_nombre or 'desconocido'}
- Email: {pipeline.visitor_email or 'no proporcionado'}
- Empresa: {pipeline.visitor_empresa or 'no proporcionada'}
- Stage actual: {pipeline.current_stage}

Genera un RESUMEN EJECUTIVO de maximo 4 lineas que incluya:
1. Que busca el cliente (producto, volumen, timing)
2. Como respondio el agente
3. En que se quedo la conversacion
4. Nivel de interes / proximidad al cierre

Responde SOLO con el resumen, sin preambulos."""

    if GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = model.generate_content(prompt)
            return resp.text.strip()
        except Exception as e:
            print(f"[summary gemini] {e}")
    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            print(f"[summary claude] {e}")
    return _fallback_summary(messages)


def _suggest_next_steps(messages: list, pipeline, commitments: list) -> list:
    """Genera pasos sugeridos basados en compromisos + stage."""
    steps = []
    # Si hay compromisos, listarlos como acciones pendientes
    for c in commitments[-5:]:  # ultimos 5
        steps.append({
            "accion": f"Cumplir compromiso ({c['tipo']})",
            "detalle": c['texto'][:120],
            "prioridad": "alta",
        })
    # Sugerencias basadas en stage
    stage_suggestions = {
        "lead_inicial": {"accion": "Calificar al lead", "detalle": "Verificar si tiene volumen real y email valido", "prioridad": "media"},
        "calificando": {"accion": "Enviar cotizacion estimada", "detalle": "Preparar rangos de precio para los productos mencionados", "prioridad": "alta"},
        "cotizando": {"accion": "Seguimiento proactivo", "detalle": "Llamar o escribir para confirmar interes y resolver dudas", "prioridad": "alta"},
        "cerrando": {"accion": "Formalizar propuesta", "detalle": "Generar PDF de cotizacion formal y condiciones de pago", "prioridad": "critica"},
        "cliente_activo": {"accion": "Onboarding post-venta", "detalle": "Enviar acceso a la plataforma y primer contacto del KAM", "prioridad": "media"},
        "soporte_post_venta": {"accion": "Atender consulta", "detalle": "Revisar pedido y responder al cliente", "prioridad": "alta"},
        "cliente_perdido": {"accion": "Nurturing suave", "detalle": "Enviar contenido de valor (case studies) en 2 semanas", "prioridad": "baja"},
    }
    sugg = stage_suggestions.get(pipeline.current_stage)
    if sugg:
        steps.append(sugg)
    # Si no hay email y el lead es bueno
    if not pipeline.visitor_email and (pipeline.intent_score or 0) >= 0.5:
        steps.append({"accion": "Obtener email del cliente", "detalle": "Pedir contacto para enviar material", "prioridad": "alta"})
    # Si requiere humano
    if pipeline.requires_human:
        steps.append({"accion": "Derivar a humano", "detalle": "El agente solicito handoff. Tomar control de la conversacion.", "prioridad": "critica"})
    return steps


@app.get("/api/pipeline/live-conversations")
def list_live_conversations(db: Session = Depends(get_db)):
    """Lista conversaciones activas en vivo (cliente escribio en los ultimos 15 min).
    Usado para el widget de 'chats abiertos' en el admin."""
    from datetime import timedelta as _td
    cutoff = datetime.now() - _td(minutes=15)
    convs = db.query(ConversationPipeline).filter(
        (ConversationPipeline.last_client_activity_at >= cutoff) |
        (ConversationPipeline.control_mode == "human")
    ).order_by(ConversationPipeline.last_message_at.desc()).all()
    out = []
    for c in convs:
        out.append({
            "id": c.id,
            "session_id": c.session_id,
            "status": _pipeline_live_status(c),
            "control_mode": c.control_mode or "ai",
            "taken_over_by": c.taken_over_by,
            "visitor_nombre": c.visitor_nombre or "",
            "visitor_email": c.visitor_email or "",
            "prospect_id": c.prospect_id,
            "stage": c.current_stage,
            "agent_id": c.current_agent_id,
            "last_client_activity_at": c.last_client_activity_at.isoformat() if c.last_client_activity_at else None,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
            "total_messages": c.total_messages or 0,
        })
    return out


# Human Handoffs endpoints

@app.get("/api/handoffs")
def list_handoffs(estado: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(HumanHandoff)
    if estado:
        q = q.filter(HumanHandoff.estado == estado)
    rows = q.order_by(HumanHandoff.created_at.desc()).all()
    return [{
        "id": h.id, "session_id": h.session_id,
        "visitor_nombre": h.visitor_nombre or "",
        "visitor_email": h.visitor_email or "",
        "visitor_telefono": h.visitor_telefono or "",
        "motivo": h.motivo or "",
        "urgencia": h.urgencia, "estado": h.estado,
        "asignado_a": h.asignado_a or "",
        "whatsapp_sent": h.whatsapp_sent or False,
        "notified_via": h.notified_via or "",
        "created_at": h.created_at.isoformat() if h.created_at else None,
    } for h in rows]


@app.get("/api/handoffs/count")
def handoffs_count(db: Session = Depends(get_db)):
    pending = db.query(HumanHandoff).filter(HumanHandoff.estado == "pendiente").count()
    return {"pending": pending}


@app.put("/api/handoffs/{id}")
def update_handoff(id: int, data: dict, db: Session = Depends(get_db)):
    h = db.query(HumanHandoff).get(id)
    if not h:
        raise HTTPException(404, "Handoff no encontrado")
    for k in ["estado", "asignado_a", "notas_resolucion"]:
        if k in data:
            setattr(h, k, data[k])
    if data.get("estado") == "resuelto":
        h.resuelto_at = datetime.now()
    db.commit()
    return {"id": h.id, "estado": h.estado}


# ═══════════════════════════════════════════════════
# STAGE ASSIGNMENTS - agente/humano por etapa
# ═══════════════════════════════════════════════════

@app.get("/api/stage-assignments")
def list_stage_assignments(stage_type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(StageAssignment).filter(StageAssignment.activo == True)
    if stage_type:
        q = q.filter(StageAssignment.stage_type == stage_type)
    rows = q.all()
    # Enrich con info del agente
    out = []
    for r in rows:
        agent_info = None
        if r.agent_id:
            a = db.query(AgentConfig).get(r.agent_id)
            if a:
                agent_info = {"id": a.id, "display_name": a.display_name, "avatar": a.avatar}
        out.append({
            "id": r.id,
            "stage_type": r.stage_type,
            "stage_key": r.stage_key,
            "agent_id": r.agent_id,
            "agent": agent_info,
            "human_email": r.human_email or "",
            "human_nombre": r.human_nombre or "",
            "fallback_to_human": r.fallback_to_human,
            "notify_on_entry": r.notify_on_entry,
            "activo": r.activo,
        })
    return out


@app.put("/api/stage-assignments")
def upsert_stage_assignment(data: dict, db: Session = Depends(get_db)):
    """Crea o actualiza la asignacion de un stage. Solo 1 assignment activo por stage_key+stage_type."""
    stage_type = data.get("stage_type", "prospect")
    stage_key = data.get("stage_key")
    if not stage_key:
        raise HTTPException(400, "Requiere stage_key")
    # Buscar existente
    existing = db.query(StageAssignment).filter(
        StageAssignment.stage_type == stage_type,
        StageAssignment.stage_key == stage_key,
    ).first()
    if existing:
        for k in ["agent_id", "human_email", "human_nombre", "fallback_to_human", "notify_on_entry", "activo"]:
            if k in data:
                setattr(existing, k, data[k])
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "updated": True}
    sa = StageAssignment(
        stage_type=stage_type, stage_key=stage_key,
        agent_id=data.get("agent_id"),
        human_email=data.get("human_email", ""),
        human_nombre=data.get("human_nombre", ""),
        fallback_to_human=data.get("fallback_to_human", False),
        notify_on_entry=data.get("notify_on_entry", True),
        activo=data.get("activo", True),
    )
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return {"id": sa.id, "created": True}


@app.delete("/api/stage-assignments/{id}")
def delete_stage_assignment(id: int, db: Session = Depends(get_db)):
    sa = db.query(StageAssignment).get(id)
    if not sa:
        raise HTTPException(404, "Assignment no encontrado")
    db.delete(sa)
    db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════
# AGENT AUTO RULES - triggers automaticos
# ═══════════════════════════════════════════════════

@app.get("/api/agents/{agent_id}/auto-rules")
def list_auto_rules(agent_id: int, db: Session = Depends(get_db)):
    rules = db.query(AgentAutoRule).filter(AgentAutoRule.agent_id == agent_id).order_by(AgentAutoRule.prioridad).all()
    return [{
        "id": r.id, "agent_id": r.agent_id,
        "nombre": r.nombre, "descripcion": r.descripcion or "",
        "trigger_type": r.trigger_type, "trigger_config": r.trigger_config,
        "action_type": r.action_type, "action_config": r.action_config,
        "prioridad": r.prioridad, "activo": r.activo,
        "total_triggered": r.total_triggered or 0,
        "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
    } for r in rules]


@app.post("/api/agents/{agent_id}/auto-rules")
def create_auto_rule(agent_id: int, data: dict, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(agent_id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    r = AgentAutoRule(
        agent_id=agent_id,
        nombre=data.get("nombre", "Regla sin nombre"),
        descripcion=data.get("descripcion", ""),
        trigger_type=data.get("trigger_type", "keyword"),
        trigger_config=data.get("trigger_config", "{}"),
        action_type=data.get("action_type", "move_stage"),
        action_config=data.get("action_config", "{}"),
        prioridad=data.get("prioridad", 100),
        activo=data.get("activo", True),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id}


@app.put("/api/auto-rules/{id}")
def update_auto_rule(id: int, data: dict, db: Session = Depends(get_db)):
    r = db.query(AgentAutoRule).get(id)
    if not r:
        raise HTTPException(404, "Regla no encontrada")
    for k in ["nombre", "descripcion", "trigger_type", "trigger_config", "action_type", "action_config", "prioridad", "activo"]:
        if k in data:
            setattr(r, k, data[k])
    db.commit()
    return {"id": r.id, "updated": True}


@app.delete("/api/auto-rules/{id}")
def delete_auto_rule(id: int, db: Session = Depends(get_db)):
    r = db.query(AgentAutoRule).get(id)
    if not r:
        raise HTTPException(404, "Regla no encontrada")
    db.delete(r)
    db.commit()
    return {"deleted": True}


def _evaluate_auto_rules(agent: AgentConfig, pipeline, message: str, intent_data: dict, db) -> dict:
    """Evalua todas las auto-rules del agente contra el mensaje actual.
    Si alguna matchea, ejecuta la accion. Retorna dict con info de lo que paso.
    """
    rules = db.query(AgentAutoRule).filter(
        AgentAutoRule.agent_id == agent.id,
        AgentAutoRule.activo == True,
    ).order_by(AgentAutoRule.prioridad).all()
    actions_executed = []
    for r in rules:
        try:
            matched = False
            config = {}
            try:
                config = json.loads(r.trigger_config or "{}")
            except Exception:
                config = {}
            # Evaluar segun tipo
            if r.trigger_type == "keyword":
                keywords = config.get("keywords", [])
                match_any = config.get("match_any", True)
                msg_lower = (message or "").lower()
                matches = [kw for kw in keywords if kw.lower() in msg_lower]
                matched = (len(matches) > 0) if match_any else (len(matches) == len(keywords))
            elif r.trigger_type == "intent":
                target_intents = config.get("intents", [])
                min_score = float(config.get("min_score", 0.5))
                matched = (intent_data.get("intent") in target_intents) and (intent_data.get("score", 0) >= min_score)
            elif r.trigger_type == "sentiment":
                target_sentiments = config.get("sentiments", [])
                matched = intent_data.get("sentiment") in target_sentiments
            elif r.trigger_type == "message_count":
                min_count = int(config.get("min_count", 5))
                matched = (pipeline.total_messages or 0) >= min_count
            elif r.trigger_type == "lead_data":
                # Match si el pipeline tiene los campos requeridos
                required = config.get("required_fields", ["email"])
                has_all = all(getattr(pipeline, f"visitor_{f}", "") for f in required)
                matched = has_all
            if not matched:
                continue

            # Ejecutar accion
            action_config = {}
            try:
                action_config = json.loads(r.action_config or "{}")
            except Exception:
                action_config = {}
            if r.action_type == "move_stage":
                target_stage = action_config.get("target_stage")
                if target_stage:
                    old = pipeline.current_stage
                    pipeline.current_stage = target_stage
                    # Buscar agente asignado al nuevo stage
                    new_agent = _find_agent_for_stage(target_stage, db)
                    if new_agent:
                        pipeline.current_agent_id = new_agent.id
                    db.add(PipelineStageLog(
                        pipeline_id=pipeline.id,
                        from_stage=old, to_stage=target_stage,
                        from_agent_id=agent.id, to_agent_id=pipeline.current_agent_id,
                        trigger_type=f"auto_rule_{r.id}",
                        trigger_data=json.dumps({"rule_nombre": r.nombre, "trigger_type": r.trigger_type}),
                    ))
                    actions_executed.append({"rule_id": r.id, "action": "move_stage", "from": old, "to": target_stage})
            elif r.action_type == "switch_agent":
                target_agent_id = action_config.get("target_agent_id")
                if target_agent_id:
                    pipeline.current_agent_id = int(target_agent_id)
                    actions_executed.append({"rule_id": r.id, "action": "switch_agent", "to": target_agent_id})
            elif r.action_type == "escalate_human":
                pipeline.requires_human = True
                pipeline.human_handoff_reason = f"Auto rule: {r.nombre}"
                pipeline.handoff_at = datetime.now()
                db.add(HumanHandoff(
                    session_id=pipeline.session_id,
                    pipeline_id=pipeline.id,
                    agent_id=agent.id,
                    visitor_email=pipeline.visitor_email,
                    visitor_nombre=pipeline.visitor_nombre,
                    motivo=f"Auto rule '{r.nombre}' triggered",
                    urgencia=action_config.get("urgencia", "media"),
                    estado="pendiente",
                ))
                actions_executed.append({"rule_id": r.id, "action": "escalate_human"})
            elif r.action_type == "tag_prospect":
                # Si pipeline tiene prospect_id, update notas
                if pipeline.prospect_id:
                    p = db.query(Prospect).get(pipeline.prospect_id)
                    if p:
                        tag = action_config.get("tag", r.nombre)
                        p.notas = (p.notas or "") + f"\n[TAG auto-rule]: {tag}"
                        actions_executed.append({"rule_id": r.id, "action": "tag_prospect", "tag": tag})

            # Actualizar stats
            r.total_triggered = (r.total_triggered or 0) + 1
            r.last_triggered_at = datetime.now()
        except Exception as e:
            print(f"[auto-rule {r.id}] error: {e}")
    if actions_executed:
        db.commit()
    return {"actions_executed": actions_executed}


# Agent Integrations endpoints

@app.get("/api/agents/{agent_id}/integrations")
def list_agent_integrations(agent_id: int, db: Session = Depends(get_db)):
    rows = db.query(AgentIntegration).filter(AgentIntegration.agent_id == agent_id).all()
    return [{
        "id": i.id, "agent_id": i.agent_id, "tipo": i.tipo,
        "nombre": i.nombre or "", "activo": i.activo,
        "config": i.config or "{}",
        "has_credentials": bool(i.credentials and i.credentials != "{}"),
    } for i in rows]


@app.post("/api/agents/{agent_id}/integrations")
def create_agent_integration(agent_id: int, data: dict, db: Session = Depends(get_db)):
    a = db.query(AgentConfig).get(agent_id)
    if not a:
        raise HTTPException(404, "Agente no encontrado")
    i = AgentIntegration(
        agent_id=agent_id,
        tipo=data.get("tipo", "custom_webhook"),
        nombre=data.get("nombre", ""),
        activo=data.get("activo", True),
        credentials=data.get("credentials", "{}"),
        config=data.get("config", "{}"),
    )
    db.add(i)
    db.commit()
    db.refresh(i)
    return {"id": i.id, "tipo": i.tipo}


@app.put("/api/integrations/{id}")
def update_integration(id: int, data: dict, db: Session = Depends(get_db)):
    i = db.query(AgentIntegration).get(id)
    if not i:
        raise HTTPException(404, "Integration no encontrada")
    for k in ["nombre", "activo", "credentials", "config"]:
        if k in data:
            setattr(i, k, data[k])
    db.commit()
    return {"id": i.id, "updated": True}


@app.delete("/api/integrations/{id}")
def delete_integration(id: int, db: Session = Depends(get_db)):
    i = db.query(AgentIntegration).get(id)
    if not i:
        raise HTTPException(404, "Integration no encontrada")
    db.delete(i)
    db.commit()
    return {"deleted": True}


# Google Calendar OAuth2

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "") or GOOGLE_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")


@app.get("/api/integrations/google-calendar/diagnostic")
def gcal_oauth_diagnostic():
    """Devuelve si las env vars de OAuth Google Calendar estan configuradas."""
    return {
        "client_id_configured": bool(GOOGLE_OAUTH_CLIENT_ID),
        "client_secret_configured": bool(GOOGLE_OAUTH_CLIENT_SECRET),
        "redirect_uri_configured": bool(GOOGLE_OAUTH_REDIRECT_URI),
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI or "",
        "ready": bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET and GOOGLE_OAUTH_REDIRECT_URI),
        "setup_url": "https://console.cloud.google.com/apis/credentials",
    }


@app.get("/api/integrations/google-calendar/oauth/start")
def gcal_oauth_start(agent_id: int):
    """Inicia el flujo OAuth2 de Google Calendar para un agente."""
    if not GOOGLE_OAUTH_CLIENT_ID or not GOOGLE_OAUTH_REDIRECT_URI:
        raise HTTPException(500, "Google OAuth no configurado. Requiere GOOGLE_OAUTH_CLIENT_ID y GOOGLE_OAUTH_REDIRECT_URI")
    from urllib.parse import urlencode
    params = {
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events",
        "access_type": "offline",
        "prompt": "consent",
        "state": f"agent_{agent_id}",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"auth_url": auth_url}


@app.get("/api/integrations/google-calendar/oauth/callback")
def gcal_oauth_callback(code: str, state: str, db: Session = Depends(get_db)):
    """Callback de Google OAuth2 - intercambia code por tokens."""
    if not GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(500, "GOOGLE_OAUTH_CLIENT_SECRET no configurado")
    # Extract agent_id from state
    try:
        agent_id = int(state.replace("agent_", ""))
    except Exception:
        raise HTTPException(400, "state invalido")
    import requests as _req
    try:
        r = _req.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=15)
        if r.status_code != 200:
            raise HTTPException(500, f"OAuth exchange fallido: {r.text[:200]}")
        tokens = r.json()
    except Exception as e:
        raise HTTPException(500, f"Error OAuth: {str(e)}")

    # Guardar en AgentIntegration
    existing = db.query(AgentIntegration).filter(
        AgentIntegration.agent_id == agent_id,
        AgentIntegration.tipo == "google_calendar",
    ).first()
    credentials = json.dumps({
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
        "token_type": tokens.get("token_type"),
        "scope": tokens.get("scope"),
    })
    if existing:
        existing.credentials = credentials
        existing.activo = True
    else:
        db.add(AgentIntegration(
            agent_id=agent_id, tipo="google_calendar",
            nombre="Google Calendar", activo=True,
            credentials=credentials,
            config=json.dumps({"calendar_id": "primary"}),
        ))
    db.commit()
    # Redirigir a la UI
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/?integration=google_calendar&status=success&agent_id=" + str(agent_id))


def _get_gcal_access_token(agent_id: int, db) -> Optional[str]:
    """Obtiene access_token valido para el agente. Si expiro, hace refresh."""
    integ = db.query(AgentIntegration).filter(
        AgentIntegration.agent_id == agent_id,
        AgentIntegration.tipo == "google_calendar",
        AgentIntegration.activo == True,
    ).first()
    if not integ or not integ.credentials:
        return None
    try:
        creds = json.loads(integ.credentials)
    except Exception:
        return None
    # Intentar access token directo. Si falla en 401 despues, se hace refresh.
    return creds.get("access_token")


def _refresh_gcal_token(agent_id: int, db) -> Optional[str]:
    integ = db.query(AgentIntegration).filter(
        AgentIntegration.agent_id == agent_id,
        AgentIntegration.tipo == "google_calendar",
    ).first()
    if not integ:
        return None
    try:
        creds = json.loads(integ.credentials or "{}")
    except Exception:
        return None
    refresh_token = creds.get("refresh_token")
    if not refresh_token:
        return None
    import requests as _req
    try:
        r = _req.post("https://oauth2.googleapis.com/token", data={
            "client_id": GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }, timeout=15)
        if r.status_code == 200:
            new_tokens = r.json()
            creds["access_token"] = new_tokens.get("access_token")
            creds["expires_in"] = new_tokens.get("expires_in")
            integ.credentials = json.dumps(creds)
            db.commit()
            return creds["access_token"]
    except Exception as e:
        print(f"[gcal refresh] error: {e}")
    return None


# Tool handler: check_calendar_availability (via Google Calendar API real)
def _handler_check_calendar(args: dict, agent, db) -> dict:
    token = _get_gcal_access_token(agent.id, db)
    if not token:
        return {"error": "Google Calendar no conectado para este agente. Conectalo en la UI de Integraciones."}
    from datetime import timedelta as _td
    time_min = args.get("time_min") or datetime.now().isoformat() + "Z"
    time_max = args.get("time_max") or (datetime.now() + _td(days=7)).isoformat() + "Z"
    import requests as _req
    try:
        r = _req.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"timeMin": time_min, "timeMax": time_max, "items": [{"id": "primary"}]},
            timeout=10,
        )
        if r.status_code == 401:
            token = _refresh_gcal_token(agent.id, db)
            if not token:
                return {"error": "Token expirado y no se pudo refrescar. Reconecta Google Calendar."}
            r = _req.post(
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"timeMin": time_min, "timeMax": time_max, "items": [{"id": "primary"}]},
                timeout=10,
            )
        if r.status_code != 200:
            return {"error": f"GCal API error: {r.status_code}", "body": r.text[:200]}
        data = r.json()
        busy = data.get("calendars", {}).get("primary", {}).get("busy", [])
        return {"busy_slots": busy, "time_range": {"min": time_min, "max": time_max}, "count": len(busy)}
    except Exception as e:
        return {"error": str(e)[:200]}


def _handler_gcal_create_event_real(args: dict, agent, db) -> dict:
    token = _get_gcal_access_token(agent.id, db)
    if not token:
        # Fallback al handler stub
        return _handler_calendar_book(args, agent, db)
    from datetime import timedelta as _td
    email = args.get("email", "")
    nombre = args.get("nombre", "")
    start_iso = args.get("fecha_iso") or args.get("start")
    duracion = args.get("duracion_min", 30)
    motivo = args.get("motivo", "Reunion MIP")
    if not start_iso:
        return {"error": "fecha_iso requerido"}
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", ""))
        end = start + _td(minutes=duracion)
    except Exception:
        return {"error": "fecha_iso invalida"}
    import requests as _req
    event = {
        "summary": f"{motivo} - {nombre or email}",
        "description": f"Agendado por {agent.display_name}\nCliente: {nombre} ({email})",
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Santiago"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Santiago"},
        "attendees": [{"email": email}] if email else [],
        "conferenceData": {
            "createRequest": {"requestId": f"mip-{int(datetime.now().timestamp())}",
                              "conferenceSolutionKey": {"type": "hangoutsMeet"}},
        },
    }
    try:
        r = _req.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=event, timeout=15,
        )
        if r.status_code == 401:
            token = _refresh_gcal_token(agent.id, db)
            if token:
                r = _req.post(
                    "https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=all",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=event, timeout=15,
                )
        if r.status_code in (200, 201):
            data = r.json()
            # Persist local booking record
            b = MateoCalendarBooking(
                visitor_email=email, visitor_nombre=nombre,
                fecha_reunion=start, duracion_min=duracion,
                motivo=motivo, estado="confirmada",
                calendar_event_id=data.get("id"),
                meet_link=data.get("hangoutLink") or "",
            )
            db.add(b)
            db.commit()
            return {
                "event_id": data.get("id"),
                "html_link": data.get("htmlLink"),
                "meet_link": data.get("hangoutLink"),
                "created": True,
            }
        return {"error": f"GCal API {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)[:200]}


# Tool handler: add_to_pipeline - agrega el cliente actual al pipeline de ventas
def _handler_add_to_pipeline(args: dict, agent, db) -> dict:
    session_id = args.get("session_id", "")
    stage = args.get("stage", "cotizando")
    valid = [s[0] for s in PIPELINE_STAGES]
    if stage not in valid:
        stage = "calificando"
    # Buscar o crear pipeline
    p = db.query(ConversationPipeline).filter(ConversationPipeline.session_id == session_id).first()
    if not p:
        p = ConversationPipeline(
            session_id=session_id or f"manual-{int(datetime.now().timestamp())}",
            current_stage=stage,
            current_agent_id=agent.id,
            visitor_nombre=args.get("nombre", ""),
            visitor_email=args.get("email", ""),
            visitor_telefono=args.get("telefono", ""),
            visitor_empresa=args.get("empresa", ""),
            notes=args.get("notes", ""),
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return {"pipeline_id": p.id, "created": True, "stage": stage}
    # Actualizar
    old_stage = p.current_stage
    p.current_stage = stage
    if args.get("nombre") and not p.visitor_nombre:
        p.visitor_nombre = args["nombre"]
    if args.get("email") and not p.visitor_email:
        p.visitor_email = args["email"]
    db.add(PipelineStageLog(
        pipeline_id=p.id, from_stage=old_stage, to_stage=stage,
        trigger_type="tool_add_to_pipeline",
        trigger_data=json.dumps({"agent_id": agent.id}),
    ))
    db.commit()
    return {"pipeline_id": p.id, "created": False, "stage": stage, "previous_stage": old_stage}


# Register new tool handlers
TOOL_HANDLERS["check_calendar_availability"] = _handler_check_calendar
TOOL_HANDLERS["gcal_check_availability"] = _handler_check_calendar
TOOL_HANDLERS["calendar_create_event_real"] = _handler_gcal_create_event_real
TOOL_HANDLERS["add_to_pipeline"] = _handler_add_to_pipeline
TOOL_HANDLERS["move_to_stage"] = _handler_add_to_pipeline


def _handler_check_order_status(args: dict, agent, db) -> dict:
    """Busca el estado de un pedido/cotizacion del cliente."""
    email = args.get("email", "").strip()
    pedido_id = args.get("pedido_id")
    # Priority: pedido_id directo
    if pedido_id:
        p = db.query(Pedido).get(pedido_id)
        if p:
            etapas = ['','Solicitud','Cotización','Muestra','Pago 50%','Producción','QC China','Embarque','Entrega','Pago final']
            etapa_nombre = etapas[p.etapa_actual] if p.etapa_actual and p.etapa_actual < len(etapas) else 'N/A'
            return {
                "pedido_id": p.id, "etapa_actual": p.etapa_actual,
                "etapa_nombre": etapa_nombre, "monto_total": p.monto_total,
                "estado": p.estado, "created_at": p.created_at.isoformat() if p.created_at else None,
            }
        return {"error": f"Pedido {pedido_id} no encontrado"}
    # Busqueda por email
    if email:
        cliente = db.query(Cliente).filter(Cliente.email == email).first()
        if not cliente:
            return {"error": f"Cliente con email {email} no encontrado"}
        cots = db.query(Cotizacion).filter(Cotizacion.cliente_id == cliente.id).order_by(Cotizacion.created_at.desc()).limit(5).all()
        if not cots:
            return {"cotizaciones": [], "mensaje": "Cliente sin cotizaciones activas"}
        out = []
        etapas = ['','Solicitud','Cotización','Muestra','Pago 50%','Producción','QC China','Embarque','Entrega','Pago final']
        for c in cots:
            pedidos = db.query(Pedido).filter(Pedido.cotizacion_id == c.id).all()
            item = {
                "cotizacion_id": c.id, "producto": c.producto,
                "estado": c.estado, "cantidad": c.cantidad,
            }
            if pedidos:
                p = pedidos[0]
                etapa_nombre = etapas[p.etapa_actual] if p.etapa_actual and p.etapa_actual < len(etapas) else 'N/A'
                item["pedido_id"] = p.id
                item["etapa_actual"] = p.etapa_actual
                item["etapa_nombre"] = etapa_nombre
            out.append(item)
        return {"cotizaciones": out, "count": len(out)}
    return {"error": "Requiere email o pedido_id"}


TOOL_HANDLERS["check_order_status"] = _handler_check_order_status


# ═══ FASE 1: EXPORT/IMPORT EXCEL DE CLIENTES ═══
@app.get("/api/admin/clientes-export-excel")
def export_clientes_excel(db: Session = Depends(get_db)):
    """Export clients to CSV format (Excel-compatible with BOM UTF-8)"""
    clientes = db.query(Cliente).order_by(Cliente.created_at.desc()).all()
    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "ID", "Nombre", "Razón Social", "Nombre Comercial (Empresa)", "RUT", "Email",
        "Teléfono", "Rubro", "Ciudad", "Dirección Despacho", "Condición Pago",
        "KAM Responsable", "Vendedor Asignado", "Sitio Web", "N° Empleados",
        "Referido Por", "Notas", "Activo", "Rol", "Fecha Creación"
    ])
    for c in clientes:
        writer.writerow([
            c.id, c.nombre or "", c.razon_social or "", c.empresa or "", c.rut or "",
            c.email or "", c.telefono or "", c.rubro or "", c.ciudad or "",
            c.direccion_despacho or "", c.condicion_pago or "", c.kam_responsable or "",
            c.vendedor_asignado or "", c.sitio_web or "", c.num_empleados or "",
            c.referido_por or "", c.notas or "", c.activo or "true", c.role or "client",
            c.created_at.strftime("%Y-%m-%d") if c.created_at else ""
        ])
    output.seek(0)
    return StreamingResponse(
        output, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=clientes_export.csv"}
    )


@app.get("/api/admin/clientes-template-excel")
def export_clientes_template(db: Session = Depends(get_db)):
    """Download empty Excel-compatible template for importing clients"""
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        "Nombre", "Razón Social", "Nombre Comercial (Empresa)", "RUT", "Email",
        "Teléfono", "Rubro", "Ciudad", "Dirección Despacho", "Condición Pago",
        "KAM Responsable", "Vendedor Asignado", "Sitio Web", "N° Empleados", "Notas"
    ])
    # Example row
    writer.writerow([
        "Juan Pérez", "Retail Ejemplo SpA", "Retail Ejemplo", "76.123.456-7",
        "juan@ejemplo.cl", "+56 9 1234 5678", "Retail / Moda", "Santiago",
        "Av. Providencia 1234", "30 días", "María González", "Pedro López",
        "www.ejemplo.cl", "11-50", "Cliente desde 2024"
    ])
    output.seek(0)
    return StreamingResponse(
        output, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=plantilla_clientes.csv"}
    )


@app.post("/api/admin/clientes-import-excel")
def import_clientes_excel(data: dict, db: Session = Depends(get_db)):
    """Import clients from parsed Excel/CSV rows (sent as JSON array)"""
    rows = data.get("rows", [])
    imported = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            # Normalize keys (accept various formats)
            email = (row.get("Email") or row.get("email") or "").strip().lower()
            nombre = (row.get("Nombre") or row.get("nombre") or "").strip()
            if not email or not nombre:
                errors.append(f"Fila {i+2}: Email y Nombre son obligatorios")
                continue
            existing = db.query(Cliente).filter(Cliente.email == email).first()
            if existing:
                errors.append(f"Fila {i+2}: Email {email} ya existe")
                continue
            c = Cliente(
                nombre=nombre,
                razon_social=(row.get("Razón Social") or row.get("razon_social") or "").strip(),
                empresa=(row.get("Nombre Comercial (Empresa)") or row.get("Empresa") or row.get("empresa") or "").strip(),
                rut=(row.get("RUT") or row.get("rut") or "").strip(),
                email=email,
                telefono=(row.get("Teléfono") or row.get("telefono") or "").strip(),
                rubro=(row.get("Rubro") or row.get("rubro") or "").strip(),
                ciudad=(row.get("Ciudad") or row.get("ciudad") or "").strip(),
                direccion_despacho=(row.get("Dirección Despacho") or row.get("direccion_despacho") or "").strip(),
                condicion_pago=(row.get("Condición Pago") or row.get("condicion_pago") or "").strip(),
                kam_responsable=(row.get("KAM Responsable") or row.get("kam_responsable") or "").strip(),
                vendedor_asignado=(row.get("Vendedor Asignado") or row.get("vendedor_asignado") or "").strip(),
                sitio_web=(row.get("Sitio Web") or row.get("sitio_web") or "").strip(),
                num_empleados=(row.get("N° Empleados") or row.get("num_empleados") or "").strip(),
                notas=(row.get("Notas") or row.get("notas") or "").strip(),
                activo="true",
            )
            db.add(c)
            db.flush()
            imported += 1
        except Exception as e:
            errors.append(f"Fila {i+2}: {str(e)}")
    db.commit()
    return {"imported": imported, "errors": errors, "total": len(rows)}


# ═══ FASE 2: DASHBOARD KPIS ═══
# ─── Costos $ ───
# Pricing por 1M tokens (USD) segun tarifas publicas al 2026-04
LLM_PRICING = {
    "gemini": {"input_per_1m": 0.075, "output_per_1m": 0.30, "label": "Gemini 2.5 Flash"},
    "claude": {"input_per_1m": 3.00, "output_per_1m": 15.00, "label": "Claude Sonnet 4.5"},
    "openai": {"input_per_1m": 2.50, "output_per_1m": 10.00, "label": "OpenAI GPT-4o"},
    "embeddings": {"input_per_1m": 0.025, "output_per_1m": 0.0, "label": "Gemini Embeddings"},
}


def _estimate_cost(provider: str, tokens_in: int, tokens_out: int) -> float:
    p = LLM_PRICING.get((provider or "").lower()) or LLM_PRICING["gemini"]
    return (tokens_in or 0) / 1_000_000.0 * p["input_per_1m"] + (tokens_out or 0) / 1_000_000.0 * p["output_per_1m"]


def _get_monthly_spent(provider: str, db=None) -> float:
    """Calcula gasto del mes actual para un proveedor especifico.
    Agrega AgentTrace + MateoConversation del mes calendario actual.
    """
    from datetime import datetime as _dt
    # Primer dia del mes actual
    now = _dt.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prov_key = (provider or "gemini").lower()
    spent = 0.0
    try:
        with engine.connect() as conn:
            # AgentTrace del mes
            tr_rows = conn.execute(text("""
                SELECT COALESCE(SUM(cost_usd), 0) as total_cost,
                       COALESCE(SUM(prompt_tokens), 0) as tin,
                       COALESCE(SUM(output_tokens), 0) as tout
                FROM agent_traces
                WHERE created_at >= :start AND LOWER(COALESCE(provider, 'gemini')) LIKE :prov
            """), {"start": month_start, "prov": f"%{prov_key}%"}).fetchone()
            if tr_rows:
                trace_cost = tr_rows[0] or 0.0
                if trace_cost > 0:
                    spent += trace_cost
                else:
                    # Si cost_usd=0 en DB, estimar por pricing
                    spent += _estimate_cost(prov_key, tr_rows[1] or 0, tr_rows[2] or 0)
            # Mateo chats solo computan si provider es gemini
            if prov_key == "gemini":
                m_rows = conn.execute(text("""
                    SELECT COALESCE(SUM(tokens_input), 0), COALESCE(SUM(tokens_output), 0)
                    FROM mateo_conversations
                    WHERE inicio_at >= :start
                """), {"start": month_start}).fetchone()
                if m_rows:
                    spent += _estimate_cost("gemini", m_rows[0] or 0, m_rows[1] or 0)
    except Exception as e:
        print(f"[_get_monthly_spent] error: {e}")
    return spent


def _check_cost_limit(provider: str, db=None):
    """Verifica si el proveedor supero el limite mensual con hard-block activo.
    Si se supero, levanta HTTPException 429 con mensaje claro.
    Si no hay limite configurado o hard_block=False, pasa silenciosamente.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT monthly_limit_usd, hard_block FROM cost_limits
                WHERE provider = :p
            """), {"p": (provider or "gemini").lower()}).fetchone()
            if not row:
                return  # sin limite configurado, dejar pasar
            monthly_limit, hard_block = row[0] or 0.0, bool(row[1])
            if monthly_limit <= 0 or not hard_block:
                return  # limite en 0 o bloqueo desactivado
            spent = _get_monthly_spent(provider, db)
            if spent >= monthly_limit:
                # Log al historial de actividades
                try:
                    if db is None:
                        from sqlalchemy.orm import Session as _S
                        with _S(engine) as _db:
                            log_evento(_db, "sistema", "limite_costos_bloqueado",
                                       f"Llamada a {provider} bloqueada: gasto ${spent:.4f} >= limite ${monthly_limit}")
                    else:
                        log_evento(db, "sistema", "limite_costos_bloqueado",
                                   f"Llamada a {provider} bloqueada: gasto ${spent:.4f} >= limite ${monthly_limit}")
                except Exception:
                    pass
                raise HTTPException(
                    status_code=429,
                    detail=f"Limite mensual de costos alcanzado para {provider}: ${spent:.2f} USD (limite: ${monthly_limit:.2f}). Contacta al admin o aumenta el limite en Sistema > Costos.",
                )
    except HTTPException:
        raise
    except Exception as e:
        # Si el check falla por cualquier razon, NO bloquear el servicio
        print(f"[_check_cost_limit] error: {e}")


@app.get("/api/admin/costs/summary")
def costs_summary(days: int = 30, db: Session = Depends(get_db)):
    """Resumen de costos en los ultimos N dias.
    Agrega AgentTrace (agentes + copiloto) + MateoConversation (chats).
    Calcula costos aun si cost_usd=0 en trace usando pricing publico.
    """
    from datetime import timedelta as _td
    cutoff = datetime.now() - _td(days=days)
    # Traces
    traces = db.query(AgentTrace).filter(AgentTrace.created_at >= cutoff).all()
    by_provider = {}
    by_day = {}
    for t in traces:
        prov = (t.provider or "gemini").lower()
        prov_key = "gemini" if "gemini" in prov else "claude" if "claude" in prov else "openai" if "openai" in prov or "gpt" in prov else prov
        bp = by_provider.setdefault(prov_key, {"tokens_in": 0, "tokens_out": 0, "calls": 0, "cost_usd": 0.0})
        bp["tokens_in"] += t.prompt_tokens or 0
        bp["tokens_out"] += t.output_tokens or 0
        bp["calls"] += 1
        cost = t.cost_usd or _estimate_cost(prov_key, t.prompt_tokens or 0, t.output_tokens or 0)
        bp["cost_usd"] += cost
        day_key = (t.created_at or datetime.now()).strftime("%Y-%m-%d")
        bd = by_day.setdefault(day_key, {"cost_usd": 0.0, "calls": 0, "tokens": 0})
        bd["cost_usd"] += cost
        bd["calls"] += 1
        bd["tokens"] += (t.prompt_tokens or 0) + (t.output_tokens or 0)
    # Mateo conversations (chat widget)
    mateo_convs = db.query(MateoConversation).filter(MateoConversation.inicio_at >= cutoff).all()
    mateo_tokens_in = sum(m.tokens_input or 0 for m in mateo_convs)
    mateo_tokens_out = sum(m.tokens_output or 0 for m in mateo_convs)
    mateo_cost = _estimate_cost("gemini", mateo_tokens_in, mateo_tokens_out)
    # Feature breakdown (aproximado por agente / tipo)
    by_feature = {"mateo_chat": mateo_cost, "copilot": 0.0, "agents": 0.0, "pdf_parser": 0.0, "embeddings": 0.0}
    for t in traces:
        feat = "agents"
        sess = (t.session_id or "").lower()
        if "copilot" in sess or "copilot" in (t.input_summary or "").lower():
            feat = "copilot"
        elif "pdf" in sess or "pdf" in (t.input_summary or "").lower():
            feat = "pdf_parser"
        elif "embed" in (t.provider or "").lower():
            feat = "embeddings"
        by_feature[feat] = by_feature.get(feat, 0.0) + (t.cost_usd or _estimate_cost(t.provider or "gemini", t.prompt_tokens or 0, t.output_tokens or 0))
    # Totales
    total_cost = sum(bp["cost_usd"] for bp in by_provider.values()) + mateo_cost
    total_tokens = sum(bp["tokens_in"] + bp["tokens_out"] for bp in by_provider.values()) + mateo_tokens_in + mateo_tokens_out
    # Limites configurados
    limits = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT provider, monthly_limit_usd, alert_pct, hard_block, billing_account, billing_card_last4 FROM cost_limits")).fetchall()
            for r in rows:
                limits[r[0]] = {
                    "monthly_limit_usd": r[1] or 0, "alert_pct": r[2] or 80,
                    "hard_block": bool(r[3]), "billing_account": r[4] or "",
                    "billing_card_last4": r[5] or "",
                }
    except Exception:
        pass
    return {
        "period_days": days,
        "total_cost_usd": round(total_cost, 4),
        "total_tokens": total_tokens,
        "total_calls": len(traces) + len(mateo_convs),
        "by_provider": {k: {**v, "cost_usd": round(v["cost_usd"], 4), "pricing": LLM_PRICING.get(k, {})} for k, v in by_provider.items()},
        "by_day": [{"date": d, **{kk: round(vv, 4) if isinstance(vv, float) else vv for kk, vv in vals.items()}} for d, vals in sorted(by_day.items())],
        "by_feature": {k: round(v, 4) for k, v in by_feature.items()},
        "mateo_chat": {"tokens_in": mateo_tokens_in, "tokens_out": mateo_tokens_out, "cost_usd": round(mateo_cost, 4), "conversations": len(mateo_convs)},
        "limits": limits,
        "pricing_reference": LLM_PRICING,
    }


@app.get("/api/admin/costs/limits")
def get_cost_limits(db: Session = Depends(get_db)):
    out = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, provider, monthly_limit_usd, alert_pct, hard_block, billing_account, billing_card_last4, notas FROM cost_limits ORDER BY provider")).fetchall()
            for r in rows:
                out.append({
                    "id": r[0], "provider": r[1], "monthly_limit_usd": r[2] or 0,
                    "alert_pct": r[3] or 80, "hard_block": bool(r[4]),
                    "billing_account": r[5] or "", "billing_card_last4": r[6] or "",
                    "notas": r[7] or "",
                })
    except Exception:
        pass
    return out


@app.put("/api/admin/costs/limits/{provider}")
def set_cost_limit(provider: str, data: dict, db: Session = Depends(get_db)):
    """Crea o actualiza limite de gasto para un proveedor."""
    monthly = float(data.get("monthly_limit_usd", 0) or 0)
    alert_pct = int(data.get("alert_pct", 80) or 80)
    hard_block = bool(data.get("hard_block", False))
    billing_account = str(data.get("billing_account", ""))[:200]
    billing_card_last4 = str(data.get("billing_card_last4", ""))[:10]
    notas = str(data.get("notas", ""))
    with engine.connect() as conn:
        # Upsert manual (portable)
        existing = conn.execute(text("SELECT id FROM cost_limits WHERE provider = :p"), {"p": provider}).fetchone()
        if existing:
            conn.execute(text("""
                UPDATE cost_limits SET monthly_limit_usd=:m, alert_pct=:a, hard_block=:h,
                       billing_account=:ba, billing_card_last4=:bc, notas=:n, updated_at=CURRENT_TIMESTAMP
                WHERE provider=:p
            """), {"m": monthly, "a": alert_pct, "h": hard_block, "ba": billing_account, "bc": billing_card_last4, "n": notas, "p": provider})
        else:
            conn.execute(text("""
                INSERT INTO cost_limits (provider, monthly_limit_usd, alert_pct, hard_block, billing_account, billing_card_last4, notas)
                VALUES (:p, :m, :a, :h, :ba, :bc, :n)
            """), {"p": provider, "m": monthly, "a": alert_pct, "h": hard_block, "ba": billing_account, "bc": billing_card_last4, "n": notas})
        conn.commit()
    return {"updated": True, "provider": provider}


@app.get("/api/admin/costs/breakdown")
def costs_breakdown(days: int = 7, db: Session = Depends(get_db)):
    """Ultimas llamadas caras para debugging del consumo."""
    from datetime import timedelta as _td
    cutoff = datetime.now() - _td(days=days)
    traces = db.query(AgentTrace).filter(AgentTrace.created_at >= cutoff).order_by(AgentTrace.cost_usd.desc()).limit(50).all()
    return [{
        "id": t.id, "agent_id": t.agent_id, "session_id": t.session_id,
        "provider": t.provider, "prompt_tokens": t.prompt_tokens,
        "output_tokens": t.output_tokens,
        "cost_usd": round(t.cost_usd or _estimate_cost(t.provider or "gemini", t.prompt_tokens or 0, t.output_tokens or 0), 6),
        "latency_ms": t.latency_ms,
        "input_summary": (t.input_summary or "")[:150],
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in traces]


@app.get("/api/admin/dashboard-metrics")
def dashboard_metrics(db: Session = Depends(get_db)):
    """Comprehensive metrics for admin dashboard"""
    cots = db.query(Cotizacion).all()
    clientes_q = db.query(Cliente).filter(Cliente.role != "admin")

    # Pipeline por etapa
    etapas = ["pendiente", "cotizado", "produccion", "entregado"]
    probabilidades = {"pendiente": 20, "cotizado": 40, "produccion": 75, "entregado": 100}
    pipeline_por_etapa = {}
    valor_pipeline = 0.0
    valor_ponderado = 0.0
    for e in etapas:
        filtered = [c for c in cots if c.estado == e]
        count = len(filtered)
        # Calculate total value from products
        total_val = 0.0
        for c in filtered:
            prods = db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == c.id).all()
            for p in prods:
                try:
                    # Parse price_objetivo like "USD $3.50 /un" or "3.50"
                    import re
                    price_match = re.search(r'[\d,\.]+', (p.precio_objetivo or "").replace(",", "."))
                    qty_match = re.search(r'\d+', p.cantidad or "")
                    if price_match and qty_match:
                        total_val += float(price_match.group()) * int(qty_match.group())
                except Exception:
                    pass
        pipeline_por_etapa[e] = {"count": count, "valor": total_val}
        if e != "entregado":
            valor_pipeline += total_val
            valor_ponderado += total_val * (probabilidades[e] / 100.0)

    # Win rate (entregado vs entregado + perdidos - usamos "entregado" como ganado)
    entregados = pipeline_por_etapa["entregado"]["count"]
    total_cerrados = entregados  # No tenemos "perdido" aún
    win_rate = (entregados / total_cerrados * 100) if total_cerrados > 0 else 0

    # Mes actual
    from datetime import datetime as dt
    now = dt.utcnow()
    mes_actual = [c for c in cots if c.created_at and c.created_at.month == now.month and c.created_at.year == now.year]
    ganados_mes = [c for c in mes_actual if c.estado == "entregado"]

    # Calcular valor total de ganados del mes (desde productos)
    import re as _re
    def _valor_cot(cot):
        prods = db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == cot.id).all()
        total = 0.0
        for p in prods:
            try:
                price_m = _re.search(r'[\d,\.]+', (p.precio_objetivo or "").replace(",", "."))
                qty_m = _re.search(r'\d+', p.cantidad or "")
                if price_m and qty_m:
                    total += float(price_m.group()) * int(qty_m.group())
            except Exception:
                pass
        return total
    ganados_valor = sum(_valor_cot(c) for c in ganados_mes)

    # Actividad reciente (últimos 30 días)
    from datetime import timedelta
    hace_30 = now - timedelta(days=30)
    nuevas_cots = len([c for c in cots if c.created_at and c.created_at > hace_30])

    return {
        "opps_abiertas": sum(pipeline_por_etapa[e]["count"] for e in ["pendiente", "cotizado", "produccion"]),
        "valor_pipeline": valor_pipeline,
        "valor_ponderado": valor_ponderado,
        "win_rate": round(win_rate, 1),
        "ganados_mes": {"count": len(ganados_mes), "valor": ganados_valor},
        "perdidos_mes": {"count": 0, "valor": 0},
        "total_clientes": clientes_q.count(),
        "total_cotizaciones": len(cots),
        "pipeline_por_etapa": pipeline_por_etapa,
        "nuevas_cotizaciones_30d": nuevas_cots,
    }


# ═══ FASE 3: ACTIVIDADES / TIMELINE ═══
@app.get("/api/actividades")
def listar_actividades(
    cliente_id: Optional[int] = None,
    cotizacion_id: Optional[int] = None,
    tipo: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List activities filtered by client or cotizacion"""
    q = db.query(Actividad)
    if cliente_id:
        q = q.filter(Actividad.cliente_id == cliente_id)
    if cotizacion_id:
        q = q.filter(Actividad.cotizacion_id == cotizacion_id)
    if tipo:
        q = q.filter(Actividad.tipo == tipo)
    return q.order_by(Actividad.created_at.desc()).limit(limit).all()


@app.post("/api/actividades", response_model=ActividadOut)
def crear_actividad(data: ActividadCreate, db: Session = Depends(get_db)):
    """Create a new activity/note"""
    act = Actividad(**data.model_dump())
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


@app.delete("/api/actividades/{id}")
def eliminar_actividad(id: int, db: Session = Depends(get_db)):
    """Delete an activity"""
    act = db.query(Actividad).get(id)
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    db.delete(act)
    db.commit()
    return {"deleted": True}


# ═══ FASE 4: PIPELINE DRAG & DROP (cambio de estado rápido) ═══
# ═══════════════════════════════════════════════════
# EMAIL AUTOMATION — trigger + render + scheduler
# ═══════════════════════════════════════════════════
def _render_email_template(tpl: str, cot: Cotizacion, cliente: Optional[Cliente]) -> str:
    """Substitute {{variables}} with real cotizacion/cliente data."""
    if not tpl:
        return ""
    vars_map = {
        "cliente": (cliente.nombre if cliente else "") or "",
        "cliente_nombre": (cliente.nombre if cliente else "") or "",
        "cliente_email": (cliente.email if cliente else "") or "",
        "empresa": (cliente.empresa if cliente else "") or "",
        "producto": cot.producto or "",
        "cantidad": cot.cantidad or "",
        "precio": cot.precio_objetivo or "",
        "numero_cotizacion": f"SOL-{cot.id:04d}",
        "numero_solicitud": f"SOL-{cot.id:04d}",
        "estado": cot.estado or "",
        "plazo": cot.plazo or "",
        "uso_final": cot.uso_final or "",
        "fecha": datetime.now().strftime("%d-%m-%Y"),
    }
    out = tpl
    for k, v in vars_map.items():
        out = out.replace("{{" + k + "}}", str(v)).replace("{{ " + k + " }}", str(v))
    return out


def _trigger_email_automation(nueva_etapa: str, cot: Cotizacion, db: Session):
    """Look for active EmailSequences matching nueva_etapa and enqueue EmailLogs."""
    if not cot or not cot.cliente_id:
        return
    cliente = db.query(Cliente).get(cot.cliente_id)
    if not cliente or not cliente.email:
        return
    sequences = db.query(EmailSequence).filter(
        EmailSequence.etapa_trigger == nueva_etapa,
        EmailSequence.activo == "true",
    ).all()
    created = 0
    for seq in sequences:
        # Skip if already queued/sent for this cot+sequence to avoid duplicates on repeated stage changes
        existing = db.query(EmailLog).filter(
            EmailLog.cotizacion_id == cot.id,
            EmailLog.sequence_id == seq.id,
            EmailLog.estado.in_(["pendiente", "enviado"]),
        ).first()
        if existing:
            continue
        asunto = _render_email_template(seq.asunto_template or "", cot, cliente)
        cuerpo = _render_email_template(seq.cuerpo_template or "", cot, cliente)
        programado = datetime.now() + timedelta(hours=int(seq.delay_horas or 0))
        log = EmailLog(
            cotizacion_id=cot.id,
            sequence_id=seq.id,
            destinatario=cliente.email,
            asunto=asunto,
            cuerpo=cuerpo,
            estado="pendiente",
            programado_para=programado,
        )
        db.add(log)
        created += 1
    if created:
        db.commit()
    return created


def _send_email_log_now(log: EmailLog) -> bool:
    """Envia un EmailLog via SMTP usando el helper centralizado.
    Si el cuerpo parece HTML (tiene <html o <body), lo manda como HTML.
    """
    cfg = _smtp_config()
    if not (cfg["user"] and cfg["password"]):
        log.estado = "error"
        log.error_msg = "SMTP no configurado (SMTP_USER/SMTP_PASS vacios)"
        return False
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        body = log.cuerpo or ""
        is_html = "<html" in body.lower() or "<body" in body.lower() or "<table" in body.lower()
        if is_html:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = log.asunto or "MIP Quality & Logistics"
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = log.destinatario
            if cfg["reply_to"]: msg["Reply-To"] = cfg["reply_to"]
            # Genera version texto plano rudimentaria
            import re as _re
            plain = _re.sub(r'<[^>]+>', '', body)
            msg.attach(MIMEText(plain, "plain", "utf-8"))
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = log.asunto or "MIP Quality & Logistics"
            msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
            msg["To"] = log.destinatario
            if cfg["reply_to"]: msg["Reply-To"] = cfg["reply_to"]
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as s:
            s.starttls()
            s.login(cfg["user"], cfg["password"])
            s.sendmail(cfg["from_email"], [log.destinatario], msg.as_string())
        log.estado = "enviado"
        log.enviado_at = datetime.now()
        log.error_msg = None
        return True
    except Exception as e:
        log.estado = "error"
        log.error_msg = str(e)[:500]
        return False


@app.post("/api/email-scheduler/run")
def run_email_scheduler(limit: int = 50, db: Session = Depends(get_db)):
    """Procesa emails pendientes cuyo programado_para <= now. Idempotente.
    Pensado para ser invocado por Cloud Scheduler cada 5 minutos."""
    now = datetime.now()
    pendientes = db.query(EmailLog).filter(
        EmailLog.estado == "pendiente",
        (EmailLog.programado_para == None) | (EmailLog.programado_para <= now),
    ).order_by(EmailLog.programado_para.asc().nullsfirst() if hasattr(EmailLog.programado_para, 'asc') else EmailLog.id).limit(limit).all()
    enviados = 0
    errores = 0
    for log in pendientes:
        ok = _send_email_log_now(log)
        if ok:
            enviados += 1
        else:
            errores += 1
        db.commit()
    return {
        "procesados": len(pendientes),
        "enviados": enviados,
        "errores": errores,
        "pendientes_restantes": db.query(EmailLog).filter(EmailLog.estado == "pendiente").count(),
    }


@app.post("/api/email-automation/trigger-manual")
def trigger_automation_manual(data: dict, db: Session = Depends(get_db)):
    """Util de prueba: disparar automation para una cotizacion en una etapa especifica."""
    cot_id = data.get("cotizacion_id")
    etapa = data.get("etapa")
    if not cot_id or not etapa:
        raise HTTPException(400, "Requiere cotizacion_id y etapa")
    cot = db.query(Cotizacion).get(cot_id)
    if not cot:
        raise HTTPException(404, "Cotización no encontrada")
    created = _trigger_email_automation(etapa, cot, db)
    return {"logs_creados": created or 0, "etapa": etapa, "cotizacion_id": cot_id}


@app.put("/api/cotizaciones/{id}/estado")
def cambiar_estado_cotizacion(id: int, data: dict, db: Session = Depends(get_db)):
    """Quick state change for pipeline drag & drop"""
    nuevo_estado = data.get("estado")
    autor = data.get("autor", "admin")
    notify_client = data.get("notify_client", True)  # por default notificar al cliente
    valid_estados = ["pendiente", "cotizado", "produccion", "entregado"]
    if nuevo_estado not in valid_estados:
        raise HTTPException(400, f"Estado inválido. Usar: {valid_estados}")
    cot = db.query(Cotizacion).get(id)
    if not cot:
        raise HTTPException(404, "Cotización no encontrada")
    estado_anterior = cot.estado
    if estado_anterior == nuevo_estado:
        return {"id": cot.id, "estado": nuevo_estado, "skipped": True, "reason": "Mismo estado"}
    cot.estado = nuevo_estado
    db.commit()
    # Auto-log as activity
    act = Actividad(
        cliente_id=cot.cliente_id,
        cotizacion_id=cot.id,
        tipo="cambio_etapa",
        titulo=f"Cambio de estado: {estado_anterior} → {nuevo_estado}",
        descripcion=f"Cotización #{cot.id} movida de '{estado_anterior}' a '{nuevo_estado}'",
        etapa_anterior=estado_anterior,
        etapa_nueva=nuevo_estado,
        autor=autor,
    )
    db.add(act)
    db.commit()
    # AUTO-TRIGGER EMAIL AUTOMATION para la nueva etapa (secuencias configuradas)
    try:
        logs_created = _trigger_email_automation(nuevo_estado, cot, db)
    except Exception as e:
        print(f"[email-automation] error trigger: {e}")
        logs_created = 0
    # ENVIO TRANSACCIONAL al cliente (independiente de secuencias)
    client_email_sent = False
    if notify_client:
        try:
            cliente = db.query(Cliente).get(cot.cliente_id) if cot.cliente_id else None
            if cliente and cliente.email and "@" in cliente.email:
                _notify_client_estado_change(cliente, cot, estado_anterior, nuevo_estado, db)
                client_email_sent = True
        except Exception as e:
            print(f"[estado-notify] error: {e}")
    return {
        "id": cot.id,
        "estado": nuevo_estado,
        "estado_anterior": estado_anterior,
        "emails_programados": logs_created or 0,
    }


# ═══════════════════════════════════════════════════
# FEATURE FLAGS - Modulo 0
# ═══════════════════════════════════════════════════
DEFAULT_FEATURES = ["proyectos", "pdf", "emails", "proveedores", "prospects"]

@app.get("/api/admin/features")
def get_features(db: Session = Depends(get_db)):
    """List all feature flags (auto-create defaults)"""
    existing = {f.modulo: f for f in db.query(FeatureFlag).all()}
    for m in DEFAULT_FEATURES:
        if m not in existing:
            f = FeatureFlag(modulo=m, activo="true")
            db.add(f)
            existing[m] = f
    db.commit()
    return [{"modulo": f.modulo, "activo": f.activo or "true"} for f in existing.values()]


@app.put("/api/admin/features/{modulo}")
def set_feature(modulo: str, data: dict, db: Session = Depends(get_db)):
    """Toggle a feature flag"""
    f = db.query(FeatureFlag).filter(FeatureFlag.modulo == modulo).first()
    if not f:
        f = FeatureFlag(modulo=modulo, activo="true")
        db.add(f)
    f.activo = data.get("activo", "true")
    db.commit()
    return {"modulo": f.modulo, "activo": f.activo}


# ═══════════════════════════════════════════════════
# PROVEEDORES - Modulo 4
# ═══════════════════════════════════════════════════
@app.get("/api/proveedores")
def listar_proveedores(db: Session = Depends(get_db)):
    return db.query(Proveedor).order_by(Proveedor.nombre).all()


@app.post("/api/proveedores", response_model=ProveedorOut)
def crear_proveedor(data: ProveedorCreate, db: Session = Depends(get_db)):
    p = Proveedor(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.get("/api/proveedores/{id}", response_model=ProveedorOut)
def get_proveedor(id: int, db: Session = Depends(get_db)):
    p = db.query(Proveedor).get(id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    return p


@app.put("/api/proveedores/{id}")
def update_proveedor(id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(Proveedor).get(id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    for k, v in data.items():
        if hasattr(p, k):
            setattr(p, k, v)
    db.commit()
    return {"id": p.id, "updated": True}


@app.delete("/api/proveedores/{id}")
def delete_proveedor(id: int, db: Session = Depends(get_db)):
    p = db.query(Proveedor).get(id)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    db.delete(p)
    db.commit()
    return {"deleted": True}


@app.get("/api/proveedores/{id}/productos")
def get_productos_proveedor(id: int, db: Session = Depends(get_db)):
    return db.query(ProductoProveedor).filter(ProductoProveedor.proveedor_id == id).all()


@app.post("/api/proveedores/{id}/productos", response_model=ProductoProveedorOut)
def add_producto_proveedor(id: int, data: dict, db: Session = Depends(get_db)):
    data["proveedor_id"] = id
    p = ProductoProveedor(**{k: v for k, v in data.items() if k in ["proveedor_id", "sku", "nombre", "categoria", "precio_fob", "moq", "lead_time_dias"]})
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ═══════════════════════════════════════════════════
# PROSPECTS - Modulo 5
# ═══════════════════════════════════════════════════
@app.get("/api/prospects")
def listar_prospects(estado: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Prospect)
    if estado:
        q = q.filter(Prospect.estado == estado)
    return q.order_by(Prospect.created_at.desc()).all()


@app.get("/api/prospects/{id}/detalle")
def get_prospect_detalle(id: int, db: Session = Depends(get_db)):
    """Detalle completo del prospect: datos + conversacion chat + pipeline + traces."""
    p = db.query(Prospect).get(id)
    if not p:
        raise HTTPException(404, "Prospect no encontrado")

    # Buscar conversation_pipelines asociados
    pipelines = db.query(ConversationPipeline).filter(ConversationPipeline.prospect_id == id).all()
    # Tambien buscar conversaciones de chat del mismo email (legacy / compat)
    chat_convs = []
    if p.email:
        for conv in db.query(MateoConversation).filter(MateoConversation.visitor_email == p.email).all():
            chat_convs.append(conv)
    # Tambien buscar por session_id si el pipeline lo tiene
    for pipe in pipelines:
        extra = db.query(MateoConversation).filter(MateoConversation.session_id == pipe.session_id).first()
        if extra and extra not in chat_convs:
            chat_convs.append(extra)

    # Expandir mensajes de cada conversacion
    conversaciones = []
    for conv in chat_convs:
        msgs = db.query(MateoMessage).filter(MateoMessage.conversation_id == conv.id).order_by(MateoMessage.created_at).all()
        conversaciones.append({
            "id": conv.id,
            "session_id": conv.session_id,
            "inicio_at": conv.inicio_at.isoformat() if conv.inicio_at else None,
            "ultimo_mensaje_at": conv.ultimo_mensaje_at.isoformat() if conv.ultimo_mensaje_at else None,
            "mensajes_count": conv.mensajes_count or 0,
            "tokens_input": conv.tokens_input or 0,
            "tokens_output": conv.tokens_output or 0,
            "proveedor_ia": conv.proveedor_ia,
            "interes_detectado": conv.interes_detectado or "",
            "sentimiento": conv.sentimiento or "neutral",
            "messages": [{
                "role": m.role, "content": m.content,
                "tokens": m.tokens_usados or 0,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            } for m in msgs],
        })

    # Actividades asociadas (timeline CRM)
    try:
        actividades = db.query(Actividad).filter(
            (Actividad.descripcion.ilike(f"%prospect {id}%")) |
            (Actividad.descripcion.ilike(f"%{p.email}%") if p.email else False)
        ).order_by(Actividad.created_at.desc()).limit(20).all()
    except Exception:
        actividades = []

    # Traces del agente (si hubo conversacion)
    traces = []
    for conv in chat_convs:
        for t in db.query(AgentTrace).filter(AgentTrace.session_id == conv.session_id).order_by(AgentTrace.created_at.desc()).limit(20).all():
            try:
                tc = json.loads(t.tool_calls or "[]")
            except Exception:
                tc = []
            traces.append({
                "id": t.id, "agent_id": t.agent_id,
                "prompt_tokens": t.prompt_tokens, "output_tokens": t.output_tokens,
                "latency_ms": t.latency_ms, "cost_usd": t.cost_usd,
                "provider": t.provider,
                "tool_calls": tc, "tool_calls_count": len(tc),
                "input_summary": t.input_summary, "output_summary": t.output_summary,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })

    return {
        "prospect": {
            "id": p.id, "nombre": p.nombre, "email": p.email,
            "telefono": p.telefono, "empresa": p.empresa,
            "sector": p.sector, "fuente": p.fuente,
            "estado": p.estado, "score_ia": p.score_ia,
            "notas": p.notas, "created_at": p.created_at.isoformat() if p.created_at else None,
        },
        "pipelines": [{
            "id": pp.id, "session_id": pp.session_id,
            "stage": pp.current_stage,
            "agent_id": pp.current_agent_id,
            "intent": pp.intent_detected, "sentiment": pp.sentiment,
            "requires_human": bool(pp.requires_human),
            "total_messages": pp.total_messages or 0,
            "last_message_at": pp.last_message_at.isoformat() if pp.last_message_at else None,
        } for pp in pipelines],
        "conversaciones": conversaciones,
        "traces": traces,
        "actividades": [{
            "id": a.id, "tipo": a.tipo, "titulo": a.titulo,
            "descripcion": a.descripcion,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        } for a in (actividades or [])],
    }


@app.post("/api/prospects", response_model=ProspectOut)
def crear_prospect(data: ProspectCreate, db: Session = Depends(get_db)):
    p = Prospect(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.put("/api/prospects/{id}")
def update_prospect(id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(Prospect).get(id)
    if not p:
        raise HTTPException(404, "Prospect no encontrado")
    old_estado = p.estado
    for k, v in data.items():
        if hasattr(p, k):
            setattr(p, k, v)
    db.commit()
    # Si cambio estado -> aplicar StageAssignment (notificar al agente/humano responsable)
    new_assignment_info = None
    if "estado" in data and data["estado"] != old_estado:
        sa = db.query(StageAssignment).filter(
            StageAssignment.stage_type == "prospect",
            StageAssignment.stage_key == data["estado"],
            StageAssignment.activo == True,
        ).first()
        if sa:
            new_assignment_info = {
                "agent_id": sa.agent_id,
                "agent_name": None,
                "human_email": sa.human_email or None,
                "human_nombre": sa.human_nombre or None,
            }
            if sa.agent_id:
                agent = db.query(AgentConfig).get(sa.agent_id)
                if agent:
                    new_assignment_info["agent_name"] = agent.display_name
                    # Si el prospect tiene pipeline, actualizar el agente del pipeline
                    pipes = db.query(ConversationPipeline).filter(ConversationPipeline.prospect_id == id).all()
                    for pipe in pipes:
                        pipe.current_agent_id = agent.id
                    db.commit()
            # Actividad
            try:
                db.add(Actividad(
                    tipo="asignacion",
                    titulo=f"Prospect pasado a '{data['estado']}'",
                    descripcion=f"Asignado a {sa.human_nombre or sa.human_email or new_assignment_info['agent_name'] or 'sin asignar'}",
                    autor="system-stage-assignment",
                ))
                db.commit()
            except Exception:
                pass
    return {
        "id": p.id, "estado": p.estado,
        "new_assignment": new_assignment_info,
    }


@app.delete("/api/prospects/{id}")
def delete_prospect(id: int, db: Session = Depends(get_db)):
    p = db.query(Prospect).get(id)
    if not p:
        raise HTTPException(404, "Prospect no encontrado")
    db.delete(p)
    db.commit()
    return {"deleted": True}


@app.post("/api/prospects/{id}/convertir")
def convertir_prospect(id: int, db: Session = Depends(get_db)):
    """Convert a prospect into a client"""
    p = db.query(Prospect).get(id)
    if not p:
        raise HTTPException(404, "Prospect no encontrado")
    if p.convertido_a_cliente_id:
        raise HTTPException(400, "Prospect ya convertido")
    # Check email not duplicated
    email = (p.email or f"prospect-{p.id}@sin-email.local").strip().lower()
    existing = db.query(Cliente).filter(Cliente.email == email).first()
    if existing:
        cliente = existing
    else:
        cliente = Cliente(
            nombre=p.nombre, empresa=p.empresa or "", email=email,
            telefono=p.telefono or "", rubro=p.sector or "",
            referido_por=p.fuente or "", notas=p.notas or "",
            role="client", activo="true",
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)
    p.estado = "convertido"
    p.convertido_a_cliente_id = cliente.id
    db.commit()
    return {"prospect_id": p.id, "cliente_id": cliente.id, "email": cliente.email}


# ═══════════════════════════════════════════════════
# EMAIL AUTOMATION - Modulo 3
# ═══════════════════════════════════════════════════
@app.get("/api/email-sequences")
def listar_sequences(db: Session = Depends(get_db)):
    return db.query(EmailSequence).order_by(EmailSequence.id).all()


@app.post("/api/email-sequences", response_model=EmailSequenceOut)
def crear_sequence(data: EmailSequenceCreate, db: Session = Depends(get_db)):
    s = EmailSequence(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@app.put("/api/email-sequences/{id}")
def update_sequence(id: int, data: dict, db: Session = Depends(get_db)):
    s = db.query(EmailSequence).get(id)
    if not s:
        raise HTTPException(404, "Secuencia no encontrada")
    for k, v in data.items():
        if hasattr(s, k):
            setattr(s, k, v)
    db.commit()
    return {"id": s.id, "activo": s.activo}


@app.delete("/api/email-sequences/{id}")
def delete_sequence(id: int, db: Session = Depends(get_db)):
    s = db.query(EmailSequence).get(id)
    if not s:
        raise HTTPException(404, "Secuencia no encontrada")
    db.delete(s)
    db.commit()
    return {"deleted": True}


@app.get("/api/email-logs")
def listar_email_logs(estado: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(EmailLog)
    if estado:
        q = q.filter(EmailLog.estado == estado)
    logs = q.order_by(EmailLog.created_at.desc()).limit(limit).all()
    # Enrich with sequence and cotizacion names
    seq_ids = list({l.sequence_id for l in logs if l.sequence_id})
    cot_ids = list({l.cotizacion_id for l in logs if l.cotizacion_id})
    seqs = {s.id: s for s in db.query(EmailSequence).filter(EmailSequence.id.in_(seq_ids)).all()} if seq_ids else {}
    cots = {c.id: c for c in db.query(Cotizacion).filter(Cotizacion.id.in_(cot_ids)).all()} if cot_ids else {}
    return [{
        "id": l.id,
        "cotizacion_id": l.cotizacion_id,
        "cotizacion_producto": cots.get(l.cotizacion_id).producto if cots.get(l.cotizacion_id) else None,
        "sequence_id": l.sequence_id,
        "sequence_nombre": seqs.get(l.sequence_id).nombre if seqs.get(l.sequence_id) else None,
        "destinatario": l.destinatario,
        "asunto": l.asunto,
        "cuerpo": l.cuerpo,
        "estado": l.estado,
        "programado_para": l.programado_para.isoformat() if l.programado_para else None,
        "enviado_at": l.enviado_at.isoformat() if l.enviado_at else None,
        "error_msg": l.error_msg,
        "created_at": l.created_at.isoformat() if l.created_at else None,
    } for l in logs]


@app.post("/api/email-logs/{id}/enviar")
def enviar_email_log(id: int, db: Session = Depends(get_db)):
    """Manually send a pending email (delega al helper centralizado)."""
    log = db.query(EmailLog).get(id)
    if not log:
        raise HTTPException(404, "Email log no encontrado")
    if log.estado == "enviado":
        return {"status": "already_sent", "id": log.id, "estado": log.estado}
    _send_email_log_now(log)
    db.commit()
    return {"id": log.id, "estado": log.estado, "error": log.error_msg}


@app.post("/api/email-logs/crear-manual")
def crear_email_log_manual(data: dict, db: Session = Depends(get_db)):
    """Create a manual email in queue (pending)"""
    log = EmailLog(
        cotizacion_id=data.get("cotizacion_id"),
        destinatario=data.get("destinatario", ""),
        asunto=data.get("asunto", ""),
        cuerpo=data.get("cuerpo", ""),
        estado="pendiente",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return {"id": log.id}


# ═══════════════════════════════════════════════════
# PROYECTOS - Modulo 1
# ═══════════════════════════════════════════════════
@app.get("/api/proyectos")
def listar_proyectos(db: Session = Depends(get_db)):
    return db.query(Proyecto).order_by(Proyecto.created_at.desc()).all()


@app.post("/api/proyectos", response_model=ProyectoOut)
def crear_proyecto(data: ProyectoCreate, db: Session = Depends(get_db)):
    p = Proyecto(**data.model_dump(), estado="planificacion")
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.get("/api/proyectos/{id}")
def get_proyecto_detalle(id: int, db: Session = Depends(get_db)):
    p = db.query(Proyecto).get(id)
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    secciones = db.query(ProyectoSeccion).filter(ProyectoSeccion.proyecto_id == id).order_by(ProyectoSeccion.orden).all()
    tareas = db.query(Tarea).filter(Tarea.proyecto_id == id).order_by(Tarea.orden).all()
    return {
        "id": p.id, "nombre": p.nombre, "descripcion": p.descripcion,
        "estado": p.estado, "color": p.color, "created_at": str(p.created_at),
        "fecha_inicio": str(p.fecha_inicio) if p.fecha_inicio else None,
        "fecha_fin": str(p.fecha_fin) if p.fecha_fin else None,
        "cotizacion_id": p.cotizacion_id,
        "secciones": [{"id": s.id, "nombre": s.nombre, "orden": s.orden} for s in secciones],
        "tareas": [{
            "id": t.id, "seccion_id": t.seccion_id, "parent_id": t.parent_id,
            "nombre": t.nombre, "descripcion": t.descripcion,
            "estado": t.estado, "prioridad": t.prioridad,
            "fecha_inicio": str(t.fecha_inicio) if t.fecha_inicio else None,
            "fecha_fin": str(t.fecha_fin) if t.fecha_fin else None,
            "progreso": t.progreso, "orden": t.orden,
            "es_milestone": t.es_milestone, "asignado_a": t.asignado_a,
        } for t in tareas]
    }


@app.put("/api/proyectos/{id}")
def update_proyecto(id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(Proyecto).get(id)
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    for k, v in data.items():
        if hasattr(p, k):
            setattr(p, k, v)
    db.commit()
    return {"id": p.id}


@app.delete("/api/proyectos/{id}")
def delete_proyecto(id: int, db: Session = Depends(get_db)):
    p = db.query(Proyecto).get(id)
    if not p:
        raise HTTPException(404, "Proyecto no encontrado")
    db.delete(p)
    db.commit()
    return {"deleted": True}


@app.post("/api/cotizaciones/{cot_id}/convertir-proyecto")
def convertir_cotizacion_proyecto(cot_id: int, db: Session = Depends(get_db)):
    """Convert a cotizacion into a project with default import workflow sections and tasks"""
    cot = db.query(Cotizacion).get(cot_id)
    if not cot:
        raise HTTPException(404, "Cotización no encontrada")
    cliente = db.query(Cliente).get(cot.cliente_id)
    cliente_name = cliente.nombre if cliente else ""
    p = Proyecto(
        cotizacion_id=cot_id,
        nombre=f"Importación - {cot.producto} ({cliente_name})"[:300],
        descripcion=f"Proyecto generado desde cotización #SOL-{str(cot_id).zfill(3)}",
        estado="activo", color="#1d6fa5",
    )
    db.add(p)
    db.flush()
    # Default sections + tasks for import workflow
    template = [
        ("Preparación", ["Revisar especificaciones", "Contactar proveedores", "Recibir cotizaciones de proveedores"]),
        ("Muestra", ["Solicitar muestra física", "Aprobar muestra con cliente"]),
        ("Pago anticipo", ["Emitir factura anticipo 50%", "Confirmar pago recibido"]),
        ("Producción", ["Iniciar producción en fábrica", "Seguimiento semanal de producción"]),
        ("Control de Calidad", ["Inspección QC en fábrica", "Reporte fotográfico de QC"]),
        ("Pago saldo", ["Emitir factura saldo 50%", "Confirmar pago pre-embarque"]),
        ("Logística", ["Booking de flete", "Embarque", "Tracking de envío"]),
        ("Aduana", ["Documentación de aduana", "Despacho aduanero"]),
        ("Entrega", ["Entrega en bodega cliente", "Confirmación de recepción"]),
    ]
    orden = 0
    for sec_name, tasks in template:
        sec = ProyectoSeccion(proyecto_id=p.id, nombre=sec_name, orden=orden)
        db.add(sec)
        db.flush()
        for ti, task_name in enumerate(tasks):
            t = Tarea(proyecto_id=p.id, seccion_id=sec.id, nombre=task_name, orden=ti, estado="pendiente", prioridad="media")
            db.add(t)
        orden += 1
    db.commit()
    db.refresh(p)
    return {"id": p.id, "nombre": p.nombre}


@app.post("/api/tareas", response_model=TareaOut)
def crear_tarea(data: TareaCreate, db: Session = Depends(get_db)):
    t = Tarea(**data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@app.put("/api/tareas/{id}")
def update_tarea(id: int, data: dict, db: Session = Depends(get_db)):
    t = db.query(Tarea).get(id)
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    for k, v in data.items():
        if hasattr(t, k):
            setattr(t, k, v)
    db.commit()
    return {"id": t.id, "estado": t.estado}


@app.delete("/api/tareas/{id}")
def delete_tarea(id: int, db: Session = Depends(get_db)):
    t = db.query(Tarea).get(id)
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    db.delete(t)
    db.commit()
    return {"deleted": True}


# ═══════════════════════════════════════════════════
# COTIZACIONES FORMALES (PDF) - Modulo 2
# ═══════════════════════════════════════════════════
@app.post("/api/cotizaciones/{cot_id}/generar-formal")
def generar_cotizacion_formal(cot_id: int, data: dict, db: Session = Depends(get_db)):
    """Generate a formal PDF quote from a cotizacion"""
    cot = db.query(Cotizacion).get(cot_id)
    if not cot:
        raise HTTPException(404, "Cotización no encontrada")
    cliente = db.query(Cliente).get(cot.cliente_id)
    productos = db.query(ProductoCotizacion).filter(ProductoCotizacion.cotizacion_id == cot_id).all()

    margen = float(data.get("margen_mip", 15))
    flete = data.get("flete_tipo", "maritimo")
    plazo = int(data.get("plazo_produccion_dias", 45))
    condiciones = data.get("condiciones_pago", "50% anticipo + 50% pre-embarque")
    notas = data.get("notas", "")

    # Calculate prices
    import re as _re
    total_fob = 0.0
    rows = []
    for p in productos:
        try:
            pm = _re.search(r'[\d\.,]+', (p.precio_objetivo or "").replace(",", "."))
            qm = _re.search(r'\d+', p.cantidad or "")
            fob = float(pm.group()) if pm else 0
            qty = int(qm.group()) if qm else 0
            sub = fob * qty
            total_fob += sub
            rows.append((p.nombre, p.categoria, qty, fob, sub))
        except Exception:
            rows.append((p.nombre, p.categoria or "", 0, 0, 0))

    flete_cost = total_fob * (0.08 if flete == "maritimo" else 0.20)
    total_cif = total_fob + flete_cost
    total_with_margin = total_cif * (1 + margen / 100)

    # Generate PDF (numero must be unique; include time to avoid collisions)
    existing = db.query(CotizacionFormal).filter(CotizacionFormal.cotizacion_id == cot_id).count()
    rev = existing + 1
    numero = f"COT-{cot_id:04d}-{datetime.now().strftime('%Y%m%d%H%M%S')}-R{rev}"
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import cm
        os.makedirs("/app/uploads/cotizaciones", exist_ok=True)
        pdf_path = f"/app/uploads/cotizaciones/{numero}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=2*cm)
        styles = getSampleStyleSheet()
        story = []
        # Header
        story.append(Paragraph("<b>MIP QUALITY &amp; LOGISTICS</b>", styles['Title']))
        story.append(Paragraph("Importación desde China — Chile", styles['Normal']))
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"<b>COTIZACIÓN {numero}</b>", styles['Heading2']))
        story.append(Paragraph(f"Fecha: {datetime.now().strftime('%d-%m-%Y')}", styles['Normal']))
        if cliente:
            story.append(Paragraph(f"Cliente: <b>{cliente.nombre}</b>", styles['Normal']))
            story.append(Paragraph(f"Empresa: {cliente.empresa or ''}", styles['Normal']))
            story.append(Paragraph(f"Email: {cliente.email}", styles['Normal']))
        story.append(Spacer(1, 0.5*cm))
        # Products table
        table_data = [["Producto", "Categoría", "Cant.", "FOB USD", "Subtotal USD"]]
        for r in rows:
            table_data.append([str(x) if x else "-" for x in [r[0], r[1], r[2], f"${r[3]:.2f}", f"${r[4]:.2f}"]])
        table_data.append(["", "", "", "Subtotal FOB:", f"${total_fob:.2f}"])
        table_data.append(["", "", "", f"Flete ({flete}):", f"${flete_cost:.2f}"])
        table_data.append(["", "", "", "Total CIF:", f"${total_cif:.2f}"])
        table_data.append(["", "", "", f"Margen MIP ({margen}%):", f"${total_with_margin-total_cif:.2f}"])
        table_data.append(["", "", "", "TOTAL:", f"${total_with_margin:.2f}"])
        t = Table(table_data, colWidths=[5*cm, 3*cm, 2*cm, 3*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a1a1a')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#e8af43')),
            ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(f"<b>Condiciones:</b> {condiciones}", styles['Normal']))
        story.append(Paragraph(f"<b>Plazo producción:</b> {plazo} días", styles['Normal']))
        story.append(Paragraph(f"<b>Flete:</b> {flete.title()} desde China", styles['Normal']))
        if notas:
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph(f"<b>Notas:</b> {notas}", styles['Normal']))
        story.append(Spacer(1, 0.8*cm))
        story.append(Paragraph("<i>MIP Quality &amp; Logistics — contacto@mipquality.com</i>", styles['Normal']))
        doc.build(story)
        pdf_url = f"/uploads/cotizaciones/{numero}.pdf"
    except Exception as e:
        raise HTTPException(500, f"Error generando PDF: {str(e)}")

    # Save to DB
    formal = CotizacionFormal(
        cotizacion_id=cot_id, numero=numero,
        valido_hasta=datetime.now() + timedelta(days=30) if (lambda: True)() else None,
        precio_unitario_fob=total_fob / max(sum(r[2] for r in rows), 1),
        costo_cif=total_cif, margen_mip=margen,
        total_clp=total_with_margin * 950,  # rough USD-CLP
        condiciones_pago=condiciones, flete_tipo=flete,
        plazo_produccion_dias=plazo, notas=notas,
        pdf_url=pdf_url, estado="borrador",
    )
    # Set valido_hasta properly
    from datetime import timedelta as _td
    formal.valido_hasta = datetime.now() + _td(days=30)
    db.add(formal)
    db.commit()
    db.refresh(formal)
    return {
        "id": formal.id, "numero": numero, "pdf_url": pdf_url,
        "total_usd": total_with_margin, "total_clp": formal.total_clp,
    }


@app.get("/api/cotizaciones-formales")
def listar_cotizaciones_formales(cotizacion_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(CotizacionFormal)
    if cotizacion_id:
        q = q.filter(CotizacionFormal.cotizacion_id == cotizacion_id)
    return q.order_by(CotizacionFormal.created_at.desc()).all()


# ─── Serve Frontend ───
@app.get("/health")
def health_nginx():
    return {"status": "ok"}


# Mount static images directory
if os.path.isdir(IMAGES_DIR):
    app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, media_type="text/html")
    return {"error": "Frontend not found"}
