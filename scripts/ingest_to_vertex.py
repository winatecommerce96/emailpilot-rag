import json
import sys
import os
import pathlib
import time

# Add the parent directory to sys.path to allow importing from app
current_dir = pathlib.Path(__file__).parent.resolve()
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from dotenv import load_dotenv

# Load/reload env vars from the parent directory (one level up from scripts, or same dir as app)
# The script is in /spokes/RAG/scripts/, .env is in /spokes/RAG/.env
load_dotenv(current_dir.parent / ".env")

from app.services.vertex_search import VertexContextEngine

INPUT_FILE = current_dir / "vertex_import_flat.jsonl"

def ingest():
    project_id = os.getenv("GCP_PROJECT_ID")
    location = os.getenv("GCP_LOCATION", "us")
    data_store_id = os.getenv("VERTEX_DATA_STORE_ID")
    
    print(f"Loaded config: Project={project_id}, Location={location}, DataStore={data_store_id}")
    
    print(f"Initializing Vertex Engine...")
    engine = VertexContextEngine(
        project_id=project_id,
        location=location,
        data_store_id=data_store_id
    )
    
    if not INPUT_FILE.exists():
        print(f"Error: Input file {INPUT_FILE} not found.")
        return

    print(f"Reading from {INPUT_FILE}...")
    
    success_count = 0
    error_count = 0
    
    with open(INPUT_FILE, "r") as f:
        lines = f.readlines()
        
    total = len(lines)
    print(f"Found {total} records to ingest.")
    
    for i, line in enumerate(lines):
        if not line.strip():
            continue
            
        try:
            record = json.loads(line)
            
            # Map JSONL fields to create_document args
            client_id = record.get("client_id")
            content = record.get("text_chunk")
            title = record.get("title")
            category = record.get("category", "general")
            source = record.get("source")
            doc_id_override = record.get("id") # The script generates IDs, but we can rely on content hash if needed, 
                                             # OR we could modify create_document to accept an ID. 
                                             # checking vertex_search.py: create_document generates its own ID based on content hash.
                                             # Let's rely on that for now to avoid modifying the service code, 
                                             # unless we really need the exact ID from the jsonl.
            
            if not client_id or not content:
                print(f"Skipping record {i}: Missing client_id or content")
                continue

            print(f"[{i+1}/{total}] Ingesting: {title} ({client_id})...")
            
            # Note: create_document writes to: projects/.../branches/default_branch/documents/
            result = engine.create_document(
                client_id=client_id,
                content=content,
                title=title,
                category=category,
                source=source
            )
            
            if result.get("success"):
                success_count += 1
            else:
                print(f"Failed to ingest record {i}: {result.get('error')}")
                error_count += 1
                
            # Rate limiting to be safe
            time.sleep(0.1)

        except json.JSONDecodeError:
            print(f"Skipping line {i}: Invalid JSON")
            error_count += 1
        except Exception as e:
            print(f"Error processing line {i}: {e}")
            error_count += 1

    print(f"\nIngestion Complete.")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    ingest()
