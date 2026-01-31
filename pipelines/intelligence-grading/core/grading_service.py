"""
Intelligence Grading Service.

Evaluates client knowledge base completeness and generates grades + recommendations.
"""

import logging
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Ensure pipeline root is in sys.path for absolute imports
_pipeline_root = Path(__file__).parent.parent
if str(_pipeline_root) not in sys.path:
    sys.path.insert(0, str(_pipeline_root))

from config.settings import (
    get_requirements_config,
    IntelligenceRequirements,
    DimensionRequirement,
    FieldRequirement
)
from core.field_extractor import FieldExtractor, ExtractedField, ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class FieldScore:
    """Score for a single field."""
    field_name: str
    display_name: str
    importance: str
    max_points: int
    earned_points: float
    coverage: float
    found: bool
    source_documents: List[str] = field(default_factory=list)
    content_summary: Optional[str] = None


@dataclass
class FieldGap:
    """A gap identified in the knowledge base."""
    field_name: str
    display_name: str
    dimension: str
    importance: str
    impact: str
    suggestion: str
    quick_capture_prompt: Optional[str] = None
    expected_improvement: float = 0


@dataclass
class DimensionScore:
    """Score for a dimension."""
    name: str
    display_name: str
    score: float
    grade: str
    weight: float
    weighted_contribution: float
    max_points: int
    earned_points: float
    fields: List[FieldScore] = field(default_factory=list)
    gaps: List[FieldGap] = field(default_factory=list)


@dataclass
class Recommendation:
    """A recommendation to improve the grade."""
    priority: int
    action: str
    dimension: str
    field_name: str
    expected_improvement: float
    quick_capture_prompt: Optional[str] = None
    template_available: bool = False


@dataclass
class IntelligenceGrade:
    """Complete intelligence grade for a client."""
    client_id: str
    overall_grade: str
    overall_score: float
    ready_for_generation: bool
    confidence_level: str  # high, medium, low
    graded_at: str

    dimension_scores: Dict[str, DimensionScore] = field(default_factory=dict)
    critical_gaps: List[FieldGap] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    generation_warnings: List[str] = field(default_factory=list)

    # Metadata
    documents_analyzed: int = 0
    total_fields: int = 0
    fields_found: int = 0


