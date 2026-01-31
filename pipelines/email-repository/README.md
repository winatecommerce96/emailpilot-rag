# Email Repository Pipeline

A RAG pipeline that ingests promotional emails from Gmail, captures screenshots, categorizes them using Gemini Vision AI, stores them in Google Drive, and indexes them in Vertex AI for semantic search.

## Features

- **Gmail Integration**: Fetches promotional emails via Gmail API with domain-wide delegation
- **Screenshot Generation**: Renders email HTML using Playwright headless browser
- **AI Categorization**: Analyzes screenshots with Gemini Vision to extract:
  - Product category (fashion, food, beauty, home, retail, tech, health, services)
  - Email type (promotional, newsletter, product launch, seasonal, etc.)
  - Visual elements (hero images, product grids, CTAs, layout types)
  - Brand identification
- **Google Drive Storage**: Organized folder structure by category/year/month
- **Vertex AI Indexing**: Full semantic search capabilities
- **Incremental Sync**: Only processes new emails since last sync

## Architecture

```
Gmail API → Playwright → Gemini Vision → Google Drive + Vertex AI
                ↓
           Firestore (State Tracking)
```

## Quick Start

### 1. Install Dependencies

```bash
cd spokes/RAG
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

```bash
# Required environment variables
export EMAIL_SYNC_SERVICE_ACCOUNT_SECRET=email-sync-service-account
export EMAIL_SYNC_DELEGATED_EMAIL=marketing-inbox@yourcompany.com
export GEMINI_API_KEY_SECRET=gemini-rag-image-processing
export GCP_PROJECT_ID=emailpilot-438321
export VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919
```

### 3. Configure Email Accounts

Edit `config/email_accounts.yaml` to add your email accounts:

```yaml
email_accounts:
  - account_email: "marketing-inbox@yourcompany.com"
    account_name: "Marketing Inbox"
    enabled: true
    sync_settings:
      date_range_start: "2023-01-01"
```

### 4. Start the Service

```bash
uvicorn app.main:app --port 8003 --reload
```

### 5. Trigger a Sync

```bash
curl -X POST http://localhost:8003/api/emails/sync \
  -H "Content-Type: application/json" \
  -d '{"force_full_sync": false}'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/emails/sync` | POST | Trigger email sync |
| `/api/emails/status/{account}` | GET | Get sync status |
| `/api/emails/search` | GET | Semantic search |
| `/api/emails/browse` | GET | Browse with filters |
| `/api/emails/recent` | GET | Recent emails |
| `/api/emails/categories` | GET | Category stats |
| `/api/emails/health` | GET | Health check |

## Google Workspace Setup

1. **Enable Gmail API** in GCP Console
2. **Create Service Account** with domain-wide delegation
3. **Configure Domain-Wide Delegation** in Workspace Admin:
   - Security > API Controls > Domain-wide Delegation
   - Add service account client ID
   - Grant scope: `https://www.googleapis.com/auth/gmail.readonly`
4. **Store Service Account** JSON in Secret Manager

## Folder Structure

Screenshots are stored in Google Drive:

```
EmailScreenshots/
├── fashion/
│   ├── 2024/
│   │   ├── 01/
│   │   └── ...
│   └── 2025/
├── food/
├── beauty/
└── ...
```

## Cost Estimate

| Component | Per Email | 200K Emails | Monthly (500) |
|-----------|-----------|-------------|---------------|
| Gmail API | Free | $0 | $0 |
| Playwright | ~$0.0001 | ~$20 | $0.05 |
| Gemini Vision | ~$0.00002 | ~$4 | $0.01 |
| Total | | **~$24** | **~$0.06** |

## Calendar Workflow Integration

The pipeline integrates with emailpilot-v4 Stage 4 (Creative):

```python
from integration.email_repository_client import EmailRepositoryClient

client = EmailRepositoryClient()
inspiration = await client.get_seasonal_inspiration(
    month="02",
    year="2024",
    product_category="fashion"
)
creative_context["email_inspiration"] = inspiration.to_prompt_context()
```

## Files

```
pipelines/email-repository/
├── __init__.py
├── README.md
├── config/
│   ├── __init__.py
│   ├── settings.py              # Configuration classes
│   └── email_accounts.yaml      # Account configuration
├── core/
│   ├── __init__.py
│   ├── gmail_client.py          # Gmail API client
│   ├── screenshot_service.py    # Playwright screenshots
│   ├── drive_uploader.py        # Drive upload
│   ├── categorizer.py           # Gemini Vision categorization
│   ├── state_manager.py         # Firestore state tracking
│   ├── vertex_ingestion.py      # Vertex AI indexing
│   └── sync_orchestrator.py     # Pipeline coordination
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI endpoints
└── docs/
    └── workflow.md              # Detailed documentation
```

## Troubleshooting

### Gmail API 403 Forbidden
- Verify domain-wide delegation is configured
- Check service account has correct scopes
- Ensure delegated email is valid

### Screenshots Blank
- Check email HTML is valid
- Verify Playwright is installed (`playwright install chromium`)
- Increase timeout for slow-loading emails

### Categorization Errors
- Verify Gemini API key is valid
- Check for rate limiting (reduce concurrency)
- Review screenshot quality
