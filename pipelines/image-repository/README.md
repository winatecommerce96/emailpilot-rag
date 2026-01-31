# Image Repository Pipeline

A visual RAG (Retrieval-Augmented Generation) system that syncs images from Google Drive, captions them using Gemini Vision AI, and indexes them in Vertex AI Search for semantic retrieval.

## Quick Links

| Environment | URL |
|-------------|-----|
| **Production** | https://rag-image-repository-p3cxgvcsla-uc.a.run.app |
| **Local** | http://localhost:8003 |
| **UI** | `/ui/image-repository.html` |
| **API Docs** | `/docs` (FastAPI Swagger) |

---

## API Reference

### Search Images by Keywords

Retrieve image links and metadata using semantic search.

```bash
# Production
curl "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/search/{client_id}?q={keywords}&limit=10"

# Local
curl "http://localhost:8003/api/images/search/{client_id}?q={keywords}&limit=10"
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `client_id` | path | Yes | Client identifier (e.g., `buca-di-beppo`, `christopher-bean-coffee`) |
| `q` | query | Yes | Search keywords (e.g., `pasta warm family`, `coffee product shot`) |
| `limit` | query | No | Max results (default: 20, max: 50) |

**Example Request:**
```bash
curl "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/search/buca-di-beppo?q=pasta%20italian%20food&limit=5"
```

**Example Response:**
```json
{
  "client_id": "buca-di-beppo",
  "query": "pasta italian food",
  "total": 5,
  "images": [
    {
      "doc_id": "img_buca-di-beppo_1UGm9MZawB4uCAV8uGlee8FgIoJbH68iN",
      "title": "BUCA-005-Stills.00_00_16_01.Still005.jpg",
      "description": "A delicious plate of pasta with garlic bread...",
      "mood": "warm",
      "setting": "indoor",
      "visual_tags": ["pasta", "food", "italian", "garlic bread", "meal"],
      "dominant_colors": ["red", "yellow", "white"],
      "drive_link": "https://drive.google.com/file/d/1UGm9MZawB4uCAV8uGlee8FgIoJbH68iN/view",
      "thumbnail_link": "https://drive.google.com/thumbnail?id=1UGm9MZawB4uCAV8uGlee8FgIoJbH68iN&sz=w200",
      "marketing_use_case": "lifestyle",
      "text_chunk": "Caption: A delicious plate of pasta... Mood: warm. Tags: pasta, food..."
    }
  ]
}
```

---

### All API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/images/search/{client_id}` | GET | Search images by keywords |
| `/api/images/sync/{client_id}` | POST | Trigger image sync for client |
| `/api/images/status/{client_id}` | GET | Get sync status and statistics |
| `/api/images/recent/{client_id}` | GET | Get recently indexed images |
| `/api/images/log/{client_id}` | GET | Get processing log (indexed/skipped) |
| `/api/images/folders/{client_id}` | GET | Get configured Drive folders |
| `/api/images/folders/{client_id}` | PUT | Update folder configuration |
| `/api/images/clients` | GET | List all configured clients |
| `/api/images/clear/{client_id}` | DELETE | Clear sync state (force full resync) |
| `/api/images/health` | GET | Health check with config status |

---

## Integration Examples

### Python

```python
import requests

BASE_URL = "https://rag-image-repository-p3cxgvcsla-uc.a.run.app"

def search_images(client_id: str, keywords: str, limit: int = 10):
    """Search for images by keywords and return Drive links."""
    response = requests.get(
        f"{BASE_URL}/api/images/search/{client_id}",
        params={"q": keywords, "limit": limit}
    )
    response.raise_for_status()
    return response.json()

def get_image_links(client_id: str, keywords: str):
    """Get just the Drive links for matching images."""
    results = search_images(client_id, keywords)
    return [img["drive_link"] for img in results.get("images", [])]

# Example usage
links = get_image_links("buca-di-beppo", "warm family dinner")
for link in links:
    print(link)
```

### JavaScript/Node.js

