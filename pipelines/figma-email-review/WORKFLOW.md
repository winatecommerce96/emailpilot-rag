# Figma Email Review Pipeline - Current Workflow

> **Last Updated**: 2025-12-30
> **Session Focus**: Pipeline Implementation Complete
> **Status**: Core functionality implemented, ready for integration testing

---

## Active Context

### Current Objective
Build a "proofing manager" pipeline that analyzes email designs from Figma for quality, brand compliance, and best practices. The pipeline is triggered from Asana when the "Messaging Stage" field changes to "✨ AI Email Review".

**Deployment Requirement (P0)**: Ensure everything is working perfectly in Cloud Run. The [Intelligence Hub](https://rag.emailpilot.ai) needs to be used and accessible. Currently, the front end is not connecting to backend information, which must be resolved.

### Recent Updates (2026-02-05)
- **UI schema alignment**: Updated `ui/email-review.html` to match the backend report schema (CTA + layout fields).
- **Brief alignment wiring**: Review orchestrator now loads brief context from the Asana task description (`notes`) and includes it in the compliance prompt.
- **Rollback toggle**: Set `EMAIL_REVIEW_BRIEF_ENABLED=false` to disable brief lookup without code changes.
- **Stage gating**: Asana tasks are filtered/validated against `Messaging Stage = "✨ AI Email Review"` before review. Roll back with `EMAIL_REVIEW_STAGE_ENFORCED=false`.

### Key Decisions Made

| Decision | Rationale | Date |
|----------|-----------|------|
| Use Asana custom field GIDs | More reliable than display names which can change | 2025-12-30 |
| Lazy initialization pattern | Avoid loading heavy dependencies until needed | 2025-12-30 |
| Background task processing | Prevent API timeouts for long-running reviews | 2025-12-30 |
| Weighted scoring system | Different aspects have different importance (brand 30%, accessibility 25%, etc.) | 2025-12-30 |
| Store insights in Vertex AI | Enable learning from past reviews for future recommendations | 2025-12-30 |
| Follow image-repository patterns | Consistency with existing pipeline architecture | 2025-12-30 |

---

## Session Progress

### Completed This Session

**Directory Structure & Configuration:**
- [x] Created `pipelines/figma-email-review/` directory structure
- [x] Created all `__init__.py` files for proper Python packaging
- [x] Created `config/settings.py` with dataclass configuration
- [x] Created `config/client_mappings.yaml` for optional fallback mappings

**Core Components:**
- [x] `core/figma_client.py` - Figma REST API wrapper with async methods
- [x] `core/vision_analyzer.py` - Gemini Vision email design analysis
- [x] `core/rag_integration.py` - Brand voice compliance via RAG queries
- [x] `core/best_practices.py` - Email marketing standards evaluation
- [x] `core/state_manager.py` - Firestore state tracking and history
- [x] `core/vertex_ingestion.py` - Vertex AI insight indexing
- [x] `core/asana_poster.py` - Post results back to Asana tasks
- [x] `core/review_orchestrator.py` - Main workflow coordinator

**API Layer:**
- [x] `api/routes.py` - FastAPI router with all endpoints
- [x] Registered router in main RAG app (`app/main.py`)

**Documentation:**
- [x] `docs/workflow.md` - Technical workflow documentation
- [x] `README.md` - API reference and quick start
- [x] `WORKFLOW.md` - This file (session tracking)
- [x] `NEXT_STEPS.md` - Future work backlog

---

## Files Created This Session

### Configuration
```
pipelines/figma-email-review/
├── __init__.py                          # Package init with version
├── config/
│   ├── __init__.py                      # Exports config classes
│   ├── settings.py                      # Dataclass configuration (~200 lines)
│   └── client_mappings.yaml             # Optional fallback mappings
```

### Core Components
```
├── core/
│   ├── __init__.py                      # Exports all core classes
│   ├── figma_client.py                  # Figma API wrapper (~300 lines)
│   ├── vision_analyzer.py               # Gemini Vision analysis (~350 lines)
│   ├── rag_integration.py               # RAG brand voice queries (~250 lines)
│   ├── best_practices.py                # Email evaluation rules (~450 lines)
│   ├── state_manager.py                 # Firestore state tracking (~200 lines)
│   ├── vertex_ingestion.py              # Vertex AI indexing (~350 lines)
│   ├── asana_poster.py                  # Asana result posting (~225 lines)
│   └── review_orchestrator.py           # Main orchestrator (~500 lines)
```

### API Layer
```
├── api/
│   ├── __init__.py
│   └── routes.py                        # FastAPI endpoints (~420 lines)
```

### Documentation
```
├── docs/
│   └── workflow.md                      # Technical workflow docs
├── README.md                            # API reference
├── WORKFLOW.md                          # This file
└── NEXT_STEPS.md                        # Future work
```

### Modified Files
```
/Users/Damon/emailpilot/spokes/RAG/app/main.py
  └── Added router registration after line 988
```

---

## Technical Notes

### Component Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Figma Client   │────▶│ Vision Analyzer │────▶│ RAG Integration │
│ (fetch designs) │     │ (Gemini Vision) │     │ (brand voice)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  Review Orchestrator  │
                    │  (coordinate workflow)│
                    └───────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │Best Practices │   │ State Manager │   │Vertex Ingestion│
    │  Evaluator    │   │  (Firestore)  │   │  (insights)   │
    └───────────────┘   └───────────────┘   └───────────────┘
```

### Scoring System

| Category | Weight | Checks |
|----------|--------|--------|
| Brand Compliance | 30% | Voice, tone, vocabulary, guidelines |
| Accessibility | 25% | Contrast, alt text, readability |
| Best Practices | 25% | Subject line, CTA, layout, footer |
| Mobile Readiness | 20% | Responsive, touch targets, width |

### Firestore Collections

| Collection | Purpose |
|------------|---------|
| `figma_review_state` | Per-file review status and version tracking |
| `figma_review_emails` | Individual review records with full reports |

### Environment Variables Required

```bash
# Figma API
FIGMA_ACCESS_TOKEN=figd_xxx

# Asana Custom Field GIDs
ASANA_MESSAGING_STAGE_GID=xxx
ASANA_FIGMA_URL_GID=xxx
ASANA_CLIENT_FIELD_GID=xxx

# AI/ML
GEMINI_API_KEY=xxx

# GCP
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=xxx
GCP_LOCATION=us
```

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/figma-review/review` | Trigger email design review |
| GET | `/api/figma-review/reports/{client_id}` | List review reports |
| GET | `/api/figma-review/reports/{client_id}/{review_id}` | Get full report |
| DELETE | `/api/figma-review/clear/{client_id}` | Clear client state |
| GET | `/api/figma-review/insights/{client_id}` | List indexed insights |
| GET | `/api/figma-review/health` | Health check |
| GET | `/api/figma-review/file/{file_key}/stats` | File statistics |

---

## Testing Plan

### Test 1: Health Check
```bash
curl http://localhost:8003/api/figma-review/health
```
Expected: Configuration status with service connectivity

### Test 2: Manual Review Trigger
```bash
curl -X POST http://localhost:8003/api/figma-review/review \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "test-client",
    "figma_url": "https://www.figma.com/file/ABC123/Email-Design",
    "post_results_to_asana": false
  }'
```
Expected: `{"status": "queued", "message": "..."}`

### Test 3: List Reports
```bash
curl http://localhost:8003/api/figma-review/reports/test-client
```
Expected: List of review summaries

---

## Handoff Notes

### For Next Session

The core pipeline is complete and registered with the RAG service. To enable the full Asana integration flow:

0. **Cloud Run Connectivity (P0)**: Fix the frontend connectivity issues at https://rag.emailpilot.ai to ensure it can talk to the backend services. This is the primary "Intelligence Hub" access point.

1. **Create Asana Pub/Sub Subscriber** in the orchestrator service
   - Location: `/orchestrator/app/services/integrations/asana/`
   - Subscribe to `asana-stage-changes` topic
   - Filter for `stage == "AI Email Review"` using GIDs
   - Call `/api/figma-review/review` endpoint

2. **Configure Environment Variables**
   - Get actual GIDs from Asana project settings
   - Set `FIGMA_ACCESS_TOKEN` with Figma API access
   - Ensure `GEMINI_API_KEY` is configured

3. **Test End-to-End Flow**
   - Change task stage in Asana
   - Verify review triggers and completes
   - Check results posted back to task

### Environment State
```bash
# Files created: 15 new files in pipelines/figma-email-review/
# Files modified: 1 (app/main.py - router registration)
# Router prefix: /api/figma-review
# Dependencies: google-cloud-discoveryengine, google-cloud-firestore, httpx, pydantic
```

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-30 | Initial pipeline implementation complete | Claude |
