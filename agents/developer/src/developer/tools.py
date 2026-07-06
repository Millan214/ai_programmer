"""Tool implementations the Developer's ReAct loop dispatches to (card 08).

Each tool wraps one platform service over HTTP — Context Provider for retrieval,
the sandbox controller for file I/O, the Verifier for facts. ``read_file`` is the one
sanctioned exception to non-negotiable #2 (Context Provider is the only retrieval
path): reading a *specific known* path after retrieval is fine; searching is not.

File I/O goes through the sandbox's ``exec`` endpoint rather than touching the
worktree from this process: the platform never edits code outside a sandbox, and the
same container the developer writes in is what later verifier phases inspect.
``edit_file`` ships content base64-encoded so arbitrary file bodies survive the shell
hop without quoting games.

Service-unreachable errors raise ``DeveloperError`` (infrastructure problem, the loop
cannot continue); a tool that ran but failed (file not found, non-zero exit) returns
its error text so the model can observe and recover.
"""

import base64
import shlex
import uuid
from typing import Protocol, cast

import httpx
from sandbox.models import SandboxHandle
from verifier.models import VerifierResult

from developer.models import DeveloperError

_DEFAULT_TIMEOUT_S = 180.0


class DeveloperToolsProtocol(Protocol):
    """The tool surface the agent loop dispatches against; tests pass a fake."""

    async def retrieve(self, query: str, mode: str) -> str: ...

    async def read_file(self, path: str, sandbox: SandboxHandle) -> str: ...

    async def edit_file(self, path: str, content: str, sandbox: SandboxHandle) -> None: ...

    async def run_verifier(self, sandbox: SandboxHandle) -> VerifierResult: ...

    async def get_diff(self, sandbox: SandboxHandle) -> str: ...


class ToolExecutionError(Exception):
    """A tool ran but failed in a way the model should observe (e.g. file not found)."""


class DeveloperTools:
    def __init__(
        self,
        *,
        context_provider_url: str,
        sandbox_url: str,
        verifier_url: str,
        repo: str,
        session_id: uuid.UUID | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._context_provider_url = context_provider_url.rstrip("/")
        self._sandbox_url = sandbox_url.rstrip("/")
        self._verifier_url = verifier_url.rstrip("/")
        self._repo = repo
        # Passed through to the Verifier so every in-loop run persists a
        # ``verifier_run`` row linked to this session (R2 / card 08 success criterion).
        self._session_id = session_id
        self._http = http if http is not None else httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_S)

    async def _post(self, url: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = await self._http.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise DeveloperError(f"service unreachable at {url}: {exc}") from exc
        if response.status_code >= 400:
            raise DeveloperError(
                f"service at {url} returned {response.status_code}: {response.text}"
            )
        return response.json()

    async def _exec(self, sandbox: SandboxHandle, command: list[str]) -> tuple[int, str, str]:
        result = await self._post(
            f"{self._sandbox_url}/sandboxes/{sandbox.id}/exec", {"command": command}
        )
        return (
            int(result["exit_code"]),  # pyright: ignore[reportArgumentType]
            str(result["stdout"]),
            str(result["stderr"]),
        )

    async def retrieve(self, query: str, mode: str) -> str:
        result = await self._post(
            f"{self._context_provider_url}/retrieve",
            {"query": query, "repo": self._repo, "mode": mode},
        )
        nodes = result.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            return f"(no results from {result.get('source', 'retrieval')})"
        lines = [f"source: {result.get('source', 'unknown')}"]
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                fields = cast("dict[str, object]", node)
                ident = fields.get("id", "?")
                kind = fields.get("kind", "")
                file = fields.get("file", "")
                snippet = fields.get("snippet") or fields.get("summary") or ""
                lines.append(f"- {ident} {kind} {file}\n  {snippet}".rstrip())
        return "\n".join(lines)

    async def read_file(self, path: str, sandbox: SandboxHandle) -> str:
        code, stdout, stderr = await self._exec(sandbox, ["cat", path])
        if code != 0:
            raise ToolExecutionError(f"read_file({path!r}) failed: {stderr.strip()}")
        return stdout

    async def edit_file(self, path: str, content: str, sandbox: SandboxHandle) -> None:
        encoded = base64.b64encode(content.encode()).decode("ascii")
        quoted = shlex.quote(path)
        parent = shlex.quote(str(_posix_parent(path)))
        script = f"mkdir -p {parent} && printf '%s' '{encoded}' | base64 -d > {quoted}"
        code, _stdout, stderr = await self._exec(sandbox, ["sh", "-c", script])
        if code != 0:
            raise ToolExecutionError(f"edit_file({path!r}) failed: {stderr.strip()}")

    async def run_verifier(self, sandbox: SandboxHandle) -> VerifierResult:
        payload: dict[str, object] = {"worktree_path": str(sandbox.worktree_path)}
        if self._session_id is not None:
            payload["session_id"] = str(self._session_id)
        result = await self._post(f"{self._verifier_url}/verify", payload)
        return VerifierResult.model_validate(result)

    async def get_diff(self, sandbox: SandboxHandle) -> str:
        try:
            response = await self._http.get(f"{self._sandbox_url}/sandboxes/{sandbox.id}/diff")
        except httpx.HTTPError as exc:
            raise DeveloperError(f"sandbox diff unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise DeveloperError(f"sandbox diff failed: {response.text}")
        payload: dict[str, object] = response.json()
        return str(payload.get("diff", ""))


def _posix_parent(path: str) -> str:
    """Parent of a sandbox-side (POSIX) path — pathlib would give Windows semantics here."""
    head, _, _ = path.replace("\\", "/").rpartition("/")
    return head or "."
