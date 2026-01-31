# RAG Service - Next Steps

**Last Updated:** 2026-01-30

---

## Priority 0: Image Repository OAuth Production Setup (NEW)

### Step 1: Create OAuth Credentials in Google Cloud Console

1. Go to: https://console.cloud.google.com/apis/credentials
2. Select project: `emailpilot-438321`
3. Click **Create Credentials** → **OAuth 2.0 Client IDs**
4. Application type: **Web application**
5. Name: `RAG Image Repository OAuth`
6. Authorized redirect URIs:
   - `http://localhost:8003/api/images/oauth/callback` (development)
   - `https://rag.emailpilot.ai/api/images/oauth/callback` (production)
7. Click **Create** and note the Client ID and Client Secret

### Step 2: Store Secrets in GCP Secret Manager

```bash
# Store OAuth Client ID
echo -n "YOUR_CLIENT_ID" | gcloud secrets create image-repo-oauth-client-id --data-file=-

# Store OAuth Client Secret
echo -n "YOUR_CLIENT_SECRET" | gcloud secrets create image-repo-oauth-client-secret --data-file=-

# Generate and store encryption key for token storage
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | gcloud secrets create oauth-encryption-key --data-file=-
```

### Step 3: Update Cloud Run Environment Variables

```bash
gcloud run services update rag-service \
  --set-env-vars="GOOGLE_OAUTH_CLIENT_ID=sm://image-repo-oauth-client-id" \
  --set-env-vars="GOOGLE_OAUTH_CLIENT_SECRET=sm://image-repo-oauth-client-secret" \
  --set-env-vars="GOOGLE_OAUTH_REDIRECT_URI=https://rag.emailpilot.ai/api/images/oauth/callback" \
  --set-env-vars="OAUTH_ENCRYPTION_KEY=sm://oauth-encryption-key"
```

Or update via Cloud Run Console → Edit & Deploy New Revision → Environment Variables.

### Step 4: Test OAuth Flow

1. Navigate to: http://localhost:8003/ui/image-repository.html
2. Click Settings (gear icon) on any client card
3. Click **Connect Google Drive**
4. Complete Google OAuth consent flow
5. Verify "Connected" status appears
6. Click **Add Your Folder** to browse your Drive
7. Select a folder and verify it appears in configured folders

### Step 5: Verify Token Storage

Check Firestore collection `oauth_tokens` for encrypted tokens:
```
oauth_tokens/{user_email}
  - access_token_encrypted: <encrypted>
  - refresh_token_encrypted: <encrypted>
  - created_at: <timestamp>
  - updated_at: <timestamp>
```

---

## Priority 1: Complete Email Repository Pipeline Setup

### Step 1: Configure Domain-Wide Delegation in Google Workspace

**This must be done by a Google Workspace admin for `unsubscribr.com`:**

1. Go to: https://admin.google.com
2. Navigate to: **Security** → **Access and data control** → **API Controls**
3. Click **Manage Domain Wide Delegation** (or scroll down to find "Domain-wide Delegation")
4. Click **Add new**
5. Enter these EXACT values:

| Field | Value |
|-------|-------|
| **Client ID** | `107287607247737156910` |
| **OAuth Scopes** | `https://www.googleapis.com/auth/gmail.readonly` |

6. Click **Authorize**

**Important Notes:**
- The Client ID is the unique identifier for the service account `email-sync-service@emailpilot-438321.iam.gserviceaccount.com`
- This grants the service account permission to read emails from ANY user in the `unsubscribr.com` domain
- Only the `gmail.readonly` scope is needed (no write access)

### Step 2: Update Email Account Configuration

After completing Step 1, edit the file:
```
spokes/RAG/pipelines/email-repository/config/email_accounts.yaml
```

Change the email address from the placeholder to your actual harvesting email:

```yaml
email_accounts:
  - account_email: "nomad@unsubscribr.com"  # <-- Update this
    account_name: "Promotional Email Harvester"
    enabled: true
    sync_settings:
      date_range_start: "2023-01-01"  # Adjust based on how far back you want
      sender_blocklist:
        - "noreply@"
        - "no-reply@"
        - "mailer-daemon@"
```

