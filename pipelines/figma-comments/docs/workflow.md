### **File 2: Figma Feedback Ingestion Pipeline**

```markdown
# Technical Blueprint: Figma Feedback Ingestion Pipeline
**Role:** Creative Quality Control (The Guardrails)
**Target System:** V3 Stage 4 (Creative Specifications)
**Priority:** High (Phase 2)

---

## 1. Executive Summary
This pipeline connects client feedback stored in BigQuery directly to the AI's creative process. It parses raw Figma comments to extract "Creative Rules" (Do's and Don'ts), preventing the AI from repeating rejected mistakes.

## 2. Architecture Overview


**Trigger:** Daily Schedule (or Event-Driven via BigQuery Log Sink).
**Infrastructure:** Google Cloud Function (Python).
**Data Source:** BigQuery.
**AI Model:** Gemini 1.5 Pro (Optimized for reasoning/nuance).

---

## 3. Implementation Steps

### Component A: The "Fetcher" (BigQuery SQL)
**Responsibility:** Retrieve only *new* comments that contain actual feedback.

**SQL Logic:**
```sql
SELECT 
  comment_id,
  file_key,
  comment_text, 
  created_at,
  user_name
FROM `project.figma.comments`
WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
  AND user_name NOT LIKE '%Internal%'  -- Filter out internal team chatter
  AND LENGTH(comment_text) > 10        -- Filter out "Done" or "Ok"
Component B: The "Processor" (AI Intermediary)
Responsibility: Distill "noise" (logistics) into "signal" (creative direction).

System Prompt:

Role: You are a Creative Director auditing feedback. Task: Analyze these design comments.

Ignore: Logistics ("Move pixel left", "Export this").

Extract: Strategic feedback on Tone, Copy, or Imagery.

Classify:

Negative: "Client hates X"

Positive: "Client loves Y" Input: "{comment_text}" Output: JSON { "rule": "Do not use puns", "sentiment": "negative", "category": "tone" }

Component C: The "Ingester" (Vertex AI)
Responsibility: Append new rules to the Client's Knowledge Base.

Strategy: Append

Strategy: Append. History is valuable here. We want a record of all feedback over time.

Metadata Schema:

JSON

{
  "doc_type": "creative_rule",
  "client_id": "acme-corp",
  "category": "copy",       // Allows Stage 4 query: "Get copy restrictions"
  "sentiment": "negative",  // Allows Stage 4 query: "What should I avoid?"
  "source_file": "Q4_Holiday_Promo"
}
4. Failure Modes & Safety
Context Loss: A comment "Change this" is meaningless without the visual.

Mitigation: The AI Processor should be prompted to discard ambiguous comments it cannot interpret from text alone.

Volume Spike: A massive design file might generate 500 comments.

Mitigation: Use BigQuery LIMIT or batch processing to prevent blowing API budgets.

5. Definition of Done
[ ] SQL Query returning clean comment stream.

[ ] Gemini successfully identifying "Strategic" vs "Logistical" comments.

[ ] V3 Stage 4 prompt successfully retrieving "Negative Constraints" before generating copy.
