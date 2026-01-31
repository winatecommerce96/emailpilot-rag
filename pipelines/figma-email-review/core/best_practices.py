"""
Email Best Practices Evaluator.

Evaluates emails against industry best practices for:
- Subject lines
- CTAs
- Accessibility
- Mobile responsiveness
- Deliverability factors
"""

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .vision_analyzer import EmailVisionAnalysis, CTAAnalysis, AccessibilityAnalysis
from .rag_integration import BrandVoiceComplianceResult

logger = logging.getLogger(__name__)


# =============================================================================
# Evaluation Result Models
# =============================================================================

class SubjectLineEvaluation(BaseModel):
    """Evaluation of email subject line."""
    subject: str = ""
    length: int = 0
    within_optimal_range: bool = True  # 20-60 chars
    has_personalization: bool = False
    has_emoji: bool = False
    spam_trigger_words: List[str] = Field(default_factory=list)
    urgency_indicators: List[str] = Field(default_factory=list)
    score: float = 1.0  # 0.0 to 1.0
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class CTAEvaluation(BaseModel):
    """Evaluation of CTA effectiveness."""
    has_cta: bool = True
    cta_count: int = 0
    primary_cta_clear: bool = True
    cta_visibility_score: float = 0.0
    action_oriented: bool = True
    score: float = 1.0
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class AccessibilityEvaluation(BaseModel):
    """Evaluation of accessibility compliance."""
    contrast_score: float = 0.0
    readable_fonts: bool = True
    alt_text_warning: bool = False  # True if image-heavy
    color_blind_safe: bool = True
    score: float = 1.0
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class MobileReadinessEvaluation(BaseModel):
    """Evaluation of mobile responsiveness."""
    appears_responsive: bool = True
    touch_friendly: bool = True
    readable_on_mobile: bool = True
    optimal_width: bool = True
    score: float = 1.0
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class LayoutEvaluation(BaseModel):
    """Evaluation of email layout."""
    has_header: bool = True
    has_footer: bool = True
    image_text_ratio_ok: bool = True
    clear_hierarchy: bool = True
    score: float = 1.0
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class EmailReviewReport(BaseModel):
    """Complete email review report."""
    # Identification
    review_id: str = ""
    email_name: str = ""
    client_id: str = ""
    review_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Source info
    figma_file_key: str = ""
    figma_frame_id: str = ""
    figma_version: Optional[str] = None
    figma_url: Optional[str] = None

    # Scores (0.0 to 1.0)
    overall_score: float = 0.0
    brand_compliance_score: float = 0.0
    accessibility_score: float = 0.0
    best_practices_score: float = 0.0
    mobile_score: float = 0.0

    # Detailed evaluations
    subject_line: Optional[SubjectLineEvaluation] = None
    cta: CTAEvaluation = Field(default_factory=CTAEvaluation)
    accessibility: AccessibilityEvaluation = Field(default_factory=AccessibilityEvaluation)
    mobile_readiness: MobileReadinessEvaluation = Field(default_factory=MobileReadinessEvaluation)
    layout: LayoutEvaluation = Field(default_factory=LayoutEvaluation)
    brand_voice: BrandVoiceComplianceResult = Field(default_factory=BrandVoiceComplianceResult)

    # Actionable output
    critical_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)

    # Metadata
    asana_task_gid: Optional[str] = None
    asana_task_name: Optional[str] = None


# =============================================================================
# Email Best Practices Evaluator
# =============================================================================

