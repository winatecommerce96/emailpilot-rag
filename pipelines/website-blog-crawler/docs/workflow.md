Website & Blog Crawler Pipeline**

```markdown
# Technical Blueprint: Website & Blog Crawler Pipeline
**Role:** Brand Terminology & Consistency (Hygiene)
**Target System:** V3 Stage 4 (Creative) & Stage 2 (Strategy)
**Priority:** Low/Medium (Phase 3/4)

---

## 1. Executive Summary
This pipeline ensures the RAG system stays synchronized with the client's public web presence. It scrapes sitemaps to ingest new blog posts, product pages, and FAQs, ensuring the AI uses the most up-to-date terminology and claims.

## 2. Architecture Overview


**Trigger:** Weekly Schedule (Sunday 00:00 UTC).
**Infrastructure:** Google Cloud Function + Firestore (State Management).
**AI Model:** Gemini 1.5 Pro (Optimized for massive text summarization).

---

## 3. Implementation Steps

### Component A: The "Smart Crawler"
**Responsibility:** Efficiently find *new* content without re-scraping the whole site.

**Logic:**
1. Fetch `domain.com/sitemap.xml`.
2. Parse `<lastmod>` tags.
3. Compare against `Firestore: { url: last_crawled_date }`.
4. **Target:** Only URLs where `lastmod > last_crawled_date`.
5. **Fetch:** Use `requests` + `BeautifulSoup` to strip HTML tags, scripts, and navbars.

### Component B: The "Processor" (AI Intermediary)
**Responsibility:** Structure the unstructured web text.

**System Prompt:**
> **Role:** Brand Archivist.
> **Task:** Analyze this webpage text.
> 1. **Identify Type:** Blog, Product Page, Policy, or FAQ.
> 2. **Extract Terminology:** Unique brand names (e.g., "Hydro-Mesh Technology").
> 3. **Extract Claims:** "Lifetime Warranty", "Sustainably Sourced".
> **Output:** JSON summary of the page content.

### Component C: The "Ingester" (Vertex AI)
**Responsibility:** Upsert fresh content.

**Strategy: Overwrite (Per URL)**
* **Strategy:** **Overwrite**. If a URL is updated, the old version is obsolete.
* **Doc ID:** `doc_id = hash(url)`.

**Metadata Schema:**
```json
{
  "doc_type": "brand_context",
  "source": "website",
  "page_type": "blog",      // Allows Stage 2 query: "Summarize recent blog topics"
  "url": "[acme.com/blog/2025-trends](https://acme.com/blog/2025-trends)"
}
4. Failure Modes & Safety
Bot Blocking: WAFs (Cloudflare) might block the scraper.

Mitigation: Use a headless browser service (like Puppeteer) if simple requests fails, or ask Client to allowlist the scraper IP.

Infinite Loops: Spider traps in calendars/filters.

Mitigation: Strictly adhere to sitemap.xml entries only; do not follow internal <a> tags recursively.

5. Definition of Done
[ ] Crawler successfully parsing XML sitemaps.

[ ] Firestore state correctly skipping unchanged URLs.

[ ] Gemini extracting "Brand Terminology" lists.

[ ] V3 Workflow successfully answering "What are the latest product claims?" via RAG.