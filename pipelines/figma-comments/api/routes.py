from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging
import os
import json
import httpx
import asyncio
import re

from app.client_id import normalize_client_id, is_canonical_client_id
from app.services.vertex_search import get_vertex_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/figma-feedback", tags=["Figma Feedback"])

# Orchestrator URL for Firestore ingestion (unified data layer)
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8001")
INTERNAL_SERVICE_KEY = os.getenv("INTERNAL_SERVICE_KEY", "")

# Figma API Configuration (check both env var names for compatibility)
FIGMA_API_TOKEN = os.getenv("FIGMA_API_TOKEN") or os.getenv("FIGMA_ACCESS_TOKEN", "")
FIGMA_API_BASE = "https://api.figma.com/v1"

# Asana API Configuration
ASANA_PAT = os.getenv("ASANA_PAT", "")
ASANA_API_BASE = "https://app.asana.com/api/1.0"
ASANA_STAGE_FIELD_GID = os.getenv("ASANA_STAGE_FIELD_GID", "1203470409880617")
ASANA_DONE_VALUE_GID = os.getenv("ASANA_DONE_VALUE_GID", "1203470409881675")
ASANA_PROJECT_NAMES = [
    "📩 Ayaan's Messaging Workflows",
    "📩 Leslie Messaging Workflows",
    "📢 Kers' Messaging Workflow",
    "📩 Team 4 Campaigns",
]
FIGMA_URL_REGEX = r'/(?:file|proto|design)/([a-zA-Z0-9]+)(?:/|$)'

# BigQuery Configuration
BQ_DATASET_ID = os.getenv("FIGMA_BQ_DATASET", "figma")
BQ_TABLE_ID = os.getenv("FIGMA_BQ_TABLE", "comments")
GCP_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "emailpilot-438321")

try:
    from google.cloud import bigquery
    BQ_CLIENT = bigquery.Client(project=GCP_PROJECT_ID)
    BQ_AVAILABLE = True
    logger.info(f"✅ BigQuery client initialized for project {GCP_PROJECT_ID}")
except Exception as e:
    BQ_AVAILABLE = False
    BQ_CLIENT = None
    logger.warning(f"⚠️ BigQuery client not available: {e}")

class FigmaComment(BaseModel):
    comment_id: str
    file_key: str
    comment_text: str
    created_at: str
    resolved_at: Optional[str] = None
    user_name: str
    client_id: str

class ProcessRequest(BaseModel):
    client_id: str
    lookback_hours: int = 24

class FeedbackRule(BaseModel):
    rule: str
    sentiment: str
    category: str
    source_file: str
    source_comment_id: str
    client_id: str
    ingested_at: str

@router.post("/process")
async def process_figma_feedback(request: ProcessRequest, background_tasks: BackgroundTasks):
    """
    Trigger the processing of new Figma comments from BigQuery into Creative Rules.
    This reads from BQ, processes with Gemini, and saves to Vertex AI.
    """
    if not BQ_AVAILABLE:
        raise HTTPException(status_code=503, detail="BigQuery not available")

    client_id = normalize_client_id(request.client_id)
    if not is_canonical_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # Start background processing
    background_tasks.add_task(run_feedback_pipeline, client_id, request.lookback_hours)

    return {
        "success": True,
        "message": f"Feedback processing started for {client_id}",
        "client_id": client_id
    }

