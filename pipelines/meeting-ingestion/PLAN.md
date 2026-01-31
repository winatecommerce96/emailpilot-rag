# Pipeline Proposal: Calendar Intelligence Harvester (Refined)

## Goal
Automate the extraction of **high-signal** strategic client intelligence from Google Calendar meetings. This pipeline will scan authorized user calendars, identify client meetings, and strictly filter for **Product, Inventory, Marketing Themes, and Promotion/Calendar** data. Generic check-ins without these specific signals will be discarded to prevent "Context Clutter."

## Architecture

### 1. "Easy" Auth Flow
- **User Action**: Simple "Connect Calendar" button in the RAG UI.
- **Mechanism**: OAuth 2.0 flow granting `calendar.events.readonly` and `drive.readonly` (for recording transcripts).
- **Control**: Users must explicitly opt-in; tokens are stored securely to allow background processing.

### 2. The "Watcher" (Scanner)
- **Schedule**: Hourly background job.
- **Logic**:
  - Scan past meetings (last 24h).
  - **Client Match**: Identify meetings with external attendees matching Client Domains (e.g., `@roguecreamery.com`).
  - **Artifact Check**: Ensure a transcript or recording exists.

### 3. The "Intelligence" & "The Gatekeeper" (Gemini 1.5 Pro)
This is the core filtering layer requested.
- **Input**: Raw meeting transcript.
- **Prompt Strategy**:
  1.  **Analyze**: Scan the conversation for specific **Signal Topics**:
      - `Product`: New launches, specs, feature changes.
      - `Inventory`: Stockouts, shortages, supply chain issues.
      - `Marketing Themes`: Campaign concepts, brand voice shifts, creative direction.
      - `Calendar/Promos`: Dates, holidays, sales events, deadlines.
  2.  **Evaluate**: If the meeting is purely administrative (scheduling, small talk, general project management status) with no new Signal Topics, return `is_relevant: false`.
  3.  **Extract**: If `is_relevant: true`, extract the structured insights.
- **Outcome**: 
  - **Low Signal**: Discard data. Log as "Skipped (No relevant context)".
  - **High Signal**: Pass structured JSON to Ingestion.

### 4. Vertex Ingestion (High Signal Only)
- **Action**: Index the structured JSON into Vertex AI Search.
- **Metadata**: `client_id`, `meeting_date`, `topics_detected` (e.g., ["inventory", "promotion"]).

## Implementation Steps
1.  **Scaffold**: Initialize `pipelines/meeting-ingestion/` structure.
2.  **Auth Service**: Implement `CalendarAuthService` (OAuth flow).
3.  **Pipeline Core**:
    - `CalendarScanner`: Finds candidate meetings.
    - `SmartProcessor`: The Gemini wrapper that enforces the "Signal vs. Noise" filter.
4.  **API**: Endpoints for UI connection and sync status.
5.  **UI**: "Connect Calendar" component in the Intelligence Hub.

## Approval Request
Do you approve this refined plan with the "Signal vs. Noise" filtering layer? (Yes/No)
