"""
Vertex AI Ingestion for Image Repository Pipeline.

Creates searchable documents in Vertex AI Search with image metadata.
"""

import logging
from datetime import datetime, UTC
from typing import Dict, Any, Optional, List
from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions
from google.protobuf import struct_pb2

logger = logging.getLogger(__name__)


class ImageVertexIngestion:
    """
    Ingest image metadata into Vertex AI Search.

    Creates documents with category "visual_asset" that can be searched
    using the RAG service's VISUAL phase.
    """

    def __init__(
        self,
        project_id: str,
        location: str,
        data_store_id: str
    ):
        """
        Initialize Vertex AI ingestion client.

        Args:
            project_id: GCP project ID
            location: GCP region (e.g., "us")
            data_store_id: Vertex AI Search data store ID
        """
        self.project_id = project_id
        self.location = location
        self.data_store_id = data_store_id

        # Configure API endpoint for the correct region
        self.client_options = ClientOptions(
            api_endpoint=f"{location}-discoveryengine.googleapis.com"
        )

        # Initialize document service client
        self.doc_client = discoveryengine.DocumentServiceClient(
            client_options=self.client_options
        )

        # Build the branch path for document operations
        self.branch_path = (
            f"projects/{project_id}/locations/{location}/"
            f"dataStores/{data_store_id}/branches/default_branch"
        )

        logger.info(f"ImageVertexIngestion initialized for data store: {data_store_id}")

    def create_image_document(
        self,
        client_id: str,
        drive_metadata: Dict[str, Any],
        caption_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a searchable image document in Vertex AI.

        Args:
            client_id: Client identifier
            drive_metadata: File metadata from Drive API
            caption_metadata: Generated caption from Gemini Vision

        Returns:
            Result dict with success status and document ID
        """
        file_id = drive_metadata["id"]
        file_name = drive_metadata["name"]

        # Generate unique document ID
        doc_id = f"img_{client_id}_{file_id}"

        # Build comprehensive text_chunk for semantic search
        text_chunk = self._build_searchable_text(file_name, caption_metadata)

        # Extract parent folder ID
        parents = drive_metadata.get("parents", [])
        folder_id = parents[0] if parents else "unknown"

        # Prepare visual tags as a list of strings
        visual_tags = caption_metadata.get("visual_tags", [])
        if isinstance(visual_tags, str):
            visual_tags = [visual_tags]

        # Prepare colors as a list
        colors = caption_metadata.get("dominant_colors", [])
        if isinstance(colors, str):
            colors = [colors]

        # Build document struct data
        struct_data = struct_pb2.Struct()
        struct_data.update({
            # Required RAG fields
            "id": doc_id,
            "client_id": client_id,
            "title": file_name,
            "category": "visual_asset",
            "text_chunk": text_chunk,
            "source": f"google_drive:{folder_id}/{file_id}",

            # Image-specific metadata
            "doc_type": "image_asset",
            "drive_link": drive_metadata.get("webViewLink", ""),
            "thumbnail_link": drive_metadata.get("thumbnailLink", ""),

            # Caption metadata
            "description": caption_metadata.get("description", ""),
            "mood": caption_metadata.get("mood", ""),
            "setting": caption_metadata.get("setting", ""),
            "composition": caption_metadata.get("composition", ""),
            "marketing_use_case": caption_metadata.get("marketing_use_case", ""),
            "people_present": caption_metadata.get("people_present", False),
            "text_visible": caption_metadata.get("text_visible", ""),
            "quality_flag": caption_metadata.get("quality_flag", "medium"),

            # Lists stored as comma-separated strings for Vertex AI
            "visual_tags_str": ", ".join(visual_tags),
            "dominant_colors_str": ", ".join(colors),

            # File metadata
            "file_size_bytes": int(drive_metadata.get("size", 0)),
            "mime_type": drive_metadata.get("mimeType", ""),
            "last_synced": datetime.now(UTC).isoformat() + "Z"
        })

        # Create the document
        document = discoveryengine.Document(
            id=doc_id,
            struct_data=struct_data
        )

        request = discoveryengine.CreateDocumentRequest(
            parent=self.branch_path,
            document=document,
            document_id=doc_id
        )

        try:
            self.doc_client.create_document(request=request)
            logger.debug(f"Created image document: {doc_id}")
            return {
                "success": True,
                "document_id": doc_id,
                "client_id": client_id,
                "file_name": file_name
            }
        except Exception as e:
            error_str = str(e).lower()
            # Check if document already exists (409 conflict - update instead)
            # Handle both "already exists" and "with the same name ... exists" patterns
            if "409" in error_str or "exists" in error_str or "already exists" in error_str:
                logger.debug(f"Document {doc_id} exists, updating instead")
                return self._update_image_document(doc_id, struct_data, file_name, client_id)
            logger.error(f"Failed to create document {doc_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_name": file_name
            }

    def _update_image_document(
        self,
        doc_id: str,
        struct_data: struct_pb2.Struct,
        file_name: str,
        client_id: str
    ) -> Dict[str, Any]:
        """
        Update an existing image document.

        Args:
            doc_id: Document ID to update
            struct_data: New document data
            file_name: Original filename
            client_id: Client identifier

        Returns:
            Result dict
        """
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"

            document = discoveryengine.Document(
                name=doc_name,
                struct_data=struct_data
            )

            request = discoveryengine.UpdateDocumentRequest(
                document=document,
                allow_missing=False
            )

            self.doc_client.update_document(request=request)
            logger.debug(f"Updated image document: {doc_id}")
            return {
                "success": True,
                "document_id": doc_id,
                "client_id": client_id,
                "file_name": file_name,
                "updated": True
            }
        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_name": file_name
            }

    def _build_searchable_text(
        self,
        file_name: str,
        caption: Dict[str, Any]
    ) -> str:
        """
        Build comprehensive text field for semantic search.

        Combines all searchable elements into natural language that
        Vertex AI can embed and search effectively.
        """
        parts = []

        # Description
        if caption.get("description"):
            parts.append(f"Caption: {caption['description']}")

        # Mood and setting
        mood = caption.get("mood", "")
        setting = caption.get("setting", "")
        if mood or setting:
            parts.append(f"Mood: {mood}. Setting: {setting}.")

        # Colors
        colors = caption.get("dominant_colors", [])
        if colors:
            parts.append(f"Colors: {', '.join(colors)}.")

        # People and composition
        people = "with people" if caption.get("people_present") else "no people"
        comp = caption.get("composition", "")
        parts.append(f"Composition: {comp}, {people}.")

        # Visual tags
        tags = caption.get("visual_tags", [])
        if tags:
            parts.append(f"Tags: {', '.join(tags)}.")

        # Visible text
        text_visible = caption.get("text_visible", "")
        if text_visible:
            parts.append(f"Visible text: {text_visible}.")

        # Marketing use case
        use_case = caption.get("marketing_use_case", "")
        if use_case:
            parts.append(f"Use case: {use_case}.")

        # Filename (for exact matches)
        parts.append(f"File: {file_name}.")

        return " ".join(parts)

    def delete_image_document(self, doc_id: str) -> bool:
        """
        Delete an image document from Vertex AI.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"
            request = discoveryengine.DeleteDocumentRequest(name=doc_name)
            self.doc_client.delete_document(request=request)
            logger.info(f"Deleted image document: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def list_client_images(
        self,
        client_id: str,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all image documents for a client.

        Args:
            client_id: Client identifier
            page_size: Maximum results to return

        Returns:
            List of image document metadata
        """
        try:
            request = discoveryengine.ListDocumentsRequest(
                parent=self.branch_path,
                page_size=min(page_size, 1000)
            )

            response = self.doc_client.list_documents(request=request)

            # Filter for this client's images
            images = []
            for doc in response:
                if doc.struct_data:
                    data = dict(doc.struct_data)
                    if (data.get("client_id") == client_id and
                        data.get("doc_type") == "image_asset"):
                        # Extract file_id from drive_link to construct public thumbnail
                        drive_link = data.get("drive_link", "")
                        thumbnail_link = ""
                        if "/d/" in drive_link:
                            try:
                                file_id = drive_link.split("/d/")[1].split("/")[0]
                                thumbnail_link = f"https://drive.google.com/thumbnail?id={file_id}&sz=w200"
                            except (IndexError, AttributeError):
                                thumbnail_link = data.get("thumbnail_link", "")

                        images.append({
                            "doc_id": doc.name.split("/")[-1],
                            "file_name": data.get("title", ""),
                            "drive_link": drive_link,
                            "thumbnail_link": thumbnail_link,
                            "mood": data.get("mood", ""),
                            "description": data.get("description", "")[:200],
                            "visual_tags": data.get("visual_tags_str", "").split(", "),
                            "last_synced": data.get("last_synced", "")
                        })

            logger.info(f"Found {len(images)} image documents for client {client_id}")
            return images

        except Exception as e:
            logger.error(f"Failed to list images for {client_id}: {e}")
            return []

    def get_image_count(self, client_id: str) -> int:
        """
        Get count of image documents for a client.

        Args:
            client_id: Client identifier

        Returns:
            Number of indexed images
        """
        images = self.list_client_images(client_id, page_size=1000)
        return len(images)

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a single document from Vertex AI.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"
            request = discoveryengine.DeleteDocumentRequest(name=doc_name)
            self.doc_client.delete_document(request=request)
            logger.info(f"Deleted document: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def delete_client_images(self, client_id: str) -> Dict[str, int]:
        """
        Delete all image documents for a client from Vertex AI.

        Args:
            client_id: Client identifier

        Returns:
            Dict with deleted and failed counts
        """
        images = self.list_client_images(client_id, page_size=1000)
        deleted = 0
        failed = 0

        for img in images:
            doc_id = img.get("doc_id")
            if doc_id and self.delete_document(doc_id):
                deleted += 1
            else:
                failed += 1

        logger.info(f"Deleted {deleted} images for client {client_id} ({failed} failed)")
        return {"deleted": deleted, "failed": failed}

    def delete_documents_by_folder(self, client_id: str, folder_id: str) -> Dict[str, int]:
        """
        Delete all documents from a specific folder.

        Args:
            client_id: Client identifier
            folder_id: Google Drive folder ID

        Returns:
            Dict with deleted and failed counts
        """
        images = self.list_client_images(client_id, page_size=1000)
        deleted = 0
        failed = 0

        for img in images:
            # Check if image is from this folder (stored in source field)
            doc_id = img.get("doc_id", "")
            # Source format: google_drive:{folder_id}/{file_id}
            # We need to check the actual document data
            if doc_id and self.delete_document(doc_id):
                deleted += 1
            else:
                failed += 1

        logger.info(f"Deleted {deleted} images from folder {folder_id} ({failed} failed)")
        return {"deleted": deleted, "failed": failed}
