import json
import pathlib
import hashlib

# CONFIGURATION
SOURCE_PATH = pathlib.Path("/Users/Damon/klaviyo/klaviyo-audit-automation/emailpilot-orchestrator/rag/processed")
OUTPUT_FILE = "scripts/vertex_import_flat.jsonl"

def migrate():
    records = []
    print(f"Scanning {SOURCE_PATH}...")
    
    if not SOURCE_PATH.exists():
        print(f"ERROR: The folder {SOURCE_PATH} does not exist!")
        return

    for file_path in SOURCE_PATH.glob("**/*.json"):
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
                
            client_id = data.get("client_id", "unknown")
            if client_id == "unknown":
                client_id = file_path.parent.name
            source = data.get("source", file_path.name)
            
            chunks = data.get("chunks", [])
            
            for i, chunk in enumerate(chunks):
                if isinstance(chunk, str):
                    content = chunk
                    chunk_id = hashlib.md5(content.encode()).hexdigest()[:8]
                    old_cat = "general"
                elif isinstance(chunk, dict):
                    content = chunk.get("content", "")
                    chunk_id = chunk.get("chunk_id", f"chunk-{i}")
                    old_cat = chunk.get("metadata", {}).get("category", "general")
                else:
                    continue

                if old_cat == "brand_guidelines": new_cat = "brand_voice"
                elif old_cat == "product_catalog": new_cat = "product_spec"
                elif old_cat == "marketing_strategy": new_cat = "past_campaign"
                elif old_cat == "visual_style": new_cat = "visual_asset"
                else: new_cat = "general"

                # FLAT STRUCTURE (No structData wrapper)
                # Using 'text_chunk' to avoid reserved word conflicts
                record = {
                    "id": f"{client_id}-{chunk_id}",
                    "text_chunk": content,
                    "client_id": client_id,
                    "category": new_cat,
                    "source": source,
                    "title": f"{client_id} - {new_cat}"
                }
                
                if content.strip():
                    records.append(record)
                
        except Exception as e:
            print(f"Skipping file {file_path}: {e}")

    with open(OUTPUT_FILE, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
            
    print(f"Success! Generated {len(records)} records at {OUTPUT_FILE}")

if __name__ == "__main__":
    migrate()
