# Building custom Python tools

This file is documentation for humans and coding agents. It is **not injected into any model prompt** by the bridge.

A user should be able to tell a coding AI something like:

> Build yourself a tool that checks disk space and make it usable through my AI Machine Bridge.

The AI should then read this file, create one `.py` file in the bridge's configured tools directory, test discovery, call the tool, and leave it ready to use. No bridge source edit or service restart is required.

## Where tools live

The installer creates a persistent tools directory and prints its path. The default is:

- Linux/macOS: `/opt/ai-machine-bridge/data/tools`
- Windows: `C:\ProgramData\ai-machine-bridge\data\tools`

The active path is also returned by authenticated `GET /health` as `tools_dir`.

Only top-level `*.py` files are discovered. Filenames beginning with `_` are ignored.

## Required Python contract

Every tool file must define exactly these public pieces:

```python
TOOL = {
    "name": "disk_space",
    "description": "Return disk usage for a requested filesystem path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Filesystem path to inspect. Defaults to /."
            }
        },
        "additionalProperties": False
    },
}


def run(arguments):
    path = arguments.get("path", "/")
    # Do the work and return a JSON-serializable value.
    return {"path": path}
```

Rules:

1. `TOOL` must be a dictionary.
2. `TOOL["name"]` must be unique and match `[A-Za-z][A-Za-z0-9_.-]{0,63}`.
3. `TOOL["description"]` must clearly state what the tool does.
4. `TOOL["input_schema"]` must be a JSON Schema object with top-level `"type": "object"`. Describe every argument well enough that another AI can use the tool without source-code knowledge.
5. `run(arguments)` must accept one dictionary and return a JSON-serializable value. `async def run(arguments)` is also supported.
6. A tool file is trusted host code. It runs with the same OS privileges as the bridge service. Do not install untrusted tool files.
7. Do not put secrets in the Python file. Read secrets from protected files or environment variables if the tool needs them.
8. Keep dependencies minimal. If a new Python package is needed, install it into the bridge virtual environment and document that dependency in a comment at the top of the tool file.

## Required build-and-test procedure for an AI

When a user asks you to build a tool:

1. Read this file and authenticated `GET /health` to learn `tools_dir`.
2. Inspect existing tools with authenticated `GET /custom-tools` so you do not reuse a name.
3. Create one `.py` file in `tools_dir` implementing the contract above.
4. Call `GET /custom-tools` again. The new tool must appear with no loader error.
5. Call it through `POST /custom-tools/call` using `{"name":"YOUR_TOOL","arguments":{...}}` and verify a real result.
6. If MCP is the user's client path, also call MCP `custom_tools`, then MCP `custom_tool_call` once.
7. If any test fails, fix the file and repeat. Do not tell the user the tool is ready until discovery and execution both succeed.

## Calling a finished tool

REST:

```text
GET  /custom-tools
POST /custom-tools/call
```

Example body:

```json
{
  "name": "disk_space",
  "arguments": {"path": "/"}
}
```

MCP exposes two built-ins:

- `custom_tools` — discovers installed custom tools and their input schemas.
- `custom_tool_call` — calls one by name with an arguments object.

The bridge rescans the directory on discovery and every call, so newly created or edited tools are usable immediately without restarting the server.
