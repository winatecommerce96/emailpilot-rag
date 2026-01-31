"""
FastAPI routes for Intelligence Grading Pipeline.

Provides endpoints for grading client knowledge base completeness.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

# Ensure pipeline root is in sys.path for absolute imports
_pipeline_root = Path(__file__).parent.parent
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence Grading"])


# =============================================================================
# Pydantic Models
# =============================================================================

class QuickCaptureAnswer(BaseModel):
    """Answer to a quick capture question."""
    field_name: str
    content: str


class QuickCaptureRequest(BaseModel):
    """Request to submit quick capture answers."""
    client_id: str
    answers: List[QuickCaptureAnswer]


class GradeResponse(BaseModel):
    """Complete grade response."""
    client_id: str
    overall_grade: str
    overall_score: float
    ready_for_generation: bool
    confidence_level: str
    graded_at: str
    documents_analyzed: int
    total_fields: int
    fields_found: int
    dimension_scores: Dict[str, Any]
    critical_gaps: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    generation_warnings: List[str]


class QuickAssessmentResponse(BaseModel):
    """Quick assessment response."""
    client_id: str
    estimated_grade: str
    estimated_score: float
    documents_analyzed: int
    fields_found: int
    total_fields: int
    dimension_summaries: Dict[str, Any]
    is_estimate: bool
    note: str


class RequirementsResponse(BaseModel):
    """Intelligence requirements configuration."""
    version: str
    dimensions: Dict[str, Any]
    grading_thresholds: Dict[str, int]
    minimum_for_generation: str


# =============================================================================
# Lazy Initialization
# =============================================================================

_grading_service = None
_requirements = None
_modules_loaded = False


def _ensure_modules_loaded():
    """Ensure all required modules are loaded via importlib."""
    global _modules_loaded
    if _modules_loaded:
        return

    import importlib.util

    # Load config.settings
    settings_path = _pipeline_root / "config" / "settings.py"
    if settings_path.exists():
        spec = importlib.util.spec_from_file_location("config.settings", settings_path)
        settings_module = importlib.util.module_from_spec(spec)
        sys.modules["config.settings"] = settings_module
        spec.loader.exec_module(settings_module)

    # Load core.field_extractor
    extractor_path = _pipeline_root / "core" / "field_extractor.py"
    if extractor_path.exists():
        spec = importlib.util.spec_from_file_location("core.field_extractor", extractor_path)
        extractor_module = importlib.util.module_from_spec(spec)
        sys.modules["core.field_extractor"] = extractor_module
        spec.loader.exec_module(extractor_module)

    # Load core.grading_service
    grading_path = _pipeline_root / "core" / "grading_service.py"
    if grading_path.exists():
        spec = importlib.util.spec_from_file_location("core.grading_service", grading_path)
        grading_module = importlib.util.module_from_spec(spec)
        sys.modules["core.grading_service"] = grading_module
        spec.loader.exec_module(grading_module)

    _modules_loaded = True
    logger.info("Intelligence Grading modules loaded")


def _get_grading_service():
    """Lazy initialization of grading service."""
    global _grading_service
    if _grading_service is None:
        _ensure_modules_loaded()
        from core.grading_service import IntelligenceGradingService
        _grading_service = IntelligenceGradingService()
        logger.info("Initialized Intelligence Grading Service")
    return _grading_service


def _get_requirements():
    """Lazy initialization of requirements config."""
    global _requirements
    if _requirements is None:
        _ensure_modules_loaded()
        from config.settings import get_requirements_config
        _requirements = get_requirements_config()
    return _requirements


def _get_vertex_engine():
    """Get the Vertex engine from the main app."""
    try:
        # Import from the main app's services
        import sys
        # Add the app directory to path if needed
        app_path = _pipeline_root.parent.parent / "app"
        if str(app_path.parent) not in sys.path:
            sys.path.insert(0, str(app_path.parent))

        from app.services.vertex_search import get_vertex_engine
        return get_vertex_engine()
    except Exception as e:
        logger.error(f"Failed to get Vertex engine: {e}")
        return None


async def _fetch_client_documents(client_id: str) -> List[Dict[str, Any]]:
    """Fetch documents for a client from Vertex AI."""
    try:
        engine = _get_vertex_engine()
        if engine is None:
            logger.warning("Vertex engine not available, using Firestore fallback")
            return await _fetch_documents_from_firestore(client_id)

        # List all documents for this client
        page = 1
        all_documents = []

        while True:
            result = engine.list_documents(client_id, page=page, limit=100)
            docs = result.get("documents", [])

            if not docs:
                break

            for doc in docs:
                doc_id = doc.get("id", "")
                doc_content = doc.get("content", "")

                # list_documents only returns first 500 chars, fetch full content
                if doc_id:
                    try:
                        full_doc_result = engine.get_document(doc_id)
                        if full_doc_result.get("success"):
                            full_doc = full_doc_result.get("document", {})
                            doc_content = full_doc.get("content", doc_content)
                    except Exception as e:
                        logger.debug(f"Could not fetch full content for {doc_id}: {e}")

                all_documents.append({
                    "title": doc.get("title", "Untitled"),
                    "content": doc_content,
                    "source_type": doc.get("source_type", "general"),
                    "doc_id": doc_id
                })

            # Check pagination
            total = result.get("total", 0)
            limit = result.get("limit", 100)
            if page * limit >= total:
                break
            page += 1

        logger.info(f"Fetched {len(all_documents)} documents for client {client_id}")
        return all_documents

    except Exception as e:
        logger.warning(f"Could not fetch documents from Vertex AI: {e}")
        import traceback
        traceback.print_exc()
        # Try Firestore fallback
        return await _fetch_documents_from_firestore(client_id)


async def _fetch_documents_from_firestore(client_id: str) -> List[Dict[str, Any]]:
    """Fallback: fetch documents from Firestore."""
    try:
        from google.cloud import firestore
        import os

        db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "emailpilot-438321"))

        # Query RAG documents collection
        docs_ref = db.collection("rag_documents").where("client_id", "==", client_id)
        docs = docs_ref.stream()

        documents = []
        for doc in docs:
            data = doc.to_dict()
            documents.append({
                "title": data.get("title", "Untitled"),
                "content": data.get("content", ""),
                "source_type": data.get("source_type", "general"),
                "doc_id": doc.id
            })

        return documents

    except Exception as e:
        logger.error(f"Failed to fetch documents from Firestore: {e}")
        return []


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/grade/{client_id}", response_model=GradeResponse)
async def grade_client(client_id: str):
    """
    Get full intelligence grade for a client.

    Analyzes all documents in the client's knowledge base and returns
    a comprehensive grade with dimension scores, gaps, and recommendations.

    - **client_id**: Client identifier (kebab-case)

    Returns overall grade (A-F), dimension scores, critical gaps,
    and actionable recommendations to improve the grade.
    """
    try:
        service = _get_grading_service()

        # Fetch client documents
        documents = await _fetch_client_documents(client_id)

        if not documents:
            logger.warning(f"No documents found for client {client_id}")

        # Grade the client
        grade = await service.grade_client(client_id, documents)

        # Convert to response format
        return GradeResponse(
            client_id=grade.client_id,
            overall_grade=grade.overall_grade,
            overall_score=grade.overall_score,
            ready_for_generation=grade.ready_for_generation,
            confidence_level=grade.confidence_level,
            graded_at=grade.graded_at,
            documents_analyzed=grade.documents_analyzed,
            total_fields=grade.total_fields,
            fields_found=grade.fields_found,
            dimension_scores={
                name: {
                    "score": ds.score,
                    "grade": ds.grade,
                    "weight": ds.weight,
                    "weighted_contribution": ds.weighted_contribution,
                    "display_name": ds.display_name,
                    "max_points": ds.max_points,
                    "earned_points": ds.earned_points,
                    "fields": [
                        {
                            "field_name": f.field_name,
                            "display_name": f.display_name,
                            "importance": f.importance,
                            "found": f.found,
                            "coverage": f.coverage,
                            "max_points": f.max_points,
                            "earned_points": f.earned_points,
                            "content_summary": f.content_summary,
                            "source_documents": f.source_documents
                        }
                        for f in ds.fields
                    ],
                    "gaps": [
                        {
                            "field_name": g.field_name,
                            "display_name": g.display_name,
                            "importance": g.importance,
                            "impact": g.impact,
                            "suggestion": g.suggestion,
                            "quick_capture_prompt": g.quick_capture_prompt,
                            "expected_improvement": g.expected_improvement
                        }
                        for g in ds.gaps
                    ]
                }
                for name, ds in grade.dimension_scores.items()
            },
            critical_gaps=[
                {
                    "field_name": g.field_name,
                    "display_name": g.display_name,
                    "dimension": g.dimension,
                    "importance": g.importance,
                    "impact": g.impact,
                    "suggestion": g.suggestion,
                    "quick_capture_prompt": g.quick_capture_prompt,
                    "expected_improvement": g.expected_improvement
                }
                for g in grade.critical_gaps
            ],
            recommendations=[
                {
                    "priority": r.priority,
                    "action": r.action,
                    "dimension": r.dimension,
                    "field_name": r.field_name,
                    "expected_improvement": r.expected_improvement,
                    "quick_capture_prompt": r.quick_capture_prompt,
                    "template_available": r.template_available
                }
                for r in grade.recommendations
            ],
            generation_warnings=grade.generation_warnings
        )

    except Exception as e:
        logger.error(f"Failed to grade client {client_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quick-assessment/{client_id}", response_model=QuickAssessmentResponse)
async def quick_assessment(client_id: str):
    """
    Get a quick assessment without full AI analysis.

    Uses keyword matching for faster results. Good for initial checks
    or when you need a quick overview before running full analysis.

    - **client_id**: Client identifier (kebab-case)
    """
    try:
        service = _get_grading_service()

        # Fetch client documents
        documents = await _fetch_client_documents(client_id)

        # Get quick assessment
        result = await service.get_quick_assessment(client_id, documents)

        return QuickAssessmentResponse(**result)

    except Exception as e:
        logger.error(f"Quick assessment failed for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/requirements")
async def get_requirements() -> RequirementsResponse:
    """
    Get the intelligence requirements configuration.

    Returns the complete list of dimensions, fields, and weights
    used for grading. Useful for building UIs or understanding
    what information is needed.
    """
    requirements = _get_requirements()

    dimensions = {}
    for dim_name, dim in requirements.dimensions.items():
        dimensions[dim_name] = {
            "display_name": dim.display_name,
            "description": dim.description,
            "weight": dim.weight,
            "minimum_score": dim.minimum_score,
            "fields": [
                {
                    "name": f.name,
                    "display_name": f.display_name,
                    "importance": f.importance,
                    "points": f.points,
                    "description": f.description,
                    "quick_capture_prompt": f.quick_capture_prompt
                }
                for f in dim.fields
            ]
        }

    return RequirementsResponse(
        version=requirements.version,
        dimensions=dimensions,
        grading_thresholds={
            "A": requirements.grading.A,
            "B": requirements.grading.B,
            "C": requirements.grading.C,
            "D": requirements.grading.D,
            "F": requirements.grading.F
        },
        minimum_for_generation=requirements.grading.minimum_for_generation
    )


@router.get("/gaps/{client_id}")
async def get_gaps(
    client_id: str,
    importance: Optional[str] = Query(None, description="Filter by importance: critical, high, medium, low")
) -> Dict[str, Any]:
    """
    Get only the gaps for a client (missing information).

    Lighter-weight endpoint when you just need to know what's missing,
    without the full grading analysis.

    - **client_id**: Client identifier
    - **importance**: Optional filter for gap importance level
    """
    try:
        service = _get_grading_service()
        documents = await _fetch_client_documents(client_id)

        grade = await service.grade_client(client_id, documents)

        # Collect all gaps
        all_gaps = []
        for dim_score in grade.dimension_scores.values():
            for gap in dim_score.gaps:
                if importance is None or gap.importance == importance:
                    all_gaps.append({
                        "field_name": gap.field_name,
                        "display_name": gap.display_name,
                        "dimension": gap.dimension,
                        "importance": gap.importance,
                        "impact": gap.impact,
                        "suggestion": gap.suggestion,
                        "quick_capture_prompt": gap.quick_capture_prompt,
                        "expected_improvement": gap.expected_improvement
                    })

        # Sort by importance
        importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_gaps.sort(key=lambda g: importance_order.get(g["importance"], 99))

        return {
            "client_id": client_id,
            "overall_grade": grade.overall_grade,
            "total_gaps": len(all_gaps),
            "gaps": all_gaps
        }

    except Exception as e:
        logger.error(f"Failed to get gaps for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ready/{client_id}")
async def check_ready(client_id: str) -> Dict[str, Any]:
    """
    Quick check if client is ready for calendar generation.

    Returns a simple boolean with the current grade.
    Use this endpoint in the calendar generation flow to gate access.

    - **client_id**: Client identifier
    """
    try:
        service = _get_grading_service()
        documents = await _fetch_client_documents(client_id)

        # Use quick assessment for speed
        result = await service.get_quick_assessment(client_id, documents)

        requirements = _get_requirements()
        is_ready = requirements.grading.is_generation_ready(result["estimated_grade"])

        return {
            "client_id": client_id,
            "ready_for_generation": is_ready,
            "current_grade": result["estimated_grade"],
            "current_score": result["estimated_score"],
            "minimum_grade_required": requirements.grading.minimum_for_generation,
            "fields_found": result["fields_found"],
            "total_fields": result["total_fields"]
        }

    except Exception as e:
        logger.error(f"Ready check failed for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quick-capture")
async def submit_quick_capture(request: QuickCaptureRequest) -> Dict[str, Any]:
    """
    Submit quick capture answers to fill gaps.

    Allows users to quickly provide information for missing fields
    without uploading full documents.

    The answers will be stored as documents in the RAG system.
    """
    try:
        from google.cloud import firestore
        from datetime import datetime
        import os

        db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "emailpilot-438321"))

        created_docs = []
        for answer in request.answers:
            # Create a document for each answer
            doc_data = {
                "client_id": request.client_id,
                "title": f"Quick Capture: {answer.field_name}",
                "content": answer.content,
                "source_type": "quick_capture",
                "field_name": answer.field_name,
                "created_at": datetime.utcnow().isoformat(),
                "source": "intelligence_grading_quick_capture"
            }

            doc_ref = db.collection("rag_documents").add(doc_data)
            created_docs.append({
                "doc_id": doc_ref[1].id,
                "field_name": answer.field_name
            })

        return {
            "status": "success",
            "client_id": request.client_id,
            "documents_created": len(created_docs),
            "documents": created_docs,
            "message": "Quick capture answers saved. Re-run grading to see updated score."
        }

    except Exception as e:
        logger.error(f"Quick capture failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check for Intelligence Grading Pipeline."""
    try:
        requirements = _get_requirements()
        return {
            "status": "healthy",
            "version": requirements.version,
            "dimensions_configured": len(requirements.dimensions),
            "total_fields": len(requirements.get_all_fields()),
            "minimum_grade": requirements.grading.minimum_for_generation
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
