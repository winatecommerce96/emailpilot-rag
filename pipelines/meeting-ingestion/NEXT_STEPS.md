# Meeting Intelligence Pipeline - Next Steps

**Last Updated:** January 29, 2026

---

## Completed (v2.0)

- [x] Google OAuth flow with Firestore token persistence
- [x] Per-user calendar authentication (not shared credentials)
- [x] 60-day initial scan on first connection
- [x] Weekly scheduled scan endpoint for Cloud Scheduler
- [x] Scan state tracking (initial_scan_completed, last_scan_at, clients_scanned)
- [x] Gemini 2.0 Flash integration with google-genai SDK
- [x] UI redesign with step indicators and modular components
- [x] Manual backfill button (force re-scan 60 days)
- [x] Quick Scan (24h) for single client
- [x] Fixed OAuth scope mismatch errors
- [x] Docker networking fix (host.docker.internal)

---

## High Priority

### 1. Cloud Scheduler Deployment
**Status:** Ready to deploy
**Task:** Create the Cloud Scheduler job in GCP

```bash
gcloud scheduler jobs create http meeting-weekly-scan \
  --location=us-central1 \
  --schedule="0 2 * * 1" \
  --uri="https://rag.emailpilot.ai/api/meeting/weekly-scan?api_key=YOUR_KEY" \
  --http-method=POST \
  --attempt-deadline=1800s
```

### 2. Production OAuth Redirect URI
**Status:** Needs configuration
**Task:** Add `https://rag.emailpilot.ai/api/meeting/callback` to Google Cloud Console OAuth credentials

### 3. Test Full Pipeline End-to-End
**Status:** Pending
**Tasks:**
- [ ] Connect calendar with real account
- [ ] Verify 60-day scan processes meetings
- [ ] Confirm transcripts are found and analyzed
- [ ] Verify intelligence appears in Vertex AI
- [ ] Test search returns meeting intelligence

---

## Medium Priority

### 4. Improve Transcript Detection
**Status:** Enhancement needed
**Issue:** Current scanner only looks at event attachments for transcripts
**Tasks:**
- [ ] Search Google Drive for Meet recordings in meeting timeframe
- [ ] Handle various transcript naming conventions
- [ ] Support audio transcription if no text transcript exists

### 5. Client Domain Mapping
**Status:** Enhancement needed
**Issue:** Scanner doesn't automatically match attendee emails to clients
**Tasks:**
- [ ] Pull client domain mappings from Orchestrator
- [ ] Auto-detect client based on attendee domains
- [ ] Filter scans by matched clients only

### 6. Scan Progress UI
**Status:** Enhancement needed
**Tasks:**
- [ ] Show real-time progress during 60-day scan
- [ ] Display which client is currently being scanned
- [ ] Show count of meetings found vs processed

### 7. Error Handling & Retry
**Status:** Enhancement needed
**Tasks:**
- [ ] Implement retry logic for failed Gemini calls
- [ ] Handle rate limits gracefully
- [ ] Add dead-letter queue for failed meetings

---

## Low Priority

### 8. OIDC Authentication for Cloud Scheduler
**Status:** Nice to have
**Task:** Replace API key auth with service account OIDC tokens

### 9. Meeting Deduplication
**Status:** Nice to have
**Issue:** Same meeting could be processed multiple times
**Task:** Track processed event_ids to prevent duplicates

### 10. Intelligence Preview in UI
**Status:** Nice to have
**Tasks:**
- [ ] Show recent meeting briefs on the UI
- [ ] Allow viewing full intelligence documents
- [ ] Add filters by date/client

### 11. Metrics & Monitoring
**Status:** Nice to have
**Tasks:**
- [ ] Track scan success/failure rates
- [ ] Monitor Gemini API usage
- [ ] Alert on failed weekly scans

---

## Known Issues

1. **Server restart required for route changes** - The `--reload` flag doesn't always pick up changes in the `pipelines/` directory. Full restart needed.

2. **Icon "history" was missing** - Added to ui.jsx ICON_PATHS. Rebuild UI after changes.

3. **Docker can't reach localhost services** - Use `host.docker.internal` in ORCHESTRATOR_URL when running in Docker.

---

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| google-genai | >=1.0.0 | Gemini AI processing |
| google-cloud-firestore | >=2.19.0 | Token & state storage |
| google-auth-oauthlib | - | OAuth flow |
| google-api-python-client | - | Calendar/Drive APIs |
| httpx | - | Manual token exchange |

---

## Files Modified (v2.0 Session)

| File | Changes |
|------|---------|
| `pipelines/meeting-ingestion/core/auth.py` | Firestore persistence, manual token exchange |
| `pipelines/meeting-ingestion/core/processor.py` | google-genai SDK migration |
| `pipelines/meeting-ingestion/core/scheduler.py` | NEW - Scan state tracking |
| `pipelines/meeting-ingestion/api/routes.py` | Added initial-scan, scan-status, weekly-scan endpoints |
| `pipelines/meeting-ingestion/config/settings.py` | Added INITIAL_SCAN_DAYS, WEEKLY_SCAN_DAYS |
| `ui/src/components/CalendarConnect.jsx` | Modular refactor, backfill button |
| `ui/src/components/MeetingIntelligence.jsx` | Layout redesign with step indicators |
| `ui/src/components/ui.jsx` | Added history, clock icons |
| `.env` | ORCHESTRATOR_URL changed to host.docker.internal |
