import pytest
from jsts_debugger.lib.utils.command import is_script_finished_command
from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
    CODE_WITH_BREAKPOINT,
)

pytestmark = pytest.mark.asyncio

async def test_create_session_and_execute_commands(mcp_server):
    """
    Tests creating a session, executing a simple command, and closing the session.
    """
    session_id, _ = await create_session_with_code(mcp_server, CODE_WITH_BREAKPOINT)

    # There are `debugger;` statements in the code, so the debugger should pause. Resume execution.
    await execute_commands(
        mcp_server, session_id, [("Debugger.resume", {})]
    )
    
    # After the first resume, there's another `debugger;` statement. Resume again.
    execution_result = await execute_commands(
        mcp_server, session_id, [("Debugger.resume", {})]
    )

    # Check for Inspector.detached event, indicating the script finished
    events = execution_result.get("execution_result", [])
    detached_event_found = False
    for result in events:
        if result.get("type") == "event":
            event_data = result.get("data", {})
            if is_script_finished_command(event_data.get("method")):
                detached_event_found = True
                break
    assert detached_event_found, "Script did not finish as expected."

    await close_session(mcp_server, session_id)
