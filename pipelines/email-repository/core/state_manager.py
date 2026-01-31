"""
Firestore State Manager for Email Repository Pipeline.

Tracks processed emails to enable incremental sync and avoid reprocessing.
"""

import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from google.cloud import firestore

logger = logging.getLogger(__name__)


class EmailSyncStateManager:
    """
    Manages email sync state in Firestore for incremental processing.

    Collections:
    - email_sync_state_{account_hash}: Per-account sync status
    - email_processed_{message_id}: Individual email processing records
    """

    def __init__(self, project_id: str, collection_prefix: str = "email_sync"):
        """
        Initialize Firestore state manager.

        Args:
            project_id: GCP project ID
            collection_prefix: Prefix for Firestore collections
        """
        self.db = firestore.Client(project=project_id)
        self.sync_state_collection = f"{collection_prefix}_state"
        self.processed_emails_collection = f"{collection_prefix}_processed"
        logger.info(
            f"EmailSyncStateManager initialized with collections: "
            f"{self.sync_state_collection}, {self.processed_emails_collection}"
        )

    def _hash_account_email(self, account_email: str) -> str:
        """Generate consistent hash for account email."""
        return hashlib.md5(account_email.lower().encode()).hexdigest()[:12]

    def get_last_sync_time(self, account_email: str) -> Optional[datetime]:
        """
        Get the last successful sync timestamp for an account.

        Args:
            account_email: Email account address

        Returns:
            Last sync datetime or None if never synced
        """
        account_hash = self._hash_account_email(account_email)
        doc_ref = self.db.collection(self.sync_state_collection).document(account_hash)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            last_sync = data.get("last_sync_timestamp")
            if last_sync:
                if hasattr(last_sync, 'replace'):
                    return last_sync.replace(tzinfo=timezone.utc)
                return last_sync
        return None

    def update_sync_state(
        self,
        account_email: str,
        status: str,
        emails_processed: int = 0,
        emails_skipped: int = 0,
        error: Optional[str] = None
    ):
        """
        Update sync state after processing.

        Args:
            account_email: Email account address
            status: Sync status ("success", "partial", "failed")
            emails_processed: Number of emails successfully processed
            emails_skipped: Number of emails skipped
            error: Error message if status is "failed"
        """
        account_hash = self._hash_account_email(account_email)
        doc_ref = self.db.collection(self.sync_state_collection).document(account_hash)

        update_data = {
            "account_email": account_email,
            "account_hash": account_hash,
            "last_sync_timestamp": firestore.SERVER_TIMESTAMP,
            "last_sync_status": status,
            "emails_processed_last_sync": emails_processed,
            "emails_skipped_last_sync": emails_skipped,
        }

        if status == "success":
            update_data["last_successful_sync"] = firestore.SERVER_TIMESTAMP

        if error:
            update_data["last_error"] = error
            update_data["last_error_timestamp"] = firestore.SERVER_TIMESTAMP

        # Use merge to update totals without overwriting
        doc_ref.set(update_data, merge=True)

        # Update running totals
        doc_ref.update({
            "total_emails_processed": firestore.Increment(emails_processed),
            "total_syncs": firestore.Increment(1)
        })

        logger.info(f"Updated sync state for {account_email}: {status}")

    def is_email_processed(self, message_id: str) -> bool:
        """
        Check if an email has already been processed.

        Args:
            message_id: Gmail message ID

        Returns:
            True if email exists in processed records
        """
        doc_ref = self.db.collection(self.processed_emails_collection).document(message_id)
        return doc_ref.get().exists

    def get_processed_email(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get processed email record.

        Args:
            message_id: Gmail message ID

        Returns:
            Email record dict or None
        """
        doc_ref = self.db.collection(self.processed_emails_collection).document(message_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def mark_email_processed(
        self,
        message_id: str,
        account_email: str,
        email_metadata: Dict[str, Any],
        categorization: Dict[str, Any],
        drive_file_id: str,
        vertex_doc_id: str
    ):
        """
        Record that an email has been successfully processed.

        Args:
            message_id: Gmail message ID
            account_email: Source account email
            email_metadata: Email metadata (subject, sender, date, etc.)
            categorization: Categorization results
            drive_file_id: Uploaded screenshot file ID
            vertex_doc_id: Created Vertex AI document ID
        """
        doc_ref = self.db.collection(self.processed_emails_collection).document(message_id)

        # Parse email date if string
        email_date = email_metadata.get('date')
        if isinstance(email_date, str):
            try:
                email_date = datetime.fromisoformat(email_date.replace('Z', '+00:00'))
            except Exception:
                email_date = None

        doc_ref.set({
            "message_id": message_id,
            "account_email": account_email,
            "email_from": email_metadata.get('sender_email', ''),
            "email_sender_name": email_metadata.get('sender', ''),
            "email_subject": email_metadata.get('subject', ''),
            "email_date": email_date,
            "email_snippet": email_metadata.get('snippet', ''),

            # Categorization data
            "product_category": categorization.get('product_category', 'other'),
            "email_type": categorization.get('email_type', 'promotional'),
            "content_theme": categorization.get('content_theme', ''),
            "brand_name": categorization.get('brand_info', {}).get('brand_name'),
            "visual_elements": categorization.get('visual_elements', {}),
            "quality_assessment": categorization.get('quality_assessment', {}),

            # Storage references
            "drive_file_id": drive_file_id,
            "vertex_doc_id": vertex_doc_id,

            # Processing metadata
            "processed_at": firestore.SERVER_TIMESTAMP,
            "status": "indexed"
        })

        logger.debug(f"Marked email processed: {message_id}")

    def mark_email_skipped(
        self,
        message_id: str,
        account_email: str,
        email_metadata: Dict[str, Any],
        skip_reason: str
    ):
        """
        Record that an email was skipped.

        Args:
            message_id: Gmail message ID
            account_email: Source account email
            email_metadata: Basic email metadata
            skip_reason: Reason for skipping
        """
        doc_ref = self.db.collection(self.processed_emails_collection).document(message_id)

        doc_ref.set({
            "message_id": message_id,
            "account_email": account_email,
            "email_from": email_metadata.get('sender_email', ''),
            "email_subject": email_metadata.get('subject', ''),
            "email_date": email_metadata.get('date'),
            "processed_at": firestore.SERVER_TIMESTAMP,
            "status": "skipped",
            "skip_reason": skip_reason,
            "drive_file_id": None,
            "vertex_doc_id": None
        })

        logger.debug(f"Marked email skipped: {message_id} - {skip_reason}")

    def get_processing_stats(self, account_email: Optional[str] = None) -> Dict[str, Any]:
        """
        Get processing statistics.

        Args:
            account_email: Optional filter by account

        Returns:
            Dictionary with processing statistics
        """
        if account_email:
            query = self.db.collection(self.processed_emails_collection).where(
                "account_email", "==", account_email
            )
        else:
            query = self.db.collection(self.processed_emails_collection)

        docs = query.stream()

        stats = {
            "total_processed": 0,
            "indexed": 0,
            "skipped": 0,
            "by_category": {},
            "by_email_type": {},
            "by_month": {},
            "recent_emails": []
        }

        for doc in docs:
            data = doc.to_dict()
            stats["total_processed"] += 1

            if data.get("status") == "indexed":
                stats["indexed"] += 1

                # Track by category
                category = data.get("product_category", "other")
                stats["by_category"][category] = stats["by_category"].get(category, 0) + 1

                # Track by email type
                email_type = data.get("email_type", "promotional")
                stats["by_email_type"][email_type] = stats["by_email_type"].get(email_type, 0) + 1

                # Track by month
                email_date = data.get("email_date")
                if email_date:
                    month_key = email_date.strftime("%Y-%m") if hasattr(email_date, 'strftime') else str(email_date)[:7]
                    stats["by_month"][month_key] = stats["by_month"].get(month_key, 0) + 1

            else:
                stats["skipped"] += 1

            # Track recent emails (last 10)
            if len(stats["recent_emails"]) < 10:
                stats["recent_emails"].append({
                    "message_id": data.get("message_id"),
                    "subject": data.get("email_subject", "")[:100],
                    "category": data.get("product_category"),
                    "status": data.get("status"),
                    "processed_at": data.get("processed_at")
                })

        return stats

    def get_sync_history(self, account_email: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get sync history for account(s).

        Args:
            account_email: Optional filter by specific account

        Returns:
            List of sync state records
        """
        if account_email:
            account_hash = self._hash_account_email(account_email)
            doc = self.db.collection(self.sync_state_collection).document(account_hash).get()
            if doc.exists:
                return [doc.to_dict()]
            return []

        # Get all accounts
        docs = self.db.collection(self.sync_state_collection).stream()
        return [doc.to_dict() for doc in docs]

    def get_emails_by_category(
        self,
        category: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get processed emails by category.

        Args:
            category: Product category to filter
            limit: Maximum results

        Returns:
            List of email records
        """
        query = self.db.collection(self.processed_emails_collection).where(
            "product_category", "==", category
        ).where(
            "status", "==", "indexed"
        ).limit(limit)

        return [doc.to_dict() for doc in query.stream()]

    def get_emails_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get processed emails within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            category: Optional category filter
            limit: Maximum results

        Returns:
            List of email records
        """
        query = self.db.collection(self.processed_emails_collection).where(
            "email_date", ">=", start_date
        ).where(
            "email_date", "<=", end_date
        ).where(
            "status", "==", "indexed"
        )

        if category:
            query = query.where("product_category", "==", category)

        return [doc.to_dict() for doc in query.limit(limit).stream()]

    def clear_account_state(self, account_email: str) -> int:
        """
        Clear all sync state for an account (for full resync).

        Args:
            account_email: Account email to clear

        Returns:
            Number of records deleted
        """
        deleted = 0

        # Delete processed email records
        query = self.db.collection(self.processed_emails_collection).where(
            "account_email", "==", account_email
        )
        for doc in query.stream():
            doc.reference.delete()
            deleted += 1

        # Delete sync state record
        account_hash = self._hash_account_email(account_email)
        doc_ref = self.db.collection(self.sync_state_collection).document(account_hash)
        if doc_ref.get().exists:
            doc_ref.delete()
            deleted += 1

        logger.info(f"Cleared {deleted} state records for {account_email}")
        return deleted

    def get_processing_log(
        self,
        account_email: Optional[str] = None,
        limit: int = 100,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get detailed processing log.

        Args:
            account_email: Optional filter by account
            limit: Maximum records
            status_filter: Filter by status ("indexed" or "skipped")

        Returns:
            List of processing records
        """
        query = self.db.collection(self.processed_emails_collection)

        if account_email:
            query = query.where("account_email", "==", account_email)

        if status_filter:
            query = query.where("status", "==", status_filter)

        docs = list(query.limit(limit).stream())

        results = []
        for doc in docs:
            data = doc.to_dict()
            results.append({
                "message_id": data.get("message_id"),
                "subject": data.get("email_subject", "")[:100],
                "sender": data.get("email_from"),
                "category": data.get("product_category"),
                "email_type": data.get("email_type"),
                "status": data.get("status"),
                "skip_reason": data.get("skip_reason"),
                "processed_at": data.get("processed_at"),
                "drive_file_id": data.get("drive_file_id"),
                "vertex_doc_id": data.get("vertex_doc_id")
            })

        return results
