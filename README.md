# SimpleAgent — Building AI Agents Step by Step

A hands-on codebase that teaches how to build AI agents incrementally. Each version adds a new capability, starting from a basic command runner and ending with browser automation via MCP.

## Quick Comparison

| Version | Language | Tools | Key Feature Added |
|---------|----------|-------|-------------------|
| **openai** | Python | 1 (weather) | No agent loop — single-shot tool call (what NOT to do) |
| **v1** | Python | Bash only | Basic agent loop with JSON actions |
| **v2** | Python | Bash only | Permission checks for dangerous commands |
| **v3** | Python | 4 structured tools | Anthropic Tools API, file operations, conversation compaction |
| **v4** | Python | 4 structured tools | Interactive REPL, permission framework, command timeouts |
| **v5** | Python | 6 structured tools | PDF ingestion (ChromaDB), persistent chat history (chDB) |
| **v6** | Python | 4 local + 16 browser tools | Browser automation — direct Selenium (no MCP) |
| **v7** | Python | 4 local + 21 MCP browser tools | Browser automation via MCP server (Selenium) |
| **v8** | Python | 6 local + 21 MCP browser tools | Full-stack: PDF RAG + chat history + browser via MCP |

## Prerequisites

- Python 3.13+
- An Anthropic API key stored at `~/.hc/anthropic.key` (for v1–v8)
- An OpenAI API key at `~/.hc/openai.key` or `OPENAI_API_KEY` env var (for openai example)

```bash
echo "sk-ant-your-key-here" > ~/.hc/anthropic.key
```

### Install dependencies

OpenAI example (no agent loop):

```bash
pip3 install -r requirements-openai.txt
```

Versions 1–4 only need the Anthropic SDK:

```bash
pip3 install -r requirements.txt
```

Version 5 has additional dependencies:

```bash
pip3 install -r requirements-v5.txt
```

Versions 6–8 (browser automation):

```bash
pip3 install -r requirements-v6.txt   # v6: direct Selenium, no MCP
pip3 install -r requirements-v7.txt   # v7: adds MCP protocol
pip3 install -r requirements-v8.txt   # v8: PDF RAG + chat history + MCP browser
```

## Version Details

---

### OpenAI Example — No Agent Loop (Anti-pattern)

**File:** `openai-based-simple-agent.py`

This is **not** a true agent — it's a single-shot tool call example using OpenAI. It demonstrates what happens when there is no agent loop: the model can call a tool once, but it cannot reason over the result and decide what to do next. Included as a contrast to show **why an agent loop matters**.

**How it works:**
1. User asks a question (e.g., "What's the weather in London?")
2. Model returns a `get_weather` function call
3. Code executes the function and feeds the result back
4. Model generates a final response

**What's missing (compared to V1+):**
- No loop — the model gets exactly one chance to call a tool
- No multi-step reasoning — can't chain decisions based on results
- No ability to recover from errors or try a different approach
- Hardcoded to a single tool (`get_weather` via weatherapi.com)

**Key concepts:**
- OpenAI function calling (single-shot)
- Why a loop is essential for agentic behavior
- The difference between "tool use" and "agent"

**Prerequisites:**
- OpenAI API key at `~/.hc/openai.key` or `OPENAI_API_KEY` env var
- Weather API key at `~/.hc/weatherapi.key` (from weatherapi.com)

**Run:**
```bash
pip3 install -r requirements-openai.txt
python3 openai-based-simple-agent.py "What is the weather in London?"
```

---

### V1 — The Simplest Agent

**File:** `agent-v1.py` (also `agent-v1.sh` — original bash version)

The most minimal agent possible. Claude receives a task, decides what bash command to run, executes it, reads the output, and repeats until done.

**Key concepts:**
- Agent loop pattern (think → act → observe → repeat)
- JSON-based action format (prompt-engineered tool use)
- Message history accumulation

**How it works:**
1. User provides a task as a CLI argument
2. Claude responds with `{"action": "bash", "command": "..."}` or `{"action": "done", "message": "..."}`
3. The agent executes the command and feeds output back to Claude
4. Loop continues until Claude responds with `"done"`

**Run:**
```bash
python3 agent-v1.py "list all python files in the current directory"
```

---

### V2 — Adding Safety Guardrails

**File:** `agent-v2.py`

