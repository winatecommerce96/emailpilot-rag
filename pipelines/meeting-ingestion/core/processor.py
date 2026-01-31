"""
The "Gatekeeper": AI Processing for "Signal vs. Noise" filtering.
Uses the new google-genai SDK.
"""
import os
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# New google-genai SDK
from google import genai
from google.genai import types


class SmartProcessor:
    """Analyzes meeting transcripts for strategic intelligence signals."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    async def process_transcript(self, transcript_text: str, metadata: Dict) -> Optional[Dict[str, Any]]:
        """
        Analyzes transcript. Returns None if "Noise". Returns structured Dict if "Signal".
        """
        if not self.client:
            print("Gemini API Key not set. Skipping processing.")
            return None

        system_prompt = """You are a Strategic Intelligence Filter for a Marketing Agency.
Analyze the following meeting transcript.

**Your Goal**: Determine if this meeting contains high-value strategic signals regarding:
1. **Product**: New launches, specs, feature changes.
2. **Inventory**: Stockouts, shortages, supply chain.
3. **Marketing Themes**: Campaign concepts, brand voice shifts.
4. **Calendar/Promos**: Specific dates, sales events, deadlines.

**Instructions**:
- If the meeting is purely administrative (scheduling, small talk, status checks) with NO new signals in the above categories, output JSON with `is_relevant: false`.
- If relevant, output `is_relevant: true` and extract the data structured as shown below.

**Input Metadata**:
- Client: {client}
- Date: {date}

**Output Format (JSON only, no markdown)**:
{{
    "is_relevant": boolean,
    "reason": "Brief explanation of why it is relevant or not",
    "extracted_data": {{
        "strategic_directives": ["..."],
        "commercial_signals": ["..."],
        "client_sentiment": "Positive/Neutral/Negative",
        "topics_detected": ["inventory", "promotion", ...]
    }}
}}"""

        prompt = system_prompt.format(
            client=metadata.get('client_id', 'Unknown'),
            date=metadata.get('date', 'Unknown')
        )

        try:
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[prompt, transcript_text],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )

            # Parse JSON response
            text_result = response.text

            # Cleanup for json code blocks (shouldn't be needed with response_mime_type)
            if "```json" in text_result:
                text_result = text_result.split("```json")[1].split("```")[0]
            elif "```" in text_result:
                text_result = text_result.split("```")[1].split("```")[0]

            data = json.loads(text_result.strip())

            if data.get('is_relevant'):
                return data.get('extracted_data')
            else:
                print(f"Meeting filtered: {data.get('reason', 'Low signal')}")
                return None

        except Exception as e:
            print(f"Error in SmartProcessor: {e}")
            return None
