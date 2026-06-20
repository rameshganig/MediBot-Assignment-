# MediBot Assignment

## Overview

MediBot is an enterprise-grade Retrieval-Augmented Generation (RAG) system developed for MediAssist Health Network to provide secure, role-aware access to internal healthcare knowledge.

Healthcare organizations manage large volumes of unstructured documents including treatment protocols, drug formularies, nursing procedures, billing guides, hospital policies, and equipment manuals. Traditional keyword-based search often results in poor retrieval quality, while unrestricted access creates significant security and compliance risks.

MediBot addresses these challenges through:

- Advanced Hybrid Retrieval (Dense + BM25 Search)
- Reranking for improved relevance
- Role-Based Access Control (RBAC) enforced at the retrieval layer
- FastAPI backend services
- Next.js frontend interface
- Source-aware responses with document citations

The system ensures users can access only the information permitted for their role while receiving highly relevant answers grounded in organizational knowledge.

## What This Project Does

- Role-based login for healthcare staff
- Intent-aware routing between SQL analytics and document retrieval
- Role-constrained answers grounded in authorized internal content
- Source-aware responses with document references
- Responsive chat UI with fixed viewport and scrollable conversation history

## Architecture

```mermaid
flowchart TD
    U[Staff User] --> L[Next.js Login / Chat UI]
    L --> A[FastAPI Gateway: api/main_api.py]
    A --> R[RBAC Layer: retrieval/rbac.py]
    A -->|Analytical intent| S[SQL Retrieval: retrieval/sql_search.py]
    A -->|Clinical / document intent| H[Hybrid Retrieval: retrieval/hybrid_search.py]
    S --> DB[(SQLite: mediassist.db)]
    H --> V[(Qdrant Hybrid Vector Store)]
    A --> O[LLM Response Formatting]
    O --> L
```

The request flow is intentionally layered:

1. The UI sends a question to the FastAPI gateway.
2. The gateway applies role and intent checks before any retrieval happens.
3. SQL queries are limited to billing executive and admin.
4. Clinical/document retrieval is filtered by collection permissions and chunk metadata.
5. The final answer is returned to the UI with a consistent chat presentation.

## Role Matrix

| Role | Department | Accessible Collections |
|---|---|---|
| `doctor` | Clinical | Clinical protocols, drug formulary, diagnostic guidelines + General |
| `nurse` | Clinical | Nursing procedures, patient care guidelines + General |
| `billing_executive` | Billing & Insurance | Insurance billing codes, claim procedures, billing FAQs + General |
| `technician` | Medical Equipment | Equipment manuals, calibration guides, maintenance schedules + General |
| `admin` | Executive / IT | All document collections |

## Screenshots

### Login Page

![MediBot login page](MediBot%20login%20page.PNG)

The login screen is intentionally minimal: project branding, username/password fields, and a single action button. It validates credentials against the backend login endpoint and then initializes a role-scoped session.

Sample login credentials (testing/demo):

| Username | Password | Role |
|---|---|---|
| `admin_user` | `password123` | `admin` |
| `doctor_user` | `password123` | `doctor` |
| `nurse_user` | `password123` | `nurse` |
| `billing_user` | `password123` | `billing_executive` |
| `tech_user` | `password123` | `technician` |

### Chat Page

![MediBot chat page](MediBot%20Chatt_page.PNG)

The chat page shows the active user, user type, and role-specific accessible collections. Access permissions are enforced in the backend retrieval layer, so users can only retrieve content allowed for their role.

The exact collection permissions follow the Role Matrix above and are enforced server-side at retrieval time.

### Security Boundary Diagram

![Security boundaries](Security%20boundries.PNG)

This diagram highlights the trust boundaries across the system: user-facing UI, API gateway, retrieval services, and storage layers. It emphasizes that authentication and role context enter through the API boundary, and every downstream component must respect RBAC decisions before any document snippets or SQL results are returned.

### Retrieval Architecture Diagram

![Retrieval architecture](MediBot_arch.png)

This architecture diagram illustrates the hybrid retrieval flow: query understanding, role-aware filtering, vector/keyword retrieval, and final response synthesis. It also shows how structured SQL retrieval and unstructured document retrieval are combined so users receive accurate answers while remaining within their permitted data scope.

## Key Files

- [api/main_api.py](api/main_api.py) - API gateway, login, routing, and RBAC enforcement
- [retrieval/rbac.py](retrieval/rbac.py) - role and collection permissions
- [retrieval/hybrid_search.py](retrieval/hybrid_search.py) - hybrid retrieval and answer generation
- [retrieval/sql_search.py](retrieval/sql_search.py) - SQL generation and result formatting
- [ui/src/app/page.tsx](ui/src/app/page.tsx) - login and chat frontend
- [ui/src/app/globals.css](ui/src/app/globals.css) - full-screen UI layout and scroll styling

