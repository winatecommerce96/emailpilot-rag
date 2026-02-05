"""
FastAPI routes for Image Repository Pipeline.

Provides endpoints for manual sync triggers, status monitoring, and folder management.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse, parse_qs
import urllib.request
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, Response
from pydantic import BaseModel, Field
from app.client_id import normalize_client_id, is_canonical_client_id
import os
import importlib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["Image Repository"])


_image_repo_initialized = False
_image_repo_modules = {}  # Cache our loaded modules with unique keys

def _import_local(module_path: str):
    """Import modules from image-repository pipeline, ensuring correct paths.

    Uses a module aliasing strategy to avoid conflicts with other pipelines
    that have identically-named modules (config, core, etc.).
    """
    import sys
    import importlib.util
    from pathlib import Path

    global _image_repo_initialized, _image_repo_modules

    # Create a unique module key for image-repository
    unique_key = f"image_repo_{module_path}"
    module_name = unique_key
    cache_key = unique_key

    # Core/config modules need their canonical names for intra-pipeline imports
    if module_path.startswith(("core", "config")):
        module_name = module_path
        cache_key = module_name

    # Return cached module if we already loaded it
    if cache_key in _image_repo_modules:
        return _image_repo_modules[cache_key]

    pipeline_root = Path(__file__).parent.parent  # pipelines/image-repository

    # Convert module path to file path
    # e.g., "config.settings" -> "config/settings.py"
    parts = module_path.split(".")
    module_file = pipeline_root / "/".join(parts[:-1]) / f"{parts[-1]}.py" if len(parts) > 1 else pipeline_root / f"{parts[0]}.py"

    # Handle package imports (e.g., "config" -> "config/__init__.py")
    if not module_file.exists():
        module_file = pipeline_root / "/".join(parts) / "__init__.py"

    if not module_file.exists():
        raise ImportError(f"Cannot find module {module_path} at {module_file}")

    # Load the module with a unique name to avoid conflicts
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec for {module_path} from {module_file}")

    module = importlib.util.module_from_spec(spec)

    # Temporarily add pipeline root to path for relative imports within the module
    pipeline_root_str = str(pipeline_root)
    path_added = False
    if pipeline_root_str not in sys.path:
        sys.path.insert(0, pipeline_root_str)
        path_added = True

    # Cleanup conflicting modules for image-repository imports
    if module_path.startswith(("core", "config")):
        for mod_name in list(sys.modules.keys()):
            if mod_name in ("core", "config") or mod_name.startswith("core.") or mod_name.startswith("config."):
                del sys.modules[mod_name]
        _image_repo_initialized = True

        # Ensure package modules exist for absolute imports like core.* and config.*
        for pkg_name in ("core", "config"):
            pkg_dir = pipeline_root / pkg_name
            if pkg_dir.exists():
                pkg_spec = importlib.machinery.ModuleSpec(pkg_name, None, is_package=True)
                pkg_module = importlib.util.module_from_spec(pkg_spec)
                pkg_module.__path__ = [str(pkg_dir)]
                pkg_module.__file__ = str(pkg_dir / "__init__.py")
                sys.modules[pkg_name] = pkg_module

    try:
        spec.loader.exec_module(module)
    finally:
        # Remove from path if we added it
        if path_added:
            try:
                sys.path.remove(pipeline_root_str)
            except ValueError:
                pass

    # Cache the loaded module
    _image_repo_modules[cache_key] = module

    return module


def require_canonical_client_id(value: str) -> str:
    raw = (value or "").strip()
    normalized = normalize_client_id(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="client_id is required")
    if normalized != raw:
        raise HTTPException(
            status_code=400,
            detail=f"client_id must be kebab-case (example: '{normalized}')"
        )
    if not is_canonical_client_id(normalized):
        raise HTTPException(
            status_code=400,
            detail="client_id must be kebab-case (lowercase letters, digits, hyphens)"
        )
    return normalized


def _extract_drive_file_id(
    drive_link: Optional[str],
    thumbnail_link: Optional[str],
    source: Optional[str],
    doc_id: Optional[str]
) -> Optional[str]:
    """Best-effort extraction of Google Drive file ID from available fields."""
    candidates = [drive_link, thumbnail_link]
    for url in candidates:
        if not url:
            continue
        # Common /file/d/<id>/ or /d/<id>/ patterns
        if "/d/" in url:
            try:
                return url.split("/d/")[1].split("/")[0].split("?")[0]
            except (IndexError, AttributeError):
                pass
        # Query param patterns (open?id=..., uc?id=..., thumbnail?id=...)
        try:
            parsed = urlparse(url)
            query_id = parse_qs(parsed.query).get("id", [None])[0]
            if query_id:
                return query_id
        except Exception:
            pass

    if source and isinstance(source, str) and source.startswith("google_drive:"):
        try:
            return source.split("google_drive:", 1)[1].split("/")[-1]
        except Exception:
            pass

    if doc_id and isinstance(doc_id, str) and doc_id.startswith("img_"):
        try:
            return doc_id.rsplit("_", 1)[-1]
        except Exception:
            pass

    return None


# =============================================================================
# Pydantic Models
# =============================================================================

class SyncTriggerRequest(BaseModel):
    """Request body for triggering image sync."""
    client_id: Optional[str] = Field(None, description="Sync specific client only")
    force_full_sync: bool = Field(False, description="Ignore incremental sync, reprocess all")


class SyncStatusResponse(BaseModel):
    """Response for sync status endpoint."""
    status: str
    message: str
    stats: Optional[Dict[str, Any]] = None


class FolderConfig(BaseModel):
    """Configuration for a Drive folder."""
    folder_id: str
    folder_name: str = ""
    enabled: bool = True


class FolderConfigUpdate(BaseModel):
    """Request to update folder configuration."""
    folders: List[FolderConfig]


class ImageInfo(BaseModel):
    """Information about an indexed image."""
    file_name: str
    drive_link: str
    thumbnail_link: str
    mood: str
    description: str
    visual_tags: List[str]


# =============================================================================
# State Management (lazy initialization)
# =============================================================================

_orchestrator = None
_folder_mappings = None
_state_manager = None
_vertex_ingestion = None
_drive_client = None


def _reset_orchestrator():
    """Reset the cached orchestrator (useful after credential changes)."""
    global _orchestrator
    _orchestrator = None


def _get_orchestrator():
    """Lazy initialization of orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        sync_orchestrator = _import_local("core.sync_orchestrator")
        drive_client_mod = _import_local("core.drive_client")
        vision_service_mod = _import_local("core.vision_service")
        state_manager_mod = _import_local("core.state_manager")
        vertex_ingestion_mod = _import_local("core.vertex_ingestion")
        settings_mod = _import_local("config.settings")

        ImageSyncOrchestrator = sync_orchestrator.ImageSyncOrchestrator
        GoogleDriveClient = drive_client_mod.GoogleDriveClient
        GeminiVisionService = vision_service_mod.GeminiVisionService
        ImageSyncStateManager = state_manager_mod.ImageSyncStateManager
        ImageVertexIngestion = vertex_ingestion_mod.ImageVertexIngestion
        get_pipeline_config = settings_mod.get_pipeline_config

        config = get_pipeline_config()

        # Check if required configuration is available
        if not config.vision.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        drive_client = GoogleDriveClient(config.drive.service_account_json)
        vision_service = GeminiVisionService(
            api_key=config.vision.api_key,
            model_name=config.vision.model_name
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

        _orchestrator = ImageSyncOrchestrator(
            drive_client=drive_client,
            vision_service=vision_service,
            state_manager=state_manager,
            vertex_ingestion=vertex_ingestion,
            sync_settings=config.sync
        )

    return _orchestrator


def _get_drive_client():
    """Lazy initialization of Drive client for thumbnail proxy."""
    global _drive_client
    if _drive_client is None:
        drive_client_mod = _import_local("core.drive_client")
        settings_mod = _import_local("config.settings")

        GoogleDriveClient = drive_client_mod.GoogleDriveClient
        get_pipeline_config = settings_mod.get_pipeline_config

        config = get_pipeline_config()
        _drive_client = GoogleDriveClient(config.drive.service_account_json)

    return _drive_client


def _get_folder_mappings():
    """Lazy initialization of folder mappings."""
    global _folder_mappings
    if _folder_mappings is None:
        settings_mod = _import_local("config.settings")
        load_folder_mappings = settings_mod.load_folder_mappings
        _folder_mappings = load_folder_mappings()
    return _folder_mappings


def _get_state_manager():
    """Lazy initialization of state manager."""
    global _state_manager
    if _state_manager is None:
        state_manager_mod = _import_local("core.state_manager")
        settings_mod = _import_local("config.settings")

        ImageSyncStateManager = state_manager_mod.ImageSyncStateManager
        get_pipeline_config = settings_mod.get_pipeline_config
        config = get_pipeline_config()
        _state_manager = ImageSyncStateManager(
            project_id=config.gcp_project_id,
            collection_prefix=config.firestore_collection
        )
    return _state_manager


def _get_vertex_ingestion():
    """Lazy initialization of Vertex AI ingestion client."""
    global _vertex_ingestion
    if _vertex_ingestion is None:
        vertex_ingestion_mod = _import_local("core.vertex_ingestion")
        settings_mod = _import_local("config.settings")

        ImageVertexIngestion = vertex_ingestion_mod.ImageVertexIngestion
        get_pipeline_config = settings_mod.get_pipeline_config
        config = get_pipeline_config()
        _vertex_ingestion = ImageVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )
    return _vertex_ingestion


