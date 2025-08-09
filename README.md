# JSTS Debugger

**An MCP Server for Remotely Debugging Arbitrary JavaScript/TypeScript Repositories**

`jsts_debugger` provides a MCP (Model-Context Protocol) server for remotely debugging JavaScript and TypeScript projects using the Chrome DevTools Protocol (CDP). It uses Docker to run each debugging session in an isolated environment, ensuring safe and independent debugging.

## Key Features

- **Remote Debugging**: Debug any JavaScript/TypeScript project, whether local or remote.
- **Isolated Sessions**: Each debugging session runs in a separate Docker container, guaranteeing complete isolation.
- **CDP Command Support**: Directly execute commands from various CDP domains like `Debugger`, `Runtime`, and `Profiler` to control the debugging flow.
- **Simple to Use**: Perform all debugging tasks with three simple MCP tools: `create_session`, `execute_commands`, and `close_session`.
- **Dynamic Image Building**: Dynamically builds and caches Docker images tailored to the project and code being debugged for improved efficiency.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker

### Installation and Execution

1.  Clone the repository and install the project in editable mode. This will also install all dependencies.
    ```bash
    git clone https://github.com/example/jsts_debugger.git
    cd jsts_debugger
    pip install -e .
    ```

2.  Run the MCP server. You must pass the path to the project you want to debug as an argument.
    ```bash
    python -m scripts.mcp_server <path/to/your/js-ts-project>
    ```

## Programmatic Usage

You can also use `jsts_debugger` as a library. This allows you to start the server and interact with it from a client in your Python code, which is useful for automation and advanced integrations.

The following example shows how to run the server in a background thread and connect to it with a client.

```python
import asyncio
import threading
import time
from jsts_debugger import make_mcp_server
from fastmcp import Client

# --- Server Setup ---

# Path to the JS/TS project you want to debug
project_path = "/path/to/your/js-ts-project"

# Create the MCP server instance
# The server will run on http://localhost:8000 by default
mcp_server = make_mcp_server("jsts-debugger-programmatic", project_path)

# Run the server in a separate daemon thread
# FastMCP defaults to port 8000 for HTTP.
server_thread = threading.Thread(target=mcp_server.run, args=("localhost", 8000), daemon=True)
server_thread.start()
print("MCP Server starting on http://localhost:8000...")
time.sleep(2) # Give the server a moment to initialize

# --- Client Interaction ---

async def main():
    print("Connecting client to http://localhost:8000/mcp...")
    client = Client("http://localhost:8000/mcp")
    async with client:
        print("Client connected.")

        # Example: Create a debugging session
        code_to_debug = """
        console.log('Hello from the debugger!');
        debugger;
        const result = 1 + 2;
        console.log('Calculation done.');
        """
        response = await client.call_tool("create_session", {"code": code_to_debug})
        data = response.data
        session_id = data['session_id']
        print(f"Session created: {session_id}")
        print("Initial events:", data['execution_result'])

        # Example: Resume execution
        print("\\nResuming execution...")
        response = await client.call_tool("execute_commands", {
            "session_id": session_id,
            "commands": [("Debugger.resume", {})]
        })
        print("Execution result after resume:", response.data['execution_result'])

        # Example: Close the session
        await client.call_tool("close_session", {"session_id": session_id})
        print(f"\\nSession {session_id} closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Client finished.")
    # The main thread exits, and the daemon server thread is terminated automatically.
```

## MCP Tool API

`jsts_debugger` provides three MCP tools.

### 1. `create_session`

Creates a new debugging session. The provided code is written to the `/app/entrypoint.ts` file in an isolated Docker container and executed immediately.

-   **Parameters**:
    -   `code` (str): The TypeScript/JavaScript code to execute.
    -   `timeout` (int, optional): Timeout for CDP responses (default: 30 seconds).
-   **Returns**:
    -   `session_id` (str): A unique ID for the created session.
    -   `execution_result` (list): A list of events that occurred until the execution paused or terminated.

**Important**: Execution starts immediately. To pause and inspect the state, you must include at least one `debugger;` statement in your code or set a breakpoint using `execute_commands` after the session is created.

### 2. `execute_commands`

Executes one or more CDP commands in an existing session.

-   **Parameters**:
    -   `session_id` (str): The ID of the target session.
    -   `commands` (list): A list of commands in the format `[("method", {"param1": "value1"})]`.
-   **Returns**:
    -   `execution_result` (list): A time-ordered, flattened list of command results and events. Each item has a `type` field (`command_result` or `event`).

#### Supported Commands

A wide range of CDP commands are supported. For a full list and detailed parameters for each command, refer to the `execute_commands` tool description in `src/mcp.py`. Key commands include:

-   `Debugger.resume`
-   `Debugger.stepOver`
-   `Debugger.stepInto`
-   `Debugger.stepOut`
-   `Debugger.setBreakpointByUrl`
-   `Debugger.evaluateOnCallFrame`
-   `Runtime.evaluate`
-   `Runtime.getProperties`
-   `Runtime.callFunctionOn`
-   ... and many more.

#### Example: Inspecting a variable at a breakpoint

```python
# 1. Create a session (with 'debugger;' in the code)
session_id, _ = create_session_with_code(mcp_server, """
    const x = 10;
    const y = 20;
    debugger;
    console.log(x + y);
""")

# Get the callFrameId from the paused state at 'debugger;'
call_frame_id = get_paused_call_frame_id(...)

# 2. Use execute_commands to check the value of variable x
result = execute_commands(mcp_server, session_id, [
    ("Debugger.evaluateOnCallFrame", {
        "expression": "x",
        "callFrameId": call_frame_id,
        "returnByValue": True
    })
])
# You can find "value": 10 in the result

# 3. Resume execution
execute_commands(mcp_server, session_id, [("Debugger.resume", {})])

# 4. Close the session
close_session(mcp_server, session_id)
```

### 3. `close_session`

Closes an active debugging session and cleans up associated resources (like the Docker container).

-   **Parameters**:
    -   `session_id` (str): The ID of the session to close.
-   **Returns**:
    -   `status` (str): A status message for the session closure.

## Container Environment

-   When a session is created, the specified project is copied to the `/app/{project_name}` path inside the container.
-   The `code` passed to the `create_session` call is saved to `/app/entrypoint.ts` and executed.
-   A basic `package.json` and `tsconfig.json` are provided and can be merged with your project's configuration files if needed.
