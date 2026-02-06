"""
RAG Integration for Brand Voice Checking.

Queries the RAG service to retrieve brand voice guidelines
and evaluates email copy against them.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
import httpx
import google.generativeai as genai

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================

class RAGResult(BaseModel):
    """Result from RAG search."""
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    relevance_score: float = 0.0
    source: Optional[str] = None


class BrandVoiceComplianceResult(BaseModel):
    """Result of brand voice compliance check."""
    is_compliant: bool = True
    compliance_score: float = 1.0  # 0.0 to 1.0
    tone_alignment: Dict[str, Any] = Field(default_factory=dict)
    vocabulary_issues: List[str] = Field(default_factory=list)
    messaging_issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    brand_guidelines_used: List[str] = Field(default_factory=list)
    analysis_notes: Optional[str] = None


# =============================================================================
# RAG Brand Voice Checker
# =============================================================================

class RAGBrandVoiceChecker:
    """
    Queries the RAG service to check brand voice compliance.

    Uses the existing /api/rag/search endpoint with phase=STRATEGY
    to retrieve brand voice guidelines for comparison.
    """

    COMPLIANCE_CHECK_PROMPT = """You are a brand voice and brief compliance expert. Compare the email copy against the brand guidelines and the campaign brief, and evaluate compliance.

**Brand Voice Guidelines:**
{guidelines}

**Brief Expectations (if provided):**
{brief}

**Email Copy to Evaluate:**
Headline: {headline}
Subheadline: {subheadline}
Body Preview: {body_preview}
CTA Text: {cta_text}

**Evaluate the following:**

1. **Tone Alignment**: Does the email match the brand's tone? (formal/casual, friendly/professional, etc.)

2. **Vocabulary**: Are there any words or phrases that don't align with the brand voice?

3. **Messaging**: Does the messaging align with brand pillars, values, and the brief expectations?

4. **Recommendations**: What specific changes would improve brand alignment and brief adherence?

If the brief expectations are not met, include those gaps in **messaging_issues** and add corrective guidance in **recommendations**.

Return your analysis as JSON:
{{
  "is_compliant": true/false,
  "compliance_score": 0.85,
  "tone_alignment": {{
    "expected_tone": "friendly, approachable",
    "actual_tone": "professional, slightly formal",
    "alignment_score": 0.7,
    "notes": "Could be more casual to match brand voice"
  }},
  "vocabulary_issues": ["Avoid 'purchase', use 'grab' or 'get' instead"],
  "messaging_issues": ["Missing sustainability messaging that's core to brand"],
  "recommendations": ["Add warmth to headline", "Include brand-specific terminology"],
  "analysis_notes": "Overall the copy is good but could better reflect the brand's personality"
}}

