### **RAG_INTEGRATION_GUIDE.md**

--- START OF FILE ---

# EmailPilot RAG Service - Integration Guide

**Version:** 1.0
**Backend:** Google Vertex AI Search (Structured Data)
**Protocol:** REST / HTTP JSON

---

## Overview

The EmailPilot RAG Service is a standalone microservice that provides **Context-Aware Intelligence** for the orchestration app. It does not just search text; it filters information based on the **Marketing Phase** (Strategy, Briefs, Visuals) to ensure the LLM gets only the most relevant data.

### Base URLs

| Environment | URL |
| :--- | :--- |
| **Local Development** | `http://localhost:8001` |
| **Production (Cloud Run)** | `https://[YOUR-SERVICE-URL].run.app` |

---

## Core Endpoint: Search

**`POST /api/rag/search`**

Retrieves context chunks relevant to a specific client and query.

### 1. Request Payload

**Content-Type:** `application/json`

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `client_id` | `string` | **Yes** | The exact slug of the client (e.g., `rogue-creamery`). **Strictly enforces data isolation.** |
| `query` | `string` | **Yes** | The natural language question (e.g., "What is the holiday pricing?", "Brand voice guidelines"). |
| `phase` | `string` | No | Controls what *type* of data is returned. Defaults to `GENERAL`. (See "Phases" below). |
| `k` | `int` | No | Number of results to return. Default is `5`. |

**Example JSON:**
```json
{
  "client_id": "rogue-creamery",
  "query": "How should we talk about our cheese?",
  "phase": "STRATEGY",
  "k": 5
}
```

### 2. The "Phases" (Smart Filtering)

The `phase` parameter changes the behavior of the search engine. Use the phase that matches the task you are performing.

| Phase Name | What it searches | Use Case |
| :--- | :--- | :--- |
| **`STRATEGY`** | Brand Voice, Past Campaigns | Generating high-level marketing plans or copy tone checks. |
| **`BRIEF`** | Product Specs, Brand Voice | Writing specific email briefs where SKU details and pricing matter. |
| **`VISUAL`** | Visual Assets | Looking for image descriptions or design guidelines. |
| **`GENERAL`** | *Everything* | Debugging or broad research. |

*Note: All phases also include "General" data as a fallback to ensure you never get zero results.*

---

### 3. Response Format

The service returns a JSON **List** of result objects.

**Example Response:**
```json
[
  {
    "content": "Our brand voice is that of a knowledgeable, passionate friend...",
    "metadata": {
      "client_id": "rogue-creamery",
      "category": "brand_voice",
      "source": "brand_guidelines_2025.pdf",
      "title": "rogue-creamery - brand_voice"
    },
    "relevance_score": 0.9
  },
  {
    "content": "Use warm, earthy tones in all holiday photography...",
    "metadata": {
      "client_id": "rogue-creamery",
      "category": "past_campaign",
      "source": "holiday_2024_retro.txt",
      "title": "rogue-creamery - past_campaign"
    },
    "relevance_score": 0.85
  }
]
```

---

## Python Integration Example (The "Adapter")

If you are connecting from the main **EmailPilot Orchestrator**, do not call the URL directly in your logic. Use this Adapter class to keep your code clean.

**`services/rag_client.py`**

```python
import httpx
import os
from typing import List, Dict, Any

# Auto-detect environment
RAG_URL = os.getenv("RAG_SERVICE_URL", "http://localhost:8001/api/rag/search")

class RAGClient:
    """
    Adapter to talk to the RAG Microservice.
    """
    async def get_context(
        self, 
        client_id: str, 
        query: str, 
        phase: str = "GENERAL"
    ) -> List[Dict[str, Any]]:
        """
        Retrieves context from the RAG service.
        Returns an empty list [] if the service is down or fails.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    RAG_URL,
                    json={
                        "client_id": client_id,
                        "query": query,
                        "phase": phase
                    },
                    timeout=10.0 # 10 second timeout
                )
                response.raise_for_status()
                return response.json()
                
            except httpx.RequestError as e:
                # Log error but don't crash the main app
                print(f"[RAG Client] Connection Error: {e}")
                return []
            except httpx.HTTPStatusError as e:
                print(f"[RAG Client] API Error {e.response.status_code}: {e.response.text}")
                return []

# --- Usage ---
# rag = RAGClient()
# context = await rag.get_context("rogue-creamery", "pricing", "BRIEF")
```

---

## Troubleshooting

| HTTP Code | Meaning | Fix |
| :--- | :--- | :--- |
| **200** | Success | Data returned (could be empty list `[]` if no matches found). |
| **400** | Bad Request | Check your `phase` spelling or Ensure `client_id` is a string. |
| **422** | Validation Error | Your JSON is missing a required field (usually `client_id`). |
| **500** | Server Error | The RAG service crashed. Check Cloud Run logs. |

--- END OF FILE ---