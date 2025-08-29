"""
jsts_debugger.debugger
----------------------

This module provides the main JSTSDebugger class, which acts as the primary
controller for creating and managing debugging sessions.
"""

import atexit
import asyncio
import hashlib
import os
from typing import List, Optional, Dict, Any, Tuple
import shutil
import json
import io
import tarfile
from pathlib import Path

import docker
import httpx
from docker.client import DockerClient
from docker.models.containers import Container
from websockets.asyncio.client import connect, ClientConnection
from websockets.exceptions import WebSocketException

from docker.errors import (
    APIError,
    BuildError,
    ContainerError,
    DockerException,
    ImageNotFound,
)

from .config import AllowedDebuggerCommand
from .session import JSTSSession
from .helpers import get_package_name
from .lib.utils.deep_merge import deep_merge


class JSTSDebuggerError(Exception):
    """Base exception for jsts_debugger."""

    pass


class ProjectNotFoundError(JSTSDebuggerError):
    """Raised when the project path does not exist."""

    pass


class DockerBuildError(JSTSDebuggerError):
    """Raised when the Docker image build fails."""

    pass


class DockerfileNotFoundError(DockerBuildError):
    """Raised when the Dockerfile is not found."""

    pass


class ContainerStartError(JSTSDebuggerError):
    """Raised when the Docker container fails to start."""

    pass


class DebuggerConnectionError(JSTSDebuggerError):
    """Raised when the connection to the debugger fails."""

    pass


