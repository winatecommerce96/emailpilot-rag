"""
Review Orchestrator for Figma Email Review Pipeline.

Coordinates all pipeline components to fetch, analyze, and review email designs.
"""

import logging
import asyncio
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from .figma_client import FigmaClient, EmailDesign, FigmaFrame
from .vision_analyzer import EmailVisionAnalyzer, EmailVisionAnalysis
from .rag_integration import RAGBrandVoiceChecker, BrandVoiceComplianceResult
from .best_practices import EmailBestPracticesEvaluator, EmailReviewReport
from .state_manager import FigmaReviewStateManager
from .vertex_ingestion import FigmaReviewVertexIngestion
from .asana_poster import AsanaResultPoster

# Load config.settings from this pipeline's directory (avoids sys.path collision)
_PIPELINE_ROOT = Path(__file__).parent.parent
_config_settings_path = _PIPELINE_ROOT / "config" / "settings.py"
_spec = importlib.util.spec_from_file_location("figma_review_config_settings", _config_settings_path)
_config_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_config_module)
PipelineConfig = _config_module.PipelineConfig
parse_figma_url = _config_module.parse_figma_url

logger = logging.getLogger(__name__)


class FigmaEmailReviewOrchestrator:
    """
    Main orchestration logic for email review pipeline.

    Workflow:
    1. Parse Figma URL to extract file_key and node_id
    2. Check if review is needed (version comparison)
    3. Identify email frames in Figma file
    4. Export frames as images
    5. Analyze with Gemini Vision
    6. Query RAG for brand voice
    7. Evaluate best practices
    8. Generate review report
    9. Store in Firestore
    10. Index insights to Vertex AI
    11. Post results to Asana
    """

    def __init__(
        self,
        figma_client: FigmaClient,
        vision_analyzer: EmailVisionAnalyzer,
        rag_checker: RAGBrandVoiceChecker,
        best_practices: EmailBestPracticesEvaluator,
        state_manager: FigmaReviewStateManager,
        vertex_ingestion: FigmaReviewVertexIngestion,
        asana_poster: AsanaResultPoster,
        config: Optional[PipelineConfig] = None
    ):
        """
        Initialize the orchestrator.

        Args:
            figma_client: Figma API client
            vision_analyzer: Gemini Vision analyzer
            rag_checker: RAG brand voice checker
            best_practices: Best practices evaluator
            state_manager: Firestore state manager
            vertex_ingestion: Vertex AI ingestion
            asana_poster: Asana result poster
            config: Pipeline configuration
        """
        self.figma = figma_client
        self.vision = vision_analyzer
        self.rag = rag_checker
        self.evaluator = best_practices
        self.state = state_manager
        self.vertex = vertex_ingestion
        self.asana = asana_poster
        self.config = config

        logger.info("FigmaEmailReviewOrchestrator initialized")

    async def review_from_url(
        self,
        client_id: str,
        figma_url: str,
        force_review: bool = False,
        include_brand_voice: bool = True,
        asana_task_gid: Optional[str] = None,
        asana_task_name: Optional[str] = None,
        post_results_to_asana: bool = True
    ) -> Dict[str, Any]:
        """
        Review an email design from a Figma URL.

        This is the main entry point called by the API/Asana trigger.

        Args:
            client_id: Client identifier
            figma_url: Figma URL (with optional node-id)
            force_review: Force review even if recently done
            include_brand_voice: Include RAG brand voice check
            asana_task_gid: Asana task GID for posting results
            asana_task_name: Asana task name
            post_results_to_asana: Whether to post results to Asana

        Returns:
            Review result with status and report
        """
        logger.info(f"Starting review from URL for client {client_id}: {figma_url}")

        # Parse URL
        url_parts = parse_figma_url(figma_url)
        file_key = url_parts.get("file_key")
        node_id = url_parts.get("node_id")

        if not file_key:
            return {
                "status": "error",
                "error": f"Could not parse Figma file key from URL: {figma_url}"
            }

        # If specific node_id provided, review just that frame
        if node_id:
            return await self.review_single_frame(
                client_id=client_id,
                file_key=file_key,
                frame_id=node_id,
                force_review=force_review,
                include_brand_voice=include_brand_voice,
                asana_task_gid=asana_task_gid,
                asana_task_name=asana_task_name,
                post_results_to_asana=post_results_to_asana
            )
        else:
            # Review all email frames in the file
            return await self.review_file(
                client_id=client_id,
                file_key=file_key,
                force_review=force_review,
                include_brand_voice=include_brand_voice,
                asana_task_gid=asana_task_gid,
                asana_task_name=asana_task_name,
                post_results_to_asana=post_results_to_asana
            )

    async def review_file(
        self,
        client_id: str,
        file_key: str,
        page_ids: Optional[List[str]] = None,
        force_review: bool = False,
        include_brand_voice: bool = True,
        asana_task_gid: Optional[str] = None,
        asana_task_name: Optional[str] = None,
        post_results_to_asana: bool = True
    ) -> Dict[str, Any]:
        """
        Review all email frames in a Figma file.

        Args:
            client_id: Client identifier
            file_key: Figma file key
            page_ids: Optional list of page IDs to search
            force_review: Force review even if recently done
            include_brand_voice: Include RAG brand voice check
            asana_task_gid: Asana task GID
            asana_task_name: Asana task name
            post_results_to_asana: Post results to Asana

        Returns:
            Review results for all frames
        """
        logger.info(f"Reviewing file {file_key} for client {client_id}")

        result = {
            "status": "in_progress",
            "client_id": client_id,
            "file_key": file_key,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "frames_found": 0,
            "frames_reviewed": 0,
            "reviews": []
        }

        try:
            # Fetch file structure
            file_data = await self.figma.get_file(file_key)
            file_name = file_data.get("name", "Unknown")

            # Check version for incremental sync
            file_version = file_data.get("version")
            if not force_review and not self.state.needs_review(client_id, file_key, file_version):
                logger.info(f"File {file_key} already reviewed at version {file_version}")
                return {
                    "status": "skipped",
                    "reason": "Already reviewed at current version",
                    "file_key": file_key,
                    "version": file_version
                }

            # Find email frames
            email_frames = self.figma.find_email_frames(file_data, page_ids)
            result["frames_found"] = len(email_frames)

            if not email_frames:
                logger.info(f"No email frames found in file {file_key}")
                return {
                    "status": "completed",
                    "frames_found": 0,
                    "message": "No email frames found in file"
                }

            # Review each frame
            for frame in email_frames:
                try:
                    review = await self._review_frame(
                        client_id=client_id,
                        file_key=file_key,
                        file_name=file_name,
                        frame=frame,
                        include_brand_voice=include_brand_voice,
                        asana_task_gid=asana_task_gid,
                        asana_task_name=asana_task_name
                    )

                    result["reviews"].append({
                        "frame_id": frame.id,
                        "frame_name": frame.name,
                        "review_id": review.review_id,
                        "overall_score": review.overall_score,
                        "critical_issues": len(review.critical_issues)
                    })
                    result["frames_reviewed"] += 1

                    # Post to Asana (only for first/primary email)
                    if post_results_to_asana and result["frames_reviewed"] == 1:
                        await self.asana.post_review_result(
                            asana_task_gid=asana_task_gid,
                            report=review
                        )

                except Exception as e:
                    logger.error(f"Error reviewing frame {frame.id}: {e}")
                    result["reviews"].append({
                        "frame_id": frame.id,
                        "frame_name": frame.name,
                        "error": str(e)
                    })

            result["status"] = "completed"
            result["completed_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            logger.error(f"Error reviewing file {file_key}: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        return result

    async def review_single_frame(
        self,
        client_id: str,
        file_key: str,
        frame_id: str,
        force_review: bool = False,
        include_brand_voice: bool = True,
        asana_task_gid: Optional[str] = None,
        asana_task_name: Optional[str] = None,
        post_results_to_asana: bool = True
    ) -> Dict[str, Any]:
        """
        Review a single email frame.

        Args:
            client_id: Client identifier
            file_key: Figma file key
            frame_id: Figma frame ID
            force_review: Force review
            include_brand_voice: Include RAG check
            asana_task_gid: Asana task GID
            asana_task_name: Asana task name
            post_results_to_asana: Post to Asana

        Returns:
            Review result
        """
        logger.info(f"Reviewing single frame {frame_id} in file {file_key}")

        try:
            # Get file metadata
            file_metadata = await self.figma.get_file_metadata(file_key)
            file_name = file_metadata.get("name", "Unknown")

            # Create a FigmaFrame object
            nodes_data = await self.figma.get_nodes(file_key, [frame_id])
            node_data = nodes_data.get("nodes", {}).get(frame_id, {}).get("document", {})

            if not node_data:
                return {
                    "status": "error",
                    "error": f"Frame {frame_id} not found in file"
                }

            bounds = node_data.get("absoluteBoundingBox", {})
            frame = FigmaFrame(
                id=frame_id,
                name=node_data.get("name", "Unknown"),
                width=bounds.get("width", 0),
                height=bounds.get("height", 0)
            )

            # Run the review
            report = await self._review_frame(
                client_id=client_id,
                file_key=file_key,
                file_name=file_name,
                frame=frame,
                include_brand_voice=include_brand_voice,
                asana_task_gid=asana_task_gid,
                asana_task_name=asana_task_name
            )

            # Post to Asana
            if post_results_to_asana and asana_task_gid:
                await self.asana.post_review_result(
                    asana_task_gid=asana_task_gid,
                    report=report
                )

            return {
                "status": "completed",
                "review_id": report.review_id,
                "email_name": report.email_name,
                "overall_score": report.overall_score,
                "critical_issues_count": len(report.critical_issues),
                "warnings_count": len(report.warnings),
                "suggestions_count": len(report.suggestions),
                "report": report.model_dump()
            }

        except Exception as e:
            logger.error(f"Error reviewing frame {frame_id}: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def _review_frame(
        self,
        client_id: str,
        file_key: str,
        file_name: str,
        frame: FigmaFrame,
        include_brand_voice: bool = True,
        asana_task_gid: Optional[str] = None,
        asana_task_name: Optional[str] = None
    ) -> EmailReviewReport:
        """
        Internal method to review a single frame.

        This is the core review logic:
        1. Export frame as image
        2. Analyze with Gemini Vision
        3. Extract text content
        4. Query RAG for brand voice
        5. Evaluate against best practices
        6. Generate comprehensive report
        7. Save to Firestore
        8. Index to Vertex AI
        """
        logger.info(f"Reviewing frame: {frame.name} ({frame.id})")

        # Step 1: Export frame as image
        image_bytes = await self.figma.export_frame_as_image(file_key, frame.id)
        if not image_bytes:
            raise ValueError(f"Failed to export frame {frame.id} as image")

        # Step 2: Analyze with Gemini Vision
        vision_analysis = await self.vision.analyze_email_design(
            image_bytes=image_bytes,
            email_name=frame.name
        )

        # Step 3: Get brand voice compliance
        brand_compliance = BrandVoiceComplianceResult()
        if include_brand_voice:
            # Extract copy from vision analysis
            email_copy = {
                "headline": vision_analysis.copy.headline,
                "subheadline": vision_analysis.copy.subheadline,
                "body_preview": vision_analysis.copy.body_preview,
                "cta_text": vision_analysis.copy.cta_text
            }

            brand_compliance = await self.rag.check_copy_compliance(
                client_id=client_id,
                email_copy=email_copy
            )

        # Step 4: Generate full report
        report = self.evaluator.generate_full_report(
            vision_analysis=vision_analysis,
            brand_compliance=brand_compliance,
            email_name=frame.name,
            client_id=client_id,
            figma_file_key=file_key,
            figma_frame_id=frame.id,
            asana_task_gid=asana_task_gid,
            asana_task_name=asana_task_name
        )

        # Step 5: Save to Firestore
        self.state.save_review_result(
            client_id=client_id,
            file_key=file_key,
            frame_id=frame.id,
            report=report
        )

        # Step 6: Index to Vertex AI
        vertex_result = self.vertex.create_insight_document(
            client_id=client_id,
            report=report
        )

        if vertex_result.get("success"):
            logger.info(f"Indexed review to Vertex AI: {vertex_result.get('document_id')}")

        logger.info(
            f"Review complete for {frame.name}: "
            f"score={report.overall_score:.0%}, "
            f"issues={len(report.critical_issues)}"
        )

        return report


async def create_orchestrator_from_config(
    config: PipelineConfig
) -> FigmaEmailReviewOrchestrator:
    """
    Create an orchestrator instance from configuration.

    Args:
        config: Pipeline configuration

    Returns:
        Configured FigmaEmailReviewOrchestrator
    """
    # Initialize components
    figma_client = FigmaClient(
        access_token=config.figma.access_token,
        timeout=config.figma.timeout_seconds,
        image_scale=config.figma.image_scale,
        image_format=config.figma.image_format
    )

    vision_analyzer = EmailVisionAnalyzer(
        api_key=config.vision.api_key,
        model_name=config.vision.model_name,
        temperature=config.vision.temperature,
        max_output_tokens=config.vision.max_output_tokens
    )

    rag_checker = RAGBrandVoiceChecker(
        rag_base_url=config.rag.base_url,
        timeout_seconds=config.rag.timeout_seconds,
        default_k=config.rag.default_k,
        gemini_api_key=config.vision.api_key,  # Reuse Gemini key
        gemini_model=config.vision.model_name
    )

    evaluator = EmailBestPracticesEvaluator(
        subject_min_length=config.best_practices.subject_line_min_length,
        subject_max_length=config.best_practices.subject_line_max_length,
        min_cta_visibility=config.best_practices.min_cta_visibility_score,
        max_image_ratio=config.best_practices.max_image_ratio,
        min_contrast=config.best_practices.min_contrast_score
    )

    state_manager = FigmaReviewStateManager(
        project_id=config.gcp_project_id,
        collection_prefix=config.firestore_collection
    )

    vertex_ingestion = FigmaReviewVertexIngestion(
        project_id=config.gcp_project_id,
        location=config.gcp_location,
        data_store_id=config.vertex_data_store_id
    )

    asana_poster = AsanaResultPoster(
        orchestrator_url=config.asana.orchestrator_url,
        timeout_seconds=30
    )

    return FigmaEmailReviewOrchestrator(
        figma_client=figma_client,
        vision_analyzer=vision_analyzer,
        rag_checker=rag_checker,
        best_practices=evaluator,
        state_manager=state_manager,
        vertex_ingestion=vertex_ingestion,
        asana_poster=asana_poster,
        config=config
    )