# =============================================================================
# Background Task Runner
# =============================================================================

async def _run_sync_task(
    orchestrator,
    folder_mappings: Dict,
    client_id: Optional[str] = None,
    force_full_sync: bool = False
):
    """Background task to run image sync."""
    try:
        if client_id:
            # Sync single client
            if client_id not in folder_mappings:
                logger.error(f"Client {client_id} not found in folder mappings")
                return

            mappings = folder_mappings[client_id]
            results = await orchestrator.sync_client(
                client_id,
                mappings,
                force_full_sync=force_full_sync
            )
        else:
            # Sync all clients
            results = await orchestrator.sync_all_clients(folder_mappings)

        logger.info(f"Background sync complete: {results}")

    except Exception as e:
        logger.error(f"Background sync failed: {e}", exc_info=True)


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/sync", response_model=SyncStatusResponse)
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger image sync pipeline.

    Can sync all clients or a specific client. Runs in background.

    - **client_id**: Optional - sync only this client
    - **force_full_sync**: If True, reprocess all images (ignore incremental sync)
    """
    try:
        orchestrator = _get_orchestrator()
        folder_mappings = _get_folder_mappings()

        client_id = None
        if request.client_id:
            client_id = require_canonical_client_id(request.client_id)
            if client_id not in folder_mappings:
                raise HTTPException(
                    status_code=404,
                    detail=f"Client '{client_id}' not found in folder mappings"
                )
            client_count = 1
        else:
            # Count actual clients (exclude internal keys)
            client_count = sum(1 for k in folder_mappings if not k.startswith('_'))

        # Run sync in background
        background_tasks.add_task(
            _run_sync_task,
            orchestrator,
            folder_mappings,
            client_id,
            request.force_full_sync
        )

        return SyncStatusResponse(
            status="started",
            message=f"Image sync started for {client_count} client(s). Running in background.",
            stats={"client_id": client_id, "force_full_sync": request.force_full_sync}
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/{client_id}", response_model=SyncStatusResponse)
async def trigger_client_sync(
    client_id: str,
    background_tasks: BackgroundTasks,
    force_full_sync: bool = Query(False, description="Reprocess all images")
):
    """
    Trigger image sync for a specific client.

    Runs in background to avoid timeout issues.
    """
    client_id = require_canonical_client_id(client_id)
    request = SyncTriggerRequest(client_id=client_id, force_full_sync=force_full_sync)
    return await trigger_sync(request, background_tasks)


@router.get("/status/{client_id}")
async def get_sync_status(client_id: str) -> Dict[str, Any]:
    """
    Get image sync statistics for a client.

    Returns processing stats, recent files, and sync history.
    Falls back to Vertex AI count if Firestore stats show 0.
    """
    client_id = require_canonical_client_id(client_id)
    try:
        state_manager = _get_state_manager()

        # Try to get stats, but handle the case where no data exists yet
        try:
            stats = state_manager.get_processing_stats(client_id)
        except Exception as stats_error:
            logger.warning(f"Could not get processing stats for {client_id}: {stats_error}")
            stats = {"total_processed": 0, "indexed": 0, "skipped": 0}

        try:
            history = state_manager.get_folder_sync_history(client_id)
        except Exception as history_error:
            logger.warning(f"Could not get sync history for {client_id}: {history_error}")
            history = []

        # VERTEX AI FALLBACK: If Firestore shows 0 indexed, check Vertex AI directly
        # This handles cases where images exist in Vertex AI but Firestore records are missing
        indexed_count = stats.get("indexed", 0)
        vertex_count = 0
        stats_source = "firestore"

        if indexed_count == 0:
            try:
                vertex = _get_vertex_ingestion()
                vertex_images = vertex.list_client_images(client_id, page_size=500)
                vertex_count = len(vertex_images)
                if vertex_count > 0:
                    logger.info(f"Vertex AI fallback: Found {vertex_count} images for {client_id} (Firestore showed 0)")
                    indexed_count = vertex_count
                    stats_source = "vertex_ai_fallback"
            except Exception as vertex_error:
                logger.warning(f"Vertex AI fallback failed for {client_id}: {vertex_error}")

        # Flatten stats for UI compatibility
        return {
            "client_id": client_id,
            "total_indexed": indexed_count,
            "skipped": stats.get("skipped", 0),
            "errors": 0,
            "last_sync_time": history[0].get("last_sync") if history else None,
            "statistics": stats,
            "sync_history": history,
            "stats_source": stats_source,
            "vertex_count": vertex_count if vertex_count > 0 else None
        }

    except Exception as e:
        logger.error(f"Failed to get sync status for {client_id}: {e}")
        # Return empty stats instead of failing
        return {
            "client_id": client_id,
            "total_indexed": 0,
            "skipped": 0,
            "errors": 0,
            "last_sync_time": None,
            "statistics": {},
            "sync_history": [],
            "error": str(e)
        }


@router.get("/folders/{client_id}")
async def get_client_folders(client_id: str) -> Dict[str, Any]:
    """
    Get configured Drive folders for a client.

    Returns list of folders with their sync status.
    """
    client_id = require_canonical_client_id(client_id)
    folder_mappings = _get_folder_mappings()

    if client_id not in folder_mappings:
        return {
            "client_id": client_id,
            "folders": [],
            "message": "No folders configured for this client"
        }

    state_manager = _get_state_manager()
    folders = []

    for mapping in folder_mappings[client_id]:
        # Get sync status for this folder
        last_sync = state_manager.get_last_sync_time(client_id, mapping.folder_id)

        folders.append({
            "folder_id": mapping.folder_id,
            "folder_name": mapping.folder_name,
            "folder_type": mapping.folder_type,
            "enabled": mapping.enabled,
            "last_sync": last_sync.isoformat() if last_sync else None
        })

    return {
        "client_id": client_id,
        "folders": folders
    }


@router.put("/folders/{client_id}")
async def update_client_folders(
    client_id: str,
    config: FolderConfigUpdate
) -> Dict[str, Any]:
    """
    Update Drive folder configuration for a client.

    Note: Changes are saved to folder_mappings.yaml.
    """
    client_id = require_canonical_client_id(client_id)
    global _folder_mappings
    settings_mod = _import_local("config.settings")
    ClientFolderMapping = settings_mod.ClientFolderMapping
    save_folder_mappings = settings_mod.save_folder_mappings
    load_folder_mappings = settings_mod.load_folder_mappings

    # Reload current mappings
    folder_mappings = load_folder_mappings()

    # Deduplicate folders by folder_id (keep first occurrence)
    seen_folder_ids = set()
    unique_folders = []
    for f in config.folders:
        if f.folder_id not in seen_folder_ids:
            seen_folder_ids.add(f.folder_id)
            unique_folders.append(f)

    # Update client's folders
    new_mappings = [
        ClientFolderMapping(
            client_id=client_id,
            folder_id=f.folder_id,
            folder_name=f.folder_name,
            folder_type="client",
            enabled=f.enabled
        )
        for f in unique_folders
    ]

    # Preserve shared folders if they exist
    existing = folder_mappings.get(client_id, [])
    shared_folders = [m for m in existing if m.folder_type == "shared"]
    folder_mappings[client_id] = new_mappings + shared_folders

    # Save to YAML
    success = save_folder_mappings(folder_mappings)

    if success:
        # Reset cached mappings
        _folder_mappings = None
        return {
            "status": "success",
            "client_id": client_id,
            "folders_updated": len(config.folders)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to save folder configuration")


@router.get("/thumbnail/{file_id}")
async def get_thumbnail(file_id: str):
    """
    Proxy endpoint to serve thumbnails for private Drive files.
    Uses the service account to fetch the image.
    """
    try:
        drive_client = _get_drive_client()

        # Check metadata first to get mime type + thumbnailLink
        mime_type = "image/jpeg"
        thumbnail_url = None
        try:
            metadata = drive_client.get_file_metadata(file_id)
            mime_type = metadata.get("mimeType", "image/jpeg")
            thumbnail_url = metadata.get("thumbnailLink")
        except Exception:
            pass

        # Prefer thumbnailLink to avoid downloading full-size image
        if thumbnail_url:
            try:
                from google.auth.transport.requests import Request as GoogleAuthRequest

                creds = drive_client.creds
                if creds and (not creds.valid or creds.expired):
                    creds.refresh(GoogleAuthRequest())

                headers = {}
                if creds and getattr(creds, "token", None):
                    headers["Authorization"] = f"Bearer {creds.token}"

                request = urllib.request.Request(thumbnail_url, headers=headers)
                with urllib.request.urlopen(request, timeout=8) as resp:
                    thumb_bytes = resp.read()
                    content_type = resp.headers.get("Content-Type") or mime_type
                    if thumb_bytes:
                        return Response(content=thumb_bytes, media_type=content_type)
            except Exception as e:
                logger.warning(f"ThumbnailLink fetch failed for {file_id}: {e}")

        # Fallback: download full image bytes (slower)
        image_bytes = drive_client.download_image_bytes(file_id)
        return Response(content=image_bytes, media_type=mime_type)
        
    except Exception as e:
        logger.error(f"Failed to fetch thumbnail for {file_id}: {e}")
        # Return a 1x1 transparent pixel or 404
        raise HTTPException(status_code=404, detail="Thumbnail not found")


@router.get("/recent/{client_id}")
async def get_recent_images(
    client_id: str,
    limit: int = Query(20, le=100, description="Maximum images to return")
) -> Dict[str, Any]:
    """
    Get recently indexed images for a client.

    Returns image metadata including thumbnails for UI preview.
    """
    client_id = require_canonical_client_id(client_id)
    try:
        vertex_ingestion_mod = _import_local("core.vertex_ingestion")
        settings_mod = _import_local("config.settings")

        ImageVertexIngestion = vertex_ingestion_mod.ImageVertexIngestion
        get_pipeline_config = settings_mod.get_pipeline_config

        config = get_pipeline_config()
        vertex = ImageVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )

        images = vertex.list_client_images(client_id, page_size=limit)

        # Post-process to use proxy thumbnails
        for img in images:
            file_id = _extract_drive_file_id(
                img.get("drive_link", ""),
                img.get("thumbnail_link", ""),
                img.get("source", ""),
                img.get("doc_id", "")
            )
            if file_id:
                img["thumbnail_link"] = f"/api/images/thumbnail/{file_id}"

        return {
            "client_id": client_id,
            "total": len(images),
            "images": images
        }

    except Exception as e:
        logger.error(f"Failed to get recent images for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log/{client_id}")
async def get_processing_log(
    client_id: str,
    limit: int = Query(100, le=500, description="Maximum records to return"),
    status: Optional[str] = Query(None, description="Filter by status: 'indexed' or 'skipped'")
) -> Dict[str, Any]:
    """
    Get detailed processing log for a client's images.

    Shows status (indexed/skipped), skip reasons, metadata for each processed image.
    """
    client_id = require_canonical_client_id(client_id)
    try:
        state_manager = _get_state_manager()
        log = state_manager.get_processing_log(client_id, limit=limit, status_filter=status)

        # Calculate summary
        indexed_count = sum(1 for item in log if item["status"] == "indexed")
        skipped_count = sum(1 for item in log if item["status"] == "skipped")

        # Group skip reasons
        skip_reasons = {}
        for item in log:
            if item["status"] == "skipped" and item.get("skip_reason"):
                reason = item["skip_reason"]
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        return {
            "client_id": client_id,
            "total": len(log),
            "indexed": indexed_count,
            "skipped": skipped_count,
            "skip_reasons": skip_reasons,
            "log": log
        }

    except Exception as e:
        logger.error(f"Failed to get processing log for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clear/{client_id}")
async def clear_client_state(client_id: str) -> Dict[str, Any]:
    """
    Clear all sync state for a client (for full resync).

    Does NOT delete indexed images from Vertex AI, only clears tracking state.
    """
    client_id = require_canonical_client_id(client_id)
    try:
        state_manager = _get_state_manager()
        deleted = state_manager.clear_client_state(client_id)

        return {
            "status": "success",
            "client_id": client_id,
            "records_cleared": deleted,
            "message": "State cleared. Next sync will reprocess all images."
        }

    except Exception as e:
        logger.error(f"Failed to clear state for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{client_id}")
async def delete_client_images(
    client_id: str,
    clear_state: bool = Query(True, description="Also clear Firestore state")
) -> Dict[str, Any]:
    """
    Delete ALL indexed images for a client from Vertex AI.

    This permanently removes all image documents from the search index.
    Use with caution - this action cannot be undone.

    - **client_id**: Client identifier
    - **clear_state**: If True, also clears Firestore tracking state (default: True)
    """
    client_id = require_canonical_client_id(client_id)
    try:
        vertex_ingestion_mod = _import_local("core.vertex_ingestion")
        settings_mod = _import_local("config.settings")

        ImageVertexIngestion = vertex_ingestion_mod.ImageVertexIngestion
        get_pipeline_config = settings_mod.get_pipeline_config

        config = get_pipeline_config()
        vertex = ImageVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )

        # Delete from Vertex AI
        result = vertex.delete_client_images(client_id)

        # Optionally clear Firestore state
        state_cleared = 0
        if clear_state:
            state_manager = _get_state_manager()
            state_cleared = state_manager.clear_client_state(client_id)

        return {
            "status": "success",
            "client_id": client_id,
            "vertex_deleted": result["deleted"],
            "vertex_failed": result["failed"],
            "state_records_cleared": state_cleared,
            "message": f"Deleted {result['deleted']} images from Vertex AI"
        }

    except Exception as e:
        logger.error(f"Failed to delete images for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete/{client_id}/{doc_id}")
async def delete_single_image(
    client_id: str,
    doc_id: str
) -> Dict[str, Any]:
    """
    Delete a single image document from Vertex AI.

    - **client_id**: Client identifier (for validation)
    - **doc_id**: Document ID to delete (e.g., img_buca-di-beppo_1ABC123)
    """
    client_id = require_canonical_client_id(client_id)
    try:
        vertex_ingestion_mod = _import_local("core.vertex_ingestion")
        settings_mod = _import_local("config.settings")

        ImageVertexIngestion = vertex_ingestion_mod.ImageVertexIngestion
        get_pipeline_config = settings_mod.get_pipeline_config

        # Validate doc_id belongs to client
        if not doc_id.startswith(f"img_{client_id}_"):
            raise HTTPException(
                status_code=400,
                detail=f"Document {doc_id} does not belong to client {client_id}"
            )

        config = get_pipeline_config()
        vertex = ImageVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )

        success = vertex.delete_document(doc_id)

        if success:
            return {
                "status": "success",
                "client_id": client_id,
                "doc_id": doc_id,
                "message": "Document deleted successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check for image repository pipeline.

    Verifies configuration and service connectivity.
    """
    settings_mod = _import_local("config.settings")
    get_pipeline_config = settings_mod.get_pipeline_config

    config = get_pipeline_config()

    # Extract service account email for UI instructions
    service_account_email = None
    if config.drive.service_account_json:
        try:
            import json
            sa_data = json.loads(config.drive.service_account_json)
            service_account_email = sa_data.get("client_email")
        except Exception:
            pass

    # Check OAuth configuration
    oauth_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    oauth_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    oauth_configured = bool(oauth_client_id and oauth_client_secret)

    result = {
        "status": "healthy",
        "gemini_configured": bool(config.vision.api_key),
        "drive_configured": bool(config.drive.service_account_json),
        "service_account_email": service_account_email,
        "oauth_configured": oauth_configured,
        "google_oauth_client_id": oauth_client_id[:20] + "..." if oauth_client_id and len(oauth_client_id) > 20 else oauth_client_id,
        "gcp_project": config.gcp_project_id,
        "vertex_data_store": config.vertex_data_store_id
    }

    # Check folder mappings
    try:
        mappings = _get_folder_mappings()
        client_count = sum(1 for k in mappings if not k.startswith('_'))
        result["clients_configured"] = client_count
    except Exception as e:
        result["folder_mappings_error"] = str(e)

    # Determine overall status
    warnings = []
    if not result["gemini_configured"]:
        warnings.append("GEMINI_API_KEY not configured")
    if not oauth_configured:
        warnings.append("Google OAuth not configured (GOOGLE_OAUTH_CLIENT_ID and/or GOOGLE_OAUTH_CLIENT_SECRET missing)")

    if warnings:
        result["status"] = "degraded"
        result["warnings"] = warnings

    return result


