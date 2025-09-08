import pytest
from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
)
from jsts_debugger.lib.utils.command import is_script_finished_command

CODE_FOR_BREAKPOINT = """
let i = 0;
debugger;
i++;
i++;
console.log('Done');
"""

pytestmark = pytest.mark.asyncio

async def test_set_breakpoint_and_resume(mcp_server):
    """
    Tests setting a breakpoint, running to it, and then finishing.
    """
    session_id, _ = await create_session_with_code(mcp_server, CODE_FOR_BREAKPOINT)

    # Set a breakpoint on the first `i++` (line 2, 0-indexed)
    breakpoint_result = await execute_commands(
        mcp_server,
        session_id,
        [
            {
                "method": "Debugger.setBreakpointByUrl",
                "params": {"lineNumber": 2, "url": "file:///app/entrypoint.ts"},
            }
        ],
    )
    
    # Check for the breakpointId in the command result
    result_list = breakpoint_result.get("execution_result", [])
    breakpoint_set = False
    for result in result_list:
        if result.get("type") == "command_result":
            if "breakpointId" in result.get("data", {}):
                breakpoint_set = True
                break
    assert breakpoint_set, "Did not find breakpointId in the result"

    # Resume execution to hit the breakpoint
    paused_result = await execute_commands(
        mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}]
    )

    # Check that we paused at the correct line by looking for a 'Debugger.paused' event
    paused_event_found = False
    for result in paused_result.get("execution_result", []):
        if result.get("type") == "event":
            event_data = result.get("data", {})
            if event_data.get("method") == "Debugger.paused":
                hit_breakpoints = event_data.get("params", {}).get("hitBreakpoints", [])
                if hit_breakpoints:
                    paused_event_found = True
                    break
    assert paused_event_found, "Execution did not pause at the breakpoint."

    # Resume again to finish execution
    final_result = await execute_commands(
        mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}]
    )

    # Check for script finishing by looking for an 'Inspector.detached' event
    detached_event_found = False
    for result in final_result.get("execution_result", []):
        if result.get("type") == "event":
            event_data = result.get("data", {})
            if is_script_finished_command(event_data.get("method", "")):
                detached_event_found = True
                break
    assert detached_event_found, "Script did not finish after resuming from breakpoint."

    await close_session(mcp_server, session_id)

