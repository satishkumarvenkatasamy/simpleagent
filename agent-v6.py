#!/usr/bin/env python3
# agent-v6.py - Agent with Browser Automation (direct, no MCP)
#
# Builds on agent-v4.py adding browser control by importing BrowserManager
# directly. No MCP server needed — the agent calls Selenium methods in-process.
# Compare with agent-v7.py which uses the same browser tools but via MCP.

import anthropic
import subprocess
import os
import json

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browseroperator.browser_manager import BrowserManager

# ─── Configuration ───────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "browseroperator", "config.json")
MODEL_NAME  = "claude-opus-4-5-20251101"

with open(os.path.expanduser("~/.hc/anthropic.key"), "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

# ─── Browser Manager (direct, no MCP) ───────────────────────────────────────

browser = BrowserManager(config_path=CONFIG_PATH)

# ─── Tools ───────────────────────────────────────────────────────────────────

TOOLS = [
    # --- V4 local tools ---
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
    # --- Browser tools (direct Selenium calls) ---
    {
        "name": "launch_browser",
        "description": "Launch Chrome or Firefox browser",
        "input_schema": {
            "type": "object",
            "properties": {
                "browser_type": {"type": "string", "description": "Browser to launch: 'chrome' or 'firefox'", "default": "chrome"},
                "headless": {"type": "boolean", "description": "Run in headless mode", "default": False}
            }
        }
    },
    {
        "name": "close_browser",
        "description": "Close the browser and clean up resources",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "navigate_to",
        "description": "Navigate to a URL",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_current_url",
        "description": "Get the current page URL",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_page_title",
        "description": "Get the current page title",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "go_back",
        "description": "Navigate back in browser history",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "go_forward",
        "description": "Navigate forward in browser history",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "refresh_page",
        "description": "Refresh the current page",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "take_screenshot",
        "description": "Take a screenshot of the current page",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Optional filename for the screenshot"}
            }
        }
    },
    {
        "name": "click_element",
        "description": "Click on an element",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Element selector"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "type_text",
        "description": "Type text into an input field",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Element selector"},
                "text": {"type": "string", "description": "Text to type"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"},
                "clear_first": {"type": "boolean", "description": "Clear field before typing", "default": True}
            },
            "required": ["selector", "text"]
        }
    },
    {
        "name": "get_element_text",
        "description": "Get text content from an element",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Element selector"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "get_page_source",
        "description": "Get the full HTML source of the current page",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "check_element_exists",
        "description": "Check if an element exists on the page",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Element selector"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "wait_for_element",
        "description": "Wait for an element to appear on the page",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Element selector"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"},
                "timeout": {"type": "integer", "description": "Max seconds to wait", "default": 10}
            },
            "required": ["selector"]
        }
    },
    {
        "name": "submit_form",
        "description": "Submit a form element",
        "input_schema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "Form element selector"},
                "by_type": {"type": "string", "description": "Selector type: css, xpath, id, name, class", "default": "css"}
            },
            "required": ["selector"]
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
    """Execute a tool — local tools run in-process, browser tools call BrowserManager."""

    # --- V4 local tools ---
    if name == "read_file":
        try:
            with open(tool_input["path"], "r") as f:
                return f"Contents of {tool_input['path']}:\n{f.read()}"
        except Exception as e:
            return f"Error reading file: {e}"

    elif name == "write_file":
        try:
            with open(tool_input["path"], "w") as f:
                f.write(tool_input["content"])
            return f"✅ Successfully wrote to {tool_input['path']}"
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
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {e}"

    # --- Browser tools (direct BrowserManager calls) ---
    elif name == "launch_browser":
        return browser.launch_browser(
            tool_input.get("browser_type", "chrome"),
            tool_input.get("headless", False)
        )

    elif name == "close_browser":
        return browser.close_browser()

    elif name == "navigate_to":
        return browser.navigate_to(tool_input["url"])

    elif name == "get_current_url":
        return browser.get_current_url()

    elif name == "get_page_title":
        return browser.get_page_title()

    elif name == "go_back":
        return browser.go_back()

    elif name == "go_forward":
        return browser.go_forward()

    elif name == "refresh_page":
        return browser.refresh_page()

    elif name == "take_screenshot":
        return browser.take_screenshot(tool_input.get("filename"))

    elif name == "click_element":
        selector = tool_input["selector"]
        by_type = tool_input.get("by_type", "css")
        if not browser.driver:
            return "No browser is running. Launch browser first."
        element = browser.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        element.click()
        return f"Successfully clicked element: {selector}"

    elif name == "type_text":
        selector = tool_input["selector"]
        text = tool_input["text"]
        by_type = tool_input.get("by_type", "css")
        clear_first = tool_input.get("clear_first", True)
        if not browser.driver:
            return "No browser is running. Launch browser first."
        element = browser.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        if clear_first:
            element.clear()
        element.send_keys(text)
        return f"Successfully typed text into element: {selector}"

    elif name == "get_element_text":
        selector = tool_input["selector"]
        by_type = tool_input.get("by_type", "css")
        if not browser.driver:
            return "No browser is running. Launch browser first."
        element = browser.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        return element.text

    elif name == "get_page_source":
        if not browser.driver:
            return "No browser is running. Launch browser first."
        return browser.driver.page_source

    elif name == "check_element_exists":
        selector = tool_input["selector"]
        by_type = tool_input.get("by_type", "css")
        element = browser.find_element(selector, by_type)
        return f"Element exists: {element is not None}"

    elif name == "wait_for_element":
        selector = tool_input["selector"]
        by_type = tool_input.get("by_type", "css")
        timeout = tool_input.get("timeout", 10)
        result = browser.wait_for_element(selector, by_type, timeout)
        return f"Element found: {result}"

    elif name == "submit_form":
        selector = tool_input["selector"]
        by_type = tool_input.get("by_type", "css")
        if not browser.driver:
            return "No browser is running. Launch browser first."
        element = browser.find_element(selector, by_type)
        if not element:
            return f"Form not found: {selector}"
        element.submit()
        return f"Successfully submitted form: {selector}"

    return f"Unknown tool: {name}"

# ─── Agent Loop ──────────────────────────────────────────────────────────────

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

def agent_loop(user_message, conversation_history):
    """Run the agent loop until the task is complete."""
    conversation_history.append({"role": "user", "content": user_message})

    while True:
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
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
        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                print(f"\n🔧 {tool_name}: {json.dumps(tool_input)}")

                if not check_permission(tool_name, tool_input):
                    result = "Permission denied by user"
                    print(f"   ❌ {result}")
                else:
                    try:
                        result = execute_tool(tool_name, tool_input)
                        result = str(result) if result is not None else "(no output)"
                    except Exception as e:
                        result = f"Error: {e}"
                    display = result[:200] + "..." if len(result) > 200 else result
                    print(f"   → {display}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        conversation_history.append({"role": "user", "content": tool_results})

    return conversation_history

# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Agent V6 — Browser Automation (Direct, no MCP)")
    print("=" * 60)
    print()
    print(f"Browser tools: {sum(1 for t in TOOLS if t['name'] not in ('read_file','write_file','list_files','run_command'))} browser + 4 local")
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

        conversation_history = agent_loop(user_input, conversation_history)

    # Clean up browser on exit
    if browser.driver:
        print("🛑 Closing browser...")
        browser.close_browser()

if __name__ == "__main__":
    main()
