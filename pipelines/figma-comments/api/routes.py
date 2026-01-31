from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from datetime import datetime
import logging
import os
import json

from app.client_id import normalize_client_id, is_canonical_client_id
from app.services.vertex_search import get_vertex_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/figma-feedback", tags=["Figma Feedback"])

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
    """Ingest rules as documents into Vertex AI."""
    engine = get_vertex_engine()
    for rule in rules:
        content = f"Creative Rule ({rule['category']}): {rule['rule_text']}\nSentiment: {rule['sentiment']}"
        engine.create_document(
            client_id=client_id,
            content=content,
            title=f"Figma Feedback Rule - {rule['category']}",
            category="creative_rule",
            source=f"figma:{rule['source_file']}",
            tags=["figma", "feedback", rule['category'], rule['sentiment']]
        )

@router.get("/health")
def health():
    return {"status": "ok", "bq_available": BQ_AVAILABLE}
