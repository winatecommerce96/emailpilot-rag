Product Velocity Ingestion Pipeline
Markdown

# Technical Blueprint: Product Velocity Ingestion Pipeline
**Role:** The Revenue Engine
**Target System:** V3 Stage 1 (Analysis) & Stage 3 (Architecture)
**Priority:** Critical (Phase 1)

---

## 1. Executive Summary
This pipeline automates the ingestion of real-time product performance data into the RAG system. It transforms raw sales metrics into "narrative assets" (Social Proof copy) that the AI Copywriter can use immediately. It ensures the V3 Workflow mathematically selects the correct "Hero Products" for every campaign.

## 2. Architecture Overview


**Trigger:** Daily Schedule (06:00 UTC) via Cloud Scheduler.
**Infrastructure:** Google Cloud Function (Python).
**AI Model:** Gemini 1.5 Flash (Optimized for speed/cost).

---

## 3. Implementation Steps

### Component A: The "Fetcher" (API Client)
**Responsibility:** Retrieve raw metric data from the internal `/product` endpoint.

**Logic:**
1. Call `GET /product?metrics=velocity,revenue,inventory&window=7d`.
2. **Filtering:** Discard products with `inventory_status = 'out_of_stock'`.
3. **Calculation:**
   * `velocity_score`: (Units Sold 7d) / (Units Sold Previous 7d).
   * `revenue_tier`: Rank top 10% as "High AOV".

**Python Snippet (Conceptual):**
```python
def fetch_product_data():
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(INTERNAL_PRODUCT_API, headers=headers)
    products = response.json()
    
    # Filter OOS
    active_products = [p for p in products if p['inventory_count'] > 50]
    return active_products
Component B: The "Narrator" (AI Intermediary)
Responsibility: Pre-compute copy assets so the main V3 workflow doesn't have to "do math" to write copy.

System Prompt:

Role: You are a Merchandising Copywriter. Input: Product Name: {name}, 7-Day Sales: {units}, Growth: {velocity}%. Task: Write 3 short "Social Proof" snippets for an email.

Bandwagon: "Join [units] people who bought this week."

Trending: "Demand is up [velocity]% - selling fast."

Scarcity: (If inventory < 100) "Only a few left." Output: JSON only.

Component C: The "Ingester" (Vertex AI)
Responsibility: Update the Vector Index.

Strategy: Overwrite vs. Append

Strategy: Overwrite. Yesterday's velocity is irrelevant today.

Doc ID Generation: Use doc_id = f"product_velocity_{sku}" to ensure new data replaces old data.

Metadata Schema:

JSON

{
  "doc_type": "product_insight",
  "sku": "12345",
  "name": "Hydration Pack V2",
  "velocity_tier": "trending",  // Allows Stage 1 query: "Show me trending products"
  "revenue_tier": "high_aov"    // Allows Stage 3 query: "Show me high revenue drivers"
}
4. Failure Modes & Safety
API Failure: If /product returns 500, halt pipeline. Do not overwrite yesterday's data with zero values.

Hallucination Risk: Gemini might invent sales numbers. Mitigation: Pass the raw numbers into the prompt as "Context" but strictly forbid the AI from altering the integers.

5. Definition of Done
[ ] Cloud Function deployed.

[ ] Successfully hitting /product endpoint.

[ ] Gemini generating "Social Proof" snippets.

[ ] Stage 1 Analysis prompt successfully retrieving "High Velocity" products via RAG.