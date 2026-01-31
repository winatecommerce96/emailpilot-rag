"""
Firestore State Manager for Figma Email Review Pipeline.

Manages review state and history in Firestore:
- Per-file review status
- Individual email review records
- Processing history and insights
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from google.cloud import firestore

logger = logging.getLogger(__name__)


class FigmaReviewStateManager:
    """
    Manages review state in Firestore.

    Collections:
    - {prefix}_state: Per-file review status and history
    - {prefix}_emails: Individual email review records
    """

    def __init__(
        self,
        project_id: str,
        collection_prefix: str = "figma_review"
    ):
        """
        Initialize the state manager.

        Args:
            project_id: GCP project ID
            collection_prefix: Prefix for Firestore collections
        """
        self.db = firestore.Client(project=project_id)
        self.state_collection = f"{collection_prefix}_state"
        self.emails_collection = f"{collection_prefix}_emails"

        logger.info(f"FigmaReviewStateManager initialized (collections: {self.state_collection}, {self.emails_collection})")

    def _get_state_doc_id(self, client_id: str, file_key: str) -> str:
        """Generate document ID for state tracking."""
        return f"{client_id}_{file_key}"

    def get_last_review_time(
        self,
        client_id: str,
        file_key: str
    ) -> Optional[datetime]:
        """
        Get last review timestamp for a Figma file.

        Args:
            client_id: Client identifier
            file_key: Figma file key

        Returns:
            Datetime of last review or None if never reviewed
        """
        doc_id = self._get_state_doc_id(client_id, file_key)
        doc_ref = self.db.collection(self.state_collection).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            timestamp = data.get("last_review_timestamp")
            if timestamp:
                return timestamp
        return None

    def get_last_reviewed_version(
        self,
        client_id: str,
        file_key: str
    ) -> Optional[str]:
        """
        Get the last reviewed Figma version for a file.

        Args:
            client_id: Client identifier
            file_key: Figma file key

        Returns:
            Version ID string or None
        """
        doc_id = self._get_state_doc_id(client_id, file_key)
        doc_ref = self.db.collection(self.state_collection).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict().get("last_reviewed_version")
        return None

    def needs_review(
        self,
        client_id: str,
        file_key: str,
        figma_version: str
    ) -> bool:
        """
        Check if a file version needs review.

        Args:
            client_id: Client identifier
            file_key: Figma file key
            figma_version: Current Figma version ID

        Returns:
            True if review is needed
        """
        last_version = self.get_last_reviewed_version(client_id, file_key)
        if last_version is None:
            return True  # Never reviewed
        return last_version != figma_version

    def update_file_state(
        self,
        client_id: str,
        file_key: str,
        file_name: str,
        version: Optional[str] = None,
        status: str = "reviewed",
        review_count: int = 1,
        average_score: Optional[float] = None,
        common_issues: Optional[List[str]] = None
    ):
        """
        Update the review state for a Figma file.

        Args:
            client_id: Client identifier
            file_key: Figma file key
            file_name: Figma file name
            version: Figma version ID
            status: Review status
            review_count: Number of reviews for this file
            average_score: Average review score
            common_issues: Common issues found
        """
        doc_id = self._get_state_doc_id(client_id, file_key)
        doc_ref = self.db.collection(self.state_collection).document(doc_id)

        # Get existing data for increment
        existing = doc_ref.get()
        existing_data = existing.to_dict() if existing.exists else {}
        total_reviews = existing_data.get("total_reviews", 0) + review_count

        data = {
            "client_id": client_id,
            "file_key": file_key,
            "file_name": file_name,
            "last_review_timestamp": datetime.now(timezone.utc),
            "last_reviewed_version": version,
            "status": status,
            "total_reviews": total_reviews,
            "updated_at": datetime.now(timezone.utc)
        }

        if average_score is not None:
            # Calculate running average
            prev_avg = existing_data.get("average_score", average_score)
            prev_count = existing_data.get("total_reviews", 0)
            if prev_count > 0:
                data["average_score"] = (prev_avg * prev_count + average_score) / total_reviews
            else:
                data["average_score"] = average_score

        if common_issues:
            # Merge with existing issues
            existing_issues = existing_data.get("common_issues", [])
            all_issues = existing_issues + common_issues
            # Keep top 10 most frequent
            from collections import Counter
            issue_counts = Counter(all_issues)
            data["common_issues"] = [issue for issue, _ in issue_counts.most_common(10)]

        doc_ref.set(data, merge=True)
        logger.info(f"Updated file state: {client_id}/{file_key}")

    def save_review_result(
        self,
        client_id: str,
        file_key: str,
        frame_id: str,
        report: Any,  # EmailReviewReport
        indexed_to_vertex: bool = False,
        vertex_doc_id: Optional[str] = None
    ) -> str:
        """
        Save an individual review result to Firestore.

        Args:
            client_id: Client identifier
            file_key: Figma file key
            frame_id: Figma frame ID
            report: EmailReviewReport object
            indexed_to_vertex: Whether indexed to Vertex AI
            vertex_doc_id: Vertex AI document ID

        Returns:
            Review document ID
        """
        # Create document with review_id
        doc_ref = self.db.collection(self.emails_collection).document(report.review_id)

        data = {
            "review_id": report.review_id,
            "client_id": client_id,
            "file_key": file_key,
            "frame_id": frame_id,
            "email_name": report.email_name,
            "reviewed_at": datetime.now(timezone.utc),

            # Scores
            "overall_score": report.overall_score,
            "brand_compliance_score": report.brand_compliance_score,
            "accessibility_score": report.accessibility_score,
            "best_practices_score": report.best_practices_score,
            "mobile_score": report.mobile_score,

            # Issues summary
            "critical_issues": report.critical_issues,
            "warnings": report.warnings,
            "suggestions": report.suggestions,

            # Asana context
            "asana_task_gid": report.asana_task_gid,
            "asana_task_name": report.asana_task_name,

            # Full report (as dict)
            "report": report.model_dump(),

            # Vertex indexing
            "indexed_to_vertex": indexed_to_vertex,
            "vertex_doc_id": vertex_doc_id
        }

        doc_ref.set(data)
        logger.info(f"Saved review result: {report.review_id}")

        # Update file state
        self.update_file_state(
            client_id=client_id,
            file_key=file_key,
            file_name=report.email_name,
            version=report.figma_version,
            average_score=report.overall_score,
            common_issues=report.critical_issues
        )

        return report.review_id

    def get_review(self, review_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific review by ID.

        Args:
            review_id: Review document ID

        Returns:
            Review data or None
        """
        doc_ref = self.db.collection(self.emails_collection).document(review_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()
        return None

    def get_review_history(
        self,
        client_id: str,
        file_key: Optional[str] = None,
        limit: int = 20,
        min_score: Optional[float] = None,
        has_critical_issues: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Get review history for a client or file.

        Args:
            client_id: Client identifier
            file_key: Optional file key to filter by
            limit: Maximum records to return
            min_score: Optional minimum score filter
            has_critical_issues: Optional filter for reviews with critical issues

        Returns:
            List of review records (summary data)
        """
        query = self.db.collection(self.emails_collection).where(
            filter=firestore.FieldFilter("client_id", "==", client_id)
        )

        if file_key:
            query = query.where(
                filter=firestore.FieldFilter("file_key", "==", file_key)
            )

        if min_score is not None:
            query = query.where(
                filter=firestore.FieldFilter("overall_score", ">=", min_score)
            )

        query = query.order_by("reviewed_at", direction=firestore.Query.DESCENDING)
        query = query.limit(limit)

        results = []
        for doc in query.stream():
            data = doc.to_dict()

            # Filter for critical issues if requested
            if has_critical_issues is not None:
                has_issues = len(data.get("critical_issues", [])) > 0
                if has_issues != has_critical_issues:
                    continue

            # Return summary data (not full report)
            results.append({
                "review_id": data.get("review_id"),
                "email_name": data.get("email_name"),
                "overall_score": data.get("overall_score"),
                "reviewed_at": data.get("reviewed_at"),
                "critical_issues_count": len(data.get("critical_issues", [])),
                "warnings_count": len(data.get("warnings", [])),
                "file_key": data.get("file_key"),
                "frame_id": data.get("frame_id"),
                "asana_task_gid": data.get("asana_task_gid")
            })

        return results

    def get_file_stats(self, client_id: str, file_key: str) -> Dict[str, Any]:
        """
        Get statistics for a specific file.

        Args:
            client_id: Client identifier
            file_key: Figma file key

        Returns:
            File statistics
        """
        doc_id = self._get_state_doc_id(client_id, file_key)
        doc_ref = self.db.collection(self.state_collection).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            return doc.to_dict()

        return {
            "client_id": client_id,
            "file_key": file_key,
            "total_reviews": 0,
            "average_score": None,
            "common_issues": [],
            "last_review_timestamp": None
        }

    def clear_client_state(self, client_id: str) -> int:
        """
        Clear all review state for a client.

        Args:
            client_id: Client identifier

        Returns:
            Number of records deleted
        """
        deleted = 0

        # Clear state collection
        state_query = self.db.collection(self.state_collection).where(
            filter=firestore.FieldFilter("client_id", "==", client_id)
        )
        for doc in state_query.stream():
            doc.reference.delete()
            deleted += 1

        # Clear emails collection
        emails_query = self.db.collection(self.emails_collection).where(
            filter=firestore.FieldFilter("client_id", "==", client_id)
        )
        for doc in emails_query.stream():
            doc.reference.delete()
            deleted += 1

        logger.info(f"Cleared {deleted} records for client {client_id}")
        return deleted
