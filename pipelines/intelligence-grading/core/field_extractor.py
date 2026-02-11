"""
Field Extractor for Intelligence Grading.

Uses Gemini AI to analyze documents and extract structured intelligence fields.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedField:
    """A field extracted from documents."""
    field_name: str
    found: bool
    coverage: float  # 0-100 percentage of how well the field is covered
    content_summary: Optional[str] = None
    source_documents: List[str] = field(default_factory=list)
    confidence: float = 0.0
    raw_content: Optional[str] = None


@dataclass
class ExtractionResult:
    """Result of field extraction for a client."""
    client_id: str
    fields: Dict[str, ExtractedField] = field(default_factory=dict)
    documents_analyzed: int = 0
    total_content_length: int = 0


class FieldExtractor:
    """
    Extracts intelligence fields from documents using Gemini AI.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Gemini API key."""
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._model = None

    def _get_model(self):
        """Lazy initialization of Gemini model."""
        if self._model is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel('gemini-2.0-flash')
                logger.info("Initialized Gemini model for field extraction")
            except ImportError:
                logger.warning("google-generativeai not installed, using keyword-based extraction only")
                self._model = "disabled"
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self._model = "disabled"

        return self._model if self._model != "disabled" else None

    async def extract_fields_from_documents(
        self,
        documents: List[Dict[str, Any]],
        field_requirements: List[Any],
        client_id: str
    ) -> ExtractionResult:
        """
        Extract intelligence fields from a list of documents.

        Args:
            documents: List of documents with 'content', 'title', 'source_type' keys
            field_requirements: List of FieldRequirement objects to extract
            client_id: Client identifier

        Returns:
            ExtractionResult with extracted fields
        """
        result = ExtractionResult(
            client_id=client_id,
            documents_analyzed=len(documents)
        )

        if not documents:
            return result

        # Combine all document content (sorted by category priority)
        combined_content = self._prepare_content(documents)
        result.total_content_length = len(combined_content)
        logger.info(
            f"Prepared {len(documents)} documents for {client_id}: "
            f"{len(combined_content):,} chars combined, "
            f"{'will truncate to 200K' if len(combined_content) > 200000 else 'fits in context window'}"
        )

        # Try AI extraction first, fall back to keyword matching
        model = self._get_model()
        if model:
            result.fields = await self._extract_with_ai(
                combined_content, field_requirements, documents
            )
        else:
            result.fields = self._extract_with_keywords(
                combined_content, field_requirements, documents
            )

        return result

    # Category priority for content ordering — higher-value categories first
    # so they survive any content truncation
    CATEGORY_PRIORITY = {
        "brand_voice": 0,
        "brand_guidelines": 1,
        "target_audience": 2,
        "product": 3,
        "products": 3,
        "product_catalog": 3,
        "product_spec": 3,
        "marketing_strategy": 4,
        "content_pillars": 5,
        "seasonal_themes": 6,
        "past_campaign": 7,
        "quick_capture": 8,
        "general": 9,
    }

    def _prepare_content(self, documents: List[Dict[str, Any]]) -> str:
        """Prepare combined content from documents, sorted by category priority."""
        # Sort documents so highest-value categories come first
        sorted_docs = sorted(
            documents,
            key=lambda d: self.CATEGORY_PRIORITY.get(
                d.get("source_type", "general"), 8
            )
        )

        sections = []
        for doc in sorted_docs:
            title = doc.get("title", "Untitled")
            source_type = doc.get("source_type", "general")
            content = doc.get("content", "")

            if content:
                sections.append(f"=== {title} ({source_type}) ===\n{content}")

        return "\n\n".join(sections)

    async def _extract_with_ai(
        self,
        content: str,
        field_requirements: List[Any],
        documents: List[Dict[str, Any]]
    ) -> Dict[str, ExtractedField]:
        """Use Gemini AI to extract fields from content."""
        import asyncio

        # Build the extraction prompt
        fields_to_extract = []
        field_names = []  # Track expected field names
        for req in field_requirements:
            field_names.append(req.name)
            fields_to_extract.append({
                "name": req.name,
                "display_name": req.display_name,
                "description": req.description,
                "questions": req.extraction_questions[:3] if req.extraction_questions else []
            })

        prompt = f"""You are analyzing a brand's knowledge base documents to determine what information is available for email marketing calendar generation.

For each field below, determine if the documents contain ANY relevant information — even partial, indirect, or implied information counts as "found".

