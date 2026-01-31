# RAG Service - Current Workflow

**Last Updated:** 2026-01-30

---

## Current Session (January 30, 2026)

### Intelligence Grading Pipeline - Complete Implementation

#### Feature Overview
Implemented a comprehensive Intelligence Gap Grading system that evaluates client knowledge base completeness for email calendar generation. The system:

1. **7-Dimension Evaluation**: Grades clients across Brand Foundation, Audience Intelligence, Product Knowledge, Historical Performance, Business Context, Operational Parameters, and Creative Assets
2. **Weighted Scoring**: Each dimension has configurable weights, with critical fields having higher impact
3. **A-F Grading Scale**: Overall grade with minimum "C" required for calendar generation
4. **Gap Detection**: Identifies missing information with actionable recommendations
5. **Quick Capture**: Provides prompts to quickly fill knowledge gaps

#### Files Created

```
pipelines/intelligence-grading/
├── __init__.py
├── config/
│   ├── __init__.py
│   ├── settings.py              # Configuration loading, dataclasses
│   └── requirements.yaml        # 500+ line YAML defining all dimensions/fields
├── core/
│   ├── __init__.py
│   ├── field_extractor.py       # Gemini AI field extraction with keyword fallback
│   └── grading_service.py       # Main grading logic, scoring, recommendations
└── api/
    ├── __init__.py
    └── routes.py                # 7 API endpoints
```

#### API Endpoints Added

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/intelligence/grade/{client_id}` | GET | Full AI-powered grading |
| `/api/intelligence/quick-assessment/{client_id}` | GET | Fast keyword-based estimate |
| `/api/intelligence/requirements` | GET | Get configuration/schema |
| `/api/intelligence/gaps/{client_id}` | GET | Get missing fields only |
| `/api/intelligence/ready/{client_id}` | GET | Check generation readiness |
| `/api/intelligence/quick-capture` | POST | Submit gap answers |
| `/api/intelligence/health` | GET | Pipeline health check |

#### UI Integration

Added "Intelligence Grade" tab to main React UI (`ui/src/app.jsx`):
- Run Full Analysis button (AI-powered with Gemini)
- Quick Assessment button (keyword-based)
- Overall grade display (A-F with percentage)
- Stats cards (documents analyzed, fields found, generation readiness)
- Dimension scores with progress bars
- Critical gaps list with importance badges
- Top recommendations with priority ranking
- Quick capture prompts for filling gaps

#### Grading Algorithm

```
Overall Score = Σ (dimension_score × dimension_weight)

Dimension Score = (earned_points / max_points) × 100

Field Points = base_points × (coverage / 100)
  - coverage from AI extraction (0-100%)
  - critical fields: 15 points
  - high importance: 10 points
  - medium importance: 5 points
  - low importance: 2 points
```

#### Grade Thresholds

| Grade | Minimum Score | Calendar Generation |
|-------|---------------|---------------------|
| A | 90% | ✅ Ready |
| B | 80% | ✅ Ready |
| C | 70% | ✅ Ready (minimum) |
| D | 50% | ⚠️ Limited quality |
| F | <50% | ❌ Insufficient |

---

### Image Repository - Data Connectivity Fixes & User OAuth Implementation

#### Problem Statement
Image Repository features (search, stats, thumbnails) were not working properly. Users needed ability to share their personal Drive folders with the pipeline.

#### Root Cause Analysis
Python module caching conflicts between pipelines. When multiple pipelines (image-repository, meeting-ingestion, email-repository, figma-feedback) were loaded, they shared cached `core` and `config` modules, causing wrong modules to be imported.

#### Fixes Implemented

##### 1. Module Import Fix
**Files Modified**: `app/main.py`, `pipelines/image-repository/api/routes.py`

Changed all pipeline imports to use isolated module loading:
```python
# In app/main.py - use spec_from_file_location for unique module names
spec = importlib.util.spec_from_file_location("image_repository_routes", image_routes_file)
image_routes_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_routes_module)
app.include_router(image_routes_module.router)

# In routes.py - clear module cache before imports
def _import_local(module_path: str):
    if not _image_repo_initialized:
        sys.path = [p for p in sys.path if 'pipelines' not in p or 'image-repository' in p]
        for mod_name in list(sys.modules.keys()):
            if mod_name in ('core', 'config') or mod_name.startswith('core.') or mod_name.startswith('config.'):
                del sys.modules[mod_name]
        _image_repo_initialized = True
    return importlib.import_module(module_path)
