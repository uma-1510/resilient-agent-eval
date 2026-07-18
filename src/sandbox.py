from __future__ import annotations

import tempfile
import time
from pathlib import Path

import docker
from docker.errors import NotFound

from config.settings import get_settings
from src.state import ExecutionResult

SCRIPT_NAME = "script.py"
IMAGE = "python:3.11-slim"


class DockerSandbox:
    """Runs untrusted generated code in a disposable, locked-down container.

    No network access, capped memory/CPU, read-only root filesystem (with a
    small writable tmpfs for /tmp since some stdlib operations need somewhere
    to write), and a hard wall-clock timeout. The container is always removed,
    success or failure.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = docker.from_env()
        self._mem_limit = settings.sandbox_mem_limit
        self._nano_cpus = settings.sandbox_nano_cpus
        self._timeout_seconds = settings.sandbox_timeout_seconds

    def run(self, code: str) -> ExecutionResult:
        with tempfile.TemporaryDirectory() as tmp_dir:
            (Path(tmp_dir) / SCRIPT_NAME).write_text(code)

            container = self._client.containers.run(
                image=IMAGE,
                command=["python", SCRIPT_NAME],
                working_dir="/sandbox",
                volumes={tmp_dir: {"bind": "/sandbox", "mode": "ro"}},
                environment={"PYTHONDONTWRITEBYTECODE": "1"},
                network_mode="none",
                mem_limit=self._mem_limit,
                nano_cpus=self._nano_cpus,
                read_only=True,
                tmpfs={"/tmp": "rw,size=16m"},
                detach=True,
            )
            try:
                return self._await_result(container)
            finally:
                try:
                    container.remove(force=True)
                except NotFound:
                    pass

    def _await_result(self, container) -> ExecutionResult:
        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            container.reload()
            if container.status == "exited":
                exit_code = container.attrs["State"]["ExitCode"]
                return ExecutionResult(
                    success=exit_code == 0,
                    stdout=_decode(container.logs(stdout=True, stderr=False)),
                    stderr=_decode(container.logs(stdout=False, stderr=True)),
                    timed_out=False,
                    exit_code=exit_code,
                )
            time.sleep(0.1)

        try:
            container.kill()
        except Exception:
            pass
        return ExecutionResult(
            success=False,
            stdout=_decode(container.logs(stdout=True, stderr=False)),
            stderr=_decode(container.logs(stdout=False, stderr=True)),
            timed_out=True,
            exit_code=None,
        )


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")
