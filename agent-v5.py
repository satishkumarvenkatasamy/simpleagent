#!/usr/bin/env python3
# agent-v5.py - Agent with PDF Knowledge Base (ChromaDB) & Chat History (chDB)
#
# Builds on agent-v4.py adding:
#   - PDF ingestion from pdf_documents/ into ChromaDB vector store
#   - Persistent chat history in chDB (embedded ClickHouse)
#   - Two new tools: search_pdf_knowledge, list_pdf_documents

import anthropic
import subprocess
import os
import json
import hashlib
import time

import pymupdf                # PDF text extraction
import chromadb               # Vector store
import chdb                   # Embedded ClickHouse

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER      = os.path.join(BASE_DIR, "pdf_documents")
CHROMADB_DIR    = os.path.join(BASE_DIR, ".chromadb")
CHDB_DIR        = os.path.join(BASE_DIR, ".chdb")

CHUNK_SIZE      = 500     # characters per chunk
CHUNK_OVERLAP   = 100     # overlap between chunks
MODEL_NAME      = "claude-opus-4-5-20251101"

# ─── API Client ──────────────────────────────────────────────────────────────

with open(os.path.expanduser("~/.hc/anthropic.key"), "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

# ─── ChromaDB Setup ──────────────────────────────────────────────────────────

os.makedirs(CHROMADB_DIR, exist_ok=True)
chroma_client = chromadb.PersistentClient(path=CHROMADB_DIR)
collection = chroma_client.get_or_create_collection(
    name="pdf_documents",
    metadata={"hnsw:space": "cosine"}
)

# ─── chDB (Chat History) Setup ───────────────────────────────────────────────

os.makedirs(CHDB_DIR, exist_ok=True)

def chdb_query(sql):
    """Run a SQL query against the embedded ClickHouse database."""
    return chdb.query(sql, "CSV", path=CHDB_DIR)

# Create chat history table
chdb_query("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id          String,
        role        String,
        content     String,
        timestamp   DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY timestamp
""")

def save_chat_message(role, content):
    """Save a single chat message to chDB."""
    msg_id = hashlib.md5(f"{role}{content}{time.time()}".encode()).hexdigest()[:16]
    escaped = content.replace("\\", "\\\\").replace("'", "\\'")
    chdb_query(f"INSERT INTO chat_history (id, role, content) VALUES ('{msg_id}', '{role}', '{escaped}')")

def load_chat_history(limit=20):
    """Load recent chat history from chDB as a conversation list."""
    result = chdb_query(f"""
        SELECT role, content FROM chat_history
        ORDER BY timestamp DESC LIMIT {limit}
    """)
    if not result:
        return []

    messages = []
    for line in result.decode().strip().split("\n"):
        if not line:
            continue
        # CSV format: "role","content"
        parts = line.split(",", 1)
        if len(parts) == 2:
            role = parts[0].strip('"')
            content = parts[1].strip('"').replace("\\'", "'").replace("\\\\", "\\")
            messages.append({"role": role, "content": content})

    messages.reverse()  # oldest first
    return messages

# ─── PDF Ingestion ───────────────────────────────────────────────────────────

def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks

def get_file_hash(filepath):
    """Get MD5 hash of a file for change detection."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()

def get_ingested_files():
    """Get set of already-ingested file hashes from ChromaDB metadata."""
    try:
        all_data = collection.get(include=["metadatas"])
        hashes = set()
        for meta in all_data["metadatas"]:
            if meta and "file_hash" in meta:
                hashes.add(meta["file_hash"])
        return hashes
    except Exception:
        return set()

def ingest_pdf(filepath):
    """Extract text from a PDF and store chunks in ChromaDB."""
    filename = os.path.basename(filepath)
    file_hash = get_file_hash(filepath)

    print(f"  📄 Ingesting: {filename}")

    doc = pymupdf.open(filepath)
    all_chunks = []
    all_ids = []
    all_metadatas = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if not text:
            continue

        chunks = chunk_text(text)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{file_hash}_{page_num}_{i}"
            all_chunks.append(chunk)
            all_ids.append(chunk_id)
            all_metadatas.append({
                "filename": filename,
                "page": page_num + 1,
                "chunk_index": i,
                "file_hash": file_hash
            })

    page_count = len(doc)
    doc.close()

    if all_chunks:
        # Upsert in batches of 100 (ChromaDB limit)
        for start in range(0, len(all_chunks), 100):
            end = start + 100
            collection.upsert(
                ids=all_ids[start:end],
                documents=all_chunks[start:end],
                metadatas=all_metadatas[start:end]
            )
        print(f"    ✅ Stored {len(all_chunks)} chunks from {page_count} pages")
    else:
        print(f"    ⚠️  No text found in {filename}")

def ingest_all_pdfs():
    """Scan pdf_documents/ and ingest any new or changed PDFs."""
    os.makedirs(PDF_FOLDER, exist_ok=True)

    pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print("📂 No PDFs found in pdf_documents/ — add PDFs there to enable knowledge search.")
        return

    ingested_hashes = get_ingested_files()
    new_count = 0

    for filename in sorted(pdf_files):
        filepath = os.path.join(PDF_FOLDER, filename)
        file_hash = get_file_hash(filepath)
        if file_hash not in ingested_hashes:
            ingest_pdf(filepath)
            new_count += 1

    if new_count == 0:
        print(f"📂 {len(pdf_files)} PDF(s) already ingested — no new files.")
    else:
        print(f"📂 Ingested {new_count} new PDF(s). Total PDFs: {len(pdf_files)}")

# ─── Tools (V4 tools + 2 new) ───────────────────────────────────────────────

TOOLS = [
    # --- V4 tools (unchanged) ---
    {
        "name": "read_file",
        "description": "Read the contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file (creates or overwrites)",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current directory)"}
            }
        }
    },
    {
        "name": "run_command",
        "description": "Run a shell command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run"}
            },
            "required": ["command"]
        }
    },
    # --- V5 new tools ---
    {
        "name": "search_pdf_knowledge",
        "description": "Search the PDF knowledge base for information. Returns relevant text chunks from ingested PDF documents along with source file and page number. Use this when the user asks about content from PDF documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "num_results": {"type": "integer", "description": "Number of results to return (default: 5)", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "list_pdf_documents",
        "description": "List all PDF documents that have been ingested into the knowledge base",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

# ─── Permission Checking (from V4) ──────────────────────────────────────────

DANGEROUS_PATTERNS = ["rm ", "sudo ", "chmod ", "mv ", "cp ", "> ", ">>"]

def check_permission(tool_name, tool_input):
    """Check if an action requires user permission."""
    if tool_name == "run_command":
        cmd = tool_input.get("command", "")
        if any(p in cmd for p in DANGEROUS_PATTERNS):
            print(f"\n⚠️  Potentially dangerous command: {cmd}")
            response = input("Allow? (y/n): ").strip().lower()
            return response == "y"
    elif tool_name == "write_file":
        path = tool_input.get("path", "")
        print(f"\n📝 Will write to: {path}")
        response = input("Allow? (y/n): ").strip().lower()
        return response == "y"
    return True

# ─── Tool Execution ─────────────────────────────────────────────────────────

def execute_tool(name, tool_input):
    """Execute a tool and return the result."""

    # --- V4 tools ---
    if name == "read_file":
        path = tool_input["path"]
        try:
            with open(path, "r") as f:
                content = f.read()
            return f"Contents of {path}:\n{content}"
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "write_file":
        path = tool_input["path"]
        content = tool_input["content"]
        try:
            with open(path, "w") as f:
                f.write(content)
            return f"✅ Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    elif name == "list_files":
        path = tool_input.get("path", ".")
        try:
            files = os.listdir(path)
            return f"Files in {path}:\n" + "\n".join(f"  {f}" for f in sorted(files))
        except Exception as e:
            return f"Error listing files: {e}"

    elif name == "run_command":
        cmd = tool_input["command"]
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            return f"$ {cmd}\n{output}" if output else f"$ {cmd}\n(no output)"
        except subprocess.TimeoutExpired:
            return f"Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {e}"

    # --- V5 new tools ---
    elif name == "search_pdf_knowledge":
        query = tool_input["query"]
        num_results = tool_input.get("num_results", 5)
        try:
            results = collection.query(query_texts=[query], n_results=num_results)

            if not results["documents"] or not results["documents"][0]:
                return "No relevant results found in the PDF knowledge base."

            output_parts = []
            for i, (doc, meta, dist) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                source = meta.get("filename", "unknown")
                page = meta.get("page", "?")
                score = round(1 - dist, 3)  # cosine similarity
                output_parts.append(
                    f"--- Result {i+1} [Source: {source}, Page: {page}, Relevance: {score}] ---\n{doc}"
                )

            return "\n\n".join(output_parts)
        except Exception as e:
            return f"Error searching knowledge base: {e}"

    elif name == "list_pdf_documents":
        try:
            pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]
            if not pdf_files:
                return "No PDF documents found. Add PDFs to the pdf_documents/ folder."

            # Get ingestion stats from ChromaDB
            all_data = collection.get(include=["metadatas"])
            file_chunks = {}
            for meta in all_data["metadatas"]:
                if meta:
                    fname = meta.get("filename", "unknown")
                    file_chunks[fname] = file_chunks.get(fname, 0) + 1

            lines = []
            for f in sorted(pdf_files):
                chunks = file_chunks.get(f, 0)
                status = f"({chunks} chunks indexed)" if chunks > 0 else "(not yet indexed)"
                lines.append(f"  📄 {f} {status}")

            return f"PDF Documents in knowledge base:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing documents: {e}"

    return f"Unknown tool: {name}"

