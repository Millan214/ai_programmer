"""OTel setup shared by all services and agents.

Public surface: ``configure``/``lifespan_for`` (startup), ``traced``/``add_llm_attributes``/
``current_span`` (span authoring), ``set_task_context``/``get_task_context`` (task scope).
"""

from platform_telemetry.context import get_task_context, set_task_context
from platform_telemetry.decorators import add_llm_attributes, current_span, traced
from platform_telemetry.setup import configure, lifespan_for

__all__ = [
    "add_llm_attributes",
    "configure",
    "current_span",
    "get_task_context",
    "lifespan_for",
    "set_task_context",
    "traced",
]