@router.get("/oauth/config")
async def get_oauth_config() -> Dict[str, Any]:
    """
    Get OAuth configuration status for the UI.

    Returns whether OAuth is configured and how to set it up if not.
    This endpoint is used by the UI to determine whether to show
    the "Connect Google Drive" button or an informational message.
    """
    oauth_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    oauth_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    oauth_redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8003/api/images/oauth/callback")

    is_configured = bool(oauth_client_id and oauth_client_secret)

    result = {
        "configured": is_configured,
        "redirect_uri": oauth_redirect_uri
    }

    if not is_configured:
        missing = []
        if not oauth_client_id:
            missing.append("GOOGLE_OAUTH_CLIENT_ID")
        if not oauth_client_secret:
            missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
        result["missing_env_vars"] = missing
        result["setup_instructions"] = (
            "To enable user Google Drive folder sharing, configure the following environment variables:\n"
            "1. GOOGLE_OAUTH_CLIENT_ID - Your Google Cloud OAuth 2.0 Client ID\n"
            "2. GOOGLE_OAUTH_CLIENT_SECRET - Your Google Cloud OAuth 2.0 Client Secret\n"
            "3. GOOGLE_OAUTH_REDIRECT_URI - (Optional) Defaults to http://localhost:8003/api/images/oauth/callback\n\n"
            "Create OAuth credentials at: https://console.cloud.google.com/apis/credentials"
        )

    return result