```

##### 2. Thumbnail Proxy Fix
**File**: `pipelines/image-repository/api/routes.py` line 504

Fixed attribute name: `orchestrator.drive_client` → `orchestrator.drive`

##### 3. Vertex AI Fallback for Stats
**File**: `pipelines/image-repository/api/routes.py` lines 352-368

When Firestore shows 0 indexed images, now falls back to Vertex AI direct query to get actual count.

##### 4. Health Check Feedback
**File**: `ui/image-repository.html`

Added toast notifications for health check results (healthy, degraded, error).

#### New Feature: User OAuth Folder Sharing

##### Files Created
| File | Purpose |
|------|---------|
| `pipelines/image-repository/core/oauth_manager.py` | OAuthTokenManager class with Fernet encryption |

##### Endpoints Added (routes.py lines 930-1130)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/images/oauth/authorize` | POST | Create OAuth authorization URL |
| `/api/images/oauth/callback` | GET | Handle callback, exchange code for tokens |
| `/api/images/oauth/status/{user_id}` | GET | Check user's OAuth status |
| `/api/images/oauth/revoke/{user_id}` | POST | Revoke and delete tokens |
| `/api/images/oauth/user-folders/{user_id}` | GET | List user's Drive folders |

##### UI Updates (image-repository.html)
- Added `currentUserId` and `userOAuthStatus` state tracking
- Added OAuth callback URL parameter handling
- Updated `showClientDetails()` modal with "Connect Google Drive" section
- Added `browseUserFolders()` for browsing user's Drive
- Added `addUserFolderToClient()` for adding folders to clients

##### Security Implementation
- Tokens encrypted using Fernet symmetric encryption
- Encryption key from `OAUTH_ENCRYPTION_KEY` env var or GCP Secret Manager
- Automatic token refresh when expired
- Token revocation with Google on disconnect
- State parameter for CSRF protection

##### Required Environment Variables
```bash
GOOGLE_OAUTH_CLIENT_ID=your-oauth-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8003/api/images/oauth/callback
OAUTH_ENCRYPTION_KEY=your-fernet-key  # Generate with: Fernet.generate_key()
```

---

## Previous Work: Email Repository Pipeline (January 29, 2026)

### What Was Built

A complete Email Repository Pipeline that:
1. Fetches promotional emails from Gmail via domain-wide delegation
2. Captures screenshots using Playwright headless browser
3. Categorizes emails with Gemini Vision AI (e-commerce focused categories)
4. Stores screenshots in Google Drive with organized folder structure
5. Indexes metadata in Vertex AI for semantic search
6. Tracks state in Firestore for incremental sync

### Files Created

```
pipelines/email-repository/
├── __init__.py
├── README.md
├── config/
│   ├── __init__.py
│   ├── settings.py              # Configuration classes, secret management
│   └── email_accounts.yaml      # Account configuration (needs update)
├── core/
│   ├── __init__.py
│   ├── gmail_client.py          # Gmail API with domain-wide delegation
│   ├── screenshot_service.py    # Playwright screenshot generation
│   ├── drive_uploader.py        # Drive upload with folder organization
│   ├── categorizer.py           # Gemini Vision AI categorization
│   ├── state_manager.py         # Firestore state tracking
│   ├── vertex_ingestion.py      # Vertex AI document indexing
│   └── sync_orchestrator.py     # Pipeline coordination
├── api/
│   ├── __init__.py
│   └── routes.py                # FastAPI endpoints
└── docs/
    └── workflow.md              # Detailed workflow documentation
```

### Calendar Workflow Integration

Created `email_repository_client.py` in:
```
orchestrator/app/workflows/emailpilot-simple/emailpilot-v4/integration/
```

This client provides methods for V4 Stage 4 (Creative) to fetch email inspiration:
- `get_seasonal_inspiration()` - Emails from same month in previous years
- `get_campaign_type_examples()` - Examples of specific campaign types
- `get_brand_style_examples()` - All emails from a specific brand
- `search_inspiration()` - Natural language search

### GCP Resources Created

| Resource | ID/Name | Status |
|----------|---------|--------|
| Service Account | `email-sync-service@emailpilot-438321.iam.gserviceaccount.com` | Created |
| Secret (SA Key) | `email-sync-service-account` | Stored in Secret Manager |
| Unique ID (for delegation) | `107287607247737156910` | Ready for Workspace setup |

### Key Decisions

