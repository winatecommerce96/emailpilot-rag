# RAG Service - Current Workflow

**Last Updated:** 2026-02-04

---

## Current Session (February 4, 2026)

### Image Repository OAuth Fixes - Clerk Scope + Auth State Reliability

#### Problem Statement
Users clicking **Connect Google Drive / Grant Drive Access** were hitting:
- `initiateOAuth called but no currentUserId` even when already signed in
- Lucide icon errors from invalid `image-search` icon name

The root cause was that `EmailPilotAuth.subscribe()` does not immediately fire for already-authenticated users, so `currentUserId` never got initialized. That blocked the OAuth flow that upgrades Drive scopes.

#### Fixes Implemented

##### 1. Resolve Auth State Immediately + Clerk Fallback
**File:** `ui/image-repository.html`
- Added `applyAuthUser()` + `ensureCurrentUserId()` to populate `currentUserId` from:
  - `EmailPilotAuth.getUser()` (current session)
  - `window.Clerk.user` (fallback)
- `initiateOAuth()` now calls `ensureCurrentUserId()` and triggers `EmailPilotAuth.signIn()` when missing
- `browseUserFolders()` now checks auth context before calling folder list API

##### 2. Align OAuth Scopes for Folder Access
**Files:** `ui/image-repository.html`, `pipelines/image-repository/core/clerk_oauth_client.py`
- UI GIS scope string includes `drive.readonly` + `drive.metadata.readonly`
- Clerk scope validation now requires both Drive scopes

##### 3. Fix Lucide Icon Error
**File:** `ui/image-repository.html`
- Replaced invalid `image-search` icon with `search`

##### 4. Validate Drive Scopes on Page Load + Google-Branded OAuth Button
**File:** `ui/image-repository.html`
- Added scope validation (`drive.readonly`, `drive.metadata.readonly`) on landing and after auth refresh
- Warns users when scopes are missing and surfaces **Grant Drive Access** immediately
- Replaced generic OAuth buttons with a Google-branded button
- Added a top-level banner warning when Drive scopes are missing (outside the client modal)

#### Files Modified
| File | Changes |
|------|---------|
| `ui/image-repository.html` | Auth state resolution, OAuth guardrails, scope validation on load, updated Drive scopes, icon fix, Google OAuth button |
| `pipelines/image-repository/core/clerk_oauth_client.py` | Require `drive.metadata.readonly` in Clerk scope validation |
| `README.md` | Documented required scopes and scope validation behavior |

---

## Current Session (February 3, 2026)

### Intelligence Grading Enhancement - Bug Fixes & Production Verification

#### Problem Statement
Two issues were reported with the Intelligence Grading system:
1. **Document Library Filter Not Working**: After uploading documents via quick-capture in the Intelligence Grade tab, the filter dropdown in the Document Library wasn't filtering by AI-categorized categories
2. **Category Color Badges Mismatched**: The color mapping function used incorrect category names that didn't match the actual categories from auto-categorization

#### Root Cause Analysis

**Issue 1 - Quick-Capture Method Bug:**
The quick-capture endpoint at `/api/intelligence/quick-capture` was calling `engine.add_document()` which doesn't exist on the `VertexContextEngine` class. This caused:
1. Exception thrown when trying to call non-existent method
2. Fallback to Firestore storage (not Vertex AI)
3. Document Library only reads from Vertex AI via `list_documents()`
4. Documents stored in Firestore fallback never appeared in Document Library

**Issue 2 - Color Mapping Mismatch:**
The `getSourceTypeColor()` function in DocumentLibrary.jsx used incorrect category names:
- `product_info` (actual: `product`)
- `campaign_history` (actual: `past_campaign`)
- Missing: `brand_voice`, `content_pillars`, `target_audience`, `seasonal_themes`

#### Fixes Implemented

##### 1. Fixed Quick-Capture to Use Correct Method
**File:** `pipelines/intelligence-grading/api/routes.py` (lines 845-871)

Changed from:
```python
result = engine.add_document(
    client_id=request.client_id,
    content=answer.content,
    metadata={
        "title": f"Quick Capture: {answer.field_name}",
        "source_type": base_source_type,
        ...
    }
)
```

