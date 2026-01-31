"""
Sync Orchestrator for Image Repository Pipeline.

Coordinates all pipeline components to discover, caption, and index images.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from core.drive_client import GoogleDriveClient
from core.vision_service import GeminiVisionService
from core.state_manager import ImageSyncStateManager
from core.vertex_ingestion import ImageVertexIngestion
from config.settings import ClientFolderMapping, SyncSettings

logger = logging.getLogger(__name__)


class ImageSyncOrchestrator:
    """
    Main orchestration logic for image sync pipeline.

    Workflow:
    1. Load client folder mappings
    2. For each folder:
       a. Query Drive for new/modified images
       b. Filter already-processed files (Firestore)
       c. Download image bytes
       d. Generate captions (Gemini Vision)
       e. Filter sensitive/low-quality images
       f. Ingest to Vertex AI
       g. Update Firestore state
    """

    def __init__(
        self,
        drive_client: GoogleDriveClient,
        vision_service: GeminiVisionService,
        state_manager: ImageSyncStateManager,
        vertex_ingestion: ImageVertexIngestion,
        sync_settings: Optional[SyncSettings] = None
    ):
        """
        Initialize sync orchestrator.

        Args:
            drive_client: Google Drive API client
            vision_service: Gemini Vision captioning service
            state_manager: Firestore state tracking
            vertex_ingestion: Vertex AI document creation
            sync_settings: Sync behavior configuration
        """
        self.drive = drive_client
        self.vision = vision_service
        self.state = state_manager
        self.vertex = vertex_ingestion
        self.settings = sync_settings or SyncSettings()

        logger.info("ImageSyncOrchestrator initialized")

    async def sync_all_clients(
        self,
        folder_mappings: Dict[str, List[ClientFolderMapping]]
    ) -> Dict[str, Any]:
        """
        Run sync for all clients.

        Args:
            folder_mappings: Dictionary mapping client_id to folder configurations

        Returns:
            Summary statistics for the sync run
        """
        logger.info(f"Starting sync for {len(folder_mappings)} clients")

        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_clients": len(folder_mappings),
            "clients_processed": 0,
            "clients_failed": 0,
            "total_images_discovered": 0,
            "total_images_indexed": 0,
            "total_images_skipped": 0,
            "errors": [],
            "client_results": {}
        }

        for client_id, mappings in folder_mappings.items():
            # Skip internal keys
            if client_id.startswith('_'):
                continue

            try:
                client_result = await self.sync_client(client_id, mappings)
                results["clients_processed"] += 1
                results["total_images_discovered"] += client_result["discovered"]
                results["total_images_indexed"] += client_result["indexed"]
                results["total_images_skipped"] += client_result["skipped"]
                results["client_results"][client_id] = client_result

            except Exception as e:
                error_msg = f"Failed to sync client {client_id}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                results["errors"].append(error_msg)
                results["clients_failed"] += 1
                results["client_results"][client_id] = {
                    "status": "failed",
                    "error": str(e)
                }

        results["completed_at"] = datetime.now(timezone.utc).isoformat()
        results["status"] = "success" if not results["errors"] else "partial"

        logger.info(
            f"Sync complete: {results['clients_processed']} clients, "
            f"{results['total_images_indexed']} images indexed, "
            f"{results['total_images_skipped']} skipped"
        )

        return results

    async def sync_client(
        self,
        client_id: str,
        folder_mappings: List[ClientFolderMapping],
        force_full_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Sync all folders for a single client.

        Args:
            client_id: Client identifier
            folder_mappings: List of folder configurations
            force_full_sync: If True, ignore incremental sync and reprocess all

        Returns:
            Client sync statistics
        """
        logger.info(f"Syncing client: {client_id} ({len(folder_mappings)} folders)")

        stats = {
            "client_id": client_id,
            "discovered": 0,
            "indexed": 0,
            "skipped": 0,
            "folders_processed": 0,
            "folders_failed": 0,
            "folder_results": []
        }

        for mapping in folder_mappings:
            if not mapping.enabled:
                logger.debug(f"Skipping disabled folder: {mapping.folder_id}")
                continue

            try:
                folder_stats = await self.sync_folder(
                    client_id=client_id,
                    folder_id=mapping.folder_id,
                    folder_type=mapping.folder_type,
                    force_full_sync=force_full_sync
                )

                stats["discovered"] += folder_stats["discovered"]
                stats["indexed"] += folder_stats["indexed"]
                stats["skipped"] += folder_stats["skipped"]
                stats["folders_processed"] += 1
                stats["folder_results"].append(folder_stats)

            except Exception as e:
                logger.error(f"Failed to sync folder {mapping.folder_id}: {e}")
                stats["folders_failed"] += 1
                stats["folder_results"].append({
                    "folder_id": mapping.folder_id,
                    "status": "failed",
                    "error": str(e)
                })

        stats["status"] = "success" if stats["folders_failed"] == 0 else "partial"
        return stats

    async def sync_folder(
        self,
        client_id: str,
        folder_id: str,
        folder_type: str = "client",
        force_full_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Sync a single Drive folder.

        Args:
            client_id: Client identifier
            folder_id: Google Drive folder ID
            folder_type: "client" or "shared"
            force_full_sync: If True, reprocess all files

        Returns:
            Folder sync statistics
        """
        logger.info(f"Syncing folder {folder_id} for client {client_id}")

        stats = {
            "folder_id": folder_id,
            "folder_type": folder_type,
            "discovered": 0,
            "indexed": 0,
            "skipped": 0,
            "status": "success"
        }

        try:
            # Verify folder access
            if not self.drive.verify_folder_access(folder_id):
                raise ValueError(f"Cannot access folder: {folder_id}")

            # Get last sync time for incremental processing
            last_sync = None
            if self.settings.incremental_sync_enabled and not force_full_sync:
                last_sync = self.state.get_last_sync_time(client_id, folder_id)
                if last_sync:
                    logger.info(f"Incremental sync from: {last_sync}")

            # Discover images
            files = self.drive.list_images_in_folder(
                folder_id=folder_id,
                modified_after=last_sync,
                supported_formats=self.settings.supported_formats
            )

            stats["discovered"] = len(files)
            logger.info(f"Discovered {len(files)} images in folder {folder_id}")

            if not files:
                self.state.update_sync_state(client_id, folder_id, "success", 0, 0)
                return stats

            # Filter already-processed files (unless force sync)
            if self.settings.incremental_sync_enabled and not force_full_sync:
                files_to_process = []
                for f in files:
                    modified_time = self._parse_drive_timestamp(f.get("modifiedTime"))
                    if self.state.needs_reprocessing(f["id"], modified_time):
                        files_to_process.append(f)
                    else:
                        stats["skipped"] += 1

                logger.info(f"Processing {len(files_to_process)} new/modified images (skipped {stats['skipped']} unchanged)")
            else:
                files_to_process = files

            # Process in batches
            batch_size = self.settings.batch_size
            for i in range(0, len(files_to_process), batch_size):
                batch = files_to_process[i:i+batch_size]
                batch_stats = await self._process_batch(
                    client_id=client_id,
                    folder_id=folder_id,
                    folder_type=folder_type,
                    files=batch
                )
                stats["indexed"] += batch_stats["indexed"]
                stats["skipped"] += batch_stats["skipped"]

            # Update sync state
            self.state.update_sync_state(
                client_id=client_id,
                folder_id=folder_id,
                status="success",
                images_processed=stats["indexed"],
                images_skipped=stats["skipped"]
            )

        except Exception as e:
            logger.error(f"Error syncing folder {folder_id}: {e}", exc_info=True)
            stats["status"] = "failed"
            stats["error"] = str(e)
            self.state.update_sync_state(
                client_id=client_id,
                folder_id=folder_id,
                status="failed",
                error=str(e)
            )

        return stats

    async def _process_batch(
        self,
        client_id: str,
        folder_id: str,
        folder_type: str,
        files: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Process a batch of images.

        Steps:
        1. Download image bytes
        2. Generate captions with Gemini Vision
        3. Filter sensitive/low-quality
        4. Ingest to Vertex AI
        5. Update state tracking
        """
        stats = {"indexed": 0, "skipped": 0}

        # Skip files that are too large
        max_size = self.settings.batch_size * 1024 * 1024  # Convert MB to bytes
        files = [f for f in files if int(f.get("size", 0)) <= max_size]

        if not files:
            return stats

        # Download images
        logger.info(f"Downloading {len(files)} images")
        download_results = []
        for f in files:
            try:
                img_bytes = self.drive.download_image_bytes(f["id"])
                download_results.append((f, img_bytes, None))
            except Exception as e:
                download_results.append((f, None, str(e)))

        # Prepare images for captioning
        images_to_caption = [
            (img_bytes, f["name"])
            for f, img_bytes, err in download_results
            if img_bytes is not None
        ]

        # Caption images
        if images_to_caption:
            logger.info(f"Captioning {len(images_to_caption)} images with Gemini Vision")
            captions = await self.vision.caption_batch(images_to_caption)
        else:
            captions = []

        # Map captions back to files
        caption_idx = 0
        for f, img_bytes, download_error in download_results:
            file_id = f["id"]
            file_name = f["name"]

            # Handle download errors
            if download_error:
                logger.warning(f"Download failed for {file_name}: {download_error}")
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, "download_failed"
                )
                continue

            # Get caption for this file
            caption = captions[caption_idx] if caption_idx < len(captions) else None
            caption_idx += 1

            # Handle caption errors
            if not caption:
                logger.warning(f"Caption failed for {file_name}")
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, "caption_failed"
                )
                continue

            # Check for skip reasons in caption
            if caption.get("skip_reason"):
                logger.info(f"Skipping {file_name}: {caption['skip_reason']}")
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, caption["skip_reason"]
                )
                continue

            # Filter sensitive content
            if caption.get("sensitive_content"):
                logger.info(f"Skipping sensitive image: {file_name}")
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, "sensitive_content"
                )
                continue

            # Filter low-quality images
            if caption.get("quality_flag") in ["low", "screenshot"]:
                logger.info(f"Skipping low-quality image: {file_name}")
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, "low_quality"
                )
                continue

            # Determine target client ID
            # For shared folders, index under "shared" client
            target_client_id = client_id if folder_type == "client" else "shared"

            # Ingest to Vertex AI
            result = self.vertex.create_image_document(
                client_id=target_client_id,
                drive_metadata=f,
                caption_metadata=caption
            )

            if result["success"]:
                stats["indexed"] += 1
                self.state.mark_file_processed(
                    file_id=file_id,
                    client_id=client_id,
                    folder_id=folder_id,
                    file_name=file_name,
                    vertex_doc_id=result["document_id"],
                    drive_metadata=f,
                    caption_metadata=caption
                )
            else:
                stats["skipped"] += 1
                self.state.mark_file_skipped(
                    file_id, client_id, folder_id, file_name, "vertex_ingestion_failed"
                )

        logger.info(f"Batch complete: {stats['indexed']} indexed, {stats['skipped']} skipped")
        return stats

    def _parse_drive_timestamp(self, timestamp_str: Optional[str]) -> datetime:
        """Parse Drive API timestamp to datetime."""
        if not timestamp_str:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except:
            return datetime.min.replace(tzinfo=timezone.utc)


async def create_orchestrator_from_env() -> ImageSyncOrchestrator:
    """
    Create an orchestrator instance using environment variables.

    Returns:
        Configured ImageSyncOrchestrator
    """
    from config.settings import get_pipeline_config

    config = get_pipeline_config()

    # Initialize components
    drive_client = GoogleDriveClient(config.drive.service_account_json)

    vision_service = GeminiVisionService(
        api_key=config.vision.api_key,
        model_name=config.vision.model_name,
        max_concurrent=config.vision.max_concurrent_requests
    )

    state_manager = ImageSyncStateManager(
        project_id=config.gcp_project_id,
        collection_prefix=config.firestore_collection
    )

    vertex_ingestion = ImageVertexIngestion(
        project_id=config.gcp_project_id,
        location=config.gcp_location,
        data_store_id=config.vertex_data_store_id
    )

    return ImageSyncOrchestrator(
        drive_client=drive_client,
        vision_service=vision_service,
        state_manager=state_manager,
        vertex_ingestion=vertex_ingestion,
        sync_settings=config.sync
    )
