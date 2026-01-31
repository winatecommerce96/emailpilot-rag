"""
FastAPI routes for Figma Email Review Pipeline.

Provides endpoints for triggering reviews, checking status, and retrieving reports.
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from app.client_id import normalize_client_id, is_canonical_client_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/figma-review", tags=["Figma Email Review"])


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


# =============================================================================
# Pydantic Request/Response Models
# =============================================================================

class ReviewTriggerRequest(BaseModel):
    """Request body for triggering email review."""
    client_id: str = Field(..., description="Client identifier")
    figma_url: str = Field(..., description="Figma URL (e.g., https://figma.com/file/ABC123/...)")
    asana_task_gid: Optional[str] = Field(None, description="Asana task GID for posting results")
    asana_task_name: Optional[str] = Field(None, description="Asana task name")
    post_results_to_asana: bool = Field(True, description="Post results back to Asana")
    include_brand_voice: bool = Field(True, description="Include RAG brand voice check")
    force_review: bool = Field(False, description="Force review even if recently done")


class ReviewStatusResponse(BaseModel):
    """Response for review status."""
    status: str  # queued, in_progress, completed, error
    message: str
    review_id: Optional[str] = None
    overall_score: Optional[float] = None
    critical_issues_count: Optional[int] = None


class ReviewReportSummary(BaseModel):
    """Summary of a review report for listings."""
    review_id: str
    email_name: str
    overall_score: float
    reviewed_at: str
    critical_issues_count: int
    warnings_count: int
    file_key: str
    frame_id: str
    asana_task_gid: Optional[str] = None


class ReviewReportResponse(BaseModel):
    """Full review report response."""
    review_id: str
    client_id: str
    email_name: str
    overall_score: float
    reviewed_at: str
    report: Dict[str, Any]
    figma_url: Optional[str] = None
    indexed_to_vertex: bool = False


# =============================================================================
# State Management (lazy initialization)
# =============================================================================

_orchestrator = None
_state_manager = None
_config = None


def _reset_orchestrator():
    """Reset the cached orchestrator."""
    global _orchestrator
    _orchestrator = None


def _get_config():
    """Lazy load configuration."""
    global _config
    if _config is None:
        from config.settings import get_pipeline_config
        _config = get_pipeline_config()
    return _config


def _get_state_manager():
    """Lazy initialization of state manager."""
    global _state_manager
    if _state_manager is None:
        from core.state_manager import FigmaReviewStateManager
        config = _get_config()
        _state_manager = FigmaReviewStateManager(
            project_id=config.gcp_project_id,
            collection_prefix=config.firestore_collection
        )
    return _state_manager


async def _get_orchestrator():
    """Lazy initialization of orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        from core.review_orchestrator import create_orchestrator_from_config
        config = _get_config()

        # Check required configuration
        if not config.figma.access_token:
            raise ValueError("FIGMA_ACCESS_TOKEN not configured")
        if not config.vision.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        _orchestrator = await create_orchestrator_from_config(config)

    return _orchestrator


# =============================================================================
# Background Task Runner
# =============================================================================

