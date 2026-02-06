"""
Cloud Function entry point for Image Repository Pipeline.

Triggered daily by Cloud Scheduler to sync all client images.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, UTC

import functions_framework
from google.cloud import secretmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_secret(project_id: str, secret_name: str) -> str:
    """Fetch secret from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def create_orchestrator():
    """Create and configure the sync orchestrator."""
    # Import pipeline modules
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from core.drive_client import GoogleDriveClient
    from core.vision_service import GeminiVisionService
    from core.state_manager import ImageSyncStateManager
    from core.vertex_ingestion import ImageVertexIngestion
    from core.sync_orchestrator import ImageSyncOrchestrator
    from config.settings import SyncSettings

    # Load configuration from environment
    project_id = os.environ.get("GCP_PROJECT_ID", "emailpilot-438321")
    data_store_id = os.environ.get("VERTEX_DATA_STORE_ID", "emailpilot-rag_1765205761919")
    location = os.environ.get("GCP_LOCATION", "us")

    # Get secret names from environment (configurable)
    gemini_secret_name = os.environ.get("GEMINI_API_KEY_SECRET", "gemini-rag-image-processing")
    service_account_secret_name = os.environ.get("IMAGE_SYNC_SERVICE_ACCOUNT_SECRET", "rag-service-account")

    # Get Gemini API key from Secret Manager or environment
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        try:
            gemini_api_key = get_secret(project_id, gemini_secret_name)
        except Exception as e:
            logger.warning(f"Could not fetch Gemini API key from Secret Manager: {e}")

    # Get service account credentials from Secret Manager or environment
    service_account_json = os.environ.get("IMAGE_SYNC_SERVICE_ACCOUNT_JSON")
    if not service_account_json:
        try:
            service_account_json = get_secret(project_id, service_account_secret_name)
        except Exception as e:
            logger.warning(f"Could not fetch Google credentials from Secret Manager: {e}")
            # Will fall back to Application Default Credentials

    # Initialize components
    drive_client = GoogleDriveClient(service_account_json)

    vision_service = GeminiVisionService(
        api_key=gemini_api_key,
        model_name=os.environ.get("GEMINI_MODEL_NAME", "gemini-1.5-flash"),
        max_concurrent=int(os.environ.get("GEMINI_MAX_CONCURRENT", "10"))
    )

    state_manager = ImageSyncStateManager(
        project_id=project_id,
        collection_prefix=os.environ.get("IMAGE_SYNC_FIRESTORE_COLLECTION", "image_sync")
    )

    vertex_ingestion = ImageVertexIngestion(
        project_id=project_id,
        location=location,
        data_store_id=data_store_id
    )

    sync_settings = SyncSettings(
        incremental_sync_enabled=os.environ.get("IMAGE_SYNC_INCREMENTAL", "true").lower() == "true",
        batch_size=int(os.environ.get("IMAGE_SYNC_BATCH_SIZE", "50"))
    )

    return ImageSyncOrchestrator(
        drive_client=drive_client,
        vision_service=vision_service,
        state_manager=state_manager,
        vertex_ingestion=vertex_ingestion,
        sync_settings=sync_settings
    )


def load_folder_mappings():
    """Load folder mappings from configuration."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from config.settings import load_folder_mappings as _load_mappings

    # Try to load from mounted config or default location
    config_path = os.environ.get(
        "IMAGE_SYNC_FOLDER_CONFIG",
        "/app/config/folder_mappings.yaml"
    )

    # Fall back to local config
    if not os.path.exists(config_path):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config",
            "folder_mappings.yaml"
        )

    return _load_mappings(config_path)


@functions_framework.http
def sync_images(request):
    """
    Cloud Function entry point for image sync.

    Triggered by Cloud Scheduler (daily) or HTTP request for manual trigger.

    Request body (optional):
    {
        "client_id": "specific-client",  // Optional: sync only this client
        "force_full_sync": false          // Optional: ignore incremental sync
    }
    """
    start_time = datetime.now(UTC)
    logger.info(f"Image sync triggered at {start_time.isoformat()}")

    try:
        # Parse request body
        request_json = request.get_json(silent=True) or {}
        client_id = request_json.get("client_id")
        force_full_sync = request_json.get("force_full_sync", False)

        # Load folder mappings
        folder_mappings = load_folder_mappings()
        if not folder_mappings:
            logger.warning("No folder mappings configured")
            return json.dumps({
                "status": "warning",
                "message": "No folder mappings configured. Add clients to folder_mappings.yaml",
                "duration_seconds": (datetime.now(UTC) - start_time).total_seconds()
            }), 200, {"Content-Type": "application/json"}

        # Filter to specific client if requested
        if client_id:
            if client_id not in folder_mappings:
                return json.dumps({
                    "status": "error",
                    "message": f"Client '{client_id}' not found in folder mappings"
                }), 404, {"Content-Type": "application/json"}
            folder_mappings = {client_id: folder_mappings[client_id]}

        # Create orchestrator
        orchestrator = create_orchestrator()

        # Run sync
        logger.info(f"Starting sync for {len(folder_mappings)} client(s)")
        results = asyncio.run(orchestrator.sync_all_clients(folder_mappings))

        # Add timing info
        results["duration_seconds"] = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(f"Sync complete: {results['total_images_indexed']} images indexed in {results['duration_seconds']:.1f}s")

        return json.dumps(results), 200, {"Content-Type": "application/json"}

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        return json.dumps({
            "status": "error",
            "message": str(e),
            "duration_seconds": (datetime.now(UTC) - start_time).total_seconds()
        }), 500, {"Content-Type": "application/json"}


@functions_framework.http
def health_check(request):
    """Health check endpoint for the Cloud Function."""
    return json.dumps({
        "status": "healthy",
        "service": "image-sync-pipeline",
        "timestamp": datetime.now(UTC).isoformat()
    }), 200, {"Content-Type": "application/json"}