class IntelligenceGradingService:
    """
    Service for grading client intelligence completeness.
    """

    def __init__(
        self,
        requirements: Optional[IntelligenceRequirements] = None,
        field_extractor: Optional[FieldExtractor] = None
    ):
        """Initialize the grading service."""
        self.requirements = requirements or get_requirements_config()
        self.field_extractor = field_extractor or FieldExtractor()

    async def grade_client(
        self,
        client_id: str,
        documents: List[Dict[str, Any]]
    ) -> IntelligenceGrade:
        """
        Grade a client's intelligence completeness.

        Args:
            client_id: Client identifier
            documents: List of documents with 'content', 'title', 'source_type'

        Returns:
            IntelligenceGrade with complete assessment
        """
        logger.info(f"Grading intelligence for client {client_id} with {len(documents)} documents")

        # Get all field requirements
        all_fields = self.requirements.get_all_fields()

        # Extract fields from documents
        extraction_result = await self.field_extractor.extract_fields_from_documents(
            documents=documents,
            field_requirements=all_fields,
            client_id=client_id
        )

        # Calculate dimension scores
        dimension_scores = self._calculate_dimension_scores(extraction_result)

        # Calculate overall score
        overall_score = sum(ds.weighted_contribution for ds in dimension_scores.values())

        # Determine grade
        overall_grade = self.requirements.grading.get_grade(overall_score)

        # Check if ready for generation
        ready_for_generation = self.requirements.grading.is_generation_ready(overall_grade)

        # Identify critical gaps
        critical_gaps = self._identify_critical_gaps(dimension_scores)

        # Generate recommendations
        recommendations = self._generate_recommendations(dimension_scores, critical_gaps)

        # Generate warnings
        generation_warnings = self._generate_warnings(dimension_scores, overall_grade)

        # Calculate confidence level
        confidence_level = self._calculate_confidence(extraction_result, dimension_scores)

        # Count fields
        total_fields = len(all_fields)
        fields_found = sum(1 for f in extraction_result.fields.values() if f.found)

        return IntelligenceGrade(
            client_id=client_id,
            overall_grade=overall_grade,
            overall_score=round(overall_score, 1),
            ready_for_generation=ready_for_generation,
            confidence_level=confidence_level,
            graded_at=datetime.utcnow().isoformat(),
            dimension_scores=dimension_scores,
            critical_gaps=critical_gaps,
            recommendations=recommendations,
            generation_warnings=generation_warnings,
            documents_analyzed=extraction_result.documents_analyzed,
            total_fields=total_fields,
            fields_found=fields_found
        )

    def _calculate_dimension_scores(
        self,
        extraction_result: ExtractionResult
    ) -> Dict[str, DimensionScore]:
        """Calculate scores for each dimension."""
        dimension_scores = {}

        for dim_name, dim_req in self.requirements.dimensions.items():
            field_scores = []
            gaps = []
            total_earned = 0

            for field_req in dim_req.fields:
                extracted = extraction_result.fields.get(field_req.name)

                if extracted and extracted.found:
                    # Calculate points based on coverage
                    earned = (extracted.coverage / 100) * field_req.points
                    total_earned += earned

                    field_scores.append(FieldScore(
                        field_name=field_req.name,
                        display_name=field_req.display_name,
                        importance=field_req.importance,
                        max_points=field_req.points,
                        earned_points=round(earned, 1),
                        coverage=extracted.coverage,
                        found=True,
                        source_documents=extracted.source_documents,
                        content_summary=extracted.content_summary
                    ))
                else:
                    # Field not found - it's a gap
                    field_scores.append(FieldScore(
                        field_name=field_req.name,
                        display_name=field_req.display_name,
                        importance=field_req.importance,
                        max_points=field_req.points,
                        earned_points=0,
                        coverage=0,
                        found=False
                    ))

                    gaps.append(FieldGap(
                        field_name=field_req.name,
                        display_name=field_req.display_name,
                        dimension=dim_req.display_name,
                        importance=field_req.importance,
                        impact=self._get_gap_impact(field_req, dim_req),
                        suggestion=f"Upload or provide: {field_req.description}",
                        quick_capture_prompt=field_req.quick_capture_prompt,
                        expected_improvement=self._estimate_improvement(field_req, dim_req)
                    ))

            # Calculate dimension score (0-100)
            total_points = dim_req.total_points
            score = (total_earned / total_points * 100) if total_points > 0 else 0
            grade = self.requirements.grading.get_grade(score)
            weighted_contribution = score * dim_req.weight

            dimension_scores[dim_name] = DimensionScore(
                name=dim_name,
                display_name=dim_req.display_name,
                score=round(score, 1),
                grade=grade,
                weight=dim_req.weight,
                weighted_contribution=round(weighted_contribution, 2),
                max_points=total_points,
                earned_points=round(total_earned, 1),
                fields=field_scores,
                gaps=gaps
            )

        return dimension_scores

    def _identify_critical_gaps(
        self,
        dimension_scores: Dict[str, DimensionScore]
    ) -> List[FieldGap]:
        """Identify the most critical gaps."""
        critical_gaps = []

        for dim_score in dimension_scores.values():
            for gap in dim_score.gaps:
                if gap.importance in ["critical", "high"]:
                    critical_gaps.append(gap)

        # Sort by importance and expected improvement
        importance_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        critical_gaps.sort(key=lambda g: (
            importance_order.get(g.importance, 99),
            -g.expected_improvement
        ))

        return critical_gaps[:10]  # Return top 10

    def _generate_recommendations(
        self,
        dimension_scores: Dict[str, DimensionScore],
        critical_gaps: List[FieldGap]
    ) -> List[Recommendation]:
        """Generate prioritized recommendations."""
        recommendations = []

        for i, gap in enumerate(critical_gaps[:5], 1):
            recommendations.append(Recommendation(
                priority=i,
                action=gap.suggestion,
                dimension=gap.dimension,
                field_name=gap.field_name,
                expected_improvement=gap.expected_improvement,
                quick_capture_prompt=gap.quick_capture_prompt,
                template_available=gap.quick_capture_prompt is not None
            ))

        return recommendations

    def _generate_warnings(
        self,
        dimension_scores: Dict[str, DimensionScore],
        overall_grade: str
    ) -> List[str]:
        """Generate warnings about calendar generation quality."""
        warnings = []

        # Check for dimensions below minimum
        for dim_name, dim_score in dimension_scores.items():
            dim_req = self.requirements.dimensions[dim_name]
            if dim_score.score < dim_req.minimum_score:
                warnings.append(
                    f"{dim_score.display_name} is below minimum ({dim_score.score:.0f}% vs {dim_req.minimum_score}% required)"
                )

        # Check for missing critical fields
        missing_critical = []
        for dim_score in dimension_scores.values():
            for gap in dim_score.gaps:
                if gap.importance == "critical":
                    missing_critical.append(gap.display_name)

        if missing_critical:
            warnings.append(f"Missing critical fields: {', '.join(missing_critical[:3])}")

        # Grade-specific warnings
        if overall_grade == "D":
            warnings.append("Calendar quality will be limited due to significant knowledge gaps")
        elif overall_grade == "F":
            warnings.append("Insufficient information for quality calendar generation")

        return warnings

    def _get_gap_impact(
        self,
        field_req: FieldRequirement,
        dim_req: DimensionRequirement
    ) -> str:
        """Generate impact statement for a gap."""
        impact_templates = {
            "brand_voice": "Emails may not match the brand's tone and personality",
            "customer_personas": "Campaigns will lack targeted messaging for specific audiences",
            "segment_definitions": "Unable to create segment-specific campaign strategies",
            "hero_products": "May feature wrong products or miss key offerings",
            "past_campaigns": "Cannot learn from historical successes",
            "revenue_goals": "Cannot align campaign strategy with business objectives",
            "send_frequency": "May recommend sending too many or too few emails"
        }

        return impact_templates.get(
            field_req.name,
            f"Limits the quality of {dim_req.display_name.lower()}-related campaign elements"
        )

    def _estimate_improvement(
        self,
        field_req: FieldRequirement,
        dim_req: DimensionRequirement
    ) -> float:
        """Estimate score improvement if field is filled."""
        # Calculate what percentage of overall score this field represents
        field_contribution = field_req.points / dim_req.total_points
        dimension_contribution = field_contribution * dim_req.weight * 100
        return round(dimension_contribution, 1)

    def _calculate_confidence(
        self,
        extraction_result: ExtractionResult,
        dimension_scores: Dict[str, DimensionScore]
    ) -> str:
        """Calculate confidence level in the grade."""
        # Factors affecting confidence:
        # 1. Number of documents analyzed
        # 2. Average extraction confidence
        # 3. Coverage completeness

        doc_count = extraction_result.documents_analyzed
        avg_confidence = 0
        found_count = 0

        for field in extraction_result.fields.values():
            if field.found:
                avg_confidence += field.confidence
                found_count += 1

        if found_count > 0:
            avg_confidence /= found_count

        # Calculate confidence score
        confidence_score = 0

        # Document count factor (more docs = more confidence)
        if doc_count >= 10:
            confidence_score += 0.4
        elif doc_count >= 5:
            confidence_score += 0.3
        elif doc_count >= 2:
            confidence_score += 0.2
        else:
            confidence_score += 0.1

        # Extraction confidence factor
        confidence_score += avg_confidence * 0.4

        # Coverage factor (what % of fields were found)
        total_fields = len(extraction_result.fields)
        if total_fields > 0:
            coverage_ratio = found_count / total_fields
            confidence_score += coverage_ratio * 0.2

        # Map to level
        if confidence_score >= 0.7:
            return "high"
        elif confidence_score >= 0.4:
            return "medium"
        else:
            return "low"

    async def get_quick_assessment(
        self,
        client_id: str,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get a quick assessment without full AI analysis.

        Uses keyword matching for faster results.
        """
        # Use keyword-only extraction
        all_fields = self.requirements.get_all_fields()

        # Prepare content
        combined_content = "\n".join(
            doc.get("content", "") for doc in documents
        ).lower()

        # Quick keyword check
        dimension_summaries = {}
        total_found = 0
        total_fields = 0

        for dim_name, dim_req in self.requirements.dimensions.items():
            found_in_dim = 0
            for field_req in dim_req.fields:
                total_fields += 1
                # Check if any keywords present
                if any(kw.lower() in combined_content for kw in field_req.detection_keywords):
                    found_in_dim += 1
                    total_found += 1

            coverage = (found_in_dim / len(dim_req.fields) * 100) if dim_req.fields else 0
            dimension_summaries[dim_name] = {
                "display_name": dim_req.display_name,
                "coverage": round(coverage, 0),
                "fields_found": found_in_dim,
                "total_fields": len(dim_req.fields)
            }

        overall_coverage = (total_found / total_fields * 100) if total_fields > 0 else 0
        estimated_grade = self.requirements.grading.get_grade(overall_coverage)

        return {
            "client_id": client_id,
            "estimated_grade": estimated_grade,
            "estimated_score": round(overall_coverage, 0),
            "documents_analyzed": len(documents),
            "fields_found": total_found,
            "total_fields": total_fields,
            "dimension_summaries": dimension_summaries,
            "is_estimate": True,
            "note": "Quick assessment based on keyword matching. Use /grade for full AI analysis."
        }
