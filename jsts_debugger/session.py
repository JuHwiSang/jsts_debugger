"""
jsts_debugger.session
---------------------

This module defines the JSTSSession class, which encapsulates the logic for
managing a single, isolated debugging session.
"""

import asyncio
import json
from datetime import datetime
from docker.models.containers import Container
from typing import Any, Optional, Dict, List
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed
from docker.errors import NotFound, APIError
from jsts_debugger.config import AllowedDebuggerCommand, allowed_debugger_commands_set, entrypoint_ts_path
from jsts_debugger.lib.utils.command import is_command_to_ignore, is_debugger_resumed_command, is_program_run_command, is_command_may_run

class CDPError(Exception):
    """Custom exception for CDP errors."""
    pass


class JSTSSession:
    """
    Represents and manages a single, isolated debugging session.

    Each session corresponds to a running Docker container with a Node.js debugger
    listening on a specific port. This class encapsulates the low-level details
    of communicating with the debugger via the Chrome DevTools Protocol (CDP)
    over a WebSocket connection.

    Attributes:
        session_id (str): A unique identifier for the session.
        container (docker.models.containers.Container): The Docker container object for this session.
        ws (websockets.client.WebSocketClientProtocol): The WebSocket client for CDP communication.
        timeout_seconds (int): The default timeout for waiting for CDP events.
    """

    def __init__(
        self,
        session_id: str,
        container: Container,
        ws: WebSocketClientProtocol,
        timeout: int = 30,
    ):
        """
        Initializes a JSTSSession object.

        Args:
            session_id (str): The unique identifier for this session.
            container (docker.models.containers.Container): The running container for this session.
            ws (websockets.client.WebSocketClientProtocol): The active WebSocket client.
            timeout (int): The default timeout in seconds for CDP operations.
        """
        self.session_id = session_id
        self.container = container
        self.ws = ws
        self.timeout_seconds = timeout
        self._message_id = 0
        self._responses: Dict[int, Any] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self._reader_task = asyncio.create_task(self._reader())
        self._done = False
        print(f"[{datetime.now()}] Session {self.session_id} created.")

    async def _reader(self):
        """Reads messages from the WebSocket and dispatches them."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                if "id" in data:
                    if len(str(data)) > 2000:
                        print(f"[{datetime.now()}] Received response: {str(data)[:1000]}\n...\n{str(data)[-1000:]}")
                    else:
                        print(f"[{datetime.now()}] Received response: {data}")
                    self._responses[data["id"]] = data
                else:
                    if is_command_to_ignore(data.get("method")):
                        continue
                    if len(str(data)) > 200:
                        print(f"[{datetime.now()}] Received event: {str(data)[:1000]}\n...\n{str(data)[-1000:]}")
                    else:
                        print(f"[{datetime.now()}] Received event: {data}")
                    await self._events.put(data)
        except ConnectionClosed:
            print(f"[{datetime.now()}] Connection closed")
            await self._events.put(None)
            self._done = True

    async def _send_command(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Low-level CDP command sender.

        - Sends a single CDP command and waits ONLY for its direct response (the message with matching id).
        - Does NOT intentionally wait for or drain subsequent CDP events (e.g., Debugger.paused/resumed).
        - Raises CDPError on timeout or if the response contains an error.
        """
        if self.is_done():
            raise CDPError("Session is already done")
        
        self._message_id += 1
        command_id = self._message_id
        command = {"id": command_id, "method": method, "params": params or {}}
        print(f"[{datetime.now()}] Sending command: {command}")
        await self.ws.send(json.dumps(command))

        try:
            async with asyncio.timeout(self.timeout_seconds):
                while command_id not in self._responses:
                    await asyncio.sleep(0.01)  # Yield control

            response = self._responses.pop(command_id)
            if "error" in response:
                raise CDPError(response["error"]["message"])
            return response.get("result")
        except asyncio.TimeoutError:
            raise CDPError(f"Timeout waiting for response to command: {method}")

    async def initialize(self) -> List[Dict[str, Any]]:
        """Initializes the session.
        Enables core domains and starts execution.
        Returns events up to the first pause or detach. Note: This function triggers
        Runtime.runIfWaitingForDebugger which begins program execution. Subsequent 
        waits for pause/detach should be driven by higher-level operations (e.g.,
        after resume/step), not by calling initialize again.
        """
        await self.execute_command("Runtime.enable", {})
        await self.execute_command("Debugger.enable", {})
        await self.execute_command("HeapProfiler.enable", {})
        await self.execute_command("Profiler.enable", {})
        await self.execute_command("Network.enable", {})

        events = await self.execute_command("Runtime.runIfWaitingForDebugger", {})
        # events = await self._wait_for_pause_or_detach()
        return events
        # await self.execute_command("Debugger.pause", {})

    async def _wait_for_pause_or_detach(self, timeout: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Waits for a Debugger.paused or Inspector.detached event.
        Wraps events in a dictionary with a 'type' field.
        """
        collected_results = []
        try:
            async with asyncio.timeout(timeout or self.timeout_seconds):
                while not self.is_done():
                    event = await self._events.get()
                    if event is None:
                        break
                    collected_results.append({"type": "event", "data": event})
                    if event.get("method") in ["Debugger.paused", "Inspector.detached", "Runtime.executionContextDestroyed"]:
                        break
            return collected_results
        except asyncio.TimeoutError:
            # 에러 낼 시, 'may run'류 명령어들이 run되지 않은 경우 에러가 발생해 응답을 받지 못하게 됨.
            print(f"Timeout waiting for pause/detach") # warning
            return collected_results

    async def execute_command(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        allow_unknown_command: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        High-level CDP command executor with event aggregation.

        Behavior:
        - Flushes any queued events first and includes them in the result as {"type": "event", ...}.
        - Sends the command and, if the response has a result, includes it as {"type": "command_result", ...}.
        - Then attempts to read the next event with a short timeout and includes it if present.
        - If that first event indicates a resume (Debugger.resumed), waits until the next pause
          (Debugger.paused) or termination (Inspector.detached), aggregating all such events.

        Returns a flat list of items in occurrence order, each tagged with 'type' (event | command_result).
        Raises CDPError if the session is already done or the command is unknown (unless allow_unknown_command).
        """
        if self.is_done():
            raise CDPError(f"Session is already done while executing command: {method}")

        collected_results = []
        while not self._events.empty() and not self.is_done():
            event = await self._events.get()
            if event is None:
                break
            collected_results.append({"type": "event", "data": event})

        if not allow_unknown_command and method not in allowed_debugger_commands_set:
            raise CDPError(f"Unknown command: {method}")

        command_result = await self._send_command(method, params)
        if command_result is not None:
            collected_results.append({"type": "command_result", "data": command_result})

        if is_program_run_command(method) or is_command_may_run(method):
            # This command may cause execution to continue, so we wait for the next
            # pause or for the script to finish.
            run_events = await self._wait_for_pause_or_detach()
            collected_results.extend(run_events)

        return collected_results

    async def execute_commands(
        self, commands: list[tuple[str, dict[str, Any]]],
        allow_unknown_command: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Executes a list of commands and collects all subsequent events.
        """
        results = []
        for method, params in commands:
            result = await self.execute_command(method, params, allow_unknown_command)
            results.extend(result)
        return results

    # async def enable_debugger(
    #     self, initial_commands: list[tuple[AllowedDebuggerCommand, dict[str, Any]]] = []
    # ) -> List[Dict[str, Any]]:
    #     """
    #     Enables the debugger and executes initial commands.
    #     """
    #     return await self.execute_commands(initial_commands)
    
    def is_done(self) -> bool:
        return self._done
    
    async def close(self):
        """
        Cleans up all resources associated with this session.
        """
        self._reader_task.cancel()
        if self.ws and not self.ws.closed:
            print(f"[{datetime.now()}] Closing WebSocket")
            await self.ws.close()

        try:
            print(f"[{datetime.now()}] Stopping container {self.container.short_id} for session {self.session_id}...")
            self.container.stop(timeout=5)
        except NotFound:
            print(f"[{datetime.now()}] Warning: Container {self.container.short_id} was not found (already stopped).")
        except APIError as e:
            print(f"[{datetime.now()}] Error while stopping container for session {self.session_id}: {e}")

    def set_timeout(self, seconds: int):
        """
        Sets the timeout for CDP operations in this session.
        """
        print(f"[{datetime.now()}] Setting timeout for session {self.session_id} to {seconds} seconds.")
        self.timeout_seconds = seconds

    # async def __aenter__(self):
    #     await self.initialize()
    #     return self

    # async def __aexit__(self, exc_type, exc_value, traceback):
    #     await self.close()