Same as V1 but adds permission checking before executing dangerous commands.

**What's new over V1:**
- `execute_with_permission()` function
- Regex-based detection of dangerous patterns: `rm`, `sudo`, `chmod`, `curl | sh`
- User prompted to approve/deny before execution

**Key concepts:**
- Safety guardrails in agentic systems
- Pattern-based risk detection
- Human-in-the-loop confirmation

**Run:**
```bash
python3 agent-v2.py "clean up temporary files in /tmp"
```

---

### V3 — Structured Tools

**File:** `agent-v3.py`

A major architectural shift. Instead of prompt-engineering Claude to respond with JSON, this version uses the **Anthropic Tools API** — Claude natively understands and invokes structured tools.

**What's new over V2:**
- Anthropic Tools API with JSON schema definitions
- Multiple tool types beyond bash: `read_file`, `write_file`, `run_bash`, `edit_file`
- Conversation compaction (summarize long conversations to free context)

**Available tools:**
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create or overwrite a file |
| `run_bash` | Execute a shell command |
| `edit_file` | Find-and-replace a unique string in a file |

**Key concepts:**
- Native tool use vs. prompt-engineered JSON
- Tool input schemas for validation
- `stop_reason: "tool_use"` vs `"end_turn"` flow control
- Context window management via summarization

**Run:**
```bash
python3 agent-v3.py "read main.py and add error handling to the calculate function"
```

---

### V4 — Interactive Agent with Permissions

**File:** `agent-v4.py`

Turns the single-task agent into an interactive session with a persistent conversation and a full permission framework.

**What's new over V3:**
- Interactive REPL loop (multi-turn conversation)
- Permission checks for dangerous commands AND all file writes
- 30-second timeout on command execution
- `list_files` tool for safe directory browsing

**Available tools:**
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create or overwrite a file (requires permission) |
| `list_files` | List directory contents |
| `run_command` | Execute a shell command (30s timeout) |

**Key concepts:**
- Persistent conversation across multiple turns
- Layered permission model (pattern-based + tool-based)
- Timeout protection against hanging processes

**Run:**
```bash
python3 agent-v4.py
# Then type your requests interactively
```

---

### V5 — PDF Knowledge Base + Persistent Chat History

**File:** `agent-v5.py`

The most advanced version. Adds a vector knowledge base for PDF documents (ChromaDB) and persistent chat history (chDB/embedded ClickHouse). All V4 features are included.

**What's new over V4:**
- PDF ingestion from `pdf_documents/` folder on startup
- Vector similarity search over PDF content
- Source attribution (filename + page number) in answers
- Chat history persisted to disk and restored on restart
- Change detection — only re-ingests new/modified PDFs

**Available tools (V4 tools + 2 new):**
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Create or overwrite a file (requires permission) |
| `list_files` | List directory contents |
| `run_command` | Execute a shell command (30s timeout) |
| `search_pdf_knowledge` | Vector search over ingested PDF documents |
| `list_pdf_documents` | Show all PDFs and their indexing status |

**Key concepts:**
- RAG (Retrieval-Augmented Generation) pattern
- Text chunking with overlap for vector search
- Embedding-based similarity search (ChromaDB)
- Persistent storage with embedded databases
- Source attribution in AI responses

**Data directories (auto-created):**
| Directory | Purpose |
|-----------|---------|
| `pdf_documents/` | Drop PDF files here for ingestion |
| `.chromadb/` | ChromaDB vector store |
| `.chdb/` | chDB (ClickHouse) chat history |

**Run:**
```bash
pip3 install -r requirements-v5.txt
# Add PDFs to pdf_documents/
python3 agent-v5.py
```

**Example interaction:**
```
You: What does the Q3 report say about revenue?
🔧 search_pdf_knowledge: {"query": "Q3 revenue"}
🤖 According to the Q3 report (Q3-Report-2024.pdf, page 4), revenue grew 15% YoY...
```

---

### V6 — Browser Automation (Direct, no MCP)

**File:** `agent-v6.py`

Adds browser automation by importing `BrowserManager` directly — no MCP server, no subprocess, no protocol overhead. Selenium runs in the same process as the agent. Compare with V7 to see the difference MCP makes.

**What's new over V4:**
- 16 browser tools (navigate, click, type, screenshot, etc.)
- Direct in-process Selenium calls via `BrowserManager`
- Browser cleanup on exit