1. **Categorization Model**: Using `gemini-2.0-flash-lite` for cost efficiency (~$0.00002/email)
2. **Screenshot Format**: PNG (can be changed to JPEG for ~30% smaller files)
3. **Folder Structure**: `EmailScreenshots/{category}/{year}/{month}/`
4. **Email Source**: `nomad@unsubscribr.com` (user's promotional email harvesting account)

---

### Clerk Google OAuth Integration (January 30, 2026)

#### Feature Overview
Integrated Clerk Google OAuth with Image Repository to enable seamless Google Drive folder sharing for users who signed in via Google OAuth through Clerk. Users no longer need a second OAuth popup - their Drive access is automatically connected.

#### User Flow
```
User signs in via Clerk
         │
         ▼
    ┌─────────────┐
    │ Google OAuth │──Yes──► Auto-claim token ──► "Drive Connected"
    │   via Clerk? │                               (no popup!)
    └─────────────┘
         │ No
         ▼
    Show "Connect Google Drive" button
         │
         ▼
    Standard OAuth flow (existing)
```

#### Files Created
| File | Purpose |
|------|---------|
| `pipelines/image-repository/core/clerk_oauth_client.py` | Clerk Backend API client to retrieve Google OAuth tokens |

#### Files Modified
| File | Changes |
|------|---------|
| `pipelines/image-repository/api/routes.py` | Added `/oauth/claim-clerk-token` endpoint, new Pydantic models |
| `pipelines/image-repository/core/oauth_manager.py` | Added `store_external_token()` method, `token_source` tracking |
| `ui/image-repository.html` | Clerk Google detection, auto-claim logic, updated UI states |

#### New API Endpoint
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/images/oauth/claim-clerk-token` | POST | Claim Google OAuth token from Clerk and store for Drive access |

#### Request/Response
```json
// POST /api/images/oauth/claim-clerk-token
// Request
{
  "clerk_user_id": "user_2abc...",
  "user_id": "user@example.com"
}

// Response (success)
{
  "status": "authorized",
  "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
  "token_source": "clerk_google",
  "message": "Google Drive connected via Clerk sign-in"
}

// Response (missing scopes)
{
  "status": "missing_scopes",
  "scopes": ["openid", "email", "profile"],
  "missing_scopes": ["https://www.googleapis.com/auth/drive.readonly"],
  "message": "Google OAuth token is missing required Drive scopes. Please grant Drive access."
}
```

#### Frontend State Variables
```javascript
let clerkUserId = null;                // Clerk's user_2abc... ID
let hasClerkGoogleOAuth = false;       // User signed in with Google
let clerkTokenClaimStatus = null;      // 'pending', 'success', 'failed', 'no_scope', 'no_google'
```

#### UI States
| State | UI Display |
|-------|------------|
| `userOAuthStatus.is_authorized` + `token_source: 'clerk_google'` | "Connected via Google Sign-in" badge + "Add Your Folder" |
| `clerkTokenClaimStatus === 'pending'` | "Connecting..." spinner |
| `clerkTokenClaimStatus === 'no_scope'` | Yellow warning + "Grant Drive Access" button |
| Default (not connected) | "Connect Google Drive" button |

#### Environment Requirements
- `CLERK_SECRET_KEY` - Required for Clerk Backend API calls (already in production)
- Clerk Google OAuth must have `drive.readonly` scope configured

---

## Current Status

### Intelligence Grading Pipeline
- **Status**: Fully functional
- **API**: 7 endpoints available at `/api/intelligence/*`
- **UI**: "Intelligence Grade" tab in main UI
- **AI**: Uses Gemini 2.0 Flash with keyword fallback

### Image Repository
- **Status**: Functional with Clerk OAuth integration
- **OAuth**: Standard flow + Clerk auto-claim implemented
- **Clerk Integration**: Requires `CLERK_SECRET_KEY` and drive.readonly scope in Clerk

### Email Repository
- **Status**: Blocked on Google Workspace Admin Console configuration for domain-wide delegation

---

## Next Steps

1. **Verify Clerk drive.readonly scope** is configured in Clerk Dashboard → Google OAuth settings
2. **Test Clerk OAuth flow** end-to-end:
   - Sign in via Google through Clerk
   - Navigate to Image Repository
   - Verify toast shows "Google Drive connected automatically!"
   - Open client modal → verify "Connected via Google Sign-in" badge
   - Click "Add Your Folder" → verify folders load
3. **Test non-Google sign-in flow** (should show standard OAuth button)
4. **Complete Email Repository** Workspace delegation setup

See main `NEXT_STEPS.md` for detailed instructions.
