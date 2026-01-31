# Technical Blueprint: Image Asset Ingestion Pipeline
**Role:** The Visual Librarian
**Target System:** V3 Stage 4 (Creative Specifications)
**Priority:** Medium/High (Phase 2 alongside Figma)

---

## 1. Executive Summary
This pipeline transforms a passive Google Drive folder of images into an active "Visual Database" for the AI. By auto-captioning every image using Multimodal AI, it allows the V3 Campaign Architect to "see" what assets are available and reference specific files in the campaign specifications, reducing the burden on designers to hunt for matching assets.

## 2. Architecture Overview


**Trigger:** Eventarc (Google Drive Event) or Polling (Hourly).
**Infrastructure:** Google Cloud Function (Python).
**AI Model:** Gemini 1.5 Flash (Multimodal - Optimized for speed/vision).

---

## 3. Implementation Steps

### Component A: The "Watcher" (Drive Trigger)
**Responsibility:** Detect new image uploads in specific Client folders.

**Strategy:**
* **Option 1 (Push):** Configure Google Cloud Eventarc to listen for `google.cloud.storage.object.v1.finalized` if using GCS, or poll the Drive API `changes.list` endpoint if using Workspace Drive.
* **Option 2 (Poll - Recommended for Drive):** A Cloud Function runs hourly, listing files in the specific `Client_Images` folder where `createdTime > last_check_time`.

**Python Logic:**
```python
def check_drive_for_images():
    query = "mimeType contains 'image/' and trashed = false and parents in 'FOLDER_ID'"
    results = drive_service.files().list(q=query).execute()
    return new_images
Component B: The "Describer" (AI Intermediary)
Responsibility: Convert visual pixels into searchable text metadata.

System Prompt:

Role: Digital Asset Manager. Task: Analyze this image for a marketing database.

Describe: What is happening? (e.g., "Family eating dinner outside").

Mood/Tone: (e.g., "Warm, energetic, rustic").

Colors: Dominant colors.

Text: Extract any visible text (OCR). Input: [Image Byte Stream] Output: JSON description.

Why Gemini 1.5 Flash? It is extremely fast and cheap for image analysis, making it viable to process thousands of historical images in a single batch.

Component C: The "Ingester" (Vertex AI)
Responsibility: Index the image descriptions so they can be searched by "Concept".

Metadata Schema:

JSON

{
  "doc_type": "image_asset",
  "client_id": "acme-corp",
  "file_name": "summer_campaign_01.jpg",
  "drive_link": "[https://drive.google.com/file/d/](https://drive.google.com/file/d/)...",
  "visual_tags": ["outdoors", "family", "dinner", "sunset"],
  "mood": "warm"
}
4. Workflow Integration (The "Payoff")
How this changes the Stage 4 (Creative) prompt:

Old Way:

"Hero Image Description: Something warm and family oriented."

New Way (with RAG):

System Query: "Find images for 'family dinner' and 'warm' tone." RAG Result: Returns 3 specific Drive links with descriptions. AI Output: "Hero Image: Use summer_campaign_01.jpg (Link: ...) - Features family eating dinner at sunset, perfectly matching the 'Connection' theme."

5. Failure Modes & Safety
Privacy/PII: Images might contain sensitive data (faces of non-talent).

Mitigation: Add a flag to the Gemini prompt: "If this image contains PII or documents, flag as 'sensitive' and do not index detailed description."

Non-Marketing Images: Accidental uploads of screenshots or memes.

Mitigation: Gemini filters out low-quality images: "If image is low resolution or a screenshot, tag as 'low_quality' and skip."

6. Definition of Done
[ ] Cloud Function detects new jpg/png files in Drive.

[ ] Gemini successfully generating accurate JSON descriptions of images.

[ ] Vertex AI Search returns correct image links when queried for concepts like "Happy Dog" or "Blue Car".
