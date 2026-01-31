from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from app.models.schemas import RAGSearchRequest, RAGResult, RAGPhase
from app.services.vertex_search import get_vertex_engine
from app.services.google_docs import get_google_docs_service
from app.services.llm_categorizer import categorize_with_llm, categorize_with_keywords, STANDARD_CATEGORIES
from app.client_id import normalize_client_id, is_canonical_client_id
from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel
from datetime import datetime
import os
import sys
import json
import uuid
import shutil
import httpx
import io
from dotenv import load_dotenv

# Clerk authentication support (optional - routes can use Depends(get_current_user))
from app.auth import AuthenticatedUser, get_current_user, get_current_user_optional

# PDF and DOCX parsing
from pypdf import PdfReader
import docx

load_dotenv()

# Orchestrator URL for fetching live clients (single source of truth)
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "https://app.emailpilot.ai")
# Internal service key for service-to-service authentication
INTERNAL_SERVICE_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

# Firestore integration for shared clients
try:
    from google.cloud import firestore
    FIRESTORE_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "emailpilot-438321")

    # Set up credentials if not already set
    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        # Try common locations for the service account key
        possible_key_paths = [
            Path(__file__).parent.parent / "emailpilot-firestore-key.json",
            Path("/Users/Damon/calendar/emailpilot-firestore-key.json"),
            Path.home() / ".config" / "gcloud" / "application_default_credentials.json",
        ]
        for key_path in possible_key_paths:
            if key_path.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)
                break

    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    FIRESTORE_PROJECT = None

from app.middleware import GlobalAuthMiddleware

app = FastAPI(
    title="EmailPilot RAG Service",
    root_path=os.getenv("FASTAPI_ROOT_PATH", "")
)

# Add Global Auth Middleware FIRST
app.add_middleware(GlobalAuthMiddleware)

from app.services.ai.tracker import TrackingContext

@app.middleware("http")
async def tracking_context_middleware(request: Request, call_next):
    """
    Middleware to inject user/org context into the AI tracking system.
    Runs AFTER GlobalAuthMiddleware, so request.state.user is available.
    Also checks X-Tracking-User-Id/Org-Id headers for service-to-service calls.
    """
    user_id = None
    org_id = None
    
    # Priority 1: Tracking headers (explicit propagation)
    if request.headers.get("X-Tracking-User-Id"):
        user_id = request.headers.get("X-Tracking-User-Id")
        org_id = request.headers.get("X-Tracking-Org-Id")
    
    # Priority 2: Authenticated User (if not set by headers)
    if not user_id and hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.get("user_id") or request.state.user.get("id")
        org_id = request.state.user.get("org_id")
        
    # Start tracking context for this request
    # This sets ContextVars that LangSmith/LangChain will pick up
    async with TrackingContext(user_id=user_id, org_id=org_id):
        response = await call_next(request)
        return response

# CORS middleware - custom domain URLs only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8001",
        "http://localhost:8002",
        "http://localhost:8003",
        "http://localhost:8004",
        "http://localhost:8008",
        "http://localhost:5173",
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8002",
        "http://127.0.0.1:8003",
        "https://emailpilot.ai",
        "https://www.emailpilot.ai",
        "https://app.emailpilot.ai",
        "https://calendar.emailpilot.ai",
        "https://rag.emailpilot.ai",
        "https://product.emailpilot.ai",
        "https://workflows.emailpilot.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = get_vertex_engine()
google_docs = get_google_docs_service()

# Paths
UI_DIR = Path(__file__).parent.parent / "ui"
DATA_DIR = Path(__file__).parent.parent / "data"
CLIENTS_FILE = DATA_DIR / "clients.json"
DOCUMENTS_DIR = DATA_DIR / "documents"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
DOCUMENTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# MODELS
# ============================================================================
class ClientCreate(BaseModel):
    name: str
    description: Optional[str] = ""

class ClientResponse(BaseModel):
    client_id: str
    name: str
    description: str
    created_at: str
    document_count: int = 0

class DocumentMetadata(BaseModel):
    title: Optional[str] = None
    source_type: Optional[str] = "general"
    tags: Optional[str] = ""

def parse_tags(raw_tags: Optional[str]) -> List[str]:
    if not raw_tags:
        return []
    raw_tags = raw_tags.strip()
    if not raw_tags:
        return []
    if raw_tags.startswith("["):
        try:
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                return [str(tag).strip() for tag in parsed if str(tag).strip()]
        except json.JSONDecodeError:
            pass
    return [tag.strip() for tag in raw_tags.split(",") if tag.strip()]

def merge_tags(*tag_lists: List[str]) -> List[str]:
    merged = []
    seen = set()
    for tag_list in tag_lists:
        for tag in tag_list:
            cleaned = str(tag).strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return merged

