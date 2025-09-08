import pytest

from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
    get_paused_call_frame_id,
)
from jsts_debugger.lib.utils.command import is_script_finished_command


pytestmark = pytest.mark.asyncio


async def test_pause_on_exceptions(mcp_server):
    code = """
function g(){ throw new Error('boom'); }
debugger;
g();
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    # Enable pause on all exceptions, then resume to hit the throw site
    paused_result = await execute_commands(
        mcp_server,
        session_id,
        [
            {"method": "Debugger.setPauseOnExceptions", "params": {"state": "uncaught"}},
            {"method": "Debugger.resume", "params": {}},
        ],
    )

    paused_event_found = False
    for result in paused_result["execution_result"]:
        if result.get("type") == "event":
            event = result.get("data", {})
            if event.get("method") == "Debugger.paused":
                reason = event.get("params", {}).get("reason")
                if reason == "promiseRejection":
                    paused_event_found = True
                    break
    assert paused_event_found, "Did not pause on exception as expected"

    finish_result = await execute_commands(
        mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}]
    )

    detached_event_found = any(
        r.get("type") == "event"
        and is_script_finished_command(r.get("data", {}).get("method", ""))
        for r in finish_result["execution_result"]
    )
    assert detached_event_found, "Script did not finish after resuming from exception pause"

    await close_session(mcp_server, session_id)


async def test_get_script_source(mcp_server):
    code = """
function foo(){ return 42; }
debugger;
foo();
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    # Find a paused event from the first 'debugger;' pause to extract scriptId
    script_id = None
    for result in initial_events:  # type: ignore[assignment]
        if result.get("type") == "event":
            event = result.get("data", {})
            if event.get("method") == "Debugger.paused":
                call_frames = event.get("params", {}).get("callFrames", [])
                if call_frames:
                    script_id = call_frames[0].get("location", {}).get("scriptId")
                    break
    assert script_id, "Could not find scriptId from initial paused event"

    # Retrieve source
    src_result = await execute_commands(
        mcp_server,
        session_id,
        [{"method": "Debugger.getScriptSource", "params": {"scriptId": script_id}}],
    )

    found_source = False
    for r in src_result.get("execution_result", []):
        if r.get("type") == "command_result":
            src = r.get("data", {}).get("scriptSource", "")
            if "function foo()" in src:
                found_source = True
                break
    assert found_source, "Script source did not contain expected function"

    # Clean up: run to end
    await execute_commands(mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}])
    await close_session(mcp_server, session_id)


async def test_set_breakpoint_on_function_call(mcp_server):
    code = """
function foo(x){ return x + 1; }
debugger;
foo(1);
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    # Already paused at 'debugger;'
    call_frame_id = await get_paused_call_frame_id(initial_events)  # type: ignore[arg-type]
    
    # Evaluate foo to get its objectId
    eval_result = await execute_commands(
        mcp_server,
        session_id,
        [{"method": "Debugger.evaluateOnCallFrame", "params": {"expression": "foo", "callFrameId": call_frame_id}}],
    )

    function_id = None
    for r in eval_result.get("execution_result", []):
        if r.get("type") == "command_result":
            d = r.get("data", {})
            if d.get("result", {}).get("type") == "function":
                function_id = d["result"].get("objectId")
                break
    assert function_id, "Could not obtain function objectId for foo"

    # Set breakpoint on function call and resume to hit it
    hit_call_bp = await execute_commands(
        mcp_server,
        session_id,
        [
            {"method": "Debugger.setBreakpointOnFunctionCall", "params": {"objectId": function_id}},
            {"method": "Debugger.resume", "params": {}},
        ],
    )

    paused_found = any(
        r.get("type") == "event" and r.get("data", {}).get("method") == "Debugger.paused"
        for r in hit_call_bp.get("execution_result", [])
    )
    assert paused_found, "Did not pause on function call breakpoint"

    # Finish execution
    finish_result = await execute_commands(mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}])
    detached_event_found = any(
        r.get("type") == "event"
        and is_script_finished_command(r.get("data", {}).get("method", ""))
        for r in finish_result.get("execution_result", [])
    )
    assert detached_event_found, "Script did not finish after resuming"

    await close_session(mcp_server, session_id)


async def test_call_function_on_object(mcp_server):
    code = """
const obj = { a: 1, b: 2 };
debugger;
"""

    session_id, initial_events = await create_session_with_code(mcp_server, code)

    call_frame_id = await get_paused_call_frame_id(initial_events)  # type: ignore[arg-type]
    
    # Evaluate obj to get its objectId
    eval_obj = await execute_commands(
        mcp_server,
        session_id,
        [{"method": "Debugger.evaluateOnCallFrame", "params": {"expression": "obj", "callFrameId": call_frame_id}}],
    )

    object_id = None
    for r in eval_obj.get("execution_result", []):
        if r.get("type") == "command_result":
            d = r.get("data", {})
            if d.get("result", {}).get("type") == "object":
                object_id = d["result"].get("objectId")
                break
    assert object_id, "Could not find objectId for obj"

    # Call function on the object to compute a + b
    call_fn = await execute_commands(
        mcp_server,
        session_id,
        [
            {
                "method": "Runtime.callFunctionOn",
                "params": {
                    "objectId": object_id,
                    "functionDeclaration": "function(){ return this.a + this.b; }",
                    "returnByValue": True,
                },
            }
        ],
    )

    got_sum = False
    for r in call_fn.get("execution_result", []):
        if r.get("type") == "command_result":
            if r.get("data", {}).get("result", {}).get("value") == 3:
                got_sum = True
                break
    assert got_sum, "callFunctionOn did not return expected sum"

    # Finish
    await execute_commands(mcp_server, session_id, [{"method": "Debugger.resume", "params": {}}])
    await close_session(mcp_server, session_id)


async def test_multiple_sessions_independent(mcp_server):
    code1 = """
debugger;
console.log('S1');
"""
    code2 = """
debugger;
console.log('S2');
"""

    session1, _ = await create_session_with_code(mcp_server, code1)
    session2, _ = await create_session_with_code(mcp_server, code2)

    # Resume both sessions to completion
    r1 = await execute_commands(mcp_server, session1, [{"method": "Debugger.resume", "params": {}}])
    r2 = await execute_commands(mcp_server, session2, [{"method": "Debugger.resume", "params": {}}])

    def finished(result):
        return any(
            x.get("type") == "event"
            and is_script_finished_command(x.get("data", {}).get("method", ""))
            for x in result["execution_result"]
        )

    assert finished(r1), "Session 1 did not finish"
    assert finished(r2), "Session 2 did not finish"

    await close_session(mcp_server, session1)
    await close_session(mcp_server, session2)


