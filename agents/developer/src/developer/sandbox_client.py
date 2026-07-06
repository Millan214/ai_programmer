"""HTTP client for the sandbox controller service — spawn and destroy only.

Exec and diff live on ``DeveloperTools`` (they are agent tools); spawn/destroy are
lifecycle, owned by the adapter around the loop.
"""

import httpx
from sandbox.models import SandboxHandle

from developer.models import DeveloperError

_DEFAULT_TIMEOUT_S = 120.0


class SandboxClient:
    def __init__(self, base_url: str, *, http: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http if http is not None else httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_S)

    async def spawn(self, repo_path: str) -> SandboxHandle:
        try:
            response = await self._http.post(
                f"{self._base_url}/sandboxes", json={"repo_path": repo_path}
            )
        except httpx.HTTPError as exc:
            raise DeveloperError(f"sandbox service unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise DeveloperError(f"sandbox spawn failed: {response.text}")
        return SandboxHandle.model_validate(response.json())

    async def destroy(self, sandbox_id: str) -> None:
        try:
            response = await self._http.delete(f"{self._base_url}/sandboxes/{sandbox_id}")
        except httpx.HTTPError as exc:
            raise DeveloperError(f"sandbox service unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise DeveloperError(f"sandbox destroy failed: {response.text}")
