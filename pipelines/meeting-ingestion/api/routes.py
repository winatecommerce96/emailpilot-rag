from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import Optional, Dict, List
from fastapi.responses import RedirectResponse
from core.auth import get_calendar_auth_service
from core.scanner import CalendarScanner
from core.processor import SmartProcessor
from core.ingestion import MeetingIngester
from core.scheduler import get_scan_state_manager
from config.settings import settings

# Import from main app (RAG service) - app should be on sys.path when loaded via main.py
from app.client_id import normalize_client_id

router = APIRouter(prefix="/api/meeting", tags=["Meeting Intelligence"])
auth_service = get_calendar_auth_service()
scan_state = get_scan_state_manager()

@router.get("/auth")
def meeting_auth_start():
    """Start OAuth for Calendar Access."""
    if not auth_service.is_configured():
        raise HTTPException(status_code=503, detail="Calendar OAuth not configured")
    return {"auth_url": auth_service.get_auth_url()}

@router.get("/callback")
def meeting_auth_callback(code: str, state: Optional[str] = None):
    """Handle OAuth Callback."""
    try:
        result = auth_service.exchange_code(code)
        # Redirect back to UI with session
        return RedirectResponse(f"/ui/meeting-intelligence.html?meeting_session={result['session_id']}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Auth failed: {e}")

@router.get("/status")
def meeting_connection_status(session_id: Optional[str] = None):
    """Check if user has a valid calendar connection."""
    if not session_id:
        return {"connected": False, "message": "No session provided"}

    credentials = auth_service.get_credentials(session_id)
    if credentials:
        # Try to get email from stored data
        token_data = auth_service._load_credentials(session_id)
        email = token_data.get("email", "unknown") if token_data else "unknown"
        return {
            "connected": True,
            "email": email,
            "session_id": session_id
        }
    return {"connected": False, "message": "Session expired or invalid"}


@router.delete("/disconnect")
def meeting_disconnect(session_id: str):
    """Disconnect/revoke calendar access."""
    success = auth_service.disconnect_user(session_id)
    if success:
        return {"success": True, "message": "Disconnected successfully"}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/scan/{client_id}")
async def trigger_scan(
    client_id: str, 
    session_id: str, 
    background_tasks: BackgroundTasks,
    lookback_hours: int = 24,
    client_domain: Optional[str] = None
):
    """
    Trigger a manual scan for a specific client.
    """
    credentials = auth_service.get_credentials(session_id)
    if not credentials:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    normalized_client_id = normalize_client_id(client_id)
    
    # Run in background
    background_tasks.add_task(run_pipeline, credentials, normalized_client_id, lookback_hours, client_domain)
    
    return {
        "status": "scan_started", 
        "client_id": normalized_client_id,
        "config": {
            "lookback_hours": lookback_hours,
            "domain": client_domain or "auto-detect"
        }
    }

async def run_pipeline(credentials, client_id, lookback_hours=24, client_domain=None):
    """
    Orchestrates the Scan -> Process -> Ingest flow.
    """
    print(f"Starting meeting scan for {client_id} (Lookback: {lookback_hours}h, Domain: {client_domain})...")
    scanner = CalendarScanner(credentials)
    processor = SmartProcessor()
    ingester = MeetingIngester()
    
    # 1. Scan
    domains = [client_domain] if client_domain else None
    candidates = scanner.scan_past_meetings(lookback_hours=lookback_hours, allowed_domains=domains)
    
    print(f"Found {len(candidates)} candidate meetings.")
    
    for meeting in candidates:
        print(f"Processing meeting: {meeting.get('summary')}")
        
        # 2. Fetch Content
        transcript = scanner.get_transcript_content(meeting)
        if not transcript:
            print("No transcript found.")
            continue
            
        # 3. Smart Filter (Gemini)
        metadata = {
            "client_id": client_id,
            "date": meeting.get('start'),
            "summary": meeting.get('summary')
        }
        
        intel = await processor.process_transcript(transcript, metadata)
        
        if intel:
            print("High signal meeting detected. Ingesting...")
            # 4. Ingest
            ingester.ingest_meeting_intel(client_id, intel, metadata)
        else:
            print("Meeting filtered out (Low signal).")

    print(f"Scan complete for {client_id}")


# ============================================================================
# Initial & Scheduled Scan Endpoints
# ============================================================================

from pydantic import BaseModel

class InitialScanRequest(BaseModel):
    client_ids: List[str]
    force: bool = False  # Allow re-running the backfill

