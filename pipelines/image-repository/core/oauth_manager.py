"""
OAuth Token Manager for Image Repository Pipeline.

Handles encrypted storage and retrieval of user Google OAuth tokens
for accessing personal Drive folders.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from google.cloud import firestore
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import json

logger = logging.getLogger(__name__)

# Scopes needed for Drive folder access
DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive.metadata.readonly'
]


class OAuthTokenManager:
    """
    Manages encrypted OAuth tokens in Firestore.

    Tokens are encrypted using a master key stored in GCP Secret Manager.
    """

    def __init__(
        self,
        project_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        collection_name: str = "oauth_tokens"
    ):
        """
        Initialize OAuth manager.

        Args:
            project_id: GCP project ID
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret (from Secret Manager)
            redirect_uri: OAuth redirect URI
            collection_name: Firestore collection for tokens
        """
        self.project_id = project_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.collection_name = collection_name
        self.db = firestore.Client(project=project_id)

        # Encryption key from environment or Secret Manager
        self._encryption_key = self._get_encryption_key()

    def _get_encryption_key(self) -> bytes:
        """Get or create encryption key for token storage."""
        # Try environment variable first (for local dev)
        key = os.environ.get('OAUTH_ENCRYPTION_KEY')
        if key:
            return key.encode() if isinstance(key, str) else key

        # Try Secret Manager
        try:
            from google.cloud import secretmanager
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{self.project_id}/secrets/oauth-encryption-key/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data
        except Exception as e:
            logger.warning(f"Could not get encryption key from Secret Manager: {e}")

        # Generate a key for development (NOT for production)
        logger.warning("Using auto-generated encryption key - NOT FOR PRODUCTION")
        from cryptography.fernet import Fernet
        return Fernet.generate_key()

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string value."""
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key)
        return f.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string."""
        from cryptography.fernet import Fernet
        f = Fernet(self._encryption_key)
        return f.decrypt(ciphertext.encode()).decode()

    def create_authorization_url(self, user_id: str, state: Optional[str] = None) -> tuple:
        """
        Create OAuth authorization URL for user to grant access.

        Returns:
            Tuple of (authorization_url, state)
        """
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
            scopes=DRIVE_SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state or user_id,
            prompt='consent'  # Force consent to get refresh token
        )

        return authorization_url, state

    def exchange_code_for_tokens(self, code: str, user_id: str) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens and store encrypted.

        Args:
            code: Authorization code from OAuth callback
            user_id: User ID to associate tokens with

        Returns:
            Dict with status and expiry info
        """
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
            scopes=DRIVE_SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        # Exchange code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Encrypt and store tokens
        token_data = {
            "access_token_encrypted": self._encrypt(credentials.token),
            "refresh_token_encrypted": self._encrypt(credentials.refresh_token) if credentials.refresh_token else None,
            "token_uri": credentials.token_uri,
            "scopes": list(credentials.scopes) if credentials.scopes else DRIVE_SCOPES,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id
        }

        # Store in Firestore
        doc_ref = self.db.collection(self.collection_name).document(user_id)
        doc_ref.set(token_data, merge=True)

        logger.info(f"Stored OAuth tokens for user {user_id}")

        return {
            "status": "authorized",
            "expires_at": token_data["expiry"],
            "scopes": token_data["scopes"]
        }

    def get_credentials(self, user_id: str) -> Optional[Credentials]:
        """
        Get valid credentials for a user, refreshing if needed.

        Returns:
            Credentials object or None if not authorized
        """
        doc_ref = self.db.collection(self.collection_name).document(user_id)
        doc = doc_ref.get()

        if not doc.exists:
            logger.info(f"No OAuth tokens found for user {user_id}")
            return None

        data = doc.to_dict()

        # Decrypt tokens
        try:
            access_token = self._decrypt(data["access_token_encrypted"])
            refresh_token = self._decrypt(data["refresh_token_encrypted"]) if data.get("refresh_token_encrypted") else None
        except Exception as e:
            logger.error(f"Failed to decrypt tokens for user {user_id}: {e}")
            return None

        # Build credentials
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=data.get("scopes", DRIVE_SCOPES)
        )

        # Refresh if expired
        if credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())

                # Update stored tokens
                update_data = {
                    "access_token_encrypted": self._encrypt(credentials.token),
                    "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                doc_ref.update(update_data)

                logger.info(f"Refreshed OAuth tokens for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to refresh tokens for user {user_id}: {e}")
                return None

        return credentials

    def get_auth_status(self, user_id: str) -> Dict[str, Any]:
        """
        Check OAuth authorization status for a user.

        Returns:
            Dict with is_authorized, expires_at, scopes
        """
        doc_ref = self.db.collection(self.collection_name).document(user_id)
        doc = doc_ref.get()

        if not doc.exists:
            return {
                "is_authorized": False,
                "expires_at": None,
                "scopes": []
            }

        data = doc.to_dict()

        return {
            "is_authorized": True,
            "expires_at": data.get("expiry"),
            "scopes": data.get("scopes", []),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "token_source": data.get("token_source")
        }

    def store_external_token(
        self,
        user_id: str,
        access_token: str,
        scopes: List[str],
        token_source: str = "clerk_google"
    ) -> Dict[str, Any]:
        """
        Store an externally-obtained token (e.g., from Clerk).

        Unlike tokens from the standard OAuth flow, these tokens may not have
        a refresh token. The token will be stored encrypted and marked with
        its source for tracking.

        Args:
            user_id: User ID to associate tokens with
            access_token: The OAuth access token
            scopes: List of granted scopes
            token_source: Source of the token (e.g., "clerk_google")

        Returns:
            Dict with status and scope info
        """
        # Encrypt and store token
        token_data = {
            "access_token_encrypted": self._encrypt(access_token),
            "refresh_token_encrypted": None,  # External tokens may not have refresh tokens
            "token_uri": "https://oauth2.googleapis.com/token",
            "scopes": scopes,
            "expiry": None,  # External tokens don't provide expiry info
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "token_source": token_source
        }

        # Store in Firestore
        doc_ref = self.db.collection(self.collection_name).document(user_id)
        doc_ref.set(token_data, merge=True)

        logger.info(f"Stored external OAuth token ({token_source}) for user {user_id}")

        return {
            "status": "authorized",
            "scopes": scopes,
            "token_source": token_source
        }

    def revoke_tokens(self, user_id: str) -> Dict[str, Any]:
        """
        Revoke and delete OAuth tokens for a user.

        Returns:
            Dict with status
        """
        doc_ref = self.db.collection(self.collection_name).document(user_id)
        doc = doc_ref.get()

        if doc.exists:
            # Optionally revoke with Google
            try:
                data = doc.to_dict()
                access_token = self._decrypt(data["access_token_encrypted"])

                import requests
                requests.post(
                    'https://oauth2.googleapis.com/revoke',
                    params={'token': access_token},
                    headers={'content-type': 'application/x-www-form-urlencoded'}
                )
            except Exception as e:
                logger.warning(f"Could not revoke token with Google: {e}")

            # Delete from Firestore
            doc_ref.delete()

            logger.info(f"Revoked OAuth tokens for user {user_id}")

        return {"status": "revoked"}
