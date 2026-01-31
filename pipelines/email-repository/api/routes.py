"""
FastAPI routes for Email Repository Pipeline.

Provides endpoints for:
- Triggering email sync (manual and automated)
- Searching indexed emails
- Viewing sync status and statistics
- Managing email accounts
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/emails", tags=["Email Repository"])


# =============================================================================
# Pydantic Models
# =============================================================================

class SyncTriggerRequest(BaseModel):
    """Request body for triggering email sync."""
    account_email: Optional[str] = Field(None, description="Sync specific account only")
    force_full_sync: bool = Field(False, description="Ignore incremental sync, reprocess all")


class SyncStatusResponse(BaseModel):
    """Response for sync status endpoint."""
    status: str
    message: str
    stats: Optional[Dict[str, Any]] = None


class EmailSearchRequest(BaseModel):
    """Request body for email search."""
    query: str = Field(..., description="Natural language search query")
    product_category: Optional[str] = None
    email_type: Optional[str] = None
    year: Optional[str] = None
    month: Optional[str] = None
    brand: Optional[str] = None
    limit: int = Field(20, le=50)


class EmailSearchResponse(BaseModel):
    """Response for email search."""
    success: bool
    query: str
    total: int
    emails: List[Dict[str, Any]]


# =============================================================================
# State Management (lazy initialization)
# =============================================================================

_orchestrator = None
_email_accounts = None
_state_manager = None
_vertex_ingestion = None


def _reset_orchestrator():
    """Reset the cached orchestrator."""
    global _orchestrator
    _orchestrator = None


def _get_config():
    """Get pipeline configuration."""
    from config.settings import get_pipeline_config
    return get_pipeline_config()


def _get_orchestrator():
    """Lazy initialization of orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        from core.gmail_client import GmailClient
        from core.screenshot_service import EmailScreenshotService
        from core.drive_uploader import DriveUploader
        from core.categorizer import EmailCategorizer
        from core.state_manager import EmailSyncStateManager
        from core.vertex_ingestion import EmailVertexIngestion
        from core.sync_orchestrator import EmailSyncOrchestrator
        from config.settings import get_pipeline_config

        config = get_pipeline_config()

        # Validate required configuration
        if not config.gmail.service_account_json:
            raise ValueError("Gmail service account not configured")
        if not config.gmail.delegated_email:
            raise ValueError("Gmail delegated email not configured")
        if not config.vision.api_key:
            raise ValueError("Gemini API key not configured")

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

        _orchestrator = EmailSyncOrchestrator(
            gmail_client=gmail_client,
            screenshot_service=screenshot_service,
            drive_uploader=drive_uploader,
            categorizer=categorizer,
            state_manager=state_manager,
            vertex_ingestion=vertex_ingestion,
            batch_size=config.sync.batch_size,
            max_emails_per_sync=config.sync.max_emails_per_sync
        )

    return _orchestrator


def _get_email_accounts():
    """Lazy initialization of email accounts."""
    global _email_accounts
    if _email_accounts is None:
        from config.settings import load_email_accounts
        _email_accounts = load_email_accounts()
    return _email_accounts


def _get_state_manager():
    """Lazy initialization of state manager."""
    global _state_manager
    if _state_manager is None:
        from core.state_manager import EmailSyncStateManager
        from config.settings import get_pipeline_config
        config = get_pipeline_config()
        _state_manager = EmailSyncStateManager(
            project_id=config.gcp_project_id,
            collection_prefix=config.firestore_collection
        )
    return _state_manager


def _get_vertex_ingestion():
    """Lazy initialization of Vertex ingestion."""
    global _vertex_ingestion
    if _vertex_ingestion is None:
        from core.vertex_ingestion import EmailVertexIngestion
        from config.settings import get_pipeline_config
        config = get_pipeline_config()
        _vertex_ingestion = EmailVertexIngestion(
            project_id=config.gcp_project_id,
            location=config.gcp_location,
            data_store_id=config.vertex_data_store_id
        )
    return _vertex_ingestion


# =============================================================================
# Background Task Runner
# =============================================================================

async def _run_sync_task(
    account_email: Optional[str] = None,
    force_full_sync: bool = False
):
    """Background task to run email sync."""
    try:
        orchestrator = _get_orchestrator()
        accounts = _get_email_accounts()

        if account_email:
            # Find specific account
            account_config = next(
                (a for a in accounts if a.account_email == account_email),
                None
            )
            if not account_config:
                logger.error(f"Account {account_email} not found")
                return

            result = await orchestrator.sync_account(
                account_email=account_email,
                force_full_sync=force_full_sync,
                date_range_start=datetime.fromisoformat(account_config.date_range_start)
                    if account_config.date_range_start else None,
                sender_blocklist=account_config.sender_blocklist,
                subject_blocklist=account_config.subject_blocklist
            )
            logger.info(f"Sync complete for {account_email}: {result.status}")
        else:
            # Sync all accounts
            results = await orchestrator.sync_all_accounts([
                {
                    'account_email': a.account_email,
                    'enabled': a.enabled,
                    'date_range_start': a.date_range_start,
                    'sender_blocklist': a.sender_blocklist,
                    'subject_blocklist': a.subject_blocklist
                }
                for a in accounts
            ])
            logger.info(f"Sync complete for {len(results)} accounts")

    except Exception as e:
        logger.error(f"Background sync failed: {e}", exc_info=True)