class EmailBestPracticesEvaluator:
    """
    Evaluates emails against industry best practices.

    Checks:
    - Subject line effectiveness (if provided)
    - CTA clarity and placement
    - Accessibility compliance
    - Mobile responsiveness
    - Layout and structure
    """

    # Spam trigger words to check for
    SPAM_TRIGGERS = [
        'FREE', 'URGENT', 'ACT NOW', 'LIMITED TIME', 'CLICK HERE',
        'BUY NOW', 'ORDER NOW', 'WINNER', 'CONGRATULATIONS', 'EXCLUSIVE',
        '100%', 'GUARANTEE', 'NO OBLIGATION', 'RISK FREE', 'CHEAP',
        'BONUS', 'CASH', 'DISCOUNT', 'DOUBLE YOUR', 'EARN MONEY',
        'LOWEST PRICE', 'MILLION DOLLARS', 'NO CATCH', 'OFFER',
        'SAVE BIG', 'SPECIAL PROMOTION', 'WHILE SUPPLIES LAST'
    ]

    # Urgency indicators
    URGENCY_WORDS = [
        'TODAY', 'NOW', 'HURRY', 'LAST CHANCE', 'ENDS SOON',
        'LIMITED', 'EXPIRES', 'DON\'T MISS', 'FINAL', 'ONLY'
    ]

    def __init__(
        self,
        subject_min_length: int = 20,
        subject_max_length: int = 60,
        min_cta_visibility: float = 0.7,
        max_image_ratio: float = 0.6,
        min_contrast: float = 0.7
    ):
        """
        Initialize the evaluator with thresholds.

        Args:
            subject_min_length: Minimum subject line length
            subject_max_length: Maximum subject line length
            min_cta_visibility: Minimum CTA visibility score
            max_image_ratio: Maximum image-to-text ratio
            min_contrast: Minimum contrast score
        """
        self.subject_min_length = subject_min_length
        self.subject_max_length = subject_max_length
        self.min_cta_visibility = min_cta_visibility
        self.max_image_ratio = max_image_ratio
        self.min_contrast = min_contrast

    def evaluate_subject_line(self, subject: str) -> SubjectLineEvaluation:
        """
        Evaluate subject line effectiveness.

        Args:
            subject: Email subject line

        Returns:
            SubjectLineEvaluation with score and issues
        """
        if not subject:
            return SubjectLineEvaluation(
                subject="",
                score=0.5,
                issues=["No subject line provided for evaluation"]
            )

        evaluation = SubjectLineEvaluation(subject=subject)
        evaluation.length = len(subject)

        # Check length
        if evaluation.length < self.subject_min_length:
            evaluation.within_optimal_range = False
            evaluation.issues.append(f"Subject too short ({evaluation.length} chars, min {self.subject_min_length})")
        elif evaluation.length > self.subject_max_length:
            evaluation.within_optimal_range = False
            evaluation.issues.append(f"Subject too long ({evaluation.length} chars, max {self.subject_max_length})")

        # Check for personalization tokens
        if "{{" in subject or "{%" in subject or "%%[" in subject:
            evaluation.has_personalization = True

        # Check for emoji
        if any(ord(c) > 127 for c in subject):
            evaluation.has_emoji = True

        # Check for spam triggers
        subject_upper = subject.upper()
        for trigger in self.SPAM_TRIGGERS:
            if trigger in subject_upper:
                evaluation.spam_trigger_words.append(trigger)

        if evaluation.spam_trigger_words:
            evaluation.issues.append(f"Contains spam trigger words: {', '.join(evaluation.spam_trigger_words[:3])}")

        # Check for urgency indicators
        for word in self.URGENCY_WORDS:
            if word in subject_upper:
                evaluation.urgency_indicators.append(word)

        # Calculate score
        score = 1.0
        if not evaluation.within_optimal_range:
            score -= 0.2
        if evaluation.spam_trigger_words:
            score -= 0.1 * min(len(evaluation.spam_trigger_words), 3)
        if evaluation.has_personalization:
            score += 0.1  # Bonus for personalization

        evaluation.score = max(0.0, min(1.0, score))

        # Add suggestions
        if not evaluation.has_personalization:
            evaluation.suggestions.append("Consider adding personalization (e.g., first name)")
        if evaluation.length > 50:
            evaluation.suggestions.append("Consider shortening for mobile preview")

        return evaluation

    def evaluate_cta(self, cta_analysis: CTAAnalysis) -> CTAEvaluation:
        """
        Evaluate CTA effectiveness based on vision analysis.

        Args:
            cta_analysis: CTA analysis from vision analyzer

        Returns:
            CTAEvaluation with score and issues
        """
        evaluation = CTAEvaluation()
        evaluation.cta_count = cta_analysis.cta_count
        evaluation.has_cta = cta_analysis.cta_count > 0
        evaluation.cta_visibility_score = cta_analysis.cta_visibility_score

        score = 1.0

        # Check if CTA exists
        if not evaluation.has_cta:
            score = 0.3
            evaluation.issues.append("No CTA found in email")
            evaluation.suggestions.append("Add a clear call-to-action button")
        else:
            # Check visibility
            if cta_analysis.cta_visibility_score < self.min_cta_visibility:
                score -= 0.2
                evaluation.issues.append(f"CTA visibility is low ({cta_analysis.cta_visibility_score:.0%})")
                evaluation.suggestions.append("Increase CTA button size or contrast")

            # Check if primary CTA is clear
            if cta_analysis.cta_count > 3:
                score -= 0.1
                evaluation.issues.append("Too many CTAs may confuse readers")
                evaluation.suggestions.append("Focus on 1-2 primary CTAs")

            # Check CTA placement
            if "above-fold" not in cta_analysis.cta_placement:
                score -= 0.1
                evaluation.warnings = ["No CTA visible above the fold"]
                evaluation.suggestions.append("Consider adding a CTA in the hero section")

            # Check contrast
            if not cta_analysis.cta_colors_contrast_with_bg:
                score -= 0.15
                evaluation.issues.append("CTA buttons may lack sufficient contrast")

        evaluation.score = max(0.0, min(1.0, score))
        return evaluation

    def evaluate_accessibility(
        self,
        accessibility_analysis: AccessibilityAnalysis,
        image_ratio: float = 0.0
    ) -> AccessibilityEvaluation:
        """
        Evaluate accessibility compliance.

        Args:
            accessibility_analysis: Accessibility analysis from vision analyzer
            image_ratio: Image-to-content ratio

        Returns:
            AccessibilityEvaluation with score and issues
        """
        evaluation = AccessibilityEvaluation()
        evaluation.contrast_score = accessibility_analysis.estimated_contrast_score
        evaluation.readable_fonts = accessibility_analysis.readable_font_sizes

        score = 1.0

        # Check contrast
        if accessibility_analysis.estimated_contrast_score < self.min_contrast:
            score -= 0.25
            evaluation.issues.append(
                f"Contrast may be insufficient ({accessibility_analysis.estimated_contrast_score:.0%})"
            )
            evaluation.suggestions.append("Increase text/background contrast ratio")

        # Check font readability
        if not accessibility_analysis.readable_font_sizes:
            score -= 0.2
            evaluation.issues.append("Some font sizes may be too small")
            evaluation.suggestions.append("Ensure minimum 14px font size for body text")

        # Check image ratio (alt text concern)
        if image_ratio > self.max_image_ratio:
            evaluation.alt_text_warning = True
            score -= 0.1
            evaluation.warnings = [f"High image ratio ({image_ratio:.0%}) - ensure alt text is provided"]

        # Add issues from vision analysis
        for issue in accessibility_analysis.issues:
            if issue not in evaluation.issues:
                evaluation.issues.append(issue)
                score -= 0.05

        evaluation.score = max(0.0, min(1.0, score))
        return evaluation

    def evaluate_mobile_readiness(
        self,
        vision_analysis: EmailVisionAnalysis
    ) -> MobileReadinessEvaluation:
        """
        Evaluate mobile responsiveness.

        Args:
            vision_analysis: Complete vision analysis

        Returns:
            MobileReadinessEvaluation with score and issues
        """
        mobile = vision_analysis.mobile_readiness
        evaluation = MobileReadinessEvaluation(
            appears_responsive=mobile.appears_responsive,
            touch_friendly=mobile.touch_friendly_buttons,
            readable_on_mobile=mobile.readable_on_mobile
        )

        score = 1.0

        if not mobile.appears_responsive:
            score -= 0.3
            evaluation.issues.append("Email may not be responsive")
            evaluation.suggestions.append("Use mobile-first design approach")

        if not mobile.touch_friendly_buttons:
            score -= 0.2
            evaluation.issues.append("Buttons may be too small for touch")
            evaluation.suggestions.append("Ensure buttons are at least 44x44px")

        if not mobile.readable_on_mobile:
            score -= 0.2
            evaluation.issues.append("Text may be hard to read on mobile")
            evaluation.suggestions.append("Use larger font sizes (16px+ for body)")

        # Add issues from vision analysis
        for issue in mobile.issues:
            if issue not in evaluation.issues:
                evaluation.issues.append(issue)
                score -= 0.05

        evaluation.score = max(0.0, min(1.0, score))
        return evaluation

    def evaluate_layout(
        self,
        vision_analysis: EmailVisionAnalysis
    ) -> LayoutEvaluation:
        """
        Evaluate email layout and structure.

        Args:
            vision_analysis: Complete vision analysis

        Returns:
            LayoutEvaluation with score and issues
        """
        layout = vision_analysis.layout
        visuals = vision_analysis.visuals

        evaluation = LayoutEvaluation(
            has_header=layout.header_present,
            has_footer=layout.footer_present,
            image_text_ratio_ok=visuals.estimated_image_ratio <= self.max_image_ratio,
            clear_hierarchy=True  # Assume true if professional score is high
        )

        score = 1.0

        if not layout.header_present:
            score -= 0.1
            evaluation.suggestions.append("Consider adding a header with logo")

        if not layout.footer_present:
            score -= 0.15
            evaluation.issues.append("Missing footer (required for compliance)")
            evaluation.suggestions.append("Add footer with unsubscribe link")

        if visuals.estimated_image_ratio > self.max_image_ratio:
            score -= 0.15
            evaluation.issues.append(f"Image-heavy design ({visuals.estimated_image_ratio:.0%})")
            evaluation.suggestions.append("Balance images with text for better deliverability")

        if vision_analysis.overall.professional_score < 0.7:
            evaluation.clear_hierarchy = False
            score -= 0.1
            evaluation.suggestions.append("Improve visual hierarchy and structure")

        evaluation.score = max(0.0, min(1.0, score))
        return evaluation

    def generate_full_report(
        self,
        vision_analysis: EmailVisionAnalysis,
        brand_compliance: BrandVoiceComplianceResult,
        email_name: str,
        client_id: str,
        figma_file_key: str = "",
        figma_frame_id: str = "",
        subject_line: Optional[str] = None,
        asana_task_gid: Optional[str] = None,
        asana_task_name: Optional[str] = None
    ) -> EmailReviewReport:
        """
        Generate comprehensive email review report.

        Args:
            vision_analysis: Vision analysis results
            brand_compliance: Brand voice compliance results
            email_name: Name of the email
            client_id: Client identifier
            figma_file_key: Figma file key
            figma_frame_id: Figma frame ID
            subject_line: Optional subject line to evaluate
            asana_task_gid: Optional Asana task GID
            asana_task_name: Optional Asana task name

        Returns:
            EmailReviewReport with all evaluations
        """
        import uuid

        # Run all evaluations
        subject_eval = self.evaluate_subject_line(subject_line) if subject_line else None
        cta_eval = self.evaluate_cta(vision_analysis.cta)
        accessibility_eval = self.evaluate_accessibility(
            vision_analysis.accessibility,
            vision_analysis.visuals.estimated_image_ratio
        )
        mobile_eval = self.evaluate_mobile_readiness(vision_analysis)
        layout_eval = self.evaluate_layout(vision_analysis)

        # Calculate scores
        brand_score = brand_compliance.compliance_score
        accessibility_score = accessibility_eval.score
        best_practices_score = (cta_eval.score + layout_eval.score) / 2
        mobile_score = mobile_eval.score

        # Overall score (weighted average)
        overall_score = (
            brand_score * 0.25 +
            accessibility_score * 0.25 +
            best_practices_score * 0.25 +
            mobile_score * 0.25
        )

        # Collect all issues
        critical_issues = []
        warnings = []
        suggestions = []

        # From CTA
        critical_issues.extend(cta_eval.issues)
        suggestions.extend(cta_eval.suggestions)

        # From accessibility
        critical_issues.extend(accessibility_eval.issues)
        suggestions.extend(accessibility_eval.suggestions)

        # From mobile
        if mobile_eval.score < 0.7:
            critical_issues.extend(mobile_eval.issues)
        else:
            warnings.extend(mobile_eval.issues)
        suggestions.extend(mobile_eval.suggestions)

        # From layout
        if layout_eval.score < 0.7:
            critical_issues.extend(layout_eval.issues)
        else:
            warnings.extend(layout_eval.issues)
        suggestions.extend(layout_eval.suggestions)

        # From brand voice
        critical_issues.extend(brand_compliance.messaging_issues)
        warnings.extend(brand_compliance.vocabulary_issues)
        suggestions.extend(brand_compliance.recommendations)

        # From subject line
        if subject_eval:
            if subject_eval.score < 0.7:
                critical_issues.extend(subject_eval.issues)
            else:
                warnings.extend(subject_eval.issues)
            suggestions.extend(subject_eval.suggestions)

        # Add vision overall suggestions
        suggestions.extend(vision_analysis.overall.improvement_suggestions)

        # Deduplicate
        critical_issues = list(dict.fromkeys(critical_issues))
        warnings = list(dict.fromkeys(warnings))
        suggestions = list(dict.fromkeys(suggestions))

        return EmailReviewReport(
            review_id=str(uuid.uuid4()),
            email_name=email_name,
            client_id=client_id,
            figma_file_key=figma_file_key,
            figma_frame_id=figma_frame_id,
            overall_score=overall_score,
            brand_compliance_score=brand_score,
            accessibility_score=accessibility_score,
            best_practices_score=best_practices_score,
            mobile_score=mobile_score,
            subject_line=subject_eval,
            cta=cta_eval,
            accessibility=accessibility_eval,
            mobile_readiness=mobile_eval,
            layout=layout_eval,
            brand_voice=brand_compliance,
            critical_issues=critical_issues[:10],  # Limit to top 10
            warnings=warnings[:10],
            suggestions=suggestions[:10],
            asana_task_gid=asana_task_gid,
            asana_task_name=asana_task_name
        )
