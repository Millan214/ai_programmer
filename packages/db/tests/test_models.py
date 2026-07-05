import uuid

from platform_db.models import AgentTurn, Base, Task, TaskSession, VerifierRun


def test_task_instantiation():
    task = Task(repo="org/demo", title="add helper", status="pending")
    assert task.repo == "org/demo"
    assert task.tenant_id is None
    assert Task.__tablename__ == "task"


def test_task_session_instantiation():
    task_id = uuid.uuid4()
    session = TaskSession(task_id=task_id, phase="plan")
    assert session.task_id == task_id
    assert session.supervisor_state is None
    assert TaskSession.__tablename__ == "task_session"


def test_agent_turn_instantiation():
    session_id = uuid.uuid4()
    turn = AgentTurn(
        session_id=session_id,
        agent="planner",
        model="claude-sonnet-5",
        prompt_version="planner/decompose@v1",
        input_tokens=100,
        output_tokens=50,
    )
    assert turn.session_id == session_id
    assert turn.tool_calls is None
    assert AgentTurn.__tablename__ == "agent_turn"


def test_verifier_run_instantiation():
    session_id = uuid.uuid4()
    run = VerifierRun(session_id=session_id, worktree_ref="refs/worktrees/abc123")
    assert run.session_id == session_id
    assert run.build is None
    assert VerifierRun.__tablename__ == "verifier_run"


def test_all_models_registered_on_base():
    table_names = set(Base.metadata.tables.keys())
    assert {"task", "task_session", "agent_turn", "verifier_run"} <= table_names
