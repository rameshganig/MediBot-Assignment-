import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from qdrant_client.models import Filter, FieldCondition, MatchAny
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Fix the Python path so it can see sibling folders like 'ingestion'
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Import ONLY the getters and the path from the embedder layer
from ingestion.embedder import get_dense_embeddings, get_sparse_embeddings, DB_PATH

# Local copy of collection permissions to avoid circular imports with retrieval.rbac.
COLLECTION_PERMISSIONS = {
    "admin": ["general", "clinical", "nursing", "billing", "equipment"],
    "billing_executive": ["general", "billing"],
    "doctor": ["general", "clinical"],
    "nurse": ["general", "nursing"],
    "technician": ["general", "equipment"],
}

load_dotenv()

# Global initialization of the Cross-Encoder model
# This model evaluates the query and document text jointly for maximum accuracy
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
reranker = None


def get_reranker():
    global reranker
    if reranker is None:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder(RERANK_MODEL)
    return reranker

def get_vector_store_client():
    """Connects directly to the existing, persistent vector index on disk."""
    if not Path(DB_PATH).exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}. Run ingestion first.")
        
    return QdrantVectorStore.from_existing_collection(
        embedding=get_dense_embeddings(),
        sparse_embedding=get_sparse_embeddings(),
        path=DB_PATH,
        collection_name="mediassist_hybrid_rag",
        retrieval_mode=RetrievalMode.HYBRID
    )

def execute_secure_hybrid_search(user_query, user_role, top_k=10):
    """
    Executes a single unified hybrid query pass with native RRF rank fusion.
    Fetches a broad initial candidate set (top_k=10) to pass to the reranker.
    """
    role_to_check = user_role.lower().strip()
    accessible_collections = {str(collection).lower().strip() for collection in COLLECTION_PERMISSIONS.get(role_to_check, [])}
    is_admin = role_to_check == "admin"
    
    role_map = {
        "nurse": ["nurse", "nurses", "nurse staff", "all"],
        "doctor": ["doctor", "doctors", "clinical", "all"],
        "admin": ["admin", "`admin`", "all"],
        "billing": ["billing", "billing executives", "`billing_executive`", "all"],
        "technician": ["technician", "technicians", "biomedical technician", "all"]
    }
    
    allowed_variants = [role_to_check]
    for key, variants in role_map.items():
        if key in role_to_check:
            allowed_variants.extend(variants)
    allowed_variants = list(set(allowed_variants))
        
    db = get_vector_store_client()

    # Pull a broader pool first, then apply a deterministic access check locally.
    # This avoids brittle payload-filter shape issues in the existing Qdrant index.
    candidate_pool = db.similarity_search(query=user_query, k=top_k * 3)

    merged_results = []
    seen_chunk_ids = set()
    allowed_set = {str(v).lower().strip() for v in allowed_variants if str(v).strip()}
    allowed_set.update({"all"})
    if role_to_check == "billing_executive":
        allowed_set.update({"billing", "billing_executive"})
    elif role_to_check == "doctor":
        allowed_set.update({"doctor", "clinical"})
    elif role_to_check == "nurse":
        allowed_set.update({"nurse"})
    elif role_to_check == "technician":
        allowed_set.update({"technician", "technicians"})
    elif role_to_check == "admin":
        allowed_set.update({"admin"})

    for chunk in candidate_pool:
        metadata = chunk.metadata or {}
        department = str(metadata.get("department", "")).lower().strip()
        collection_name = str(metadata.get("collection") or department).lower().strip()
        chunk_allowed_roles = metadata.get("allowed_roles", [])
        if isinstance(chunk_allowed_roles, str):
            chunk_allowed_roles = [chunk_allowed_roles]
        chunk_allowed_roles = {str(role).lower().strip() for role in chunk_allowed_roles if str(role).strip()}

        is_general = department == "general"
        is_collection_allowed = is_admin or (not accessible_collections or collection_name in accessible_collections)
        is_role_allowed = is_admin or bool(chunk_allowed_roles.intersection(allowed_set))

        if not (is_general or (is_collection_allowed and is_role_allowed)):
            continue

        chunk_id = metadata.get("chunk_id") or metadata.get("_id") or metadata.get("source")
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        merged_results.append(chunk)

        if len(merged_results) >= top_k:
            break

    return merged_results

