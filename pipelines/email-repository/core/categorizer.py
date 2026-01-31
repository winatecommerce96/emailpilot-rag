"""
Gemini Vision Email Categorizer.

Analyzes email screenshots to extract category, type, visual elements,
and other metadata for organization and search.
"""

import asyncio
import base64
import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

import google.generativeai as genai

logger = logging.getLogger(__name__)


# E-commerce focused categorization prompt
EMAIL_CATEGORIZATION_PROMPT = """Analyze this promotional email screenshot.

Provide JSON response:
{
  "product_category": "fashion|food|beauty|home|retail|tech|health|services|other",
  "email_type": "promotional|newsletter|transactional|winback|cart_abandonment|welcome_series|product_launch|seasonal|educational|announcement",
  "visual_elements": {
    "has_hero_image": true/false,
    "has_product_grid": true/false,
    "text_heavy": true/false,
    "has_cta_button": true/false,
    "color_scheme": "bright|dark|minimal|colorful|branded",
    "layout_type": "single_column|multi_column|grid|hero_focused"
  },
  "brand_info": {
    "brand_name": "string or null",
    "industry_vertical": "string"
  },
  "content_theme": "sale|new_arrival|restock|educational|lifestyle|seasonal|holiday|event|loyalty|feedback",
  "quality_assessment": {
    "overall_quality": "high|medium|low",
    "design_sophistication": "premium|standard|basic",
    "mobile_optimized": true/false
  }
}

Focus on e-commerce/DTC brand emails. Identify fashion, food/beverage, beauty, home goods patterns.
Respond ONLY with valid JSON."""


@dataclass
class CategorizationResult:
    """Result of email categorization."""
    email_id: str
    success: bool
    product_category: str = "other"
    email_type: str = "promotional"
    visual_elements: Optional[Dict[str, Any]] = None
    brand_info: Optional[Dict[str, str]] = None
    content_theme: str = "promotional"
    quality_assessment: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "email_id": self.email_id,
            "success": self.success,
            "product_category": self.product_category,
            "email_type": self.email_type,
            "visual_elements": self.visual_elements or {},
            "brand_info": self.brand_info or {},
            "content_theme": self.content_theme,
            "quality_assessment": self.quality_assessment or {},
            "error": self.error
        }


