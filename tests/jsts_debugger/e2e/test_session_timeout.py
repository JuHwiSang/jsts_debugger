import pytest
import asyncio
from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
)
from jsts_debugger.lib.utils.command import is_script_finished_command

CODE_FOR_TIMEOUT_TEST = """
debugger; // Pause to keep the session alive
console.log('Resuming after delay...');
"""

pytestmark = pytest.mark.asyncio


async def test_session_persists_after_delay(mcp_server):
    """
    Tests that a session remains active and responsive after a period of inactivity.
    """
    # 1. Create a session that pauses immediately
    session_id, initial_events = await create_session_with_code(
        mcp_server, CODE_FOR_TIMEOUT_TEST
    )
    assert "error" not in initial_events, f"Session creation failed: {initial_events}"
    assert any(
        event.get("data", {}).get("method") == "Debugger.paused"
        for event in initial_events if event.get("type") == "event"
    ), "Execution did not pause as expected."

    # 2. Wait for 30 seconds to test session persistence
    # The debugger could potentially timeout and close inactive connections after a period,
    # so we wait to verify the session remains active and connected even after inactivity
    await asyncio.sleep(30)

    # 3. Resume execution to see if the session is still alive
    resume_result = await execute_commands(
        mcp_server, session_id, [("Debugger.resume", {})]
    )
    assert "error" not in resume_result, f"Resume command failed: {resume_result}"


    # 4. Verify that the script ran to completion
    execution_result = resume_result.get("execution_result", [])
    script_finished = any(
        is_script_finished_command(event.get("data", {}).get("method"))
        for event in execution_result
        if event.get("type") == "event"
    )
    assert (
        script_finished
    ), "Script did not finish after the delay, session might have timed out."

    # 5. Clean up
    await close_session(mcp_server, session_id)