def generate_clinical_response(user_query, user_role):
    """
    1. Fetches broad top-10 candidate set from hybrid search.
    2. Reranks text using a local Cross-Encoder model.
    3. Narrows candidates down to top-3 before cloud LLM generation.
    """
    # REQUIREMENT: Fetch a broader candidate set (top-10)
    initial_candidates = execute_secure_hybrid_search(user_query, user_role, top_k=10)
    
    if not initial_candidates:
        return {
            "answer": "Access Denied: You do not possess the required authorization credentials.",
            "sources": []
        }

    print(f"[Reranker] Evaluating {len(initial_candidates)} candidates against the query...")

    # REQUIREMENT: Cross-encoder reads query and chunks together (jointly)
    # Prepare pairs for the model: [(query, doc_1), (query, doc_2), ...]
    pairs = [[user_query, doc.page_content] for doc in initial_candidates]
    scores = get_reranker().predict(pairs)

    # Attach scores to documents and sort them from highest to lowest relevance
    scored_docs = list(zip(initial_candidates, scores))
    scored_docs.sort(key=lambda x: x[1], reverse=True) # FIXED: Explicitly sort by the score index

    # REQUIREMENT: Narrow down to top-3 chunks before passing to the LLM
    reranked_top_chunks = [doc for doc, score in scored_docs[:3]]
    
    # FIXED: Dynamically print the actual count retrieved (e.g., top-2 if only 2 exist)
    actual_top_k = min(3, len(scored_docs))
    print(f"[Reranker] Narrowed down to top-{actual_top_k} highest scoring candidates.")


    # Build the top-chunk context block once so both the LLM and fallback paths can use it.
    context_block = "\n\n".join([
        f"Source: {d.metadata.get('source_document', d.metadata.get('source', 'Unknown Document'))}\n{d.page_content}"
        for d in reranked_top_chunks
    ])

    # Fetch Cloud API Credentials. If the key is absent, return a safe local fallback
    # instead of raising an error that looks like the app is asking for a password.
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        cloud_llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0.0, api_key=api_key)

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert clinical AI assistant at MediAssist. Your job is to answer the user's "
                "question by rephrasing and rewriting the provided reference context text into a clear response.\n\n"
                "Strict Guidelines:\n"
                "- Rely ONLY on the clear facts, metrics, and gauges mentioned in the context.\n"
                "- Do not extrapolate, guess, or introduce external medical knowledge."
            )),
            ("user", "Provided Context:\n\n{context}\n\nQuestion: {query}")
        ])

        chain = prompt | cloud_llm | StrOutputParser()
        answer = chain.invoke({"context": context_block, "query": user_query})
    else:
        # Keep the app functional without a cloud key by returning a concise extractive answer.
        answer = (
            "Cloud answer generation is unavailable because GROQ_API_KEY is not set. "
            "Here is the most relevant context I found:\n\n"
            f"{context_block if context_block else 'No matching context was retrieved.'}"
        )

    sources = [
        {
            "source_document": doc.metadata.get("source_document", doc.metadata.get("source", "Unknown Document")),
            "section_title": " > ".join(doc.metadata.get("heading_hierarchy", [])) or doc.metadata.get("department", "General Document Section"),
            "collection": doc.metadata.get("collection", doc.metadata.get("department", "medical_policies"))
        }
        for doc in reranked_top_chunks
    ]

    return {
        "answer": answer,
        "sources": sources
    }

if __name__ == "__main__":
    print("--- RUNNING FIXED HYBRID RETRIEVAL + CROSS-ENCODER RERANK PASS ---")
    try:
        answer = generate_clinical_response(
            user_query="Who is responsible for approving leave for doctors working within the ICU department?",
            user_role="doctor"
        )
        print("\n=== CLOUD REPHRASED RESPONSE ===")
        print(answer)
    except Exception as e:
        print(f"\n[ERROR] Execution failed: {e}")

