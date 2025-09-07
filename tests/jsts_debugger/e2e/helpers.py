from typing import Any, Dict, List, Optional, Tuple, cast
from fastmcp import FastMCP, Client
import pytest
from jsts_debugger.debugger import CDPItem

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

    sc = create_result.structured_content
    if sc is None:
        pytest.fail("create_session returned no structured_content")
    data = cast(Dict[str, Any], sc)
    print('data', data)
    if not data.get("success"):
        pytest.fail(
            f"Failed to create session: {data.get('error')}\n{data.get('stack_trace')}"
        )

    assert data and data.get("session_id") is not None
    return data["session_id"], data.get("execution_result", [])


async def execute_commands(
    mcp_server: FastMCP, session_id: str, commands: List[Tuple[str, Dict[str, Any]]]
):
    """Executes commands and returns the result dict (structured_data)."""
    client = Client(mcp_server)
    async with client:
        execute_result = await client.call_tool(
            "execute_commands", {"session_id": session_id, "commands": commands}
        )

    sc = execute_result.structured_content
    if sc is None:
        pytest.fail("execute_commands returned no structured_content")
    data = cast(Dict[str, Any], sc)
    if not data.get("success"):
        pytest.fail(
            f"Failed to execute commands: {data.get('error')}\n{data.get('stack_trace')}"
        )

    return {
        "execution_result": data.get("execution_result", []),
        "success": bool(data.get("success")),
    }


async def close_session(mcp_server: FastMCP, session_id: str):
    """Closes a session."""
    client = Client(mcp_server)
    async with client:
        close_result = await client.call_tool(
            "close_session", {"session_id": session_id}
        )

    sc = close_result.structured_content
    if sc is None:
        pytest.fail("close_session returned no structured_content")
    data = cast(Dict[str, Any], sc)
    if not data.get("success"):
        pytest.fail(
            f"Failed to close session: {data.get('error')}\n{data.get('stack_trace')}"
        )

    assert data and data.get("status") == f"Session {session_id} closed."


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
