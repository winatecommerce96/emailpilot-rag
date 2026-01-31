# Figma Email Review Pipeline - Next Steps

> **Last Updated**: 2025-12-30
> **Priority Legend**: P0 = Critical | P1 = High | P2 = Medium | P3 = Low

---

## Immediate (Required for Production)

### P0 - Critical

These items are required before the pipeline can be used in production.

#### Asana Pub/Sub Subscriber - COMPLETED
**Location**: `/orchestrator/app/services/integrations/asana/email_review_subscriber.py`

The subscriber has been created with:
- `EmailReviewSubscriber` class that handles Pub/Sub messages
- Filters for `stage == "AI Email Review"` using field GIDs
- Extracts Figma URL and client from custom fields by GID
- Triggers the `/api/figma-review/review` endpoint

**API Endpoints Created** (`/orchestrator/app/api/routers/email_review_api.py`):
- `POST /api/pubsub/email-review` - Receives Pub/Sub push notifications
- `GET /api/pubsub/email-review/status` - Subscriber configuration status
- `POST /api/asana/tasks/{task_gid}/comment` - Post comments to Asana tasks
- `PUT /api/asana/tasks/{task_gid}` - Update Asana task custom fields
- `GET /api/email-review/health` - Health check

#### Create the Pub/Sub Subscription
Run this command to create the subscription in GCP:

```bash
gcloud pubsub subscriptions create asana-email-review-sub \
  --topic=asana-stage-changes \
  --project=emailpilot-438321 \
  --push-endpoint=https://YOUR-ORCHESTRATOR-URL/api/pubsub/email-review \
  --push-auth-service-account=pubsub-invoker@emailpilot-438321.iam.gserviceaccount.com \
  --ack-deadline=600 \
  --message-retention-duration=7d
```

#### Environment Variable Configuration
- [ ] Get actual Asana custom field GIDs from project settings
- [ ] Configure `FIGMA_ACCESS_TOKEN` with production Figma account
- [ ] Verify `GEMINI_API_KEY` has sufficient quota
- [ ] Set up `VERTEX_DATA_STORE_ID` for proofing insights

Required environment variables:
```bash
ASANA_MESSAGING_STAGE_GID=xxx   # "Messaging Stage" dropdown field GID
ASANA_FIGMA_URL_GID=xxx         # "Figma URL" text field GID
ASANA_CLIENT_FIELD_GID=xxx      # "Client" field GID
RAG_SERVICE_URL=http://localhost:8003
```

**Effort**: Low (1-2 hours)

#### End-to-End Testing
- [ ] Test Asana webhook → Pub/Sub flow
- [ ] Test pipeline execution with real Figma designs
- [ ] Verify results post correctly to Asana
- [ ] Test with multiple concurrent reviews

**Effort**: Medium (3-4 hours)

---

## Short Term (This Week)

### P1 - High Priority

#### Orchestrator Asana Endpoint - COMPLETED
The `AsanaResultPoster` posts to `/api/asana/tasks/{gid}/comment` on the orchestrator. This endpoint has been created.

**Location**: `/orchestrator/app/api/routers/email_review_api.py`

#### Error Recovery & Retry Logic
- [ ] Add retry logic for Figma API failures (rate limits, timeouts)
- [ ] Add retry logic for Gemini Vision failures
- [ ] Implement job status tracking in Firestore
- [ ] Add webhook for job completion notifications

**Effort**: Medium (4-6 hours)

#### Review Queue Management
- [ ] Prevent duplicate reviews for same frame
- [ ] Add job prioritization (newer requests first)
- [ ] Implement review timeout and cleanup
- [ ] Add job cancellation support

**Effort**: Medium (4-6 hours)

### P1 - High Priority (UI)

#### Email Review UI Dashboard
Create a UI for the Email Review pipeline and add it to the RAG navigation menu:

**Navigation Integration:**
- [ ] Add "Email Review" link to RAG/Visual RAG menu bar
- [ ] Create `/spokes/RAG/ui/email-review.html` page
- [ ] Match existing RAG UI styling and patterns

**Dashboard Features:**
- [ ] Client selector dropdown
- [ ] List of recent reviews per client with scores
- [ ] Detailed report view with:
  - Overall score with visual indicator
  - Score breakdown (Brand, Accessibility, Best Practices, Mobile)
  - Critical issues list
  - Warnings and suggestions
  - Link to Figma design
  - Link to Asana task
- [ ] Trigger manual review button
- [ ] Filter by score/issues
- [ ] Trend charts over time (optional)

**API Endpoints to Use:**
- `GET /api/figma-review/reports/{client_id}` - List reviews
- `GET /api/figma-review/reports/{client_id}/{review_id}` - Get report detail
- `POST /api/figma-review/review` - Trigger manual review
- `GET /api/figma-review/health` - Status check

**Location**: `/spokes/RAG/ui/email-review.html`
**Effort**: Medium-High (6-8 hours)

### P2 - Medium Priority

#### Enhanced Vision Analysis
- [ ] Add subject line analysis from Figma text layers
- [ ] Detect preheader text separately
- [ ] Analyze email width variants (desktop vs mobile)
- [ ] Add dark mode compatibility check

**Effort**: Medium (4-6 hours)

