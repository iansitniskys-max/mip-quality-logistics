# MIP Quality & Logistics — Plataforma Demo

> Tu socio estratégico en importación y logística

Mockup interactivo y navegable de la plataforma empresarial de MIP Quality & Logistics — broker de importación de productos desde China.

**Stack:** HTML + CSS + JS vanilla → Nginx Alpine → Google Cloud Run

---

## Vistas incluidas

| # | Vista | Descripción |
|---|-------|-------------|
| 1 | **Landing page** | Hero, ADN de marca, proceso 5 pasos, sectores, logos empresariales (marquee), testimonios premium, footer |
| 2 | **Login / Registro** | Tabs login + registro con campos empresa, RUT, rubro |
| 3 | **Portal cliente** | Dashboard con KPIs, tabla de solicitudes con filtros por estado |
| 4 | **Nueva cotización** | Formulario completo con upload de imágenes/archivos, switch de personalización |
| 5 | **Panel admin** | Tabla de solicitudes, panel lateral de detalle, subir cotización con IA Copilot (simulado) |
| 6 | **Gestión operacional** | Timeline visual 9 etapas, upload facturas, integraciones Google Drive + IA |
| 7 | **Contabilidad y gastos** | P&L, libro de gastos/ingresos, control presupuestario, modal de registro de movimientos |

---

## Ejecutar localmente

Abrir `mip-platform.html` en el navegador. No requiere servidor.

Para probar con Docker:

```bash
docker build -t mip-platform .
docker run -p 8080:8080 mip-platform
# Abrir http://localhost:8080
```

---

## Deploy a producción

### Opción rápida (sin Docker local)

```bash
gcloud run deploy mip-quality-platform \
  --source=. \
  --platform=managed \
  --region=us-central1 \
  --port=8080 \
  --allow-unauthenticated \
  --memory=256Mi
```

### Con Claude Code

Ver `CLAUDE_CODE_PROMPT.md` — contiene un prompt listo para copiar y pegar que ejecuta GitHub + Cloud Run de corrido.

---

## Estructura

```
├── mip-platform.html      # Plataforma completa (standalone)
├── Dockerfile              # nginx:alpine, puerto 8080
├── nginx.conf              # gzip, headers seguridad, health check
├── .dockerignore
├── .gitignore
├── CLAUDE_CODE_PROMPT.md   # Prompt para deploy automatizado
└── README.md
```

---

## Costos Cloud Run

Con `min-instances=0`, el servicio escala a cero sin tráfico.  
Free tier cubre ~2M requests/mes → **$0/mes** para demo/staging.

---

## Dominio personalizado (opcional)

```bash
gcloud run domain-mappings create \
  --service=mip-quality-platform \
  --domain=app.mipquality.com \
  --region=us-central1
```

---

MIP Quality & Logistics — Todos los derechos reservados.
