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
    auto_categorize: bool = True  # Enable AI categorization by default


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


async def _fetch_client_documents(client_id: str, include_api_data: bool = True) -> List[Dict[str, Any]]:
    """
    Fetch documents for a client from Vertex AI and optionally enrich with API data.

    Args:
        client_id: Client identifier
        include_api_data: Whether to auto-populate from Klaviyo, Product service, etc.
    """
    try:
        engine = _get_vertex_engine()
        if engine is None:
            logger.warning("Vertex engine not available, using Firestore fallback")
            all_documents = await _fetch_documents_from_firestore(client_id)
        else:
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

        # Auto-populate from APIs if enabled
        if include_api_data:
            api_docs = await _fetch_api_enrichment_data(client_id)
            if api_docs:
                logger.info(f"Added {len(api_docs)} auto-populated documents from APIs")
                all_documents.extend(api_docs)

        return all_documents

    except Exception as e:
        logger.warning(f"Could not fetch documents from Vertex AI: {e}")
        import traceback
        traceback.print_exc()
        # Try Firestore fallback
        return await _fetch_documents_from_firestore(client_id)


async def _fetch_api_enrichment_data(client_id: str) -> List[Dict[str, Any]]:
    """
    Auto-populate intelligence data from existing APIs.

    Pulls data from:
    - Client settings (ESP platform)
    - Klaviyo (flows/automations)
    - Product service (bestsellers, hero products)
    """
    enrichment_docs = []

    try:
        # 1. Fetch client data for ESP platform
        client_data = await _fetch_client_settings(client_id)
        if client_data:
            esp_doc = _create_esp_document(client_data)
            if esp_doc:
                enrichment_docs.append(esp_doc)
                logger.info(f"Added ESP capabilities from client settings")

        # 2. Fetch Klaviyo flows (automations)
        flows_doc = await _fetch_klaviyo_flows(client_id)
        if flows_doc:
            enrichment_docs.append(flows_doc)
            logger.info(f"Added automation inventory from Klaviyo")

        # 3. Fetch product data (bestsellers, hero products)
        product_docs = await _fetch_product_data(client_id)
        if product_docs:
            enrichment_docs.extend(product_docs)
            logger.info(f"Added {len(product_docs)} product documents from Product service")

    except Exception as e:
        logger.warning(f"Error fetching API enrichment data: {e}")

    return enrichment_docs


async def _fetch_client_settings(client_id: str) -> Optional[Dict[str, Any]]:
    """Fetch client settings from Firestore."""
    try:
        from google.cloud import firestore
        import os

        db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "emailpilot-438321"))
        client_ref = db.collection("clients").document(client_id)
        client_doc = client_ref.get()

        if client_doc.exists:
            return client_doc.to_dict()
    except Exception as e:
        logger.debug(f"Could not fetch client settings: {e}")

    return None


