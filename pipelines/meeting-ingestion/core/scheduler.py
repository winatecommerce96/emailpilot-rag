"""
Meeting scan state tracking and scheduling logic.
Manages initial 60-day scans and weekly recurring scans.
"""
import os
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False


class ScanStateManager:
    """
    Tracks scan state per user in Firestore.
    - initial_scan_completed: bool
    - last_scan_at: timestamp
    - clients_scanned: list of client_ids
    """

    COLLECTION = "meeting_scan_state"

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None and FIRESTORE_AVAILABLE:
            project = os.getenv("GOOGLE_CLOUD_PROJECT", "emailpilot-438321")
            self._db = firestore.Client(project=project)
        return self._db

    def get_user_state(self, session_id: str) -> Dict[str, Any]:
        """Get the scan state for a user session."""
        if not self.db:
            return {"initial_scan_completed": False, "last_scan_at": None, "clients_scanned": []}

        try:
            doc = self.db.collection(self.COLLECTION).document(session_id).get()
            if doc.exists:
                return doc.to_dict()
        except Exception as e:
            print(f"⚠️ Failed to get scan state: {e}")

        return {"initial_scan_completed": False, "last_scan_at": None, "clients_scanned": []}

    def mark_initial_scan_started(self, session_id: str, email: str, client_ids: List[str]):
        """Mark that initial scan has been started for a user."""
        if not self.db:
            return

        try:
            self.db.collection(self.COLLECTION).document(session_id).set({
                "email": email,
                "initial_scan_started_at": datetime.now(timezone.utc).isoformat(),
                "initial_scan_completed": False,
                "clients_to_scan": client_ids,
                "clients_scanned": [],
                "last_scan_at": None
            }, merge=True)
        except Exception as e:
            print(f"⚠️ Failed to mark initial scan started: {e}")

    def mark_client_scanned(self, session_id: str, client_id: str, meetings_found: int):
        """Mark a client as scanned (during initial or weekly scan)."""
        if not self.db:
            return

        try:
            doc_ref = self.db.collection(self.COLLECTION).document(session_id)
            doc_ref.update({
                "clients_scanned": firestore.ArrayUnion([client_id]),
                "last_scan_at": datetime.now(timezone.utc).isoformat(),
                f"scan_results.{client_id}": {
                    "scanned_at": datetime.now(timezone.utc).isoformat(),
                    "meetings_found": meetings_found
                }
            })
        except Exception as e:
            print(f"⚠️ Failed to mark client scanned: {e}")

    def mark_initial_scan_completed(self, session_id: str):
        """Mark the initial 60-day scan as fully completed."""
        if not self.db:
            return

        try:
            self.db.collection(self.COLLECTION).document(session_id).update({
                "initial_scan_completed": True,
                "initial_scan_completed_at": datetime.now(timezone.utc).isoformat()
            })
            print(f"✅ Initial scan completed for session {session_id[:8]}...")
        except Exception as e:
            print(f"⚠️ Failed to mark initial scan completed: {e}")

    def get_users_due_for_weekly_scan(self) -> List[Dict[str, Any]]:
        """
        Get all users who have completed initial scan and are due for weekly scan.
        Returns users whose last_scan_at is older than 7 days.
        """
        if not self.db:
            return []

        try:
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            cutoff_str = cutoff.isoformat()

            # Query users with initial_scan_completed = True and last_scan_at < 7 days ago
            docs = self.db.collection(self.COLLECTION)\
                .where("initial_scan_completed", "==", True)\
                .stream()

            due_users = []
            for doc in docs:
                data = doc.to_dict()
                last_scan = data.get("last_scan_at")
                if not last_scan or last_scan < cutoff_str:
                    due_users.append({
                        "session_id": doc.id,
                        "email": data.get("email"),
                        "clients_scanned": data.get("clients_scanned", []),
                        "last_scan_at": last_scan
                    })

            return due_users
        except Exception as e:
            print(f"⚠️ Failed to get users due for weekly scan: {e}")
            return []


# Singleton
_scan_state_manager = None

def get_scan_state_manager() -> ScanStateManager:
    global _scan_state_manager
    if _scan_state_manager is None:
        _scan_state_manager = ScanStateManager()
    return _scan_state_manager