Analyze now:"""

    def __init__(
        self,
        rag_base_url: str = "https://rag-service-p3cxgvcsla-uc.a.run.app",
        timeout_seconds: int = 30,
        default_k: int = 5,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-2.0-flash-lite"
    ):
        """
        Initialize the brand voice checker.

        Args:
            rag_base_url: Base URL for RAG service
            timeout_seconds: Request timeout
            default_k: Default number of results to return
            gemini_api_key: API key for Gemini (for compliance analysis)
            gemini_model: Gemini model to use
        """
        self.base_url = rag_base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.default_k = default_k
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model

        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.model = genai.GenerativeModel(gemini_model)
        else:
            self.model = None

    async def search_rag(
        self,
        query: str,
        client_id: str,
        phase: str = "STRATEGY",
        k: Optional[int] = None
    ) -> List[RAGResult]:
        """
        Search the RAG service for relevant documents.

        Args:
            query: Search query
            client_id: Client identifier
            phase: Workflow phase (STRATEGY, BRIEF, VISUAL, GENERAL)
            k: Number of results to return

        Returns:
            List of RAGResult objects
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/rag/search",
                    json={
                        "query": query,
                        "client_id": client_id,
                        "phase": phase,
                        "k": k or self.default_k
                    }
                )
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict):
                    items = data.get("results") or data.get("documents") or data.get("data") or []
                elif isinstance(data, list):
                    items = data
                else:
                    items = []

                results = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    results.append(RAGResult(
                        content=item.get("content") or item.get("text") or "",
                        metadata=item.get("metadata") or {},
                        relevance_score=item.get("relevance_score", item.get("score", 0.0)),
                        source=(item.get("metadata") or {}).get("source")
                    ))

                logger.info(f"RAG search returned {len(results)} results for client {client_id}")
                return results

            except httpx.HTTPError as e:
                logger.error(f"RAG search failed: {e}")
                return []

    async def get_brand_voice(self, client_id: str) -> List[RAGResult]:
        """
        Fetch brand voice guidelines from RAG.

        Args:
            client_id: Client identifier

        Returns:
            List of brand voice related documents
        """
        # Search for brand voice related content
        results = await self.search_rag(
            query="brand voice guidelines tone messaging style personality",
            client_id=client_id,
            phase="STRATEGY",
            k=5
        )

        # Also search for brand pillars and values
        additional = await self.search_rag(
            query="brand pillars values mission key messages",
            client_id=client_id,
            phase="STRATEGY",
            k=3
        )

        # Combine and deduplicate
        seen_content = set()
        combined = []
        for result in results + additional:
            content_key = result.content[:100]  # Use first 100 chars as key
            if content_key not in seen_content:
                seen_content.add(content_key)
                combined.append(result)

        return combined

    async def get_past_campaign_patterns(
        self,
        client_id: str,
        campaign_type: Optional[str] = None
    ) -> List[RAGResult]:
        """
        Retrieve past campaign patterns for reference.

        Args:
            client_id: Client identifier
            campaign_type: Optional type (promotional, newsletter, etc.)

        Returns:
            List of past campaign related documents
        """
        query = "past email campaign examples patterns successful"
        if campaign_type:
            query = f"{campaign_type} {query}"

        return await self.search_rag(
            query=query,
            client_id=client_id,
            phase="STRATEGY",
            k=5
        )

    async def check_copy_compliance(
        self,
        client_id: str,
        email_copy: Dict[str, Any],
        brand_guidelines: Optional[List[RAGResult]] = None,
        brief_text: Optional[str] = None
    ) -> BrandVoiceComplianceResult:
        """
        Compare email copy against brand voice using LLM.

        Args:
            client_id: Client identifier
            email_copy: Dictionary with headline, subheadline, body_preview, cta_text
            brand_guidelines: Pre-fetched guidelines (fetches if None)

        Returns:
            BrandVoiceComplianceResult with detailed analysis
        """
        # Fetch guidelines if not provided
        if brand_guidelines is None:
            brand_guidelines = await self.get_brand_voice(client_id)

        # If no guidelines found, return high compliance (no basis to judge)
        if not brand_guidelines:
            logger.warning(f"No brand guidelines found for client {client_id}")
            return BrandVoiceComplianceResult(
                is_compliant=True,
                compliance_score=1.0,
                analysis_notes="No brand guidelines found in RAG - unable to verify compliance"
            )

        # If no LLM configured, return basic result
        if not self.model:
            logger.warning("Gemini not configured for compliance check")
            return BrandVoiceComplianceResult(
                is_compliant=True,
                compliance_score=0.8,
                brand_guidelines_used=[r.source or "Unknown" for r in brand_guidelines[:3]],
                analysis_notes="LLM not configured - manual review recommended"
            )

        # Format guidelines for prompt
        guidelines_text = "\n\n".join([
            f"[{r.source or 'Document'}]:\n{r.content[:500]}"
            for r in brand_guidelines[:5]
        ])

        # Format email copy
        headline = email_copy.get("headline", "")
        subheadline = email_copy.get("subheadline", "")
        body_preview = email_copy.get("body_preview", "")
        cta_text = ", ".join(email_copy.get("cta_text", []))

        # Build prompt
        prompt = self.COMPLIANCE_CHECK_PROMPT.format(
            guidelines=guidelines_text,
            brief=brief_text or "(not provided)",
            headline=headline or "(not provided)",
            subheadline=subheadline or "(not provided)",
            body_preview=body_preview or "(not provided)",
            cta_text=cta_text or "(not provided)"
        )

        try:
            # Generate analysis
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1000
                )
            )

            # Parse response
            result = self._parse_compliance_response(response.text)
            result.brand_guidelines_used = [r.source or "Unknown" for r in brand_guidelines[:5]]

            logger.info(f"Compliance check complete: score={result.compliance_score}")
            return result

        except Exception as e:
            logger.error(f"Compliance check failed: {e}")
            return BrandVoiceComplianceResult(
                is_compliant=True,
                compliance_score=0.7,
                brand_guidelines_used=[r.source or "Unknown" for r in brand_guidelines[:3]],
                recommendations=[f"Manual review needed - analysis error: {str(e)}"]
            )

    def _parse_compliance_response(self, response_text: str) -> BrandVoiceComplianceResult:
        """Parse LLM response into BrandVoiceComplianceResult."""
        import json

        # Try to extract JSON
        try:
            # Try direct parse
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON in response
            if "{" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                try:
                    data = json.loads(response_text[start:end])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}

        if not data:
            return BrandVoiceComplianceResult(
                analysis_notes="Could not parse compliance response"
            )

        return BrandVoiceComplianceResult(
            is_compliant=data.get("is_compliant", True),
            compliance_score=float(data.get("compliance_score", 0.8)),
            tone_alignment=data.get("tone_alignment", {}),
            vocabulary_issues=data.get("vocabulary_issues", []),
            messaging_issues=data.get("messaging_issues", []),
            recommendations=data.get("recommendations", []),
            analysis_notes=data.get("analysis_notes")
        )
