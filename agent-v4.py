#!/usr/bin/env python3
# mini-claude-code.py - A minimal Claude Code clone

import anthropic
import subprocess
import os
import json

with open("/Users/satishkumar/.hc/anthropic.key", "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

TOOLS = [
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

def execute_tool(name, tool_input):
    """Execute a tool and return the result."""
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

def agent_loop(user_message, conversation_history):
    """Run the agent loop until the task is complete."""
    conversation_history.append({"role": "user", "content": user_message})

    while True:
        # Call Claude
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=4096,
            system=f"You are a helpful coding assistant. Working directory: {os.getcwd()}",
            tools=TOOLS,
            messages=conversation_history
        )

        # Add assistant response to history
        conversation_history.append({"role": "assistant", "content": response.content})

        # Check if we're done (no tool use)
        if response.stop_reason == "end_turn":
            # Print the final text response
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

                # Check permissions
                if not check_permission(tool_name, tool_input):
                    result = "Permission denied by user"
                    print(f"   ❌ {result}")
                else:
                    result = execute_tool(tool_name, tool_input)
                    # Truncate long output for display
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

def main():
    print("My Mini Agent that manages files and directories in my system")
    print(" Type your requests, or 'quit' to exit.\n")

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

if __name__ == "__main__":
    main()