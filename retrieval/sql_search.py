import os
import re
import sqlite3
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Load App/.env explicitly
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

# Default to a supported model if not configured (Using Llama 3.3 for reliable structured SQL outputs)
GROQ_MODEL = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
# Navigates up out of 'retrieval' folder, then branches into 'mediassist_data/db/mediassist.db'
db_path = Path(__file__).resolve().parent.parent / "mediassist_data" / "db" / "mediassist.db"

ALLOWED_SQL_ROLES = {"billing_executive", "admin"}

client_sql = Groq()

# Compressed, token-efficient prompt containing healthcare claims and maintenance tickets schema definitions
sql_prompt = """You are an expert SQLite query generator. Generate a single, valid SQLite query based ONLY on the user question and schema.

Rules:
1. Return ONLY the SQL query inside <SQL></SQL> tags. No markdown, no backticks, and no explanation.
2. Use only schema tables and columns. If impossible, return 'I do not know'.
3. For partial/text matching, use standard LIKE with '%' wildcards. Since SQLite LIKE is case-insensitive by default, do not wrap columns in LOWER(). Never use ILIKE.
4. Dates use string matching (e.g., LIKE 'YYYY-MM%').

<schema>
Table: claims(claim_id TEXT PK, patient_id TEXT, patient_name TEXT, department TEXT, claim_type TEXT, diagnosis_code TEXT, insurer TEXT, claimed_amount REAL, approved_amount REAL, status TEXT, submitted_date TEXT, resolved_date TEXT)
Table: maintenance_tickets(ticket_id TEXT PK, equipment_name TEXT, equipment_id TEXT, category TEXT, campus TEXT, issue_type TEXT, fault_code TEXT, raised_by TEXT, raised_date TEXT, resolved_date TEXT, status TEXT, resolution_note TEXT)
</schema>

Examples:
Q: Find pending claims for Blue Cross
A: <SQL>SELECT * FROM claims WHERE insurer LIKE '%blue cross%' AND status = 'pending';</SQL>
Q: Show total claimed amount by department
A: <SQL>SELECT department, SUM(claimed_amount) FROM claims GROUP BY department;</SQL>
Q: Open tickets for AC on North campus
A: <SQL>SELECT * FROM maintenance_tickets WHERE equipment_name LIKE '%ac%' AND campus = 'north' AND status = 'open';</SQL>
"""

# Context interpreter prompt tuned to format healthcare and maintenance datasets cleanly
comprehension_prompt = """
You are a data interpretation assistant. You will be given:
1. A user's QUESTION
2. The SQL query result (a list of claims or maintenance tickets in tabular/dictionary format) called DATA

Your task:
- Understand the user's intent from the question.
- Interpret the SQL result as records of claims or maintenance tickets.
- Reshape and present the data in a clean, human-readable chat response.

Formatting rules:
- Present results as a structured list.
- Clearly separate each individual record (e.g., Record 1:, Record 2:).
- Dynamically display the relevant fields present in the data (such as Patient Name, Insurer, Claimed Amount, Equipment Name, Campus, Status, etc.).
- Ensure monetary values and dates are clearly formatted and readable.

Important rules:
- Do not fabricate, assume, or hallucinate any values.
- Do not explain SQL logic, database inner workings, or mention the word "database" or "query".
- Do not return raw JSON, raw DataFrames, or raw SQL strings.
Keep the response concise, structured, and user-friendly.
"""

def generate_sql_query(question: str) -> str:
    chat_completion = client_sql.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": sql_prompt
            },
            {
                "role": "user",
                "content": question
            },
        ],
        model=os.getenv('GROQ_MODEL_NAME', GROQ_MODEL),
        temperature=0.1,  # Kept minimal to force strict syntax matching
        max_tokens=500,   # Avoid execution code-bloat overhead
    )
    return chat_completion.choices[0].message.content

def run_query(query):
    if query.strip().upper().startswith("SELECT"):
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(query, conn)
            return df
    else:
        raise ValueError("Only SELECT queries are allowed.")

def data_comprehension(question: str, context) -> str:
    try:
        chat_completion = client_sql.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": comprehension_prompt
                },
                {
                    "role": "user",
                    "content": f"QUESTION: {question}\n DATA: {context}"
                },
            ],
            model=os.getenv('GROQ_MODEL_NAME', GROQ_MODEL),
            temperature=0.2,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Sorry, I couldn't format the query results right now ({type(e).__name__})."



def sql_chain(question: str, user_role: str):
    # Enforce Security Guardrail Strategy: check incoming privileges
    normalized_role = str(user_role).strip().lower()
    if normalized_role not in ALLOWED_SQL_ROLES:
        return "Access Denied: SQL RAG is only available to roles with analytical responsibilities."

    try:
        sql_query = generate_sql_query(question)
    except Exception as e:
        return f"Sorry, I couldn't generate SQL for that request ({type(e).__name__})."
    
    print("Generated SQL Query: ", sql_query)
    
    # Extract SQL from <SQL>...</SQL> if present
    pattern = r"<SQL>\s*(.*?)\s*</SQL>"
    matches = re.findall(pattern, sql_query, re.IGNORECASE | re.DOTALL)
    
    # FIX: Targeted element 0 index out of the match list cleanly
    if matches:
        sql_query = matches[0].strip()
    else:
        sql_query = sql_query.strip()
        
    print("SQL Query extracted from tags: ", sql_query)
    
    # Safety check
    if not sql_query.upper().startswith("SELECT"):
        raise ValueError(f"Only SELECT queries are allowed: {sql_query}")
        
    response = run_query(sql_query)
    
    if response.empty:
        return "No matching records found."
        
    context = response.to_dict(orient='records')
    
    # Send execution context to LLM for final natural phrasing
    data_response = data_comprehension(question, context)
    
    # Local fallback formatter that dynamically parses any structural columns from either table
    if isinstance(data_response, str) and data_response.startswith("Sorry, I couldn't format"):
        lines = []
        for i, row in enumerate(context, start=1):
            lines.append(f"Record {i}:")
            for key, value in row.items():
                # Clean up snake_case key strings into readable title names
                friendly_key = key.replace('_', ' ').title()
                lines.append(f"- {friendly_key}: {value if value is not None else 'N/A'}")
            lines.append("")
        return "\n".join(lines)
        
    return data_response

if __name__ == "__main__":
    test_question = "Show me the 3 most recent claims"
    print(f"Testing App Query Pipeline with question: '{test_question}'\n")
    
    # Test Scenario 1: Unauthorized access check (Should be blocked instantly)
    print("--- 1. Testing with Unauthorized Role ('nurse') ---")
    denied_answer = sql_chain(test_question, user_role="nurse")
    print("Response:", denied_answer)
    
    print("\n" + "="*60 + "\n")
    
    # Test Scenario 2: Authorized access check (Should proceed and fetch records)
    print("--- 2. Testing with Authorized Role ('billing_executive') ---")
    allowed_answer = sql_chain(test_question, user_role="billing_executive")
    print("\nFinal Formatted Answer:\n", allowed_answer)

