"""
Email Sync Orchestrator.

Coordinates the email ingestion pipeline:
1. Fetch emails from Gmail
2. Generate screenshots with Playwright
3. Categorize with Gemini Vision
4. Upload to Google Drive
5. Index in Vertex AI
6. Track state in Firestore
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from .gmail_client import GmailClient, EmailMessage
from .screenshot_service import EmailScreenshotService
from .drive_uploader import DriveUploader
from .categorizer import EmailCategorizer
from .state_manager import EmailSyncStateManager
from .vertex_ingestion import EmailVertexIngestion

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    account_email: str
    status: str  # "success", "partial", "failed"
    emails_found: int = 0
    emails_processed: int = 0
    emails_skipped: int = 0
    emails_failed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class EmailSyncOrchestrator:
    """
    Orchestrates the email sync pipeline.

    Handles:
    - Incremental sync (only new emails since last sync)
    - Full sync (all emails in date range)
    - Batch processing with error handling
    - Progress tracking and state management
    """

    def __init__(
        self,
        gmail_client: GmailClient,
        screenshot_service: EmailScreenshotService,
        drive_uploader: DriveUploader,
        categorizer: EmailCategorizer,
        state_manager: EmailSyncStateManager,
        vertex_ingestion: EmailVertexIngestion,
        batch_size: int = 25,
        max_emails_per_sync: int = 500
    ):
        """
        Initialize orchestrator with component services.

        Args:
            gmail_client: Gmail API client
            screenshot_service: Playwright screenshot service
            drive_uploader: Google Drive uploader
            categorizer: Gemini Vision categorizer
            state_manager: Firestore state manager
            vertex_ingestion: Vertex AI ingestion service
            batch_size: Number of emails to process per batch
            max_emails_per_sync: Maximum emails to process in single sync
        """
        self.gmail = gmail_client
        self.screenshot_service = screenshot_service
        self.drive_uploader = drive_uploader
        self.categorizer = categorizer
        self.state_manager = state_manager
        self.vertex_ingestion = vertex_ingestion
        self.batch_size = batch_size
        self.max_emails_per_sync = max_emails_per_sync

    async def sync_account(
        self,
        account_email: str,
        force_full_sync: bool = False,
        date_range_start: Optional[datetime] = None,
        sender_blocklist: Optional[List[str]] = None,
        subject_blocklist: Optional[List[str]] = None
    ) -> SyncResult:
        """
        Sync emails from an account.

        Workflow:
        1. Query Gmail for emails (incremental or full)
        2. Filter already-processed emails (Firestore check)
        3. Batch retrieve HTML content
        4. Generate screenshots (Playwright)
        5. Categorize with Gemini Vision
        6. Upload to Google Drive
        7. Index in Vertex AI
        8. Update Firestore state

        Args:
            account_email: Email account to sync
            force_full_sync: If True, ignore incremental sync
            date_range_start: Start date for email query
            sender_blocklist: Senders to skip
            subject_blocklist: Subjects to skip

        Returns:
            SyncResult with processing statistics
        """
        start_time = datetime.now()
        logger.info(f"Starting sync for {account_email} (force_full={force_full_sync})")

        try:
            # Determine date range for query
            if force_full_sync or date_range_start:
                after_date = date_range_start
            else:
                # Incremental: only emails since last sync
                after_date = self.state_manager.get_last_sync_time(account_email)
                if after_date:
                    logger.info(f"Incremental sync from {after_date}")
                else:
                    logger.info("No previous sync found, doing full sync")

            # Fetch email list from Gmail
            emails = self.gmail.list_emails(
                after_date=after_date,
                max_results=self.max_emails_per_sync,
                sender_blocklist=sender_blocklist,
                subject_blocklist=subject_blocklist
            )

            logger.info(f"Found {len(emails)} emails to potentially process")

            if not emails:
                self.state_manager.update_sync_state(
                    account_email=account_email,
                    status="success",
                    emails_processed=0,
                    emails_skipped=0
                )
                return SyncResult(
                    account_email=account_email,
                    status="success",
                    emails_found=0,
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            # Filter already-processed emails
            emails_to_process = []
            already_processed = 0

            for email in emails:
                if self.state_manager.is_email_processed(email.message_id):
                    already_processed += 1
                else:
                    emails_to_process.append(email)

            logger.info(f"After filtering: {len(emails_to_process)} new, {already_processed} already processed")

            if not emails_to_process:
                self.state_manager.update_sync_state(
                    account_email=account_email,
                    status="success",
                    emails_processed=0,
                    emails_skipped=already_processed
                )
                return SyncResult(
                    account_email=account_email,
                    status="success",
                    emails_found=len(emails),
                    emails_skipped=already_processed,
                    duration_seconds=(datetime.now() - start_time).total_seconds()
                )

            # Process in batches
            total_processed = 0
            total_failed = 0

            for i in range(0, len(emails_to_process), self.batch_size):
                batch = emails_to_process[i:i + self.batch_size]
                batch_num = i // self.batch_size + 1
                logger.info(f"Processing batch {batch_num} ({len(batch)} emails)")

                processed, failed = await self._process_batch(batch, account_email)
                total_processed += processed
                total_failed += failed

            # Update final sync state
            status = "success" if total_failed == 0 else "partial"
            self.state_manager.update_sync_state(
                account_email=account_email,
                status=status,
                emails_processed=total_processed,
                emails_skipped=already_processed + total_failed
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Sync complete for {account_email}: "
                f"{total_processed} processed, {total_failed} failed in {duration:.1f}s"
            )

            return SyncResult(
                account_email=account_email,
                status=status,
                emails_found=len(emails),
                emails_processed=total_processed,
                emails_skipped=already_processed,
                emails_failed=total_failed,
                duration_seconds=duration
            )

        except Exception as e:
            logger.error(f"Sync failed for {account_email}: {e}", exc_info=True)
            self.state_manager.update_sync_state(
                account_email=account_email,
                status="failed",
                error=str(e)
            )
            return SyncResult(
                account_email=account_email,
                status="failed",
                error=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds()
            )

    async def _process_batch(
        self,
        emails: List[EmailMessage],
        account_email: str
    ) -> tuple:
        """
        Process a batch of emails through the pipeline.

        Args:
            emails: List of emails to process
            account_email: Source account email

        Returns:
            Tuple of (processed_count, failed_count)
        """
        processed = 0
        failed = 0

        # Step 1: Fetch HTML content for all emails
        html_contents = []
        for email in emails:
            try:
                html = self.gmail.get_email_html(email.message_id)
                if html:
                    html_contents.append((email, html))
                else:
                    self.state_manager.mark_email_skipped(
                        message_id=email.message_id,
                        account_email=account_email,
                        email_metadata=email.to_dict(),
                        skip_reason="no_html_content"
                    )
                    failed += 1
            except Exception as e:
                logger.warning(f"Failed to fetch HTML for {email.message_id}: {e}")
                self.state_manager.mark_email_skipped(
                    message_id=email.message_id,
                    account_email=account_email,
                    email_metadata=email.to_dict(),
                    skip_reason=f"html_fetch_error: {str(e)[:50]}"
                )
                failed += 1

        if not html_contents:
            return processed, failed

        # Step 2: Generate screenshots
        screenshot_tasks = [
            (html, email.message_id) for email, html in html_contents
        ]

        async with EmailScreenshotService(
            viewport_width=800,
            viewport_height=1200,
            format="png"
        ) as screenshot_service:
            screenshot_results = await screenshot_service.capture_batch(
                screenshot_tasks,
                max_concurrent=5
            )

        # Map results back to emails
        screenshots = {}
        for (email, _), result in zip(html_contents, screenshot_results):
            if result.success and result.image_bytes:
                screenshots[email.message_id] = (email, result.image_bytes)
            else:
                self.state_manager.mark_email_skipped(
                    message_id=email.message_id,
                    account_email=account_email,
                    email_metadata=email.to_dict(),
                    skip_reason=f"screenshot_error: {result.error or 'unknown'}"[:100]
                )
                failed += 1

        if not screenshots:
            return processed, failed

        # Step 3: Categorize with Gemini Vision
        categorization_tasks = [
            (image_bytes, msg_id, email.to_dict())
            for msg_id, (email, image_bytes) in screenshots.items()
        ]

        categorization_results = await self.categorizer.categorize_batch(
            categorization_tasks,
            max_concurrent=10
        )

        # Map results
        categorized = {}
        for (msg_id, (email, image_bytes)), result in zip(screenshots.items(), categorization_results):
            if result.success:
                categorized[msg_id] = (email, image_bytes, result.to_dict())
            else:
                # Still proceed with default categorization
                default_cat = {
                    "product_category": self.categorizer.categorize_by_keywords(
                        email.subject, email.sender
                    ),
                    "email_type": "promotional",
                    "visual_elements": {},
                    "brand_info": {},
                    "content_theme": "",
                    "quality_assessment": {}
                }
                categorized[msg_id] = (email, image_bytes, default_cat)
                logger.warning(f"Categorization failed for {msg_id}, using default")

        # Step 4: Upload to Drive and index in Vertex
        for msg_id, (email, image_bytes, categorization) in categorized.items():
            try:
                # Determine folder organization
                category = categorization.get("product_category", "other")
                year = str(email.date.year) if email.date else "unknown"
                month = str(email.date.month).zfill(2) if email.date else "00"

                # Generate filename
                safe_subject = email.subject[:50].replace('/', '_').replace('\\', '_')
                filename = f"{msg_id}_{safe_subject}"

                # Upload to Drive
                upload_result = self.drive_uploader.upload_screenshot(
                    image_bytes=image_bytes,
                    filename=filename,
                    category=category,
                    year=year,
                    month=month
                )

                if not upload_result.success:
                    self.state_manager.mark_email_skipped(
                        message_id=msg_id,
                        account_email=account_email,
                        email_metadata=email.to_dict(),
                        skip_reason=f"drive_upload_error: {upload_result.error or 'unknown'}"[:100]
                    )
                    failed += 1
                    continue

                # Index in Vertex AI
                vertex_result = self.vertex_ingestion.create_email_document(
                    message_id=msg_id,
                    account_email=account_email,
                    email_metadata=email.to_dict(),
                    categorization=categorization,
                    drive_file_id=upload_result.file_id,
                    screenshot_link=upload_result.web_view_link
                )

                if vertex_result.get("success"):
                    # Mark as processed
                    self.state_manager.mark_email_processed(
                        message_id=msg_id,
                        account_email=account_email,
                        email_metadata=email.to_dict(),
                        categorization=categorization,
                        drive_file_id=upload_result.file_id,
                        vertex_doc_id=vertex_result.get("document_id", "")
                    )
                    processed += 1
                else:
                    self.state_manager.mark_email_skipped(
                        message_id=msg_id,
                        account_email=account_email,
                        email_metadata=email.to_dict(),
                        skip_reason=f"vertex_error: {vertex_result.get('error', 'unknown')}"[:100]
                    )
                    failed += 1

            except Exception as e:
                logger.error(f"Failed to process email {msg_id}: {e}")
                self.state_manager.mark_email_skipped(
                    message_id=msg_id,
                    account_email=account_email,
                    email_metadata=email.to_dict(),
                    skip_reason=f"processing_error: {str(e)[:50]}"
                )
                failed += 1

        return processed, failed

    async def sync_all_accounts(
        self,
        accounts: List[Dict[str, Any]]
    ) -> List[SyncResult]:
        """
        Sync multiple email accounts.

        Args:
            accounts: List of account configurations

        Returns:
            List of SyncResult for each account
        """
        results = []

        for account in accounts:
            if not account.get('enabled', True):
                continue

            result = await self.sync_account(
                account_email=account['account_email'],
                date_range_start=datetime.fromisoformat(account.get('date_range_start'))
                    if account.get('date_range_start') else None,
                sender_blocklist=account.get('sender_blocklist'),
                subject_blocklist=account.get('subject_blocklist')
            )
            results.append(result)

        return results

    def get_sync_status(self, account_email: str) -> Dict[str, Any]:
        """
        Get current sync status for an account.

        Args:
            account_email: Account to check

        Returns:
            Status dictionary with stats
        """
        history = self.state_manager.get_sync_history(account_email)
        stats = self.state_manager.get_processing_stats(account_email)

        return {
            "account_email": account_email,
            "last_sync": history[0] if history else None,
            "total_indexed": stats.get("indexed", 0),
            "total_skipped": stats.get("skipped", 0),
            "by_category": stats.get("by_category", {}),
            "by_email_type": stats.get("by_email_type", {})
        }


async def create_orchestrator_from_config(config) -> EmailSyncOrchestrator:
    """
    Create orchestrator from pipeline configuration.

    Args:
        config: PipelineConfig object

    Returns:
        Configured EmailSyncOrchestrator
    """
    # Initialize components
    gmail_client = GmailClient(
        service_account_json=config.gmail.service_account_json,
        delegated_email=config.gmail.delegated_email
    )

    screenshot_service = EmailScreenshotService(
        viewport_width=config.screenshot.viewport_width,
        viewport_height=config.screenshot.viewport_height,
        format=config.screenshot.format
    )

    drive_uploader = DriveUploader(
        service_account_json=config.drive.service_account_json,
        root_folder_id=config.drive.root_folder_id
    )

    categorizer = EmailCategorizer(
        api_key=config.vision.api_key,
        model_name=config.vision.model_name
    )

    state_manager = EmailSyncStateManager(
        project_id=config.gcp_project_id,
        collection_prefix=config.firestore_collection
    )

    vertex_ingestion = EmailVertexIngestion(
        project_id=config.gcp_project_id,
        location=config.gcp_location,
        data_store_id=config.vertex_data_store_id
    )

    return EmailSyncOrchestrator(
        gmail_client=gmail_client,
        screenshot_service=screenshot_service,
        drive_uploader=drive_uploader,
        categorizer=categorizer,
        state_manager=state_manager,
        vertex_ingestion=vertex_ingestion,
        batch_size=config.sync.batch_size,
        max_emails_per_sync=config.sync.max_emails_per_sync
    )