@router.get("/search/{client_id}")
async def search_images(
    client_id: str,
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, le=50, description="Maximum results")
) -> Dict[str, Any]:
    """
    Search indexed images for a client using semantic search.

    Returns images matching the query with thumbnails and metadata.
    """
    client_id = require_canonical_client_id(client_id)
    try:
        from google.cloud import discoveryengine_v1 as discoveryengine
        from google.api_core.client_options import ClientOptions
        settings_mod = _import_local("config.settings")
        get_pipeline_config = settings_mod.get_pipeline_config

        config = get_pipeline_config()

        # Initialize search client
        client_options = ClientOptions(
            api_endpoint=f"{config.gcp_location}-discoveryengine.googleapis.com"
        )
        search_client = discoveryengine.SearchServiceClient(
            client_options=client_options
        )

        # Build serving config path
        serving_config = search_client.serving_config_path(
            project=config.gcp_project_id,
            location=config.gcp_location,
            data_store=config.vertex_data_store_id,
            serving_config="default_search",
        )

        # Build filter for client and visual assets
        filter_str = f'client_id: ANY("{client_id}") AND category: ANY("visual_asset")'

        # Execute search
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=q,
            page_size=limit,
            filter=filter_str,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
        )

        response = search_client.search(request)

        # Parse results
        images = []
        for result in response.results:
            data = dict(result.document.struct_data)

            drive_link = data.get("drive_link", "")
            thumbnail_link = data.get("thumbnail_link", "")
            file_id = _extract_drive_file_id(
                drive_link,
                thumbnail_link,
                data.get("source", ""),
                result.document.id
            )
            if file_id:
                thumbnail_link = f"/api/images/thumbnail/{file_id}"

            images.append({
                "doc_id": result.document.id,
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "mood": data.get("mood", ""),
                "setting": data.get("setting", ""),
                "visual_tags": data.get("visual_tags_str", "").split(", ") if data.get("visual_tags_str") else [],
                "dominant_colors": data.get("dominant_colors_str", "").split(", ") if data.get("dominant_colors_str") else [],
                "drive_link": drive_link,
                "thumbnail_link": thumbnail_link,
                "marketing_use_case": data.get("marketing_use_case", ""),
                "text_chunk": data.get("text_chunk", "")[:300] + "..." if len(data.get("text_chunk", "")) > 300 else data.get("text_chunk", ""),
            })

        return {
            "client_id": client_id,
            "query": q,
            "total": len(images),
            "images": images
        }

    except Exception as e:
        logger.error(f"Image search failed for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients")
