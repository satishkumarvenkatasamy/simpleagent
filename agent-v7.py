#!/usr/bin/env python3
# agent-v7.py - Agent with Browser Automation via MCP
#
# Builds on agent-v4.py adding browser control through the browseroperator MCP server.
# The MCP server is launched as a subprocess (stdio transport) and the agent
# discovers browser tools dynamically. Claude can use both local tools (files,
# commands) and browser tools (navigate, click, type, etc.) in the same session.

import anthropic
import subprocess
import os
import sys
import json
import asyncio

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MODEL_NAME = "claude-opus-4-5-20251101"

with open(os.path.expanduser("~/.hc/anthropic.key"), "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

# ─── Local Tools (from V4) ──────────────────────────────────────────────────

LOCAL_TOOLS = [
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

# ─── Local Tool Execution (from V4) ─────────────────────────────────────────

def execute_local_tool(name, tool_input):
    """Execute a local tool and return the result."""
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
    # MCP returns a list of content blocks
    parts = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else "(no output)"

# ─── Agent Loop (async, with MCP session) ───────────────────────────────────

SYSTEM_PROMPT = f"""You are a helpful coding assistant with browser automation capabilities. Working directory: {os.getcwd()}

You have two sets of tools:
1. LOCAL tools: read_file, write_file, list_files, run_command — for file and shell operations.
2. BROWSER tools: launch_browser, navigate_to, click_element, type_text, get_page_source, take_screenshot, etc. — for web automation.

To use the browser:
1. First call launch_browser to start Chrome or Firefox.
2. Then navigate_to a URL.
3. Interact with elements using click_element, type_text, etc.
4. Extract data with get_element_text, get_page_source, etc.
5. Call close_browser when done.

Selectors can be css, xpath, id, name, or class (specify via by_type parameter)."""

async def agent_loop(user_message, conversation_history, mcp_session, browser_tool_names):
    """Run the agent loop — routes tool calls to local executor or MCP server."""
    conversation_history.append({"role": "user", "content": user_message})

    # Combine local + browser tools for Claude
    all_tools = LOCAL_TOOLS + browser_tool_names  # browser_tool_names is already Anthropic format

    while True:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=all_tools,
            messages=conversation_history
        )

        conversation_history.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n🤖 {block.text}")
            break

        # Process tool calls
        tool_results = []
        local_tool_set = {t["name"] for t in LOCAL_TOOLS}

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                print(f"\n🔧 {tool_name}: {json.dumps(tool_input)}")

                if tool_name in local_tool_set:
                    # Local tool — check permissions, execute locally
                    if not check_permission(tool_name, tool_input):
                        result = "Permission denied by user"
                        print(f"   ❌ {result}")
                    else:
                        result = execute_local_tool(tool_name, tool_input)
                        display = result[:200] + "..." if len(result) > 200 else result
                        print(f"   → {display}")
                else:
                    # Browser tool — forward to MCP server
                    try:
                        result = await call_mcp_tool(mcp_session, tool_name, tool_input)
                        display = result[:200] + "..." if len(result) > 200 else result
                        print(f"   🌐 {display}")
                    except Exception as e:
                        result = f"MCP tool error: {e}"
                        print(f"   ❌ {result}")

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
    print("  Agent V7 — Browser Automation via MCP")
    print("=" * 60)
    print()

    # Launch the browser MCP server as a subprocess via stdio
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "browseroperator.browser_server", "--transport", "stdio"],
        cwd=BASE_DIR
    )

    print("🚀 Starting browser MCP server...")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the MCP session
            await session.initialize()

            # Discover browser tools from the MCP server
            tools_result = await session.list_tools()
            browser_tools_anthropic = [mcp_schema_to_anthropic_tool(t) for t in tools_result.tools]

            print(f"✅ Connected to MCP server — {len(browser_tools_anthropic)} browser tools available:")
            for t in browser_tools_anthropic:
                print(f"   🌐 {t['name']}")
            print()
            print("Type your requests, or 'quit' to exit.\n")

            conversation_history = []

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
