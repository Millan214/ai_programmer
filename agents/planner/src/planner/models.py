from pydantic import BaseModel


class Subtask(BaseModel):
    title: str
    description: str
    acceptance: str


class Plan(BaseModel):
    subtasks: list[Subtask]
    risks: list[str]
    estimated_files: list[str]


class PlannerOutputError(Exception):
    """Raised when the planner's LLM output can't be parsed into a ``Plan``."""
