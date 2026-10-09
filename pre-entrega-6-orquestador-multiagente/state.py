"""Estado compartido. Cada especialista escribe solo su parcela."""

from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Siguiente = Literal["Investigador", "Analista", "FINALIZAR"]


class ResearchArtifact(BaseModel):
    """Lo que el investigador puede afirmar después de leer las fuentes."""

    consulta: str = Field(min_length=1)
    producto: str = Field(min_length=1)
    findings: list[str] = Field(min_length=1)
    fuentes: list[str] = Field(default_factory=list)
    muestra: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class AnalysisArtifact(BaseModel):
    """Lo que el analista calcula sobre las reseñas ya reunidas."""

    producto: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    muestra: int = Field(ge=1)
    sentimiento: Literal["positivo", "neutral", "negativo"]
    destacar: bool
    suficiente: bool


class AgentState(MessagesState):
    """Historial más las parcelas. messages se acumula; el resto se pisa."""

    messages: Annotated[list[BaseMessage], add_messages]
    next: Siguiente
    research: ResearchArtifact | None
    analysis: AnalysisArtifact | None
    steps: int
    task_completed: bool