To:
```python
result = engine.create_document(
    client_id=request.client_id,
    content=answer.content,
    title=f"Quick Capture: {answer.field_name}",
    category=base_source_type,  # Maps to source_type in list_documents
    source="intelligence_grading_quick_capture",
    tags=categorization_info.get("keywords", []) if categorization_info else []
)
```

##### 2. Fixed Category Color Mapping
**File:** `ui/src/components/DocumentLibrary.jsx` (lines 70-80)

Updated `getSourceTypeColor()` to match actual categories from LLM categorizer:
```javascript
const colors = {
    brand_voice: 'bg-indigo-100 text-indigo-700',
    brand_guidelines: 'bg-purple-100 text-purple-700',
    content_pillars: 'bg-cyan-100 text-cyan-700',
    marketing_strategy: 'bg-blue-100 text-blue-700',
    product: 'bg-green-100 text-green-700',
    target_audience: 'bg-amber-100 text-amber-700',
    past_campaign: 'bg-orange-100 text-orange-700',
    seasonal_themes: 'bg-rose-100 text-rose-700',
    general: 'bg-gray-100 text-gray-700',
};
```

#### Production Verification

Smoke tests completed on `https://rag.emailpilot.ai`:
- ✅ Health endpoint: `{"status":"ok","service":"vertex-rag"}`
- ✅ UI accessible at `/ui/` (301 redirect working)
- ✅ app.js served with updated color mapping (verified `brand_voice:"bg-indigo`, `seasonal_themes:"bg-rose`)
- ✅ CATEGORY_OPTIONS in filter dropdown matches STANDARD_CATEGORIES from LLM categorizer

#### Files Modified

| File | Changes |
|------|---------|
| `pipelines/intelligence-grading/api/routes.py` | Fixed `add_document()` → `create_document()` with correct parameters |
| `ui/src/components/DocumentLibrary.jsx` | Updated `getSourceTypeColor()` to use correct category names |

---

## Previous Session (February 2, 2026)

### Figma Feedback Unified Data Layer - Complete Implementation

#### Problem Statement
Figma design feedback was fragmented across multiple data stores:
- **BigQuery**: `figma.comments`, `figma.creative_rules` (used by RAG backfill)
- **Firestore**: `creative_intelligence/clients/{client_id}/comments` (used by Design Feedback UI)
- **Vertex AI**: Searchable documents for brief generation

This fragmentation caused:
1. Design Feedback UI only showed clients from GitHub Action (weekly runs)
2. Historical backfill data didn't appear in the Design Feedback UI
3. Long-term client feedback (e.g., "never mention stinky cheese" from 90 days ago) wasn't persisting for briefs

#### Solution: Unified Three-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     UNIFIED DATA FLOW                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Source: Figma API                                               │
│       │                                                          │
│       │ /api/figma-feedback/pull-from-figma                      │
│       │ /api/figma-feedback/auto-backfill/{client_id}            │
│       ▼                                                          │
│  RAG Service (spokes/RAG)                                        │
│       │                                                          │
│       ├─► Firestore (via Orchestrator)  ─► Design Feedback UI    │
│       │   POST /api/design-feedback/ingest                       │
│       │   (X-Internal-Service-Key auth)                          │
│       │                                                          │
│       ├─► BigQuery (legacy analytics)                            │
│       │                                                          │
│       └─► Vertex AI RAG ─────────────────► Brief Generation      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### Files Modified

| File | Changes |
|------|---------|
| `pipelines/figma-comments/api/routes.py` | Added `push_comments_to_firestore()` function, updated `run_direct_figma_pull()` to use unified flow |
| `ui/figma-feedback.html` | Added "60 Day Backfill" button (from previous session) |

#### New Function: `push_comments_to_firestore()`

