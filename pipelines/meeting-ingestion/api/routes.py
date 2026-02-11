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
    background_tasks.add_task(
        run_pipeline, credentials, session_id, normalized_client_id,
        lookback_hours, client_domain
    )

    return {
        "status": "scan_started",
        "client_id": normalized_client_id,
        "config": {
            "lookback_hours": lookback_hours,
            "domain": client_domain or "auto-detect"
        }
    }

async def run_pipeline(credentials, session_id, client_id, lookback_hours=24, client_domain=None):
    """
    Orchestrates the Scan -> Process -> Ingest flow for a single client.
    Includes dedup: skips events already ingested for this client.
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
        event_id = meeting.get('event_id')

        # Fix #5: skip already-ingested events
        if scan_state.is_event_ingested(session_id, client_id, event_id):
            print(f"Skipping already-ingested event: {meeting.get('summary')}")
            continue

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
            # 5. Mark as ingested for dedup
            scan_state.mark_event_ingested(session_id, client_id, event_id)
        else:
            print("Meeting filtered out (Low signal).")

    print(f"Scan complete for {client_id}")


# ============================================================================
# Initial & Scheduled Scan Endpoints
# ============================================================================

from pydantic import BaseModel

class InitialScanRequest(BaseModel):
    client_ids: List[str]
    client_domains: Dict[str, List[str]] = {}  # client_id -> [domain1, domain2]
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

    client_domains is an optional mapping of client_id -> [allowed_domains] for
    matching meetings to the correct client.
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

    # Normalize domain mapping
    domain_map = {}
    for cid, domains in request.client_domains.items():
        domain_map[normalize_client_id(cid)] = [d.lower() for d in domains]

    # Mark scan as started (persist domain map for weekly scan reuse)
    scan_state.mark_initial_scan_started(session_id, email, normalized_clients, domain_map)

    # Run initial scan in background
    background_tasks.add_task(
        run_initial_scan,
        credentials,
        session_id,
        normalized_clients,
        domain_map
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
            domain_map = user.get("client_domains", {})
            if client_ids:
                background_tasks.add_task(
                    run_weekly_scan,
                    credentials,
                    session_id,
                    client_ids,
                    domain_map
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


def _match_meeting_to_clients(
    event: Dict, client_ids: List[str], domain_map: Dict[str, List[str]]
) -> List[str]:
    """
    Match a meeting to the correct client(s) based on attendee domains.

    Fix #2: Instead of blindly assigning every meeting to every client,
    check which client domains appear in the meeting's attendee list.

    Returns list of client_ids that match. Falls back to all clients
    if no domain_map is provided (preserves existing behavior).
    """
    if not domain_map:
        # No domain mapping available — fall back to all clients
        return client_ids

    # Extract attendee domains from the meeting
    # Note: attendees are email strings (transformed in scanner.py:73)
    attendee_domains = set()
    for email in event.get('attendees', []):
        if isinstance(email, str) and '@' in email:
            attendee_domains.add(email.split('@')[1].lower())

    matched = []
    for cid in client_ids:
        client_domains = domain_map.get(cid, [])
        if not client_domains:
            # No domains configured for this client — include it (safe default)
            matched.append(cid)
            continue
        # Check if any client domain appears in attendees
        if attendee_domains & set(client_domains):
            matched.append(cid)

    return matched


async def run_initial_scan(
    credentials, session_id: str, client_ids: List[str],
    domain_map: Dict[str, List[str]] = None
):
    """
    Run the initial 60-day scan for all user's clients.

    Fix #2: Scans calendar ONCE, then matches each meeting to the correct
    client(s) by attendee domain. Prevents N x M duplicate processing.
    Fix #5: Skips events already ingested per client.
    """
    if domain_map is None:
        domain_map = {}

    lookback_hours = settings.INITIAL_SCAN_DAYS * 24  # Convert days to hours
    print(f"Starting initial scan for {len(client_ids)} clients ({settings.INITIAL_SCAN_DAYS} days lookback)")

    scanner = CalendarScanner(credentials)
    processor = SmartProcessor()
    ingester = MeetingIngester()

    # Fix #2: scan calendar ONCE (no allowed_domains filter — we match after)
    candidates = scanner.scan_past_meetings(lookback_hours=lookback_hours)
    print(f"Found {len(candidates)} candidate meetings across all clients")

    # Track per-client counts
    client_counts = {cid: 0 for cid in client_ids}

    for meeting in candidates:
        event_id = meeting.get('event_id')

        # Fix #2: determine which clients this meeting belongs to
        matched_clients = _match_meeting_to_clients(meeting, client_ids, domain_map)
        if not matched_clients:
            continue

        # Only fetch transcript once per meeting (expensive operation)
        transcript = scanner.get_transcript_content(meeting)
        if not transcript:
            continue

        for client_id in matched_clients:
            # Fix #5: skip already-ingested events
            if scan_state.is_event_ingested(session_id, client_id, event_id):
                continue

            metadata = {
                "client_id": client_id,
                "date": meeting.get('start'),
                "summary": meeting.get('summary')
            }

            try:
                intel = await processor.process_transcript(transcript, metadata)
                if intel:
                    ingester.ingest_meeting_intel(client_id, intel, metadata)
                    scan_state.mark_event_ingested(session_id, client_id, event_id)
                    client_counts[client_id] += 1
            except Exception as e:
                print(f"Error processing meeting for {client_id}: {e}")

    # Mark each client as scanned
    for client_id in client_ids:
        scan_state.mark_client_scanned(session_id, client_id, client_counts[client_id])
        print(f"Processed {client_counts[client_id]} meetings for {client_id}")

    # Mark initial scan as completed
    scan_state.mark_initial_scan_completed(session_id)
    print(f"Initial scan complete for session {session_id[:8]}...")


async def run_weekly_scan(
    credentials, session_id: str, client_ids: List[str],
    domain_map: Dict[str, List[str]] = None
):
    """
    Run weekly scan for a user's clients (past 7 days).

    Fix #2: Scans calendar ONCE, matches meetings to clients by domain.
    Fix #5: Skips already-ingested events.
    """
    if domain_map is None:
        domain_map = {}

    lookback_hours = settings.WEEKLY_SCAN_DAYS * 24
    print(f"Running weekly scan for session {session_id[:8]}... ({len(client_ids)} clients)")

    scanner = CalendarScanner(credentials)
    processor = SmartProcessor()
    ingester = MeetingIngester()

    # Fix #2: scan calendar ONCE
    candidates = scanner.scan_past_meetings(lookback_hours=lookback_hours)

    client_counts = {cid: 0 for cid in client_ids}

    for meeting in candidates:
        event_id = meeting.get('event_id')
        matched_clients = _match_meeting_to_clients(meeting, client_ids, domain_map)
        if not matched_clients:
            continue

        transcript = scanner.get_transcript_content(meeting)
        if not transcript:
            continue

        for client_id in matched_clients:
            if scan_state.is_event_ingested(session_id, client_id, event_id):
                continue

            metadata = {
                "client_id": client_id,
                "date": meeting.get('start'),
                "summary": meeting.get('summary')
            }

            try:
                intel = await processor.process_transcript(transcript, metadata)
                if intel:
                    ingester.ingest_meeting_intel(client_id, intel, metadata)
                    scan_state.mark_event_ingested(session_id, client_id, event_id)
                    client_counts[client_id] += 1
            except Exception as e:
                print(f"Weekly scan error for {client_id}: {e}")

    for client_id in client_ids:
        scan_state.mark_client_scanned(session_id, client_id, client_counts[client_id])

    print(f"Weekly scan complete for session {session_id[:8]}...")
