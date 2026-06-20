import os
from pathlib import Path
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from langchain_core.documents import Document
from qdrant_client.models import Filter, FieldCondition, MatchAny

# 1. Define models and dynamic file system paths
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# Use the existing repo-local LangChain hybrid database that already contains
# dense + sparse vectors for the mediassist_hybrid_rag collection.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = str(PROJECT_ROOT / "mediassist_data" / "mediassist_langchain_hybrid_db")

# 2. Lazy-load LangChain embedding engines so the backend can start without
# downloading models during module import.
dense_embeddings = None
sparse_embeddings = None


def get_dense_embeddings():
    global dense_embeddings
    if dense_embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings
        dense_embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
    return dense_embeddings


def get_sparse_embeddings():
    global sparse_embeddings
    if sparse_embeddings is None:
        from langchain_qdrant import FastEmbedSparse
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25", batch_size=32)
    return sparse_embeddings


def initialize_and_vectorize_db(chunks):
    """
    Receives raw chunk maps from loader.py, builds layout-fused 
    context documents, and instantiates the local persistent database index.
    """
    print(f"[Embedder] Initializing dense model: {EMBED_MODEL}")
    print("[Embedder] Initializing sparse model: Qdrant/BM25")

    dense_model = get_dense_embeddings()
    sparse_model = get_sparse_embeddings()
    
    langchain_docs = []
    
    for chunk in chunks:
        # Clean up HTML 'amp;' artifacts from extracted text attributes
        cleaned_roles = [role.replace("amp;", "").strip() for role in chunk["metadata"]["allowed_roles"]]
        cleaned_roles = list(set([r for r in cleaned_roles if r]))
        
        # REQUIREMENT 1: Context Enrichment (Prefixing the parent trace path)
        hierarchy = chunk["metadata"]["heading_hierarchy"]
        context_prefix = f"Context: {' > '.join(hierarchy)}\n\n" if hierarchy else ""
        enriched_text = f"{context_prefix}{chunk['text']}"
        
        # REQUIREMENT 2: Mapping the complete required metadata schema
        metadata_schema = {
            "source": chunk["metadata"]["source"],
            "file_type": chunk["metadata"]["file_type"],
            "chunk_id": chunk["metadata"]["chunk_id"],
            "department": chunk["metadata"]["department"],
            "document_ref": chunk["metadata"]["document_ref"],
            "version": str(chunk["metadata"]["version"]),
            "allowed_roles": cleaned_roles,
            "heading_hierarchy": hierarchy
        }
        
        langchain_docs.append(
            Document(page_content=enriched_text, metadata=metadata_schema)
        )
        
    print(f"[Embedder] Structural preparation complete. Vectorizing {len(langchain_docs)} chunks...")
    
    # 3. Create the Persistent Hybrid Vector Index
    db = QdrantVectorStore.from_documents(
        documents=langchain_docs,
        embedding=dense_model,
        sparse_embedding=sparse_model,
        path=DB_PATH,
        collection_name="mediassist_hybrid_rag",
        retrieval_mode=RetrievalMode.HYBRID
    )
    
    print("[Embedder] Vector storage pipeline completed successfully!")
    return db



