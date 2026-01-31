# Meeting Intelligence Pipeline - Workflow

**Version:** 2.0 (January 2026)
**Purpose:** Automate extraction of strategic client context from Google Calendar meetings into Vertex AI RAG.
**Architecture:** FastAPI routes integrated into RAG service, Google OAuth, Firestore persistence, Gemini AI.

---

## 1. Executive Summary

This pipeline solves the "Context Clutter" problem by selectively ingesting high-value client interactions into the RAG system. Users connect their Google Calendar via OAuth, and the system:

1. **Initial Scan**: Scans 60 days of past meetings for all user's clients
2. **Weekly Scans**: Automatically scans the past week for new meetings
3. **AI Analysis**: Uses Gemini to extract strategic signals, ignoring small talk
4. **RAG Indexing**: Stores intelligence in Vertex AI for semantic search

### Key Capabilities

| Feature | Description |
|---------|-------------|
| **Per-User OAuth** | Each user authenticates with their own Google account |
| **Persistent Sessions** | OAuth tokens stored in Firestore, auto-refresh on expiry |
| **60-Day Backfill** | Initial scan captures 2 months of meeting history |
| **Weekly Automation** | Cloud Scheduler triggers scans for all authorized users |
| **Gemini Processing** | Extracts strategic directives, commercial signals, sentiment |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Meeting Intelligence                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │   User UI    │───▶│  OAuth Flow  │───▶│  Firestore Sessions  │   │
│  │  (React)     │    │  (Google)    │    │  (Token Storage)     │   │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
│         │                                          │                 │
│         ▼                                          ▼                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │  Calendar    │───▶│   Gemini     │───▶│    Vertex AI RAG     │   │
│  │  Scanner     │    │   Processor  │    │    (Ingestion)       │   │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Cloud Scheduler                            │   │
│  │                  (Weekly Trigger)                             │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. User Flow

### First-Time Connection

1. User navigates to `/ui/meeting-intelligence.html`
2. Clicks "Sign in with Google" button
3. Google OAuth consent screen appears (Calendar + Drive read-only scopes)
4. User grants permission
5. Callback stores tokens in Firestore, returns session ID
6. **Automatic 60-day backfill** triggers for all user's clients
7. UI shows scan progress

### Returning User

1. Session ID retrieved from localStorage
2. Connection status checked via `/api/meeting/status`
3. If tokens expired, auto-refresh occurs
4. User can trigger Quick Scan (24h) or Backfill (60 days)

### Weekly Automated Scan

1. Cloud Scheduler calls `/api/meeting/weekly-scan` every Monday
2. System queries Firestore for users due for scan (last_scan > 7 days)
3. For each user, scans past 7 days for all their clients
4. New intelligence indexed in Vertex AI

---

## 4. Component Details

### 4.1 OAuth Service (`core/auth.py`)

**Responsibilities:**
- Generate OAuth URLs with Calendar/Drive scopes
- Exchange authorization codes for tokens
- Store/retrieve tokens from Firestore
- Auto-refresh expired tokens
- Map sessions to user emails

**Firestore Collection:** `meeting_oauth_sessions`

```python
{
    "token": "ya29.xxx",
    "refresh_token": "1//xxx",
    "email": "user@example.com",
    "scopes": ["calendar.events.readonly", "drive.readonly", "userinfo.email"],
    "updated_at": "2026-01-29T12:00:00Z"
}
```

### 4.2 Calendar Scanner (`core/scanner.py`)

**Responsibilities:**
- List calendar events within time window
- Filter for external meetings (non-company attendees)
- Retrieve transcript/recording attachments from Drive
- Extract document content from Google Docs transcripts

### 4.3 AI Processor (`core/processor.py`)

**Responsibilities:**
- Analyze transcripts using Gemini 2.0 Flash
- Extract structured intelligence:
  - Strategic directives
  - Commercial signals (promos, inventory)
  - Client sentiment
  - Topics detected

**Output Schema:**
```json
{
    "is_high_signal": true,
    "strategic_directives": ["Focus on sustainability messaging"],
    "commercial_signals": ["20% off sale next month"],
    "client_sentiment": "Positive - excited about new direction",
    "topics_detected": ["Q1 planning", "brand refresh"]
}
```

### 4.4 Scan State Manager (`core/scheduler.py`)

**Responsibilities:**
- Track initial scan completion per user
- Record which clients have been scanned
- Find users due for weekly scan
- Store scan results/timestamps

**Firestore Collection:** `meeting_scan_state`

