"""
Google Drive Uploader for Email Screenshots.

Uploads screenshots with organized folder hierarchy:
EmailScreenshots/{category}/{year}/{month}/
"""

import json
import logging
from io import BytesIO
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of a Drive upload operation."""
    success: bool
    file_id: Optional[str] = None
    web_view_link: Optional[str] = None
    thumbnail_link: Optional[str] = None
    error: Optional[str] = None
    folder_path: Optional[str] = None


class DriveUploader:
    """
    Upload email screenshots to Google Drive with organized folder structure.

    Folder hierarchy:
    EmailScreenshots/
    ├── fashion/
    │   ├── 2024/
    │   │   ├── 01/
    │   │   ├── 02/
    │   │   └── ...
    │   └── 2025/
    ├── food/
    ├── beauty/
    └── ...
    """

    SCOPES = ['https://www.googleapis.com/auth/drive.file']

    def __init__(
        self,
        service_account_json: str,
        root_folder_id: Optional[str] = None,
        root_folder_name: str = "EmailScreenshots"
    ):
        """
        Initialize Drive uploader.

        Args:
            service_account_json: Service account key JSON (string or path)
            root_folder_id: Optional root folder ID (if None, will create/find)
            root_folder_name: Name for root folder
        """
        self.service = self._build_service(service_account_json)
        self.root_folder_name = root_folder_name
        self._root_folder_id = root_folder_id
        self._folder_cache: Dict[str, str] = {}

    def _build_service(self, service_account_json: str):
        """Build authenticated Drive API service."""
        if service_account_json.startswith('{'):
            credentials_info = json.loads(service_account_json)
        else:
            with open(service_account_json, 'r') as f:
                credentials_info = json.load(f)

        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=self.SCOPES
        )

        service = build('drive', 'v3', credentials=credentials)
        logger.info("Drive client initialized")
        return service

    @property
    def root_folder_id(self) -> str:
        """Get or create root folder ID."""
        if self._root_folder_id is None:
            self._root_folder_id = self._get_or_create_root_folder()
        return self._root_folder_id

    def _get_or_create_root_folder(self) -> str:
        """Get or create the root EmailScreenshots folder."""
        # Search for existing folder
        query = f"name = '{self.root_folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

        try:
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = response.get('files', [])
            if files:
                folder_id = files[0]['id']
                logger.info(f"Found existing root folder: {folder_id}")
                return folder_id

            # Create new folder
            folder_metadata = {
                'name': self.root_folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            logger.info(f"Created root folder: {folder_id}")
            return folder_id

        except HttpError as e:
            logger.error(f"Error getting/creating root folder: {e}")
            raise

    def _get_or_create_folder(
        self,
        name: str,
        parent_id: str
    ) -> str:
        """
        Get or create a folder within a parent folder.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Folder ID
        """
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        # Search for existing folder
        query = f"name = '{name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"

        try:
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)'
            ).execute()

            files = response.get('files', [])
            if files:
                folder_id = files[0]['id']
                self._folder_cache[cache_key] = folder_id
                return folder_id

            # Create new folder
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }

            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()

            folder_id = folder.get('id')
            self._folder_cache[cache_key] = folder_id
            logger.info(f"Created folder: {self.root_folder_name}/{name} -> {folder_id}")
            return folder_id

        except HttpError as e:
            logger.error(f"Error getting/creating folder {name}: {e}")
            raise

    def _get_folder_path(
        self,
        category: str,
        year: str,
        month: str
    ) -> str:
        """
        Get or create the full folder path for a screenshot.

        Args:
            category: Email category (fashion, food, etc.)
            year: Year string (e.g., "2025")
            month: Month string (e.g., "01")

        Returns:
            Leaf folder ID
        """
        # Create category folder
        category_folder = self._get_or_create_folder(
            category.lower(),
            self.root_folder_id
        )

        # Create year folder
        year_folder = self._get_or_create_folder(
            year,
            category_folder
        )

        # Create month folder
        month_folder = self._get_or_create_folder(
            month.zfill(2),  # Ensure 2 digits
            year_folder
        )

        return month_folder

    def upload_screenshot(
        self,
        image_bytes: bytes,
        filename: str,
        category: str,
        year: str,
        month: str,
        mime_type: str = "image/png"
    ) -> UploadResult:
        """
        Upload screenshot to organized folder structure.

        Args:
            image_bytes: PNG/JPEG image bytes
            filename: Filename for the screenshot
            category: Email category for folder organization
            year: Year for folder organization
            month: Month for folder organization
            mime_type: MIME type of the image

        Returns:
            UploadResult with file ID and links
        """
        folder_path = f"{category}/{year}/{month}"

        try:
            # Get/create folder hierarchy
            folder_id = self._get_folder_path(category, year, month)

            # Ensure unique filename
            safe_filename = self._sanitize_filename(filename)
            if not safe_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                extension = '.png' if 'png' in mime_type else '.jpg'
                safe_filename += extension

            # Upload file
            file_metadata = {
                'name': safe_filename,
                'parents': [folder_id]
            }

            media = MediaIoBaseUpload(
                BytesIO(image_bytes),
                mimetype=mime_type,
                resumable=True
            )

            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            file_id = file.get('id')
            web_view_link = file.get('webViewLink')

            # Generate thumbnail link
            thumbnail_link = f"https://drive.google.com/thumbnail?id={file_id}&sz=w200"

            logger.info(f"Uploaded screenshot: {folder_path}/{safe_filename} -> {file_id}")

            return UploadResult(
                success=True,
                file_id=file_id,
                web_view_link=web_view_link,
                thumbnail_link=thumbnail_link,
                folder_path=folder_path
            )

        except HttpError as e:
            logger.error(f"Drive upload failed for {filename}: {e}")
            return UploadResult(
                success=False,
                error=str(e),
                folder_path=folder_path
            )

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for Drive compatibility.

        Args:
            filename: Original filename

        Returns:
            Safe filename
        """
        # Remove/replace invalid characters
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        safe_name = filename
        for char in invalid_chars:
            safe_name = safe_name.replace(char, '_')

        # Limit length
        max_length = 200
        if len(safe_name) > max_length:
            # Preserve extension
            parts = safe_name.rsplit('.', 1)
            if len(parts) == 2:
                name, ext = parts
                safe_name = name[:max_length - len(ext) - 1] + '.' + ext
            else:
                safe_name = safe_name[:max_length]

        return safe_name

    def upload_batch(
        self,
        screenshots: List[Dict[str, Any]]
    ) -> List[UploadResult]:
        """
        Upload multiple screenshots.

        Args:
            screenshots: List of dicts with keys:
                - image_bytes: bytes
                - filename: str
                - category: str
                - year: str
                - month: str
                - mime_type: str (optional)

        Returns:
            List of UploadResult objects
        """
        results = []

        for screenshot in screenshots:
            result = self.upload_screenshot(
                image_bytes=screenshot['image_bytes'],
                filename=screenshot['filename'],
                category=screenshot['category'],
                year=screenshot['year'],
                month=screenshot['month'],
                mime_type=screenshot.get('mime_type', 'image/png')
            )
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(f"Batch upload complete: {successful}/{len(screenshots)} successful")

        return results

    def list_folder_contents(
        self,
        category: Optional[str] = None,
        year: Optional[str] = None,
        month: Optional[str] = None,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List files in a specific folder.

        Args:
            category: Optional category filter
            year: Optional year filter
            month: Optional month filter
            page_size: Maximum files to return

        Returns:
            List of file metadata dicts
        """
        # Determine folder to list
        if category and year and month:
            try:
                folder_id = self._get_folder_path(category, year, month)
            except Exception:
                return []
        elif category and year:
            try:
                category_folder = self._get_or_create_folder(category, self.root_folder_id)
                folder_id = self._get_or_create_folder(year, category_folder)
            except Exception:
                return []
        elif category:
            try:
                folder_id = self._get_or_create_folder(category, self.root_folder_id)
            except Exception:
                return []
        else:
            folder_id = self.root_folder_id

        try:
            query = f"'{folder_id}' in parents and trashed = false"
            response = self.service.files().list(
                q=query,
                pageSize=page_size,
                fields='files(id, name, mimeType, size, createdTime, webViewLink)'
            ).execute()

            return response.get('files', [])

        except HttpError as e:
            logger.error(f"Error listing folder contents: {e}")
            return []

    def get_folder_stats(self) -> Dict[str, int]:
        """
        Get statistics about folder contents.

        Returns:
            Dict with category counts
        """
        stats = {}

        try:
            # List category folders
            query = f"'{self.root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            response = self.service.files().list(
                q=query,
                fields='files(id, name)'
            ).execute()

            for folder in response.get('files', []):
                category = folder['name']
                # Count files in this category (recursive would be expensive)
                stats[category] = self._count_files_recursive(folder['id'])

        except HttpError as e:
            logger.error(f"Error getting folder stats: {e}")

        return stats

    def _count_files_recursive(self, folder_id: str, depth: int = 0) -> int:
        """
        Count files recursively in a folder (limited depth).

        Args:
            folder_id: Folder to count
            depth: Current recursion depth

        Returns:
            File count
        """
        if depth > 3:  # Limit depth to year/month structure
            return 0

        count = 0
        try:
            query = f"'{folder_id}' in parents and trashed = false"
            response = self.service.files().list(
                q=query,
                pageSize=1000,
                fields='files(id, mimeType)'
            ).execute()

            for file in response.get('files', []):
                if file['mimeType'] == 'application/vnd.google-apps.folder':
                    count += self._count_files_recursive(file['id'], depth + 1)
                else:
                    count += 1

        except HttpError as e:
            logger.warning(f"Error counting files in {folder_id}: {e}")

        return count

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Drive.

        Args:
            file_id: File ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            self.service.files().delete(fileId=file_id).execute()
            logger.info(f"Deleted file: {file_id}")
            return True
        except HttpError as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            return False