@router.get("/rules/{client_id}")
async def list_creative_rules(client_id: str):
    """List creative rules extracted for a client from BigQuery."""
    if not BQ_AVAILABLE:
        raise HTTPException(status_code=503, detail="BigQuery not available")

    client_id = normalize_client_id(client_id)
    
    try:
        # Use parameterized query to prevent SQL injection
        query = f"""
            SELECT rule_text, sentiment, category, source_file, ingested_at
            FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ID}.creative_rules`
            WHERE client_id = @client_id
            ORDER BY ingested_at DESC
            LIMIT 100
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("client_id", "STRING", client_id)
            ]
        )
        query_job = BQ_CLIENT.query(query, job_config=job_config)
        results = query_job.result()
        
        rules = []
        for row in results:
            rules.append({
                "rule": row.rule_text,
                "sentiment": row.sentiment,
                "category": row.category,
                "source_file": row.source_file,
                "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None
            })
            
        return {"client_id": client_id, "rules": rules, "count": len(rules)}
    except Exception as e:
        logger.error(f"Error fetching rules: {e}")
        return {"client_id": client_id, "rules": [], "error": str(e)}

async def run_feedback_pipeline(client_id: str, lookback_hours: int):
    """The actual pipeline execution logic."""
    logger.info(f"🚀 Running Figma Feedback Pipeline for {client_id}")
    
    try:
        # 1. Fetch new comments from BQ
        comments = fetch_new_comments(client_id, lookback_hours)
        if not comments:
            logger.info(f"No new comments found for {client_id} in the last {lookback_hours} hours")
            return

        # 2. Process with AI (Simulated for now)
        rules = []
        for comment in comments:
            rule = extract_rule_simulated(comment)
            if rule:
                rules.append(rule)

        if not rules:
            logger.info(f"No creative rules extracted from {len(comments)} comments")
            return

        # 3. Save rules to BigQuery (Table: creative_rules)
        save_rules_to_bq(rules)

        # 4. Ingest into Vertex AI RAG
        ingest_into_rag(client_id, rules)

        logger.info(f"✅ Pipeline complete: {len(rules)} rules created for {client_id}")

    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)

def fetch_new_comments(client_id: str, hours: int) -> List[Dict]:
    """Retrieve comments from project.figma.comments."""
    # Use parameterized query to prevent SQL injection
    query = f"""
        SELECT comment_id, file_key, comment_text, created_at, user_name
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ID}.{BQ_TABLE_ID}`
        WHERE client_id = @client_id
          AND created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
          AND user_name NOT LIKE '%Internal%'
          AND LENGTH(comment_text) > 10
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("client_id", "STRING", client_id),
            bigquery.ScalarQueryParameter("hours", "INT64", hours)
        ]
    )
    query_job = BQ_CLIENT.query(query, job_config=job_config)
    return [dict(row) for row in query_job.result()]

def extract_rule_simulated(comment: Dict) -> Optional[Dict]:
    """Simulates AI rule extraction."""
    text = comment['comment_text'].lower()
    
    category = "general"
    sentiment = "neutral"
    
    if any(k in text for k in ["tone", "voice", "feel"]): category = "tone"
    elif any(k in text for k in ["copy", "text", "headline"]): category = "copy"
    elif any(k in text for k in ["image", "photo", "graphic"]): category = "imagery"
    
    if any(k in text for k in ["bad", "wrong", "hate", "don't"]): sentiment = "negative"
    elif any(k in text for k in ["good", "love", "keep"]): sentiment = "positive"
    
    # Only return if it seems like a real rule
    if category != "general" or sentiment != "neutral":
        return {
            "rule_text": comment['comment_text'],
            "sentiment": sentiment,
            "category": category,
            "source_file": comment['file_key'],
            "source_comment_id": comment['comment_id'],
            "client_id": "placeholder", # Will be overwritten
            "ingested_at": datetime.utcnow().isoformat()
        }
    return None

def save_rules_to_bq(rules: List[Dict]):
    """Insert into creative_rules table."""
    table_id = f"{GCP_PROJECT_ID}.{BQ_DATASET_ID}.creative_rules"
    errors = BQ_CLIENT.insert_rows_json(table_id, rules)
    if errors:
        logger.error(f"BQ Insert Rules Error: {errors}")

def ingest_into_rag(client_id: str, rules: List[Dict]):
    """Ingest rules as documents into Vertex AI with semantic search optimization."""
    engine = get_vertex_engine()
    for rule in rules:
        # Create content optimized for semantic search with clear Do/Don't format
        sentiment = rule['sentiment']
        category = rule['category']
        rule_text = rule['rule_text']

        # Format content to match search query "Figma comments, feedback, and design review notes"
        if sentiment == 'positive':
            content = f"""Figma Design Feedback - DO:
Category: {category.title()}
Feedback: {rule_text}

This is a positive design guideline to FOLLOW. Apply this feedback when creating email designs."""
        elif sentiment == 'negative':
            content = f"""Figma Design Feedback - DON'T:
Category: {category.title()}
Feedback: {rule_text}

This is a negative design constraint to AVOID. Do not repeat this mistake in email designs."""
        else:
            content = f"""Figma Design Feedback:
Category: {category.title()}
Feedback: {rule_text}

Design review note from Figma comments."""

        engine.create_document(
            client_id=client_id,
            content=content,
            title=f"Figma Feedback - {sentiment.title()} - {category.title()}",
            category="figma_comments",  # Changed from "creative_rule" for better RAG retrieval
            source=f"figma:{rule['source_file']}",
            tags=["figma", "feedback", "design_review", category, sentiment]
        )

@router.post("/backfill/{client_id}")
async def backfill_figma_feedback(
    client_id: str,
    days_back: int = 60,
    background_tasks: BackgroundTasks = None
):
    """
    Backfill historical Figma comments for a client.
    Processes all comments from BigQuery for the specified time period.
    """
    if not BQ_AVAILABLE:
        raise HTTPException(status_code=503, detail="BigQuery not available")

    client_id = normalize_client_id(client_id)
    if not is_canonical_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    background_tasks.add_task(run_backfill_pipeline, client_id, days_back)

    return {
        "success": True,
        "message": f"Backfill started for {client_id} - processing {days_back} days",
        "client_id": client_id,
        "days_back": days_back
    }


async def run_backfill_pipeline(client_id: str, days_back: int):
    """Backfill pipeline - processes historical comments in batches."""
    logger.info(f"🚀 Running Figma Feedback Backfill for {client_id} ({days_back} days)")

    try:
        comments = fetch_historical_comments(client_id, days_back)
        logger.info(f"Found {len(comments)} comments for backfill")

        if not comments:
            logger.info(f"No comments found for {client_id} in the last {days_back} days")
            return

        # Process in batches
        batch_size = 50
        total_rules = 0

        for i in range(0, len(comments), batch_size):
            batch = comments[i:i + batch_size]
            rules = []

            for comment in batch:
                rule = extract_rule_simulated(comment)
                if rule:
                    rule['client_id'] = client_id
                    rules.append(rule)

            if rules:
                save_rules_to_bq(rules)
                ingest_into_rag(client_id, rules)
                total_rules += len(rules)

            logger.info(f"Processed batch {i//batch_size + 1}: {len(rules)} rules")

        logger.info(f"✅ Backfill complete: {total_rules} rules created for {client_id}")

    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}", exc_info=True)


def fetch_historical_comments(client_id: str, days: int) -> List[Dict]:
    """Retrieve comments from the last N days."""
    query = f"""
        SELECT comment_id, file_key, comment_text, created_at, user_name
        FROM `{GCP_PROJECT_ID}.{BQ_DATASET_ID}.{BQ_TABLE_ID}`
        WHERE client_id = @client_id
          AND created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
          AND user_name NOT LIKE '%Internal%'
          AND LENGTH(comment_text) > 10
        ORDER BY created_at DESC
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("client_id", "STRING", client_id),
            bigquery.ScalarQueryParameter("days", "INT64", days)
        ]
    )
    query_job = BQ_CLIENT.query(query, job_config=job_config)
    return [dict(row) for row in query_job.result()]


@router.get("/health")
def health():
    return {"status": "ok", "bq_available": BQ_AVAILABLE, "figma_token_configured": bool(FIGMA_API_TOKEN)}


# =============================================================================
# DIRECT FIGMA API PULL (Bypasses BigQuery - pulls directly from Figma)
# =============================================================================

class DirectPullRequest(BaseModel):
    """Request for direct Figma API pull."""
    client_id: str
    file_keys: List[str] = Field(..., description="List of Figma file keys to pull comments from")
    days_back: int = Field(60, description="Only include comments from the last N days")


async def fetch_figma_comments_api(file_key: str, token: str) -> List[Dict]:
    """Fetch ALL comments from a Figma file via the Figma API."""
    url = f"{FIGMA_API_BASE}/files/{file_key}/comments"
    headers = {"X-Figma-Token": token}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid Figma API token")
        if response.status_code == 403:
            raise HTTPException(status_code=403, detail="Figma API token expired or lacks permissions")
        if response.status_code == 404:
            logger.warning(f"Figma file not found: {file_key}")
            return []
        if response.status_code == 429:
            raise HTTPException(status_code=429, detail="Figma API rate limited. Try again later.")
        if not response.is_success:
            raise HTTPException(status_code=response.status_code, detail=f"Figma API error: {response.text}")

        data = response.json()
        return data.get("comments", [])


def transform_figma_comment(comment: Dict, file_key: str, client_id: str) -> Dict:
    """Transform Figma API comment to our internal format."""
    return {
        "comment_id": comment.get("id", ""),
        "file_key": file_key,
        "comment_text": comment.get("message", ""),
        "created_at": comment.get("created_at", ""),
        "resolved_at": comment.get("resolved_at"),
        "user_name": comment.get("user", {}).get("handle") or comment.get("user", {}).get("id", "Unknown"),
        "client_id": client_id
    }


def save_comments_to_bq(comments: List[Dict]):
    """Insert raw comments into figma.comments table."""
    if not comments or not BQ_AVAILABLE:
        return
    table_id = f"{GCP_PROJECT_ID}.{BQ_DATASET_ID}.{BQ_TABLE_ID}"

    # Transform to BQ schema
    rows = []
    for c in comments:
        rows.append({
            "comment_id": c["comment_id"],
            "client_id": c["client_id"],
            "file_key": c["file_key"],
            "comment_text": c["comment_text"],
            "created_at": c["created_at"],
            "resolved_at": c.get("resolved_at"),
            "user_name": c["user_name"],
            "copy_and_design": "",  # Not available from direct API pull
            "ingested_at": datetime.utcnow().isoformat()
        })

    errors = BQ_CLIENT.insert_rows_json(table_id, rows)
    if errors:
        logger.error(f"BQ Insert Comments Error: {errors}")
    else:
        logger.info(f"Saved {len(rows)} comments to BigQuery")


async def push_comments_to_firestore(client_id: str, file_key: str, comments: List[Dict], file_name: Optional[str] = None):
    """
    Push comments to Firestore via orchestrator's design-feedback ingest endpoint.

    This creates a unified data layer where both the Design Feedback UI and RAG
    read from the same source (Firestore).

    Uses X-Internal-Service-Key header for service-to-service authentication.
    """
    if not comments:
        logger.info("No comments to push to Firestore")
        return

    if not INTERNAL_SERVICE_KEY:
        logger.warning("INTERNAL_SERVICE_KEY not configured - skipping Firestore ingestion")
        return

    # Transform comments to the orchestrator's expected format
    ingest_payload = {
        "client_id": client_id,
        "file_key": file_key,
        "file_name": file_name,
        "comments": [
            {
                "comment_id": c["comment_id"],
                "message": c["comment_text"],
                "user_name": c["user_name"],
                "created_at": c["created_at"],
                "resolved_at": c.get("resolved_at"),
                "parent_id": c.get("parent_id"),
                "file_name": file_name
            }
            for c in comments
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{ORCHESTRATOR_URL}/api/design-feedback/ingest",
                headers={
                    "X-Internal-Service-Key": INTERNAL_SERVICE_KEY,
                    "Content-Type": "application/json"
                },
                json=ingest_payload
            )

            if response.is_success:
                data = response.json()
                logger.info(
                    f"✅ Pushed {len(comments)} comments to Firestore for {client_id}",
                    extra={"ingested_count": data.get("ingested_count")}
                )
            else:
                logger.error(
                    f"Failed to push comments to Firestore: HTTP {response.status_code}",
                    extra={"response": response.text[:500]}
                )
    except Exception as e:
        logger.error(f"Error pushing comments to Firestore: {e}", exc_info=True)


@router.post("/pull-from-figma")
async def pull_from_figma_api(
    request: DirectPullRequest,
    background_tasks: BackgroundTasks
):
    """
    Pull comments directly from Figma API and process them.

    This bypasses BigQuery and fetches ALL historical comments from the specified
    Figma files, then processes them into creative rules for RAG.

    Use this for initial backfill when BigQuery is empty.
    """
    if not FIGMA_API_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="FIGMA_API_TOKEN not configured. Set it in environment variables."
        )

    client_id = normalize_client_id(request.client_id)
    if not is_canonical_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    if not request.file_keys:
        raise HTTPException(status_code=400, detail="At least one file_key is required")

    # Start background processing
    background_tasks.add_task(
        run_direct_figma_pull,
        client_id,
        request.file_keys,
        request.days_back
    )

    return {
        "success": True,
        "message": f"Direct Figma pull started for {client_id}",
        "client_id": client_id,
        "file_keys": request.file_keys,
        "days_back": request.days_back
    }


async def run_direct_figma_pull(client_id: str, file_keys: List[str], days_back: int):
    """
    Background task to pull comments from Figma API and process them.

    This implements the unified three-layer architecture:
    1. Source: Figma API (raw comments)
    2. Operational: Firestore (via orchestrator's /api/design-feedback/ingest)
    3. Knowledge: Vertex AI RAG (for brief generation semantic search)

    Also saves to BigQuery for historical analysis.
    """
    logger.info(f"🚀 Starting direct Figma pull for {client_id} from {len(file_keys)} files")

    cutoff_date = datetime.utcnow() - timedelta(days=days_back)
    total_comments = 0
    total_rules = 0

    for file_key in file_keys:
        try:
            logger.info(f"Fetching comments from Figma file: {file_key}")

            # Fetch from Figma API
            raw_comments = await fetch_figma_comments_api(file_key, FIGMA_API_TOKEN)
            logger.info(f"Got {len(raw_comments)} raw comments from {file_key}")

            # Transform and filter by date
            comments = []
            for raw in raw_comments:
                created_at_str = raw.get("created_at", "")
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created_at.replace(tzinfo=None) < cutoff_date:
                        continue  # Skip comments older than cutoff
                except:
                    pass  # Include if we can't parse the date

                comment = transform_figma_comment(raw, file_key, client_id)
                if len(comment["comment_text"]) > 10:  # Skip very short comments
                    comments.append(comment)

            logger.info(f"Filtered to {len(comments)} comments within {days_back} days")
            total_comments += len(comments)

            if not comments:
                continue

            # Layer 2: Save to Firestore (Operational - for Design Feedback UI)
            await push_comments_to_firestore(client_id, file_key, comments, file_name=f"Figma file {file_key}")

            # Also save to BigQuery (legacy - for historical analysis)
            save_comments_to_bq(comments)

            # Process into rules for RAG
            rules = []
            for comment in comments:
                rule = extract_rule_simulated(comment)
                if rule:
                    rule['client_id'] = client_id
                    rules.append(rule)

            if rules:
                save_rules_to_bq(rules)
                # Layer 3: Ingest into Vertex AI RAG (Knowledge - for brief generation)
                ingest_into_rag(client_id, rules)
                total_rules += len(rules)
                logger.info(f"Created {len(rules)} rules from {file_key}")

            # Rate limit: wait between files
            await asyncio.sleep(1)

        except HTTPException as e:
            logger.error(f"HTTP error fetching {file_key}: {e.detail}")
        except Exception as e:
            logger.error(f"Error processing {file_key}: {e}", exc_info=True)

    logger.info(f"✅ Direct Figma pull complete: {total_comments} comments → {total_rules} rules for {client_id}")


@router.get("/figma-token-status")
async def check_figma_token():
    """Check if the Figma API token is valid."""
    if not FIGMA_API_TOKEN:
        return {
            "configured": False,
            "valid": False,
            "error": "FIGMA_API_TOKEN not set"
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{FIGMA_API_BASE}/me",
                headers={"X-Figma-Token": FIGMA_API_TOKEN}
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "configured": True,
                    "valid": True,
                    "user": {
                        "id": data.get("id"),
                        "email": data.get("email"),
                        "handle": data.get("handle")
                    }
                }
            else:
                return {
                    "configured": True,
                    "valid": False,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}"
                }
    except Exception as e:
        return {
            "configured": True,
            "valid": False,
            "error": str(e)
        }


# =============================================================================
# ASANA LOOKUP - Find Figma files for a client from Asana tasks
# =============================================================================

def parse_figma_file_key(url: str) -> Optional[str]:
    """Extract Figma file key from a URL."""
    if not url:
        return None
    match = re.search(FIGMA_URL_REGEX, url)
    return match.group(1) if match else None


async def get_asana_workspace_id(token: str) -> str:
    """Get the first Asana workspace ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{ASANA_API_BASE}/workspaces",
            headers={"Authorization": f"Bearer {token}"}
        )
        if not response.is_success:
            raise HTTPException(status_code=response.status_code, detail="Failed to get Asana workspaces")
        data = response.json()
        workspaces = data.get("data", [])
        if not workspaces:
            raise HTTPException(status_code=404, detail="No Asana workspaces found")
        return workspaces[0]["gid"]


async def get_asana_projects(token: str, workspace_id: str) -> List[Dict]:
    """Get all projects in a workspace."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{ASANA_API_BASE}/projects",
            headers={"Authorization": f"Bearer {token}"},
            params={"workspace": workspace_id}
        )
        if not response.is_success:
            raise HTTPException(status_code=response.status_code, detail="Failed to get Asana projects")
        return response.json().get("data", [])


async def get_done_tasks_for_project(token: str, project_gid: str, lookback_days: int = 60) -> List[Dict]:
    """Get tasks in 'Done' stage from a project."""
    completed_since = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat()

    all_tasks = []
    offset = None

    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            params = {
                "project": project_gid,
                "opt_fields": "name,custom_fields.gid,custom_fields.name,custom_fields.display_value,custom_fields.enum_value.gid",
                "limit": 100,
                "completed_since": completed_since
            }
            if offset:
                params["offset"] = offset

            response = await client.get(
                f"{ASANA_API_BASE}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                params=params
            )

            if not response.is_success:
                logger.warning(f"Failed to get tasks for project {project_gid}: {response.status_code}")
                break

            data = response.json()
            tasks = data.get("data", [])

            # Filter for "Done" tasks
            for task in tasks:
                custom_fields = task.get("custom_fields", [])
                stage_field = next(
                    (f for f in custom_fields if f.get("gid") == ASANA_STAGE_FIELD_GID),
                    None
                )
                if stage_field:
                    enum_value = stage_field.get("enum_value") or {}
                    if enum_value.get("gid") == ASANA_DONE_VALUE_GID:
                        all_tasks.append(task)

            # Pagination
            next_page = data.get("next_page")
            if next_page and next_page.get("offset"):
                offset = next_page["offset"]
            else:
                break

    return all_tasks


def extract_figma_urls_from_task(task: Dict) -> tuple:
    """Extract client name and Figma URL from task custom fields."""
    custom_fields = task.get("custom_fields", [])

    client_name = None
    figma_url = None

    for field in custom_fields:
        field_name = (field.get("name") or "").lower()
        display_value = field.get("display_value") or ""

        if field_name == "client":
            client_name = display_value
        elif field_name == "figma url":
            figma_url = display_value

    return client_name, figma_url


@router.get("/discover-figma-files/{client_id}")
async def discover_figma_files(client_id: str, lookback_days: int = 60):
    """
    Discover Figma file keys for a client by searching Asana tasks.

    Searches through the configured Asana projects for tasks in "Done" stage
    that match the specified client, then extracts and returns the Figma file keys.
    """
    if not ASANA_PAT:
        raise HTTPException(
            status_code=503,
            detail="ASANA_PAT not configured. Set it in environment variables."
        )

    client_id = normalize_client_id(client_id)
    if not is_canonical_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # Normalize client_id for matching (e.g., "rogue-creamery" -> "roguecreamery", "rogue creamery")
    client_normalized = client_id.replace("-", "").lower()
    client_with_spaces = client_id.replace("-", " ").lower()

    try:
        workspace_id = await get_asana_workspace_id(ASANA_PAT)
        all_projects = await get_asana_projects(ASANA_PAT, workspace_id)

        # Filter to our target projects
        target_projects = [p for p in all_projects if p.get("name") in ASANA_PROJECT_NAMES]
        logger.info(f"Found {len(target_projects)} target projects to search")

        file_keys = set()
        tasks_found = []

        for project in target_projects:
            logger.info(f"Searching project: {project.get('name')}")
            tasks = await get_done_tasks_for_project(ASANA_PAT, project["gid"], lookback_days)
            logger.info(f"Found {len(tasks)} done tasks in {project.get('name')}")

            for task in tasks:
                task_client, figma_url = extract_figma_urls_from_task(task)

                if not task_client or not figma_url:
                    continue

                # Normalize task client for matching
                task_client_normalized = task_client.replace("-", "").replace(" ", "").lower()

                # Check if client matches
                if client_normalized in task_client_normalized or task_client_normalized in client_normalized:
                    file_key = parse_figma_file_key(figma_url)
                    if file_key:
                        file_keys.add(file_key)
                        tasks_found.append({
                            "task_name": task.get("name"),
                            "client": task_client,
                            "figma_url": figma_url,
                            "file_key": file_key
                        })

            # Rate limit between projects
            await asyncio.sleep(0.5)

        return {
            "success": True,
            "client_id": client_id,
            "lookback_days": lookback_days,
            "file_keys": list(file_keys),
            "file_count": len(file_keys),
            "tasks_found": tasks_found,
            "projects_searched": [p.get("name") for p in target_projects]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discovering Figma files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to discover Figma files: {str(e)}")


@router.post("/auto-backfill/{client_id}")
async def auto_backfill_from_asana(
    client_id: str,
    days_back: int = 60,
    background_tasks: BackgroundTasks = None
):
    """
    Automatically discover Figma files for a client from Asana and run a full backfill.

    This is the "one-click" backfill that:
    1. Searches Asana for tasks matching the client
    2. Extracts Figma file keys from those tasks
    3. Pulls ALL comments from those files via Figma API
    4. Processes them into creative rules for RAG

    Use this when BigQuery is empty and you need historical data.
    """
    if not ASANA_PAT:
        raise HTTPException(status_code=503, detail="ASANA_PAT not configured")
    if not FIGMA_API_TOKEN:
        raise HTTPException(status_code=503, detail="FIGMA_API_TOKEN not configured")

    client_id = normalize_client_id(client_id)
    if not is_canonical_client_id(client_id):
        raise HTTPException(status_code=400, detail="Invalid client_id")

    # Start background task
    background_tasks.add_task(run_auto_backfill, client_id, days_back)

    return {
        "success": True,
        "message": f"Auto-backfill started for {client_id}",
        "client_id": client_id,
        "days_back": days_back,
        "note": "This will discover Figma files from Asana and pull all historical comments"
    }


async def run_auto_backfill(client_id: str, days_back: int):
    """Background task for auto-backfill."""
    logger.info(f"🚀 Starting auto-backfill for {client_id} ({days_back} days)")

    try:
        # Step 1: Discover Figma files from Asana
        logger.info(f"Step 1: Discovering Figma files for {client_id} from Asana...")

        workspace_id = await get_asana_workspace_id(ASANA_PAT)
        all_projects = await get_asana_projects(ASANA_PAT, workspace_id)
        target_projects = [p for p in all_projects if p.get("name") in ASANA_PROJECT_NAMES]

        client_normalized = client_id.replace("-", "").lower()
        file_keys = set()

        for project in target_projects:
            tasks = await get_done_tasks_for_project(ASANA_PAT, project["gid"], days_back)

            for task in tasks:
                task_client, figma_url = extract_figma_urls_from_task(task)
                if not task_client or not figma_url:
                    continue

                task_client_normalized = task_client.replace("-", "").replace(" ", "").lower()
                if client_normalized in task_client_normalized or task_client_normalized in client_normalized:
                    file_key = parse_figma_file_key(figma_url)
                    if file_key:
                        file_keys.add(file_key)

            await asyncio.sleep(0.5)

        logger.info(f"Discovered {len(file_keys)} unique Figma files for {client_id}")

        if not file_keys:
            logger.warning(f"No Figma files found for {client_id} in Asana tasks")
            return

        # Step 2: Pull comments from Figma API
        logger.info(f"Step 2: Pulling comments from {len(file_keys)} Figma files...")
        await run_direct_figma_pull(client_id, list(file_keys), days_back)

        logger.info(f"✅ Auto-backfill complete for {client_id}")

    except Exception as e:
        logger.error(f"❌ Auto-backfill failed for {client_id}: {e}", exc_info=True)
