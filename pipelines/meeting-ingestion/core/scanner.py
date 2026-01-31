"""
The "Watcher": Scans calendar for relevant client meetings.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from app.client_id import normalize_client_id

class CalendarScanner:
    def __init__(self, credentials: Credentials):
        self.service = build('calendar', 'v3', credentials=credentials)
        self.drive_service = build('drive', 'v3', credentials=credentials)

    def scan_past_meetings(self, lookback_hours: int = 24, allowed_domains: List[str] = None) -> List[Dict[str, Any]]:
        """
        Scan for meetings in the past X hours that look like client meetings.
        """
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(hours=lookback_hours)).isoformat()
        
        # List events
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=time_min,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        candidates = []
        
        for event in events:
            # 1. Filter: Must be an external meeting (checking attendees)
            if not self._is_external_meeting(event, allowed_domains):
                continue
                
            # 2. Filter: Must have a transcript or recording artifact
            # Note: The 'conferenceData' or 'attachments' field usually holds this.
            # For this MVP, we will optimistically include it if it has an external guest
            # and later the Processor will check for the actual transcript file.
            
            candidates.append({
                "event_id": event.get('id'),
                "summary": event.get('summary'),
                "start": event.get('start').get('dateTime'),
                "attendees": [a.get('email') for a in event.get('attendees', [])],
                "conference_data": event.get('conferenceData', {}),
                "attachments": event.get('attachments', [])
            })
            
        return candidates

    def _is_external_meeting(self, event: Dict, allowed_domains: List[str] = None) -> bool:
        """Check if any attendee is external or matches allowed domains."""
        attendees = event.get('attendees', [])
        if not attendees:
            return False
            
        if allowed_domains:
            # Strict domain matching
            for attendee in attendees:
                email = attendee.get('email', '').lower()
                if any(email.endswith(f"@{d.lower()}") for d in allowed_domains):
                    return True
            return False
        
        # Heuristic: Check for domains that look like clients if no domain specified
        return True

    def get_transcript_content(self, event: Dict) -> Optional[str]:
        """
        Attempt to fetch transcript content from event attachments.
        This searches for Google Doc attachments that look like transcripts.
        """
        attachments = event.get('attachments', [])
        for attachment in attachments:
            if attachment.get('mimeType') == 'application/vnd.google-apps.document':
                # Potential transcript. 
                # In a real flow, we'd check the title or source.
                return self._fetch_doc_content(attachment.get('fileId'))
        return None

    def _fetch_doc_content(self, file_id: str) -> Optional[str]:
        """Fetch content of a Google Doc (Transcript)."""
        try:
            # Uses the Drive API to export or Docs API to read
            # For simplicity, reusing the logic from existing GoogleDocsService would be ideal
            # but we are self-contained here.
            docs_service = build('docs', 'v1', credentials=self.service.credentials)
            doc = docs_service.documents().get(documentId=file_id).execute()
            
            # Simple text extraction
            text = ""
            for item in doc.get('body').get('content', []):
                if 'paragraph' in item:
                    for element in item['paragraph']['elements']:
                        text += element.get('textRun', {}).get('content', '')
            return text
        except Exception as e:
            print(f"Error fetching doc {file_id}: {e}")
            return None