**Available tools:**
| Category | Tools |
|----------|-------|
| Local (from V4) | `read_file`, `write_file`, `list_files`, `run_command` |
| Browser Control | `launch_browser`, `close_browser`, `navigate_to`, `go_back`, `go_forward`, `refresh_page`, `take_screenshot` |
| Element Interaction | `click_element`, `type_text`, `submit_form` |
| Data Extraction | `get_element_text`, `get_page_source`, `get_current_url`, `get_page_title` |
| Element Utilities | `check_element_exists`, `wait_for_element` |

**Key concepts:**
- Direct library integration (import and call)
- Same browser capabilities as V7 but without MCP
- Simpler architecture — everything in one process
- Good baseline for understanding what MCP adds

**V6 vs V7 — why both?**
| Aspect | V6 (Direct) | V7 (MCP) |
|--------|-------------|----------|
| Architecture | Single process | Client + server subprocess |
| Tool discovery | Hardcoded tool definitions | Dynamic from MCP server |
| Extra dependency | None (just selenium) | `mcp` library |
| Extensibility | Edit agent code | Swap/add MCP servers |
| Reusability | Tied to this agent | Any MCP client can use the server |

**Run:**
```bash
pip3 install -r requirements-v6.txt
python3 agent-v6.py
```

---

### V7 — Browser Automation via MCP

**File:** `agent-v7.py`

Adds browser automation by connecting to the `browseroperator` MCP server as a client. The MCP server runs as a subprocess (stdio transport) and exposes 21 Selenium-based browser tools. Claude can use both local tools and browser tools in the same session.

**What's new over V4:**
- MCP client connecting to a local MCP server (stdio transport)
- Dynamic tool discovery — browser tools loaded from the server at startup
- Hybrid tool routing — local tools executed in-process, browser tools forwarded via MCP
- 21 browser tools: navigation, clicking, typing, screenshots, cookies, etc.

**Available tools:**
| Category | Tools |
|----------|-------|
| Local (from V4) | `read_file`, `write_file`, `list_files`, `run_command` |
| Browser Control | `launch_browser`, `close_browser`, `navigate_to`, `go_back`, `go_forward`, `refresh_page`, `take_screenshot` |
| Element Interaction | `click_element`, `type_text`, `select_dropdown`, `submit_form` |
| Data Extraction | `get_element_text`, `get_element_attribute`, `get_page_source`, `get_current_url`, `get_page_title` |
| Element Utilities | `check_element_exists`, `wait_for_element` |
| Cookies & Status | `get_cookies`, `set_cookie`, `get_browser_status` |

**Key concepts:**
- MCP (Model Context Protocol) — standardized tool server protocol
- MCP client/server over stdio transport
- Dynamic tool discovery from MCP server
- Hybrid local + remote tool routing in one agent

**How it works:**
1. Agent launches `browseroperator` MCP server as a subprocess
2. Connects via stdio and discovers 21 browser tools
3. Converts MCP tool schemas to Anthropic tool format
4. When Claude calls a tool, the agent routes it:
   - Local tools → executed in-process
   - Browser tools → forwarded to MCP server via `session.call_tool()`

**Run:**
```bash
pip3 install -r requirements-v7.txt
python3 agent-v7.py
```

**Example interaction:**
```
You: Go to wikipedia.org and search for "Python programming"
🔧 launch_browser: {"browser_type": "chrome"}
   🌐 Browser launched successfully
🔧 navigate_to: {"url": "https://wikipedia.org"}
   🌐 Navigated to https://wikipedia.org
🔧 type_text: {"selector": "#searchInput", "text": "Python programming", "by_type": "css"}
   🌐 Successfully typed text into element: #searchInput
🔧 submit_form: {"selector": "#search-form", "by_type": "css"}
   🌐 Successfully submitted form
🤖 I've navigated to Wikipedia and searched for "Python programming"...
```

---

### V8 — Full-Stack Agent (PDF RAG + Chat History + Browser via MCP)

**File:** `agent-v8.py`

The most complete version. Combines all features from V5 (PDF knowledge base + persistent chat history) and V7 (browser automation via MCP) into a single agent.

**What's new over V7:**
- PDF ingestion from `pdf_documents/` into ChromaDB vector store
- Vector similarity search over PDF content with source attribution
- Persistent chat history saved to disk (chDB/ClickHouse embedded)
- Conversation history restored on restart
- Change detection — only re-ingests new/modified PDFs

