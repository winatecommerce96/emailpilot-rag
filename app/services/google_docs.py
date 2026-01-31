"""
Google Docs OAuth integration for importing documents into RAG.
Handles OAuth flow and document content extraction.
"""
import os
import re
from typing import Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# OAuth scopes needed for Google Docs read access
SCOPES = [
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]


class GoogleDocsService:
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
        self.redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "https://rag-service-p3cxgvcsla-uc.a.run.app/api/google/callback")

        # In-memory token storage (use Redis/DB in production)
        self._tokens: Dict[str, Credentials] = {}

    def is_configured(self) -> bool:
        """Check if OAuth credentials are configured."""
        return bool(self.client_id and self.client_secret)

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Generate OAuth authorization URL for user to grant access."""
        if not self.is_configured():
            raise ValueError("Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")

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
            scopes=SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        auth_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state,
            prompt='consent'
        )
        return auth_url

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
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
            scopes=SCOPES
        )
        flow.redirect_uri = self.redirect_uri

        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Generate a simple session ID (use proper session management in production)
        import hashlib
        import time
        session_id = hashlib.sha256(f"{credentials.token}{time.time()}".encode()).hexdigest()[:32]

        # Store credentials
        self._tokens[session_id] = credentials

        return {
            "session_id": session_id,
            "expires_at": credentials.expiry.isoformat() if credentials.expiry else None
        }

    def get_credentials(self, session_id: str) -> Optional[Credentials]:
        """Get stored credentials for a session."""
        return self._tokens.get(session_id)

    def extract_doc_id(self, url_or_id: str) -> Optional[str]:
        """Extract Google Doc ID from URL or return as-is if already an ID."""
        # If it looks like a URL, extract the ID
        if 'docs.google.com' in url_or_id or 'drive.google.com' in url_or_id:
            # Match patterns like /d/DOC_ID/ or /document/d/DOC_ID/
            match = re.search(r'/d/([a-zA-Z0-9_-]+)', url_or_id)
            if match:
                return match.group(1)
            return None

        # Assume it's already a document ID
        if re.match(r'^[a-zA-Z0-9_-]+$', url_or_id):
            return url_or_id

        return None

    def fetch_document(self, session_id: str, doc_url_or_id: str) -> Dict[str, Any]:
        """
        Fetch a Google Doc's content using stored OAuth credentials.
        Returns document title and extracted text content.
        """
        credentials = self.get_credentials(session_id)
        if not credentials:
            return {"success": False, "error": "Invalid or expired session. Please re-authenticate."}

        doc_id = self.extract_doc_id(doc_url_or_id)
        if not doc_id:
            return {"success": False, "error": "Invalid Google Doc URL or ID."}

        try:
            # Build the Docs API service
            service = build('docs', 'v1', credentials=credentials)

            # Fetch the document
            document = service.documents().get(documentId=doc_id).execute()

            title = document.get('title', 'Untitled Document')
            content = self._extract_text_from_doc(document)

            return {
                "success": True,
                "doc_id": doc_id,
                "title": title,
                "content": content,
                "word_count": len(content.split())
            }

        except HttpError as e:
            if e.resp.status == 404:
                return {"success": False, "error": "Document not found. Check the URL and ensure you have access."}
            elif e.resp.status == 403:
                return {"success": False, "error": "Access denied. Make sure you have permission to view this document."}
            else:
                return {"success": False, "error": f"Google API error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to fetch document: {str(e)}"}

    def _extract_text_from_doc(self, document: Dict) -> str:
        """Extract plain text content from Google Docs API response."""
        text_parts = []

        content = document.get('body', {}).get('content', [])

        for element in content:
            if 'paragraph' in element:
                paragraph = element['paragraph']
                para_text = ""

                for elem in paragraph.get('elements', []):
                    if 'textRun' in elem:
                        para_text += elem['textRun'].get('content', '')

                text_parts.append(para_text)

            elif 'table' in element:
                # Extract text from table cells
                table = element['table']
                for row in table.get('tableRows', []):
                    row_text = []
                    for cell in row.get('tableCells', []):
                        cell_content = cell.get('content', [])
                        for cell_elem in cell_content:
                            if 'paragraph' in cell_elem:
                                for text_elem in cell_elem['paragraph'].get('elements', []):
                                    if 'textRun' in text_elem:
                                        row_text.append(text_elem['textRun'].get('content', '').strip())
                    if row_text:
                        text_parts.append(' | '.join(row_text))

        return '\n'.join(text_parts)

    def list_recent_docs(self, session_id: str, max_results: int = 20) -> Dict[str, Any]:
        """List user's recent Google Docs."""
        credentials = self.get_credentials(session_id)
        if not credentials:
            return {"success": False, "error": "Invalid or expired session. Please re-authenticate."}

        try:
            # Build the Drive API service
            service = build('drive', 'v3', credentials=credentials)

            # Query for Google Docs only
            results = service.files().list(
                q="mimeType='application/vnd.google-apps.document'",
                pageSize=max_results,
                fields="files(id, name, modifiedTime, webViewLink)",
                orderBy="modifiedTime desc"
            ).execute()

            files = results.get('files', [])

            return {
                "success": True,
                "documents": [
                    {
                        "id": f['id'],
                        "name": f['name'],
                        "modified": f.get('modifiedTime'),
                        "url": f.get('webViewLink')
                    }
                    for f in files
                ]
            }

        except HttpError as e:
            return {"success": False, "error": f"Google API error: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to list documents: {str(e)}"}


# Singleton instance
_google_docs_service: Optional[GoogleDocsService] = None

def get_google_docs_service() -> GoogleDocsService:
    global _google_docs_service
    if _google_docs_service is None:
        _google_docs_service = GoogleDocsService()
    return _google_docs_service