async def list_configured_clients() -> Dict[str, Any]:
    """
    List all clients with configured image folders.

    Returns client IDs, folder details, and enabled status.
    """
    folder_mappings = _get_folder_mappings()

    clients = []
    for client_id, mappings in folder_mappings.items():
        if client_id.startswith('_'):
            continue

        # Build folder list for UI
        folders = [
            {
                "folder_id": m.folder_id,
                "name": m.folder_name,
                "enabled": m.enabled,
                "type": m.folder_type
            }
            for m in mappings
        ]

        # Client is enabled if it has at least one enabled folder
        enabled = any(m.enabled for m in mappings)

        clients.append({
            "client_id": client_id,
            "enabled": enabled,
            "folders": folders,
            "folder_count": len(folders),
            "has_shared_folders": any(m.folder_type == "shared" for m in mappings)
        })

    return {
        "total_clients": len(clients),
        "clients": clients
    }


# =============================================================================
# Google OAuth Endpoints for User Drive Access
# =============================================================================

class OAuthAuthorizeRequest(BaseModel):
    """Request to start OAuth flow."""
    user_id: str = Field(..., description="User identifier (email or unique ID)")
    redirect_after: Optional[str] = Field(None, description="URL to redirect after OAuth completes")


class OAuthAuthorizeResponse(BaseModel):
    """Response with OAuth authorization URL."""
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""
    code: str = Field(..., description="Authorization code from Google")
    state: str = Field(..., description="State parameter for CSRF protection")