class EmailCategorizer:
    """
    Gemini Vision-based email categorizer.

    Uses the cheapest Gemini model (flash-lite) for cost efficiency.
    """

    VALID_CATEGORIES = [
        "fashion", "food", "beauty", "home", "retail", "tech", "health", "services", "other"
    ]

    VALID_EMAIL_TYPES = [
        "promotional", "newsletter", "transactional", "winback",
        "cart_abandonment", "welcome_series", "product_launch",
        "seasonal", "educational", "announcement"
    ]

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-lite",
        temperature: float = 0.3,
        max_output_tokens: int = 800
    ):
        """
        Initialize categorizer with Gemini API.

        Args:
            api_key: Gemini API key
            model_name: Model to use (default: flash-lite for cost)
            temperature: Generation temperature (lower = more deterministic)
            max_output_tokens: Maximum tokens in response
        """
        genai.configure(api_key=api_key)

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens
            )
        )

        logger.info(f"EmailCategorizer initialized with model: {model_name}")

    async def categorize_email(
        self,
        screenshot_bytes: bytes,
        email_id: str,
        email_metadata: Optional[Dict[str, Any]] = None
    ) -> CategorizationResult:
        """
        Categorize an email based on its screenshot.

        Args:
            screenshot_bytes: PNG/JPEG image bytes
            email_id: Unique identifier for the email
            email_metadata: Optional metadata (subject, sender, etc.)

        Returns:
            CategorizationResult with extracted information
        """
        try:
            # Create image part for Gemini
            image_part = {
                "mime_type": "image/png",  # Works for both PNG and JPEG
                "data": base64.standard_b64encode(screenshot_bytes).decode('utf-8')
            }

            # Build prompt with optional metadata context
            prompt = EMAIL_CATEGORIZATION_PROMPT
            if email_metadata:
                context = []
                if email_metadata.get('subject'):
                    context.append(f"Subject: {email_metadata['subject']}")
                if email_metadata.get('sender'):
                    context.append(f"From: {email_metadata['sender']}")
                if context:
                    prompt = f"Email context:\n{chr(10).join(context)}\n\n{prompt}"

            # Generate response
            response = await asyncio.to_thread(
                self.model.generate_content,
                [prompt, image_part]
            )

            # Parse JSON response
            result_text = response.text.strip()

            # Clean up response (remove markdown code blocks if present)
            if result_text.startswith('```'):
                lines = result_text.split('\n')
                # Remove first and last lines (code block markers)
                result_text = '\n'.join(lines[1:-1] if lines[-1].startswith('```') else lines[1:])

            try:
                result_json = json.loads(result_text)
            except json.JSONDecodeError:
                # Try to extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group())
                else:
                    raise ValueError(f"Could not parse JSON from response: {result_text[:200]}")

            # Validate and normalize category
            product_category = result_json.get('product_category', 'other').lower()
            if product_category not in self.VALID_CATEGORIES:
                product_category = 'other'

            # Validate and normalize email type
            email_type = result_json.get('email_type', 'promotional').lower()
            if email_type not in self.VALID_EMAIL_TYPES:
                email_type = 'promotional'

            return CategorizationResult(
                email_id=email_id,
                success=True,
                product_category=product_category,
                email_type=email_type,
                visual_elements=result_json.get('visual_elements'),
                brand_info=result_json.get('brand_info'),
                content_theme=result_json.get('content_theme', 'promotional'),
                quality_assessment=result_json.get('quality_assessment'),
                raw_response=result_text
            )

        except Exception as e:
            logger.error(f"Categorization failed for {email_id}: {e}")
            return CategorizationResult(
                email_id=email_id,
                success=False,
                error=str(e)
            )

    async def categorize_batch(
        self,
        emails: List[Tuple[bytes, str, Optional[Dict]]],
        max_concurrent: int = 10
    ) -> List[CategorizationResult]:
        """
        Categorize multiple emails concurrently.

        Args:
            emails: List of (screenshot_bytes, email_id, metadata) tuples
            max_concurrent: Maximum concurrent API calls

        Returns:
            List of CategorizationResult objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def categorize_with_semaphore(
            screenshot: bytes,
            email_id: str,
            metadata: Optional[Dict]
        ) -> CategorizationResult:
            async with semaphore:
                return await self.categorize_email(screenshot, email_id, metadata)

        tasks = [
            categorize_with_semaphore(screenshot, email_id, metadata)
            for screenshot, email_id, metadata in emails
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to CategorizationResult
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                email_id = emails[i][1] if i < len(emails) else 'unknown'
                processed_results.append(CategorizationResult(
                    email_id=email_id,
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        successful = sum(1 for r in processed_results if r.success)
        logger.info(f"Batch categorization complete: {successful}/{len(emails)} successful")

        return processed_results

    def categorize_by_keywords(
        self,
        subject: str,
        sender: str
    ) -> str:
        """
        Quick categorization based on keywords (fallback method).

        Args:
            subject: Email subject line
            sender: Sender email/name

        Returns:
            Product category string
        """
        text = f"{subject} {sender}".lower()

        keyword_mappings = {
            "fashion": ["fashion", "clothing", "apparel", "shoes", "accessories", "jewelry", "dress", "outfit"],
            "food": ["food", "restaurant", "beverage", "grocery", "meal", "coffee", "wine", "delivery", "recipe"],
            "beauty": ["beauty", "cosmetics", "skincare", "makeup", "fragrance", "hair", "spa"],
            "home": ["home", "furniture", "decor", "kitchen", "garden", "outdoor", "interior"],
            "retail": ["sale", "discount", "shop", "store", "deal", "offer"],
            "tech": ["tech", "software", "app", "digital", "device", "gadget"],
            "health": ["health", "wellness", "fitness", "supplement", "vitamin", "workout"],
            "services": ["subscription", "membership", "travel", "booking", "service"]
        }

        for category, keywords in keyword_mappings.items():
            for keyword in keywords:
                if keyword in text:
                    return category

        return "other"


async def categorize_email_screenshots(
    emails: List[Tuple[bytes, str, Optional[Dict]]],
    api_key: str,
    model_name: str = "gemini-2.0-flash-lite",
    max_concurrent: int = 10
) -> List[CategorizationResult]:
    """
    Convenience function to categorize multiple email screenshots.

    Args:
        emails: List of (screenshot_bytes, email_id, metadata) tuples
        api_key: Gemini API key
        model_name: Model to use
        max_concurrent: Maximum concurrent operations

    Returns:
        List of CategorizationResult objects
    """
    categorizer = EmailCategorizer(api_key=api_key, model_name=model_name)
    return await categorizer.categorize_batch(emails, max_concurrent=max_concurrent)