@router.post("/initial-scan")
async def trigger_initial_scan(
    session_id: str,
    request: InitialScanRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger initial 60-day scan for all clients assigned to a user.
    Called once when a user first connects their calendar, or manually via Backfill button.
    Set force=true to re-run even if already completed.
    """
    credentials = auth_service.get_credentials(session_id)
    if not credentials:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Check if initial scan already completed (skip check if force=true)
    state = scan_state.get_user_state(session_id)
    if state.get("initial_scan_completed") and not request.force:
        return {
            "status": "already_completed",
            "message": "Initial scan was already completed. Use force=true to re-run.",
            "completed_at": state.get("initial_scan_completed_at")
        }

    # Get user email
    token_data = auth_service._load_credentials(session_id)
    email = token_data.get("email", "unknown") if token_data else "unknown"

    # Normalize client IDs
    normalized_clients = [normalize_client_id(c) for c in request.client_ids]

    # Mark scan as started
    scan_state.mark_initial_scan_started(session_id, email, normalized_clients)

    # Run initial scan in background
    background_tasks.add_task(
        run_initial_scan,
        credentials,
        session_id,
        normalized_clients
    )

    return {
        "status": "initial_scan_started",
        "lookback_days": settings.INITIAL_SCAN_DAYS,
        "clients": normalized_clients,
        "message": f"Scanning {len(normalized_clients)} clients for the past {settings.INITIAL_SCAN_DAYS} days"
    }


@router.get("/scan-status")
def get_scan_status(session_id: str):
    """Get the current scan status for a user."""
    credentials = auth_service.get_credentials(session_id)
    if not credentials:
        raise HTTPException(status_code=401, detail="Invalid session")

    state = scan_state.get_user_state(session_id)
    return {
        "initial_scan_completed": state.get("initial_scan_completed", False),
        "initial_scan_started_at": state.get("initial_scan_started_at"),
        "initial_scan_completed_at": state.get("initial_scan_completed_at"),
        "last_scan_at": state.get("last_scan_at"),
        "clients_scanned": state.get("clients_scanned", []),
        "scan_results": state.get("scan_results", {})
    }


@router.post("/weekly-scan")
async def trigger_weekly_scan(
    background_tasks: BackgroundTasks,
    api_key: Optional[str] = None
):
    """
    Trigger weekly scan for all users due for a scan.
    Called by Cloud Scheduler or cron job.
    Requires internal API key for security.
    """
    import os
    expected_key = os.getenv("INTERNAL_SERVICE_KEY")
    if expected_key and api_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Get all users due for weekly scan
    due_users = scan_state.get_users_due_for_weekly_scan()

    if not due_users:
        return {"status": "no_users_due", "message": "No users due for weekly scan"}

    # Queue scans for each user
    users_queued = []
    for user in due_users:
        session_id = user["session_id"]
        credentials = auth_service.get_credentials(session_id)
        if credentials:
            client_ids = user.get("clients_scanned", [])
            if client_ids:
                background_tasks.add_task(
                    run_weekly_scan,
                    credentials,
                    session_id,
                    client_ids
                )
                users_queued.append({
                    "email": user.get("email"),
                    "clients": len(client_ids)
                })

    return {
        "status": "weekly_scans_queued",
        "users_queued": len(users_queued),
        "details": users_queued
    }


async def run_initial_scan(credentials, session_id: str, client_ids: List[str]):
    """
    Run the initial 60-day scan for all user's clients.
    """
    lookback_hours = settings.INITIAL_SCAN_DAYS * 24  # Convert days to hours
    print(f"🚀 Starting initial scan for {len(client_ids)} clients ({settings.INITIAL_SCAN_DAYS} days lookback)")

    scanner = CalendarScanner(credentials)
    processor = SmartProcessor()
    ingester = MeetingIngester()

    for client_id in client_ids:
        print(f"\n📅 Scanning for client: {client_id}")
        try:
            candidates = scanner.scan_past_meetings(lookback_hours=lookback_hours)
            print(f"   Found {len(candidates)} candidate meetings")

            meetings_processed = 0
            for meeting in candidates:
                transcript = scanner.get_transcript_content(meeting)
                if not transcript:
                    continue

                metadata = {
                    "client_id": client_id,
                    "date": meeting.get('start'),
                    "summary": meeting.get('summary')
                }

                intel = await processor.process_transcript(transcript, metadata)
                if intel:
                    ingester.ingest_meeting_intel(client_id, intel, metadata)
                    meetings_processed += 1

            # Mark client as scanned
            scan_state.mark_client_scanned(session_id, client_id, meetings_processed)
            print(f"   ✅ Processed {meetings_processed} meetings for {client_id}")

        except Exception as e:
            print(f"   ❌ Error scanning {client_id}: {e}")

    # Mark initial scan as completed
    scan_state.mark_initial_scan_completed(session_id)
    print(f"\n🎉 Initial scan complete for session {session_id[:8]}...")


async def run_weekly_scan(credentials, session_id: str, client_ids: List[str]):
    """
    Run weekly scan for a user's clients (past 7 days).
    """
    lookback_hours = settings.WEEKLY_SCAN_DAYS * 24
    print(f"📆 Running weekly scan for session {session_id[:8]}... ({len(client_ids)} clients)")

    scanner = CalendarScanner(credentials)
    processor = SmartProcessor()
    ingester = MeetingIngester()

    for client_id in client_ids:
        try:
            candidates = scanner.scan_past_meetings(lookback_hours=lookback_hours)

            meetings_processed = 0
            for meeting in candidates:
                transcript = scanner.get_transcript_content(meeting)
                if not transcript:
                    continue

                metadata = {
                    "client_id": client_id,
                    "date": meeting.get('start'),
                    "summary": meeting.get('summary')
                }

                intel = await processor.process_transcript(transcript, metadata)
                if intel:
                    ingester.ingest_meeting_intel(client_id, intel, metadata)
                    meetings_processed += 1

            scan_state.mark_client_scanned(session_id, client_id, meetings_processed)

        except Exception as e:
            print(f"❌ Weekly scan error for {client_id}: {e}")

    print(f"✅ Weekly scan complete for session {session_id[:8]}...")
