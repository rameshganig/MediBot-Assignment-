import os
import re
import sys
import uuid
from typing import List, Dict, Any
from pathlib import Path
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# --- STRUCTURAL ENVIRONMENT PATH ALIGNMENT ---
# Injects the project root directory and retrieval folder path into the Python lookup registry
sys.path.append(str(Path(__file__).resolve().parent.parent))

# --- UPDATED CODEBASE IMPORTS ---
# Pull permissions and credential data cleanly from your rbac file
from retrieval.rbac import COLLECTION_PERMISSIONS, USER_DATABASE

# Pull analytical processing tools out of your sql search file
from retrieval.sql_search import sql_chain, ALLOWED_SQL_ROLES

# Pull clinical text search tools out of your hybrid search file
from retrieval.hybrid_search import generate_clinical_response

app = FastAPI(
    title="MediAssist Advanced RAG Backend Gateway",
    version="1.0.0",
    description="Unified API hosting Role-Based Access Controls, Hybrid Vector Queries, and Text-to-SQL Pipelines."
)

# Enable CORS for UI dashboards (Next.js frontend connectivity)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PYDANTIC SCHEMA VALIDATION ENTITIES ---
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    session_token: str
    role: str

class ChatRequest(BaseModel):
    question: str
    role: str

class SourceItem(BaseModel):
    source_document: str
    section_title: str
    collection: str

class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    retrieval_type: str
    role: str


def default_source(retrieval_type: str, role: str, reason: str = "response") -> List[SourceItem]:
    """Builds a safe fallback citation so every response carries at least one source reference."""
    if retrieval_type == "sql_rag":
        return [
            SourceItem(
                source_document="mediassist.db",
                section_title="claims and maintenance_tickets tables",
                collection="billing"
            )
        ]

    section_lookup = {
        "access_denied": "RBAC policy guardrail",
        "admin_only": "Admin-only policy rule",
        "response": "General document section",
    }
    return [
        SourceItem(
            source_document="MediBot policy context",
            section_title=section_lookup.get(reason, "General document section"),
            collection="general" if role != "admin" else "all"
        )
    ]

# --- INTENT ROUTING ENGINE ---
def is_analytical_question(question: str) -> bool:
    """
    Scans intent patterns to determine if a question requires a database query.
    """
    analytical_keywords = {
        "claim", "claims", "ticket", "tickets", "total", "sum", "average", 
        "expensive", "cost", "department", "insurer", "pending", "approved",
        "fault", "code", "codes", "campus", "how many", "most recent", "recent",
        "insurance", "reimbursement", "reimburse", "tariff"
    }
    tokens = set(re.findall(r'\w+', question.lower()))
    return not tokens.isdisjoint(analytical_keywords)


def get_required_collections(question: str) -> List[str]:
    """
    Detects information domains requested by the user question.
    These map to collection-level permissions for hard RBAC enforcement.
    """
    q = question.lower()
    required: List[str] = []

    maintenance_markers = [
        "equipment", "calibration", "caliberation", "maintenance", "radiology", "service engineer", "manual"
    ]
    billing_markers = [
        "billing", "claim", "claims", "insurance", "reimbursement", "tariff", "cpt", "code", "codes"
    ]
    patient_record_markers = [
        "patient record", "patient records", "diagnosis history", "ehr", "medical record"
    ]

    if any(marker in q for marker in maintenance_markers):
        required.append("equipment")
    if any(marker in q for marker in billing_markers):
        required.append("billing")
    if any(marker in q for marker in patient_record_markers):
        required.append("clinical")

    return list(dict.fromkeys(required))


def is_admin_only_question(question: str) -> bool:
    q = question.lower()
    admin_only_markers = [
        "admin-level", "admin level", "permission matrix", "user permission", "permission table", "staff accounts"
    ]
    return any(marker in q for marker in admin_only_markers)

# --- REST API ENDPOINTS ---

