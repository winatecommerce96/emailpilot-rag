"""
The "Watcher": Scans calendar for relevant client meetings.

Fixes applied:
- #1: Drive search for Google Meet transcripts (not event attachments)
- #3: timeMax to exclude future events
- #4: Pagination for large lookback windows
- #6: Filter cancelled/declined meetings
- #7: Handle all-day events safely
- #8: Use Drive export instead of Docs API (covered by drive.readonly scope)
"""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


class CalendarScanner:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build('calendar', 'v3', credentials=credentials)
        self.drive_service = build('drive', 'v3', credentials=credentials)

    def scan_past_meetings(self, lookback_hours: int = 24, allowed_domains: List[str] = None) -> List[Dict[str, Any]]:
        """
        Scan for meetings in the past X hours that look like client meetings.
        Paginates through all results and excludes future/cancelled/declined events.
        """
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(hours=lookback_hours)).isoformat()
        time_max = now.isoformat()  # Fix #3: exclude future events

        # Fix #4: paginate through all results
        candidates = []
        page_token = None

        while True:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                maxResults=250,
                pageToken=page_token
            ).execute()

            events = events_result.get('items', [])

            for event in events:
                # Fix #6: skip cancelled events
                if event.get('status') == 'cancelled':
                    continue

                # Fix #6: skip events the calendar owner declined
                if self._user_declined(event):
                    continue

                # Filter: must be an external meeting (checking attendees)
                if not self._is_external_meeting(event, allowed_domains):
                    continue

                # Fix #7: handle all-day events safely
                start_obj = event.get('start', {})
                start_time = start_obj.get('dateTime') or start_obj.get('date')

                candidates.append({
                    "event_id": event.get('id'),
                    "summary": event.get('summary', ''),
                    "start": start_time,
                    "attendees": [a.get('email') for a in event.get('attendees', [])],
                    "conference_data": event.get('conferenceData', {}),
                    "attachments": event.get('attachments', [])
                })

            # Check for more pages
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break

        return candidates

    def _user_declined(self, event: Dict) -> bool:
        """Check if the calendar owner declined this meeting."""
        for attendee in event.get('attendees', []):
            if attendee.get('self') and attendee.get('responseStatus') == 'declined':
                return True
        return False

    def _is_external_meeting(self, event: Dict, allowed_domains: List[str] = None) -> bool:
        """Check if any attendee is external or matches allowed domains."""
        attendees = event.get('attendees', [])
        if not attendees:
            return False

        if allowed_domains:
            for attendee in attendees:
                email = attendee.get('email', '').lower()
                if any(email.endswith(f"@{d.lower()}") for d in allowed_domains):
                    return True
            return False

        # Heuristic: at least 2 attendees means a real meeting
        return len(attendees) >= 2

    def get_transcript_content(self, event: Dict) -> Optional[str]:
        """
        Attempt to fetch transcript content for a meeting.

        Fix #1: Google Meet auto-transcripts are saved as standalone Google Docs
        in Drive (typically "My Drive/Meet Transcripts/"), NOT as calendar event
        attachments. We search Drive by meeting summary + date.

        Falls back to checking event attachments for manually-attached docs.
        """
        # Strategy 1: Search Drive for Google Meet transcript
        transcript = self._search_drive_for_transcript(event)
        if transcript:
            return transcript

        # Strategy 2: Check event attachments (manually attached docs)
        attachments = event.get('attachments', [])
        for attachment in attachments:
            if attachment.get('mimeType') == 'application/vnd.google-apps.document':
                content = self._fetch_doc_content(attachment.get('fileId'))
                if content:
                    return content

        return None

    def _search_drive_for_transcript(self, event: Dict) -> Optional[str]:
        """
        Search Google Drive for a Meet transcript matching this event.
        Google Meet names transcripts like:
          "Meeting transcript - <summary> (YYYY-MM-DD)"
        """
        summary = event.get('summary', '')
        start = event.get('start', '')

        if not summary or not start:
            return None

        # Extract date portion (handles both dateTime and date formats)
        date_str = start[:10] if start else ''  # "2026-02-10" from ISO

        try:
            # Search for transcript docs matching the meeting
            # Google Meet transcript naming: "Meeting transcript - <summary> (<date>)"
            # Use broad search to catch variations
            query_parts = [
                "mimeType='application/vnd.google-apps.document'",
                "name contains 'transcript'",
            ]

            # Add summary words to narrow search (use first few significant words)
            # Remove non-alphanumeric chars and escape single quotes for Drive API query
            clean_summary = re.sub(r'[^\w\s]', '', summary).strip()
            summary_words = clean_summary.split()[:3]  # First 3 words
            for word in summary_words:
                if len(word) > 2:  # Skip tiny words like "a", "to"
                    safe_word = word.replace("'", "\\'")
                    query_parts.append(f"name contains '{safe_word}'")

            query = " and ".join(query_parts)

            results = self.drive_service.files().list(
                q=query,
                orderBy='modifiedTime desc',
                fields='files(id, name, modifiedTime)',
                pageSize=5
            ).execute()

            files = results.get('files', [])

            # If we found transcript files, try to match by date
            for f in files:
                fname = f.get('name', '')
                # Check if the transcript date matches the event date
                if date_str and date_str in fname:
                    content = self._fetch_doc_content(f['id'])
                    if content and len(content.strip()) > 50:
                        return content

            # If no date match, take the best candidate from results
            # (only if the modified time is within 24h of the meeting)
            if files and date_str:
                for f in files:
                    modified = f.get('modifiedTime', '')[:10]
                    if modified == date_str:
                        content = self._fetch_doc_content(f['id'])
                        if content and len(content.strip()) > 50:
                            return content

        except Exception as e:
            print(f"Drive transcript search error: {e}")

        return None

    def _fetch_doc_content(self, file_id: str) -> Optional[str]:
        """
        Fetch content of a Google Doc using Drive export.

        Fix #8: Uses Drive API export (text/plain) instead of Docs API,
        which is fully covered by the existing drive.readonly scope.
        """
        try:
            content = self.drive_service.files().export(
                fileId=file_id,
                mimeType='text/plain'
            ).execute()

            if isinstance(content, bytes):
                return content.decode('utf-8')
            return str(content)
        except Exception as e:
            print(f"Error fetching doc {file_id}: {e}")
            return None

    def get_attendee_domains(self, event: Dict) -> List[str]:
        """Extract unique attendee domains from a meeting event."""
        domains = set()
        for email in event.get('attendees', []):
            if isinstance(email, str) and '@' in email:
                domains.add(email.split('@')[1].lower())
            elif isinstance(email, dict):
                addr = email.get('email', '')
                if '@' in addr:
                    domains.add(addr.split('@')[1].lower())
        return list(domains)
