#!/usr/bin/env python3
# agent-v1.py - Simple agent with a loop (bash commands only, no permission checks)
#
# Python conversion of agent-v1.sh
# Takes a single task from the command line and runs it to completion.

import anthropic
import subprocess
import json
import sys

with open("/Users/satishkumar/.hc/anthropic.key", "r") as f:
    api_key = f.read().strip()
client = anthropic.Anthropic(api_key=api_key)

SYSTEM_PROMPT = """You are a helpful assistant that can run bash commands.

When the user gives you a task, respond with JSON in this exact format:
{"action": "bash", "command": "your command here"}

When the task is complete, respond with:
{"action": "done", "message": "explanation of what was accomplished"}

Only respond with JSON. No other text."""

def run_agent(task):
    """Main agent loop — sends task to Claude and executes bash commands."""
    messages = [{"role": "user", "content": task}]

    while True:
        # Call Claude
        response = client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        # Extract the text response
        ai_text = response.content[0].text

        # Add assistant message to history
        messages.append({"role": "assistant", "content": ai_text})

        # Parse the JSON action
        try:
            action_data = json.loads(ai_text)
            action = action_data.get("action")
        except json.JSONDecodeError:
            print(f"❌ Could not parse response: {ai_text}")
            break

        if action == "done":
            print(f"✅ {action_data.get('message', 'Done')}")
            break

        elif action == "bash":
            command = action_data["command"]
            print(f"🔧 Running: {command}")

            # Execute and capture output (no permission check)
            output = subprocess.run(command, shell=True, capture_output=True, text=True)
            result = output.stdout + output.stderr
            print(result)

            # Feed result back to Claude
            messages.append({"role": "user", "content": f"Command output: {result}"})

        else:
            print(f"❌ Unknown action: {action}")
            break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agent-v1.py 'your task here'")
        sys.exit(1)
    run_agent(sys.argv[1])