# ============================================================================
# CLIENT STORAGE HELPERS
# ============================================================================
def load_clients() -> Dict[str, Any]:
    """Load local clients from JSON file"""
    if CLIENTS_FILE.exists():
        with open(CLIENTS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_clients(clients: Dict[str, Any]):
    """Save local clients to JSON file"""
    with open(CLIENTS_FILE, 'w') as f:
        json.dump(clients, f, indent=2)

def get_client_doc_count(client_id: str) -> int:
    """Get document count for a client from Vertex AI"""
    client_id = normalize_client_id(client_id)
    if not client_id:
        return 0
    try:
        return engine.get_client_document_count(client_id)
    except Exception:
        # Fallback to local count if Vertex AI fails
        client_dir = DOCUMENTS_DIR / client_id
        if client_dir.exists():
            return len(list(client_dir.glob("*.json")))
        return 0

def load_firestore_clients() -> List[Dict[str, Any]]:
    """Load clients from Firestore (shared across EmailPilot ecosystem)"""
    if not FIRESTORE_AVAILABLE:
        return []

    try:
        db = firestore.Client(project=FIRESTORE_PROJECT)
        clients = []

        for doc in db.collection('clients').stream():
            client_data = doc.to_dict()
            clients.append({
                "client_id": doc.id,
                "name": client_data.get("client_name") or client_data.get("name") or doc.id,
                "description": client_data.get("description", ""),
                "created_at": client_data.get("created_at", ""),
                "industry": client_data.get("industry", ""),
                "source": "firestore"
            })

        return clients
    except Exception as e:
        print(f"Firestore client load error: {e}")
        return []

# Cache for orchestrator clients (simple in-memory cache)
_orchestrator_client_cache = {"clients": [], "timestamp": 0}
_CACHE_TTL = 300  # 5 minutes

def require_canonical_client_id(value: str) -> str:
    raw = (value or "").strip()
    normalized = normalize_client_id(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="client_id is required")
    if normalized != raw:
        raise HTTPException(
            status_code=400,
            detail=f"client_id must be kebab-case (example: '{normalized}')"
        )
    if not is_canonical_client_id(normalized):
        raise HTTPException(
            status_code=400,
            detail="client_id must be kebab-case (lowercase letters, digits, hyphens)"
        )
    return normalized

async def get_valid_orchestrator_clients() -> List[str]:
    """Get list of valid client IDs from orchestrator (with caching)"""
    import time
    now = time.time()

    # Return cached if fresh
    if _orchestrator_client_cache["clients"] and (now - _orchestrator_client_cache["timestamp"]) < _CACHE_TTL:
        return _orchestrator_client_cache["clients"]

    # Fetch fresh from orchestrator
    clients = await fetch_orchestrator_clients()
    client_ids = []
    for client in clients:
        raw_id = client.get("client_id") or client.get("id") or client.get("slug") or ""
        normalized = normalize_client_id(raw_id)
        if normalized:
            client_ids.append(normalized)

    # Update cache
    _orchestrator_client_cache["clients"] = client_ids
    _orchestrator_client_cache["timestamp"] = now

    return client_ids

async def is_valid_client_async(client_id: str) -> bool:
    """Check if a client exists (async version - checks orchestrator, local, Firestore)"""
    client_id = normalize_client_id(client_id)
    if not client_id:
        return False

    # Check local first (fast)
    local_clients = load_clients()
    if client_id in local_clients:
        return True

    # Check orchestrator clients (cached)
    orchestrator_ids = await get_valid_orchestrator_clients()
    if client_id in orchestrator_ids:
        return True

    # Fallback to Firestore (slow, might fail)
    firestore_clients = load_firestore_clients()
    for fc in firestore_clients:
        if fc["client_id"] == client_id:
            return True

    return False

def is_valid_client(client_id: str) -> bool:
    """Check if a client exists in local storage or Firestore (sync version - deprecated)"""
    client_id = normalize_client_id(client_id)
    if not client_id:
        return False
    # Check local first
    local_clients = load_clients()
    if client_id in local_clients:
        return True

    # For sync context, check if client_id looks valid (slug format)
    # This allows orchestrator clients to work without async check
    if client_id and isinstance(client_id, str) and len(client_id) > 0:
        # Accept any valid-looking slug from orchestrator
        # The actual validation happens when fetching from orchestrator
        return True

    return False

@app.post("/api/rag/search", response_model=List[RAGResult])
def search_rag(request: RAGSearchRequest):
    try:
        # Now we call it synchronously (no await needed)
        results = engine.search(request)
        return results
    except Exception as e:
        print(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "vertex-rag"}

@app.get("/auth/config")
def auth_config():
    """
    Return Clerk authentication configuration for frontend.
    Used by UI to initialize Clerk SDK.
    """
    # Check if auth is enabled
    auth_enabled = os.getenv("GLOBAL_AUTH_ENABLED", "true").lower() in {"1", "true", "yes", "on"}

    # Get Clerk publishable key (try both variants)
    publishable_key = os.getenv("CLERK_PUBLISHABLE_KEY") or os.getenv("VITE_CLERK_PUBLISHABLE_KEY", "")

    # Get Clerk frontend API
    clerk_frontend_api = os.getenv("CLERK_FRONTEND_API", "current-stork-99.clerk.accounts.dev")

    return {
        "enabled": auth_enabled,
        "provider": "clerk",
        "clerk": {
            "publishable_key": publishable_key,
            "frontend_api": clerk_frontend_api,
            "sign_in_url": "/static/login.html"
        }
    }

@app.get("/api/me")
async def get_current_user_info(user: AuthenticatedUser = Depends(get_current_user)):
    """
    Example protected endpoint - requires Clerk authentication.
    Returns information about the currently authenticated user.

    Usage:
        curl -H "Authorization: Bearer <clerk-jwt-token>" http://localhost:8003/api/me
    """
    return {
        "user_id": user.user_id,
        "email": user.email,
        "claims": user.claims
    }

# ============================================================================
# ORCHESTRATOR PROXY ENDPOINTS (Single Source of Truth for Clients)
# ============================================================================
async def fetch_orchestrator_clients() -> List[Dict[str, Any]]:
    """Fetch clients from EmailPilot Orchestrator API using internal secure endpoint"""
    try:
        headers = {}
        if INTERNAL_SERVICE_KEY:
            headers["X-Internal-Service-Key"] = INTERNAL_SERVICE_KEY
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ORCHESTRATOR_URL}/api/internal/clients",
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("clients", [])
            else:
                print(f"Orchestrator fetch failed: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"Orchestrator fetch error: {e}")
    return []

def filter_active_clients(clients: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter for active/LIVE clients only (matches calendar app pattern)"""
    filtered = []
    for client in clients:
        # Check status is LIVE (not INACTIVE, ONBOARDING, etc.)
        status = client.get("status", "").upper()
        is_live = status == "LIVE"

        # Check metadata.active is not False
        metadata = client.get("metadata", {}) or {}
        is_active = metadata.get("active") != False

        if is_live and is_active:
            filtered.append(client)

    return filtered

@app.get("/api/orchestrator/clients")
async def list_orchestrator_clients(request: Request, include_inactive: bool = False):
    """
    Fetch live clients from EmailPilot Orchestrator (single source of truth).
    Filtered by user permissions via orchestrator's /api/clients endpoint.
    """
    # Check authentication (middleware should have set this)
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Fetch user-filtered clients from orchestrator
    clients = await fetch_user_filtered_clients(request)

    # Filter for active clients unless explicitly including inactive
    if not include_inactive:
        clients = filter_active_clients(clients)

    # Transform to consistent format with rich metadata
    result = []
    for client in clients:
        metadata = client.get("metadata", {}) or {}
        raw_id = client.get("client_id") or client.get("id") or client.get("slug") or ""
        client_id = normalize_client_id(raw_id)
        if not client_id:
            continue
        result.append({
            "client_id": client_id,
            "name": client.get("client_name") or client.get("name") or client.get("display_name") or client_id,
            "industry": client.get("industry", ""),
            "status": client.get("status", "UNKNOWN"),
            "description": client.get("description", ""),
            "timezone": metadata.get("timezone", ""),
            "client_voice": metadata.get("client_voice", ""),
            "client_background": metadata.get("client_background", ""),
            "document_count": get_client_doc_count(client_id),
            "is_demo": client.get("is_demo", False),
            "source": "orchestrator"
        })

    # Sort by name
    result.sort(key=lambda x: x.get("name", "").lower())

    return {"clients": result, "total": len(result)}

# ============================================================================
# CLIENT MANAGEMENT ENDPOINTS (User-filtered via Orchestrator)
# ============================================================================
async def fetch_user_filtered_clients(request: Request) -> List[Dict[str, Any]]:
    """
    Fetch clients from Orchestrator's /api/clients endpoint with auth forwarding.
    This ensures user permission filtering is applied.
    """
    try:
        headers = {}

        # Forward auth header if present
        auth_header = request.headers.get("Authorization")
        if auth_header:
            headers["Authorization"] = auth_header

        # Also forward SSO cookie if present
        sso_cookie = request.cookies.get("emailpilot_clerk_jwt")
        if sso_cookie and not auth_header:
            headers["Authorization"] = f"Bearer {sso_cookie}"

        # NOTE: Internal service key is intentionally NOT forwarded here.
        # User requests must be filtered by the user's actual permissions.
        # Adding X-Internal-Service-Key would grant super_admin access and bypass filtering.

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ORCHESTRATOR_URL}/api/clients",  # User-filtered endpoint
                headers=headers,
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                # Orchestrator returns a list directly
                return data if isinstance(data, list) else data.get("clients", [])
            else:
                print(f"Orchestrator /api/clients fetch failed: {response.status_code} - {response.text[:200]}")
    except Exception as e:
        print(f"Orchestrator /api/clients fetch error: {e}")
    return []


@app.get("/api/clients")
async def list_clients(request: Request):
    """
    List all clients filtered by user permissions.

    Proxies to orchestrator's /api/clients endpoint which handles:
    - Super admins see ALL clients
    - Regular users see only assigned clients + demo clients
    - Visitors see demo clients ONLY

    Requires authentication (handled by middleware).
    """
    # Check authentication (middleware should have set this)
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Fetch clients from orchestrator with auth forwarding
    orchestrator_clients = await fetch_user_filtered_clients(request)
    if orchestrator_clients:
        result = []
        for client in orchestrator_clients:
            raw_id = client.get("client_id") or client.get("id") or client.get("slug") or ""
            client_id = normalize_client_id(raw_id)
            if not client_id:
                continue
            result.append({
                "client_id": client_id,
                "name": client.get("name") or client.get("client_name") or client_id,
                "industry": client.get("industry", ""),
                "status": client.get("status", "LIVE"),
                "description": client.get("description", ""),
                "document_count": get_client_doc_count(client_id),
                "is_demo": client.get("is_demo", False),
                "source": "orchestrator"
            })
        result.sort(key=lambda x: x.get("name", "").lower())
        return {"clients": result, "total": len(result)}

    # Fallback to Firestore + local (legacy behavior - filtered by user permissions)
    # Note: In fallback mode, we can't properly filter without user's client_ids
    # from claims. For safety, return empty list if user doesn't have internal access.
    is_internal_service = user.get("is_internal_service", False)
    user_roles = user.get("roles", [])
    is_super_admin = "super_admin" in user_roles or is_internal_service

    if not is_super_admin:
        # Cannot properly filter in fallback mode - return empty to prevent data leakage
        print(f"Warning: Fallback mode cannot filter clients for non-admin user")
        return {"clients": [], "total": 0}

    # Only super admins get fallback data
    result = []
    seen_ids = set()

    # First, load Firestore clients (shared across EmailPilot ecosystem)
    firestore_clients = load_firestore_clients()
    for client in firestore_clients:
        client_id = client["client_id"]
        if client_id not in seen_ids:
            result.append({
                "client_id": client_id,
                "name": client["name"],
                "description": client.get("description", ""),
                "created_at": client.get("created_at", ""),
                "industry": client.get("industry", ""),
                "document_count": get_client_doc_count(client_id),
                "source": "firestore"
            })
            seen_ids.add(client_id)

    # Then add local clients (created in RAG UI)
    local_clients = load_clients()
    for client_id, client_data in local_clients.items():
        if client_id not in seen_ids:
            result.append({
                "client_id": client_id,
                "name": client_data.get("name", client_id),
                "description": client_data.get("description", ""),
                "created_at": client_data.get("created_at", ""),
                "document_count": get_client_doc_count(client_id),
                "source": "local"
            })
            seen_ids.add(client_id)

    # Sort by name
    result.sort(key=lambda x: x.get("name", "").lower())

    return {"clients": result, "total": len(result)}

@app.post("/api/clients")
def create_client(client: ClientCreate):
    """Create a new client"""
    clients = load_clients()

    # Generate client ID from name
    client_id = normalize_client_id(client.name)
    if not is_canonical_client_id(client_id):
        raise HTTPException(
            status_code=400,
            detail="client_id must be kebab-case (lowercase letters, digits, hyphens)"
        )

    if client_id in clients:
        raise HTTPException(status_code=400, detail=f"Client '{client_id}' already exists")

    clients[client_id] = {
        "name": client.name,
        "description": client.description or "",
        "created_at": datetime.utcnow().isoformat()
    }
    save_clients(clients)

    # Create document directory for client
    (DOCUMENTS_DIR / client_id).mkdir(exist_ok=True)

    return {
        "client_id": client_id,
        "name": client.name,
        "description": client.description,
        "created_at": clients[client_id]["created_at"],
        "document_count": 0
    }

@app.get("/api/clients/{client_id}")
def get_client(client_id: str):
    """Get a specific client"""
    client_id = require_canonical_client_id(client_id)
    clients = load_clients()
    if client_id not in clients:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    client_data = clients[client_id]
    return {
        "client_id": client_id,
        "name": client_data.get("name", client_id),
        "description": client_data.get("description", ""),
        "created_at": client_data.get("created_at", ""),
        "document_count": get_client_doc_count(client_id)
    }

@app.delete("/api/clients/{client_id}")
def delete_client(client_id: str):
    """Delete a client and all their documents"""
    client_id = require_canonical_client_id(client_id)
    clients = load_clients()
    if client_id not in clients:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Delete client documents
    client_dir = DOCUMENTS_DIR / client_id
    if client_dir.exists():
        shutil.rmtree(client_dir)

    # Remove from clients
    del clients[client_id]
    save_clients(clients)

    return {"message": f"Client '{client_id}' deleted successfully"}

# ============================================================================
# FILE PARSING HELPERS
# ============================================================================
def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text content from a PDF file."""
    reader = PdfReader(io.BytesIO(file_bytes))
    text_content = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_content += page_text + "\n"
    return text_content

def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text content from a DOCX file."""
    doc = docx.Document(io.BytesIO(file_bytes))
    text_content = ""
    for para in doc.paragraphs:
        if para.text.strip():
            text_content += para.text + "\n"
    return text_content

def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    """Extract text from file based on extension."""
    filename_lower = filename.lower()

    if filename_lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif filename_lower.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    else:
        # Plain text files (txt, md, etc.)
        try:
            return file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            return file_bytes.decode('latin-1')

def chunk_text(text: str, min_chunk_size: int = 100, max_chunk_size: int = 2000) -> List[str]:
    """
    Split text into chunks for better RAG retrieval.
    Uses paragraph boundaries when possible.
    """
    # Split by double newlines (paragraphs)
    paragraphs = text.split("\n\n")

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If adding this paragraph exceeds max size, save current and start new
        if len(current_chunk) + len(para) > max_chunk_size and current_chunk:
            if len(current_chunk) >= min_chunk_size:
                chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            current_chunk += "\n\n" + para if current_chunk else para

    # Don't forget the last chunk
    if current_chunk and len(current_chunk) >= min_chunk_size:
        chunks.append(current_chunk.strip())

    # If no chunks were created (text too short), use the whole text
    if not chunks and text.strip():
        chunks.append(text.strip())

    return chunks

# ============================================================================
# DOCUMENT MANAGEMENT ENDPOINTS
# ============================================================================
@app.get("/api/documents/{client_id}")
def list_documents(client_id: str, page: int = 1, limit: int = 20):
    """List documents for a client from Vertex AI data store"""
    client_id = require_canonical_client_id(client_id)
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Fetch documents from Vertex AI
    return engine.list_documents(client_id, page, limit)

@app.post("/api/documents/{client_id}/upload")
async def upload_document(
    client_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    auto_categorize: bool = Form(True),  # NEW: Auto-categorize by default
    tags: Optional[str] = Form("")
):
    """
    Upload a document for a client to Vertex AI (supports PDF, DOCX, and text files).

    If auto_categorize=True and source_type is not provided, uses LLM to automatically
    determine the most appropriate category based on content analysis.
    """
    client_id = require_canonical_client_id(client_id)
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Read file content
    file_bytes = await file.read()
    filename = file.filename or "document.txt"

    # Extract text based on file type
    try:
        text_content = extract_text_from_file(filename, file_bytes)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if not text_content.strip():
        raise HTTPException(status_code=400, detail="No text content could be extracted from the file")

    # Chunk the text for better RAG retrieval
    chunks = chunk_text(text_content)
    doc_title = title or filename

    # Determine category - use LLM if auto_categorize and no source_type provided
    category = source_type
    categorization_method = "manual"
    categorization_confidence = 1.0
    generated_keywords = []
    manual_tags = parse_tags(tags)

    if not category and auto_categorize:
        # Use LLM to auto-categorize based on content and generate keywords
        category, categorization_confidence, generated_keywords = await categorize_with_llm(text_content, doc_title)
        categorization_method = "llm"
    elif not category:
        category = "general"

    combined_tags = merge_tags(manual_tags, generated_keywords)

    # Upload chunks to Vertex AI
    if len(chunks) == 1:
        # Single chunk - upload as one document
        result = engine.create_document(
            client_id=client_id,
            content=chunks[0],
            title=doc_title,
            category=category,
            source=filename,
            tags=combined_tags
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to upload: {result.get('error')}")

        return {
            "message": "Document uploaded to Vertex AI successfully",
            "document": {
                "id": result.get("document_id"),
                "client_id": client_id,
                "title": result.get("title"),
                "source_type": result.get("category"),
                "tags": combined_tags,
                "size": result.get("size"),
                "source": "vertex_ai"
            },
            "chunks_created": 1,
            "categorization": {
                "method": categorization_method,
                "category": category,
                "confidence": categorization_confidence,
                "keywords": generated_keywords
            }
        }
    else:
        # Multiple chunks - upload each as separate document
        results = engine.import_documents(
            client_id=client_id,
            chunks=chunks,
            title=doc_title,
            category=category,  # Use the determined category (manual, LLM, or default)
            source=filename,
            tags=combined_tags
        )

        if not results.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to upload: {results.get('error')}")

        return {
            "message": f"Document chunked and uploaded to Vertex AI ({results.get('documents_created')} chunks)",
            "document": {
                "id": results.get("document_ids", [""])[0],
                "client_id": client_id,
                "title": doc_title,
                "source_type": category,
                "tags": combined_tags,
                "size": sum(len(c) for c in chunks),
                "source": "vertex_ai"
            },
            "chunks_created": results.get("documents_created", len(chunks)),
            "categorization": {
                "method": categorization_method,
                "category": category,
                "confidence": categorization_confidence,
                "keywords": generated_keywords
            }
        }

@app.post("/api/documents/{client_id}/text")
async def upload_text(
    client_id: str,
    content: str = Form(...),
    title: Optional[str] = Form("Text Document"),
    source_type: Optional[str] = Form(None),
    auto_categorize: bool = Form(True),  # NEW: Auto-categorize by default
    tags: Optional[str] = Form("")
):
    """
    Upload text content directly to Vertex AI.

    If auto_categorize=True and source_type is not provided, uses LLM to automatically
    determine the most appropriate category based on content analysis.
    """
    client_id = require_canonical_client_id(client_id)
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Determine category - use LLM if auto_categorize and no source_type provided
    category = source_type
    categorization_method = "manual"
    categorization_confidence = 1.0
    generated_keywords = []
    manual_tags = parse_tags(tags)

    if not category and auto_categorize:
        # Use LLM to auto-categorize based on content and generate keywords
        category, categorization_confidence, generated_keywords = await categorize_with_llm(content, title)
        categorization_method = "llm"
    elif not category:
        category = "general"

    combined_tags = merge_tags(manual_tags, generated_keywords)

    # Upload to Vertex AI
    result = engine.create_document(
        client_id=client_id,
        content=content,
        title=title or "Text Document",
        category=category,
        source="text_input",
        tags=combined_tags
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"Failed to upload: {result.get('error')}")

    return {
        "message": "Text uploaded to Vertex AI successfully",
        "document": {
            "id": result.get("document_id"),
            "client_id": client_id,
            "title": result.get("title"),
            "source_type": result.get("category"),
            "tags": combined_tags,
            "size": result.get("size"),
            "source": "vertex_ai"
        },
        "categorization": {
            "method": categorization_method,
            "category": category,
            "confidence": categorization_confidence,
            "keywords": generated_keywords
        }
    }

@app.get("/api/documents/{client_id}/{doc_id}")
def get_document(client_id: str, doc_id: str):
    """Get a specific document from Vertex AI with full content"""
    client_id = require_canonical_client_id(client_id)
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    result = engine.get_document(doc_id)

    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Document not found"))

    return result.get("document")

@app.delete("/api/documents/{client_id}/{doc_id}")
def delete_document(client_id: str, doc_id: str):
    """Delete a document from Vertex AI"""
    client_id = require_canonical_client_id(client_id)
    result = engine.delete_document(doc_id)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=f"Failed to delete: {result.get('error')}")

    return {"message": "Document deleted from Vertex AI successfully"}


@app.get("/api/categories")
def list_categories():
    """
    List all available document categories for RAG ingestion.

    Returns standard categories that align with the V3/V4 workflow
    phase-based filtering system.
    """
    return {
        "categories": [
            {
                "name": name,
                "description": info["description"],
                "phase": info["phase"],
                "keywords": info["keywords"]
            }
            for name, info in STANDARD_CATEGORIES.items()
        ],
        "auto_categorization_available": True,
        "llm_model": "claude-3-5-haiku-latest"
    }

@app.get("/api/stats/{client_id}")
def get_client_stats(client_id: str):
    """Get statistics for a client from Vertex AI"""
    client_id = require_canonical_client_id(client_id)
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Fetch stats from Vertex AI
    return engine.get_client_stats(client_id)

# ============================================================================
# GOOGLE DOCS OAUTH ENDPOINTS
# ============================================================================
@app.get("/api/google/status")
def google_oauth_status():
    """Check if Google OAuth is configured and available."""
    return {
        "configured": google_docs.is_configured(),
        "message": "Google Docs import is available" if google_docs.is_configured()
                   else "Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
    }

@app.get("/api/google/auth")
def google_auth_start(client_id: Optional[str] = None):
    """Start Google OAuth flow. Returns URL to redirect user to."""
    if not google_docs.is_configured():
        raise HTTPException(status_code=503, detail="Google OAuth not configured")

    # Include client_id in state so we know where to import after auth
    state = require_canonical_client_id(client_id) if client_id else ""
    auth_url = google_docs.get_auth_url(state=state)

    return {"auth_url": auth_url}

@app.get("/api/google/callback")
def google_auth_callback(code: str, state: Optional[str] = None):
    """
    OAuth callback endpoint. Google redirects here after user grants access.
    Returns session_id for subsequent API calls.
    """
    try:
        result = google_docs.exchange_code(code)
        # Redirect to UI with session info
        redirect_url = f"/ui/?google_session={result['session_id']}"
        if state:
            normalized_state = normalize_client_id(state)
            if normalized_state and is_canonical_client_id(normalized_state):
                redirect_url += f"&client_id={normalized_state}"
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")

@app.get("/api/google/docs")
def list_google_docs(session_id: str, limit: int = 20):
    """List user's recent Google Docs (requires valid session)."""
    result = google_docs.list_recent_docs(session_id, max_results=limit)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error"))
    return result

class GoogleDocImport(BaseModel):
    session_id: str
    doc_url: str
    client_id: str
    source_type: Optional[str] = "general"
    title: Optional[str] = None

@app.post("/api/google/import")
async def import_google_doc(request: GoogleDocImport):
    """
    Import a Google Doc into the RAG system for a specific client.
    Fetches the doc content, chunks it, and uploads to Vertex AI.
    """
    client_id = require_canonical_client_id(request.client_id)
    # Validate client
    if not is_valid_client(client_id):
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found")

    # Fetch document from Google
    doc_result = google_docs.fetch_document(request.session_id, request.doc_url)
    if not doc_result.get("success"):
        raise HTTPException(status_code=400, detail=doc_result.get("error"))

    content = doc_result.get("content", "")
    doc_title = request.title or doc_result.get("title", "Google Doc")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Document is empty or could not extract text")

    # Chunk the content
    chunks = chunk_text(content)

    # Upload to Vertex AI
    if len(chunks) == 1:
        result = engine.create_document(
            client_id=client_id,
            content=chunks[0],
            title=doc_title,
            category=request.source_type or "general",
            source=f"google_doc:{doc_result.get('doc_id')}"
        )
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to upload: {result.get('error')}")

        return {
            "message": "Google Doc imported successfully",
            "document": {
                "id": result.get("document_id"),
                "client_id": client_id,
                "title": doc_title,
                "source_type": request.source_type,
                "word_count": doc_result.get("word_count"),
                "source": "google_docs"
            },
            "chunks_created": 1
        }
    else:
        results = engine.import_documents(
            client_id=client_id,
            chunks=chunks,
            title=doc_title,
            category=request.source_type or "general",
            source=f"google_doc:{doc_result.get('doc_id')}"
        )
        if not results.get("success"):
            raise HTTPException(status_code=500, detail=f"Failed to upload: {results.get('error')}")

        return {
            "message": f"Google Doc imported ({results.get('documents_created')} chunks)",
            "document": {
                "id": results.get("document_ids", [""])[0],
                "client_id": client_id,
                "title": doc_title,
                "source_type": request.source_type,
                "word_count": doc_result.get("word_count"),
                "source": "google_docs"
            },
            "chunks_created": results.get("documents_created", len(chunks))
        }

# UI Routes
@app.get("/")
def root():
    """Serve Intelligence Hub UI at root"""
    return FileResponse(UI_DIR / "index.html")

@app.get("/ui/")
def serve_ui():
    """Redirect /ui/ to root"""
    return RedirectResponse(url="/", status_code=301)

# Mount static files for UI assets
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")

# ============================================================================
# FIGMA FEEDBACK PIPELINE ROUTES
# ============================================================================
try:
    import importlib.util
    figma_feedback_path = Path(__file__).parent.parent / "pipelines" / "figma-comments"
    figma_feedback_routes_file = figma_feedback_path / "api" / "routes.py"

    if str(figma_feedback_path) not in sys.path:
        sys.path.insert(0, str(figma_feedback_path))

    spec = importlib.util.spec_from_file_location("figma_feedback_routes", figma_feedback_routes_file)
    figma_feedback_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(figma_feedback_module)

    app.include_router(figma_feedback_module.router)
    print("✅ Figma Feedback routes loaded")
except ImportError as e:
    print(f"⚠️ Figma Feedback routes not loaded: {e}")
except Exception as e:
    print(f"⚠️ Figma Feedback routes error: {e}")

# ============================================================================
# IMAGE REPOSITORY PIPELINE ROUTES
# ============================================================================
# Import and include image repository routes (lazy loading to avoid startup errors)
try:
    import sys
    import importlib.util
    # Load image-repository routes using importlib to avoid module caching issues
    pipelines_path = Path(__file__).parent.parent / "pipelines" / "image-repository"
    image_routes_file = pipelines_path / "api" / "routes.py"

    if pipelines_path not in sys.path:
        sys.path.insert(0, str(pipelines_path))

    spec = importlib.util.spec_from_file_location("image_repository_routes", image_routes_file)
    image_routes_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(image_routes_module)

    app.include_router(image_routes_module.router)
    print("✅ Image Repository routes loaded")
except ImportError as e:
    print(f"⚠️ Image Repository routes not loaded: {e}")
except Exception as e:
    print(f"⚠️ Image Repository routes error: {e}")

# ============================================================================
# FIGMA EMAIL REVIEW PIPELINE ROUTES
# ============================================================================
# Import and include Figma email review routes using importlib to avoid module caching
try:
    figma_review_path = Path(__file__).parent.parent / "pipelines" / "figma-email-review"
    figma_review_routes_file = figma_review_path / "api" / "routes.py"

    if str(figma_review_path) not in sys.path:
        sys.path.insert(0, str(figma_review_path))

    spec = importlib.util.spec_from_file_location("figma_review_routes", figma_review_routes_file)
    figma_review_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(figma_review_module)

    app.include_router(figma_review_module.router)
    print("✅ Figma Email Review routes loaded")
except ImportError as e:
    print(f"⚠️ Figma Email Review routes not loaded: {e}")
except Exception as e:
    print(f"⚠️ Figma Email Review routes error: {e}")

# ============================================================================
# EMAIL REPOSITORY PIPELINE ROUTES
# ============================================================================
# Import and include Email Repository routes using importlib to avoid module caching
try:
    email_repo_path = Path(__file__).parent.parent / "pipelines" / "email-repository"
    email_repo_routes_file = email_repo_path / "api" / "routes.py"

    if str(email_repo_path) not in sys.path:
        sys.path.insert(0, str(email_repo_path))

    spec = importlib.util.spec_from_file_location("email_repo_routes", email_repo_routes_file)
    email_repo_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(email_repo_module)

    app.include_router(email_repo_module.router)
    print("✅ Email Repository routes loaded")
except ImportError as e:
    print(f"⚠️ Email Repository routes not loaded: {e}")
except Exception as e:
    print(f"⚠️ Email Repository routes error: {e}")

# ============================================================================
# MEETING INGESTION PIPELINE ROUTES
# ============================================================================
try:
    import importlib.util

    # Ensure RAG root is on path so 'app.*' imports work from submodules
    rag_root = str(Path(__file__).parent.parent)
    if rag_root not in sys.path:
        sys.path.insert(0, rag_root)

    meeting_ingestion_path = Path(__file__).parent.parent / "pipelines" / "meeting-ingestion"
    if str(meeting_ingestion_path) not in sys.path:
        sys.path.insert(0, str(meeting_ingestion_path))

    # Use importlib to avoid module cache conflicts with other api/routes.py files
    routes_file = meeting_ingestion_path / "api" / "routes.py"
    spec = importlib.util.spec_from_file_location("meeting_ingestion_routes", routes_file)
    meeting_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(meeting_module)

    app.include_router(meeting_module.router)
    print("✅ Meeting Ingestion routes loaded")
except ImportError as e:
    print(f"⚠️ Meeting Ingestion routes not loaded: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"⚠️ Meeting Ingestion routes error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# INTELLIGENCE GRADING PIPELINE ROUTES
# ============================================================================
try:
    import importlib.util

    intelligence_grading_path = Path(__file__).parent.parent / "pipelines" / "intelligence-grading"
    routes_file = intelligence_grading_path / "api" / "routes.py"

    if routes_file.exists():
        # Add pipeline to path
        if str(intelligence_grading_path) not in sys.path:
            sys.path.insert(0, str(intelligence_grading_path))

        spec = importlib.util.spec_from_file_location("intelligence_grading_routes", routes_file)
        grading_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grading_module)

        app.include_router(grading_module.router)
        print("✅ Intelligence Grading routes loaded")
    else:
        print(f"⚠️ Intelligence Grading routes file not found at {routes_file}")
except ImportError as e:
    print(f"⚠️ Intelligence Grading routes not loaded: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"⚠️ Intelligence Grading routes error: {e}")
    import traceback
    traceback.print_exc()