### Step 3: Set Environment Variable

Add to your `.env` file or environment:

```bash
export EMAIL_SYNC_DELEGATED_EMAIL=nomad@unsubscribr.com
```

### Step 4: Test the Pipeline

```bash
# Start the RAG service
cd spokes/RAG
source .venv/bin/activate
uvicorn app.main:app --port 8003 --reload

# Test the health endpoint
curl http://localhost:8003/api/emails/health

# Trigger a sync (will run in background)
curl -X POST http://localhost:8003/api/emails/sync \
  -H "Content-Type: application/json" \
  -d '{"force_full_sync": false}'

# Check sync status
curl http://localhost:8003/api/emails/status/nomad@unsubscribr.com
```

### Step 5: Access the UI

Navigate to: http://localhost:8003/ui/email-repository.html

---

## Priority 2: Production Deployment Considerations

### Environment Variables for Cloud Run

```bash
# Required for email sync
EMAIL_SYNC_SERVICE_ACCOUNT_SECRET=email-sync-service-account
EMAIL_SYNC_DELEGATED_EMAIL=nomad@unsubscribr.com

# Already configured (verify these exist)
GEMINI_API_KEY_SECRET=gemini-rag-image-processing
GCP_PROJECT_ID=emailpilot-438321
VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919
```

### Playwright in Docker

If deploying to Cloud Run, ensure the Dockerfile includes:

```dockerfile
# Install Playwright dependencies
RUN pip install playwright
RUN playwright install chromium
RUN playwright install-deps
```

---

## Priority 3: Future Enhancements

1. **Automated Scheduling**: Set up Cloud Scheduler to trigger sync daily
2. **Batch Processing**: Process historical backlog in chunks (recommended: 500 emails/sync)
3. **Brand Detection**: Enhance categorizer to extract brand names more reliably
4. **V4 Integration**: Connect email inspiration to Stage 4 creative prompts

---

## Troubleshooting

### "403 Forbidden" from Gmail API
- Domain-wide delegation not configured correctly
- Client ID mismatch
- Delegated email doesn't exist in the Workspace

### "Service account key not found"
- Secret `email-sync-service-account` not in Secret Manager
- Service account doesn't have Secret Manager access

### Screenshots are blank/broken
- Email HTML is malformed
- Playwright timeout (increase `timeout_ms` in settings)
- Missing Chromium browser (run `playwright install chromium`)

---

## Resources

- **Service Account Email**: `email-sync-service@emailpilot-438321.iam.gserviceaccount.com`
- **Service Account Client ID**: `107287607247737156910`
- **Secret Name**: `email-sync-service-account`
- **Pipeline Documentation**: `spokes/RAG/pipelines/email-repository/docs/workflow.md`

---

## Recently Completed (2026-01-30)

| Item | Status | Notes |
|------|--------|-------|
| **Intelligence Grading Pipeline** | ✅ Done | Full 7-dimension grading system with AI extraction, A-F grades, gap detection, recommendations |
| **Intelligence Grading UI** | ✅ Done | New "Intelligence Grade" tab in React UI with buttons for full/quick analysis |
| **Intelligence Grading API** | ✅ Done | 7 endpoints: grade, quick-assessment, requirements, gaps, ready, quick-capture, health |
| **Image Repository OAuth** | ✅ Done | `oauth_manager.py` with Fernet encryption, 5 OAuth endpoints, UI integration |
| **Module Import Fix** | ✅ Done | Fixed Python caching conflicts between pipelines using isolated imports |
| **Thumbnail Proxy** | ✅ Done | Fixed attribute name (`drive` not `drive_client`) |
| **Vertex AI Fallback** | ✅ Done | Stats endpoint falls back to Vertex AI when Firestore shows 0 |
| **Health Check Feedback** | ✅ Done | Toast notifications for healthy/degraded/error states |
| **UI Folder Links** | ✅ Done | Client cards now show clickable Drive folder links |
| **HTML Cleanup** | ✅ Done | Removed duplicate HTML from email-repository.html and figma-feedback.html |
| **Root URL Fix** | ✅ Done | `http://localhost:8003` now serves UI directly (FileResponse instead of redirect) |
