"""
Firestore State Manager for Image Repository Pipeline.

Tracks which images have been processed to enable incremental sync.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from google.cloud import firestore

logger = logging.getLogger(__name__)


class ImageSyncStateManager:
    """
    Manages sync state in Firestore to enable incremental processing.

    Collections:
    - image_sync_state: Per-folder sync status and timestamps
    - processed_images: Individual file processing records
    """

    def __init__(self, project_id: str, collection_prefix: str = "image_sync"):
        """
        Initialize Firestore state manager.

        Args:
            project_id: GCP project ID
            collection_prefix: Prefix for Firestore collections
        """
        self.db = firestore.Client(project=project_id)
        self.sync_state_collection = f"{collection_prefix}_state"
        self.processed_images_collection = f"{collection_prefix}_processed"
        logger.info(f"ImageSyncStateManager initialized with collections: {self.sync_state_collection}, {self.processed_images_collection}")

    def get_last_sync_time(self, client_id: str, folder_id: str) -> Optional[datetime]:
        """
        Get the last successful sync timestamp for a folder.

        Args:
            client_id: Client identifier
            folder_id: Google Drive folder ID

        Returns:
            Last sync datetime or None if never synced
        """
        doc_id = f"{client_id}_{folder_id}"
        doc_ref = self.db.collection(self.sync_state_collection).document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            last_sync = data.get("last_sync_timestamp")
            if last_sync:
                # Firestore returns datetime with timezone
                if hasattr(last_sync, 'replace'):
                    return last_sync.replace(tzinfo=timezone.utc)
                return last_sync
        return None

    def update_sync_state(
        self,
        client_id: str,
        folder_id: str,
        status: str,
        images_processed: int = 0,
        images_skipped: int = 0,
        error: Optional[str] = None
    ):
        """
        Update sync state after processing.

        Args:
            client_id: Client identifier
            folder_id: Google Drive folder ID
            status: Sync status ("success", "partial", "failed")
            images_processed: Number of images successfully processed
            images_skipped: Number of images skipped
            error: Error message if status is "failed"
        """
        doc_id = f"{client_id}_{folder_id}"
        doc_ref = self.db.collection(self.sync_state_collection).document(doc_id)

        update_data = {
            "client_id": client_id,
            "folder_id": folder_id,
            "last_sync_timestamp": firestore.SERVER_TIMESTAMP,
            "last_sync_status": status,
            "images_processed_last_sync": images_processed,
            "images_skipped_last_sync": images_skipped,
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
            "total_images_processed": firestore.Increment(images_processed),
            "total_syncs": firestore.Increment(1)
        })

        logger.info(f"Updated sync state for {client_id}/{folder_id}: {status}")

    def is_file_processed(self, file_id: str) -> bool:
        """
        Check if a file has already been processed.

        Args:
            file_id: Google Drive file ID

        Returns:
            True if file exists in processed records
        """
        doc_ref = self.db.collection(self.processed_images_collection).document(file_id)
        return doc_ref.get().exists

    def needs_reprocessing(
        self,
        file_id: str,
        current_modified_time: datetime
    ) -> bool:
        """
        Check if a file needs reprocessing (modified since last sync).

        Args:
            file_id: Google Drive file ID
            current_modified_time: File's current modified timestamp from Drive

        Returns:
            True if file should be reprocessed
        """
        doc_ref = self.db.collection(self.processed_images_collection).document(file_id)
        doc = doc_ref.get()

        if not doc.exists:
            return True

        data = doc.to_dict()
        last_modified = data.get("drive_modified_time")

        if not last_modified:
            return True

        # Compare timestamps (handle timezone-aware/naive comparison)
        if hasattr(last_modified, 'replace') and last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        if hasattr(current_modified_time, 'replace') and current_modified_time.tzinfo is None:
            current_modified_time = current_modified_time.replace(tzinfo=timezone.utc)

        return current_modified_time > last_modified

    def mark_file_processed(
        self,
        file_id: str,
        client_id: str,
        folder_id: str,
        file_name: str,
        vertex_doc_id: str,
        drive_metadata: Dict[str, Any],
        caption_metadata: Dict[str, Any]
    ):
        """
        Record that a file has been successfully processed.

        Args:
            file_id: Google Drive file ID
            client_id: Client identifier
            folder_id: Source folder ID
            file_name: Original filename
            vertex_doc_id: Created Vertex AI document ID
            drive_metadata: File metadata from Drive API
            caption_metadata: Generated caption metadata
        """
        doc_ref = self.db.collection(self.processed_images_collection).document(file_id)

        # Parse Drive modified time if string
        drive_modified = drive_metadata.get("modifiedTime")
        if isinstance(drive_modified, str):
            drive_modified = datetime.fromisoformat(drive_modified.replace("Z", "+00:00"))

        doc_ref.set({
            "file_id": file_id,
            "client_id": client_id,
            "folder_id": folder_id,
            "file_name": file_name,
            "processed_at": firestore.SERVER_TIMESTAMP,
            "vertex_doc_id": vertex_doc_id,
            "caption_generated": True,
            "sensitive_content": caption_metadata.get("sensitive_content", False),
            "quality_flag": caption_metadata.get("quality_flag", "unknown"),
            "mood": caption_metadata.get("mood", ""),
            "visual_tags": caption_metadata.get("visual_tags", []),
            "drive_modified_time": drive_modified,
            "drive_link": drive_metadata.get("webViewLink", ""),
            "thumbnail_link": drive_metadata.get("thumbnailLink", ""),
            "file_size": int(drive_metadata.get("size", 0)),
            "skip_reason": None
        })

        logger.debug(f"Marked file processed: {file_name} ({file_id})")

    def mark_file_skipped(
        self,
        file_id: str,
        client_id: str,
        folder_id: str,
        file_name: str,
        skip_reason: str
    ):
        """
        Record that a file was skipped (PII, low quality, error, etc.).

        Args:
            file_id: Google Drive file ID
            client_id: Client identifier
            folder_id: Source folder ID
            file_name: Original filename
            skip_reason: Reason for skipping (e.g., "sensitive_content", "low_quality", "download_failed")
        """
        doc_ref = self.db.collection(self.processed_images_collection).document(file_id)

        doc_ref.set({
            "file_id": file_id,
            "client_id": client_id,
            "folder_id": folder_id,
            "file_name": file_name,
            "processed_at": firestore.SERVER_TIMESTAMP,
            "caption_generated": False,
            "skip_reason": skip_reason,
            "vertex_doc_id": None
        })

        logger.debug(f"Marked file skipped: {file_name} ({file_id}) - {skip_reason}")

    def get_processing_stats(self, client_id: str) -> Dict[str, Any]:
        """
        Get statistics for a client's image processing.

        Args:
            client_id: Client identifier

        Returns:
            Dictionary with processing statistics
        """
        query = self.db.collection(self.processed_images_collection).where(
            "client_id", "==", client_id
        )

        docs = query.stream()

        stats = {
            "total_processed": 0,
            "indexed": 0,
            "skipped": 0,
            "sensitive": 0,
            "low_quality": 0,
            "by_mood": {},
            "recent_files": []
        }

        recent_cutoff = datetime.now(timezone.utc)

        for doc in docs:
            data = doc.to_dict()
            stats["total_processed"] += 1

            if data.get("caption_generated"):
                stats["indexed"] += 1
            else:
                stats["skipped"] += 1

            if data.get("sensitive_content"):
                stats["sensitive"] += 1

            if data.get("quality_flag") in ["low", "screenshot"]:
                stats["low_quality"] += 1

            # Track mood distribution
            mood = data.get("mood", "unknown")
            stats["by_mood"][mood] = stats["by_mood"].get(mood, 0) + 1

            # Track recent files (last 10)
            if len(stats["recent_files"]) < 10:
                file_id = data.get("file_id")
                # Construct public thumbnail URL from file_id
                thumbnail_link = f"https://drive.google.com/thumbnail?id={file_id}&sz=w200" if file_id else ""
                stats["recent_files"].append({
                    "file_id": file_id,
                    "file_name": data.get("file_name"),
                    "mood": mood,
                    "processed_at": data.get("processed_at"),
                    "thumbnail_link": thumbnail_link
                })

        return stats

    def get_folder_sync_history(self, client_id: str) -> List[Dict[str, Any]]:
        """
        Get sync history for all folders belonging to a client.

        Args:
            client_id: Client identifier

        Returns:
            List of sync state records
        """
        query = self.db.collection(self.sync_state_collection).where(
            "client_id", "==", client_id
        ).order_by("last_sync_timestamp", direction=firestore.Query.DESCENDING)

        docs = query.stream()
        history = []

        for doc in docs:
            data = doc.to_dict()
            history.append({
                "folder_id": data.get("folder_id"),
                "last_sync": data.get("last_sync_timestamp"),
                "status": data.get("last_sync_status"),
                "images_processed": data.get("images_processed_last_sync", 0),
                "images_skipped": data.get("images_skipped_last_sync", 0),
                "total_images": data.get("total_images_processed", 0),
                "error": data.get("last_error")
            })

        return history

    def get_processing_log(
        self,
        client_id: str,
        limit: int = 100,
        status_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get detailed processing log for a client's images.

        Args:
            client_id: Client identifier
            limit: Maximum number of records to return
            status_filter: Optional filter - "indexed", "skipped", or None for all

        Returns:
            List of processing records with status details
        """
        query = self.db.collection(self.processed_images_collection).where(
            "client_id", "==", client_id
        )

        docs = list(query.stream())

        # Sort by processed_at descending (in memory since Firestore needs index)
        docs_data = []
        for doc in docs:
            data = doc.to_dict()
            docs_data.append(data)

        # Sort by processed_at
        docs_data.sort(
            key=lambda x: x.get("processed_at") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        results = []
        for data in docs_data:
            if len(results) >= limit:
                break

            # Determine status
            if data.get("caption_generated"):
                status = "indexed"
            else:
                status = "skipped"

            # Apply filter if specified
            if status_filter and status != status_filter:
                continue

            # Construct public thumbnail URL from file_id
            file_id = data.get("file_id")
            thumbnail_link = f"https://drive.google.com/thumbnail?id={file_id}&sz=w200" if file_id else ""

            results.append({
                "file_id": file_id,
                "file_name": data.get("file_name"),
                "status": status,
                "skip_reason": data.get("skip_reason"),
                "mood": data.get("mood", ""),
                "quality_flag": data.get("quality_flag", ""),
                "sensitive_content": data.get("sensitive_content", False),
                "visual_tags": data.get("visual_tags", []),
                "processed_at": data.get("processed_at"),
                "thumbnail_link": thumbnail_link,
                "drive_link": data.get("drive_link"),
                "vertex_doc_id": data.get("vertex_doc_id"),
                "folder_id": data.get("folder_id")
            })

        return results

    def clear_client_state(self, client_id: str) -> int:
        """
        Clear all sync state for a client (for full resync).

        Args:
            client_id: Client identifier

        Returns:
            Number of records deleted
        """
        deleted = 0

        # Delete processed images records
        query = self.db.collection(self.processed_images_collection).where(
            "client_id", "==", client_id
        )
        for doc in query.stream():
            doc.reference.delete()
            deleted += 1

        # Delete sync state records
        query = self.db.collection(self.sync_state_collection).where(
            "client_id", "==", client_id
        )
        for doc in query.stream():
            doc.reference.delete()
            deleted += 1

        logger.info(f"Cleared {deleted} state records for client {client_id}")
        return deleted