```python
async def push_comments_to_firestore(client_id: str, file_key: str, comments: List[Dict], file_name: Optional[str] = None):
    """
    Push comments to Firestore via orchestrator's design-feedback ingest endpoint.
    Uses X-Internal-Service-Key header for service-to-service authentication.
    """
    ingest_payload = {
        "client_id": client_id,
        "file_key": file_key,
        "file_name": file_name,
        "comments": [transform_comment(c) for c in comments]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ORCHESTRATOR_URL}/api/design-feedback/ingest",
            headers={"X-Internal-Service-Key": INTERNAL_SERVICE_KEY},
            json=ingest_payload
        )
```

#### Environment Variables Added to Cloud Run

| Variable | Secret | Purpose |
|----------|--------|---------|
| `FIGMA_ACCESS_TOKEN` | `figma-api-token:latest` | Figma API authentication |
| `ASANA_PAT` | `asana-pat:latest` | Asana API for Figma file discovery |

#### Production Verification

Smoke tests completed successfully:
- ✅ RAG service health: `https://emailpilot-rag-935786836546.us-central1.run.app/health`
- ✅ Orchestrator design-feedback: `https://app.emailpilot.ai/api/design-feedback/clients`
- ✅ rogue-creamery: 413 comments synced to Firestore
- ✅ Internal service authentication working

---

### UI Shell Integration Fix - Critical Display Issues Resolved

#### Problem Statement
All RAG UI pages were displaying improperly:
- **index.html** (localhost:8003/): Giant lime-green "EmailPilot" watermark overlapping sidebar
- **image-repository.html**: Wrong colors (pink/purple gradient instead of neutral)
- **email-repository.html**: Wrong colors (blue/purple gradient)
- **email-review.html**: UI elements overlapping, not adhering to margins
- **meeting-intelligence.html**: Displayed properly (reference)
- **figma-feedback.html**: Displayed properly (reference)

#### Root Cause Analysis
Two issues were causing the display problems:

1. **Local CSS Blocking Orchestrator CSS**: All 6 RAG UI pages loaded a local `ui-shell.css` file which blocked the orchestrator's CSS from loading. The EP:UI-SHELL script block checks for existing ui-shell stylesheets and skips loading if found.

2. **Conflicting Gradient Styles**: Some pages defined their own `.gradient-bg` class with colored gradients (pink, blue, orange) that overrode the shell's neutral white gradient.

3. **Duplicate Content in email-review.html**: File had 1192 lines with two `</html>` tags - entire page content was duplicated after line 705. Also had a nested `<main>` wrapper causing double padding.

#### Fixes Implemented

##### 1. Removed Local CSS References (All 6 Pages)
**Files Modified**: `ui/index.html`, `ui/image-repository.html`, `ui/email-repository.html`, `ui/email-review.html`, `ui/meeting-intelligence.html`, `ui/figma-feedback.html`

Changed:
```html
<!-- Local UI Shell CSS - loaded directly for reliability (no cross-origin dependency) -->
<link rel="stylesheet" href="ui-shell.css">
```
To:
```html
<!-- UI Shell CSS loaded dynamically from orchestrator via EP:UI-SHELL block -->
```

##### 2. Removed Conflicting Gradient Styles (3 Pages)
**Files Modified**: `ui/image-repository.html`, `ui/email-repository.html`, `ui/email-review.html`

Removed inline `.gradient-bg` style definitions:
```css
/* REMOVED: These were overriding the shell's neutral gradient */
.gradient-bg {
    background: linear-gradient(135deg, #ec4899 0%, #8b5cf6 100%); /* pink */
    /* or #3b82f6 blue, or #f97316 orange */
}
```

##### 3. Fixed email-review.html Structure
- Removed duplicate content (trimmed from 1192 to 703 lines)
- Removed nested `<main class="flex-1 overflow-y-auto p-8">` wrapper that caused double padding
- Changed orphan `</main>` tag to `</div>` to properly close content-scroll

#### Technical Details