```javascript
const BASE_URL = "https://rag-image-repository-p3cxgvcsla-uc.a.run.app";

async function searchImages(clientId, keywords, limit = 10) {
  const params = new URLSearchParams({ q: keywords, limit });
  const response = await fetch(
    `${BASE_URL}/api/images/search/${clientId}?${params}`
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function getImageLinks(clientId, keywords) {
  const results = await searchImages(clientId, keywords);
  return results.images.map(img => ({
    link: img.drive_link,
    thumbnail: img.thumbnail_link,
    mood: img.mood,
    tags: img.visual_tags
  }));
}

// Example usage
const images = await getImageLinks("christopher-bean-coffee", "coffee product");
console.log(images);
```

### cURL One-Liners

```bash
# Search and extract just Drive links
curl -s "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/search/buca-di-beppo?q=pasta&limit=5" | jq -r '.images[].drive_link'

# Search and get thumbnails
curl -s "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/search/buca-di-beppo?q=warm%20family&limit=10" | jq '.images[] | {title, mood, thumbnail: .thumbnail_link}'

# Get all images with specific mood
curl -s "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/search/christopher-bean-coffee?q=professional%20product&limit=20" | jq '.images[] | select(.mood == "professional")'
```

---

## Search Tips

### Semantic Search Capabilities

The search uses Vertex AI's semantic understanding, so you can search by:

| Search Type | Example Query | What It Finds |
|-------------|---------------|---------------|
| **Mood** | `warm cozy` | Images with warm, inviting atmosphere |
| **Setting** | `outdoor lifestyle` | Outdoor photography, lifestyle shots |
| **Subject** | `coffee beans product` | Product photography of coffee |
| **Color** | `red vibrant` | Images with dominant red colors |
| **Style** | `professional clean` | Clean, professional compositions |
| **Use Case** | `social media hero` | Images suitable for hero banners |

### Combining Keywords

```bash
# Mood + Subject
curl ".../search/buca-di-beppo?q=warm+italian+family+dinner"

# Setting + Style
curl ".../search/christopher-bean-coffee?q=professional+product+shot+white+background"

# Marketing context
curl ".../search/buca-di-beppo?q=social+media+lifestyle+friends"
```

---

## Local Development

### Prerequisites

- Python 3.11+
- Google Cloud SDK (`gcloud`)
- Access to GCP project `emailpilot-438321`

### Setup

```bash
# Clone the repository
git clone https://github.com/winatecommerce96/rag-image-repository.git
cd rag-image-repository

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GCP_PROJECT_ID="emailpilot-438321"
export GCP_LOCATION="us"
export VERTEX_DATA_STORE_ID="emailpilot-rag_1765205761919"
export GEMINI_API_KEY="your-gemini-api-key"  # Or use Secret Manager

# Run locally
uvicorn app.main:app --port 8003 --reload
```

### Docker

