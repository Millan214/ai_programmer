"""HTTP client for the real Verifier service (card 05), wired in behind ``VerifierProtocol``.

The Verifier is its own FastAPI service (``services/verifier``), not an in-process
package the orchestrator imports — matching every other service boundary in this
platform, agents talk to it over HTTP rather than importing its code directly. This
client flattens ADR-0006's structured ``VerifierResult`` down to the per-check
pass/fail/skip dict ``VerifierProtocol`` carries (the same shape ``FakeVerifier``
returns, so ``_route_after_verify``'s ``build``/``tests`` check keeps working
unchanged).

Errors are not swallowed into a fake "fail" — a Verifier that's unreachable or errors
is an infrastructure problem, not a verification result, and reporting it as one would
be exactly the kind of factual claim ADR-0006 exists to prevent. It propagates.
"""

import uuid

import httpx

from orchestrator.protocols import EditsDict, VerifierFacts


class VerifierClientError(Exception):
    """Raised when ``edits`` carries no worktree for the Verifier to inspect."""


class VerifierHttpClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def verify(self, edits: EditsDict, session_id: uuid.UUID) -> VerifierFacts:
        worktree_path = edits.get("worktree_path")
        if not isinstance(worktree_path, str):
            raise VerifierClientError(
                "edits has no string 'worktree_path' — the Developer agent (card 08) "
                "must set one before Verify can call the real Verifier"
            )
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/verify",
                json={"worktree_path": worktree_path, "session_id": str(session_id)},
            )
            response.raise_for_status()
        result = response.json()
        return {
            "build": result["build"]["status"],
            "typecheck": result["typecheck"]["status"],
            "tests": result["tests"]["status"],
            "lint": result["lint"]["status"],
        }