class OAuthStatusResponse(BaseModel):
    """User OAuth status."""
    is_authorized: bool
    expires_at: Optional[str] = None
    scopes: List[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    token_source: Optional[str] = None


class ClaimClerkTokenRequest(BaseModel):
    """Request to claim Google OAuth token from Clerk."""
    clerk_user_id: str = Field(..., description="Clerk user ID (user_2abc...)")
    user_id: str = Field(..., description="User identifier for storage (email)")


class ClaimClerkTokenResponse(BaseModel):
    """Response from claiming Clerk token."""
    status: str
    scopes: List[str] = []
    token_source: Optional[str] = None
    missing_scopes: List[str] = []
    message: Optional[str] = None


_oauth_manager = None
_clerk_oauth_client = None


def _get_clerk_oauth_client():
    """Lazy initialization of Clerk OAuth client."""
    global _clerk_oauth_client
    if _clerk_oauth_client is None:
        clerk_oauth_mod = _import_local("core.clerk_oauth_client")
        ClerkOAuthClient = clerk_oauth_mod.ClerkOAuthClient
        try:
            _clerk_oauth_client = ClerkOAuthClient()
        except ValueError as e:
            logger.warning(f"Clerk OAuth client not available: {e}")
            return None
    return _clerk_oauth_client


def _get_oauth_manager():
    """Lazy initialization of OAuth token manager."""
    global _oauth_manager
    if _oauth_manager is None:
        oauth_manager_mod = _import_local("core.oauth_manager")
        settings_mod = _import_local("config.settings")

        OAuthTokenManager = oauth_manager_mod.OAuthTokenManager
        get_pipeline_config = settings_mod.get_pipeline_config
        config = get_pipeline_config()

        # Get OAuth credentials from environment
        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:8003/api/images/oauth/callback")

        if not client_id or not client_secret:
            raise ValueError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be configured")

        _oauth_manager = OAuthTokenManager(
            project_id=config.gcp_project_id,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        )
    return _oauth_manager


@router.post("/oauth/authorize", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(request: OAuthAuthorizeRequest):
    """
    Start Google OAuth flow for user Drive access.

    Returns an authorization URL that the user should be redirected to.
    The user will grant access to their Drive folders, and Google will
    redirect back to the callback endpoint with an authorization code.
    """
    # Check if OAuth is configured before attempting to get manager
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning("OAuth authorize called but GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET not configured")
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Please contact your administrator to set up GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET."
        )

    try:
        oauth_manager = _get_oauth_manager()

        # Include redirect_after in state if provided (for post-auth redirect)
        state = request.user_id
        if request.redirect_after:
            import base64
            state_data = f"{request.user_id}|{request.redirect_after}"
            state = base64.urlsafe_b64encode(state_data.encode()).decode()

        authorization_url, returned_state = oauth_manager.create_authorization_url(
            user_id=request.user_id,
            state=state
        )

        return OAuthAuthorizeResponse(
            authorization_url=authorization_url,
            state=returned_state
        )

    except ValueError as e:
        logger.error(f"OAuth configuration error: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"OAuth configuration error: {str(e)}. Please check your environment variables."
        )
    except Exception as e:
        logger.error(f"Failed to create OAuth authorization URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate OAuth flow")


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State parameter"),
    error: Optional[str] = Query(None, description="Error from OAuth provider")
):
    """
    Handle OAuth callback from Google.

    Exchanges the authorization code for tokens and stores them encrypted.
    Redirects back to the UI with success/error status.
    """
    import base64
    from fastapi.responses import RedirectResponse

    if error:
        logger.error(f"OAuth callback received error: {error}")
        return RedirectResponse(
            url=f"/ui/image-repository.html?oauth_error={error}",
            status_code=302
        )

    try:
        oauth_manager = _get_oauth_manager()

        # Decode state to get user_id and optional redirect URL
        redirect_after = "/ui/image-repository.html"
        try:
            decoded_state = base64.urlsafe_b64decode(state.encode()).decode()
            if "|" in decoded_state:
                user_id, redirect_after = decoded_state.split("|", 1)
            else:
                user_id = decoded_state
        except Exception:
            # State is just the user_id (no encoding)
            user_id = state

        # Exchange code for tokens
        result = oauth_manager.exchange_code_for_tokens(code=code, user_id=user_id)

        logger.info(f"OAuth tokens stored for user {user_id}")

        # Redirect back to UI with success
        redirect_url = f"{redirect_after}?oauth_success=true&user_id={user_id}"
        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return RedirectResponse(
            url=f"/ui/image-repository.html?oauth_error=token_exchange_failed",
            status_code=302
        )


