"""
Configuration settings for Intelligence Grading Pipeline.

Loads requirements from YAML and provides typed access.
"""

import os
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class FieldRequirement:
    """A single required field within a dimension."""
    name: str
    display_name: str
    importance: str  # critical, high, medium, low
    points: int
    description: str
    detection_keywords: List[str] = field(default_factory=list)
    extraction_questions: List[str] = field(default_factory=list)
    example_content: Optional[str] = None
    quick_capture_prompt: Optional[str] = None

    @property
    def importance_weight(self) -> float:
        """Convert importance to numeric weight for scoring."""
        weights = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.5,
            "low": 0.3
        }
        return weights.get(self.importance, 0.5)


@dataclass
class DimensionRequirement:
    """A dimension (category) of intelligence requirements."""
    name: str
    weight: float
    display_name: str
    description: str
    minimum_score: int
    fields: List[FieldRequirement] = field(default_factory=list)

    @property
    def total_points(self) -> int:
        """Total possible points in this dimension."""
        return sum(f.points for f in self.fields)

    @property
    def critical_fields(self) -> List[FieldRequirement]:
        """Fields marked as critical importance."""
        return [f for f in self.fields if f.importance == "critical"]


@dataclass
class GradingThresholds:
    """Grade thresholds."""
    A: int = 90
    B: int = 80
    C: int = 70
    D: int = 50
    F: int = 0
    minimum_for_generation: str = "C"
    minimum_dimension_score: int = 40

    def get_grade(self, score: float) -> str:
        """Convert numeric score to letter grade."""
        if score >= self.A:
            return "A"
        elif score >= self.B:
            return "B"
        elif score >= self.C:
            return "C"
        elif score >= self.D:
            return "D"
        else:
            return "F"

    def is_generation_ready(self, grade: str) -> bool:
        """Check if grade meets minimum for calendar generation."""
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_grade = self.minimum_for_generation
        return grade_order.get(grade, 0) >= grade_order.get(min_grade, 0)


@dataclass
class IntelligenceRequirements:
    """Complete intelligence requirements configuration."""
    version: str
    grading: GradingThresholds
    dimensions: Dict[str, DimensionRequirement] = field(default_factory=dict)

    def get_all_fields(self) -> List[FieldRequirement]:
        """Get all fields across all dimensions."""
        fields = []
        for dim in self.dimensions.values():
            fields.extend(dim.fields)
        return fields

    def get_critical_fields(self) -> List[FieldRequirement]:
        """Get all critical fields across all dimensions."""
        fields = []
        for dim in self.dimensions.values():
            fields.extend(dim.critical_fields)
        return fields

    def get_all_keywords(self) -> List[str]:
        """Get all detection keywords across all fields."""
        keywords = []
        for field in self.get_all_fields():
            keywords.extend(field.detection_keywords)
        return list(set(keywords))


_requirements_config: Optional[IntelligenceRequirements] = None


def load_requirements_from_yaml(yaml_path: Path) -> IntelligenceRequirements:
    """Load requirements configuration from YAML file."""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)

    # Parse grading thresholds
    grading_data = data.get("grading", {})
    thresholds_data = grading_data.get("thresholds", {})
    grading = GradingThresholds(
        A=thresholds_data.get("A", 90),
        B=thresholds_data.get("B", 80),
        C=thresholds_data.get("C", 70),
        D=thresholds_data.get("D", 50),
        F=thresholds_data.get("F", 0),
        minimum_for_generation=grading_data.get("minimum_for_generation", "C"),
        minimum_dimension_score=grading_data.get("minimum_dimension_score", 40)
    )

    # Parse dimensions
    dimensions = {}
    for dim_name, dim_data in data.get("dimensions", {}).items():
        fields = []
        for field_data in dim_data.get("fields", []):
            fields.append(FieldRequirement(
                name=field_data["name"],
                display_name=field_data.get("display_name", field_data["name"]),
                importance=field_data.get("importance", "medium"),
                points=field_data.get("points", 10),
                description=field_data.get("description", ""),
                detection_keywords=field_data.get("detection_keywords", []),
                extraction_questions=field_data.get("extraction_questions", []),
                example_content=field_data.get("example_content"),
                quick_capture_prompt=field_data.get("quick_capture_prompt")
            ))

        dimensions[dim_name] = DimensionRequirement(
            name=dim_name,
            weight=dim_data.get("weight", 0.1),
            display_name=dim_data.get("display_name", dim_name),
            description=dim_data.get("description", ""),
            minimum_score=dim_data.get("minimum_score", 50),
            fields=fields
        )

    return IntelligenceRequirements(
        version=data.get("version", "1.0.0"),
        grading=grading,
        dimensions=dimensions
    )


def get_requirements_config() -> IntelligenceRequirements:
    """Get or load the requirements configuration."""
    global _requirements_config

    if _requirements_config is None:
        config_path = Path(__file__).parent / "requirements.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Requirements config not found at {config_path}")

        _requirements_config = load_requirements_from_yaml(config_path)
        logger.info(f"Loaded intelligence requirements v{_requirements_config.version} "
                   f"with {len(_requirements_config.dimensions)} dimensions")

    return _requirements_config


def reload_requirements_config() -> IntelligenceRequirements:
    """Force reload of requirements configuration."""
    global _requirements_config
    _requirements_config = None
    return get_requirements_config()
