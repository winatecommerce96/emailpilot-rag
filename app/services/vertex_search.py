from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import AlreadyExists
from google.protobuf import struct_pb2
from app.models.schemas import RAGSearchRequest, RAGResult
from typing import List, Dict, Any, Optional
import os
import hashlib

class VertexContextEngine:
    def __init__(
        self, 
        project_id: Optional[str] = None, 
        location: Optional[str] = None, 
        data_store_id: Optional[str] = None
    ):
        # CRITICAL FIX: Explicitly set defaults to prevent "project None" errors
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID") or "emailpilot-438321"
        self.location = location or os.getenv("GCP_LOCATION", "us") 
        self.data_store_id = data_store_id or os.getenv("VERTEX_DATA_STORE_ID") or "emailpilot-rag_1765205761919"
        
        print(f"[VertexContextEngine] Initialized with Project: {self.project_id}, Location: {self.location}, DataStore: {self.data_store_id}", flush=True)
        
        # CRITICAL FIX: Point explicitly to the US API Endpoint.
        # This resolves the "Incorrect API endpoint used" error.
        self.client_options = ClientOptions(
            api_endpoint="us-discoveryengine.googleapis.com"
        )
        
        # Initialize the search client with the specific US options
        self.client = discoveryengine.SearchServiceClient(
            client_options=self.client_options
        )

        # Initialize the document service client for listing documents
        self.doc_client = discoveryengine.DocumentServiceClient(
            client_options=self.client_options
        )

        # Parent path for document operations
        self.branch_path = f"projects/{self.project_id}/locations/{self.location}/dataStores/{self.data_store_id}/branches/default_branch"

        # Construct the full resource path
        self.serving_config = self.client.serving_config_path(
            project=self.project_id,
            location=self.location,
            data_store=self.data_store_id,
            serving_config="default_search",
        )

        # Map Phases to Data Categories (with "general" fallback)
        # Includes both standard categories AND actual production categories
        # (e.g., marketing_strategy, brand_guidelines found in wheelchair-getaways)
        self.PHASE_MAPPING = {
            "STRATEGY": [
                "brand_voice", "past_campaign", "general",
                "marketing_strategy",  # Contains brand voice, pillars, themes
                "brand_guidelines",    # Contains brand guidelines
                "content_pillars",
                "seasonal_themes",
            ],
            "BRIEF": [
                "product_spec", "brand_voice", "general",
                "product", "products", "product_catalog",  # Standard product categories
                "marketing_strategy",  # May contain relevant context
            ],
            "VISUAL": [
                "visual_asset", "general",
                "brand_guidelines",    # Contains visual guidelines
                "design_guidelines",
            ],
            "GENERAL": []  # No filter - search everything
        }

    def _normalize_tags(self, raw_tags: Any) -> List[str]:
        if not raw_tags:
            return []
        if isinstance(raw_tags, struct_pb2.ListValue):
            raw_tags = list(raw_tags)
        if isinstance(raw_tags, (list, tuple)):
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        elif isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            return []
        seen = set()
        deduped = []
        for tag in tags:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(tag)
        return deduped

    def search(self, request: RAGSearchRequest):
        """
        Execute a search against Vertex AI with strict Client ID isolation.
        """
        # 1. Determine which categories to search based on the Phase
        target_categories = self.PHASE_MAPPING.get(request.phase.value, [])
        
        # 2. Build the Filter String
        # Always enforce Client ID
        filter_str = f'client_id: ANY("{request.client_id}")'
        
        # Append Category filters if needed
        if target_categories:
            cat_list = ", ".join([f'"{c}"' for c in target_categories])
            filter_str += f' AND category: ANY({cat_list})'

        # 3. Build the Search Request
        req = discoveryengine.SearchRequest(
            serving_config=self.serving_config,
            query=request.query,
            page_size=request.k,
            filter=filter_str,
            # Enable Auto-Complete / Spell Check logic
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
            spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.AUTO
            ),
            # Enable extractive answers and snippets for better content retrieval
            content_search_spec=discoveryengine.SearchRequest.ContentSearchSpec(
                extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
                    max_extractive_answer_count=3,
                    max_extractive_segment_count=5,
                ),
                snippet_spec=discoveryengine.SearchRequest.ContentSearchSpec.SnippetSpec(
                    return_snippet=True,
                ),
            ),
        )

        # 4. Execute (Synchronously)
        try:
            response = self.client.search(req)
        except Exception as e:
            print(f"Vertex Search Error: {e}")
            return []

        # 5. Parse and Return Results
        results = []
        for result in response.results:
            data = result.document.struct_data

            # Extract content safely
            content_text = (
                data.get("text_chunk") or
                data.get("content") or
                ""
            )

            # Append extractive answers if available
            extractive_parts = []
            if hasattr(result.document, 'derived_struct_data') and result.document.derived_struct_data:
                derived = dict(result.document.derived_struct_data)
                for answer in derived.get("extractive_answers", []):
                    if isinstance(answer, dict) and answer.get("content"):
                        extractive_parts.append(answer["content"])

            if extractive_parts:
                content_text += "\n\n--- Extractive Answers ---\n" + "\n".join(extractive_parts)

            res = RAGResult(
                content=content_text,
                metadata={
                    "client_id": data.get("client_id"),
                    "category": data.get("category"),
                    "source": data.get("source"),
                    "title": data.get("title")
                },
                relevance_score=result.document.struct_data.get("relevance_score", 0.5) if hasattr(result, 'ranking_score') else 0.5
            )
            results.append(res)

        return results

    def list_documents(self, client_id: str, page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """
        List all documents from Vertex AI data store for a specific client.
        Note: Discovery Engine doesn't support server-side filtering for list operations,
        so we fetch all and filter client-side.
        """
        try:
            request = discoveryengine.ListDocumentsRequest(
                parent=self.branch_path,
                page_size=1000  # Fetch larger batch to filter client-side
            )
            response = self.doc_client.list_documents(request=request)

            # Filter and collect documents for this client
            docs = []
            for doc in response:
                if doc.struct_data:
                    data = dict(doc.struct_data)
                    if data.get("client_id") == client_id:
                        # Extract document ID from full path
                        doc_id = doc.name.split("/")[-1] if doc.name else ""

                        docs.append({
                            "id": doc_id,
                            "client_id": client_id,
                            "title": data.get("title", "Untitled"),
                            "source_type": data.get("category", "general"),
                            "content": data.get("text_chunk", data.get("content", ""))[:500],  # Preview only
                            "size": len(data.get("text_chunk", data.get("content", ""))),
                            "tags": self._normalize_tags(data.get("tags")),
                            "source": "vertex_ai",
                            "metadata": {
                                "source": data.get("source"),
                                "category": data.get("category"),
                            }
                        })

            # Sort by title
            docs.sort(key=lambda x: x.get("title", "").lower())

            # Paginate
            total = len(docs)
            start = (page - 1) * limit
            end = start + limit
            paginated = docs[start:end]

            return {
                "documents": paginated,
                "total": total,
                "page": page,
                "limit": limit
            }

        except Exception as e:
            print(f"Error listing documents from Vertex AI: {e}")
            return {
                "documents": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "error": str(e)
            }

    def get_client_document_count(self, client_id: str) -> int:
        """Get total document count for a client from Vertex AI."""
        try:
            request = discoveryengine.ListDocumentsRequest(
                parent=self.branch_path,
                page_size=1000
            )
            response = self.doc_client.list_documents(request=request)

            count = 0
            for doc in response:
                if doc.struct_data:
                    data = dict(doc.struct_data)
                    if data.get("client_id") == client_id:
                        count += 1
            return count
        except Exception as e:
            print(f"Error counting documents: {e}")
            return 0

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get statistics for a client's documents in Vertex AI."""
        try:
            request = discoveryengine.ListDocumentsRequest(
                parent=self.branch_path,
                page_size=1000
            )
            response = self.doc_client.list_documents(request=request)

            total_chars = 0
            source_types = {}
            doc_count = 0

            for doc in response:
                if doc.struct_data:
                    data = dict(doc.struct_data)
                    if data.get("client_id") == client_id:
                        doc_count += 1
                        content = data.get("text_chunk", data.get("content", ""))
                        total_chars += len(content)

                        st = data.get("category", "general")
                        source_types[st] = source_types.get(st, 0) + 1

            return {
                "document_count": doc_count,
                "total_characters": total_chars,
                "source_types": source_types,
                "vector_enabled": True
            }
        except Exception as e:
            print(f"Error getting client stats: {e}")
            return {
                "document_count": 0,
                "total_characters": 0,
                "source_types": {},
                "vector_enabled": True,
                "error": str(e)
            }

    def create_document(
        self,
        client_id: str,
        content: str,
        title: Optional[str] = None,
        category: str = "general",
        source: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a new document in Vertex AI data store.
        Follows the schema: id, client_id, title, category, text_chunk, source
        """
        # Generate unique document ID
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        doc_id = f"{client_id}-{content_hash}"

        # Format title following existing pattern
        display_title = title or f"{client_id} - {category}"

        normalized_tags = self._normalize_tags(tags)

        # Build document struct data
        struct_data = struct_pb2.Struct()
        struct_data.update({
            "id": doc_id,
            "client_id": client_id,
            "title": display_title,
            "category": category,
            "text_chunk": content,
            "source": source or f"upload_{doc_id}.txt",
            "tags": normalized_tags
        })

        # Create the document
        document = discoveryengine.Document(
            id=doc_id,
            struct_data=struct_data
        )

        try:
            request = discoveryengine.CreateDocumentRequest(
                parent=self.branch_path,
                document=document,
                document_id=doc_id
            )
            self.doc_client.create_document(request=request)
        except AlreadyExists:
            # Document with same content hash exists — update it instead
            document.name = f"{self.branch_path}/documents/{doc_id}"
            update_request = discoveryengine.UpdateDocumentRequest(
                document=document,
                allow_missing=True
            )
            self.doc_client.update_document(request=update_request)
        except Exception as e:
            print(f"Error creating document in Vertex AI: {e}")
            return {
                "success": False,
                "error": str(e)
            }

        return {
            "success": True,
            "document_id": doc_id,
            "title": display_title,
            "client_id": client_id,
            "category": category,
            "tags": normalized_tags,
            "size": len(content)
        }

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        """Get a single document from Vertex AI data store with full content."""
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"
            print(f"[get_document] Looking up document: {doc_name}", flush=True)
            request = discoveryengine.GetDocumentRequest(name=doc_name)
            doc = self.doc_client.get_document(request=request)
            print(f"[get_document] Found document, struct_data: {bool(doc.struct_data)}", flush=True)

            if doc.struct_data:
                data = dict(doc.struct_data)
                return {
                    "success": True,
                    "document": {
                        "id": doc_id,
                        "client_id": data.get("client_id"),
                        "title": data.get("title", "Untitled"),
                        "source_type": data.get("category", "general"),
                        "content": data.get("text_chunk", data.get("content", "")),
                        "size": len(data.get("text_chunk", data.get("content", ""))),
                        "tags": self._normalize_tags(data.get("tags")),
                        "source": data.get("source"),
                        "metadata": {
                            "source": data.get("source"),
                            "category": data.get("category"),
                        }
                    }
                }
            else:
                return {"success": False, "error": "Document has no structured data"}

        except Exception as e:
            print(f"[get_document] Error getting document from Vertex AI: {e}", flush=True)
            return {"success": False, "error": str(e)}

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """Delete a document from Vertex AI data store."""
        try:
            doc_name = f"{self.branch_path}/documents/{doc_id}"
            request = discoveryengine.DeleteDocumentRequest(name=doc_name)
            self.doc_client.delete_document(request=request)
            return {"success": True, "document_id": doc_id}
        except Exception as e:
            print(f"Error deleting document from Vertex AI: {e}")
            return {"success": False, "error": str(e)}

    def import_documents(
        self,
        client_id: str,
        chunks: List[str],
        title: str,
        category: str = "general",
        source: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Import multiple document chunks to Vertex AI data store.
        Each chunk becomes a separate searchable document.
        """
        document_ids = []
        errors = []

        normalized_tags = self._normalize_tags(tags)

        for i, chunk in enumerate(chunks):
            # Generate unique document ID for each chunk
            content_hash = hashlib.md5(chunk.encode()).hexdigest()[:8]
            doc_id = f"{client_id}-{content_hash}"

            # Title includes chunk number for multi-chunk documents
            chunk_title = f"{title} (Part {i + 1}/{len(chunks)})" if len(chunks) > 1 else title

            # Build document struct data
            struct_data = struct_pb2.Struct()
            struct_data.update({
                "id": doc_id,
                "client_id": client_id,
                "title": chunk_title,
                "category": category,
                "text_chunk": chunk,
                "source": source or f"upload_{doc_id}.txt",
                "tags": normalized_tags
            })

            # Create the document
            document = discoveryengine.Document(
                id=doc_id,
                struct_data=struct_data
            )

            try:
                request = discoveryengine.CreateDocumentRequest(
                    parent=self.branch_path,
                    document=document,
                    document_id=doc_id
                )
                self.doc_client.create_document(request=request)
            except AlreadyExists:
                # Document with same content hash exists — update it instead
                document.name = f"{self.branch_path}/documents/{doc_id}"
                update_request = discoveryengine.UpdateDocumentRequest(
                    document=document,
                    allow_missing=True
                )
                self.doc_client.update_document(request=update_request)
            except Exception as e:
                errors.append(f"Chunk {i + 1}: {str(e)}")
                print(f"Error creating document chunk {i + 1}: {e}")
                continue

            document_ids.append(doc_id)

        if document_ids:
            return {
                "success": True,
                "documents_created": len(document_ids),
                "document_ids": document_ids,
                "errors": errors if errors else None,
                "tags": normalized_tags
            }
        else:
            return {
                "success": False,
                "error": "; ".join(errors) if errors else "No documents created"
            }

# Factory function required by main.py
def get_vertex_engine():
    return VertexContextEngine()