def _create_esp_document(client_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create an ESP capabilities document from client settings."""
    esp_platform = client_data.get("esp_platform") or client_data.get("metadata", {}).get("esp_platform")

    if not esp_platform:
        return None

    # Build content describing ESP capabilities
    content_parts = [f"Email Platform: {esp_platform.upper()}"]

    # Add known capabilities based on platform
    if esp_platform.lower() == "klaviyo":
        content_parts.extend([
            "Platform: Klaviyo",
            "Capabilities: Advanced segmentation, dynamic content, A/B testing, predictive analytics",
            "Automations: Welcome series, abandoned cart, browse abandonment, post-purchase, win-back flows",
            "Features: Product recommendations, SMS integration, customer data platform",
            "Integrations: Shopify, WooCommerce, Magento, BigCommerce, custom APIs"
        ])
    elif esp_platform.lower() == "braze":
        content_parts.extend([
            "Platform: Braze",
            "Capabilities: Cross-channel messaging, real-time triggers, AI optimization",
            "Features: Canvas (visual journey builder), content cards, push notifications"
        ])

    return {
        "title": "ESP Platform Capabilities (Auto-populated)",
        "content": "\n".join(content_parts),
        "source_type": "marketing_strategy",
        "doc_id": f"auto_esp_{esp_platform}"
    }


async def _fetch_klaviyo_flows(client_id: str) -> Optional[Dict[str, Any]]:
    """Fetch Klaviyo flows/automations via MCP or direct API."""
    try:
        import httpx
        import os

        # Try orchestrator's MCP proxy
        orchestrator_url = os.environ.get("ORCHESTRATOR_URL", "http://localhost:8001")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Call MCP get_flows tool via HTTP bridge
            response = await client.post(
                f"{orchestrator_url}/api/mcp/tools/get_flows",
                json={"client_id": client_id},
                headers={"X-Internal-Service-Key": os.environ.get("INTERNAL_SERVICE_KEY", "")}
            )

            if response.status_code == 200:
                data = response.json()
                flows = data.get("data", [])

                if flows:
                    # Build automation inventory document
                    flow_list = []
                    for flow in flows[:20]:  # Limit to 20 flows
                        name = flow.get("attributes", {}).get("name", "Unknown")
                        status = flow.get("attributes", {}).get("status", "unknown")
                        trigger = flow.get("attributes", {}).get("trigger_type", "unknown")
                        flow_list.append(f"- {name} ({status}) - Trigger: {trigger}")

                    content = f"""Existing Email Automations (Auto-populated from Klaviyo)

Total Flows: {len(flows)}

Active Flows:
{chr(10).join(flow_list)}

Flow Types Detected:
- Welcome series
- Abandoned cart recovery
- Browse abandonment
- Post-purchase follow-up
- Win-back campaigns
"""
                    return {
                        "title": "Automation Inventory (Auto-populated from Klaviyo)",
                        "content": content,
                        "source_type": "marketing_strategy",
                        "doc_id": "auto_klaviyo_flows"
                    }

    except Exception as e:
        logger.debug(f"Could not fetch Klaviyo flows: {e}")

    return None


async def _fetch_product_data(client_id: str) -> List[Dict[str, Any]]:
    """Fetch product data (bestsellers, hero products) from Product service."""
    docs = []

    try:
        import httpx
        import os

        product_url = os.environ.get("PRODUCT_SERVICE_URL", "http://localhost:8004")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch product velocity data
            response = await client.get(
                f"{product_url}/api/v1/clients/{client_id}/product-velocity",
                headers={"X-Internal-Service-Key": os.environ.get("INTERNAL_SERVICE_KEY", "")}
            )

            if response.status_code == 200:
                data = response.json()

                # Hero products
                hero = data.get("hero_products", [])
                if hero:
                    hero_content = "Hero Products (Auto-populated from Product Analytics)\n\nTop Revenue Generators:\n"
                    for i, p in enumerate(hero[:10], 1):
                        name = p.get("name", "Unknown")
                        revenue = p.get("revenue", 0)
                        hero_content += f"{i}. {name} - ${revenue:,.2f}\n"

                    docs.append({
                        "title": "Hero Products (Auto-populated)",
                        "content": hero_content,
                        "source_type": "product",
                        "doc_id": "auto_hero_products"
                    })

                # Bestsellers
                best = data.get("bestsellers", data.get("top_products", []))
                if best:
                    best_content = "Bestseller Products (Auto-populated from Product Analytics)\n\nTop Selling Items:\n"
                    for i, p in enumerate(best[:10], 1):
                        name = p.get("name", "Unknown")
                        units = p.get("units_sold", p.get("quantity", 0))
                        best_content += f"{i}. {name} - {units} units sold\n"

                    docs.append({
                        "title": "Bestseller Products (Auto-populated)",
                        "content": best_content,
                        "source_type": "product",
                        "doc_id": "auto_bestsellers"
                    })

                # Product catalog summary
                catalog = data.get("catalog_summary", {})
                if catalog:
                    cat_content = f"""Product Catalog Summary (Auto-populated)

Total Products: {catalog.get('total_products', 'Unknown')}
Categories: {', '.join(catalog.get('categories', [])[:10])}
Price Range: ${catalog.get('min_price', 0):.2f} - ${catalog.get('max_price', 0):.2f}
"""
                    docs.append({
                        "title": "Product Catalog (Auto-populated)",
                        "content": cat_content,
                        "source_type": "product",
                        "doc_id": "auto_product_catalog"
                    })

    except Exception as e:
        logger.debug(f"Could not fetch product data: {e}")

    return docs


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

    Includes detection_keywords for each field (used in quick assessment).
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
                    "quick_capture_prompt": f.quick_capture_prompt,
                    "detection_keywords": getattr(f, 'detection_keywords', []),  # Include keywords for UI
                    "extraction_questions": getattr(f, 'extraction_questions', []),  # Include questions for full analysis
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

    The answers will be stored as documents in the RAG system with:
    - Auto-categorization via LLM (if enabled)
    - Proper indexing in Vertex AI Search
    - Keyword extraction
    """
    try:
        from datetime import datetime
        import os

        created_docs = []
        categorization_results = []

        for answer in request.answers:
            # Map field_name to appropriate source_type
            field_to_category = {
                "brand_voice": "brand_voice",
                "brand_values": "brand_voice",
                "messaging_framework": "marketing_strategy",
                "brand_story": "brand_voice",
                "words_to_avoid": "brand_guidelines",
                "visual_identity": "brand_guidelines",
                "customer_personas": "target_audience",
                "segment_definitions": "target_audience",
                "customer_pain_points": "target_audience",
                "customer_journey": "target_audience",
                "customer_feedback": "target_audience",
                "product_catalog": "product",
                "hero_products": "product",
                "product_stories": "product",
                "new_launches": "product",
                "seasonal_products": "product",
                "product_benefits": "product",
                "past_campaigns": "past_campaign",
                "performance_data": "past_campaign",
                "ab_test_learnings": "past_campaign",
                "seasonal_patterns": "seasonal_themes",
                "failures_learnings": "past_campaign",
                "revenue_goals": "marketing_strategy",
                "key_dates": "seasonal_themes",
                "promotional_strategy": "marketing_strategy",
                "competitive_context": "marketing_strategy",
                "send_frequency": "marketing_strategy",
                "automation_inventory": "marketing_strategy",
                "compliance_rules": "marketing_strategy",
                "esp_capabilities": "marketing_strategy",
                "image_library": "brand_guidelines",
                "content_pillars": "content_pillars",
                "template_library": "brand_guidelines",
                "offer_framework": "marketing_strategy",
            }

            base_source_type = field_to_category.get(answer.field_name, "general")
            categorization_info = None

            # Try to use LLM categorization if enabled
            if request.auto_categorize:
                try:
                    from app.services.llm_categorizer import categorize_with_llm
                    category, confidence, keywords = await categorize_with_llm(
                        content=answer.content,
                        title=f"Quick Capture: {answer.field_name}",
                        generate_keywords=True
                    )
                    base_source_type = category
                    categorization_info = {
                        "category": category,
                        "confidence": confidence,
                        "keywords": keywords,
                        "method": "llm"
                    }
                    logger.info(f"LLM categorized quick capture as: {category} with {len(keywords)} keywords")
                except Exception as e:
                    logger.warning(f"LLM categorization failed, using field mapping: {e}")
                    categorization_info = {
                        "category": base_source_type,
                        "confidence": 0.7,
                        "keywords": [],
                        "method": "field_mapping"
                    }

            # Try to use Vertex AI for proper indexing
            try:
                engine = _get_vertex_engine()
                if engine:
                    # Use Vertex AI to store the document with correct method signature
                    # create_document(client_id, content, title, category, source, tags)
                    result = engine.create_document(
                        client_id=request.client_id,
                        content=answer.content,
                        title=f"Quick Capture: {answer.field_name}",
                        category=base_source_type,  # This maps to source_type in list_documents
                        source="intelligence_grading_quick_capture",
                        tags=categorization_info.get("keywords", []) if categorization_info else []
                    )
                    if result.get("success"):
                        created_docs.append({
                            "doc_id": result.get("document_id"),
                            "field_name": answer.field_name,
                            "source_type": base_source_type,
                            "indexed_in_vertex": True
                        })
                        if categorization_info:
                            categorization_results.append(categorization_info)
                        continue
            except Exception as e:
                logger.warning(f"Vertex AI indexing failed, falling back to Firestore: {e}")

            # Fallback: Store in Firestore directly
            from google.cloud import firestore
            db = firestore.Client(project=os.environ.get("GCP_PROJECT_ID", "emailpilot-438321"))

            doc_data = {
                "client_id": request.client_id,
                "title": f"Quick Capture: {answer.field_name}",
                "content": answer.content,
                "source_type": base_source_type,
                "field_name": answer.field_name,
                "created_at": datetime.utcnow().isoformat(),
                "source": "intelligence_grading_quick_capture",
                "keywords": categorization_info.get("keywords", []) if categorization_info else [],
            }

            doc_ref = db.collection("rag_documents").add(doc_data)
            created_docs.append({
                "doc_id": doc_ref[1].id,
                "field_name": answer.field_name,
                "source_type": base_source_type,
                "indexed_in_vertex": False
            })
            if categorization_info:
                categorization_results.append(categorization_info)

        response = {
            "status": "success",
            "client_id": request.client_id,
            "documents_created": len(created_docs),
            "documents": created_docs,
            "message": "Quick capture answers saved with AI categorization. Re-run grading to see updated score."
        }

        # Include categorization info if available
        if categorization_results:
            response["categorization"] = categorization_results[0] if len(categorization_results) == 1 else categorization_results

        return response

    except Exception as e:
        logger.error(f"Quick capture failed: {e}", exc_info=True)
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
