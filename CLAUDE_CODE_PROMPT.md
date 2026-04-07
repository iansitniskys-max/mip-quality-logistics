# Prompt para Claude Code — Deploy MIP Quality & Logistics

Pega esto directamente en Claude Code desde el directorio donde tienes los archivos del proyecto.

---

## Prompt (copiar y pegar en Claude Code):

```
Tengo un proyecto web estático listo para deploy. Los archivos en este directorio son:

- mip-platform.html (plataforma completa, HTML+CSS+JS standalone)
- Dockerfile (nginx:alpine, puerto 8080)
- nginx.conf (config optimizada para Cloud Run)
- .dockerignore
- .gitignore
- README.md

Necesito que hagas lo siguiente en orden:

### 1. Inicializar Git y subir a GitHub
- Inicializar repo git en este directorio
- Commit inicial con mensaje "feat: MIP Quality & Logistics platform v1.0"
- Crear repo público en GitHub llamado "mip-quality-platform" usando gh CLI
- Push a main

### 2. Deploy a Google Cloud Run
- Verificar que gcloud CLI está autenticado
- Habilitar las APIs: run.googleapis.com, cloudbuild.googleapis.com
- Hacer deploy usando --source=. (Cloud Build, sin necesidad de Docker local):

gcloud run deploy mip-quality-platform \
  --source=. \
  --platform=managed \
  --region=us-central1 \
  --port=8080 \
  --allow-unauthenticated \
  --memory=256Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3

### 3. Verificar
- Mostrarme la URL pública del servicio
- Hacer curl al /health endpoint para confirmar que funciona

Si algo falla, diagnostica y reintenta. No me pidas confirmación intermedia, ejecuta todo seguido.
```

---

## Requisitos previos (antes de ejecutar)

1. **GitHub CLI** instalado y autenticado:
   ```bash
   gh auth login
   ```

2. **Google Cloud CLI** instalado y autenticado:
   ```bash
   gcloud auth login
   gcloud config set project TU_PROJECT_ID
   ```

3. **Todos los archivos** en un solo directorio:
   ```
   mi-proyecto/
   ├── mip-platform.html
   ├── Dockerfile
   ├── nginx.conf
   ├── .dockerignore
   ├── .gitignore
   └── README.md
   ```

---

## Resultado esperado

- Repo en: `https://github.com/TU_USUARIO/mip-quality-platform`
- App live en: `https://mip-quality-platform-xxxxx-uc.a.run.app`
- Costo: **$0/mes** dentro del free tier de Cloud Run (min-instances=0)
