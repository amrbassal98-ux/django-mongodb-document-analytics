# AI-Driven Intelligent Document Analytics Engine

A high-performance Django-based document analysis pipeline designed to process, parse, and structure dynamic document metadata. The engine employs a schema-agnostic MongoDB backend to handle highly polymorphic payloads extracted from LLM-driven document analysis models, and renders them as clean, human-readable UI components instead of raw JSON.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Host: Windows 11                                       │
│  IDE:  VS Code (thin-client frontend)                   │
├─────────────────────────────────────────────────────────┤
│  WSL 2 — Ubuntu Distribution                            │
│  Filesystem: ext4 virtual disk (native Linux perf)      │
│  Project root: ~/projects/django-mongodb-document-      │
│                analytics                                 │
├─────────────────────────────────────────────────────────┤
│  Docker Compose                                         │
│  ├── mongodb (mongo:7, port 27017)                      │
│  └── app     (Django 6.0 / Gunicorn, port 8000)         │
└─────────────────────────────────────────────────────────┘
```

---

## Features

- **Schema-Agnostic MongoDB Backend** — Stores unstructured polymorphic payloads as native JSON documents via `django-mongodb-backend`.
- **Intelligent Polymorphic Payload Rendering** — Recursively parses lists, nested dictionaries, scalars, and nulls, rendering each type with appropriate Bootstrap 5 components (badges, list groups, definition lists, nested cards) in a dark-theme-compatible interface.
- **Dual-Mode LLM Pipeline** — Dispatches plain-text files to a text model and image/PDF files to a multimodal vision model (Groq API), with automatic text truncation at 30 KB.
- **Automatic PDF & Image Processing** — Extracts text from PDFs via PyMuPDF; converts documents to base64 JPEG for vision model ingestion.
- **Multi-Stage Containerized Deployment** — Docker Compose orchestrates a health-checked MongoDB 7 instance and a Gunicorn-served Django application with automatic migration execution on startup.
- **Strict PEP 8 Compliance** — The entire codebase achieves a **10.00/10** pylint score with all diagnostic categories enabled, including PEP 257 docstring conventions.

### Polymorphic Payload Rendering

| Data Type | Bootstrap 5 Component |
|---|---|
| Dictionary (top-level) | `<dl class="row">` definition list |
| Dictionary (nested) | Nested `<div class="card ... bg-body-tertiary">` |
| List (simple, ≤12 items) | `<span class="badge bg-secondary">` badges |
| List (complex / long) | `<ul class="list-group list-group-flush">` |
| Boolean | `<span class="badge bg-success\|bg-secondary">` |
| Integer | `<span class="text-info fw-semibold">` |
| Float | `<span class="text-warning fw-semibold">` |
| `None` / `null` | `<span class="text-body-secondary fst-italic">null</span>` |
| Empty list | `<span class="text-body-secondary fst-italic">empty list</span>` |

---

## Setup & Installation (WSL 2 / Ubuntu Bash)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL 2 integration enabled
- Ubuntu 22.04+ distribution installed via `wsl --install`
- Python 3.14+ recommended (matching the container runtime)

### Steps

```bash
# 1. Clone the repository to the native Linux filesystem (ext4)
git clone https://github.com/amrbassal98-ux/django-mongodb-document-analytics.git
cd django-mongodb-document-analytics

# 2. Create and activate a local Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Build and boot the full stack with Docker Compose
docker compose up --build
```

The application will be available at **http://localhost:8000**.

### Environment Variables

Create or edit `.env` in the project root:

```bash
DEBUG=True
SECRET_KEY=django-insecure-<your-secret-key>
MONGO_URI=mongodb://127.0.0.1:27017/
MONGO_DB_NAME=document_analytics_db
GROQ_API_KEY=gsk_<your-groq-api-key>
```

When running via Docker Compose, the `MONGO_URI` is automatically overridden to `mongodb://mongodb:27017/` (container-to-container DNS resolution), so the `.env` value serves only as a fallback for local development without Docker.

---

## Database Configuration

The Django settings module (`core/settings.py`) uses `django-mongodb-backend` as the database engine. The `HOST` setting reads from the `MONGO_URI` environment variable:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django_mongodb_backend',
        'HOST': os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017/"),
        'NAME': os.getenv("MONGO_DB_NAME", "document_analytics_db"),
    }
}

DATABASE_ROUTERS = ["django_mongodb_backend.routers.MongoRouter"]
DEFAULT_AUTO_FIELD = 'django_mongodb_backend.fields.ObjectIdAutoField'
```

Under Docker Compose, the `app` service sets `MONGO_URI: mongodb://mongodb:27017/`, resolving the hostname `mongodb` to the database container via the internal Compose network. The `mongodb` service declares a health check that waits for `mongosh --eval 'db.runCommand("ping").ok'` to succeed before the app container starts.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/documents/upload/` | Upload a file (text, image, or PDF) |
| `GET` | `/api/v1/documents/<doc_id>/` | Retrieve document metadata & analysis |
| `POST` | `/api/v1/documents/<doc_id>/process/` | Trigger LLM analysis pipeline |
| `POST` | `/api/v1/documents/<doc_id>/annotate/` | Add a user annotation |
| `GET` | `/` | HTML dashboard (all documents) |
| `GET` | `/documents/<doc_id>/` | HTML document detail page |

---

## Code Style & Standards

The project enforces **PEP 8** (Style Guide for Python Code) and **PEP 257** (Docstring Conventions). Quality is verified with `pylint`:

```bash
pip install pylint pylint-django

pylint --load-plugins=pylint_django \
       --django-settings-module=core.settings \
       analytics_engine/ core/ manage.py mongo_migrations/
```

Current score: **10.00/10** — zero warnings across all categories.

---

## Project Structure

```
django-mongodb-document-analytics/
├── analytics_engine/
│   ├── management/              # Django management commands
│   ├── migrations/              # App-specific migrations
│   ├── templatetags/            # Custom template filters
│   │   └── analytics_extras.py  # json_pretty, render_payload
│   ├── admin.py                 # Django admin configuration
│   ├── apps.py                  # App config
│   ├── frontend_urls.py         # HTML route definitions
│   ├── models.py                # Document, AnalysisMetadata, Annotation
│   ├── services.py              # LLM analysis pipeline (text + vision)
│   ├── tests.py                 # Test suite (41 tests)
│   ├── urls.py                  # API route definitions
│   ├── utils.py                 # Text extraction & encoding utilities
│   └── views.py                 # API + HTML views
├── core/
│   ├── apps.py                  # MongoDB-aware app configs
│   ├── settings.py              # Django settings
│   ├── urls.py                  # Root URL configuration
│   └── wsgi.py                  # WSGI entry point
├── templates/
│   ├── base.html                # Bootstrap 5 dark-theme layout
│   └── analytics/
│       ├── dashboard.html        # Document listing
│       └── document_detail.html  # Detail view with polymorphic payload
├── mongo_migrations/            # Django admin/auth/contenttypes migrations
├── .dockerignore
├── .env                         # Environment secrets (gitignored locally)
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── manage.py
└── requirements.txt
```
