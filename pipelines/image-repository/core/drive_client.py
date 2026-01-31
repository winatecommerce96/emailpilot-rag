"""
Google Drive Client for Image Repository Pipeline.

Handles service account authentication and image discovery from shared drives.
"""

import io
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

logger = logging.getLogger(__name__)


class GoogleDriveClient:
    """
    Google Drive client for image discovery using service account auth.

    Service account must be added to shared drives with "Viewer" permissions.
    """

    SCOPES = [
        'https://www.googleapis.com/auth/drive.readonly',
        'https://www.googleapis.com/auth/drive.metadata.readonly'
    ]

    DEFAULT_SUPPORTED_FORMATS = [
        'image/jpeg', 'image/png', 'image/webp', 'image/gif'
    ]

    SHORTCUT_MIME_TYPE = 'application/vnd.google-apps.shortcut'
    FOLDER_MIME_TYPE = 'application/vnd.google-apps.folder'

    def __init__(self, service_account_json: Optional[str] = None):
        """
        Initialize Drive client with service account credentials.

        Args:
            service_account_json: JSON string of service account credentials.
                                  If None, uses Application Default Credentials.
        """
        self.service = None
        self._authenticate(service_account_json)

    def _authenticate(self, service_account_json: Optional[str] = None):
        """Authenticate with Google Drive API."""
        try:
            if service_account_json:
                # Parse JSON string to dict
                if isinstance(service_account_json, str):
                    creds_dict = json.loads(service_account_json)
                else:
                    creds_dict = service_account_json

                self.creds = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=self.SCOPES
                )
            else:
                # Use Application Default Credentials
                import google.auth
                self.creds, _ = google.auth.default(scopes=self.SCOPES)

            self.service = build('drive', 'v3', credentials=self.creds)
            logger.info("Google Drive Client authenticated successfully")

        except Exception as e:
            logger.error(f"Failed to authenticate Google Drive Client: {e}")
            raise

    def list_images_in_folder(
        self,
        folder_id: str,
        modified_after: Optional[datetime] = None,
        supported_formats: Optional[List[str]] = None,
        recursive: bool = True,
        max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        List all images in a folder, optionally filtered by modification time.

        Args:
            folder_id: Google Drive folder ID
            modified_after: Only return files modified after this timestamp
            supported_formats: MIME types to include (e.g., ['image/jpeg'])
            recursive: If True, also search subfolders
            max_results: Maximum number of files to return

        Returns:
            List of file metadata dicts with keys: id, name, mimeType,
            modifiedTime, size, webViewLink, thumbnailLink, parents
        """
        if not self.service:
            raise ValueError("Drive client not initialized")

        formats = supported_formats or self.DEFAULT_SUPPORTED_FORMATS

        # Build MIME type filter
        mime_filter = " or ".join([f"mimeType='{fmt}'" for fmt in formats])

        # Build query
        query_parts = [
            f"'{folder_id}' in parents",
            f"({mime_filter})",
            "trashed = false"
        ]

        if modified_after:
            iso_time = modified_after.strftime('%Y-%m-%dT%H:%M:%S')
            query_parts.append(f"modifiedTime > '{iso_time}'")

        query = " and ".join(query_parts)

        # Fetch files with pagination
        files = []
        page_token = None

        while len(files) < max_results:
            try:
                results = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id, name, mimeType, size, '
                           'modifiedTime, createdTime, webViewLink, thumbnailLink, '
                           'parents, imageMediaMetadata)',
                    pageSize=min(100, max_results - len(files)),
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()

                files.extend(results.get('files', []))
                page_token = results.get('nextPageToken')

                if not page_token:
                    break

            except HttpError as e:
                logger.error(f"Drive API error listing folder {folder_id}: {e}")
                raise

        logger.info(f"Found {len(files)} direct images in folder {folder_id}")

        # Also resolve image shortcuts in this folder
        shortcut_images = self._list_shortcuts_in_folder(folder_id)
        files.extend(shortcut_images)

        if shortcut_images:
            logger.info(f"Found {len(shortcut_images)} images via shortcuts in folder {folder_id}")

        # Optionally search subfolders (including shortcut folders)
        if recursive:
            subfolders = self._list_subfolders(folder_id)
            for subfolder in subfolders:
                if len(files) >= max_results:
                    break
                subfolder_files = self.list_images_in_folder(
                    folder_id=subfolder['id'],
                    modified_after=modified_after,
                    supported_formats=formats,
                    recursive=True,
                    max_results=max_results - len(files)
                )
                files.extend(subfolder_files)

        return files[:max_results]

    def _list_subfolders(self, folder_id: str) -> List[Dict[str, str]]:
        """List immediate subfolders of a folder, including shortcut targets."""
        try:
            # Query for both actual folders and shortcuts
            query = (f"'{folder_id}' in parents and "
                     f"(mimeType='{self.FOLDER_MIME_TYPE}' or mimeType='{self.SHORTCUT_MIME_TYPE}') "
                     f"and trashed=false")
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, shortcutDetails)',
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            folders = []
            for file in results.get('files', []):
                if file.get('mimeType') == self.SHORTCUT_MIME_TYPE:
                    # Resolve shortcut to get target
                    shortcut_details = file.get('shortcutDetails', {})
                    target_id = shortcut_details.get('targetId')
                    target_mime = shortcut_details.get('targetMimeType')

                    if target_id and target_mime == self.FOLDER_MIME_TYPE:
                        logger.info(f"Resolved folder shortcut '{file.get('name')}' -> {target_id}")
                        folders.append({'id': target_id, 'name': file.get('name')})
                else:
                    folders.append({'id': file['id'], 'name': file.get('name')})

            return folders
        except HttpError as e:
            logger.warning(f"Failed to list subfolders of {folder_id}: {e}")
            return []

    def _resolve_shortcut(self, file: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Resolve a shortcut to get the actual target file metadata.

        Args:
            file: Shortcut file metadata containing shortcutDetails

        Returns:
            Target file metadata or None if not resolvable
        """
        shortcut_details = file.get('shortcutDetails', {})
        target_id = shortcut_details.get('targetId')
        target_mime = shortcut_details.get('targetMimeType', '')

        if not target_id:
            logger.warning(f"Shortcut {file.get('name')} has no target ID")
            return None

        # Check if target is an image
        if target_mime.startswith('image/'):
            try:
                target_metadata = self.get_file_metadata(target_id)
                logger.debug(f"Resolved image shortcut '{file.get('name')}' -> {target_metadata.get('name')}")
                return target_metadata
            except HttpError as e:
                logger.warning(f"Failed to resolve shortcut {file.get('name')}: {e}")
                return None

        return None

    def _list_shortcuts_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """
        List shortcuts in a folder and resolve image shortcuts.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            List of resolved image file metadata from shortcuts
        """
        try:
            query = (f"'{folder_id}' in parents and "
                     f"mimeType='{self.SHORTCUT_MIME_TYPE}' and trashed=false")

            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, mimeType, shortcutDetails)',
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()

            resolved_images = []
            for shortcut in results.get('files', []):
                shortcut_details = shortcut.get('shortcutDetails', {})
                target_mime = shortcut_details.get('targetMimeType', '')

                # Only resolve image shortcuts (folder shortcuts handled in _list_subfolders)
                if target_mime.startswith('image/'):
                    resolved = self._resolve_shortcut(shortcut)
                    if resolved:
                        resolved_images.append(resolved)

            if resolved_images:
                logger.info(f"Resolved {len(resolved_images)} image shortcuts in folder {folder_id}")

            return resolved_images

        except HttpError as e:
            logger.warning(f"Failed to list shortcuts in {folder_id}: {e}")
            return []

    def download_image_bytes(self, file_id: str) -> bytes:
        """
        Download image file as bytes for Gemini vision processing.

        Args:
            file_id: Google Drive file ID

        Returns:
            Image file bytes
        """
        if not self.service:
            raise ValueError("Drive client not initialized")

        try:
            request = self.service.files().get_media(fileId=file_id)
            file_bytes = io.BytesIO()

            downloader = MediaIoBaseDownload(file_bytes, request)

            done = False
            while not done:
                status, done = downloader.next_chunk()

            return file_bytes.getvalue()

        except HttpError as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            raise

    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Get detailed metadata for a single file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dictionary
        """
        if not self.service:
            raise ValueError("Drive client not initialized")

        try:
            return self.service.files().get(
                fileId=file_id,
                fields='id, name, mimeType, size, modifiedTime, createdTime, '
                       'webViewLink, thumbnailLink, parents, imageMediaMetadata',
                supportsAllDrives=True
            ).execute()
        except HttpError as e:
            logger.error(f"Failed to fetch metadata for {file_id}: {e}")
            raise

    def get_folder_info(self, folder_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a folder.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            Folder metadata or None if not found/accessible
        """
        try:
            return self.service.files().get(
                fileId=folder_id,
                fields='id, name, mimeType, webViewLink',
                supportsAllDrives=True
            ).execute()
        except HttpError as e:
            if e.resp.status == 404:
                logger.warning(f"Folder not found: {folder_id}")
                return None
            logger.error(f"Failed to get folder info {folder_id}: {e}")
            return None

    def verify_folder_access(self, folder_id: str) -> bool:
        """
        Verify that the service account has access to a folder.

        Args:
            folder_id: Google Drive folder ID

        Returns:
            True if accessible, False otherwise
        """
        folder_info = self.get_folder_info(folder_id)
        if folder_info:
            logger.info(f"Verified access to folder: {folder_info.get('name', folder_id)}")
            return True
        return False

    def get_thumbnail_url(self, file_id: str, size: int = 400) -> str:
        """
        Get thumbnail URL for an image.

        Args:
            file_id: Google Drive file ID
            size: Thumbnail size in pixels

        Returns:
            Thumbnail URL
        """
        return f"https://drive.google.com/thumbnail?id={file_id}&sz=w{size}"

    def get_direct_link(self, file_id: str) -> str:
        """
        Get direct link to view/open a file.

        Args:
            file_id: Google Drive file ID

        Returns:
            Direct view link
        """
        return f"https://drive.google.com/file/d/{file_id}/view"
