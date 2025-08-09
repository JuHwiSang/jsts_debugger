import pytest
from tests.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
    get_paused_call_frame_id,
    CODE_WITH_BREAKPOINT,
)

pytestmark = pytest.mark.asyncio

async def test_evaluate_expression_in_session(mcp_server):
    """
    Tests creating a session and evaluating an expression.
    """
    session_id, _ = await create_session_with_code(
        mcp_server,
        CODE_WITH_BREAKPOINT,
    )

    # The debugger should be paused at the `debugger;` statement.
    # Let's step over a few times to get into the function.
    step_result = await execute_commands(
        mcp_server, session_id, [("Debugger.stepOver", {})] * 5
    )

    call_frame_id = await get_paused_call_frame_id(step_result["execution_result"])

    # Now evaluate 'a + b' and resume
    eval_result = await execute_commands(
        mcp_server,
        session_id,
        [
            ("Debugger.evaluateOnCallFrame", {"expression": "a + b", "callFrameId": call_frame_id}),
            ("Debugger.resume", {}),
        ],
    )

    # Find the evaluation result in the results
    evaluation_result_found = False
    for result in eval_result["execution_result"]:
        if result.get("type") == "command_result":
            result_data = result.get("data", {})
            # The actual evaluation result is nested inside the 'result' key
            if result_data.get("result", {}).get("value") == 3:
                evaluation_result_found = True
                break
    
    assert evaluation_result_found, "Did not find the correct evaluation result for 'a + b'"

    await close_session(mcp_server, session_id)
