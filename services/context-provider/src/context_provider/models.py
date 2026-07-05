"""Data shapes unifying Graphify and CRG results (ADR-0002).

``Confidence`` mirrors Graphify's EXTRACTED/INFERRED/AMBIGUOUS edge tags, which
ADR-0006 leans on for the Verifier's structured facts; CRG results are treated as
EXTRACTED (they come from an AST + embedding index, not LLM inference).
"""

from typing import Literal

from pydantic import BaseModel

Confidence = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]


class Node(BaseModel):
    id: str
    label: str
    kind: str
    path: str | None = None
    summary: str | None = None
    confidence: Confidence = "EXTRACTED"


class Edge(BaseModel):
    source: str
    target: str
    relation: str
    confidence: Confidence = "EXTRACTED"


class GraphQueryResult(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


class Path(BaseModel):
    nodes: list[Node]
    edges: list[Edge]


class ImpactResult(BaseModel):
    symbol: str
    affected: list[Node]


class Community(BaseModel):
    id: str
    label: str
    members: list[str]


class RetrievalResult(BaseModel):
    source: Literal["graphify", "crg"]
    nodes: list[Node]
