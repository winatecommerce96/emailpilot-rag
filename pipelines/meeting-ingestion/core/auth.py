"""
OAuth service for Google Calendar and Drive access.
Supports persistent user sessions via Firestore.
"""
import os
import json
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Ensure .env is loaded before reading credentials
load_dotenv()

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from config.settings import settings

# Firestore for persistent token storage
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False


class CalendarAuthService:
    """
    Manages Google OAuth for Calendar/Drive access.
    Tokens are stored in Firestore, keyed by user email (from Google).
    """

    COLLECTION = "meeting_oauth_sessions"

    def __init__(self):
        self.client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        self.redirect_uri = settings.REDIRECT_URI

        # Firestore client (lazy init)
        self._db = None

        # Fallback in-memory storage if Firestore unavailable
        self._tokens: Dict[str, Dict] = {}

    @property
    def db(self):
        """Lazy-load Firestore client."""
        if self._db is None and FIRESTORE_AVAILABLE:
            project = os.getenv("GOOGLE_CLOUD_PROJECT", "emailpilot-438321")
            self._db = firestore.Client(project=project)
        return self._db

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Generate OAuth URL for user to authenticate."""
        if not self.is_configured():
            raise ValueError("Google OAuth not configured.")

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=settings.SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            state=state,
            prompt='consent',  # Force consent screen to ensure Calendar/Drive scopes are granted
            include_granted_scopes='true'  # Incremental auth: add to existing scopes
        )
        return auth_url

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange auth code for tokens and store them persistently."""
        if not self.is_configured():
            raise ValueError("Google OAuth not configured.")

        # Manual token exchange to avoid strict scope checking
        import httpx

        token_response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code"
            }
        )

        if token_response.status_code != 200:
            raise ValueError(f"Token exchange failed: {token_response.text}")

        token_data = token_response.json()

        # Build credentials from response (accepts whatever scopes Google returns)
        credentials = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=token_data.get("scope", "").split() if token_data.get("scope") else settings.SCOPES
        )

        # Get user email from Google
        email = self._get_user_email(credentials)

        # Generate session ID based on email (deterministic per user)
        session_id = hashlib.sha256(email.encode()).hexdigest()[:32]

        # Store credentials persistently
        self._store_credentials(session_id, credentials, email)

        return {
            "session_id": session_id,
            "email": email
        }

    def _store_credentials(self, session_id: str, credentials: Credentials, email: str):
        """Store credentials in Firestore (or fallback to memory)."""
        token_data = {
            "token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": list(credentials.scopes) if credentials.scopes else [],
            "email": email,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if self.db:
            try:
                self.db.collection(self.COLLECTION).document(session_id).set(token_data)
                print(f"✅ Stored OAuth tokens for {email} in Firestore")
                return
            except Exception as e:
                print(f"⚠️ Firestore write failed: {e}, using memory fallback")

        # Fallback to in-memory
        self._tokens[session_id] = token_data
        print(f"✅ Stored OAuth tokens for {email} in memory")

    def _load_credentials(self, session_id: str) -> Optional[Dict]:
        """Load credentials from Firestore (or fallback to memory)."""
        if self.db:
            try:
                doc = self.db.collection(self.COLLECTION).document(session_id).get()
                if doc.exists:
                    return doc.to_dict()
            except Exception as e:
                print(f"⚠️ Firestore read failed: {e}")

        # Fallback to in-memory
        return self._tokens.get(session_id)

    def get_credentials(self, session_id: str) -> Optional[Credentials]:
        """Get credentials for a session, refreshing if needed."""
        token_data = self._load_credentials(session_id)
        if not token_data:
            return None

        credentials = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id") or self.client_id,
            client_secret=token_data.get("client_secret") or self.client_secret,
            scopes=token_data.get("scopes", settings.SCOPES)
        )

        # Refresh if expired
        if credentials.expired and credentials.refresh_token:
            try:
                from google.auth.transport.requests import Request
                credentials.refresh(Request())
                # Update stored credentials with new token
                self._store_credentials(session_id, credentials, token_data.get("email", "unknown"))
                print(f"🔄 Refreshed OAuth token for session {session_id[:8]}...")
            except Exception as e:
                print(f"⚠️ Token refresh failed: {e}")
                return None

        return credentials

    def get_session_for_user(self, email: str) -> Optional[str]:
        """Get existing session ID for a user by email."""
        # Session ID is deterministic based on email
        return hashlib.sha256(email.encode()).hexdigest()[:32]

    def check_user_connected(self, email: str) -> bool:
        """Check if a user has an existing valid connection."""
        session_id = self.get_session_for_user(email)
        credentials = self.get_credentials(session_id)
        return credentials is not None

    def disconnect_user(self, session_id: str) -> bool:
        """Revoke and delete a user's OAuth session."""
        if self.db:
            try:
                self.db.collection(self.COLLECTION).document(session_id).delete()
                print(f"🗑️ Deleted OAuth session {session_id[:8]}...")
                return True
            except Exception as e:
                print(f"⚠️ Failed to delete session: {e}")

        # Fallback
        if session_id in self._tokens:
            del self._tokens[session_id]
            return True
        return False

    def _get_user_email(self, credentials: Credentials) -> str:
        """Get user's email from Google."""
        from googleapiclient.discovery import build
        try:
            service = build('oauth2', 'v2', credentials=credentials)
            user_info = service.userinfo().get().execute()
            return user_info.get('email', 'unknown')
        except Exception as e:
            print(f"⚠️ Failed to get user email: {e}")
            return 'unknown'


# Singleton
_calendar_auth_service = None

def get_calendar_auth_service() -> CalendarAuthService:
    global _calendar_auth_service
    if _calendar_auth_service is None:
        _calendar_auth_service = CalendarAuthService()
    return _calendar_auth_service