```python
{
    "email": "user@example.com",
    "initial_scan_completed": true,
    "initial_scan_completed_at": "2026-01-29T12:00:00Z",
    "last_scan_at": "2026-01-29T12:00:00Z",
    "clients_scanned": ["client-a", "client-b"],
    "scan_results": {
        "client-a": {"scanned_at": "...", "meetings_found": 5}
    }
}
```

### 4.5 Vertex Ingestion (`core/ingestion.py`)

**Responsibilities:**
- Format intelligence into RAG-friendly documents
- Create documents in Vertex AI with metadata
- Tag with client_id, date, source="meeting_harvester"

---

## 5. API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/meeting/auth` | None | Start OAuth flow |
| `GET` | `/api/meeting/callback` | None | OAuth callback |
| `GET` | `/api/meeting/status` | Session | Check connection |
| `DELETE` | `/api/meeting/disconnect` | Session | Revoke access |
| `POST` | `/api/meeting/scan/{client_id}` | Session | Manual scan |
| `POST` | `/api/meeting/initial-scan` | Session | 60-day backfill |
| `GET` | `/api/meeting/scan-status` | Session | Get progress |
| `POST` | `/api/meeting/weekly-scan` | API Key | Scheduled scan |

---

## 6. Configuration

### Environment Variables

```bash
# Google OAuth
GOOGLE_OAUTH_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-xxx
MEETING_OAUTH_REDIRECT_URI=http://localhost:8003/api/meeting/callback

# Gemini AI
GEMINI_API_KEY=AIzaSyxxx

# Internal service key (for scheduled scans)
INTERNAL_SERVICE_KEY=your-secure-key

# GCP Project
GOOGLE_CLOUD_PROJECT=emailpilot-438321
```

### Settings (`config/settings.py`)

```python
SCOPES = [
    'calendar.events.readonly',
    'drive.readonly',
    'userinfo.email'
]
INITIAL_SCAN_DAYS = 60   # Backfill on first connection
WEEKLY_SCAN_DAYS = 7     # Weekly automated scans
LOOKBACK_HOURS = 24      # Default manual scan
```

---

## 7. Cloud Scheduler Setup

```bash
gcloud scheduler jobs create http meeting-weekly-scan \
  --location=us-central1 \
  --schedule="0 2 * * 1" \
  --uri="https://rag.emailpilot.ai/api/meeting/weekly-scan?api_key=YOUR_KEY" \
  --http-method=POST \
  --attempt-deadline=1800s \
  --description="Weekly meeting intelligence scan"
```

---

## 8. UI Components

### MeetingIntelligence.jsx

Main page with:
- Header with client selector and connection status
- Step progress indicator (Connect → Select → Scan)
- Scan controls card (Quick Scan / Backfill buttons)
- Search interface with results

### CalendarConnect.jsx (Modular Components)

- `ConnectionStatus` - Shows connected/disconnected badge
- `GoogleSignInButton` - Official Google branding OAuth button
- `ScanControls` - Quick Scan + Backfill buttons
- `MeetingSearch` - Search input + results display
- `useCalendarConnect` - React hook for state management

---

## 9. Security Considerations

### OAuth Token Storage
- Tokens encrypted at rest in Firestore
- Refresh tokens used to maintain access
- Session IDs are SHA-256 hashes of user emails

### API Protection
- Weekly scan endpoint requires `INTERNAL_SERVICE_KEY`
- User endpoints require valid session_id
- No PII logged to console

### Scope Minimization
- Read-only Calendar access
- Read-only Drive access (for transcripts)
- Email scope only for user identification

---

## 10. Troubleshooting

### OAuth "Scope Changed" Error
**Cause:** Google returning different scopes than requested
**Fix:** Manual token exchange bypasses strict scope checking

### 404 on New Endpoints
**Cause:** Server not restarted after code changes
**Fix:** Full restart of uvicorn (--reload may not catch pipeline changes)

### Docker Can't Reach Orchestrator
**Cause:** `localhost:8001` doesn't work inside container
**Fix:** Use `host.docker.internal:8001` for ORCHESTRATOR_URL

---

## 11. Changelog

### v2.0 (January 2026)
- Implemented full OAuth flow with Firestore persistence
- Added 60-day initial scan on first connection
- Added weekly scheduled scans via Cloud Scheduler
- Redesigned UI with step indicators and modular components
- Updated to google-genai SDK for Gemini processing
- Fixed scope mismatch errors with manual token exchange

### v1.0 (Initial Design)
- Original architecture document
- Cloud Functions-based design (not implemented)
