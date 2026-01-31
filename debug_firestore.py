
import os
from google.cloud import firestore

# Hardcode project ID to be sure
PROJECT_ID = "emailpilot-438321"

def check_collections():
    print(f"Checking Firestore collections in project: {PROJECT_ID}")
    try:
        db = firestore.Client(project=PROJECT_ID)
        collections = db.collections()
        found_any = False
        for coll in collections:
            if not coll.id.startswith("image"):
                continue
            
            # Count first few docs
            docs = list(coll.limit(5).stream())
            doc_count = len(docs)
            print(f"Found collection: {coll.id} (Has data: {doc_count > 0})")
            
            if doc_count > 0:
                print(f"  Sample Client IDs:")
                for doc in docs:
                    data = doc.to_dict()
                    c_id = data.get("client_id", "UNKNOWN")
                    print(f"    - {c_id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_collections()
