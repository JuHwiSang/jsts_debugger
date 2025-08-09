from fastmcp import FastMCP
import json

from src.config import AllowedDebuggerCommand, allowed_debugger_commands
from src.debugger import JSTSDebugger
from typing import Any, Optional, Dict, List
import traceback
import re
from src.helpers import get_package_name
from src.lib.utils.remove_tabs import remove_tabs


def make_mcp_server(name: str, project_path: str) -> FastMCP:
    mcp = FastMCP(name=name, instructions=remove_tabs("""
                  Debug JavaScript/TypeScript repository via the Chrome DevTools Protocol (CDP).
                  1) Create a session with your entrypoint code. Execution starts immediately.
                  2) Use 'debugger;' in your code (at least once) to pause and inspect.
                  3) Execute CDP commands (set breakpoints, step, evaluate, etc.) against that session.
                  """))
    debugger = JSTSDebugger()

    @mcp.tool(
        description=remove_tabs(f"""
            Create a new debugging session in an isolated Docker container.
            The provided code is written to /app/entrypoint.ts and executed with Node (tsx).
            Returns 'session_id' and 'execution_result' (events up to the first pause or termination).

            Important:
            - Execution starts immediately. Include at least one 'debugger;' statement or a breakpoint to pause.
            - After creation, call 'execute_commands' to drive the session (step, evaluate, resume, etc.).

            On creation, core domains are enabled automatically (Runtime, Debugger, HeapProfiler, Profiler, Network).

            Options:
            - timeout (seconds, default 30)

            You can set breakpoints under /app/{get_package_name(project_path)}/... to debug project files.
            If your code needs additional packages at runtime, spawn installation commands via child_process (e.g., npm install).
            Each session runs in its own container.

            Container layout:
            /app
                /entrypoint.ts
                /package.json
                /tsconfig.json
                /{get_package_name(project_path)}
                    /...

            package.json: ```json
            {{
            "name": "universal-tsx-runner",
            "private": true,
            "type": "module"
            }}
            ```

            tsconfig.json: ```json
            {{
            "compilerOptions": {{
                "module": "NodeNext",
                "moduleResolution": "NodeNext",
                "target": "ES2022",
                "lib": ["ES2022"],
                "skipLibCheck": true,
                "allowSyntheticDefaultImports": true,
                "esModuleInterop": true,
                "allowImportingTsExtensions": true,
                "preserveSymlinks": true
            }},
            "include": ["**/*"]
            }}
            ```
        """),
    )
    async def create_session(
        code: str,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        새로운 디버깅 세션을 생성하고 초기 이벤트 목록을 반환합니다.
        """
        try:
            session, execution_result = await debugger.create_session(
                project_path=project_path,
                code=code,
                initial_commands=[],
                timeout=timeout,
            )
            return {
                "session_id": session.session_id,
                "execution_result": execution_result,
            }
        except Exception as e:
            return {"error": str(e), "stack_trace": traceback.format_exc()}

    @mcp.tool(
        description=remove_tabs(
            """
            Execute CDP commands in a debugging session.
            Example payload:
            {"commands": [{"method": "Debugger.evaluateOnCallFrame", "params": {"expression": "1+1", "callFrameId": "6229198816740614410.1.0"}}, {"method": "Debugger.resume", "params": {}}]}

            Results are flattened in time order and each item is tagged with a 'type' field:
            - "command_result": the return value of a CDP command (if any)
            - "event": an emitted CDP event

            For resume/step commands that trigger "Debugger.resumed", the session waits until the next
            pause ("Debugger.paused") or termination ("Inspector.detached") and includes those events in the result.

            Note: In ESM, with pause-on-exceptions set to 'uncaught', a top-level throw pauses once
            at the throw site with reason='exception'. The secondary pause for the module promise rejection
            (reason='promiseRejection') does not occur. If you switch policy to 'all', you may observe two pauses
            and may need to call Debugger.resume twice to reach termination.

            Allowed commands: """ + json.dumps(allowed_debugger_commands) + """
            
            Here are the detailed command descriptions:
            Debugger.setBreakpointByUrl:
            ```
            {
            "url": "file:///app/entrypoint.ts",
            "urlRegex": "file:///app/entrypoint.ts", // optional, default ""
            "lineNumber": 0,
            "columnNumber": 0,          // optional, default 0
            "condition": ""             // optional, default ""
            }
            ```
            
            Debugger.setBreakpointOnFunctionCall:
            ```
            {
            "objectId": "<functionId>",
            "condition": ""             // optional, default ""
            }
            ```
            
            Debugger.removeBreakpoint:
            ```
            {
            "breakpointId": "<breakpointId>"
            }
            ```
            
            Debugger.setSkipAllPauses:
            ```
            {
            "skip": true // true: set to skip all pauses, false: set to not skip
            }
            ```
            
            Debugger.setBlackboxPatterns:
            ```
            {
            "patterns": ["/node_modules/"]
            }
            ```
            
            Debugger.setPauseOnExceptions:
            ```
            {
            "state": "all" // "all": set to pause on all exceptions, "none": set to not pause on exceptions, "uncaught": set to pause on uncaught exceptions
            }
            ```
            
            Debugger.getScriptSource:
            ```
            {
            "scriptId": "<scriptId>"
            }
            ```
            
            Debugger.getStackTrace:
            ```
            {
            "stackTraceId": { // You can get stackTraceId from stackTrace
                "id": "<stackTraceId>",
            }
            }
            ```
            
            Runtime.evaluate: // evaluate expression on global scope
            ```
            {
            "expression": "1+1",
            "returnByValue": true, // optional, default false
            "awaitPromise": true, // optional, default false
            "generatePreview": true, // optional, default false
            "throwOnSideEffect": true, // optional, default false // if false, you can do allocation in the expression like `const a = new Array(10);`
            "allowUnsafeEvalBlockedByCSP": true, // optional, default true
            "disableBreaks": true, // optional, default false
            "timeout": 10000 // optional ms, default 0 (no timeout)
            }
            ```
            
            Debugger.evaluateOnCallFrame: // evaluate expression on call frame
            ```
            {
            "expression": "1+1",
            "callFrameId": "<callFrameId>", // You can get callFrameId from Debugger.paused event // current call frame is the first call frame.
            "returnByValue": true,
            "awaitPromise": true,
            "throwOnSideEffect": true,
            }
            ```
            
            Runtime.callFunctionOn: // call function on object
            ```
            {
            "objectId": "<objId>",
            "functionDeclaration": "() => 42",
            "arguments": [{ "value": 1 }, { "unserializableValue": "Infinity" }, { "objectId": "<objId>" }], // You can choose value(JSON), unserializableValue(NaN, Infinity, -0), and objectId. Only one property is allowed per one argument.
            "returnByValue": true, // true: return JSON, false: return objectId. default false.
            "awaitPromise": true // default false.
            }
            ```
            
            Runtime.getProperties:
            ```
            {
            "objectId": "<objId>",
            "ownProperties": true, // optional, default false
            "accessorPropertiesOnly": true, // optional, default false
            "generatePreview": true, // optional, default false
            "nonIndexedPropertiesOnly": true, // optional, default false
            }
            ```
            
            Profiler.startPreciseCoverage:
            ```
            {
            "callCount": true,
            "detailed": true,
            "allowTriggeredUpdates": true // optional, default false
            }
            ```
            """
        ),
    )
    async def execute_commands(
        session_id: str,
        commands: List[tuple[str, dict[str, Any]]],
    ) -> Dict[str, Any]:
        """
        기존 디버깅 세션에서 명령어들을 실행하고 결과를 반환합니다.
        """
        session = debugger.get_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}

        try:
            execution_result = await session.execute_commands(commands)
            return {"execution_result": execution_result}
        except Exception as e:
            return {"error": str(e), "stack_trace": traceback.format_exc()}

    @mcp.tool(
        description="Close a debugging session.",
    )
    def close_session(session_id: str) -> Dict[str, Any]:
        """Closes a specific debugging session."""
        try:
            debugger.close_session(session_id)
            return {"status": f"Session {session_id} closed."}
        except Exception as e:
            return {"error": str(e), "stack_trace": traceback.format_exc()}

    return mcp
