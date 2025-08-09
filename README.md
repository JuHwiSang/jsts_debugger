# JSTS Debugger

> [!WARNING]
> This project is in a very early and unstable stage of development. Please use it with caution.

**An MCP Server that Provides an Interface for LLMs to Remotely Debug JavaScript/TypeScript Repositories**

`jsts_debugger` provides a MCP (Model-Context Protocol) server that enables a Large Language Model (LLM) to debug JavaScript and TypeScript projects. It uses the Chrome DevTools Protocol (CDP) for debugging and runs each session in an isolated Docker container, ensuring safe and independent operation.

## Key Features

- **LLM-Centric Debugging**: Provides a high-level MCP interface for LLMs to control the debugging process.
- **Isolated Sessions**: Each debugging session runs in a separate Docker container, guaranteeing complete isolation.
- **CDP Command Support**: Directly execute commands from various CDP domains like `Debugger`, `Runtime`, and `Profiler` to control the debugging flow.
- **Simple Toolset**: Perform all debugging tasks with three simple MCP tools: `create_session`, `execute_commands`, and `close_session`.

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

You can also use `jsts_debugger` as a library.

### 1. Starting the Server

The following example shows how to run the server in a background thread.

```python
from jsts_debugger import make_mcp_server

# Path to the JS/TS project you want to debug
project_path = "/path/to/your/js-ts-project"

# Create the MCP server instance
mcp_server = make_mcp_server("jsts-debugger-server", project_path)

# Run the server
mcp_server.run(transport="http", host="127.0.0.1", port=8000)
```

### 2. Connecting a Client and Debugging

Once the server is running, you can connect to it with a client to start debugging. Note that in most cases, this connection and debugging process will be handled by an LLM rather than direct user interaction.

```python
import asyncio
from fastmcp import Client

# Client connects to the running server's MCP endpoint
client = Client("http://127.0.0.1:8000/mcp")

async def debug_session():
    async with client:
        # The code below demonstrates a simple debugging scenario.
        # It logs a message, pauses execution with a `debugger` statement,
        # performs a simple calculation, and then logs a final message.
        code_to_debug = """
        console.log('Hello from the debugger!');
        debugger; // Pause execution
        const result = 1 + 2;
        console.log('Calculation done.');
        """
        
        # 1. Create a session
        response = await client.call_tool("create_session", {"code": code_to_debug})
        session_id = response.data['session_id']
        # 'initial_events' contains all events up to the first pause
        # At this point, initial_events contains the console message
        # "Hello from the debugger!" and the pause event from the debugger statement
        initial_events = response.data['execution_result']

        # 2. Resume execution
        response = await client.call_tool(
            "execute_commands",
            {
                "session_id": session_id,
                "commands": [("Debugger.resume", {})]
            }
        )
        # 'execution_result' contains events after resuming
        # At this point, execution_result contains the console message
        # "Calculation done." and the execution context destroyed event
        execution_result = response.data['execution_result']

        # 3. Close the session
        await client.call_tool("close_session", {"session_id": session_id})

# Run the async debugging logic
asyncio.run(debug_session())
```

## MCP Tool API

`jsts_debugger` provides three MCP tools.

### 1. `create_session`

Creates a new debugging session. The provided code is written to the `/app/entrypoint.ts` file and executed immediately. The primary purpose of the `code` parameter is to import and run specific parts of the project (e.g., a function or a class method) that you want to debug.

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

A wide range of CDP commands are supported. For a full list and detailed parameters for each command, refer to the `execute_commands` tool description in `jsts_debugger/mcp.py`. Key commands include:

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