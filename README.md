# Intelligence Hub (RAG Service)

**EmailPilot Intelligence Hub** - A FastAPI microservice for document management and semantic search powered by Google Vertex AI Discovery Engine.

## 📦 GitHub Repository & Deployment

| Property | Value |
|----------|-------|
| **GitHub Repository** | [winatecommerce96/emailpilot-rag](https://github.com/winatecommerce96/emailpilot-rag) |
| **Docker Container** | `emailpilot-rag` |
| **Cloud Run Service** | `rag-service` |
| **Production URL** | https://rag.emailpilot.ai |

### Git Workflow

```bash
# Clone the repository
git clone https://github.com/winatecommerce96/emailpilot-rag.git

# Create a feature branch
git checkout -b feature/your-feature-name

# Push changes
git add .
git commit -m "Description of changes"
git push origin feature/your-feature-name

# Create PR to main branch for deployment
```

### Deployment

```bash
# Deploy to Cloud Run (from spokes/RAG directory)
gcloud builds submit --config cloudbuild.yaml
```

--- 

> **Nomenclature Note**: For marketing and end-user purposes, this service is referred to as the **Intelligence Hub**. Internal documentation and technical implementation may still use the term **RAG** (Retrieval-Augmented Generation).

**Cloud Run Endpoint**: [https://rag.emailpilot.ai](https://rag.emailpilot.ai) (The "Intelligence Hub")

## Overview

The Intelligence Hub provides:
- **Document Storage & Retrieval**: Upload, manage, and search documents per client
- **Phase-Aware Search**: Intelligent search filtering based on workflow phases (Strategy, Brief, Visual)
- **Multi-Format Support**: PDF, DOCX, and text file ingestion with automatic chunking
- **Google Docs Integration**: OAuth-based import from Google Docs
- **Image Repository Pipeline**: AI-powered image cataloging with Gemini Vision
- **Intelligence Grading**: AI-powered gap analysis with A-F grades for calendar generation readiness
- **Clerk Authentication**: Optional JWT-based authentication for protected endpoints

## Developer Requirements

**Documentation**: Upon closing out a project, developers MUST update and append the following files:
1. `README.md`
2. `WORKFLOW.md` (specifically within the relevant pipeline or project directory)
3. `NEXT_STEPS.md`

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                     Intelligence Hub Service (:8003)                       │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐  │
│  │   FastAPI    │  │   Vertex AI  │  │     Image      │  │ Intelligence│  │
│  │   Endpoints  │──│   Discovery  │  │   Repository   │  │   Grading   │  │
│  │              │  │   Engine     │  │ (Gemini Vision)│  │ (Gemini AI) │  │
│  └──────────────┘  └──────────────┘  └────────────────┘  └─────────────┘  │
│         │                │                    │                 │         │
│         └────────────────┴────────────────────┴─────────────────┘         │
│                                    │                                      │
│                              ┌─────┴─────┐                                │
│                              │ Firestore │  (State & Sync Tracking)       │
│                              └───────────┘                                │
└───────────────────────────────────────────────────────────────────────────┘
```

## Features

### Core Features

| Feature | Description |
|---------|-------------|
| **Document Management** | Upload, list, view, and delete documents per client |
| **Semantic Search** | Vector-based search with relevance scoring |
| **Phase-Aware Filtering** | STRATEGY, BRIEF, VISUAL, GENERAL phases filter document categories |
| **Auto-Chunking** | Large documents automatically split for optimal retrieval |
| **Multi-Format Support** | PDF, DOCX, TXT, MD file parsing |
| **Client Isolation** | Documents strictly isolated by client_id |

### Document Categories

| Category | Used In Phases | Description |
|----------|----------------|-------------|
| `brand_voice` | STRATEGY, BRIEF | Brand guidelines and voice documentation |
| `past_campaign` | STRATEGY | Historical campaign data |
| `product_spec` | BRIEF | Product specifications and details |
| `visual_asset` | VISUAL | Visual asset descriptions |
| `general` | All phases | Catch-all category |

### Integration Features

| Feature | Description |
|---------|-------------|
| **Google Docs Import** | OAuth flow to import documents directly from Google Docs |
| **Orchestrator Sync** | Fetches client list from EmailPilot Orchestrator (single source of truth) |
| **Firestore Integration** | Shared client data across EmailPilot ecosystem |
| **Image Repository** | AI-powered image cataloging from Google Drive |

### Authentication

| Feature | Description |
|---------|-------------|
| **Clerk JWKS Auth** | JWT verification via Clerk's JWKS endpoint |
| **Optional per-route** | Auth is opt-in; routes remain public by default |
| **User Context** | Access `user_id`, `email`, and claims in protected routes |

## Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud Project with Vertex AI Discovery Engine enabled
- Service account with appropriate permissions

### Installation

```bash
cd /Users/Damon/emailpilot/spokes/RAG

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:

```bash
# GCP Configuration (Required)
GCP_PROJECT_ID=emailpilot-438321
GCP_LOCATION=us
VERTEX_DATA_STORE_ID=your-data-store-id

# Orchestrator Integration
ORCHESTRATOR_URL=https://emailpilot-orchestrator-p3cxgvcsla-uc.a.run.app
INTERNAL_SERVICE_KEY=your-service-key

# Google Docs OAuth (Optional)
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8003/api/google/callback

# Clerk Authentication (Optional)
CLERK_FRONTEND_API=current-stork-99.clerk.accounts.dev
CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
GLOBAL_AUTH_ENABLED=true

# Image Repository Pipeline (Optional)
GEMINI_API_KEY=your-gemini-key

# Image Repository OAuth (User Folder Sharing)
GOOGLE_OAUTH_CLIENT_ID=your-oauth-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8003/api/images/oauth/callback
OAUTH_ENCRYPTION_KEY=your-fernet-encryption-key  # Or use GCP Secret Manager
```

### Running Locally

```bash
# Start the service
uvicorn app.main:app --port 8003 --reload

# Access the UI
open http://localhost:8003/ui/

# Health check
curl http://localhost:8003/health
```

### Docker

```bash
# Build
docker build -t rag-service .

# Run
docker run -p 8003:8080 --env-file .env rag-service
```

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/auth/config` | Clerk configuration for frontend |
| `POST` | `/api/rag/search` | Semantic search across documents |

### Client Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/clients` | List all clients (from Orchestrator/Firestore) |
| `POST` | `/api/clients` | Create a new local client |
| `GET` | `/api/clients/{client_id}` | Get client details |
| `DELETE` | `/api/clients/{client_id}` | Delete client and documents |
| `GET` | `/api/orchestrator/clients` | List clients from Orchestrator (includes metadata) |

### Document Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/documents/{client_id}` | List documents (paginated) |
| `POST` | `/api/documents/{client_id}/upload` | Upload file (PDF, DOCX, TXT) |
| `POST` | `/api/documents/{client_id}/text` | Upload raw text content |
| `GET` | `/api/documents/{client_id}/{doc_id}` | Get document with full content |
| `DELETE` | `/api/documents/{client_id}/{doc_id}` | Delete document |
| `GET` | `/api/stats/{client_id}` | Get client statistics |

### Google Docs Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/google/status` | Check OAuth configuration |
| `GET` | `/api/google/auth` | Start OAuth flow |
| `GET` | `/api/google/callback` | OAuth callback handler |
| `GET` | `/api/google/docs` | List user's Google Docs |
| `POST` | `/api/google/import` | Import a Google Doc |

### Image Repository Pipeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/images/sync` | Trigger image sync (all clients) |
| `POST` | `/api/images/sync/{client_id}` | Trigger sync for specific client |
| `GET` | `/api/images/status/{client_id}` | Get sync status and stats |
| `GET` | `/api/images/folders/{client_id}` | Get configured Drive folders |
| `PUT` | `/api/images/folders/{client_id}` | Update folder configuration |
| `GET` | `/api/images/recent/{client_id}` | Get recently indexed images |
| `GET` | `/api/images/search/{client_id}` | Semantic search indexed images |
| `GET` | `/api/images/thumbnail/{file_id}` | Proxy endpoint for private Drive thumbnails |
| `DELETE` | `/api/images/clear/{client_id}` | Clear sync state (for resync) |
| `DELETE` | `/api/images/delete/{client_id}` | Delete all images for client from Vertex AI |
| `GET` | `/api/images/clients` | List clients with image folders |
| `GET` | `/api/images/health` | Pipeline health check |

### Image Repository OAuth (User Folder Sharing)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/images/oauth/config` | Check OAuth configuration status (for UI) |
| `POST` | `/api/images/oauth/authorize` | Start Google OAuth flow for user Drive access |
| `GET` | `/api/images/oauth/callback` | Handle OAuth callback from Google |
| `GET` | `/api/images/oauth/status/{user_id}` | Check user's OAuth authorization status |
| `POST` | `/api/images/oauth/revoke/{user_id}` | Revoke user's OAuth tokens |
| `GET` | `/api/images/oauth/user-folders/{user_id}` | List user's Drive folders via OAuth credentials |

### Intelligence Grading Pipeline

Evaluates the completeness of a client's knowledge base for email calendar generation.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/intelligence/grade/{client_id}` | Full intelligence grade with AI analysis |
| `GET` | `/api/intelligence/quick-assessment/{client_id}` | Fast keyword-based assessment |
| `GET` | `/api/intelligence/requirements` | Get grading requirements config |
| `GET` | `/api/intelligence/gaps/{client_id}` | Get missing information (gaps) |
| `GET` | `/api/intelligence/ready/{client_id}` | Quick check if ready for calendar generation |
| `POST` | `/api/intelligence/quick-capture` | Submit quick answers to fill gaps |
| `GET` | `/api/intelligence/health` | Pipeline health check |

**Grading Scale:**
- **A (90-100%)**: World-class output - Ready for premium calendars
- **B (80-89%)**: Strong output - Minor gaps, good to proceed
- **C (70-79%)**: Acceptable output - Notable gaps, proceed with caution
- **D (50-69%)**: Weak output - Significant gaps, needs improvement
- **F (<50%)**: Poor output - Critical gaps, do not generate

**7 Intelligence Dimensions:**
1. Brand Foundation (25%) - Voice, values, messaging
2. Audience Intelligence (20%) - Personas, segments, pain points
3. Product Knowledge (20%) - Catalog, hero products, stories
4. Historical Performance (15%) - Past campaigns, metrics, learnings
5. Business Context (10%) - Goals, key dates, promotions
6. Operational Parameters (5%) - Send frequency, automations
7. Creative Assets (5%) - Images, templates, content pillars

## Search API

### Request Schema

```json
{
  "query": "What is the brand voice?",
  "client_id": "rogue-creamery",
  "phase": "BRIEF",
  "k": 5
}
```

### Phase Filtering

| Phase | Categories Searched |
|-------|---------------------|
| `STRATEGY` | brand_voice, past_campaign, general |
| `BRIEF` | product_spec, brand_voice, general |
| `VISUAL` | visual_asset, general |
| `GENERAL` | All categories (no filter) |

### Response Schema

```json
{
  "results": [
    {
      "content": "Brand voice: warm, artisanal, heritage-focused...",
      "metadata": {
        "client_id": "rogue-creamery",
        "category": "brand_voice",
        "source": "brand_guidelines.json",
        "title": "Brand Guidelines"
      },
      "relevance_score": 0.87
    }
  ]
}
```

## Image Repository Pipeline

The Image Repository Pipeline automatically indexes images from Google Drive using Gemini Vision AI.

### Features

- **Drive Sync**: Monitor Google Drive folders for new/updated images
- **AI Analysis**: Gemini Vision extracts mood, description, and visual tags
- **Incremental Sync**: Only process new/changed files
- **Vertex Ingestion**: Index metadata in Vertex AI for search
- **Semantic Search**: Search indexed images with natural language queries
- **Thumbnail Proxy**: Serve private Drive images through authenticated proxy
- **User OAuth Folder Sharing**: Users can connect their Google Drive and share folders they have access to

### User OAuth Folder Sharing

Users can connect their personal Google Drive accounts to share folders with the image repository. This enables:
- Browsing user's Drive folders through the UI
- Adding user-accessible folders to client image repositories
- Secure encrypted token storage in Firestore

**Security Features**:
- Tokens encrypted using Fernet encryption before Firestore storage
- Encryption key from `OAUTH_ENCRYPTION_KEY` env var or GCP Secret Manager
- Automatic token refresh when expired
- Token revocation with Google on disconnect

**UI Access**: Settings button in client card → "Connect Google Drive" → Browse folders → Add to client

### Configuration

Folder mappings are defined in `pipelines/image-repository/config/folder_mappings.yaml`:

```yaml
philz-coffee:
  - folder_id: "1abc123..."
    folder_name: "Brand Images"
    folder_type: "client"
    enabled: true
```

### Pipeline Components

| Component | Description |
|-----------|-------------|
| `drive_client.py` | Google Drive API integration |
| `vision_service.py` | Gemini Vision image analysis |
| `state_manager.py` | Firestore-based sync state tracking |
| `vertex_ingestion.py` | Vertex AI document creation |
| `sync_orchestrator.py` | Coordinates the full sync pipeline |
| `oauth_manager.py` | User OAuth token management with encrypted storage |

## UI

The service includes a React-based document management UI:

- **Document Manager** (`/ui/`): Upload, browse, and manage documents
- **Image Repository** (`/ui/image-repository.html`): View and manage indexed images
- **Email Repository** (`/ui/email-repository.html`): Search and sync promotional emails
- **Email Review** (`/ui/email-review.html`): Review email campaigns before send
- **Meeting Intelligence** (`/ui/meeting-intelligence.html`): Connect calendar and search meeting insights
- **Figma Feedback** (`/ui/figma-feedback.html`): View and manage Figma design feedback

### UI Shell Integration

All UI pages use the **EmailPilot UI Shell** loaded dynamically from the orchestrator service. This provides consistent styling, navigation sidebar, and authentication across all spokes.

**Key requirements for UI pages:**

1. **Enable shell mode** - Add `data-ep-shell="true"` to the `<html>` tag:
   ```html
   <html lang="en" data-ep-shell="true">
   ```

2. **Include EP:UI-SHELL script block** - This script dynamically loads CSS/JS from orchestrator:
   ```html
   <!-- EP:UI-SHELL:START -->
   <script>
       (function () {
           // ... loads ui-shell.css and ui-shell.js from orchestrator
       })();
   </script>
   <!-- EP:UI-SHELL:END -->
   ```

3. **Do NOT include local CSS references** - The shell script has duplicate detection that will skip loading orchestrator CSS if a local `ui-shell.css` is found.

4. **Use standard body classes**:
   ```html
   <body class="h-screen flex overflow-hidden ep-shell-lock" data-layout="ultimate">
   ```

5. **Include gradient background containers**:
   ```html
   <div class="gradient-bg"></div>
   <div class="gradient-orbs">
       <div class="orb orb1"></div>
       <div class="orb orb2"></div>
       <div class="orb orb3"></div>
   </div>
   ```

**Orchestrator URLs:**
- Local: `http://localhost:8001/static/ui-shell.v{VERSION}.css`
- Production: `https://app.emailpilot.ai/static/ui-shell.v{VERSION}.css`

## Authentication

### Protecting Routes

```python
from fastapi import Depends
from app.auth import AuthenticatedUser, get_current_user

@app.get("/api/protected")
async def protected_route(user: AuthenticatedUser = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email}
```

### Optional Authentication

```python
from app.auth import get_current_user_optional

@app.get("/api/optional")
async def optional_route(user: AuthenticatedUser | None = Depends(get_current_user_optional)):
    if user:
        return {"authenticated": True, "user_id": user.user_id}
    return {"authenticated": False}
```

## Project Structure

```
RAG/
├── app/
│   ├── main.py              # FastAPI application
│   ├── auth.py              # Clerk JWT authentication
│   ├── models/
│   │   └── schemas.py       # Pydantic models
│   └── services/
│       ├── vertex_search.py # Vertex AI Discovery Engine client
│       └── google_docs.py   # Google Docs OAuth service
├── pipelines/
│   ├── image-repository/    # Image indexing pipeline
│   │   ├── api/routes.py    # FastAPI routes
│   │   ├── core/            # Pipeline components
│   │   └── config/          # Settings and folder mappings
│   ├── email-repository/    # Email ingestion pipeline (NEW)
│   │   ├── api/routes.py    # FastAPI routes
│   │   ├── core/            # Gmail, screenshots, categorization
│   │   └── config/          # Settings and email accounts
│   └── meeting-ingestion/   # Meeting intelligence pipeline
│       ├── api/routes.py    # FastAPI routes
│       └── core/            # Calendar, transcripts, analysis
├── ui/                      # React frontend
├── data/                    # Local data storage
├── requirements.txt
├── Dockerfile
└── README.md
```

## Deployment

### Cloud Run

The service is deployed to Google Cloud Run:

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/rag-service

# Deploy
gcloud run deploy rag-service \
  --image gcr.io/PROJECT_ID/rag-service \
  --platform managed \
  --region us-central1 \
  --set-env-vars="GLOBAL_AUTH_ENABLED=true" \
  --allow-unauthenticated
```

### Port Mapping

| Environment | Port | Notes |
|-------------|------|-------|
| Local | 8003 | Development |
| Docker (internal) | 8080 | Container port |
| Docker (external) | 8003 | Host mapping |
| Cloud Run | 8080 | Standard Cloud Run port |

## Related Documentation

- [AUTH_IMPLEMENTATION.md](./AUTH_IMPLEMENTATION.md) - Clerk authentication details
- [AUTH_FLOW_DIAGRAM.md](./AUTH_FLOW_DIAGRAM.md) - Authentication flow diagrams
- [QUICK_START_AUTH.md](./QUICK_START_AUTH.md) - Quick start guide for auth setup

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Search | Google Vertex AI Discovery Engine |
| Vision AI | Google Gemini |
| Database | Google Firestore |
| Authentication | Clerk (JWKS) |
| File Parsing | pypdf, python-docx |
| Frontend | React, TailwindCSS |

## Email Repository Pipeline

The Email Repository Pipeline ingests promotional emails from Gmail, captures screenshots, categorizes them using Gemini Vision AI, stores them in Google Drive, and indexes them in Vertex AI for semantic search and Calendar Workflow (v4) integration.

### Features

- **Gmail Integration**: Fetches promotional emails via Gmail API with domain-wide delegation
- **Screenshot Generation**: Renders email HTML using Playwright headless browser
- **AI Categorization**: Analyzes screenshots with Gemini Vision (fashion, food, beauty, home, retail, tech, etc.)
- **Google Drive Storage**: Organized folder structure `EmailScreenshots/{category}/{year}/{month}/`
- **Vertex AI Indexing**: Full semantic search capabilities
- **Incremental Sync**: Only processes new emails since last sync
- **v4 Integration**: Feeds email inspiration into emailpilot-v4 Stage 4 (Creative)

### UI Access

- **Email Repository** (`/ui/email-repository.html`): Search, browse, and sync promotional emails

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/emails/sync` | Trigger email sync (background) |
| `GET` | `/api/emails/status/{account}` | Get sync status and stats |
| `GET` | `/api/emails/search` | Semantic search with filters |
| `GET` | `/api/emails/browse` | Browse with category/date filters |
| `GET` | `/api/emails/recent` | Recently processed emails |
| `GET` | `/api/emails/categories` | Category breakdown stats |
| `GET` | `/api/emails/health` | Pipeline health check |

### Environment Variables

```bash
# Gmail API with domain-wide delegation
EMAIL_SYNC_SERVICE_ACCOUNT_SECRET=email-sync-service-account
EMAIL_SYNC_DELEGATED_EMAIL=nomad@unsubscribr.com

# Gemini AI (reuse existing)
GEMINI_API_KEY_SECRET=gemini-rag-image-processing

# GCP (existing)
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919
```

### Google Workspace Setup

Requires domain-wide delegation configuration in Google Workspace Admin Console:
- Security > API Controls > Domain-wide Delegation
- Client ID: `107287607247737156910`
- OAuth Scope: `https://www.googleapis.com/auth/gmail.readonly`

See `NEXT_STEPS.md` and `pipelines/email-repository/README.md` for detailed setup instructions.

### Pipeline Components

| Component | Location | Description |
|-----------|----------|-------------|
| `gmail_client.py` | `pipelines/email-repository/core/` | Gmail API with domain-wide delegation |
| `screenshot_service.py` | `pipelines/email-repository/core/` | Playwright screenshot generation |
| `drive_uploader.py` | `pipelines/email-repository/core/` | Drive upload with folder organization |
| `categorizer.py` | `pipelines/email-repository/core/` | Gemini Vision AI categorization |
| `state_manager.py` | `pipelines/email-repository/core/` | Firestore state tracking |
| `vertex_ingestion.py` | `pipelines/email-repository/core/` | Vertex AI document creation |
| `sync_orchestrator.py` | `pipelines/email-repository/core/` | Pipeline coordination |
| `routes.py` | `pipelines/email-repository/api/` | FastAPI endpoints |

---

## Figma Feedback Pipeline

The Figma Feedback Pipeline ingests design feedback comments from Figma files, extracts creative rules using AI, and stores them for retrieval during calendar generation workflows.

### Features

- **Figma Comments Ingestion**: Fetches comments directly from Figma API or via GitHub Actions
- **Unified Three-Layer Storage**: Firestore (UI), BigQuery (analytics), Vertex AI (RAG search)
- **Creative Rules Extraction**: AI extracts reusable design rules from feedback patterns
- **Asana Integration**: Auto-discovers Figma files from completed Asana tasks
- **60-Day Backfill**: Historical comment ingestion with one-click backfill button
- **Weekly Automation**: GitHub Actions workflow runs every Monday at 11 AM UTC

### Data Architecture

| Layer | Storage | Purpose |
|-------|---------|---------|
| **Operational** | Firestore (`creative_intelligence/clients/{client_id}/comments`) | Design Feedback UI, real-time access |
| **Analytics** | BigQuery (`figma.comments`, `figma.creative_rules`) | Historical analysis, batch processing |
| **Knowledge** | Vertex AI RAG | Semantic search for brief generation |

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/figma-feedback/health` | Pipeline health check with token status |
| `POST` | `/api/figma-feedback/process` | Process comments from BigQuery |
| `GET` | `/api/figma-feedback/rules/{client_id}` | Get extracted creative rules |
| `POST` | `/api/figma-feedback/backfill/{client_id}` | Backfill from BigQuery (N days) |
| `POST` | `/api/figma-feedback/pull-from-figma` | Pull directly from Figma API |
| `GET` | `/api/figma-feedback/figma-token-status` | Check Figma API token validity |
| `GET` | `/api/figma-feedback/discover-figma-files/{client_id}` | Find Figma files from Asana tasks |
| `POST` | `/api/figma-feedback/auto-backfill/{client_id}` | One-click: discover files + pull + process |

### Environment Variables

```bash
# Figma API (for direct API pulls and backfills)
FIGMA_ACCESS_TOKEN=figd_xxxxx  # or FIGMA_API_TOKEN

# Asana API (for auto-discovering Figma files from tasks)
ASANA_PAT=your-asana-personal-access-token

# Orchestrator URL (for Firestore sync)
ORCHESTRATOR_URL=http://orchestrator:8001  # local
ORCHESTRATOR_URL=https://app.emailpilot.ai  # production

# Internal service key (for authenticated cross-service calls)
INTERNAL_SERVICE_KEY=your-internal-service-key
```

### GitHub Actions Workflow

The ingestion workflow lives in external repository `winatecommerce96/figma-comments-review`:
- **Schedule**: Mondays 11 AM UTC (`0 11 * * 1`)
- **Workflow File**: `.github/workflows/weekly-ingestion.yml`
- **Required Secrets**: `GCP_SERVICE_ACCOUNT_KEY`, `ASANA_PAT`, `FIGMA_TOKEN`, `EMAILPILOT_SERVICE_KEY`

### Related UI

- **Creative Intelligence** (`/static/design_feedback.html` on Orchestrator): Browse and manage design feedback
- **Trigger Sync**: Orchestrator endpoint `POST /api/design-feedback/trigger-sync` can manually trigger the GitHub Action

---

## Meeting Intelligence Pipeline

The Meeting Intelligence Pipeline automatically harvests strategic insights from client meetings by scanning Google Calendar, analyzing transcripts with Gemini AI, and indexing the intelligence for RAG search.

### Features

- **Google Calendar OAuth**: Per-user calendar access with persistent Firestore sessions
- **60-Day Initial Scan**: On first connection, scans 60 days of past meetings for all user's clients
- **Weekly Automated Scans**: Cloud Scheduler triggers weekly scans for all authorized users
- **AI-Powered Analysis**: Gemini extracts strategic directives, commercial signals, and sentiment
- **Vertex AI Ingestion**: Intelligence indexed for semantic search in the RAG system

### UI Access

- **Meeting Intelligence** (`/ui/meeting-intelligence.html`): Connect calendar, scan meetings, search intelligence

### Localhost Development

When running locally on `localhost:8003`, Clerk authentication redirects to the orchestrator (`localhost:8001`) for login. This is handled automatically by `auth_controller.js`.

**Prerequisites for local development**:
1. Start the orchestrator: `cd orchestrator && uvicorn main_firestore:app --port 8001 --reload`
2. Start the RAG service: `cd spokes/RAG && uvicorn app.main:app --port 8003 --reload`
3. Access Meeting Intelligence at `http://localhost:8003/ui/meeting-intelligence.html`
4. If not authenticated, you'll be redirected to `http://localhost:8001/static/login.html`

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/meeting/auth` | Start Google OAuth flow |
| `GET` | `/api/meeting/callback` | OAuth callback handler |
| `GET` | `/api/meeting/status` | Check connection status |
| `DELETE` | `/api/meeting/disconnect` | Revoke calendar access |
| `POST` | `/api/meeting/scan/{client_id}` | Trigger manual scan for a client |
| `POST` | `/api/meeting/initial-scan` | Trigger 60-day scan for all clients |
| `GET` | `/api/meeting/scan-status` | Get scan progress/state |
| `POST` | `/api/meeting/weekly-scan` | Scheduled weekly scan (Cloud Scheduler) |

### Environment Variables

```bash
# Google OAuth for Meeting Intelligence
GOOGLE_OAUTH_CLIENT_ID=your-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
MEETING_OAUTH_REDIRECT_URI=http://localhost:8003/api/meeting/callback

# Gemini AI for transcript analysis
GEMINI_API_KEY=your-gemini-key

# Internal service key (for scheduled scans)
INTERNAL_SERVICE_KEY=your-service-key
```

### Cloud Scheduler Setup

```bash
gcloud scheduler jobs create http meeting-weekly-scan \
  --location=us-central1 \
  --schedule="0 2 * * 1" \
  --uri="https://rag.emailpilot.ai/api/meeting/weekly-scan?api_key=YOUR_KEY" \
  --http-method=POST \
  --attempt-deadline=1800s
```

### Pipeline Components

| Component | Location | Description |
|-----------|----------|-------------|
| `auth.py` | `pipelines/meeting-ingestion/core/` | OAuth service with Firestore persistence |
| `scanner.py` | `pipelines/meeting-ingestion/core/` | Calendar scanning and transcript retrieval |
| `processor.py` | `pipelines/meeting-ingestion/core/` | Gemini AI transcript analysis |
| `scheduler.py` | `pipelines/meeting-ingestion/core/` | Scan state tracking and scheduling |
| `ingestion.py` | `pipelines/meeting-ingestion/core/` | Vertex AI document creation |
| `routes.py` | `pipelines/meeting-ingestion/api/` | FastAPI endpoints |

---

## License

Internal EmailPilot service - proprietary.
