"""Contrato del orquestador. El supervisor escribe next; cada especialista, su propio artefacto."""

from __future__ import annotations

from typing import Literal, NotRequired

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

Siguiente = Literal["Investigador", "Analista", "Aprobacion", "FINALIZAR"]
Sentimiento = Literal["positivo", "neutral", "negativo"]
JobStatus = Literal["pending", "running", "waiting_approval", "completed", "failed"]


class Fragmento(BaseModel):
    fuente: str = Field(min_length=1)
    texto: str = Field(min_length=1)


class ResearchArtifact(BaseModel):
    consulta: str = Field(min_length=1)
    producto: str = ""
    findings: list[str] = Field(min_length=0)
    fuentes: list[str] = Field(default_factory=list)
    fragmentos: list[Fragmento] = Field(default_factory=list)
    muestra: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class AnalysisArtifact(BaseModel):
    producto: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    muestra: int = Field(ge=0)
    sentimiento: Sentimiento
    destacar: bool
    suficiente: bool


class AgentState(MessagesState):
    next: NotRequired[str]
    research: NotRequired[dict | None]
    analysis: NotRequired[dict | None]
    steps: NotRequired[int]
    task_completed: NotRequired[bool]
    aprobado: NotRequired[bool | None]
    publicado: NotRequired[bool]


class DecisionSupervisor(BaseModel):
    next: Siguiente
    motivo: str = Field(min_length=1)


class ConsultaInput(BaseModel):
    consulta: str = Field(min_length=1, max_length=500)


class TareaEntrada(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class TareaCreada(BaseModel):
    job_id: str
    status: JobStatus


class AprobacionEntrada(BaseModel):
    approved: bool


class TareaEstado(BaseModel):
    job_id: str
    status: JobStatus
    query: str
    result: str = ""
    error: str = ""
    approval: dict | None = None