@app.post("/login", response_model=LoginResponse, tags=["Authentication"])
def login(payload: LoginRequest):
    """
    Verifies user credentials against rbac.py metadata and provides a session token.
    """
    user = USER_DATABASE.get(payload.username)
    if not user or user["password"] != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password configuration."
        )
    
    token = f"token_{uuid.uuid4().hex[:12]}"
    return LoginResponse(session_token=token, role=user["role"])

@app.post("/chat", response_model=ChatResponse, tags=["RAG Gateway Engine"])
def chat(payload: ChatRequest):
    """
    Core RAG orchestrator. Classifies incoming requests, applies role filtering rules, 
    and runs queries across SQL or document search engines.
    """
    question = payload.question.strip()
    role = payload.role.strip().lower()

    # Hard RBAC checks based on requested information domain.
    role_collections = set(COLLECTION_PERMISSIONS.get(role, []))
    required_collections = get_required_collections(question)

    if is_admin_only_question(question) and role != "admin":
        return ChatResponse(
            answer="Access Denied: This information is restricted to admin role.",
            sources=default_source("hybrid_rag", role, reason="admin_only"),
            retrieval_type="hybrid_rag",
            role=payload.role
        )

    for required_collection in required_collections:
        if required_collection not in role_collections:
            return ChatResponse(
                answer="Access Denied: You do not have permission to access this information domain.",
                sources=default_source("hybrid_rag", role, reason="access_denied"),
                retrieval_type="hybrid_rag",
                role=payload.role
            )
    
    # 1. Routing step: Is this an analytical/numbers question?
    if is_analytical_question(question):
        # 2. SQL RAG Security Rule Validation check
        if role not in ALLOWED_SQL_ROLES:
            return ChatResponse(
                answer="Access Denied: SQL RAG is only available to roles with analytical responsibilities.",
                sources=default_source("sql_rag", role, reason="access_denied"),
                retrieval_type="sql_rag",
                role=payload.role
            )
        
        sql_result = sql_chain(question, user_role=payload.role)
        return ChatResponse(
            answer=sql_result,
            sources=default_source("sql_rag", role),
            retrieval_type="sql_rag",
            role=payload.role
        )
    
    else:
        # 3. Document Search Rule: Run your hybrid text + reranking pipeline
        rag_output = generate_clinical_response(question, payload.role)
        
        if isinstance(rag_output, dict):
            answer_text = rag_output.get("answer", "No document response text generated.")
            raw_sources = rag_output.get("sources", [])
        else:
            answer_text = str(rag_output)
            raw_sources = []

        formatted_sources = [
            SourceItem(
                source_document=s.get("source_document", "Unknown Document"),
                section_title=s.get("section_title", "General Document Section"),
                collection=s.get("collection", "medical_policies")
            ) for s in raw_sources
        ]
        if not formatted_sources:
            formatted_sources = default_source("hybrid_rag", role)
        
        return ChatResponse(
            answer=answer_text,
            sources=formatted_sources,
            retrieval_type="hybrid_rag",
            role=payload.role
        )

@app.get("/collections/{role}", response_model=List[str], tags=["Data Discovery Permissions"])
def get_collections(role: str):
    """
    Lists document directories accessible by the targeted organizational user role.
    """
    normalized_role = role.strip().lower()
    if normalized_role not in COLLECTION_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requested role '{role}' is unrecognized by the data security manager context."
        )
    return COLLECTION_PERMISSIONS[normalized_role]

@app.get("/health", tags=["System Performance Monitoring"])
def health_check():
    """
    Runs availability traces across systemic file dependencies.
    """
    from retrieval.sql_search import db_path
    db_file_status = "healthy" if db_path.exists() else "database_file_missing"
    return {
        "status": "healthy" if db_file_status == "healthy" else "degraded",
        "modules_loaded": ["rbac", "sql_search", "hybrid_search"],
        "database_connectivity": db_file_status,
        "api_layer": "operational"
    }

if __name__ == "__main__":
    import uvicorn
    print("Launching ASGI Application Server via http://127.0.0.1:8000")
    uvicorn.run("main_api:app", host="127.0.0.1", port=8000, reload=True)
