"""
Email Vision Analyzer using Gemini Vision.

Analyzes email design images to extract:
- Layout structure
- Visual elements (colors, images, CTAs)
- Accessibility indicators
- Mobile readiness signals
"""

import logging
import json
import asyncio
import base64
from typing import Dict, List, Any, Optional
from datetime import datetime, UTC
from pydantic import BaseModel, Field
import google.generativeai as genai

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Analysis Results
# =============================================================================

class LayoutAnalysis(BaseModel):
    """Analysis of email layout structure."""
    structure: str = "unknown"  # single-column, multi-column, hybrid
    header_present: bool = False
    footer_present: bool = False
    sections: List[str] = Field(default_factory=list)  # hero, body, cta, footer, etc.
    estimated_scroll_depth: str = "unknown"  # above-fold, short, medium, long


class VisualElements(BaseModel):
    """Analysis of visual elements in the email."""
    primary_colors: List[str] = Field(default_factory=list)  # Hex colors
    image_count: int = 0
    estimated_image_ratio: float = 0.0  # 0.0 to 1.0
    has_hero_image: bool = False
    has_product_images: bool = False
    has_logo: bool = False
    has_icons: bool = False


class CTAAnalysis(BaseModel):
    """Analysis of Call-to-Action elements."""
    cta_count: int = 0
    primary_cta_text: Optional[str] = None
    cta_texts: List[str] = Field(default_factory=list)
    cta_visibility_score: float = 0.0  # 0.0 to 1.0
    cta_placement: List[str] = Field(default_factory=list)  # above-fold, middle, footer
    cta_colors_contrast_with_bg: bool = True


class AccessibilityAnalysis(BaseModel):
    """Analysis of accessibility indicators."""
    estimated_contrast_score: float = 0.0  # 0.0 to 1.0
    readable_font_sizes: bool = True
    sufficient_line_spacing: bool = True
    alt_text_indicators: bool = False  # Can't determine from image, but can flag image-heavy
    issues: List[str] = Field(default_factory=list)


class MobileReadinessAnalysis(BaseModel):
    """Analysis of mobile responsiveness indicators."""
    appears_responsive: bool = True
    touch_friendly_buttons: bool = True
    readable_on_mobile: bool = True
    issues: List[str] = Field(default_factory=list)


class CopyAnalysis(BaseModel):
    """Extracted copy/text visible in the email."""
    headline: Optional[str] = None
    subheadline: Optional[str] = None
    body_preview: Optional[str] = None  # First ~200 chars
    cta_text: List[str] = Field(default_factory=list)
    preheader_visible: Optional[str] = None


class OverallImpression(BaseModel):
    """Overall quality assessment."""
    professional_score: float = 0.0  # 0.0 to 1.0
    brand_alignment_indicators: List[str] = Field(default_factory=list)
    improvement_suggestions: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)


class EmailVisionAnalysis(BaseModel):
    """Complete vision analysis result for an email design."""
    layout: LayoutAnalysis = Field(default_factory=LayoutAnalysis)
    visuals: VisualElements = Field(default_factory=VisualElements)
    cta: CTAAnalysis = Field(default_factory=CTAAnalysis)
    accessibility: AccessibilityAnalysis = Field(default_factory=AccessibilityAnalysis)
    mobile_readiness: MobileReadinessAnalysis = Field(default_factory=MobileReadinessAnalysis)
    copy: CopyAnalysis = Field(default_factory=CopyAnalysis)
    overall: OverallImpression = Field(default_factory=OverallImpression)
    analysis_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_used: str = ""
    raw_response: Optional[str] = None  # For debugging


# =============================================================================
# Email Vision Analyzer
# =============================================================================

