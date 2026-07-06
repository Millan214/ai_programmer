"""``platform-cli`` — a thin Click wrapper over the task API (card 09).

Every command opens a client via ``_client()`` (tests monkeypatch it to inject an
``httpx.MockTransport``) and talks to ``PLATFORM_API_URL`` (default localhost:8000).
"""

import os

import click
import httpx

_DEFAULT_URL = "http://localhost:8000"
_TIMEOUT_S = 30.0


def _base_url() -> str:
    return os.environ.get("PLATFORM_API_URL", _DEFAULT_URL)


def _client() -> httpx.Client:
    return httpx.Client(base_url=_base_url(), timeout=_TIMEOUT_S)


@click.group()
def main() -> None:
    """Submit and inspect platform tasks."""


@main.command()
@click.option("--repo", required=True, help="Target repo the task runs against.")
@click.option("--title", required=True, help="Short task title.")
@click.option("--description", required=True, help="What the task should accomplish.")
@click.option("--budget", type=float, default=None, help="Optional USD budget.")
def submit(repo: str, title: str, description: str, budget: float | None) -> None:
    """Create a task and enqueue its run."""
    payload: dict[str, object] = {"repo": repo, "title": title, "description": description}
    if budget is not None:
        payload["budget_usd"] = budget
    with _client() as client:
        response = client.post("/tasks", json=payload)
        response.raise_for_status()
        data = response.json()
    click.echo(f"task_id: {data['task_id']}")


@main.command()
@click.argument("task_id")
def status(task_id: str) -> None:
    """Show a task's current status and phase."""
    with _client() as client:
        response = client.get(f"/tasks/{task_id}")
    if response.status_code == 404:
        raise click.ClickException(f"task {task_id} not found")
    response.raise_for_status()
    data = response.json()
    phase = data.get("phase") or "-"
    click.echo(f"status: {data['status']}  phase: {phase}")
    verifier = data.get("verifier")
    if verifier:
        click.echo(
            "verifier: "
            f"build={verifier.get('build') or '-'} "
            f"typecheck={verifier.get('typecheck') or '-'} "
            f"tests={verifier.get('tests') or '-'} "
            f"lint={verifier.get('lint') or '-'}"
        )


@main.command(name="list")
@click.option("--limit", type=int, default=20, help="Max rows to show.")
def list_tasks(limit: int) -> None:
    """List recent tasks, newest first."""
    with _client() as client:
        response = client.get("/tasks", params={"limit": limit})
        response.raise_for_status()
        data = response.json()
    rows = data["tasks"]
    if not rows:
        click.echo("(no tasks)")
        return
    click.echo(f"{'TASK ID':36}  {'STATUS':14}  {'REPO':16}  TITLE")
    for row in rows:
        click.echo(
            f"{row['task_id']:36}  {row['status']:14}  {row['repo']:16}  {row['title']}"
        )


if __name__ == "__main__":
    main()
