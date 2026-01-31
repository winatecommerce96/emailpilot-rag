# Figma Email Review Pipeline - Workflow Documentation

## Overview

The Figma Email Review Pipeline is a "proofing manager" that analyzes email designs from Figma for quality, brand compliance, and best practices. It integrates with Asana for workflow automation and stores insights in Vertex AI for continuous learning.

## Trigger Flow

```
┌──────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Asana Task      │────▶│  Asana Webhook Hub   │────▶│  Pub/Sub Topic  │
│ Stage: "AI       │     │  (existing service)  │     │ asana-stage-    │
│ Email Review"    │     │  /webhooks/asana     │     │ changes         │
└──────────────────┘     └──────────────────────┘     └─────────────────┘
                                                              │
                                                              ▼
┌──────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│  Review Results  │◀────│  Figma Email Review  │◀────│  Orchestrator   │
│  posted back to  │     │  Pipeline (RAG)      │     │  Pub/Sub        │
│  Asana task      │     │  /api/figma-review/* │     │  Subscriber     │
└──────────────────┘     └──────────────────────┘     └─────────────────┘
```

### How It Works

1. Designer changes Asana task's "Messaging Stage" to "AI Email Review"
2. Asana webhook fires → Webhook Hub receives the event
3. Webhook Hub publishes to `asana-stage-changes` Pub/Sub topic
4. Orchestrator subscriber filters for `stage == "AI Email Review"`
5. Subscriber extracts Figma URL from task custom field (by GID)
6. Calls `/api/figma-review/review` with the Figma URL
7. Pipeline runs full analysis in background
8. Results posted back to Asana task as formatted comment

## Review Workflow

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

### Detailed Steps

1. **Parse Figma URL**: Extract `file_key` and optional `node_id`
2. **Check Review Status**: Version comparison for incremental sync
3. **Identify Email Frames**: Find frames matching email dimensions
4. **Export as Images**: Get PNG exports via Figma API
5. **Vision Analysis**: Gemini Vision analyzes layout, visuals, accessibility
6. **Brand Voice Check**: Query RAG for client's brand guidelines
7. **Best Practices Evaluation**: Check against email marketing standards
8. **Generate Report**: Comprehensive EmailReviewReport with scores
9. **Store Results**: Save to Firestore for history
10. **Index Insights**: Add to Vertex AI for future retrieval
11. **Post to Asana**: Formatted comment with scores and issues

## Scoring System

### Overall Score Calculation

```python
overall_score = (
    brand_compliance * 0.30 +
    accessibility * 0.25 +
    best_practices * 0.25 +
    mobile_readiness * 0.20
)
```

### Score Thresholds

| Score | Status | Emoji |
|-------|--------|-------|
| ≥ 85% | Excellent | ✅ |
| ≥ 70% | Good | 🟡 |
| ≥ 50% | Needs Work | 🟠 |
| < 50% | Critical | 🔴 |

## Component Details

### Figma Client (`core/figma_client.py`)

- Fetches file structure and metadata
- Identifies email frames by dimensions (320-800px width)
- Exports frames as PNG images
- Extracts text content from designs

### Vision Analyzer (`core/vision_analyzer.py`)

Uses Gemini Vision to analyze:
- **Layout**: Header, hero, body, CTA, footer presence
- **Visual Elements**: Colors, imagery, whitespace
- **CTA**: Visibility, clarity, placement
- **Accessibility**: Contrast, alt text indicators
- **Mobile Readiness**: Single column, touch targets
- **Copy**: Headline, subheadline, body, CTA text

### RAG Integration (`core/rag_integration.py`)

Queries the RAG service for:
- Brand voice guidelines
- Tone and vocabulary standards
- Past campaign patterns
- Compliance checking with AI interpretation

### Best Practices Evaluator (`core/best_practices.py`)

Checks against email marketing standards:
- Subject line length and spam triggers
- CTA clarity and visibility
- Image-to-text ratio
- Footer requirements (unsubscribe, address)
- Mobile responsiveness

### State Manager (`core/state_manager.py`)

Firestore collections:
- `figma_review_state`: Per-file review status
- `figma_review_emails`: Individual review records

Features:
- Version-based incremental sync
- Review history tracking
- Deduplication support

### Vertex Ingestion (`core/vertex_ingestion.py`)

Indexes review insights as `category="proofing_insight"`:
- Recurring issues
- Best practice examples
- Brand patterns
- Searchable for future reviews

## Configuration

### Environment Variables

```bash
# Figma API
FIGMA_ACCESS_TOKEN=figd_xxx

# Asana Custom Field GIDs
ASANA_MESSAGING_STAGE_GID=1234567890123456
ASANA_FIGMA_URL_GID=1234567890123457
ASANA_CLIENT_FIELD_GID=1234567890123458

# AI/ML
GEMINI_API_KEY=xxx

# GCP
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=xxx
GCP_LOCATION=us
```

### Asana Integration

The pipeline identifies custom fields by GID (not display name) for reliability:
- `ASANA_MESSAGING_STAGE_GID`: The "Messaging Stage" dropdown field
- `ASANA_FIGMA_URL_GID`: The "Figma URL" text field
- `ASANA_CLIENT_FIELD_GID`: The "Client" field for client identification

## Error Handling

### Retry Logic
- Figma API: 3 retries with exponential backoff
- Vision API: 2 retries
- RAG queries: Fallback to empty compliance result

### Graceful Degradation
- Missing brand voice: Review continues without brand check
- Figma export failure: Skip frame, continue with others
- Asana post failure: Log error, don't block review completion

## Monitoring

### Health Check
`GET /api/figma-review/health` returns:
- Configuration status
- Service connectivity
- Missing credentials warnings

### Logging
All components use Python logging with:
- INFO: Normal operations
- WARNING: Non-critical issues
- ERROR: Failures requiring attention