# =============================================================================
# API Endpoints - Sync Operations
# =============================================================================

@router.post("/sync", response_model=SyncStatusResponse)
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger email sync pipeline.

    Can sync all configured accounts or a specific account. Runs in background.

    - **account_email**: Optional - sync only this account
    - **force_full_sync**: If True, reprocess all emails (ignore incremental sync)
    """
    try:
        accounts = _get_email_accounts()

        if request.account_email:
            # Validate account exists
            account = next(
                (a for a in accounts if a.account_email == request.account_email),
                None
            )
            if not account:
                raise HTTPException(
                    status_code=404,
                    detail=f"Account '{request.account_email}' not found in configuration"
                )
            account_count = 1
        else:
            account_count = sum(1 for a in accounts if a.enabled)

        # Run sync in background
        background_tasks.add_task(
            _run_sync_task,
            request.account_email,
            request.force_full_sync
        )

        return SyncStatusResponse(
            status="started",
            message=f"Email sync started for {account_count} account(s). Running in background.",
            stats={
                "account_email": request.account_email,
                "force_full_sync": request.force_full_sync
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to trigger sync: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{account_email}")
async def get_sync_status(account_email: str) -> Dict[str, Any]:
    """
    Get email sync statistics for an account.

    Returns processing stats, recent emails, and sync history.
    """
    try:
        state_manager = _get_state_manager()

        stats = state_manager.get_processing_stats(account_email)
        history = state_manager.get_sync_history(account_email)

        return {
            "account_email": account_email,
            "total_indexed": stats.get("indexed", 0),
            "total_skipped": stats.get("skipped", 0),
            "by_category": stats.get("by_category", {}),
            "by_email_type": stats.get("by_email_type", {}),
            "by_month": stats.get("by_month", {}),
            "recent_emails": stats.get("recent_emails", []),
            "sync_history": history
        }

    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        return {
            "account_email": account_email,
            "total_indexed": 0,
            "total_skipped": 0,
            "error": str(e)
        }


# =============================================================================
# API Endpoints - Search & Query
# =============================================================================

@router.get("/search")
async def search_emails(
    q: str = Query(..., description="Search query"),
    product_category: Optional[str] = Query(None, description="Filter by category"),
    email_type: Optional[str] = Query(None, description="Filter by email type"),
    year: Optional[str] = Query(None, description="Filter by year"),
    month: Optional[str] = Query(None, description="Filter by month"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    limit: int = Query(20, le=50, description="Results limit")
) -> Dict[str, Any]:
    """
    Search indexed emails using semantic search.

    Supports natural language queries with optional filters.

    Example queries:
    - "fashion promotional emails from February 2025"
    - "food brand newsletter with hero images"
    - "sale announcements from Nike"
    """
    try:
        vertex = _get_vertex_ingestion()

        filters = {}
        if product_category:
            filters["product_category"] = product_category
        if email_type:
            filters["email_type"] = email_type
        if year:
            filters["year"] = year
        if month:
            filters["month"] = month.zfill(2) if month else None
        if brand:
            filters["brand"] = brand

        result = vertex.search_emails(
            query=q,
            filters=filters if filters else None,
            page_size=limit
        )

        return result

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/browse")
async def browse_emails(
    product_category: Optional[str] = Query(None),
    email_type: Optional[str] = Query(None),
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    limit: int = Query(50, le=100)
) -> Dict[str, Any]:
    """
    Browse emails with filters (no semantic search).

    For exploration and filtering without a specific query.
    """
    try:
        state_manager = _get_state_manager()

        # Build filter criteria
        if product_category:
            emails = state_manager.get_emails_by_category(product_category, limit=limit)
        elif year and month:
            start_date = datetime(int(year), int(month), 1)
            end_month = int(month) + 1 if int(month) < 12 else 1
            end_year = int(year) if int(month) < 12 else int(year) + 1
            end_date = datetime(end_year, end_month, 1)
            emails = state_manager.get_emails_by_date_range(
                start_date=start_date,
                end_date=end_date,
                category=product_category,
                limit=limit
            )
        else:
            emails = state_manager.get_processing_log(limit=limit, status_filter="indexed")

        # Add thumbnail links
        for email in emails:
            if email.get("drive_file_id"):
                email["thumbnail_link"] = f"https://drive.google.com/thumbnail?id={email['drive_file_id']}&sz=w200"

        return {
            "total": len(emails),
            "emails": emails,
            "filters": {
                "product_category": product_category,
                "email_type": email_type,
                "year": year,
                "month": month
            }
        }

    except Exception as e:
        logger.error(f"Browse failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# API Endpoints - Statistics
# =============================================================================

@router.get("/categories")
async def get_category_stats() -> Dict[str, Any]:
    """
    Get email count breakdown by category.
    """
    try:
        vertex = _get_vertex_ingestion()
        stats = vertex.get_category_stats()

        return {
            "categories": stats,
            "total": sum(stats.values())
        }

    except Exception as e:
        logger.error(f"Failed to get category stats: {e}")
        return {"categories": {}, "total": 0, "error": str(e)}


@router.get("/brands")
async def get_brand_list(limit: int = Query(50, le=200)) -> Dict[str, Any]:
    """
    Get list of brands with email counts.
    """
    try:
        state_manager = _get_state_manager()
        stats = state_manager.get_processing_stats()

        # Extract unique brands (would need to add brand tracking to state manager)
        # For now, return placeholder
        return {
            "brands": [],
            "total": 0,
            "message": "Brand tracking will be implemented in processing log"
        }

    except Exception as e:
        logger.error(f"Failed to get brands: {e}")
        return {"brands": [], "error": str(e)}


@router.get("/recent")
async def get_recent_emails(
    limit: int = Query(20, le=100)
) -> Dict[str, Any]:
    """
    Get recently processed emails.
    """
    try:
        state_manager = _get_state_manager()
        emails = state_manager.get_processing_log(limit=limit, status_filter="indexed")

        # Add thumbnail links
        for email in emails:
            if email.get("drive_file_id"):
                email["thumbnail_link"] = f"https://drive.google.com/thumbnail?id={email['drive_file_id']}&sz=w200"

        return {
            "total": len(emails),
            "emails": emails
        }

    except Exception as e:
        logger.error(f"Failed to get recent emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{email_id}")
async def get_email_details(email_id: str) -> Dict[str, Any]:
    """
    Get full details for a specific email.
    """
    try:
        state_manager = _get_state_manager()
        email = state_manager.get_processed_email(email_id)

        if not email:
            raise HTTPException(status_code=404, detail=f"Email {email_id} not found")

        # Add thumbnail link
        if email.get("drive_file_id"):
            email["thumbnail_link"] = f"https://drive.google.com/thumbnail?id={email['drive_file_id']}&sz=w200"
            email["full_screenshot_link"] = f"https://drive.google.com/uc?id={email['drive_file_id']}"

        return email

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get email {email_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# API Endpoints - Management
# =============================================================================

@router.delete("/clear/{account_email}")
async def clear_account_state(account_email: str) -> Dict[str, Any]:
    """
    Clear all sync state for an account (for full resync).

    Does NOT delete screenshots from Drive or documents from Vertex AI.
    """
    try:
        state_manager = _get_state_manager()
        deleted = state_manager.clear_account_state(account_email)

        return {
            "status": "success",
            "account_email": account_email,
            "records_cleared": deleted,
            "message": "State cleared. Next sync will reprocess all emails."
        }

    except Exception as e:
        logger.error(f"Failed to clear state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounts")
async def list_configured_accounts() -> Dict[str, Any]:
    """
    List all configured email accounts.
    """
    accounts = _get_email_accounts()

    return {
        "accounts": [
            {
                "account_email": a.account_email,
                "account_name": a.account_name,
                "enabled": a.enabled,
                "date_range_start": a.date_range_start
            }
            for a in accounts
        ],
        "total": len(accounts)
    }


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check for email repository pipeline.

    Verifies configuration and service connectivity.
    """
    from config.settings import get_pipeline_config

    config = get_pipeline_config()

    result = {
        "status": "healthy",
        "gmail_configured": bool(config.gmail.service_account_json and config.gmail.delegated_email),
        "gemini_configured": bool(config.vision.api_key),
        "drive_configured": bool(config.drive.service_account_json),
        "gcp_project": config.gcp_project_id,
        "vertex_data_store": config.vertex_data_store_id
    }

    # Check email accounts
    try:
        accounts = _get_email_accounts()
        result["accounts_configured"] = len(accounts)
    except Exception as e:
        result["accounts_error"] = str(e)

    # Determine overall status
    if not result["gmail_configured"]:
        result["status"] = "degraded"
        result["warning"] = "Gmail not configured (missing service account or delegated email)"
    elif not result["gemini_configured"]:
        result["status"] = "degraded"
        result["warning"] = "Gemini API key not configured"

    return result
