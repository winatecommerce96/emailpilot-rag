"""
LLM-based Document Categorization Service

Automatically categorizes documents during RAG ingestion using Claude
to determine the most appropriate category based on content analysis.

This ensures consistent categorization across all clients and improves
retrieval quality by matching content to the correct phase filters.
"""

import os
import json
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List
import httpx

logger = logging.getLogger(__name__)

# Standard RAG categories that align with PHASE_MAPPING in vertex_search.py
STANDARD_CATEGORIES = {
    "brand_voice": {
        "description": "Brand voice guidelines, tone of voice, messaging style, communication principles",
        "keywords": ["voice", "tone", "messaging", "style", "communication", "personality"],
        "phase": "STRATEGY"
    },
    "content_pillars": {
        "description": "Content themes, messaging pillars, strategic topics, key narratives",
        "keywords": ["pillars", "themes", "topics", "narratives", "content strategy"],
        "phase": "STRATEGY"
    },
    "brand_guidelines": {
        "description": "Visual brand guidelines, logo usage, color palettes, typography, design standards",
        "keywords": ["logo", "colors", "typography", "visual", "design", "brand guide"],
        "phase": "VISUAL"
    },
    "product": {
        "description": "Product catalog, SKUs, pricing, product descriptions, inventory",
        "keywords": ["product", "sku", "price", "catalog", "inventory", "item"],
        "phase": "BRIEF"
    },
    "target_audience": {
        "description": "Customer personas, demographics, audience segments, buyer profiles",
        "keywords": ["audience", "persona", "demographic", "customer", "segment"],
        "phase": "STRATEGY"
    },
    "past_campaign": {
        "description": "Previous campaign examples, marketing history, performance data",
        "keywords": ["campaign", "marketing", "performance", "history", "results"],
        "phase": "STRATEGY"
    },
    "seasonal_themes": {
        "description": "Seasonal content themes, holiday campaigns, calendar events",
        "keywords": ["seasonal", "holiday", "calendar", "event", "promotion"],
        "phase": "STRATEGY"
    },
    "marketing_strategy": {
        "description": "Overall marketing strategy, content strategy, campaign themes (general category for mixed content)",
        "keywords": ["strategy", "marketing", "themes", "approach"],
        "phase": "STRATEGY"
    },
    "general": {
        "description": "General content that doesn't fit other categories",
        "keywords": [],
        "phase": "GENERAL"
    }
}


def get_category_prompt() -> str:
    """Generate the categorization prompt with all available categories."""
    category_list = "\n".join([
        f"- {name}: {info['description']}"
        for name, info in STANDARD_CATEGORIES.items()
        if name != "general"  # Don't explicitly offer general
    ])

    return f"""You are a document categorization assistant for a marketing automation platform.
Your task is to analyze the content and assign the most appropriate category.

Available categories:
{category_list}

Rules:
1. Choose the SINGLE most appropriate category based on the primary content
2. If content spans multiple areas, choose the dominant one
3. Only use "general" if content truly doesn't fit any other category
4. For brand style guides that include both voice AND visual guidelines, prefer "brand_guidelines" if visual elements dominate, "brand_voice" if messaging dominates
5. Marketing strategy documents with mixed content should use "marketing_strategy"

Respond with ONLY the category name (e.g., "brand_voice"), nothing else."""


@dataclass
class CategorizationResult:
    """Result of document categorization including keywords."""
    category: str
    confidence: float
    keywords: List[str]
    method: str  # "llm" or "keyword"


async def categorize_with_llm(
    content: str,
    title: Optional[str] = None,
    max_content_chars: int = 4000,
    generate_keywords: bool = True
) -> Tuple[str, float, List[str]]:
    """
    Use Claude to categorize document content and generate keywords.

    Args:
        content: The document content to categorize
        title: Optional document title for additional context
        max_content_chars: Maximum content characters to send to LLM
        generate_keywords: Whether to also generate keywords

    Returns:
        Tuple of (category_name, confidence_score, keywords_list)
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        logger.warning("ANTHROPIC_API_KEY not set, falling back to keyword matching")
        cat, conf = categorize_with_keywords(content, title)
        keywords = suggest_keywords_from_content(content) if generate_keywords else []
        return (cat, conf, keywords)

    # Truncate content for LLM
    truncated_content = content[:max_content_chars]
    if len(content) > max_content_chars:
        truncated_content += "\n... [content truncated]"

    # Build the user message - ask for both category AND keywords
    user_message = f"""Analyze this document:

