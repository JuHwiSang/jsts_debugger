import pytest

from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
    get_paused_call_frame_id,
)
from jsts_debugger.lib.utils.command import is_script_finished_command


pytestmark = pytest.mark.asyncio


async def test_set_skip_all_pauses(mcp_server):
    code = """
debugger;
console.log('A');
debugger;
console.log('B');
"""

    session_id, _ = await create_session_with_code(mcp_server, code)

    result = await execute_commands(
        mcp_server,
        session_id,
        [
            ("Debugger.setSkipAllPauses", {"skip": True}),
            ("Debugger.resume", {}),
        ],
    )

    events = result.get("execution_result", [])
    paused_found = any(
        r.get("type") == "event" and r.get("data", {}).get("method") == "Debugger.paused"
        for r in events
    )
    finished_found = any(
        r.get("type") == "event"
        and is_script_finished_command(r.get("data", {}).get("method", ""))
        for r in events
    )
    assert not paused_found, "Should not pause when skipAllPauses is enabled"
    assert finished_found, "Script did not finish with skipAllPauses enabled"

    await close_session(mcp_server, session_id)


async def test_remove_breakpoint(mcp_server):
    code = """
debugger;
console.log('line1');
console.log('line2');
console.log('line3');
"""

    session_id, _ = await create_session_with_code(mcp_server, code)

    # Set a breakpoint at line 1 (0-indexed) then remove it
    bp_set = await execute_commands(
        mcp_server,
        session_id,
        [("Debugger.setBreakpointByUrl", {"lineNumber": 1, "url": "file:///app/entrypoint.ts"})],
    )

    breakpoint_id = None
    for r in bp_set.get("execution_result", []):
        if r.get("type") == "command_result" and "breakpointId" in r.get("data", {}):
            breakpoint_id = r["data"]["breakpointId"]
            break
    assert breakpoint_id, "Failed to obtain breakpointId"

    # Remove and resume; should run to completion without pausing at that line
    result = await execute_commands(
        mcp_server,
        session_id,
        [
            ("Debugger.removeBreakpoint", {"breakpointId": breakpoint_id}),
            ("Debugger.resume", {}),
        ],
    )

    events = result.get("execution_result", [])
    paused_found = any(
        r.get("type") == "event" and r.get("data", {}).get("method") == "Debugger.paused"
        for r in events
    )
    finished_found = any(
        r.get("type") == "event"
        and is_script_finished_command(r.get("data", {}).get("method", ""))
        for r in events
    )
    assert not paused_found, "Should not pause after removing the breakpoint"
    assert finished_found, "Script did not finish after removing the breakpoint and resuming"

    await close_session(mcp_server, session_id)


async def test_runtime_evaluate_global(mcp_server):
    code = """
debugger;
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    eval_result = await execute_commands(
        mcp_server,
        session_id,
        [("Runtime.evaluate", {"expression": "1 + 2", "returnByValue": True})],
    )

    value_ok = False
    for r in eval_result.get("execution_result", []):
        if r.get("type") == "command_result":
            if r.get("data", {}).get("result", {}).get("value") == 3:
                value_ok = True
                break
    assert value_ok, "Runtime.evaluate did not return expected value"

    # Finish
    await execute_commands(mcp_server, session_id, [("Debugger.resume", {})])
    await close_session(mcp_server, session_id)


async def test_precise_coverage_smoke(mcp_server):
    code = """
debugger;
let x = 0;
x += 1;
x += 2;
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    # Start coverage while paused at start, step a couple lines, take coverage, stop, then finish
    # Step twice to execute increments while staying in paused cycles
    step_then_cov = await execute_commands(
        mcp_server,
        session_id,
        [
            ("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True}),
            ("Debugger.stepOver", {}),
            ("Debugger.stepOver", {}),
            ("Profiler.takePreciseCoverage", {}),
            ("Profiler.stopPreciseCoverage", {}),
        ],
    )

    got_coverage = False
    for r in step_then_cov.get("execution_result", []):
        if r.get("type") == "command_result" and isinstance(r.get("data"), dict):
            if "result" in r.get("data", {}) or "coverage" in r.get("data", {}):
                got_coverage = True
                break
    assert got_coverage, "Did not receive any precise coverage data/result"

    # Now finish
    finish = await execute_commands(mcp_server, session_id, [("Debugger.resume", {})])
    finished_found = any(
        r.get("type") == "event"
        and is_script_finished_command(r.get("data", {}).get("method", ""))
        for r in finish.get("execution_result", [])
    )
    assert finished_found, "Script did not finish after resuming"

    await close_session(mcp_server, session_id)


