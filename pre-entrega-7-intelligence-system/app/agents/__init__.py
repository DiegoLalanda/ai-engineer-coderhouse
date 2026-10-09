"""Especialistas del orquestador."""

from app.agents.analyst import build_analista
from app.agents.research import build_investigador

__all__ = ["build_analista", "build_investigador"]
