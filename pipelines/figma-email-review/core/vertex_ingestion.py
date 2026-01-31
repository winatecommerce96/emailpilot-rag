"""
Vertex AI Insight Ingestion for Figma Email Review Pipeline.

Indexes review insights to Vertex AI for future retrieval,
enabling the system to learn from past reviews.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions
from google.protobuf import struct_pb2

from .best_practices import EmailReviewReport

logger = logging.getLogger(__name__)


class FigmaReviewVertexIngestion:
    """
    Index review insights to Vertex AI for future retrieval.

    Creates documents with category "proofing_insight" that can be
    searched to inform future email reviews and catch recurring issues.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        data_store_id: str
    ):
        """
        Initialize the ingestion service.

        Args:
            project_id: GCP project ID
            location: GCP region (e.g., "us")
            data_store_id: Vertex AI data store ID
        """
        self.project_id = project_id
        self.location = location
        self.data_store_id = data_store_id

        # Initialize client
        self.client_options = ClientOptions(
            api_endpoint=f"{location}-discoveryengine.googleapis.com"
        )
        self.client = discoveryengine.DocumentServiceClient(
            client_options=self.client_options
        )

        # Build parent path
        self.branch_path = self.client.branch_path(
            project=project_id,
            location=location,
            data_store=data_store_id,
            branch="default_branch"
        )

        logger.info(f"FigmaReviewVertexIngestion initialized: {data_store_id}")

    def _generate_doc_id(self, client_id: str, review_id: str) -> str:
        """Generate unique document ID for insight."""
        # Create a short hash to avoid overly long IDs
        hash_input = f"{client_id}_{review_id}"
        hash_suffix = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"insight_{client_id}_{hash_suffix}"

    def _build_searchable_text(self, report: EmailReviewReport) -> str:
        """
        Build a text chunk optimized for semantic search.

        This text will be used by Vertex AI to find relevant insights.
        """
        parts = []

        # Summary
        parts.append(f"Email Review Insight for {report.email_name}.")
        parts.append(f"Client: {report.client_id}.")
        parts.append(f"Overall score: {report.overall_score:.0%}.")

        # Score breakdown
        parts.append(
            f"Scores - Brand: {report.brand_compliance_score:.0%}, "
            f"Accessibility: {report.accessibility_score:.0%}, "
            f"Best Practices: {report.best_practices_score:.0%}, "
            f"Mobile: {report.mobile_score:.0%}."
        )

        # Critical issues
        if report.critical_issues:
            issues_text = "; ".join(report.critical_issues[:5])
            parts.append(f"Critical issues found: {issues_text}.")

        # Warnings
        if report.warnings:
            warnings_text = "; ".join(report.warnings[:3])
            parts.append(f"Warnings: {warnings_text}.")

        # Recommendations
        if report.suggestions:
            suggestions_text = "; ".join(report.suggestions[:3])
            parts.append(f"Recommendations: {suggestions_text}.")

        # Brand voice insights
        if report.brand_voice:
            if report.brand_voice.vocabulary_issues:
                parts.append(
                    f"Brand voice issues: {', '.join(report.brand_voice.vocabulary_issues[:3])}."
                )
            if report.brand_voice.recommendations:
                parts.append(
                    f"Brand recommendations: {', '.join(report.brand_voice.recommendations[:3])}."
                )

        # Layout insights
        if report.layout:
            if not report.layout.has_footer:
                parts.append("Missing footer element.")
            if not report.layout.image_text_ratio_ok:
                parts.append("Image-to-text ratio needs improvement.")

        return " ".join(parts)

    def _determine_insight_type(self, report: EmailReviewReport) -> str:
        """Determine the type of insight based on the report."""
        if report.critical_issues:
            return "recurring_issue"
        elif report.overall_score >= 0.85:
            return "best_practice"
        elif report.brand_voice and not report.brand_voice.is_compliant:
            return "brand_pattern"
        else:
            return "general_insight"

    def _determine_severity(self, report: EmailReviewReport) -> str:
        """Determine severity based on score and issues."""
        if report.overall_score < 0.5 or len(report.critical_issues) > 3:
            return "critical"
        elif report.overall_score < 0.7 or report.critical_issues:
            return "warning"
        else:
            return "suggestion"

    def _get_related_issues(self, report: EmailReviewReport) -> List[str]:
        """Extract categories of issues found."""
        categories = set()

        if report.accessibility_score < 0.7:
            categories.add("accessibility")
        if report.mobile_score < 0.7:
            categories.add("mobile")
        if report.brand_compliance_score < 0.7:
            categories.add("brand_voice")
        if report.cta and report.cta.score < 0.7:
            categories.add("cta")
        if report.layout and report.layout.score < 0.7:
            categories.add("layout")

        return list(categories)

    def create_insight_document(
        self,
        client_id: str,
        report: EmailReviewReport
    ) -> Dict[str, Any]:
        """
        Create and index an insight document.

        Args:
            client_id: Client identifier
            report: Email review report

        Returns:
            Result with success status and document ID
        """
        doc_id = self._generate_doc_id(client_id, report.review_id)
        text_chunk = self._build_searchable_text(report)

        # Build metadata for filtering
        metadata = {
            "client_id": client_id,
            "category": "proofing_insight",
            "source": f"figma:{report.figma_file_key}:{report.figma_frame_id}",
            "insight_type": self._determine_insight_type(report),
            "severity": self._determine_severity(report),
            "overall_score": report.overall_score,
            "review_id": report.review_id,
            "email_name": report.email_name,
            "created_at": datetime.now(timezone.utc).isoformat(),

            # Related issue categories
            "related_issues_str": ", ".join(self._get_related_issues(report)),

            # Scores for filtering
            "brand_score": report.brand_compliance_score,
            "accessibility_score": report.accessibility_score,
            "mobile_score": report.mobile_score,
        }

        # Build document
        document = discoveryengine.Document(
            id=doc_id,
            struct_data=struct_pb2.Struct(
                fields={
                    "text_chunk": struct_pb2.Value(string_value=text_chunk),
                    "title": struct_pb2.Value(string_value=f"Email Review: {report.email_name}"),
                    **{
                        k: struct_pb2.Value(string_value=str(v) if not isinstance(v, (int, float)) else struct_pb2.Value(number_value=v))
                        for k, v in metadata.items()
                    }
                }
            )
        )

        try:
            # Create or update document
            result = self.client.create_document(
                parent=self.branch_path,
                document=document,
                document_id=doc_id
            )

            logger.info(f"Created insight document: {doc_id}")
            return {
                "success": True,
                "document_id": doc_id,
                "insight_type": metadata["insight_type"],
                "severity": metadata["severity"]
            }

        except Exception as e:
            # If document exists, try update
            if "already exists" in str(e).lower():
                try:
                    doc_path = f"{self.branch_path}/documents/{doc_id}"
                    document.name = doc_path
                    result = self.client.update_document(document=document)

                    logger.info(f"Updated insight document: {doc_id}")
                    return {
                        "success": True,
                        "document_id": doc_id,
                        "updated": True
                    }
                except Exception as update_error:
                    logger.error(f"Failed to update insight document: {update_error}")
                    return {"success": False, "error": str(update_error)}

            logger.error(f"Failed to create insight document: {e}")
            return {"success": False, "error": str(e)}

    def list_client_insights(
        self,
        client_id: str,
        limit: int = 50,
        insight_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all insights for a client.

        Args:
            client_id: Client identifier
            limit: Maximum results
            insight_type: Optional filter by type

        Returns:
            List of insight summaries
        """
        # Build filter
        filter_str = f'client_id: ANY("{client_id}") AND category: ANY("proofing_insight")'
        if insight_type:
            filter_str += f' AND insight_type: ANY("{insight_type}")'

        try:
            # Use search to find documents
            from google.cloud import discoveryengine_v1 as discoveryengine

            search_client = discoveryengine.SearchServiceClient(
                client_options=self.client_options
            )

            serving_config = search_client.serving_config_path(
                project=self.project_id,
                location=self.location,
                data_store=self.data_store_id,
                serving_config="default_search"
            )

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query="email review insight",
                page_size=limit,
                filter=filter_str
            )

            response = search_client.search(request)

            insights = []
            for result in response.results:
                data = dict(result.document.struct_data)
                insights.append({
                    "doc_id": result.document.id,
                    "email_name": data.get("email_name", ""),
                    "insight_type": data.get("insight_type", ""),
                    "severity": data.get("severity", ""),
                    "overall_score": data.get("overall_score", 0),
                    "created_at": data.get("created_at", ""),
                    "related_issues": data.get("related_issues_str", "").split(", ")
                })

            return insights

        except Exception as e:
            logger.error(f"Failed to list insights: {e}")
            return []

    def delete_client_insights(self, client_id: str) -> Dict[str, int]:
        """
        Delete all insights for a client.

        Args:
            client_id: Client identifier

        Returns:
            Count of deleted and failed documents
        """
        insights = self.list_client_insights(client_id, limit=500)

        deleted = 0
        failed = 0

        for insight in insights:
            try:
                doc_path = f"{self.branch_path}/documents/{insight['doc_id']}"
                self.client.delete_document(name=doc_path)
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete {insight['doc_id']}: {e}")
                failed += 1

        logger.info(f"Deleted {deleted} insights for client {client_id} ({failed} failed)")
        return {"deleted": deleted, "failed": failed}

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a specific document.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted successfully
        """
        try:
            doc_path = f"{self.branch_path}/documents/{doc_id}"
            self.client.delete_document(name=doc_path)
            logger.info(f"Deleted document: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False
