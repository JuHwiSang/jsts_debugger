import pytest
from tests.jsts_debugger.e2e.helpers import (
    create_session_with_code,
    execute_commands,
    close_session,
    get_paused_call_frame_id,
)

CODE_FOR_PROPERTIES = """
const myObject = { a: 1, b: 'hello' };
debugger;
"""

pytestmark = pytest.mark.asyncio

async def test_get_properties(mcp_server):
    """
    Tests getting properties of an object.
    """
    session_id, initial_events = await create_session_with_code(mcp_server, CODE_FOR_PROPERTIES)

    # The code has a `debugger;` statement, so it should be paused.
    # We can get the callFrameId directly from the initial events.
    call_frame_id = await get_paused_call_frame_id(initial_events)  # type: ignore[arg-type]

    # First, evaluate 'myObject' to get its objectId
    eval_result = await execute_commands(
        mcp_server,
        session_id,
        [
            (
                "Debugger.evaluateOnCallFrame",
                {"expression": "myObject", "callFrameId": call_frame_id},
            )
        ],
    )

    object_id = None
    for result in eval_result.get("execution_result", []):
        if result.get("type") == "command_result":
            result_data = result.get("data", {})
            if result_data.get("result", {}).get("type") == "object":
                object_id = result_data["result"].get("objectId")
                break
    
    assert object_id, "Could not find the objectId for 'myObject'"

    # Now, get the properties of the object
    properties_result = await execute_commands(
        mcp_server, session_id, [("Runtime.getProperties", {"objectId": object_id})]
    )

    # Check the properties
    properties_found = False
    for result in properties_result.get("execution_result", []):
        if result.get("type") == "command_result":
            props_data = result.get("data", {}).get("result", [])
            prop_names = {p["name"] for p in props_data}
            if "a" in prop_names and "b" in prop_names:
                properties_found = True
                break

    assert properties_found, "Did not find the expected properties for 'myObject'"

    # Clean up
    await execute_commands(mcp_server, session_id, [("Debugger.resume", {})])
    await close_session(mcp_server, session_id)
