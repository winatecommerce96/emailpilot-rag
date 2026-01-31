"""
Vertex AI Ingestion Logic.
"""
from app.services.vertex_search import get_vertex_engine
from typing import Dict, Any

class MeetingIngester:
    def __init__(self):
        self.engine = get_vertex_engine()

    def ingest_meeting_intel(self, client_id: str, intel_data: Dict[str, Any], metadata: Dict[str, Any]):
        """
        Save the processed intelligence to Vertex AI.
        """
        # Format the content into a readable string for the RAG chunk
        title = f"Meeting Intel: {metadata.get('summary', 'Sync')} ({metadata.get('date')})"
        
        content = f"# Intelligence Brief: {title}\n\n"
        
        if intel_data.get('strategic_directives'):
            content += "## Strategic Directives\n"
            for item in intel_data['strategic_directives']:
                content += f"- {item}\n"
            content += "\n"
            
        if intel_data.get('commercial_signals'):
            content += "## Commercial Signals (Promos/Inventory)\n"
            for item in intel_data['commercial_signals']:
                content += f"- {item}\n"
            content += "\n"
            
        content += f"## Sentiment\n{intel_data.get('client_sentiment', 'Neutral')}\n"
        
        # Tags
        tags = ["meeting-intel"]
        tags.extend(intel_data.get('topics_detected', []))
        
        # Ingest
        result = self.engine.create_document(
            client_id=client_id,
            content=content,
            title=title,
            category="strategy", # or 'general'
            source="meeting_harvester",
            tags=tags
        )
        
        return result
