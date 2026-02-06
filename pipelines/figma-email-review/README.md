# Figma Email Review Pipeline

> AI-powered email design proofing manager that analyzes Figma designs for quality, brand compliance, and best practices.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Scoring System](#scoring-system)
- [Integrations](#integrations)
- [Directory Structure](#directory-structure)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Figma Email Review Pipeline is a comprehensive "proofing manager" that automatically reviews email designs for:

- **Brand Voice Compliance** - Ensures copy matches client guidelines via RAG
- **Accessibility** - Checks contrast, alt text, readability
- **Best Practices** - Validates subject lines, CTAs, layout, footers
- **Mobile Readiness** - Verifies responsive design and touch targets

### How It Works

1. Designer changes Asana task's "Messaging Stage" to "✨ AI Email Review"
2. Pipeline receives Figma URL from Asana task custom field
3. Fetches email design from Figma API and exports as image
4. Analyzes with Gemini Vision for layout, visuals, accessibility
5. Pulls brief expectations from the Asana task description
6. Queries RAG for brand voice guidelines and compliance
7. Evaluates against email marketing best practices
8. Generates comprehensive report with scores and issues
9. Stores results in Firestore and indexes insights to Vertex AI
10. Posts formatted results back to Asana task as comment

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           TRIGGER FLOW                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐     │
│  │  Asana Task  │────▶│ Asana Webhook Hub│────▶│ Pub/Sub Topic     │     │
│  │ Stage: "AI   │     │ (webhook event)  │     │ asana-stage-      │     │
│  │ Email Review"│     │                  │     │ changes           │     │
│  └──────────────┘     └──────────────────┘     └─────────┬─────────┘     │
│                                                          │               │
│                                                          ▼               │
│  ┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐     │
│  │ Review Posted│◀────│ Figma Email      │◀────│ Orchestrator      │     │
│  │ to Asana Task│     │ Review Pipeline  │     │ Pub/Sub Subscriber│     │
│  └──────────────┘     └──────────────────┘     └───────────────────┘     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│                          PIPELINE COMPONENTS                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     │
│  │  Figma Client   │────▶│ Vision Analyzer │────▶│ RAG Integration │     │
│  │                 │     │                 │     │                 │     │
│  │ • Fetch file    │     │ • Gemini Vision │     │ • Brand voice   │     │
│  │ • Export frames │     │ • Layout check  │     │ • Guidelines    │     │
│  │ • Extract text  │     │ • Visual assess │     │ • Compliance    │     │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘     │
│          │                       │                       │               │
│          └───────────────────────┼───────────────────────┘               │
│                                  │                                       │
│                                  ▼                                       │
│                      ┌───────────────────────┐                           │
│                      │  Review Orchestrator  │                           │
│                      │                       │                           │
│                      │ • Coordinate workflow │                           │
│                      │ • Aggregate scores    │                           │
│                      │ • Generate report     │                           │
│                      └───────────────────────┘                           │
│                                  │                                       │
│              ┌───────────────────┼───────────────────┐                   │
│              ▼                   ▼                   ▼                   │
│      ┌───────────────┐   ┌───────────────┐   ┌───────────────┐           │
│      │Best Practices │   │ State Manager │   │Vertex Ingestion│          │
│      │               │   │               │   │               │           │
│      │ • Subject line│   │ • Firestore   │   │ • Index docs  │           │
│      │ • CTA check   │   │ • Version sync│   │ • Search API  │           │
│      │ • Layout rules│   │ • History     │   │ • Insights    │           │
│      └───────────────┘   └───────────────┘   └───────────────┘           │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Features

### Vision Analysis (Gemini Vision)

| Feature | Description |
|---------|-------------|
| **Layout Detection** | Identifies header, hero, body, CTA, footer sections |
| **Visual Elements** | Analyzes colors, imagery, whitespace, brand consistency |
| **CTA Analysis** | Evaluates visibility, clarity, placement, button design |
| **Accessibility** | Checks contrast ratios, text sizing, alt text indicators |
| **Mobile Readiness** | Verifies single-column layout, touch target sizes |
| **Copy Extraction** | Extracts headline, subheadline, body, CTA text |

### Brand Voice Compliance (RAG)

| Feature | Description |
|---------|-------------|
| **Guideline Retrieval** | Fetches client's brand voice documents from RAG |
| **Tone Analysis** | Compares email copy against approved tone |
| **Vocabulary Check** | Identifies forbidden/recommended words |
| **Pattern Matching** | Learns from past campaign patterns |

### Best Practices Evaluation

| Category | Checks |
|----------|--------|
| **Subject Line** | Length (30-60 chars), spam triggers, urgency words |
| **CTA** | Visibility score, action verb usage, placement |
| **Layout** | Image-to-text ratio, footer presence, hierarchy |
| **Mobile** | Width (320-600px), touch targets (44x44px min) |
| **Accessibility** | Contrast (4.5:1 min), font size (14px min) |

### State Management (Firestore)

| Feature | Description |
|---------|-------------|
| **Version Tracking** | Incremental sync based on Figma file version |
| **Review History** | Full history of all reviews per client |
| **Deduplication** | Prevents duplicate reviews of same content |
| **Statistics** | Aggregate stats per file and client |

### Insight Indexing (Vertex AI)

| Feature | Description |
|---------|-------------|
| **Document Indexing** | Creates searchable insight documents |
| **Category Tagging** | Labels as recurring_issue, best_practice, brand_pattern |
| **Severity Rating** | Critical, warning, or suggestion |
| **Future Retrieval** | Enables learning from past reviews |

---

## Installation

The pipeline is part of the RAG service and is automatically loaded when the service starts.

### Prerequisites

```bash
# Python 3.11+
python --version

# Required packages (add to requirements.txt if not present)
pip install google-cloud-discoveryengine google-cloud-firestore httpx pydantic
```

### Verify Installation

```bash
# Start RAG service
cd /Users/Damon/emailpilot/spokes/RAG
uvicorn app.main:app --port 8003 --reload

# Check pipeline loaded
curl http://localhost:8003/api/figma-review/health
```

Expected output:
```json
{
  "status": "healthy",
  "figma_configured": true,
  "gemini_configured": true,
  "rag_url": "http://localhost:8003",
  "gcp_project": "emailpilot-438321",
  "vertex_data_store": "your-data-store-id",
  "asana_configured": true
}
```

---

## Configuration

### Environment Variables

```bash
# =============================================================================
# FIGMA API
# =============================================================================
FIGMA_ACCESS_TOKEN=figd_xxxxxxxxxxxxxxxxxxxxx
# Get from: https://www.figma.com/developers/api#access-tokens

# =============================================================================
# ASANA CUSTOM FIELD GIDs
# =============================================================================
# Find these in Asana project settings > Custom Fields
ASANA_MESSAGING_STAGE_GID=1234567890123456    # "Messaging Stage" dropdown
ASANA_FIGMA_URL_GID=1234567890123457          # "Figma URL" text field
ASANA_CLIENT_FIELD_GID=1234567890123458       # "Client" field

# =============================================================================
# AI/ML
# =============================================================================
GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxx
# Get from: https://makersuite.google.com/app/apikey

# =============================================================================
# GCP
# =============================================================================
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=your-data-store-id
GCP_LOCATION=us

# =============================================================================
# OPTIONAL: Override defaults
# =============================================================================
RAG_BASE_URL=http://localhost:8003           # Default: http://localhost:8003
FIRESTORE_COLLECTION_PREFIX=figma_review     # Default: figma_review
ASANA_ORCHESTRATOR_URL=http://localhost:8001 # Default: http://localhost:8001

# =============================================================================
# OPTIONAL: Brief Alignment
# =============================================================================
EMAIL_REVIEW_BRIEF_ENABLED=true              # Default: true (disable to rollback)
EMAIL_REVIEW_BRIEF_MAX_CHARS=4000            # Truncate brief text in prompt

# =============================================================================
# OPTIONAL: Stage Gating
# =============================================================================
EMAIL_REVIEW_STAGE_ENFORCED=true             # Default: true (disable to rollback)
EMAIL_REVIEW_STAGE_NAME="Messaging Stage"    # Custom field name
ASANA_EMAIL_REVIEW_STAGE="✨ AI Email Review" # Required stage value
```

### Brief Alignment Behavior

When enabled, the pipeline will fetch the Asana task description (`notes`) for the
current `asana_task_gid` and include it in the compliance prompt. If no description
is found or lookup fails, the review proceeds without brief context.

### Stage Gating Behavior

When enabled, the review only runs if the Asana task's `Messaging Stage` matches
`ASANA_EMAIL_REVIEW_STAGE`. If the stage is missing or different, the review is
blocked with a clear error. Disable via `EMAIL_REVIEW_STAGE_ENFORCED=false` to rollback.

### Finding Asana GIDs

1. Open your Asana project
2. Click the dropdown arrow next to the project name
3. Select "Manage custom fields"
4. Click on each field to see its GID in the URL

Or use the Asana API:
```bash
curl -H "Authorization: Bearer $ASANA_TOKEN" \
  "https://app.asana.com/api/1.0/projects/{project_gid}/custom_field_settings"
```

---

## API Reference

### POST /api/figma-review/review

Trigger an email design review. Runs in background to avoid timeouts.

**Request:**
```json
{
  "client_id": "rogue-creamery",
  "figma_url": "https://www.figma.com/file/ABC123/Email-Design?node-id=0:1",
  "asana_task_gid": "1234567890123456",
  "asana_task_name": "Summer Sale Email",
  "post_results_to_asana": true,
  "include_brand_voice": true,
  "force_review": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `client_id` | string | Yes | Client identifier |
| `figma_url` | string | Yes | Figma file or frame URL |
| `asana_task_gid` | string | No | Asana task for posting results |
| `asana_task_name` | string | No | Task name for context |
| `post_results_to_asana` | boolean | No | Auto-post results (default: true) |
| `include_brand_voice` | boolean | No | Include RAG brand check (default: true) |
| `force_review` | boolean | No | Force even if recently reviewed (default: false) |

**Response:**
```json
{
  "status": "queued",
  "message": "Review queued for rogue-creamery. Processing in background."
}
```

---

### GET /api/figma-review/reports/{client_id}

List review reports for a client.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max reports (max: 100) |
| `min_score` | float | null | Filter by minimum score (0-1) |
| `has_critical_issues` | boolean | null | Filter by critical issues |

**Response:**
```json
{
  "client_id": "rogue-creamery",
  "total": 5,
  "reports": [
    {
      "review_id": "abc123def456",
      "email_name": "Summer Sale Email",
      "overall_score": 0.82,
      "reviewed_at": "2025-01-15T10:30:00Z",
      "critical_issues_count": 0,
      "warnings_count": 2,
      "file_key": "ABC123",
      "frame_id": "0:1",
      "asana_task_gid": "1234567890123456"
    }
  ]
}
```

---

### GET /api/figma-review/reports/{client_id}/{review_id}

Get full review report details.

**Response:**
```json
{
  "review_id": "abc123def456",
  "client_id": "rogue-creamery",
  "email_name": "Summer Sale Email",
  "overall_score": 0.82,
  "reviewed_at": "2025-01-15T10:30:00Z",
  "report": {
    "brand_compliance_score": 0.85,
    "accessibility_score": 0.78,
    "best_practices_score": 0.80,
    "mobile_score": 0.88,
    "critical_issues": [],
    "warnings": [
      "CTA could be more prominent",
      "Consider increasing button contrast"
    ],
    "suggestions": [
      "Add alt text indicators for images",
      "Consider A/B testing subject line length"
    ],
    "cta": {
      "text": "Shop Now",
      "visibility_score": 0.75,
      "has_action_verb": true,
      "is_above_fold": true
    },
    "layout": {
      "has_header": true,
      "has_hero": true,
      "has_body": true,
      "has_footer": true,
      "has_unsubscribe": true,
      "image_text_ratio_ok": true,
      "score": 0.90
    },
    "brand_voice": {
      "is_compliant": true,
      "tone_match_score": 0.85,
      "vocabulary_issues": [],
      "recommendations": []
    }
  },
  "figma_url": "https://www.figma.com/file/ABC123?node-id=0:1",
  "indexed_to_vertex": true,
  "asana_task_gid": "1234567890123456"
}
```

---

### GET /api/figma-review/insights/{client_id}

List indexed review insights from Vertex AI.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max results (max: 100) |
| `insight_type` | string | null | Filter: `recurring_issue`, `best_practice`, `brand_pattern` |

**Response:**
```json
{
  "client_id": "rogue-creamery",
  "total": 3,
  "insights": [
    {
      "doc_id": "insight_rogue-creamery_abc12345",
      "email_name": "Summer Sale Email",
      "insight_type": "best_practice",
      "severity": "suggestion",
      "overall_score": 0.85,
      "created_at": "2025-01-15T10:30:00Z",
      "related_issues": ["accessibility", "cta"]
    }
  ]
}
```

---

### DELETE /api/figma-review/clear/{client_id}

Clear all review state and history for a client. Does NOT delete Vertex AI insights.

**Response:**
```json
{
  "status": "success",
  "client_id": "rogue-creamery",
  "records_cleared": 15,
  "message": "Review state cleared. Next review will process all frames fresh."
}
```

---

### GET /api/figma-review/health

Health check with configuration status.

**Response:**
```json
{
  "status": "healthy",
  "figma_configured": true,
  "gemini_configured": true,
  "rag_url": "http://localhost:8003",
  "gcp_project": "emailpilot-438321",
  "vertex_data_store": "your-data-store-id",
  "asana_configured": true
}
```

Status values:
- `healthy` - All systems operational
- `degraded` - Missing non-critical configuration

---

### GET /api/figma-review/file/{file_key}/stats

Get review statistics for a specific Figma file.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_id` | string | Yes | Client identifier |

**Response:**
```json
{
  "file_key": "ABC123",
  "client_id": "rogue-creamery",
  "total_reviews": 12,
  "average_score": 0.78,
  "last_reviewed_at": "2025-01-15T10:30:00Z",
  "common_issues": [
    "CTA visibility",
    "Mobile touch targets"
  ]
}
```

---

## Scoring System

### Overall Score Calculation

```python
overall_score = (
    brand_compliance_score * 0.30 +   # 30% weight
    accessibility_score * 0.25 +       # 25% weight
    best_practices_score * 0.25 +      # 25% weight
    mobile_score * 0.20                # 20% weight
)
```

### Score Thresholds

| Score Range | Status | Emoji | Action |
|-------------|--------|-------|--------|
| 85% - 100% | Excellent | ✅ | Ready to send |
| 70% - 84% | Good | 🟡 | Minor improvements suggested |
| 50% - 69% | Needs Work | 🟠 | Address warnings before sending |
| 0% - 49% | Critical | 🔴 | Must fix critical issues |

### Issue Severity

| Severity | Description | Examples |
|----------|-------------|----------|
| **Critical** | Must fix before sending | Missing unsubscribe link, spam triggers |
| **Warning** | Should address if possible | Low contrast, long subject line |
| **Suggestion** | Nice-to-have improvements | A/B testing ideas, accessibility enhancements |

---

## Integrations

### Figma Integration

The pipeline connects to Figma REST API to:
- Fetch file structure and metadata
- Identify email frames by dimensions (320-800px width)
- Export frames as PNG images for vision analysis
- Track file versions for incremental sync

**Required**: `FIGMA_ACCESS_TOKEN` with read access to target files.

### Asana Integration

The pipeline integrates with Asana for:
- **Trigger**: "Messaging Stage" field change to "AI Email Review"
- **Input**: Figma URL from task custom field
- **Output**: Formatted review comment posted to task

**Field Identification**: Uses GIDs (not display names) for reliability.

### RAG Integration

Queries the existing RAG service at `/api/rag/search` for:
- Brand voice guidelines
- Tone and vocabulary standards
- Past campaign patterns
- Content pillars and messaging

### Vertex AI Integration

Indexes review insights as `category="proofing_insight"` for:
- Learning from past reviews
- Identifying recurring issues
- Building best practice examples
- Searchable knowledge base

---

## Directory Structure

```
pipelines/figma-email-review/
├── __init__.py                     # Package init, version info
├── README.md                       # This file
├── WORKFLOW.md                     # Current session tracking
├── NEXT_STEPS.md                   # Future work backlog
│
├── config/
│   ├── __init__.py                 # Exports configuration classes
│   ├── settings.py                 # Dataclass configuration
│   │   ├── FigmaConfig             # Figma API settings
│   │   ├── VisionConfig            # Gemini Vision settings
│   │   ├── RAGConfig               # RAG service settings
│   │   ├── AsanaConfig             # Asana field GIDs
│   │   ├── BestPracticesConfig     # Evaluation thresholds
│   │   └── PipelineConfig          # Main config aggregator
│   └── client_mappings.yaml        # Optional fallback mappings
│
├── core/
│   ├── __init__.py                 # Exports all core classes
│   ├── figma_client.py             # Figma REST API wrapper
│   │   ├── FigmaClient             # Async API client
│   │   ├── FigmaFrame              # Frame data model
│   │   └── EmailDesign             # Design data model
│   ├── vision_analyzer.py          # Gemini Vision analysis
│   │   ├── EmailVisionAnalyzer     # Vision API wrapper
│   │   └── EmailVisionAnalysis     # Analysis result model
│   ├── rag_integration.py          # Brand voice RAG queries
│   │   ├── RAGBrandVoiceChecker    # RAG query client
│   │   └── BrandVoiceComplianceResult
│   ├── best_practices.py           # Email evaluation rules
│   │   ├── EmailBestPracticesEvaluator
│   │   └── EmailReviewReport       # Full report model
│   ├── state_manager.py            # Firestore state tracking
│   │   └── FigmaReviewStateManager
│   ├── vertex_ingestion.py         # Vertex AI insight indexing
│   │   └── FigmaReviewVertexIngestion
│   ├── asana_poster.py             # Post results to Asana
│   │   └── AsanaResultPoster
│   └── review_orchestrator.py      # Main workflow coordinator
│       ├── FigmaEmailReviewOrchestrator
│       └── create_orchestrator_from_config()
│
├── api/
│   ├── __init__.py
│   └── routes.py                   # FastAPI router
│       ├── POST /review
│       ├── GET /reports/{client_id}
│       ├── GET /reports/{client_id}/{review_id}
│       ├── DELETE /clear/{client_id}
│       ├── GET /insights/{client_id}
│       ├── GET /health
│       └── GET /file/{file_key}/stats
│
└── docs/
    └── workflow.md                 # Technical workflow documentation
```

---

## Development

### Running Locally

```bash
# Navigate to RAG service
cd /Users/Damon/emailpilot/spokes/RAG

# Set environment variables
export FIGMA_ACCESS_TOKEN=figd_xxx
export GEMINI_API_KEY=xxx
export GCP_PROJECT_ID=emailpilot-438321

# Start service
uvicorn app.main:app --port 8003 --reload

# Verify pipeline loaded
curl http://localhost:8003/api/figma-review/health
```

### Running Tests

```bash
cd /Users/Damon/emailpilot/spokes/RAG
pytest pipelines/figma-email-review/tests/ -v
```

### Manual Testing

```bash
# Trigger a review
curl -X POST http://localhost:8003/api/figma-review/review \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "test-client",
    "figma_url": "https://www.figma.com/file/ABC123/Email",
    "post_results_to_asana": false
  }'

# Check results (after background processing)
curl http://localhost:8003/api/figma-review/reports/test-client
```

### Adding New Evaluation Rules

1. Add rule to `core/best_practices.py` in appropriate method
2. Update `EmailReviewReport` model if new fields needed
3. Adjust score weights if adding new category
4. Update documentation

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "FIGMA_ACCESS_TOKEN not configured" | Missing env var | Set `FIGMA_ACCESS_TOKEN` |
| "GEMINI_API_KEY not configured" | Missing env var | Set `GEMINI_API_KEY` |
| "Could not parse Figma file key" | Invalid URL format | Use full Figma URL |
| "Frame not found" | Invalid node-id | Verify node-id exists in file |
| Empty reports list | No reviews completed | Check background task logs |

### Debugging

```bash
# Check service logs
docker logs emailpilot-rag --tail 100 -f

# Or if running locally
uvicorn app.main:app --port 8003 --reload --log-level debug

# Test Figma API access
curl -H "X-Figma-Token: $FIGMA_ACCESS_TOKEN" \
  "https://api.figma.com/v1/files/ABC123"
```

### Health Check Failures

If `/health` returns `degraded`:

1. Check environment variables are set
2. Verify GCP credentials for Firestore/Vertex AI
3. Confirm Figma token has read access
4. Test RAG service connectivity

---

## Related Documentation

- [Workflow Details](docs/workflow.md) - Technical workflow documentation
- [Image Repository Pipeline](../image-repository/README.md) - Similar architecture pattern
- [RAG Service](../../README.md) - Parent service documentation
- [EmailPilot CLAUDE.md](../../../../CLAUDE.md) - Project-wide development guide
