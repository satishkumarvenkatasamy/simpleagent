# agent-v3.py - Agent with structured tools
import anthropic
import json
import os

with open("/Users/satishkumar/anthropic.key", "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

SEARCH_TOOLS = [
    {
        "name": "glob",
        "description": "Find files matching a pattern",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"}
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "grep",
        "description": "Search for a pattern in files",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search in"}
            },
            "required": ["pattern"]
        }
    }
]

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
        "description": "Write content to a file",
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
        "name": "run_bash",
        "description": "Run a bash command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "edit_file",
        "description": "Make a precise edit to a file by replacing a unique string",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "old_str": {"type": "string", "description": "Exact string to find (must be unique in file)"},
                "new_str": {"type": "string", "description": "String to replace it with"}
            },
            "required": ["path", "old_str", "new_str"]
        }
    }
]

def compact_conversation(messages):
    """Summarize the conversation to free up context."""
    summary_prompt = """Summarize this conversation concisely, preserving:
    - The original task
    - Key findings and decisions
    - Current state of the work
    - What still needs to be done"""
    
    summary = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=2000,
        messages=[
            {"role": "user", "content": f"{messages}\n\n{summary_prompt}"}
        ]
    )
    
    return [{"role": "user", "content": f"Previous work summary:\n{summary}"}]


def edit_file(path, old_str, new_str):
    with open(path, "r") as f:
        content = f.read()
    
    # Ensure the string is unique
    count = content.count(old_str)
    if count == 0:
        return f"Error: '{old_str}' not found in file"
    if count > 1:
        return f"Error: '{old_str}' found {count} times. Must be unique."
    
    new_content = content.replace(old_str, new_str)
    with open(path, "w") as f:
        f.write(new_content)
    
    return f"Successfully replaced text in {path} with {new_str}"

def execute_tool(name, input):
    """Execute a tool and return the result."""
    if name == "read_file":
        try:
            with open(input["path"], "r") as f:
                return f.read()
        except Exception as e:
            return f"Error: {e}"
    
    elif name == "write_file":
        try:
            with open(input["path"], "w") as f:
                f.write(input["content"])
            return f"Successfully wrote to {input['path']}"
        except Exception as e:
            return f"Error: {e}"
    
    elif name == "run_bash":
        import subprocess
        result = subprocess.run(
            input["command"], 
            shell=True, 
            capture_output=True, 
            text=True
        )
        return result.stdout + result.stderr

def run_agent(task):
    """Main agent loop."""
    messages = [{"role": "user", "content": task}]
    
    while True:
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages
        )
        
        # Check if we're done
        if response.stop_reason == "end_turn":
            # Extract final text response
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"✅ {block.text}")
            break
        
        # Process tool uses
        if response.stop_reason == "tool_use":
            # Add assistant's response to history
            messages.append({"role": "assistant", "content": response.content})
            
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"🔧 {block.name}: {json.dumps(block.input)}")
                    result = execute_tool(block.name, block.input)
                    print(f"   → {result[:200]}...")  # Truncate for display
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })
            
            # Add results to conversation
            messages.append({"role": "user", "content": tool_results})

if __name__ == "__main__":
    import sys
    run_agent(sys.argv[1])