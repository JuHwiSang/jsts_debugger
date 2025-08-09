from typing import Any, Dict, List, Optional, Tuple
from fastmcp import FastMCP, Client
import pytest

CODE_WITH_BREAKPOINT = """
import { main } from 'test-project';

async function run() {
    await main();
}

run();
"""


async def create_session_with_code(
    mcp_server: FastMCP,
    code: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Creates a session (execution starts immediately) and returns the session ID and initial events up to first pause or termination."""
    client = Client(mcp_server)
    async with client:
        create_result = await client.call_tool(
            "create_session", {"code": code}
        )

    data = create_result.data
    if "error" in data:
        pytest.fail(
            f"Failed to create session: {data.get('error')}\\n{data.get('stack_trace')}"
        )

    assert "session_id" in data
    assert "execution_result" in data
    return data["session_id"], data["execution_result"]


async def execute_commands(
    mcp_server: FastMCP, session_id: str, commands: List[Tuple[str, Dict[str, Any]]]
) -> Dict[str, Any]:
    """Executes commands and returns the result."""
    client = Client(mcp_server)
    async with client:
        execute_result = await client.call_tool(
            "execute_commands", {"session_id": session_id, "commands": commands}
        )

    data = execute_result.data
    if "error" in data:
        pytest.fail(
            f"Failed to execute commands: {data.get('error')}\\n{data.get('stack_trace')}"
        )

    return data


async def close_session(mcp_server: FastMCP, session_id: str):
    """Closes a session."""
    client = Client(mcp_server)
    async with client:
        close_result = await client.call_tool(
            "close_session", {"session_id": session_id}
        )

    data = close_result.data
    if "error" in data:
        pytest.fail(
            f"Failed to close session: {data.get('error')}\\n{data.get('stack_trace')}"
        )

    assert data.get("status") == f"Session {session_id} closed."


async def get_paused_call_frame_id(results: List[Dict[str, Any]]) -> str:
    """Finds the call frame ID from a list of debugger events."""
    for result in results:
        if result.get("type") == "event":
            event = result.get("data", {})
            if event.get("method") == "Debugger.paused":
                call_frames = event.get("params", {}).get("callFrames", [])
                if call_frames:
                    return call_frames[0].get("callFrameId")
    pytest.fail("Could not find a paused event with a call frame ID.")