RULES:
- Be GENEROUS in detection. If a document mentions anything related to the field, mark it as found.
- Coverage should reflect completeness: 20 = minimal mention, 50 = partial info, 80 = solid coverage, 100 = comprehensive.
- If information is spread across multiple documents, combine the coverage (don't penalize for fragmentation).
- When in doubt, lean toward "found": true with lower coverage rather than "found": false.

For each field, provide:
1. "found": true/false — is there ANY relevant information?
2. "coverage": 0-100 — how complete is the information?
3. "summary": Brief summary of what was found (or null if not found)
4. "confidence": 0-1 — how confident you are

IMPORTANT: Use EXACTLY these field names as keys in your response:
{json.dumps(field_names)}

FIELDS TO EXTRACT:
{json.dumps(fields_to_extract, indent=2)}

DOCUMENTS:
{content[:200000]}

Respond with valid JSON only:
{{
    "field_name": {{
        "found": true/false,
        "coverage": 0-100,
        "summary": "Brief summary of found content" or null,
        "confidence": 0.0-1.0
    }},
    ...
}}
"""

        try:
            model = self._get_model()
            if not model:
                logger.warning("AI model not available, using keyword extraction")
                return self._extract_with_keywords(content, field_requirements, documents)

            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json"
                }
            )

            # Parse the response
            response_text = response.text.strip()
            logger.debug(f"AI response (first 500 chars): {response_text[:500]}")

            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                parts = response_text.split("```")
                if len(parts) >= 2:
                    response_text = parts[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                    response_text = response_text.strip()

            extracted_data = json.loads(response_text)

            # Convert to ExtractedField objects
            result = {}
            doc_titles = [d.get("title", "Unknown") for d in documents]

            # Ensure ALL required fields are in result (even if AI missed them)
            for req in field_requirements:
                field_name = req.name
                field_data = extracted_data.get(field_name, {})

                if field_data:
                    result[field_name] = ExtractedField(
                        field_name=field_name,
                        found=field_data.get("found", False),
                        coverage=field_data.get("coverage", 0),
                        content_summary=field_data.get("summary"),
                        source_documents=doc_titles if field_data.get("found") else [],
                        confidence=field_data.get("confidence", 0.5)
                    )
                else:
                    # AI didn't return this field - try keyword fallback for this field
                    keyword_result = self._extract_single_field_with_keywords(
                        content, req, documents
                    )
                    result[field_name] = keyword_result

            logger.info(f"AI extraction complete: {sum(1 for f in result.values() if f.found)}/{len(result)} fields found")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"AI extraction JSON parse failed: {e}, falling back to keywords")
            return self._extract_with_keywords(content, field_requirements, documents)
        except Exception as e:
            logger.error(f"AI extraction failed: {e}, falling back to keywords")
            import traceback
            traceback.print_exc()
            return self._extract_with_keywords(content, field_requirements, documents)

    def _extract_single_field_with_keywords(
        self,
        content: str,
        field_req: Any,
        documents: List[Dict[str, Any]]
    ) -> ExtractedField:
        """Extract a single field using keyword matching."""
        content_lower = content.lower()
        matches = 0
        total_keywords = len(field_req.detection_keywords)

        for keyword in field_req.detection_keywords:
            if keyword.lower() in content_lower:
                matches += 1

        if total_keywords > 0:
            match_ratio = matches / total_keywords
            found = match_ratio > 0.1
            coverage = min(100, int(match_ratio * 150))
        else:
            found = False
            coverage = 0

        source_docs = []
        for doc in documents:
            doc_content = doc.get("content", "").lower()
            if any(kw.lower() in doc_content for kw in field_req.detection_keywords):
                source_docs.append(doc.get("title", "Unknown"))

        return ExtractedField(
            field_name=field_req.name,
            found=found,
            coverage=coverage,
            content_summary=f"Found {matches}/{total_keywords} keywords" if found else None,
            source_documents=source_docs,
            confidence=0.6 if found else 0.3
        )

    def _extract_with_keywords(
        self,
        content: str,
        field_requirements: List[Any],
        documents: List[Dict[str, Any]]
    ) -> Dict[str, ExtractedField]:
        """Fallback keyword-based field extraction."""
        content_lower = content.lower()
        result = {}

        for req in field_requirements:
            # Count keyword matches
            matches = 0
            total_keywords = len(req.detection_keywords)

            for keyword in req.detection_keywords:
                if keyword.lower() in content_lower:
                    matches += 1

            # Calculate coverage based on keyword matches
            if total_keywords > 0:
                match_ratio = matches / total_keywords
                found = match_ratio > 0.1  # At least 10% of keywords found
                coverage = min(100, int(match_ratio * 150))  # Scale up but cap at 100
            else:
                found = False
                coverage = 0

            # Find which documents contain the keywords
            source_docs = []
            for doc in documents:
                doc_content = doc.get("content", "").lower()
                if any(kw.lower() in doc_content for kw in req.detection_keywords):
                    source_docs.append(doc.get("title", "Unknown"))

            result[req.name] = ExtractedField(
                field_name=req.name,
                found=found,
                coverage=coverage,
                content_summary=f"Found {matches}/{total_keywords} keywords" if found else None,
                source_documents=source_docs,
                confidence=0.6 if found else 0.3  # Lower confidence for keyword matching
            )

        return result

    async def extract_single_field(
        self,
        content: str,
        field_name: str,
        field_description: str,
        extraction_questions: List[str]
    ) -> ExtractedField:
        """Extract a single field from content."""
        model = self._get_model()
        if not model:
            return ExtractedField(
                field_name=field_name,
                found=False,
                coverage=0
            )

        prompt = f"""Analyze this content and extract information about: {field_name}

Description: {field_description}

Questions to answer:
{chr(10).join(f'- {q}' for q in extraction_questions)}

CONTENT:
{content[:100000]}

Respond with JSON:
{{
    "found": true/false,
    "coverage": 0-100,
    "summary": "extracted content summary" or null,
    "confidence": 0.0-1.0
}}
"""

        try:
            import asyncio
            response = await asyncio.to_thread(
                model.generate_content,
                prompt,
                generation_config={
                    "temperature": 0.0,
                    "response_mime_type": "application/json"
                }
            )

            data = json.loads(response.text.strip())
            return ExtractedField(
                field_name=field_name,
                found=data.get("found", False),
                coverage=data.get("coverage", 0),
                content_summary=data.get("summary"),
                confidence=data.get("confidence", 0.5)
            )

        except Exception as e:
            logger.error(f"Single field extraction failed: {e}")
            return ExtractedField(
                field_name=field_name,
                found=False,
                coverage=0
            )
