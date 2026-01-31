"""
Asana Result Poster.

Posts review results back to Asana task as a formatted comment.
"""

import logging
from typing import Dict, Any, Optional
import httpx

from .best_practices import EmailReviewReport

logger = logging.getLogger(__name__)


class AsanaResultPoster:
    """
    Posts review results back to Asana task as a comment.

    Creates a rich-text comment with:
    - Overall score (with emoji indicator)
    - Critical issues list
    - Warnings and suggestions
    - Link to full report in RAG UI
    """

    def __init__(
        self,
        orchestrator_url: str = "https://app.emailpilot.ai",
        timeout_seconds: int = 30
    ):
        """
        Initialize the Asana poster.

        Args:
            orchestrator_url: URL of the orchestrator service (which has Asana API access)
            timeout_seconds: Request timeout
        """
        self.orchestrator_url = orchestrator_url.rstrip("/")
        self.timeout = timeout_seconds

    def _score_to_emoji(self, score: float) -> str:
        """Convert score to emoji indicator."""
        if score >= 0.85:
            return "✅"  # Excellent
        elif score >= 0.70:
            return "🟡"  # Good, minor issues
        elif score >= 0.50:
            return "🟠"  # Needs attention
        else:
            return "🔴"  # Critical issues

    def _format_score_bar(self, score: float, label: str) -> str:
        """Format a score as a visual bar."""
        filled = int(score * 10)
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        return f"{label}: {bar} {score:.0%}"

    def _format_report_as_comment(
        self,
        report: EmailReviewReport,
        rag_ui_url: Optional[str] = None
    ) -> str:
        """
        Format the review report as an Asana comment.

        Uses plain text with some formatting since Asana
        has limited rich text support in API comments.
        """
        lines = []

        # Header
        emoji = self._score_to_emoji(report.overall_score)
        lines.append(f"{emoji} AI Email Review Complete")
        lines.append(f"Email: {report.email_name}")
        lines.append("")

        # Overall score
        lines.append(f"Overall Score: {report.overall_score:.0%}")
        lines.append("")

        # Score breakdown
        lines.append("Score Breakdown:")
        lines.append(self._format_score_bar(report.brand_compliance_score, "Brand Voice"))
        lines.append(self._format_score_bar(report.accessibility_score, "Accessibility"))
        lines.append(self._format_score_bar(report.best_practices_score, "Best Practices"))
        lines.append(self._format_score_bar(report.mobile_score, "Mobile Ready"))
        lines.append("")

        # Critical issues
        if report.critical_issues:
            lines.append("🔴 Critical Issues:")
            for issue in report.critical_issues[:5]:
                lines.append(f"  • {issue}")
            if len(report.critical_issues) > 5:
                lines.append(f"  ... and {len(report.critical_issues) - 5} more")
            lines.append("")

        # Warnings
        if report.warnings:
            lines.append("🟡 Warnings:")
            for warning in report.warnings[:3]:
                lines.append(f"  • {warning}")
            if len(report.warnings) > 3:
                lines.append(f"  ... and {len(report.warnings) - 3} more")
            lines.append("")

        # Suggestions
        if report.suggestions:
            lines.append("💡 Suggestions:")
            for suggestion in report.suggestions[:3]:
                lines.append(f"  • {suggestion}")
            lines.append("")

        # Link to full report
        if rag_ui_url:
            lines.append(f"View full report: {rag_ui_url}/reports/{report.client_id}/{report.review_id}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("Powered by EmailPilot AI Proofing")

        return "\n".join(lines)

    async def post_review_result(
        self,
        asana_task_gid: str,
        report: EmailReviewReport,
        rag_ui_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Post formatted review results to Asana task.

        Uses the orchestrator's Asana API to add a comment.

        Args:
            asana_task_gid: Asana task GID
            report: EmailReviewReport to post
            rag_ui_url: Optional URL to RAG UI for full report link

        Returns:
            Result with success status
        """
        if not asana_task_gid:
            logger.warning("No Asana task GID provided, skipping post")
            return {"success": False, "error": "No Asana task GID"}

        comment_text = self._format_report_as_comment(report, rag_ui_url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Post comment via orchestrator's Asana endpoint
                response = await client.post(
                    f"{self.orchestrator_url}/api/asana/tasks/{asana_task_gid}/comment",
                    json={
                        "text": comment_text,
                        "is_pinned": report.overall_score < 0.7  # Pin if score is low
                    }
                )

                if response.status_code == 200:
                    logger.info(f"Posted review to Asana task {asana_task_gid}")
                    return {
                        "success": True,
                        "task_gid": asana_task_gid,
                        "comment_posted": True
                    }
                else:
                    logger.error(f"Failed to post to Asana: {response.status_code} - {response.text}")
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }

        except httpx.HTTPError as e:
            logger.error(f"HTTP error posting to Asana: {e}")
            return {"success": False, "error": str(e)}

        except Exception as e:
            logger.error(f"Error posting to Asana: {e}")
            return {"success": False, "error": str(e)}

    async def update_task_custom_field(
        self,
        asana_task_gid: str,
        field_gid: str,
        value: str
    ) -> Dict[str, Any]:
        """
        Update a custom field on the Asana task.

        Can be used to update the Messaging Stage after review.

        Args:
            asana_task_gid: Asana task GID
            field_gid: Custom field GID
            value: New value for the field

        Returns:
            Result with success status
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.put(
                    f"{self.orchestrator_url}/api/asana/tasks/{asana_task_gid}",
                    json={
                        "custom_fields": {
                            field_gid: value
                        }
                    }
                )

                if response.status_code == 200:
                    logger.info(f"Updated custom field on task {asana_task_gid}")
                    return {"success": True, "updated": True}
                else:
                    logger.error(f"Failed to update task: {response.status_code}")
                    return {"success": False, "error": f"HTTP {response.status_code}"}

        except Exception as e:
            logger.error(f"Error updating task: {e}")
            return {"success": False, "error": str(e)}