class JSTSDebugger:
    """
    The main controller for creating and managing debugging sessions.
    """

    def __init__(
        self,
        base_dockerfile_path: str = "templates/Dockerfile.base",
        base_package_json_path: str = "templates/package.base.json",
        base_tsconfig_json_path: str = "templates/tsconfig.base.json",
    ):
        """Initializes the JSTSDebugger."""
        self.base_dockerfile_path = base_dockerfile_path
        with open(base_package_json_path, "r") as f:
            self.base_package_json = json.load(f)
        with open(base_tsconfig_json_path, "r") as f:
            self.base_tsconfig_json = json.load(f)
        try:
            self.docker_client: DockerClient = docker.from_env()
        except DockerException:
            raise RuntimeError(
                "Docker is not running or not configured correctly. Please start Docker and try again."
            )
        self.sessions: dict[str, JSTSSession] = {}
        atexit.register(self.close_all_sessions)
        print("JSTSDebugger initialized. Ready to create sessions.")

    def _get_image_tag(self, project_path: str, code: str) -> str:
        """Generates a unique Docker image tag based on project path and entry code.

        Including the entrypoint code in the hash ensures different code snippets
        do not accidentally reuse an image built for a previous test/session.
        """
        abs_path = os.path.abspath(project_path)
        hasher = hashlib.md5()
        hasher.update(abs_path.encode("utf-8"))
        hasher.update(b"::")
        hasher.update(code.encode("utf-8"))
        return f"jsts_debugger/project:{hasher.hexdigest()}"

    async def _build_or_get_image(
        self,
        project_path: str,
        image_tag: str,
        code: str,
        package_json_data: Optional[dict[str, Any]],
        tsconfig_json_data: Optional[dict[str, Any]],
    ) -> None:
        """Builds a Docker image if it doesn't exist, or gets the existing one."""
        try:
            self.docker_client.images.get(image_tag)
            print(f"Found cached image: {image_tag}")
            return
        except ImageNotFound:
            print(
                f"Image not found. Building image for {project_path} with tag {image_tag}..."
            )

        if not os.path.exists(self.base_dockerfile_path):
            raise DockerfileNotFoundError(
                f"Base Dockerfile not found at '{self.base_dockerfile_path}'"
            )

        # Merge package.json and tsconfig.json data
        final_package_json = deep_merge(self.base_package_json, package_json_data or {})
        final_tsconfig_json = deep_merge(
            self.base_tsconfig_json, tsconfig_json_data or {}
        )

        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            repo_name = get_package_name(project_path)
            if repo_name is None:
                raise ValueError(f"Package name not found in {project_path}")
            
            # Add project files to tar
            for root, _, files in os.walk(project_path):
                for file in files:
                    host_path = Path(root) / file
                    arc_path = str(host_path.relative_to(project_path))
                    tar.add(str(host_path), repo_name + "/" + arc_path)

            # Add dynamically generated files
            # 1. Dockerfile
            with open(self.base_dockerfile_path, "r") as f:
                dockerfile_content = f.read()
            if repo_name is None:
                raise ValueError(f"Package name not found in {project_path}")
            dockerfile_content = dockerfile_content.replace("{repo_name}", repo_name)
            dockerfile_info = tarfile.TarInfo("Dockerfile")
            dockerfile_bytes = dockerfile_content.encode("utf-8")
            dockerfile_info.size = len(dockerfile_bytes)
            tar.addfile(dockerfile_info, io.BytesIO(dockerfile_bytes))

            # 2. package.json
            package_json_str = json.dumps(final_package_json, indent=4)
            package_json_info = tarfile.TarInfo(f"package.json")
            package_json_bytes = package_json_str.encode("utf-8")
            package_json_info.size = len(package_json_bytes)
            tar.addfile(package_json_info, io.BytesIO(package_json_bytes))

            # 3. tsconfig.json
            tsconfig_json_str = json.dumps(final_tsconfig_json, indent=4)
            tsconfig_json_info = tarfile.TarInfo(f"tsconfig.json")
            tsconfig_json_bytes = tsconfig_json_str.encode("utf-8")
            tsconfig_json_info.size = len(tsconfig_json_bytes)
            tar.addfile(tsconfig_json_info, io.BytesIO(tsconfig_json_bytes))

            # 4. Entrypoint code
            entrypoint_info = tarfile.TarInfo("entrypoint.ts")
            code_bytes = code.encode("utf-8")
            entrypoint_info.size = len(code_bytes)
            tar.addfile(entrypoint_info, io.BytesIO(code_bytes))

        buf.seek(0)

        try:
            self.docker_client.images.build(
                fileobj=buf,
                custom_context=True,
                tag=image_tag,
                rm=True,
                encoding="gzip",
            )
            print(f"Image built successfully: {image_tag}")
        except (BuildError, APIError) as e:
            raise DockerBuildError(f"Error building Docker image: {e}") from e

    def _build_command(self, entry: str, port: int = 9229) -> List[str]:
        """
        Return (command_list, env) that debugs .ts or .js on Win/Linux.
        Always uses transpile-only & skips tsconfig.json.
        """
        node_flags = [
            f"--inspect-wait=0.0.0.0:{port}",
            "--enable-source-maps",
            "--preserve-symlinks",
        ]

        if entry.lower().endswith(".ts"):
            cmd = ["npx", "tsx"]
            cmd += [*node_flags, entry]
        else:
            cmd = ["node", *node_flags, entry]
        
        return cmd

    def _start_container(
        self,
        image_tag: str,
    ) -> Container:
        """Starts the Docker container and returns the container object."""
        container_entrypoint_path = "/app/entrypoint.ts"
        command = self._build_command(container_entrypoint_path)

        try:
            container = self.docker_client.containers.run(
                image=image_tag,
                command=command,
                ports={"9229/tcp": None},
                detach=True,
                remove=True,
            )
            print(f"Container {container.short_id} started.")
            return container
        except (ContainerError, APIError) as e:
            raise ContainerStartError(f"Error starting container: {e}") from e

    async def _connect_to_debugger(
        self, container: Container
    ) -> ClientConnection:
        """Connects to the debugger inside the container and returns a WebSocket client."""
        try:
            container.reload()
            host_port = container.ports["9229/tcp"][0]["HostPort"]
            await asyncio.sleep(1.5)  # Wait for the debugger to initialize

            ws_url_info = f"http://127.0.0.1:{host_port}/json/list"
            async with httpx.AsyncClient() as client:
                for _ in range(5):  # Retry mechanism
                    try:
                        resp = await client.get(ws_url_info, timeout=10)
                        resp.raise_for_status()
                        tabs = resp.json()
                        if tabs and "webSocketDebuggerUrl" in tabs[0]:
                            debugger_ws_url = tabs[0]["webSocketDebuggerUrl"]
                            # Disable ping/pong to avoid idle close from servers that don't respond to pings (e.g., Node inspector)
                            return await connect(
                                debugger_ws_url,
                                open_timeout=10,
                                ping_interval=None,
                                ping_timeout=None,
                                close_timeout=5,
                            )
                    except (httpx.RequestError, KeyError, IndexError):
                        await asyncio.sleep(1)
                else:
                    raise DebuggerConnectionError(
                        "Could not get WebSocket debugger URL after retries."
                    )
        except (ConnectionError, WebSocketException, KeyError) as e:
            raise DebuggerConnectionError(f"Failed to connect to debugger: {e}") from e

    async def create_session(
        self,
        project_path: str,
        code: str,
        initial_commands: list[tuple[str, dict[str, Any]]] = [],
        timeout: int = 30,
        package_json_data: Optional[dict[str, Any]] = None,
        tsconfig_json_data: Optional[dict[str, Any]] = None,
    ) -> Tuple[JSTSSession, List[Dict[str, Any]]]:
        """
        Creates a new debugging session by building an image, starting a container, and connecting.
        Returns the session.
        """
        if not os.path.isdir(project_path):
            raise ProjectNotFoundError(
                f"Project path '{project_path}' does not exist or is not a directory."
            )

        image_tag = self._get_image_tag(project_path, code)

        container = None
        try:
            await self._build_or_get_image(
                project_path,
                image_tag,
                code,
                package_json_data,
                tsconfig_json_data,
            )
            container = self._start_container(image_tag)
            ws = await self._connect_to_debugger(container)

            session_id = container.short_id
            new_session = JSTSSession(session_id, container, ws, timeout)
            self.sessions[session_id] = new_session

            events = await new_session.initialize()
            execution_result = await new_session.execute_commands(
                initial_commands
            )
            
            # import time
            # time.sleep(1000000) # debug

            return new_session, events + execution_result

        except JSTSDebuggerError:
            if container:
                container.stop()
            raise
        except Exception as e:
            if container:
                container.stop()
            raise JSTSDebuggerError(
                f"An unexpected error occurred during session creation: {e}"
            ) from e


    def close_session(self, session_id: str):
        """Closes a specific debugging session by its ID."""
        if session_id in self.sessions:
            print(f"Closing session {session_id}...")
            session = self.sessions.pop(session_id)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(session.close())
            except RuntimeError:
                asyncio.run(session.close())
            print(f"Session {session_id} closed.")
        else:
            print(f"Warning: Session {session_id} not found.")

    def close_all_sessions(self):
        """Closes all active debugging sessions."""
        print("Closing all active sessions...")
        if not self.sessions:
            return
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.close_session(session_id)
        print("All sessions closed.")

    def get_session(self, session_id: str) -> Optional[JSTSSession]:
        """
        Returns a debugging session by its ID.

        Args:
            session_id (str): The ID of the session to retrieve.

        Returns:
            Optional[JSTSSession]: The session object if found, None otherwise.
        """
        return self.sessions.get(session_id)
