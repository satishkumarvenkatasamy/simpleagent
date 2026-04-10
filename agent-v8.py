#!/usr/bin/env python3
# agent-v8.py - Agent with PDF Knowledge Base + Chat History + Browser Automation via MCP
#
# Combines all features from:
#   - agent-v5.py: PDF ingestion (ChromaDB), persistent chat history (chDB)
#   - agent-v7.py: Browser automation via MCP server (browseroperator)
#
# Tools available:
#   LOCAL (file/shell): read_file, write_file, list_files, run_command
#   LOCAL (knowledge):  search_pdf_knowledge, list_pdf_documents
#   BROWSER (via MCP):  launch_browser, navigate_to, click_element, type_text,
#                       take_screenshot, get_page_source, and more...

import anthropic
import subprocess
import os
import sys
import json
import asyncio
import hashlib
import time
import httpx
import csv
import io

import pymupdf        # PDF text extraction
import chromadb       # Vector store
import chdb           # Embedded ClickHouse (chat history)

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PDF_FOLDER   = os.path.join(BASE_DIR, "pdf_documents")
CHROMADB_DIR = os.path.join(BASE_DIR, ".chromadb")
CHDB_DIR     = os.path.join(BASE_DIR, ".chdb")

CHUNK_SIZE   = 500    # characters per chunk
CHUNK_OVERLAP = 100   # overlap between chunks
MODEL_NAME   = "claude-opus-4-5-20251101"

# ─── API Client ──────────────────────────────────────────────────────────────

with open(os.path.expanduser("~/.hc/anthropic.key"), "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(
    api_key=api_key,
    http_client=httpx.Client(verify=False)
)

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
    result = chdb.query(sql, "CSV", path=CHDB_DIR)
    if result is None:
        return None
    if hasattr(result, "read_string"):
        return result.read_string()
    elif hasattr(result, "decode"):
        return result.decode()
    return str(result)

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

MAX_MSG_CHARS = 2000  # truncate old messages to keep history within token limits

def load_chat_history(limit=20):
    """Load recent chat history from chDB as a conversation list."""
    result = chdb_query(f"""
        SELECT role, content FROM chat_history
        ORDER BY timestamp DESC LIMIT {limit}
    """)
    if not result:
        return []

    messages = []
    reader = csv.reader(io.StringIO(result.strip()))
    for row in reader:
        if len(row) == 2:
            role, content = row
            if role in ("user", "assistant"):
                if len(content) > MAX_MSG_CHARS:
                    content = content[:MAX_MSG_CHARS] + "... [truncated]"
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
    all_chunks, all_ids, all_metadatas = [], [], []

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

# ─── Local Tools ─────────────────────────────────────────────────────────────

LOCAL_TOOLS = [
    # --- V4 tools ---
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
    # --- V5 knowledge tools ---
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

LOCAL_TOOL_NAMES = {t["name"] for t in LOCAL_TOOLS}

# ─── Permission Checking ─────────────────────────────────────────────────────

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

# ─── Local Tool Execution ────────────────────────────────────────────────────

def execute_local_tool(name, tool_input):
    """Execute a local tool and return the result."""

    if name == "read_file":
        path = tool_input.get("path", tool_input.get("file_path", ""))
        try:
            with open(path, "r") as f:
                return f"Contents of {path}:\n{f.read()}"
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "write_file":
        path = tool_input.get("path", tool_input.get("file_path", ""))
        content = tool_input.get("content", tool_input.get("text", ""))
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
        cmd = tool_input.get("command", tool_input.get("cmd", ""))
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            return f"$ {cmd}\n{output}" if output else f"$ {cmd}\n(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {e}"

    elif name == "search_pdf_knowledge":
        query = tool_input.get("query", tool_input.get("q", tool_input.get("search_query", "")))
        num_results = tool_input.get("num_results", 5)
        try:
            results = collection.query(query_texts=[query], n_results=num_results)
            if not results["documents"] or not results["documents"][0]:
                return "No relevant results found in the PDF knowledge base."
            parts = []
            for i, (doc, meta, dist) in enumerate(zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )):
                source = meta.get("filename", "unknown")
                page   = meta.get("page", "?")
                score  = round(1 - dist, 3)
                parts.append(
                    f"--- Result {i+1} [Source: {source}, Page: {page}, Relevance: {score}] ---\n{doc}"
                )
            return "\n\n".join(parts)
        except Exception as e:
            return f"Error searching knowledge base: {e}"

    elif name == "list_pdf_documents":
        try:
            pdf_files = [f for f in os.listdir(PDF_FOLDER) if f.lower().endswith(".pdf")]
            if not pdf_files:
                return "No PDF documents found. Add PDFs to the pdf_documents/ folder."
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
            return "PDF Documents in knowledge base:\n" + "\n".join(lines)
        except Exception as e:
            return f"Error listing documents: {e}"

    return f"Unknown tool: {name}"

