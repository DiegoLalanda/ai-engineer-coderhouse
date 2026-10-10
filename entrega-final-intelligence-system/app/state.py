"""Estado del orquestador del módulo 6, más la decisión humana."""

from __future__ import annotations

from typing import Annotated, Literal, NotRequired

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

Siguiente = Literal["Investigador", "Analista", "Aprobacion", "FINALIZAR"]
JobStatus = Literal["pending", "running", "waiting_approval", "done", "failed"]


class Fragmento(BaseModel):
    fuente: str = Field(min_length=1)
    texto: str = Field(min_length=1)


class ResearchArtifact(BaseModel):
    consulta: str = Field(min_length=1)
    producto: str = Field(min_length=1)
    findings: list[str] = Field(min_length=1)
    fuentes: list[str] = Field(default_factory=list)
    fragmentos: list[Fragmento] = Field(default_factory=list)
    muestra: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class AnalysisArtifact(BaseModel):
    producto: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    muestra: int = Field(ge=1)
    sentimiento: Literal["positivo", "neutral", "negativo"]
    destacar: bool
    suficiente: bool


class AgentState(MessagesState):
    messages: Annotated[list[BaseMessage], add_messages]
    next: NotRequired[str]
    research: NotRequired[dict | None]
    analysis: NotRequired[dict | None]
    steps: NotRequired[int]
    task_completed: NotRequired[bool]
    aprobado: NotRequired[bool | None]
    publicado: NotRequired[bool]


class TareaEntrada(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class TareaCreada(BaseModel):
    job_id: str
    status: Literal["pending"]


class AprobacionEntrada(BaseModel):
    approved: bool


class TareaEstado(BaseModel):
    job_id: str
    status: JobStatus
    query: str
    result: str = ""
    error: str = ""
    approval: dict | None = None


def leer_investigacion(crudo: dict | ResearchArtifact | None) -> ResearchArtifact | None:
    if crudo is None:
        return None
    if isinstance(crudo, ResearchArtifact):
        return crudo
    return ResearchArtifact.model_validate(crudo)


def leer_analisis(crudo: dict | AnalysisArtifact | None) -> AnalysisArtifact | None:
    if crudo is None:
        return None
    if isinstance(crudo, AnalysisArtifact):
        return crudo
    return AnalysisArtifact.model_validate(crudo)
