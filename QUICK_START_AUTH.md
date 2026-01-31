# RAG Service Authentication - Quick Start Guide

## 1. Install Dependencies

```bash
cd /Users/Damon/emailpilot/spokes/RAG
pip install python-jose[cryptography] cachetools
```

## 2. Configure Environment

Add to `.env`:
```bash
CLERK_FRONTEND_API=current-stork-99.clerk.accounts.dev
CLERK_PUBLISHABLE_KEY=pk_test_xxxxxxxxxxxxx
GLOBAL_AUTH_ENABLED=true
```

## 3. Start Service

```bash
uvicorn app.main:app --port 8003 --reload
```

## 4. Test Public Endpoints

```bash
# Health check (always public)
curl http://localhost:8003/health

# Auth config (public, used by frontend)
curl http://localhost:8003/auth/config
```

## 5. Test Protected Endpoint

```bash
# Get a Clerk token (from frontend or Clerk dashboard)
TOKEN="your-clerk-jwt-token-here"

# Call protected endpoint
curl -H "Authorization: Bearer $TOKEN" http://localhost:8003/api/me
```

## 6. Protect Your Own Routes

```python
from fastapi import Depends
from app.auth import AuthenticatedUser, get_current_user

@app.get("/api/your-route")
async def your_route(user: AuthenticatedUser = Depends(get_current_user)):
    # User is authenticated - can access user.user_id, user.email
    return {"message": f"Hello {user.email}"}
```

## Common Issues

### "Module not found: jose"
```bash
pip install python-jose[cryptography]
```

### "GLOBAL_AUTH_JWKS_URL is not configured"
Add to `.env`:
```bash
CLERK_FRONTEND_API=current-stork-99.clerk.accounts.dev
```

### "Token validation failed"
- Ensure token is from correct Clerk instance
- Check token hasn't expired
- Verify `CLERK_FRONTEND_API` matches your Clerk instance

## File Locations

- **Auth Module**: `/Users/Damon/emailpilot/spokes/RAG/app/auth.py`
- **Main App**: `/Users/Damon/emailpilot/spokes/RAG/app/main.py`
- **Tests**: `/Users/Damon/emailpilot/spokes/RAG/test_auth.py`
- **Full Docs**: `/Users/Damon/emailpilot/spokes/RAG/AUTH_IMPLEMENTATION.md`
- **Report**: `/Users/Damon/emailpilot/spokes/RAG/CLERK_AUTH_IMPLEMENTATION_REPORT.md`

## Example Frontend Integration

```javascript
// 1. Fetch config
const config = await fetch('http://localhost:8003/auth/config')
  .then(r => r.json());

// 2. Get token from Clerk
const token = await clerk.session.getToken();

// 3. Make authenticated request
const response = await fetch('http://localhost:8003/api/me', {
  headers: { 'Authorization': `Bearer ${token}` }
});
```

## Quick Reference

| Endpoint | Auth Required | Purpose |
|----------|---------------|---------|
| `/health` | No | Health check |
| `/auth/config` | No | Get Clerk config |
| `/api/me` | Yes | Current user info |
| All other routes | No (default) | Can be protected per route |

## Disable Authentication

```bash
# In .env
GLOBAL_AUTH_ENABLED=false
```

Then restart the service.