Title: {title or 'Untitled'}

Content:
{truncated_content}

Respond with JSON in this exact format:
{{"category": "category_name", "keywords": ["keyword1", "keyword2", "keyword3"]}}

Rules for keywords:
- Extract 3-8 relevant keywords/phrases that describe the content
- Include brand names, product names, key topics, and themes
- Use lowercase for general terms, preserve case for proper nouns
- Focus on terms useful for search and retrieval"""

    system_prompt = get_category_prompt() + """

After determining the category, also extract relevant keywords from the content.
Respond ONLY with valid JSON containing "category" and "keywords" fields."""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-haiku-latest",  # Fast, cheap model for categorization
                    "max_tokens": 200,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_message}]
                }
            )

            if response.status_code != 200:
                logger.error(f"LLM categorization failed: {response.status_code} - {response.text}")
                cat, conf = categorize_with_keywords(content, title)
                keywords = suggest_keywords_from_content(content) if generate_keywords else []
                return (cat, conf, keywords)

            result = response.json()
            text_response = result.get("content", [{}])[0].get("text", "").strip()

            # Parse JSON response
            try:
                parsed = json.loads(text_response)
                category = parsed.get("category", "").lower()
                keywords = parsed.get("keywords", [])

                # Validate category
                if category not in STANDARD_CATEGORIES:
                    logger.warning(f"LLM returned invalid category '{category}', falling back to keywords")
                    cat, conf = categorize_with_keywords(content, title)
                    return (cat, conf, keywords if keywords else suggest_keywords_from_content(content))

                logger.info(f"LLM categorized document as: {category} with {len(keywords)} keywords")
                return (category, 0.9, keywords[:10])  # Cap at 10 keywords

            except json.JSONDecodeError:
                # Fallback: try to extract just the category
                category = text_response.lower().strip()
                if category in STANDARD_CATEGORIES:
                    keywords = suggest_keywords_from_content(content) if generate_keywords else []
                    return (category, 0.8, keywords)
                else:
                    cat, conf = categorize_with_keywords(content, title)
                    keywords = suggest_keywords_from_content(content) if generate_keywords else []
                    return (cat, conf, keywords)

    except Exception as e:
        logger.error(f"LLM categorization error: {e}")
        cat, conf = categorize_with_keywords(content, title)
        keywords = suggest_keywords_from_content(content) if generate_keywords else []
        return (cat, conf, keywords)


def categorize_with_keywords(
    content: str,
    title: Optional[str] = None
) -> Tuple[str, float]:
    """
    Fallback keyword-based categorization when LLM is unavailable.

    Args:
        content: The document content to categorize
        title: Optional document title for additional context

    Returns:
        Tuple of (category_name, confidence_score)
    """
    combined_text = f"{title or ''} {content}".lower()

    # Count keyword matches for each category
    scores = {}
    for category, info in STANDARD_CATEGORIES.items():
        if not info["keywords"]:  # Skip general
            continue
        score = sum(1 for kw in info["keywords"] if kw in combined_text)
        if score > 0:
            scores[category] = score

    if not scores:
        return ("general", 0.3)

    # Return category with highest score
    best_category = max(scores, key=scores.get)
    confidence = min(0.7, scores[best_category] / len(STANDARD_CATEGORIES[best_category]["keywords"]))

    logger.info(f"Keyword categorization: {best_category} (confidence: {confidence:.2f})")
    return (best_category, confidence)


def suggest_keywords_from_content(content: str, max_keywords: int = 10) -> List[str]:
    """
    Extract potential keywords/tags from document content.

    Args:
        content: The document content
        max_keywords: Maximum number of keywords to return

    Returns:
        List of suggested keywords
    """
    # Simple keyword extraction - look for capitalized phrases and common marketing terms
    import re

    keywords = set()

    # Extract capitalized multi-word phrases (likely proper nouns/brand terms)
    caps_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b'
    keywords.update(re.findall(caps_pattern, content)[:5])

    # Marketing-relevant terms
    marketing_terms = [
        "email", "campaign", "brand", "customer", "audience",
        "product", "seasonal", "holiday", "promotion", "engagement",
        "conversion", "segment", "persona", "voice", "tone"
    ]
    for term in marketing_terms:
        if term.lower() in content.lower():
            keywords.add(term)

    return list(keywords)[:max_keywords]


# Export for use in main.py
__all__ = [
    "categorize_with_llm",
    "categorize_with_keywords",
    "suggest_keywords_from_content",
    "STANDARD_CATEGORIES"
]
