"""
Clerk OAuth Client for Image Repository Pipeline.

Retrieves Google OAuth tokens from Clerk Backend API for users who
signed in via Google OAuth through Clerk.
"""

import os
import logging
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

# Required scopes for Drive folder access
REQUIRED_DRIVE_SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
]


class ClerkOAuthClient:
    """
    Client to retrieve OAuth tokens from Clerk Backend API.

    Uses the Clerk Backend API to get Google OAuth access tokens for users
    who signed in via Google OAuth, allowing seamless Drive access without
    a second OAuth popup.
    """

    CLERK_API_BASE = "https://api.clerk.com/v1"

    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize Clerk OAuth client.

        Args:
            secret_key: Clerk secret key (sk_live_* or sk_test_*).
                       Falls back to CLERK_SECRET_KEY env var.
        """
        self.secret_key = secret_key or os.getenv("CLERK_SECRET_KEY")
        if not self.secret_key:
            raise ValueError(
                "CLERK_SECRET_KEY must be configured to retrieve OAuth tokens from Clerk"
            )

    async def get_google_oauth_token(self, clerk_user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Google OAuth access token for a Clerk user.

        Calls Clerk Backend API to retrieve the OAuth token that was obtained
        when the user signed in via Google.

        Args:
            clerk_user_id: Clerk user ID (user_2abc...)

        Returns:
            Dict with token info if available:
            {
                "token": "ya29.xxx...",
                "scopes": ["openid", "email", "profile", "https://www.googleapis.com/auth/drive.readonly"],
                "provider_user_id": "google-user-id",
                "label": null
            }
            Returns None if user has no Google OAuth connection.
        """
        url = f"{self.CLERK_API_BASE}/users/{clerk_user_id}/oauth_access_tokens/google"

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=headers)

                if response.status_code == 404:
                    logger.info(f"No Google OAuth connection found for user {clerk_user_id}")
                    return None

                if response.status_code == 401:
                    logger.error("Clerk API authentication failed - check CLERK_SECRET_KEY")
                    return None

                if response.status_code != 200:
                    logger.warning(
                        f"Clerk API returned {response.status_code} for user {clerk_user_id}: "
                        f"{response.text}"
                    )
                    return None

                # Clerk returns an array of OAuth tokens
                tokens = response.json()

                if not tokens or len(tokens) == 0:
                    logger.info(f"No Google OAuth tokens found for user {clerk_user_id}")
                    return None

                # Return the first (and typically only) token
                token_data = tokens[0]

                logger.info(
                    f"Retrieved Google OAuth token for user {clerk_user_id} "
                    f"with scopes: {token_data.get('scopes', [])}"
                )

                return token_data

        except httpx.TimeoutException:
            logger.error(f"Timeout calling Clerk API for user {clerk_user_id}")
            return None
        except Exception as e:
            logger.error(f"Error calling Clerk API for user {clerk_user_id}: {e}")
            return None

    def has_required_scopes(self, token_data: Dict[str, Any]) -> bool:
        """
        Check if the token has the required Drive scopes.

        Args:
            token_data: Token data from get_google_oauth_token()

        Returns:
            True if token has drive.readonly scope
        """
        if not token_data:
            return False

        scopes = token_data.get("scopes", [])

        # Check for drive.readonly scope
        for required_scope in REQUIRED_DRIVE_SCOPES:
            if required_scope not in scopes:
                logger.info(f"Token missing required scope: {required_scope}")
                return False

        return True

    def get_missing_scopes(self, token_data: Dict[str, Any]) -> List[str]:
        """
        Get list of required scopes that are missing from the token.

        Args:
            token_data: Token data from get_google_oauth_token()

        Returns:
            List of missing scope strings
        """
        if not token_data:
            return REQUIRED_DRIVE_SCOPES.copy()

        scopes = set(token_data.get("scopes", []))
        return [s for s in REQUIRED_DRIVE_SCOPES if s not in scopes]