@router.get("/oauth/status/{user_id}", response_model=OAuthStatusResponse)
async def oauth_status(user_id: str):
    """
    Check OAuth authorization status for a user.

    Returns whether the user has valid credentials and when they expire.
    """
    try:
        oauth_manager = _get_oauth_manager()
        status = oauth_manager.get_auth_status(user_id)

        return OAuthStatusResponse(
            is_authorized=status["is_authorized"],
            expires_at=status.get("expires_at"),
            scopes=status.get("scopes", []),
            created_at=status.get("created_at"),
            updated_at=status.get("updated_at"),
            token_source=status.get("token_source")
        )

    except ValueError as e:
        # OAuth not configured - return unauthorized status
        return OAuthStatusResponse(
            is_authorized=False,
            scopes=[]
        )
    except Exception as e:
        logger.error(f"Failed to get OAuth status for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to check OAuth status")


@router.post("/oauth/claim-clerk-token", response_model=ClaimClerkTokenResponse)
async def claim_clerk_google_token(request: ClaimClerkTokenRequest):
    """
    Claim Google OAuth token from Clerk and store for Drive access.

    For users who signed in via Google OAuth through Clerk, this endpoint
    retrieves their Google access token from Clerk and stores it for use
    with Google Drive operations. This eliminates the need for a second
    OAuth popup for Google Drive access.

    Args:
        clerk_user_id: Clerk user ID (user_2abc...)
        user_id: User identifier for storage (typically email)

    Returns:
        - status: "authorized" if token claimed successfully
        - status: "no_google_oauth" if user didn't sign in with Google
        - status: "missing_scopes" if token lacks drive.readonly scope
    """
    try:
        clerk_client = _get_clerk_oauth_client()
        if not clerk_client:
            return ClaimClerkTokenResponse(
                status="clerk_not_configured",
                message="Clerk OAuth integration is not configured"
            )

        # Get Google OAuth token from Clerk
        token_data = await clerk_client.get_google_oauth_token(request.clerk_user_id)

        if not token_data:
            return ClaimClerkTokenResponse(
                status="no_google_oauth",
                message="No Google OAuth connection found. User may not have signed in with Google."
            )

        # Check for required scopes
        if not clerk_client.has_required_scopes(token_data):
            missing = clerk_client.get_missing_scopes(token_data)
            return ClaimClerkTokenResponse(
                status="missing_scopes",
                scopes=token_data.get("scopes", []),
                missing_scopes=missing,
                message="Google OAuth token is missing required Drive scopes. Please grant Drive access."
            )

        # Store the token for Drive operations
        oauth_manager = _get_oauth_manager()
        result = oauth_manager.store_external_token(
            user_id=request.user_id,
            access_token=token_data["token"],
            scopes=token_data.get("scopes", []),
            token_source="clerk_google"
        )

        logger.info(f"Claimed Clerk Google token for user {request.user_id}")

        return ClaimClerkTokenResponse(
            status="authorized",
            scopes=result.get("scopes", []),
            token_source="clerk_google",
            message="Google Drive connected via Clerk sign-in"
        )

    except Exception as e:
        logger.error(f"Failed to claim Clerk token for {request.clerk_user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to claim token: {str(e)}")


