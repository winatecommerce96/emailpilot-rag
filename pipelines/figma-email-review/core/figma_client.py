"""
Figma REST API Client for fetching email designs.

Provides methods to:
- Fetch file structure and metadata
- Export frames as images
- Extract text content from nodes
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class FigmaTextNode(BaseModel):
    """Represents a text node in Figma."""
    id: str
    name: str
    characters: str  # The actual text content
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[int] = None
    text_align: Optional[str] = None
    fills: List[Dict[str, Any]] = Field(default_factory=list)


class FigmaNode(BaseModel):
    """Represents a node in Figma's document tree."""
    id: str
    name: str
    type: str  # FRAME, TEXT, GROUP, COMPONENT, INSTANCE, etc.
    visible: bool = True
    absolute_bounding_box: Optional[Dict[str, float]] = None
    children: Optional[List["FigmaNode"]] = None


class FigmaFrame(BaseModel):
    """Represents a frame (potential email design) in Figma."""
    id: str
    name: str
    width: float
    height: float
    background_color: Optional[Dict[str, float]] = None
    children_count: int = 0


class EmailDesign(BaseModel):
    """Represents a complete email design extracted from Figma."""
    frame_id: str
    frame_name: str
    file_key: str
    file_name: str
    version_id: Optional[str] = None
    last_modified: Optional[datetime] = None
    width: float
    height: float
    image_url: Optional[str] = None
    image_bytes: Optional[bytes] = None
    text_content: List[FigmaTextNode] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


# =============================================================================
# Figma Client
# =============================================================================