async def _run_review_task(
    client_id: str,
    figma_url: str,
    asana_task_gid: Optional[str],
    asana_task_name: Optional[str],
    post_results_to_asana: bool,
    include_brand_voice: bool,
    force_review: bool
):
    """Background task to run email review."""
    try:
        orchestrator = await _get_orchestrator()

        result = await orchestrator.review_from_url(
            client_id=client_id,
            figma_url=figma_url,
            force_review=force_review,
            include_brand_voice=include_brand_voice,
            asana_task_gid=asana_task_gid,
            asana_task_name=asana_task_name,
            post_results_to_asana=post_results_to_asana
        )

        logger.info(f"Review completed: {result.get('status')}")

    except Exception as e:
        logger.error(f"Background review failed: {e}", exc_info=True)


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/review", response_model=ReviewStatusResponse)
async def trigger_review(
    request: ReviewTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger email design review.

    Accepts a Figma URL and triggers the review pipeline.
    Runs in background to avoid timeout issues.

    - **client_id**: Client identifier (required)
    - **figma_url**: Figma file/frame URL (required)
    - **asana_task_gid**: Asana task GID for posting results
    - **post_results_to_asana**: Whether to post results to Asana
    - **include_brand_voice**: Include RAG brand voice check
    - **force_review**: Force review even if recently done
    """
    try:
        client_id = require_canonical_client_id(request.client_id)
        # Validate URL format
        from config.settings import parse_figma_url
        url_parts = parse_figma_url(request.figma_url)

        if not url_parts.get("file_key"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Figma URL: could not extract file key from '{request.figma_url}'"
            )

        # Queue background task
        background_tasks.add_task(
            _run_review_task,
            client_id=client_id,
            figma_url=request.figma_url,
            asana_task_gid=request.asana_task_gid,
            asana_task_name=request.asana_task_name,
            post_results_to_asana=request.post_results_to_asana,
            include_brand_voice=request.include_brand_voice,
            force_review=request.force_review
        )

        return ReviewStatusResponse(
            status="queued",
            message=f"Review queued for {client_id}. Processing in background.",
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger review: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{client_id}")
async def list_review_reports(
    client_id: str,
    limit: int = Query(20, le=100, description="Maximum reports to return"),
    min_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum score filter"),
    has_critical_issues: Optional[bool] = Query(None, description="Filter by critical issues")
) -> Dict[str, Any]:
    """
    List review reports for a client.

    Returns paginated list of review summaries with optional filters.
    """
    try:
        client_id = require_canonical_client_id(client_id)
        state_manager = _get_state_manager()

        reports = state_manager.get_review_history(
            client_id=client_id,
            limit=limit,
            min_score=min_score,
            has_critical_issues=has_critical_issues
        )

        return {
            "client_id": client_id,
            "total": len(reports),
            "reports": reports
        }

    except Exception as e:
        logger.error(f"Failed to list reports for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/{client_id}/{review_id}")
async def get_review_report(
    client_id: str,
    review_id: str
) -> Dict[str, Any]:
    """
    Get full review report details.

    Returns the complete review report including all scores and issues.
    """
    try:
        client_id = require_canonical_client_id(client_id)
        state_manager = _get_state_manager()

        review = state_manager.get_review(review_id)

        if not review:
            raise HTTPException(
                status_code=404,
                detail=f"Review {review_id} not found"
            )

        # Verify client ownership
        if review.get("client_id") != client_id:
            raise HTTPException(
                status_code=403,
                detail="Review does not belong to this client"
            )

        # Build Figma URL for reference
        file_key = review.get("file_key", "")
        frame_id = review.get("frame_id", "")
        figma_url = None
        if file_key:
            figma_url = f"https://www.figma.com/file/{file_key}"
            if frame_id:
                # URL-encode the frame ID (replace : with %3A)
                encoded_frame = frame_id.replace(":", "%3A")
                figma_url += f"?node-id={encoded_frame}"

        return {
            "review_id": review_id,
            "client_id": client_id,
            "email_name": review.get("email_name"),
            "overall_score": review.get("overall_score"),
            "reviewed_at": review.get("reviewed_at"),
            "report": review.get("report"),
            "figma_url": figma_url,
            "indexed_to_vertex": review.get("indexed_to_vertex", False),
            "asana_task_gid": review.get("asana_task_gid")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get review {review_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear/{client_id}")
async def clear_client_state(client_id: str) -> Dict[str, Any]:
    """
    Clear all review state and history for a client.

    Does NOT delete indexed insights from Vertex AI.
    Use this to reset review tracking for a fresh start.
    """
    try:
        client_id = require_canonical_client_id(client_id)
        state_manager = _get_state_manager()
        deleted = state_manager.clear_client_state(client_id)

        return {
            "status": "success",
            "client_id": client_id,
            "records_cleared": deleted,
            "message": "Review state cleared. Next review will process all frames fresh."
        }

    except Exception as e:
        logger.error(f"Failed to clear state for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/{client_id}")
async def list_client_insights(
    client_id: str,
    limit: int = Query(20, le=100),
    insight_type: Optional[str] = Query(None, description="Filter by type: recurring_issue, best_practice, brand_pattern")
) -> Dict[str, Any]:
    """
    List indexed review insights for a client.

    Returns insights indexed in Vertex AI that can inform future reviews.
    """
    try:
        client_id = require_canonical_client_id(client_id)
        from core.vertex_ingestion import FigmaReviewVertexIngestion
        config = _get_config()

        vertex = FigmaReviewVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )

        insights = vertex.list_client_insights(
            client_id=client_id,
            limit=limit,
            insight_type=insight_type
        )

        return {
            "client_id": client_id,
            "total": len(insights),
            "insights": insights
        }

    except Exception as e:
        logger.error(f"Failed to list insights for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check for Figma Email Review pipeline.

    Verifies configuration and service connectivity.
    """
    config = _get_config()

    result = {
        "status": "healthy",
        "figma_configured": bool(config.figma.access_token),
        "gemini_configured": bool(config.vision.api_key),
        "rag_url": config.rag.base_url,
        "gcp_project": config.gcp_project_id,
        "vertex_data_store": config.vertex_data_store_id
    }

    # Check Asana configuration
    result["asana_configured"] = bool(
        config.asana.messaging_stage_gid and
        config.asana.figma_url_gid
    )

    # Determine overall status
    if not result["figma_configured"]:
        result["status"] = "degraded"
        result["warning"] = "FIGMA_ACCESS_TOKEN not configured"
    elif not result["gemini_configured"]:
        result["status"] = "degraded"
        result["warning"] = "GEMINI_API_KEY not configured"

    return result


@router.get("/file/{file_key}/stats")
async def get_file_stats(
    file_key: str,
    client_id: str = Query(..., description="Client identifier")
) -> Dict[str, Any]:
    """
    Get review statistics for a specific Figma file.

    Returns total reviews, average score, and common issues.
    """
    try:
        client_id = require_canonical_client_id(client_id)
        state_manager = _get_state_manager()
        stats = state_manager.get_file_stats(client_id, file_key)

        return stats

    except Exception as e:
        logger.error(f"Failed to get file stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
