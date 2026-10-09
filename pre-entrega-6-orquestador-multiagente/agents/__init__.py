"""Especialistas. Cada módulo arma su ReAct y devuelve el nodo del grafo padre."""

from agents.analyst_agent import build_analista
from agents.research_agent import build_investigador

__all__ = ["build_analista", "build_investigador"]