## Running the App

## Setup Instructions

### API Keys

Create a `.env` file in the project root with:

```env
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL_NAME=llama-3.3-70b-versatile
```

Notes:

- `GROQ_API_KEY` is required for full LLM response generation.
- If `GROQ_API_KEY` is missing, Hybrid RAG returns fallback extractive context.

### Backend Setup and Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn api.main_api:app --host 127.0.0.1 --port 8002
```

### Frontend Setup and Run

```bash
cd ui
npm install
npm run dev
```

Frontend default URL: `http://127.0.0.1:3000`
Backend default URL: `http://127.0.0.1:8002`

### Demo Credentials (All 5 Roles)

| Username | Password | Role |
|---|---|---|
| `admin_user` | `password123` | `admin` |
| `doctor_user` | `password123` | `doctor` |
| `nurse_user` | `password123` | `nurse` |
| `billing_user` | `password123` | `billing_executive` |
| `tech_user` | `password123` | `technician` |

### Backend

```bash
python -m uvicorn api.main_api:app --host 127.0.0.1 --port 8002
```

### Frontend

```bash
cd ui
npm install
npm run dev
```

### Hybrid RAG Validation

Suggested test prompts:

- [doctor] "In the drug formulary, what is the dosing guidance for amoxicillin in adults?"
- [doctor] "Which section mentions ICD-10 code E11 and its diagnostic category?"
- [technician] "Find calibration steps for equipment model GE Vivid S60."
- [technician] "Where is the maintenance schedule for Philips IntelliVue MX800 documented?"

Expected behavior:

- Retrieval type should be `Hybrid RAG`.
- Answer should include citations with `source_document` and `section_title`.
- Role access must still be enforced (for example, nurse cannot retrieve equipment-only content).

### Reranking Validation

Suggested test prompts:

- [nurse] "Show the post-op infection control steps for ICU patients and include isolation guidance."
- [doctor] "For pneumonia treatment protocol, include dosage timing and contraindications."

Expected behavior:

- Initial retrieval should bring a broader candidate set (for example top-10).
- Logged reranker scores should reorder candidates by relevance to the exact question.
- Final answer should be grounded only in the top reranked chunks (for example top-3), with citations.

### SQL RAG Validation

Suggested test prompts:

- [billing_executive] "How many claims were approved last month?"
- [admin] "Which equipment category has the highest number of open maintenance tickets?"
- [billing_executive] "Show pending claims for Blue Cross insurance."

Expected behavior:

- Retrieval type should be `sql_rag` for analytical questions.
- The executed query must be a clean SQL statement (no markdown fences, no explanatory text).
- Response should return a natural-language summary with a citation to the SQL source context.
- Only `billing_executive` and `admin` should be able to run SQL RAG successfully.

### RBAC Validation

Suggested test prompts:

- [nurse] "Show me insurance billing code references and claim submission rules."
- [billing_executive] "Provide ICU drug protocol for sepsis treatment."
- [technician] "Give me hospital leave policy and calibration checklist for GE Vivid S60."

Expected behavior:

- Restricted collection content must be blocked with a clear role-aware denial message.
- Allowed collection content should still be answered normally with citations.
- No restricted document citation should appear in blocked responses.

RBAC blocking evidence (restricted collection access):

The following screenshots show adversarial attempts to access restricted content (billing, calibration/equipment, and claim-rule data) by roles that are not authorized for those collections. In each case, MediBot correctly blocks the request at the retrieval layer, preventing restricted chunks from reaching the LLM.

#### Doctor blocked from caliberation data

![Doctor access blocked from caliberation data](Doctor%20Access%20blocked%20for%20from%20caliberation.PNG)

#### Nurse blocked from billing collection

![Nurse access blocked for billing collection](Nurse%20Access%20blocked%20for%20billing%20collection.PNG)

#### Technician blocked from claim rules

![Technician access blocked for claim rules](Technician%20Access%20blocked%20for%20claim%20rules.PNG)

### Document Parsing Validation

Suggested test prompts:

- [technician] "In the equipment manual, what are the quarterly, annual, and 18-month maintenance tasks?"
- [billing_executive] "From the claim submission guide, list the exact step-by-step workflow headings."

Expected behavior:

- First ingestion run may take longer due to model download and parser initialization.
- Chunk text should preserve parent heading context so extracted answers remain interpretable.
- Citations should point to relevant section titles rather than generic document-level labels.