```bash
# Build
docker build -t rag-image-repository .

# Run
docker run -p 8003:8080 \
  -e GCP_PROJECT_ID=emailpilot-438321 \
  -e GCP_LOCATION=us \
  -e VERTEX_DATA_STORE_ID=emailpilot-rag_1765205761919 \
  -v ~/.config/gcloud:/root/.config/gcloud \
  rag-image-repository
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Image Repository Pipeline                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │ Google Drive │───>│ Gemini Vision│───>│  Vertex AI   │              │
│  │   (Source)   │    │ (Captioning) │    │   (Index)    │              │
│  └──────────────┘    └──────────────┘    └──────────────┘              │
│         │                   │                   │                       │
│         │                   │                   │                       │
│         ▼                   ▼                   ▼                       │
│  ┌──────────────────────────────────────────────────────┐              │
│  │                    Firestore                         │              │
│  │         (Sync State & Processing Logs)               │              │
│  └──────────────────────────────────────────────────────┘              │
│                                                                         │
│  Data Flow:                                                            │
│  1. Sync triggered (manual or scheduled)                               │
│  2. Drive client discovers images in configured folders                │
│  3. Images downloaded to memory (NOT stored)                           │
│  4. Gemini Vision generates structured captions                        │
│  5. Metadata indexed in Vertex AI Search                               │
│  6. State tracked in Firestore for incremental sync                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### What Gets Indexed

For each image, the system extracts and indexes:

| Field | Description | Example |
|-------|-------------|---------|
| `description` | 2-3 sentence AI description | "A family enjoying pasta at a restaurant..." |
| `mood` | Emotional tone | `warm`, `professional`, `bold`, `playful` |
| `setting` | Environment type | `indoor`, `outdoor`, `product-shot`, `lifestyle` |
| `visual_tags` | Subject keywords | `["pasta", "family", "dinner", "restaurant"]` |
| `dominant_colors` | Main colors | `["red", "brown", "white"]` |
| `marketing_use_case` | Suggested usage | `lifestyle`, `product`, `hero`, `social` |
| `quality_flag` | Image quality | `high`, `medium`, `low`, `screenshot` |

---

## Configuration

### Client Folder Mappings

Edit `config/folder_mappings.yaml` to add client Drive folders:

```yaml
client_folders:
  - client_id: your-client-id
    client_name: Your Client Name
    folders:
      - folder_id: "1ABC123..."  # Google Drive folder ID
        name: "Marketing Assets"
        enabled: true
      - folder_id: "1DEF456..."
        name: "Product Photos"
        enabled: true

sync_settings:
  incremental_sync_enabled: true
  max_file_size_mb: 50
  skip_folders:
    - Archive
    - DO NOT USE
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GCP_PROJECT_ID` | Google Cloud project | `emailpilot-438321` |
| `GCP_LOCATION` | Vertex AI region | `us` |
| `VERTEX_DATA_STORE_ID` | Vertex AI data store | `emailpilot-rag_1765205761919` |
| `GEMINI_API_KEY` | Gemini API key | (from Secret Manager) |
| `GEMINI_MODEL_NAME` | Vision model | `gemini-2.0-flash-lite` |
| `IMAGE_SYNC_SERVICE_ACCOUNT_JSON` | Drive service account | (from Secret Manager) |
| `IMAGE_SYNC_FIRESTORE_COLLECTION` | Firestore collection prefix | `image_sync_state` |

---

## Triggering Syncs

### Via API

```bash
# Sync specific client
curl -X POST "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/sync/buca-di-beppo"

# Force full resync (ignore incremental state)
curl -X POST "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/sync/buca-di-beppo?force_full_sync=true"
```

### Via UI

1. Navigate to `/ui/image-repository.html`
2. Select client from "Configured Clients" section
3. Click "Sync Images" button

### Scheduled (Cloud Scheduler)

The pipeline includes a Cloud Function for scheduled syncs:

```bash
cd cloud_function
./deploy.sh
```

This sets up daily syncs at 6 AM UTC.

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Folder not found" | Service account lacks access | Share Drive folder with service account email |
| "0 images synced" | Incremental sync, no new files | Use `?force_full_sync=true` |
| Thumbnails not loading | Old URL format | Thumbnails use `drive.google.com/thumbnail?id=` format |
| "caption_failed" | Hidden macOS files (`._*`) | These are filtered automatically |

### Checking Logs

```bash
# Cloud Run logs
gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=rag-image-repository" --limit 50

# Processing log via API
curl "https://rag-image-repository-p3cxgvcsla-uc.a.run.app/api/images/log/buca-di-beppo?limit=50"
```

---

## Security Notes

- **Images are NOT stored** - only downloaded to memory for captioning
- Service account credentials stored in Secret Manager
- Thumbnails served directly from Google Drive
- No PII/sensitive images indexed (filtered by Gemini Vision)

---

## Related Resources

- [Vertex AI Search Documentation](https://cloud.google.com/generative-ai-app-builder/docs)
- [Gemini Vision API](https://ai.google.dev/gemini-api/docs/vision)
- [Google Drive API](https://developers.google.com/drive/api/v3/reference)
