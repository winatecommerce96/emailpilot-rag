# Email Repository Pipeline - Workflow Documentation

## Overview

The Email Repository Pipeline ingests promotional emails from Gmail (via domain-wide delegation), captures screenshots using Playwright, categorizes them with Gemini Vision AI, stores them in Google Drive, and indexes them in Vertex AI for semantic search.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Email Repository Pipeline                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌───────────────┐    ┌─────────────────┐          │
│  │ Gmail API    │───▶│ Playwright    │───▶│ Gemini Vision   │          │
│  │ (Fetch HTML) │    │ (Screenshot)  │    │ (Categorize)    │          │
│  └──────────────┘    └───────────────┘    └────────┬────────┘          │
│                                                      │                  │
│                           ┌──────────────────────────┴──────────────┐   │
│                           ▼                                         ▼   │
│                    ┌─────────────┐                          ┌──────────┐│
│                    │Google Drive │                          │Vertex AI ││
│                    │(Screenshot) │                          │(Index)   ││
│                    └─────────────┘                          └──────────┘│
│                           │                                         │   │
│                           └──────────────┬──────────────────────────┘   │
│                                          ▼                              │
│                                   ┌─────────────┐                       │
│                                   │ Firestore   │                       │
│                                   │ (State)     │                       │
│                                   └─────────────┘                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Gmail Fetch**: Query promotional emails from Google Groups/alias account
2. **HTML Extraction**: Retrieve full HTML content for each email
3. **Screenshot Generation**: Render HTML in Playwright, capture PNG
4. **AI Categorization**: Analyze screenshot with Gemini Vision for:
   - Product category (fashion, food, beauty, etc.)
   - Email type (promotional, newsletter, product launch, etc.)
   - Visual elements (hero image, product grid, CTA, etc.)
   - Brand identification
5. **Drive Upload**: Store screenshot in organized folder structure
6. **Vertex Indexing**: Create searchable document with metadata
7. **State Tracking**: Record processing status in Firestore

## Folder Structure

Screenshots are organized in Google Drive as:
```
EmailScreenshots/
├── fashion/
│   ├── 2024/
│   │   ├── 01/
│   │   ├── 02/
│   │   └── ...
│   └── 2025/
├── food/
├── beauty/
├── home/
├── retail/
├── tech/
├── health/
├── services/
└── other/
```

## Vertex AI Document Schema

```json
{
  "id": "email_{message_id}",
  "client_id": "email_repository",
  "category": "email_asset",
  "title": "{subject}",
  "text_chunk": "Searchable text combining all metadata",

  "email_from": "sender@brand.com",
  "email_subject": "Subject line",
  "email_date": "2025-01-15T10:30:00Z",

  "product_category": "fashion",
  "email_type": "promotional",
  "content_theme": "sale",
  "brand_name": "Brand Name",

  "has_hero_image": true,
  "has_product_grid": false,
  "layout_type": "hero_focused",

  "year_received": "2025",
  "month_received": "01",
  "quarter_received": "Q1",

  "screenshot_drive_link": "https://drive.google.com/...",
  "screenshot_thumbnail_link": "https://drive.google.com/thumbnail?id=...",

  "processed_at": "2026-01-20T12:00:00Z"
}
```

## API Endpoints

### Sync Operations
- `POST /api/emails/sync` - Trigger email sync (background)
- `GET /api/emails/status/{account}` - Get sync status and stats

### Search & Query
- `GET /api/emails/search` - Semantic search with filters
- `GET /api/emails/browse` - Browse with filters (no query)
- `GET /api/emails/recent` - Recently processed emails
- `GET /api/emails/{email_id}` - Single email details

### Statistics
- `GET /api/emails/categories` - Category breakdown
- `GET /api/emails/brands` - Brand list with counts

### Management
- `DELETE /api/emails/clear/{account}` - Clear sync state
- `GET /api/emails/accounts` - List configured accounts
- `GET /api/emails/health` - Pipeline health check

## Configuration

### Required Environment Variables

```bash
# Gmail API (Domain-Wide Delegation)
EMAIL_SYNC_SERVICE_ACCOUNT_SECRET=email-sync-service-account
EMAIL_SYNC_DELEGATED_EMAIL=marketing-inbox@yourcompany.com

# Google Drive
DRIVE_SCREENSHOTS_ROOT_FOLDER_ID=   # Optional, auto-created if empty

# Gemini Vision
GEMINI_API_KEY_SECRET=gemini-rag-image-processing

# Vertex AI
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919
```

### Google Workspace Setup

1. **Enable Gmail API** in GCP Console
2. **Create Service Account** with domain-wide delegation
3. **Configure Domain-Wide Delegation** in Workspace Admin:
   - Go to Security > API Controls > Domain-wide Delegation
   - Add service account client ID
   - Grant scope: `https://www.googleapis.com/auth/gmail.readonly`
4. **Store Service Account** JSON in Secret Manager

## Cost Analysis

| Component | Per Unit | 200K Emails | Monthly (500 new) |
|-----------|----------|-------------|-------------------|
| Gmail API | Free | $0 | $0 |
| Playwright Screenshots | ~$0.0001 | $20 | $0.05 |
| Gemini Vision (flash-lite) | $0.00001875 | $3.75 | $0.01 |
| Drive Storage | 15GB free | $0 | $0 |
| Vertex AI Indexing | $0.001/1K | $0.20 | $0.0005 |
| **Total** | | **~$24** | **~$0.06** |

## Calendar Workflow Integration

The Email Repository integrates with emailpilot-v4 Stage 4 (Creative) to provide email inspiration:

```python
from integration.email_repository_client import EmailRepositoryClient

# In V4 orchestrator
email_client = EmailRepositoryClient(service_url="http://localhost:8003")

# Get seasonal inspiration
inspiration = await email_client.get_seasonal_inspiration(
    month="02",
    year="2024",  # Same month last year
    product_category="fashion",
    limit=5
)

# Include in creative prompt
creative_context["email_inspiration"] = inspiration.to_prompt_context()
```

## Troubleshooting

### Common Issues

1. **Gmail API 403 Forbidden**
   - Verify domain-wide delegation is configured
   - Check service account has correct scopes
   - Ensure delegated email is valid

2. **Screenshots Blank/Broken**
   - Check email HTML is valid
   - Verify Playwright is installed (`playwright install chromium`)
   - Increase timeout for slow-loading emails

3. **Categorization Errors**
   - Verify Gemini API key is valid
   - Check for rate limiting (reduce concurrency)
   - Review screenshot quality

4. **Drive Upload Failures**
   - Verify service account has Drive access
   - Check folder permissions
   - Review quota limits