The working pattern (from product spoke's `sales_dashboard.html`):
- Does NOT load local ui-shell.css
- Lets the EP:UI-SHELL script block dynamically load orchestrator's CSS
- Uses shell's centralized CSS for consistent styling across all spokes

The problematic pattern (RAG pages before fix):
- Loaded local `ui-shell.css` first
- EP:UI-SHELL detected existing stylesheet and skipped orchestrator's CSS
- Local CSS was outdated/different, causing display issues

#### Verification
All 6 pages now have:
- 0 local `ui-shell.css` references
- No conflicting `.gradient-bg` inline styles
- Proper HTML structure without duplicates

---

### Image Repository - Module Caching Fix & OAuth Configuration Handling

#### Problems Identified

1. **Search Endpoint 500 Error**: `module 'config.settings' has no attribute 'get_pipeline_config'`
2. **OAuth Initiation 500 Error**: `initiateOAuth()` failing when OAuth environment variables not configured

#### Root Cause Analysis

**Issue 1 - Module Caching Conflict:**
Python's `sys.modules` cache was loading the wrong `config.settings` module. When multiple pipelines (email-repository, figma-email-review, image-repository) have identically-named modules, the first loaded module gets cached and reused incorrectly.

**Issue 2 - Missing Environment Variables:**
The OAuth authorize endpoint required `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`. If not configured, it raised a `ValueError` which became a generic 500 error.

#### Fixes Implemented

##### 1. Rewrote `_import_local()` Function
**File:** `pipelines/image-repository/api/routes.py`

Changed from shared module cache to unique module aliasing:
```python
_image_repo_modules = {}  # Cache with unique keys

def _import_local(module_path: str):
    unique_key = f"image_repo_{module_path}"
    if unique_key in _image_repo_modules:
        return _image_repo_modules[unique_key]

    # Load module directly from file with unique name
    spec = importlib.util.spec_from_file_location(unique_key, module_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _image_repo_modules[unique_key] = module
    return module
```

##### 2. New OAuth Configuration Endpoint
Added `GET /api/images/oauth/config`:
- Returns `{"configured": true}` when OAuth env vars are set
- Returns helpful setup instructions when not configured

##### 3. Improved OAuth Error Handling
- OAuth authorize endpoint returns 503 with helpful message instead of 500
- Message explains which environment variables need to be configured

##### 4. Enhanced Health Check
Added `oauth_configured` field to `/api/images/health` response.

##### 5. UI Improvements
**File:** `ui/image-repository.html`
- Added `checkOAuthConfiguration()` function called on page load
- Modal shows "OAuth not configured" message instead of broken button

#### Files Modified

| File | Changes |
|------|---------|
| `pipelines/image-repository/api/routes.py` | Rewrote `_import_local()`, added `/oauth/config`, improved error handling |
| `ui/image-repository.html` | Added OAuth config check, improved UX when not configured |

#### Verification

```bash
curl http://localhost:8003/api/images/health          # oauth_configured: true ✅
curl http://localhost:8003/api/images/oauth/config    # configured: true ✅
curl "http://localhost:8003/api/images/search/buca-di-beppo?q=test"  # No more error ✅
```

---

## Previous Session (January 30, 2026)

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
  "scopes": [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
  ],
  "token_source": "clerk_google",
  "message": "Google Drive connected via Clerk sign-in"
}

// Response (missing scopes)
{
  "status": "missing_scopes",
  "scopes": ["openid", "email", "profile"],
  "missing_scopes": [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
  ],
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
- Clerk Google OAuth must have `drive.readonly` and `drive.metadata.readonly` scopes configured

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
- **Clerk Integration**: Requires `CLERK_SECRET_KEY` and Drive scopes (`drive.readonly`, `drive.metadata.readonly`) in Clerk

### Email Repository
- **Status**: Blocked on Google Workspace Admin Console configuration for domain-wide delegation

---

## Next Steps

1. **Verify Clerk Drive scopes** are configured in Clerk Dashboard → Google OAuth settings (`drive.readonly`, `drive.metadata.readonly`)
2. **Test Clerk OAuth flow** end-to-end:
   - Sign in via Google through Clerk
   - Navigate to Image Repository
   - Verify toast shows "Google Drive connected automatically!"
   - Open client modal → verify "Connected via Google Sign-in" badge
   - Click "Add Your Folder" → verify folders load
3. **Test non-Google sign-in flow** (should show standard OAuth button)
4. **Complete Email Repository** Workspace delegation setup

See main `NEXT_STEPS.md` for detailed instructions.