@router.post("/oauth/revoke/{user_id}")
async def oauth_revoke(user_id: str) -> Dict[str, Any]:
    """
    Revoke OAuth tokens for a user.

    Deletes stored tokens and optionally revokes them with Google.
    """
    try:
        oauth_manager = _get_oauth_manager()
        result = oauth_manager.revoke_tokens(user_id)

        return {
            "status": "success",
            "user_id": user_id,
            "message": "OAuth tokens revoked"
        }

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to revoke OAuth tokens for {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke tokens")


@router.get("/oauth/user-folders/{user_id}")
async def list_user_drive_folders(
    user_id: str,
    parent_id: Optional[str] = Query(None, description="Parent folder ID (root if not specified)")
) -> Dict[str, Any]:
    """
    List Drive folders accessible to the user via their OAuth credentials.

    This allows users to browse their own Drive and select folders to share
    with the image repository pipeline.
    """
    try:
        oauth_manager = _get_oauth_manager()
        credentials = oauth_manager.get_credentials(user_id)

        if not credentials:
            raise HTTPException(
                status_code=401,
                detail="User not authorized. Please connect your Google account first."
            )

        # Use the user's credentials to list their Drive folders
        from googleapiclient.discovery import build

        service = build('drive', 'v3', credentials=credentials)

        # Build query for folders only
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        else:
            query += " and 'root' in parents"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, mimeType, parents, webViewLink)",
            orderBy="name"
        ).execute()

        folders = results.get('files', [])

        return {
            "user_id": user_id,
            "parent_id": parent_id or "root",
            "folders": [
                {
                    "folder_id": f["id"],
                    "name": f["name"],
                    "web_link": f.get("webViewLink", f"https://drive.google.com/drive/folders/{f['id']}")
                }
                for f in folders
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list user Drive folders: {e}")
        raise HTTPException(status_code=500, detail=str(e))
