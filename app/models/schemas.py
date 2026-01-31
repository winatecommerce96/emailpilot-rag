"""
RAG Microservice - Pydantic Models
Phase-aware search schemas for Vertex AI Agent Builder

Created: 2025-12-07
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class RAGPhase(str, Enum):
    """
    Workflow phases that determine which document categories to search.
    Acts as the "librarian's brain" for intelligent context retrieval.
    """
    STRATEGY = "STRATEGY"   # Brand voice + past campaigns
    BRIEF = "BRIEF"         # Product specs + brand voice
    VISUAL = "VISUAL"       # Visual assets only
    GENERAL = "GENERAL"     # Search everything (no filter)


class RAGSearchRequest(BaseModel):
    """
    Request schema for RAG search operations.
    Extends base search with phase-aware filtering.
    """
    query: str = Field(..., min_length=1, description="Search query text")
    client_id: str = Field(..., min_length=1, description="Client identifier for data isolation")
    phase: Optional[RAGPhase] = Field(
        default=RAGPhase.GENERAL,
        description="Workflow phase to filter relevant document categories"
    )
    k: int = Field(default=5, ge=1, le=20, description="Number of results to return")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What is the brand voice for email campaigns?",
                "client_id": "rogue-creamery",
                "phase": "BRIEF",
                "k": 5
            }
        }


class RAGResult(BaseModel):
    """
    Individual search result from Vertex AI Search.
    Contains content chunk with full metadata lineage.
    """
    content: str = Field(..., description="Retrieved text content chunk")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Document metadata (client_id, category, source, title)"
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Relevance score from Vertex AI Search"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "content": "Brand voice: warm, artisanal, heritage-focused...",
                "metadata": {
                    "client_id": "rogue-creamery",
                    "category": "brand_voice",
                    "source": "brand_guidelines.json",
                    "title": "Rogue Creamery Brand Guidelines"
                },
                "relevance_score": 0.87
            }
        }


class RAGSearchResponse(BaseModel):
    """
    Full response wrapper for search results.
    Includes metadata about the search operation.
    """
    results: List[RAGResult] = Field(default_factory=list)
    query: str
    client_id: str
    phase: RAGPhase
    total_results: int = 0
    search_metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "results": [],
                "query": "brand voice guidelines",
                "client_id": "rogue-creamery",
                "phase": "BRIEF",
                "total_results": 5,
                "search_metadata": {
                    "filter_applied": "client_id: ANY(\"rogue-creamery\") AND category: ANY(\"brand_voice\", \"product_spec\")",
                    "execution_time_ms": 145
                }
            }
        }


class HealthResponse(BaseModel):
    """Health check response schema."""
    status: str = "healthy"
    service: str = "rag-microservice"
    vertex_connected: bool = False
    data_store_id: Optional[str] = None