#### Improved Brand Voice Checking
- [ ] Cache RAG results for faster subsequent checks
- [ ] Add specific vocabulary checking (forbidden words)
- [ ] Compare against past approved emails
- [ ] Add brand color palette validation

**Effort**: Medium (4-6 hours)

---

## Backlog (Future)

### P2 - Medium Priority

#### Batch Review Capability
Allow reviewing multiple emails at once:
- [ ] Accept list of Figma URLs
- [ ] Parallel processing with rate limiting
- [ ] Aggregate report across all emails
- [ ] Compare emails within same campaign

**Effort**: High (8-12 hours)

#### Historical Analysis
- [ ] Track score trends over time per client
- [ ] Identify recurring issues
- [ ] Generate monthly quality reports
- [ ] Alert on score degradation

**Effort**: Medium (6-8 hours)

#### A/B Variant Comparison
- [ ] Detect A/B variants in same Figma file
- [ ] Compare variants side by side
- [ ] Recommend which variant is stronger
- [ ] Check for sufficient differentiation

**Effort**: Medium-High (6-10 hours)

### P3 - Low Priority / Nice to Have

#### Figma Plugin
Create Figma plugin for in-editor reviews:
- [ ] One-click review trigger
- [ ] Inline issue annotations
- [ ] Score overlay on frames
- [ ] Fix suggestions

**Effort**: High (12-20 hours)

#### Slack Integration
- [ ] Send review summaries to Slack channel
- [ ] Critical issue alerts
- [ ] Weekly quality digest
- [ ] Interactive approval workflow

**Effort**: Medium (4-6 hours)

#### Machine Learning Improvements
- [ ] Train custom model on approved emails
- [ ] Learn client-specific patterns
- [ ] Predict review scores before full analysis
- [ ] Auto-suggest improvements

**Effort**: Very High (20+ hours)

---

## Technical Debt

| Item | Location | Effort | Impact |
|------|----------|--------|--------|
| Add comprehensive unit tests | `tests/` | Medium | High - Ensures reliability |
| Add integration tests | `tests/integration/` | Medium | High - Catches API issues |
| Add type hints throughout | All `core/` files | Low | Medium - Better IDE support |
| Add request validation | `api/routes.py` | Low | Medium - Better error messages |
| Add rate limiting | `api/routes.py` | Low | Medium - Prevents abuse |
| Add metrics/monitoring | All components | Medium | High - Production visibility |

---

## Feature Ideas

| Idea | Description | Complexity |
|------|-------------|------------|
| **Email Template Library** | Store reviewed emails as templates for future reference | Medium |
| **Competitor Analysis** | Compare client emails against industry benchmarks | High |
| **Accessibility Simulator** | Show how email appears with color blindness filters | Medium |
| **Send Time Optimization** | Suggest optimal send times based on past performance | High |
| **Subject Line Generator** | AI-generate subject line alternatives | Low |
| **Personalization Checker** | Verify merge tags and dynamic content | Medium |

---

## Dependencies

### Required for P0 Items

| Dependency | Status | Owner | Notes |
|------------|--------|-------|-------|
| Asana Webhook Hub | Exists | Platform | Needs to publish to topic |
| Pub/Sub Topic | Needs Creation | DevOps | `asana-stage-changes` |
| Orchestrator Asana API | Needs Verification | Backend | Comment posting endpoint |
| Figma Access Token | Needs Creation | Design | Read access to files |

### External Services

| Service | Used For | SLA Required |
|---------|----------|--------------|
| Figma API | Design export | 99.9% |
| Gemini Vision | Image analysis | 99% |
| Firestore | State storage | 99.9% |
| Vertex AI | Insight indexing | 99% |
| Asana API | Result posting | 99% |

---

## Blocked / Waiting

| Item | Blocked By | Owner | ETA |
|------|------------|-------|-----|
| Asana subscriber deployment | Pub/Sub topic creation | DevOps | TBD |
| Production testing | Staging environment | Platform | TBD |

---

## Recently Completed

| Item | Completed | Notes |
|------|-----------|-------|
| Core pipeline implementation | 2025-12-30 | All components created |
| API endpoints | 2025-12-30 | Full CRUD + health check |
| Router registration | 2025-12-30 | Integrated with RAG main.py |
| Documentation | 2025-12-30 | README, WORKFLOW, NEXT_STEPS |

---

## Notes for Future Development

### Architecture Decisions

- **Lazy Initialization**: Components are initialized on first use to avoid startup delays
- **Background Processing**: Reviews run in FastAPI BackgroundTasks to prevent timeouts
- **GID-based Field Lookup**: Asana fields identified by GID for reliability
- **Weighted Scoring**: Brand (30%), Accessibility (25%), Best Practices (25%), Mobile (20%)

### Key Files to Understand

| File | Purpose |
|------|---------|
| `core/review_orchestrator.py` | Main workflow logic |
| `core/best_practices.py` | Scoring rules and thresholds |
| `api/routes.py` | All API endpoints |
| `config/settings.py` | Configuration management |

### Testing Strategy

1. **Unit Tests**: Each core component in isolation
2. **Integration Tests**: Full pipeline with mocked external services
3. **E2E Tests**: Asana trigger → Review → Post results
4. **Load Tests**: Multiple concurrent reviews

### Monitoring Recommendations

- Track review duration per stage
- Alert on error rate > 5%
- Monitor Gemini Vision API usage
- Track Figma API rate limit headroom