**Available tools:**
| Category | Tools |
|----------|-------|
| File/Shell | `read_file`, `write_file`, `list_files`, `run_command` |
| Knowledge | `search_pdf_knowledge`, `list_pdf_documents` |
| Browser (via MCP) | `launch_browser`, `navigate_to`, `click_element`, `type_text`, `take_screenshot`, `get_page_source`, and 15 more |

**Key concepts:**
- Combines RAG + persistent memory + browser automation in one agent
- All V5 and V7 concepts apply here
- Tool routing: local tools → in-process, browser tools → MCP server

**Data directories (auto-created):**
| Directory | Purpose |
|-----------|---------|
| `pdf_documents/` | Drop PDF files here for ingestion |
| `.chromadb/` | ChromaDB vector store |
| `.chdb/` | chDB (ClickHouse) chat history |

**Run:**
```bash
pip3 install -r requirements-v8.txt
# Optionally add PDFs to pdf_documents/
python3 agent-v8.py
```

**Example interaction:**
```
You: Analyze kpi-csp11.csv and summarize the key metrics
🔧 read_file: {"path": "kpi-csp11.csv"}
   → Contents of kpi-csp11.csv: ...
🤖 Here's a summary of the key KPI metrics...

You: Search the web for the latest AI agent frameworks
🔧 launch_browser: {"browser_type": "chrome"}
   🌐 Browser launched successfully
🔧 navigate_to: {"url": "https://www.google.com"}
   🌐 Navigated successfully
...
```


## Architecture Evolution

```
V1: User → [JSON prompt] → Claude → {"action":"bash"} → subprocess → output → Claude → done
V2: User → [JSON prompt] → Claude → {"action":"bash"} → permission? → subprocess → output → Claude → done
V3: User → [Tools API] → Claude → tool_use block → execute_tool() → tool_result → Claude → end_turn
V4: User → [REPL + Tools API] → Claude → tool_use → permission? → execute_tool() → tool_result → Claude → end_turn
V5: User → [REPL + Tools API + RAG] → Claude → search_pdf_knowledge → ChromaDB → tool_result → Claude → end_turn
                                                                         ↕                    ↕
                                                                    .chromadb/             .chdb/
V6: User → [REPL + Tools API] → Claude → tool_use → local? → execute_tool() → file/shell
                                                    → browser? → BrowserManager → Selenium (in-process)
V7: User → [REPL + Tools API + MCP] → Claude → tool_use → local? → execute_local_tool()
                                                        → browser? → MCP stdio → browseroperator → Selenium
V8: User → [REPL + Tools API + RAG + MCP] → Claude → tool_use → local/knowledge? → execute_local_tool()
                                                               → browser? → MCP stdio → browseroperator → Selenium
                                                                    ↕                         ↕
                                                               .chromadb/ .chdb/         pdf_documents/
```

## File Reference

```
simpleagent/
├── openai-based-simple-agent.py  # No agent loop — single-shot tool call (anti-pattern)
├── agent-v1.py            # Basic agent loop
├── agent-v2.py            # + permission checks
├── agent-v3.py            # + structured tools (Anthropic Tools API)
├── agent-v4.py            # + interactive REPL, timeouts
├── agent-v5.py            # + PDF knowledge base, chat history
├── agent-v6.py            # + browser automation (direct Selenium)
├── agent-v7.py            # + browser automation via MCP
├── agent-v8.py            # + PDF RAG + chat history + browser via MCP (full-stack)
├── requirements-openai.txt # Dependencies for openai example
├── requirements.txt       # Dependencies for v1–v4
├── requirements-v5.txt    # Dependencies for v5
├── requirements-v6.txt    # Dependencies for v6
├── requirements-v7.txt    # Dependencies for v7
├── requirements-v8.txt    # Dependencies for v8
├── pdf_documents/         # Drop PDFs here for v5 ingestion
├── browseroperator/       # MCP server for browser automation (Selenium)
│   ├── browser_server.py  # FastMCP server (21 tools)
│   ├── browser_manager.py # Selenium WebDriver wrapper
│   ├── security_manager.py# URL filtering, rate limiting
│   └── config.json        # Domain whitelist, browser settings
```
