"""
Gmail API Client with Domain-Wide Delegation.

Fetches promotional emails from Google Groups/alias accounts
using service account impersonation.
"""

import json
import base64
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Represents a parsed email message."""
    message_id: str
    thread_id: str
    subject: str
    sender: str
    sender_email: str
    date: datetime
    html_content: str
    text_content: str
    snippet: str
    labels: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "date": self.date.isoformat() if self.date else None,
            "snippet": self.snippet,
            "labels": self.labels,
            "has_html": bool(self.html_content),
            "has_text": bool(self.text_content)
        }


class GmailClient:
    """
    Gmail API client with domain-wide delegation for Google Groups access.

    Requires:
    1. Service account with domain-wide delegation enabled
    2. Gmail API scopes granted in Google Workspace Admin Console
    3. Delegated email address (the account to impersonate)
    """

    SCOPES = [
        'https://www.googleapis.com/auth/gmail.readonly',
        'https://www.googleapis.com/auth/gmail.metadata'
    ]

    def __init__(
        self,
        service_account_json: str,
        delegated_email: str
    ):
        """
        Initialize Gmail client with domain-wide delegation.

        Args:
            service_account_json: Service account key JSON (string or path)
            delegated_email: Google Groups/alias email to impersonate
        """
        self.delegated_email = delegated_email
        self.service = self._build_service(service_account_json, delegated_email)

    def _build_service(self, service_account_json: str, delegated_email: str):
        """Build authenticated Gmail API service."""
        # Parse service account credentials
        if service_account_json.startswith('{'):
            # JSON string
            credentials_info = json.loads(service_account_json)
        else:
            # File path
            with open(service_account_json, 'r') as f:
                credentials_info = json.load(f)

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=self.SCOPES,
            subject=delegated_email
        )

        service = build('gmail', 'v1', credentials=credentials)
        logger.info(f"Gmail client initialized for {delegated_email}")
        return service

    def list_emails(
        self,
        after_date: Optional[datetime] = None,
        before_date: Optional[datetime] = None,
        max_results: int = 500,
        query_filter: Optional[str] = None,
        sender_blocklist: Optional[List[str]] = None,
        subject_blocklist: Optional[List[str]] = None
    ) -> List[EmailMessage]:
        """
        List emails matching the specified criteria.

        Args:
            after_date: Only emails after this date
            before_date: Only emails before this date
            max_results: Maximum number of emails to return
            query_filter: Additional Gmail query filter
            sender_blocklist: List of sender patterns to exclude
            subject_blocklist: List of subject patterns to exclude

        Returns:
            List of EmailMessage objects with metadata only (no content)
        """
        # Build Gmail query
        query_parts = []

        # Category filter - focus on promotional emails
        query_parts.append("category:promotions OR category:updates")

        # Date filters
        if after_date:
            query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")
        if before_date:
            query_parts.append(f"before:{before_date.strftime('%Y/%m/%d')}")

        # Additional custom query
        if query_filter:
            query_parts.append(f"({query_filter})")

        query = " ".join(query_parts)
        logger.info(f"Gmail query: {query}")

        messages = []
        page_token = None

        try:
            while len(messages) < max_results:
                # List messages
                response = self.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=min(100, max_results - len(messages)),
                    pageToken=page_token
                ).execute()

                batch_messages = response.get('messages', [])
                if not batch_messages:
                    break

                # Process each message
                for msg_data in batch_messages:
                    try:
                        email = self._get_message_metadata(msg_data['id'])
                        if email:
                            # Apply blocklist filters
                            if self._should_skip_email(
                                email, sender_blocklist, subject_blocklist
                            ):
                                continue
                            messages.append(email)

                            if len(messages) >= max_results:
                                break
                    except Exception as e:
                        logger.warning(f"Error fetching message {msg_data['id']}: {e}")
                        continue

                # Check for more pages
                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            logger.info(f"Found {len(messages)} emails matching criteria")
            return messages

        except HttpError as e:
            logger.error(f"Gmail API error: {e}")
            raise

    def _get_message_metadata(self, message_id: str) -> Optional[EmailMessage]:
        """
        Fetch metadata for a single message (no body content).

        Args:
            message_id: Gmail message ID

        Returns:
            EmailMessage with metadata only
        """
        try:
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()

            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}

            # Parse sender
            sender_raw = headers.get('From', '')
            sender_name, sender_email = self._parse_sender(sender_raw)

            # Parse date
            date_str = headers.get('Date', '')
            try:
                email_date = parsedate_to_datetime(date_str)
            except Exception:
                email_date = datetime.now()

            return EmailMessage(
                message_id=message_id,
                thread_id=msg.get('threadId', ''),
                subject=headers.get('Subject', '(No Subject)'),
                sender=sender_name,
                sender_email=sender_email,
                date=email_date,
                html_content='',  # Not fetched in metadata
                text_content='',  # Not fetched in metadata
                snippet=msg.get('snippet', ''),
                labels=msg.get('labelIds', [])
            )

        except HttpError as e:
            logger.warning(f"Error fetching message metadata {message_id}: {e}")
            return None

    def get_email_html(self, message_id: str) -> str:
        """
        Fetch the HTML content of an email.

        Args:
            message_id: Gmail message ID

        Returns:
            HTML content as string
        """
        try:
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            payload = msg.get('payload', {})
            html_content = self._extract_html_from_payload(payload)

            if not html_content:
                # Fallback to text content wrapped in HTML
                text_content = self._extract_text_from_payload(payload)
                if text_content:
                    html_content = f"<html><body><pre>{text_content}</pre></body></html>"

            return html_content or ""

        except HttpError as e:
            logger.error(f"Error fetching email HTML {message_id}: {e}")
            raise

    def _extract_html_from_payload(self, payload: Dict) -> str:
        """Recursively extract HTML content from email payload."""
        mime_type = payload.get('mimeType', '')

        # Direct HTML body
        if mime_type == 'text/html':
            body_data = payload.get('body', {}).get('data', '')
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')

        # Multipart - search parts
        parts = payload.get('parts', [])
        for part in parts:
            html = self._extract_html_from_payload(part)
            if html:
                return html

        return ''

    def _extract_text_from_payload(self, payload: Dict) -> str:
        """Recursively extract text content from email payload."""
        mime_type = payload.get('mimeType', '')

        # Direct text body
        if mime_type == 'text/plain':
            body_data = payload.get('body', {}).get('data', '')
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')

        # Multipart - search parts
        parts = payload.get('parts', [])
        for part in parts:
            text = self._extract_text_from_payload(part)
            if text:
                return text

        return ''

    def _parse_sender(self, sender_raw: str) -> tuple:
        """
        Parse sender string into name and email.

        Args:
            sender_raw: Raw sender string (e.g., "John Doe <john@example.com>")

        Returns:
            Tuple of (sender_name, sender_email)
        """
        import re
        match = re.match(r'^(?:"?([^"<]*)"?\s*)?<?([^>]+)>?$', sender_raw)
        if match:
            name = match.group(1) or ''
            email = match.group(2) or sender_raw
            return name.strip(), email.strip().lower()
        return '', sender_raw.strip().lower()

    def _should_skip_email(
        self,
        email: EmailMessage,
        sender_blocklist: Optional[List[str]],
        subject_blocklist: Optional[List[str]]
    ) -> bool:
        """
        Check if email should be skipped based on blocklist rules.

        Args:
            email: EmailMessage to check
            sender_blocklist: Patterns to match against sender
            subject_blocklist: Patterns to match against subject

        Returns:
            True if email should be skipped
        """
        sender_lower = email.sender_email.lower()
        subject_lower = email.subject.lower()

        # Check sender blocklist
        if sender_blocklist:
            for pattern in sender_blocklist:
                if pattern.lower() in sender_lower:
                    logger.debug(f"Skipping email from blocked sender: {email.sender_email}")
                    return True

        # Check subject blocklist
        if subject_blocklist:
            for pattern in subject_blocklist:
                if pattern.lower() in subject_lower:
                    logger.debug(f"Skipping email with blocked subject: {email.subject}")
                    return True

        return False

    def get_email_count(
        self,
        after_date: Optional[datetime] = None,
        query_filter: Optional[str] = None
    ) -> int:
        """
        Get count of emails matching criteria (for progress estimation).

        Args:
            after_date: Only count emails after this date
            query_filter: Additional query filter

        Returns:
            Estimated count of matching emails
        """
        query_parts = ["category:promotions OR category:updates"]

        if after_date:
            query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")
        if query_filter:
            query_parts.append(f"({query_filter})")

        query = " ".join(query_parts)

        try:
            response = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=1
            ).execute()

            # Gmail API returns resultSizeEstimate
            return response.get('resultSizeEstimate', 0)

        except HttpError as e:
            logger.error(f"Error getting email count: {e}")
            return 0

    def get_labels(self) -> List[Dict[str, str]]:
        """
        Get list of Gmail labels for debugging/configuration.

        Returns:
            List of label dictionaries
        """
        try:
            response = self.service.users().labels().list(userId='me').execute()
            return response.get('labels', [])
        except HttpError as e:
            logger.error(f"Error fetching labels: {e}")
            return []