# ─── Agent Loop ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a helpful coding assistant with access to a PDF knowledge base. Working directory: {os.getcwd()}

You have access to PDF documents that have been ingested into a vector knowledge base.
When the user asks questions that might relate to PDF document content, use the search_pdf_knowledge tool to find relevant information.
Always cite which PDF file and page number the information came from in your response.
Format your answers in the way the user requests (table, summary, bullet points, etc.)."""

def agent_loop(user_message, conversation_history):
    """Run the agent loop until the task is complete."""
    conversation_history.append({"role": "user", "content": user_message})
    save_chat_message("user", user_message)

    while True:
        # Call Claude
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation_history
        )

        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": response.content})

        # Check if we're done (no tool use)
        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n🤖 {block.text}")
                    save_chat_message("assistant", block.text)
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                print(f"\n🔧 {tool_name}: {json.dumps(tool_input)}")

                # Check permissions
                if not check_permission(tool_name, tool_input):
                    result = "Permission denied by user"
                    print(f"   ❌ {result}")
                else:
                    result = execute_tool(tool_name, tool_input)
                    display = result[:200] + "..." if len(result) > 200 else result
                    print(f"   → {display}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        # Add tool results to conversation
        conversation_history.append({"role": "user", "content": tool_results})

    return conversation_history

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Agent V5 — PDF Knowledge Base + Chat History")
    print("=" * 60)
    print()

    # Step 1: Ingest PDFs
    print("🔍 Scanning for PDF documents...")
    ingest_all_pdfs()
    print()

    # Step 2: Load chat history from chDB
    conversation_history = load_chat_history(limit=20)
    if conversation_history:
        print(f"💬 Restored {len(conversation_history)} messages from chat history.")
    else:
        print("💬 No previous chat history found. Starting fresh.")
    print()

    print("Type your requests, or 'quit' to exit.")
    print("Tip: Add PDFs to pdf_documents/ and restart to index them.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        conversation_history = agent_loop(user_input, conversation_history)

if __name__ == "__main__":
    main()
