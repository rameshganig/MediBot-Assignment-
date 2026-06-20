import os
import re
from pathlib import Path
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

# Reliable path resolution for Jupyter Notebooks
DATA_DIR = Path(os.getcwd()).parent / "mediassist_data"

def extract_metadata_from_text(first_page_text, folder_name):
    """
    Parses the raw text of the document to build structured metadata.
    """
    default_roles = ["admin"] if folder_name.lower() != "general" else ["admin", "doctor", "nurse", "billing_executive", "technician"]
    metadata = {
        "department": folder_name.lower(),
        "document_ref": "unknown",
        "version": "1.0",
        "allowed_roles": default_roles
    }
    
    # 1. Extract Document Reference
    ref_match = re.search(r"Document ref:\s*([^\s·\n]+)", first_page_text, re.IGNORECASE)
    if ref_match:
        metadata["document_ref"] = ref_match.group(1).strip()
        
    # 2. Extract Version
    ver_match = re.search(r"Version\s*([\d.]+)", first_page_text, re.IGNORECASE)
    if ver_match:
        metadata["version"] = ver_match.group(1).strip()
        
    # 3. Extract Access/Roles
    access_match = re.search(r"Access:\s*([^\n]+)", first_page_text, re.IGNORECASE)
    if access_match:
        raw_roles = access_match.group(1).lower()
        roles_list = re.split(r",|&|\band\b", raw_roles)
        cleaned_roles = [role.strip() for role in roles_list if role.strip()]
        metadata["allowed_roles"] = list(set(cleaned_roles + ["admin"]))
        if folder_name.lower() == "general":
            metadata["allowed_roles"] = ["admin", "doctor", "nurse", "billing_executive", "technician"]
        
    return metadata

def load_and_chunk_documents():
    all_chunks = []
    
    # Initialize Docling Converter
    converter = DocumentConverter()
    
    # Pass 1 & 2 Config: Structural chunker with token limits
    chunker = HybridChunker(
        tokenizer="sentence-transformers/all-MiniLM-L6-v2", 
        max_tokens=256,                                      
        merge_peers=True                                     
    )
    
    # Find all PDFs and Markdown files recursively
    all_files = []
    for ext in ("**/*.pdf", "**/*.md"):
        all_files.extend(DATA_DIR.glob(ext))
    
    for doc_file in all_files:
        print(f"Processing & Chunking: {doc_file.name} ({doc_file.suffix.upper()})...")
        
        try:
            # Pass 1: Parse layout into a structural tree
            result = converter.convert(doc_file)
            doc_structure = result.document
            
            # Extract parent metadata
            full_text = doc_structure.export_to_markdown()
            doc_metadata = extract_metadata_from_text(full_text, doc_file.parent.name)
            
            # Pass 2: Apply token-aware chunk boundaries over layout objects
            doc_chunks = chunker.chunk(doc_structure)
            
            for i, chunk in enumerate(doc_chunks, start=1):
                # FIXED: Restored serialize() which matches your package environment version
                chunk_text = chunker.serialize(chunk)
                
                # FIXED: Safely check if headings are objects with a .text attribute or plain strings
                heading_list = []
                if chunk.meta.headings:
                    for node in chunk.meta.headings:
                        if hasattr(node, "text"):
                            heading_list.append(node.text)
                        else:
                            heading_list.append(str(node))

                all_chunks.append(
                    {
                        "text": chunk_text,
                        "metadata": {
                            "source": doc_file.name,
                            "file_type": doc_file.suffix.lower().replace(".", ""),
                            "chunk_id": f"{doc_file.stem}_chunk_{i}",
                            "department": doc_metadata["department"],
                            "document_ref": doc_metadata["document_ref"],
                            "version": doc_metadata["version"],
                            "allowed_roles": doc_metadata["allowed_roles"],
                            "heading_hierarchy": heading_list
                        }
                    }
                )
        except Exception as e:
            print(f"Error processing {doc_file.name}: {e}")
            
    return all_chunks

# # Run the fixed pipeline
# chunks = load_and_chunk_documents()
# print(f"\nSuccessfully generated {len(chunks)} structural chunks.")

# if chunks:
#     print("\n=== SAMPLE CHUNK TEXT FROM FIRST CHUNK ===")
#     print(chunks[0]["text"])
#     print("\n=== SAMPLE CHUNK METADATA ===")
#     import pprint
#     pprint.pprint(chunks[0]["metadata"])

if __name__ == "__main__":
    print("--- STARTING LOCAL TEST FOR LOADER.PY ---")
    try:
        # Run the chunk compiler
        test_chunks = load_and_chunk_documents()
        
        print(f"\n[SUCCESS] Loader compiled {len(test_chunks)} total chunks.")
        
        # Inspect the very first chunk sample if chunks exist
        if test_chunks:
            print("\n=== SAMPLE CHUNK TEXT ===")
            print(test_chunks[0]["text"])
            print("\n=== SAMPLE CHUNK METADATA ===")
            import pprint
            pprint.pprint(test_chunks[0]["metadata"])
            
    except Exception as e:
        print(f"\n[FAILURE] Loader test crashed with error: {e}")