"""
Gemini Vision Service for Image Repository Pipeline.

Generates structured captions and metadata from images using Gemini 1.5 Flash.
"""

import io
import json
import logging
import asyncio
from typing import Dict, List, Optional, Any
from PIL import Image

logger = logging.getLogger(__name__)


# Caption prompt for marketing image analysis
CAPTION_PROMPT = """You are a Digital Asset Manager analyzing marketing images for a creative database.

Analyze this image and provide a JSON response with the following structure:

{
  "description": "Detailed description of what's happening in the image (2-3 sentences)",
  "mood": "One word describing the emotional tone: warm, energetic, professional, calm, playful, luxurious, rustic, modern, cozy, bold",
  "dominant_colors": ["color1", "color2", "color3"],
  "visual_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "text_visible": "Any text visible in the image (empty string if none)",
  "people_present": true or false,
  "setting": "indoor, outdoor, product-shot, lifestyle, abstract, studio",
  "composition": "portrait, landscape, square, close-up, wide-angle",
  "quality_flag": "high, medium, low, screenshot",
  "sensitive_content": false,
  "marketing_use_case": "hero-banner, product-feature, lifestyle, social-media, email-header"
}

IMPORTANT GUIDELINES:
- If image is a screenshot, low resolution (<500px), or a meme: set quality_flag to "screenshot" or "low"
- If image contains identifiable people who aren't professional models: set sensitive_content to true
- If image contains documents, receipts, IDs, or personal info: set sensitive_content to true
- Visual tags should be single lowercase words focused on searchable marketing concepts
- Dominant colors should be common color names (not hex codes)
- Be specific about products, food, settings - these details help search

Respond ONLY with valid JSON, no markdown formatting or code blocks."""


class GeminiVisionService:
    """
    Image captioning service using Gemini 1.5 Flash.

    Generates structured metadata including:
    - Description (what's happening in the image)
    - Mood/tone (warm, energetic, professional, etc.)
    - Dominant colors
    - Visual tags (keywords for search)
    - Sensitivity flags (PII, low-quality)
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-lite",
        max_concurrent: int = 10
    ):
        """
        Initialize Gemini Vision service.

        Args:
            api_key: Gemini API key
            model_name: Model to use (default: gemini-1.5-flash)
            max_concurrent: Maximum concurrent API requests
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.max_concurrent = max_concurrent

        # Safety settings to allow marketing content
        self.safety_settings = {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_MEDIUM_AND_ABOVE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
        }

        self.generation_config = {
            "temperature": 0.3,  # Low temp for consistent output
            "top_p": 0.9,
            "max_output_tokens": 500
        }

        logger.info(f"Gemini Vision Service initialized with model: {model_name}")

    async def caption_image(
        self,
        image_bytes: bytes,
        file_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Generate structured caption for a single image.

        Args:
            image_bytes: Raw image file bytes
            file_name: Original filename (for context and logging)

        Returns:
            Structured metadata dict or None if processing fails
        """
        try:
            # Load image for Gemini
            image = Image.open(io.BytesIO(image_bytes))

            # Validate image size
            width, height = image.size
            if width < 100 or height < 100:
                logger.warning(f"Image too small ({width}x{height}): {file_name}")
                return {
                    "description": "Image too small to analyze",
                    "quality_flag": "low",
                    "sensitive_content": False,
                    "skip_reason": "image_too_small"
                }

            # Resize large images to avoid API limits (max 2048px on longest side)
            MAX_DIMENSION = 2048
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                if width > height:
                    new_width = MAX_DIMENSION
                    new_height = int(height * (MAX_DIMENSION / width))
                else:
                    new_height = MAX_DIMENSION
                    new_width = int(width * (MAX_DIMENSION / height))
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"Resized {file_name} from {width}x{height} to {new_width}x{new_height}")

            # Generate caption (run in executor for async compatibility)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(
                    [CAPTION_PROMPT, image],
                    safety_settings=self.safety_settings,
                    generation_config=self.generation_config
                )
            )

            # Parse JSON response
            caption_text = response.text.strip()

            # Remove markdown code blocks if present
            if caption_text.startswith("```"):
                lines = caption_text.split('\n')
                # Remove first and last lines (```json and ```)
                caption_text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])
                caption_text = caption_text.strip()

            if caption_text.startswith("json"):
                caption_text = caption_text[4:].strip()

            metadata = json.loads(caption_text)

            # Add filename reference
            metadata["original_filename"] = file_name

            # Add image dimensions
            metadata["dimensions"] = {"width": width, "height": height}

            # Validate required fields
            required = ["description", "mood", "visual_tags", "quality_flag", "sensitive_content"]
            missing = [f for f in required if f not in metadata]
            if missing:
                logger.warning(f"Incomplete metadata for {file_name}, missing: {missing}")
                # Fill in defaults for missing fields
                defaults = {
                    "description": "Image analyzed but description unavailable",
                    "mood": "neutral",
                    "visual_tags": [],
                    "quality_flag": "medium",
                    "sensitive_content": False
                }
                for field in missing:
                    metadata[field] = defaults.get(field, "")

            logger.debug(f"Successfully captioned: {file_name}")
            return metadata

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response for {file_name}: {e}")
            logger.debug(f"Raw response: {response.text if 'response' in dir() else 'N/A'}")
            return None

        except Exception as e:
            logger.error(f"Vision API error for {file_name}: {e}")
            return None

    async def caption_batch(
        self,
        images: List[tuple],  # List of (image_bytes, filename) tuples
        max_concurrent: Optional[int] = None
    ) -> List[Optional[Dict[str, Any]]]:
        """
        Process multiple images concurrently.

        Args:
            images: List of (image_bytes, filename) tuples
            max_concurrent: Maximum concurrent API requests (default: self.max_concurrent)

        Returns:
            List of metadata dicts (parallel to input list), None for failed items
        """
        concurrent = max_concurrent or self.max_concurrent
        semaphore = asyncio.Semaphore(concurrent)

        async def process_with_limit(img_bytes: bytes, filename: str) -> Optional[Dict]:
            async with semaphore:
                # Add small delay to avoid rate limiting
                await asyncio.sleep(0.1)
                return await self.caption_image(img_bytes, filename)

        tasks = [
            process_with_limit(img_bytes, filename)
            for img_bytes, filename in images
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to None
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Exception processing image {images[i][1]}: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        success_count = sum(1 for r in processed_results if r is not None)
        logger.info(f"Batch captioning complete: {success_count}/{len(images)} successful")

        return processed_results

    def build_searchable_text(self, file_name: str, caption: Dict[str, Any]) -> str:
        """
        Build comprehensive text field for semantic search.

        Combines all searchable elements into a natural language paragraph
        that Vertex AI can embed and search effectively.

        Args:
            file_name: Original filename
            caption: Caption metadata from Gemini

        Returns:
            Searchable text string
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