class EmailVisionAnalyzer:
    """
    Analyzes email designs using Gemini Vision.

    Extracts structured information about:
    - Visual layout and structure
    - Text content and copy
    - CTA effectiveness
    - Accessibility issues
    - Mobile responsiveness
    """

    EMAIL_ANALYSIS_PROMPT = """You are an expert email marketing analyst. Analyze this email design image and provide a detailed JSON response.

Your analysis should cover:

1. **Layout Analysis**: Identify the email structure (single-column, multi-column, hybrid), sections present, and scroll depth.

2. **Visual Elements**: Identify colors used, image count, image-to-text ratio, and whether hero/product images are present.

3. **CTA Analysis**: Find all calls-to-action, their text, visibility, and placement. Rate CTA visibility on a 0-1 scale.

4. **Accessibility**: Estimate contrast score (0-1), check for readable font sizes, and note any accessibility issues.

5. **Mobile Readiness**: Assess if the design appears responsive, has touch-friendly buttons, and is readable on mobile.

6. **Copy Extraction**: Extract visible text including headline, subheadline, body preview (first 200 chars), and CTA text.

7. **Overall Impression**: Rate professionalism (0-1), list strengths and improvement suggestions.

Return ONLY valid JSON in this exact format (no markdown, no code blocks):
{
  "layout": {
    "structure": "single-column",
    "header_present": true,
    "footer_present": true,
    "sections": ["hero", "body", "cta", "footer"],
    "estimated_scroll_depth": "medium"
  },
  "visuals": {
    "primary_colors": ["#1E40AF", "#FFFFFF", "#F3F4F6"],
    "image_count": 3,
    "estimated_image_ratio": 0.4,
    "has_hero_image": true,
    "has_product_images": true,
    "has_logo": true,
    "has_icons": false
  },
  "cta": {
    "cta_count": 2,
    "primary_cta_text": "Shop Now",
    "cta_texts": ["Shop Now", "Learn More"],
    "cta_visibility_score": 0.85,
    "cta_placement": ["above-fold", "footer"],
    "cta_colors_contrast_with_bg": true
  },
  "accessibility": {
    "estimated_contrast_score": 0.8,
    "readable_font_sizes": true,
    "sufficient_line_spacing": true,
    "alt_text_indicators": false,
    "issues": ["Low contrast on footer text"]
  },
  "mobile_readiness": {
    "appears_responsive": true,
    "touch_friendly_buttons": true,
    "readable_on_mobile": true,
    "issues": []
  },
  "copy": {
    "headline": "Summer Sale Starts Now",
    "subheadline": "Up to 50% off select items",
    "body_preview": "Don't miss out on our biggest sale of the season. Shop early for best selection...",
    "cta_text": ["Shop Now", "Learn More"],
    "preheader_visible": null
  },
  "overall": {
    "professional_score": 0.85,
    "brand_alignment_indicators": ["Consistent color palette", "Professional typography"],
    "improvement_suggestions": ["Increase CTA button size", "Add more white space"],
    "strengths": ["Clear hierarchy", "Strong visual appeal", "Prominent CTA"]
  }
}

Analyze the email image now:"""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash-lite",
        temperature: float = 0.3,
        max_output_tokens: int = 2000
    ):
        """
        Initialize the vision analyzer.

        Args:
            api_key: Gemini API key
            model_name: Gemini model to use
            temperature: Generation temperature (0.0-1.0)
            max_output_tokens: Maximum tokens in response
        """
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

        # Configure the API
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    async def analyze_email_design(
        self,
        image_bytes: bytes,
        email_name: str = "Email"
    ) -> EmailVisionAnalysis:
        """
        Analyze an email design image with Gemini Vision.

        Args:
            image_bytes: Raw image bytes (PNG or JPEG)
            email_name: Name of the email for logging

        Returns:
            EmailVisionAnalysis with structured results
        """
        logger.info(f"Analyzing email design: {email_name}")

        try:
            # Encode image for Gemini
            image_part = {
                "mime_type": "image/png",
                "data": image_bytes
            }

            # Generate analysis
            response = await asyncio.to_thread(
                self.model.generate_content,
                [self.EMAIL_ANALYSIS_PROMPT, image_part],
                generation_config=genai.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens
                )
            )

            # Parse response
            response_text = response.text.strip()
            logger.debug(f"Raw response: {response_text[:500]}...")

            # Try to extract JSON from response
            analysis_dict = self._parse_json_response(response_text)

            # Convert to Pydantic models
            analysis = self._dict_to_analysis(analysis_dict)
            analysis.model_used = self.model_name
            analysis.raw_response = response_text

            logger.info(f"Analysis complete for {email_name}: score={analysis.overall.professional_score}")
            return analysis

        except Exception as e:
            logger.error(f"Vision analysis failed for {email_name}: {e}")
            # Return empty analysis on failure
            return EmailVisionAnalysis(
                model_used=self.model_name,
                overall=OverallImpression(
                    improvement_suggestions=[f"Analysis failed: {str(e)}"]
                )
            )

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from Gemini response, handling various formats."""
        # Try direct JSON parse
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code block
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            if end > start:
                try:
                    return json.loads(response_text[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try to extract any JSON object
        if "{" in response_text:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if end > start:
                try:
                    return json.loads(response_text[start:end])
                except json.JSONDecodeError:
                    pass

        # Return empty dict if parsing fails
        logger.warning("Could not parse JSON from response")
        return {}

    def _dict_to_analysis(self, data: Dict[str, Any]) -> EmailVisionAnalysis:
        """Convert dictionary to EmailVisionAnalysis with validation."""
        try:
            layout_data = data.get("layout", {})
            layout = LayoutAnalysis(
                structure=layout_data.get("structure", "unknown"),
                header_present=layout_data.get("header_present", False),
                footer_present=layout_data.get("footer_present", False),
                sections=layout_data.get("sections", []),
                estimated_scroll_depth=layout_data.get("estimated_scroll_depth", "unknown")
            )

            visuals_data = data.get("visuals", {})
            visuals = VisualElements(
                primary_colors=visuals_data.get("primary_colors", []),
                image_count=visuals_data.get("image_count", 0),
                estimated_image_ratio=visuals_data.get("estimated_image_ratio", 0.0),
                has_hero_image=visuals_data.get("has_hero_image", False),
                has_product_images=visuals_data.get("has_product_images", False),
                has_logo=visuals_data.get("has_logo", False),
                has_icons=visuals_data.get("has_icons", False)
            )

            cta_data = data.get("cta", {})
            cta = CTAAnalysis(
                cta_count=cta_data.get("cta_count", 0),
                primary_cta_text=cta_data.get("primary_cta_text"),
                cta_texts=cta_data.get("cta_texts", []),
                cta_visibility_score=cta_data.get("cta_visibility_score", 0.0),
                cta_placement=cta_data.get("cta_placement", []),
                cta_colors_contrast_with_bg=cta_data.get("cta_colors_contrast_with_bg", True)
            )

            accessibility_data = data.get("accessibility", {})
            accessibility = AccessibilityAnalysis(
                estimated_contrast_score=accessibility_data.get("estimated_contrast_score", 0.0),
                readable_font_sizes=accessibility_data.get("readable_font_sizes", True),
                sufficient_line_spacing=accessibility_data.get("sufficient_line_spacing", True),
                alt_text_indicators=accessibility_data.get("alt_text_indicators", False),
                issues=accessibility_data.get("issues", [])
            )

            mobile_data = data.get("mobile_readiness", {})
            mobile = MobileReadinessAnalysis(
                appears_responsive=mobile_data.get("appears_responsive", True),
                touch_friendly_buttons=mobile_data.get("touch_friendly_buttons", True),
                readable_on_mobile=mobile_data.get("readable_on_mobile", True),
                issues=mobile_data.get("issues", [])
            )

            copy_data = data.get("copy", {})
            copy = CopyAnalysis(
                headline=copy_data.get("headline"),
                subheadline=copy_data.get("subheadline"),
                body_preview=copy_data.get("body_preview"),
                cta_text=copy_data.get("cta_text", []),
                preheader_visible=copy_data.get("preheader_visible")
            )

            overall_data = data.get("overall", {})
            overall = OverallImpression(
                professional_score=overall_data.get("professional_score", 0.0),
                brand_alignment_indicators=overall_data.get("brand_alignment_indicators", []),
                improvement_suggestions=overall_data.get("improvement_suggestions", []),
                strengths=overall_data.get("strengths", [])
            )

            return EmailVisionAnalysis(
                layout=layout,
                visuals=visuals,
                cta=cta,
                accessibility=accessibility,
                mobile_readiness=mobile,
                copy=copy,
                overall=overall
            )

        except Exception as e:
            logger.error(f"Error converting dict to analysis: {e}")
            return EmailVisionAnalysis()

    async def analyze_batch(
        self,
        designs: List[tuple]  # List of (image_bytes, email_name) tuples
    ) -> List[EmailVisionAnalysis]:
        """
        Analyze multiple email designs in sequence.

        Args:
            designs: List of (image_bytes, email_name) tuples

        Returns:
            List of EmailVisionAnalysis results
        """
        results = []
        for image_bytes, email_name in designs:
            try:
                result = await self.analyze_email_design(image_bytes, email_name)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch analysis failed for {email_name}: {e}")
                results.append(EmailVisionAnalysis(
                    model_used=self.model_name,
                    overall=OverallImpression(
                        improvement_suggestions=[f"Analysis failed: {str(e)}"]
                    )
                ))

            # Small delay between requests to avoid rate limiting
            await asyncio.sleep(0.5)

        return results
