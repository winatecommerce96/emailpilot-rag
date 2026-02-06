"""
Vertex AI Ingestion for Email Repository Pipeline.

Creates searchable documents in Vertex AI Search with email metadata.
"""

import logging
from datetime import datetime, UTC
from typing import Dict, Any, Optional, List
from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions
from google.protobuf import struct_pb2

logger = logging.getLogger(__name__)


class EmailVertexIngestion:
    """
    Ingest email metadata into Vertex AI Search.

    Creates documents with category "email_asset" that can be searched
    using the RAG service.
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

        # Configure API endpoint
        self.client_options = ClientOptions(
            api_endpoint=f"{location}-discoveryengine.googleapis.com"
        )

        # Initialize document service client
        self.doc_client = discoveryengine.DocumentServiceClient(
            client_options=self.client_options
        )

        # Build branch path
        self.branch_path = (
            f"projects/{project_id}/locations/{location}/"
            f"dataStores/{data_store_id}/branches/default_branch"
        )

        logger.info(f"EmailVertexIngestion initialized for data store: {data_store_id}")

    def create_email_document(
        self,
        message_id: str,
        account_email: str,
        email_metadata: Dict[str, Any],
        categorization: Dict[str, Any],
        drive_file_id: str,
        screenshot_link: str
    ) -> Dict[str, Any]:
        """
        Create a searchable email document in Vertex AI.

        Args:
            message_id: Gmail message ID
            account_email: Source email account
            email_metadata: Email metadata (subject, sender, date)
            categorization: Categorization results from Gemini Vision
            drive_file_id: Google Drive file ID for screenshot
            screenshot_link: Web view link to screenshot

        Returns:
            Result dict with success status and document ID
        """
        # Generate unique document ID
        doc_id = f"email_{message_id}"

        # Extract metadata
        subject = email_metadata.get('subject', '')
        sender_email = email_metadata.get('sender_email', '')
        sender_name = email_metadata.get('sender', '')
        email_date = email_metadata.get('date')

        # Parse date for year/month/quarter
        year_received = ""
        month_received = ""
        quarter_received = ""

        if email_date:
            if isinstance(email_date, str):
                try:
                    email_date = datetime.fromisoformat(email_date.replace('Z', '+00:00'))
                except Exception:
                    email_date = None

            if email_date:
                year_received = str(email_date.year)
                month_received = str(email_date.month).zfill(2)
                quarter = (email_date.month - 1) // 3 + 1
                quarter_received = f"Q{quarter}"

        # Extract categorization data
        product_category = categorization.get('product_category', 'other')
        email_type = categorization.get('email_type', 'promotional')
        content_theme = categorization.get('content_theme', '')
        brand_name = categorization.get('brand_info', {}).get('brand_name', '')
        industry_vertical = categorization.get('brand_info', {}).get('industry_vertical', '')

        visual_elements = categorization.get('visual_elements', {})
        quality_assessment = categorization.get('quality_assessment', {})

        # Build comprehensive text_chunk for semantic search
        text_chunk = self._build_searchable_text(
            subject=subject,
            sender_name=sender_name,
            sender_email=sender_email,
            product_category=product_category,
            email_type=email_type,
            content_theme=content_theme,
            brand_name=brand_name,
            visual_elements=visual_elements
        )

        # Build document struct
        struct_data = struct_pb2.Struct()
        struct_data.update({
            # Required RAG fields
            "id": doc_id,
            "client_id": "email_repository",
            "title": subject,
            "category": "email_asset",
            "text_chunk": text_chunk,
            "source": f"gmail:{account_email}:{message_id}",

            # Email metadata
            "email_from": sender_email,
            "email_sender_name": sender_name,
            "email_subject": subject,
            "email_date": email_date.isoformat() if email_date else "",

            # Categorization
            "product_category": product_category,
            "email_type": email_type,
            "content_theme": content_theme,
            "brand_name": brand_name or "",
            "industry_vertical": industry_vertical or "",

            # Visual elements
            "has_hero_image": visual_elements.get("has_hero_image", False),
            "has_product_grid": visual_elements.get("has_product_grid", False),
            "text_heavy": visual_elements.get("text_heavy", False),
            "has_cta_button": visual_elements.get("has_cta_button", False),
            "color_scheme": visual_elements.get("color_scheme", ""),
            "layout_type": visual_elements.get("layout_type", ""),

            # Quality assessment
            "overall_quality": quality_assessment.get("overall_quality", ""),
            "design_sophistication": quality_assessment.get("design_sophistication", ""),
            "mobile_optimized": quality_assessment.get("mobile_optimized", False),

            # Time-based fields for filtering
            "year_received": year_received,
            "month_received": month_received,
            "quarter_received": quarter_received,

            # Screenshot references
            "drive_file_id": drive_file_id,
            "screenshot_drive_link": screenshot_link,
            "screenshot_thumbnail_link": f"https://drive.google.com/thumbnail?id={drive_file_id}&sz=w200",

            # Processing metadata
            "processed_at": datetime.now(UTC).isoformat() + "Z"
        })

        # Create document
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
            logger.debug(f"Created email document: {doc_id}")
            return {
                "success": True,
                "document_id": doc_id,
                "message_id": message_id,
                "subject": subject
            }
        except Exception as e:
            error_str = str(e).lower()
            # Check if document already exists
            if "409" in error_str or "exists" in error_str:
                logger.debug(f"Document {doc_id} exists, updating instead")
                return self._update_email_document(doc_id, struct_data, subject, message_id)
            logger.error(f"Failed to create document {doc_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message_id": message_id
            }

    def _update_email_document(
        self,
        doc_id: str,
        struct_data: struct_pb2.Struct,
        subject: str,
        message_id: str
    ) -> Dict[str, Any]:
        """Update an existing email document."""
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
            logger.debug(f"Updated email document: {doc_id}")
            return {
                "success": True,
                "document_id": doc_id,
                "message_id": message_id,
                "subject": subject,
                "updated": True
            }
        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message_id": message_id
            }

    def _build_searchable_text(
        self,
        subject: str,
        sender_name: str,
        sender_email: str,
        product_category: str,
        email_type: str,
        content_theme: str,
        brand_name: str,
        visual_elements: Dict[str, Any]
    ) -> str:
        """
        Build comprehensive text field for semantic search.

        Combines all searchable elements for Vertex AI embeddings.
        """
        parts = []

        # Subject line
        if subject:
            parts.append(f"Subject: {subject}")

        # Sender info
        if brand_name:
            parts.append(f"Brand: {brand_name}")
        elif sender_name:
            parts.append(f"From: {sender_name}")

        # Category and type
        parts.append(f"Category: {product_category}. Type: {email_type}.")

        # Content theme
        if content_theme:
            parts.append(f"Theme: {content_theme}.")

        # Visual elements
        visual_parts = []
        if visual_elements.get("has_hero_image"):
            visual_parts.append("hero image")
        if visual_elements.get("has_product_grid"):
            visual_parts.append("product grid")
        if visual_elements.get("has_cta_button"):
            visual_parts.append("call-to-action button")
        if visual_elements.get("text_heavy"):
            visual_parts.append("text-heavy design")

        if visual_parts:
            parts.append(f"Visual elements: {', '.join(visual_parts)}.")

        # Layout and color
        layout = visual_elements.get("layout_type", "")
        color_scheme = visual_elements.get("color_scheme", "")
        if layout or color_scheme:
            parts.append(f"Layout: {layout}. Colors: {color_scheme}.")

        return " ".join(parts)

    def delete_email_document(self, doc_id: str) -> bool:
        """
        Delete an email document from Vertex AI.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"
            request = discoveryengine.DeleteDocumentRequest(name=doc_name)
            self.doc_client.delete_document(request=request)
            logger.info(f"Deleted email document: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def search_emails(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Search indexed emails using semantic search.

        Args:
            query: Natural language search query
            filters: Optional filters (product_category, email_type, year, month, brand)
            page_size: Maximum results to return

        Returns:
            Search results with email metadata
        """
        try:
            # Initialize search client
            search_client = discoveryengine.SearchServiceClient(
                client_options=self.client_options
            )

            # Build serving config path
            serving_config = search_client.serving_config_path(
                project=self.project_id,
                location=self.location,
                data_store=self.data_store_id,
                serving_config="default_search",
            )

            # Build filter string
            filter_parts = ['category: ANY("email_asset")']

            if filters:
                if filters.get("product_category"):
                    filter_parts.append(f'product_category: ANY("{filters["product_category"]}")')
                if filters.get("email_type"):
                    filter_parts.append(f'email_type: ANY("{filters["email_type"]}")')
                if filters.get("year"):
                    filter_parts.append(f'year_received: ANY("{filters["year"]}")')
                if filters.get("month"):
                    filter_parts.append(f'month_received: ANY("{filters["month"]}")')
                if filters.get("brand"):
                    filter_parts.append(f'brand_name: ANY("{filters["brand"]}")')

            filter_str = " AND ".join(filter_parts)

            # Execute search
            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=page_size,
                filter=filter_str,
                query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                    condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
                ),
            )

            response = search_client.search(request)

            # Parse results
            emails = []
            for result in response.results:
                data = dict(result.document.struct_data)
                emails.append({
                    "doc_id": result.document.id,
                    "message_id": data.get("source", "").split(":")[-1],
                    "subject": data.get("email_subject", ""),
                    "sender": data.get("email_sender_name", "") or data.get("email_from", ""),
                    "date": data.get("email_date", ""),
                    "product_category": data.get("product_category", ""),
                    "email_type": data.get("email_type", ""),
                    "brand_name": data.get("brand_name", ""),
                    "screenshot_link": data.get("screenshot_drive_link", ""),
                    "thumbnail_link": data.get("screenshot_thumbnail_link", ""),
                    "visual_elements": {
                        "has_hero_image": data.get("has_hero_image", False),
                        "has_product_grid": data.get("has_product_grid", False),
                        "layout_type": data.get("layout_type", "")
                    }
                })

            return {
                "success": True,
                "query": query,
                "total": len(emails),
                "emails": emails
            }

        except Exception as e:
            logger.error(f"Email search failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "emails": []
            }

    def list_emails(
        self,
        page_size: int = 100,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List indexed email documents.

        Args:
            page_size: Maximum results
            category: Optional category filter

        Returns:
            List of email document metadata
        """
        try:
            request = discoveryengine.ListDocumentsRequest(
                parent=self.branch_path,
                page_size=min(page_size, 1000)
            )

            response = self.doc_client.list_documents(request=request)

            emails = []
            for doc in response:
                if doc.struct_data:
                    data = dict(doc.struct_data)
                    if data.get("category") == "email_asset":
                        if category and data.get("product_category") != category:
                            continue
                        emails.append({
                            "doc_id": doc.name.split("/")[-1],
                            "subject": data.get("email_subject", ""),
                            "product_category": data.get("product_category", ""),
                            "email_type": data.get("email_type", ""),
                            "brand_name": data.get("brand_name", ""),
                            "date": data.get("email_date", ""),
                            "thumbnail_link": data.get("screenshot_thumbnail_link", "")
                        })

            logger.info(f"Listed {len(emails)} email documents")
            return emails

        except Exception as e:
            logger.error(f"Failed to list emails: {e}")
            return []

    def get_email_count(self, category: Optional[str] = None) -> int:
        """
        Get count of indexed email documents.

        Args:
            category: Optional category filter

        Returns:
            Number of indexed emails
        """
        emails = self.list_emails(page_size=1000, category=category)
        return len(emails)

    def get_category_stats(self) -> Dict[str, int]:
        """
        Get count of emails by category.

        Returns:
            Dict mapping category to count
        """
        emails = self.list_emails(page_size=1000)
        stats = {}
        for email in emails:
            category = email.get("product_category", "other")
            stats[category] = stats.get(category, 0) + 1
        return stats
