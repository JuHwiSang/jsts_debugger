import pytest
import threading
import time
import asyncio
from jsts_debugger import make_mcp_server
from fastmcp import Client
from jsts_debugger.lib.utils.command import is_script_finished_command

pytestmark = pytest.mark.asyncio

async def test_readme_programmatic_usage_example(test_project):
    """
    Tests the programmatic usage example from README.md.
    It verifies that the server can be started, a session created,
    commands executed, and the session closed, all from a Python script
    interacting with the server over HTTP.
    """
    # --- Server Setup ---
    # Use a different port to avoid conflicts with other tests
    test_port = 8001 
    mcp_server = make_mcp_server("jsts-debugger-readme-test", test_project)
    
    def run_server():
        mcp_server.run(transport="streamable-http", host="127.0.0.1", port=test_port, path="/mcp")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2) # Give the server a moment to start

    # --- Client Interaction ---
    client = Client(f"http://127.0.0.1:{test_port}/mcp")
    async with client:
        # 1. Create a debugging session
        code_to_debug = """
        console.log('Hello from the debugger!');
        debugger; // Pause execution
        const result = 1 + 2;
        console.log('Calculation done.');
        """
        create_response = await client.call_tool("create_session", {"code": code_to_debug})
        
        data = create_response.structured_content or {}
        assert data.get("success"), f"Failed to create session: {data.get('error')}"
        session_id = data.get("session_id")
        assert session_id is not None
        
        # Verify that we are paused
        initial_events = data.get('execution_result', [])
        print('initial_events', initial_events)
        assert any(
            event.get("data", {}).get("method") == "Debugger.paused"
            for event in initial_events if event.get("type") == "event"
        ), "Execution did not pause at the 'debugger;' statement."

        # 2. Resume execution and run to completion
        resume_response = await client.call_tool("execute_commands", {
            "session_id": session_id,
            "commands": [("Debugger.resume", {})]
        })
        
        data = resume_response.structured_content or {}
        assert data.get("success"), f"Failed to execute resume: {data.get('error')}"
        
        # Verify that the script finished
        execution_result = data.get('execution_result', [])
        assert any(
            is_script_finished_command(event.get("data", {}).get("method", ""))
            for event in execution_result if event.get("type") == "event"
        ), "Script did not finish after resuming."

        # 3. Close the session
        close_response = await client.call_tool("close_session", {"session_id": session_id})
        data = close_response.structured_content or {}
        assert data.get("success"), f"Failed to close session: {data.get('error')}"
        assert data.get("status") == f"Session {session_id} closed."