class FigmaClient:
    """
    Figma REST API client for fetching email design files.

    API Endpoints used:
    - GET /v1/files/:key - Get file metadata and structure
    - GET /v1/files/:key/nodes?ids=:ids - Get specific node data
    - GET /v1/images/:key?ids=:ids - Export nodes as images
    - GET /v1/files/:key/versions - Get version history
    """

    def __init__(
        self,
        access_token: str,
        api_base_url: str = "https://api.figma.com/v1",
        timeout: int = 30,
        image_scale: float = 2.0,
        image_format: str = "png"
    ):
        """
        Initialize Figma client.

        Args:
            access_token: Figma personal access token
            api_base_url: Base URL for Figma API
            timeout: Request timeout in seconds
            image_scale: Scale factor for image exports (1.0-4.0)
            image_format: Image format for exports (png, jpg, svg, pdf)
        """
        self.access_token = access_token
        self.api_base_url = api_base_url
        self.timeout = timeout
        self.image_scale = image_scale
        self.image_format = image_format
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.api_base_url,
                headers={
                    "X-Figma-Token": self.access_token,
                    "Content-Type": "application/json"
                },
                timeout=self.timeout
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_file(self, file_key: str) -> Dict[str, Any]:
        """
        Fetch complete file structure with all nodes.

        Args:
            file_key: Figma file key (from URL)

        Returns:
            File data including document tree
        """
        client = await self._get_client()
        response = await client.get(f"/files/{file_key}")
        response.raise_for_status()
        return response.json()

    async def get_file_metadata(self, file_key: str) -> Dict[str, Any]:
        """
        Fetch file metadata without the full document tree.

        Args:
            file_key: Figma file key

        Returns:
            File metadata including name, last modified, version
        """
        client = await self._get_client()
        # Use depth=1 to get minimal data
        response = await client.get(f"/files/{file_key}?depth=1")
        response.raise_for_status()
        data = response.json()
        return {
            "name": data.get("name"),
            "last_modified": data.get("lastModified"),
            "version": data.get("version"),
            "thumbnail_url": data.get("thumbnailUrl")
        }

    async def get_nodes(
        self,
        file_key: str,
        node_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Fetch specific nodes by ID.

        Args:
            file_key: Figma file key
            node_ids: List of node IDs to fetch

        Returns:
            Node data for requested IDs
        """
        client = await self._get_client()
        ids_param = ",".join(node_ids)
        response = await client.get(f"/files/{file_key}/nodes?ids={ids_param}")
        response.raise_for_status()
        return response.json()

    async def get_image_urls(
        self,
        file_key: str,
        node_ids: List[str],
        scale: Optional[float] = None,
        format: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Get URLs for exported images of nodes.

        Args:
            file_key: Figma file key
            node_ids: List of node IDs to export
            scale: Scale factor (1.0-4.0)
            format: Image format (png, jpg, svg, pdf)

        Returns:
            Dictionary mapping node_id to image URL
        """
        client = await self._get_client()
        ids_param = ",".join(node_ids)
        scale = scale or self.image_scale
        format = format or self.image_format

        response = await client.get(
            f"/images/{file_key}?ids={ids_param}&scale={scale}&format={format}"
        )
        response.raise_for_status()

        data = response.json()
        if data.get("err"):
            logger.error(f"Figma image export error: {data['err']}")
            return {}

        return data.get("images", {})

    async def export_frame_as_image(
        self,
        file_key: str,
        node_id: str,
        scale: Optional[float] = None,
        format: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Export a frame/node as an image.

        Args:
            file_key: Figma file key
            node_id: Node ID to export
            scale: Scale factor
            format: Image format

        Returns:
            Image bytes or None if export failed
        """
        # Get image URL from Figma
        image_urls = await self.get_image_urls(file_key, [node_id], scale, format)

        if not image_urls or node_id not in image_urls:
            logger.error(f"Failed to get image URL for node {node_id}")
            return None

        image_url = image_urls[node_id]
        if not image_url:
            logger.error(f"Empty image URL for node {node_id}")
            return None

        # Download the image
        async with httpx.AsyncClient(timeout=60) as download_client:
            response = await download_client.get(image_url)
            response.raise_for_status()
            return response.content

    async def get_file_versions(
        self,
        file_key: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a file.

        Args:
            file_key: Figma file key
            limit: Maximum versions to return

        Returns:
            List of version objects
        """
        client = await self._get_client()
        response = await client.get(f"/files/{file_key}/versions")
        response.raise_for_status()

        data = response.json()
        versions = data.get("versions", [])
        return versions[:limit]

    def extract_text_nodes(
        self,
        node: Dict[str, Any],
        results: Optional[List[FigmaTextNode]] = None
    ) -> List[FigmaTextNode]:
        """
        Recursively extract all text nodes from a Figma node tree.

        Args:
            node: Figma node dictionary
            results: Accumulator for results

        Returns:
            List of FigmaTextNode objects
        """
        if results is None:
            results = []

        if node.get("type") == "TEXT" and node.get("visible", True):
            style = node.get("style", {})
            results.append(FigmaTextNode(
                id=node["id"],
                name=node.get("name", ""),
                characters=node.get("characters", ""),
                font_family=style.get("fontFamily"),
                font_size=style.get("fontSize"),
                font_weight=style.get("fontWeight"),
                text_align=style.get("textAlignHorizontal"),
                fills=node.get("fills", [])
            ))

        # Recurse into children
        for child in node.get("children", []):
            self.extract_text_nodes(child, results)

        return results

    def find_email_frames(
        self,
        document: Dict[str, Any],
        page_ids: Optional[List[str]] = None
    ) -> List[FigmaFrame]:
        """
        Find frames that appear to be email designs.

        Heuristics:
        - Frame name contains "email", "newsletter", "campaign", "blast"
        - Frame dimensions suggest email (width 500-700px, height > width)
        - Frame is a direct child of a page (not nested deeply)

        Args:
            document: Figma document object
            page_ids: Optional list of specific page IDs to search

        Returns:
            List of FigmaFrame objects that appear to be emails
        """
        email_frames = []
        email_keywords = ['email', 'newsletter', 'campaign', 'blast', 'edm', 'mail']

        pages = document.get("document", {}).get("children", [])

        for page in pages:
            # Filter by page_ids if specified
            if page_ids and page.get("id") not in page_ids:
                continue

            # Look at direct children of the page (top-level frames)
            for child in page.get("children", []):
                if child.get("type") != "FRAME":
                    continue

                if not child.get("visible", True):
                    continue

                frame_name = child.get("name", "").lower()
                bounds = child.get("absoluteBoundingBox", {})
                width = bounds.get("width", 0)
                height = bounds.get("height", 0)

                # Check if it looks like an email
                is_email = False

                # Heuristic 1: Name contains email-related keyword
                if any(kw in frame_name for kw in email_keywords):
                    is_email = True

                # Heuristic 2: Dimensions suggest email (common widths: 600-640px)
                if 500 <= width <= 700 and height > width:
                    is_email = True

                if is_email:
                    email_frames.append(FigmaFrame(
                        id=child["id"],
                        name=child.get("name", ""),
                        width=width,
                        height=height,
                        background_color=self._extract_bg_color(child),
                        children_count=len(child.get("children", []))
                    ))

        logger.info(f"Found {len(email_frames)} email frames")
        return email_frames

    def _extract_bg_color(self, node: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """Extract background color from node fills."""
        fills = node.get("fills", [])
        for fill in fills:
            if fill.get("type") == "SOLID" and fill.get("visible", True):
                return fill.get("color")
        return None

    async def get_email_design(
        self,
        file_key: str,
        frame_id: str,
        include_image: bool = True
    ) -> EmailDesign:
        """
        Fetch complete email design data for a frame.

        Args:
            file_key: Figma file key
            frame_id: Frame/node ID
            include_image: Whether to export and include image bytes

        Returns:
            EmailDesign object with all extracted data
        """
        # Get file metadata
        file_metadata = await self.get_file_metadata(file_key)

        # Get the specific node
        nodes_data = await self.get_nodes(file_key, [frame_id])
        node_data = nodes_data.get("nodes", {}).get(frame_id, {}).get("document", {})

        if not node_data:
            raise ValueError(f"Node {frame_id} not found in file {file_key}")

        bounds = node_data.get("absoluteBoundingBox", {})

        # Extract text content
        text_nodes = self.extract_text_nodes(node_data)

        # Export image if requested
        image_bytes = None
        if include_image:
            image_bytes = await self.export_frame_as_image(file_key, frame_id)

        # Parse last modified date
        last_modified = None
        if file_metadata.get("last_modified"):
            try:
                last_modified = datetime.fromisoformat(
                    file_metadata["last_modified"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return EmailDesign(
            frame_id=frame_id,
            frame_name=node_data.get("name", "Unknown"),
            file_key=file_key,
            file_name=file_metadata.get("name", "Unknown"),
            version_id=file_metadata.get("version"),
            last_modified=last_modified,
            width=bounds.get("width", 0),
            height=bounds.get("height", 0),
            image_bytes=image_bytes,
            text_content=text_nodes
        )