# ─── MCP Tool Helpers ────────────────────────────────────────────────────────

def mcp_schema_to_anthropic_tool(mcp_tool):
    """Convert an MCP tool definition to Anthropic tool format."""
    input_schema = mcp_tool.inputSchema if mcp_tool.inputSchema else {"type": "object", "properties": {}}
    return {
        "name": mcp_tool.name,
        "description": mcp_tool.description or mcp_tool.name,
        "input_schema": input_schema
    }

async def call_mcp_tool(session, tool_name, tool_input):
    """Call a tool on the MCP server and return the result as a string."""
    result = await session.call_tool(tool_name, arguments=tool_input)
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else "(no output)"

# ─── Agent Loop ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a helpful assistant with file operations, a PDF knowledge base, and browser automation capabilities. Working directory: {os.getcwd()}

You have three sets of tools:
1. FILE tools: read_file, write_file, list_files, run_command — for file and shell operations.
2. KNOWLEDGE tools: search_pdf_knowledge, list_pdf_documents — for querying ingested PDF documents.
3. BROWSER tools (via MCP): launch_browser, navigate_to, click_element, type_text, take_screenshot, etc. — for web automation.

When answering questions about PDF content, always cite the source file and page number.
To use the browser: call launch_browser first, then navigate_to a URL, interact with elements, and close_browser when done.
Selectors can be css, xpath, id, name, or class (specify via by_type parameter)."""

async def agent_loop(user_message, conversation_history, mcp_session, browser_tool_names):
    """Run the agent loop — routes tool calls to local executor or MCP server."""
    conversation_history.append({"role": "user", "content": user_message})
    save_chat_message("user", user_message)

    all_tools = LOCAL_TOOLS + browser_tool_names

    while True:
        # Keep only the last 6 messages to avoid exceeding the context window
        trimmed_history = conversation_history[-6:] if len(conversation_history) > 6 else conversation_history

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=all_tools,
            messages=trimmed_history
        )

        conversation_history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n🤖 {block.text}")
                    save_chat_message("assistant", block.text)
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_name  = block.name
                tool_input = block.input

                print(f"\n🔧 {tool_name}: {json.dumps(tool_input)}")

                if tool_name in LOCAL_TOOL_NAMES:
                    if not check_permission(tool_name, tool_input):
                        result = "Permission denied by user"
                        print(f"   ❌ {result}")
                    else:
                        result  = execute_local_tool(tool_name, tool_input)
                        display = result[:200] + "..." if len(result) > 200 else result
                        print(f"   → {display}")
                else:
                    try:
                        result  = await call_mcp_tool(mcp_session, tool_name, tool_input)
                        display = result[:200] + "..." if len(result) > 200 else result
                        print(f"   🌐 {display}")
                    except Exception as e:
                        result = f"MCP tool error: {e}"
                        print(f"   ❌ {result}")

                # Truncate large tool results (e.g. PDF search) to stay within token limits
                MAX_TOOL_RESULT = 4000
                if len(result) > MAX_TOOL_RESULT:
                    result = result[:MAX_TOOL_RESULT] + "\n... [truncated]"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        conversation_history.append({"role": "user", "content": tool_results})

    return conversation_history

# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Agent V8 — PDF Knowledge Base + Chat History + Browser MCP")
    print("=" * 60)
    print()

    # Step 1: Ingest PDFs into ChromaDB
    print("🔍 Scanning for PDF documents...")
    ingest_all_pdfs()
    print()

    # Step 2: Load persistent chat history from chDB
    conversation_history = load_chat_history(limit=10)
    if conversation_history:
        print(f"💬 Restored {len(conversation_history)} messages from chat history.")
    else:
        print("💬 No previous chat history found. Starting fresh.")
    print()

    # Step 3: Launch the browser MCP server as a subprocess
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "browseroperator.browser_server", "--transport", "stdio"],
        cwd=BASE_DIR
    )

    print("🚀 Starting browser MCP server...")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            browser_tools_anthropic = [mcp_schema_to_anthropic_tool(t) for t in tools_result.tools]

            print(f"✅ Connected to MCP server — {len(browser_tools_anthropic)} browser tools available.")
            print()
            print("Type your requests, or 'quit' to exit.")
            print("Tips:")
            print("  - Ask questions about PDFs → uses search_pdf_knowledge")
            print("  - Ask to browse the web   → uses browser tools via MCP")
            print("  - Add PDFs to pdf_documents/ and restart to index them.\n")

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

                conversation_history = await agent_loop(
                    user_input, conversation_history, session, browser_tools_anthropic
                )

    print("🛑 MCP server stopped.")

if __name__ == "__main__":
    asyncio.run(main())
