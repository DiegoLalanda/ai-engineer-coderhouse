"""Comprueba la rúbrica sin API key y deja la traza de delegación en evidencia/.

    python verificar_rubrica.py
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, get_type_hints

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages

import main as entrada
from agents.analyst_agent import armar_analisis, puntuar
from agents.research_agent import armar_investigacion, buscar_resenas
from graph import build_graph
from settings import BASE_DIR
from state import AgentState
from trace import correr, render_log

REPORT_PATH = BASE_DIR / "evidencia" / "verificacion.txt"
MERMAID_PATH = BASE_DIR / "evidencia" / "grafo.mmd"


@dataclass
class Check:
    criterion: str
    passed: bool
    evidence: str


class ModeloEnsayo(BaseChatModel):
    """Sustituto determinista. Sigue la rúbrica del supervisor y usa las herramientas reales."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> ModeloEnsayo:
        return self

    @property
    def _llm_type(self) -> str:
        return "ensayo"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._decidir(list(messages)))])

    async def _agenerate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)

    def _decidir(self, messages: list[BaseMessage]) -> AIMessage:
        system = _system(messages)
        if "Sos el supervisor" in system:
            return _ruta_supervisor(_last_human(messages))
        if "Sos el investigador" in system:
            return _ruta_investigador(messages)
        if "Sos el analista" in system:
            return _ruta_analista(messages)
        return AIMessage(content="FINALIZAR")


class ModeloBucle(BaseChatModel):
    """Siempre pide Investigador. El tope de pasos tiene que cortar."""

    def bind_tools(self, tools: Any, **kwargs: Any) -> ModeloBucle:
        return self

    @property
    def _llm_type(self) -> str:
        return "bucle"

    def _generate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        system = _system(list(messages))
        if "Sos el supervisor" in system:
            message = AIMessage(content="Investigador")
        else:
            message = AIMessage(content="Listo.")
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages: list[BaseMessage], **kwargs: Any) -> ChatResult:
        return self._generate(messages, **kwargs)


def _call(name: str, args: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def _system(messages: list[BaseMessage]) -> str:
    for message in messages:
        if message.type == "system" and isinstance(message.content, str):
            return message.content
    return ""


def _last_human(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if message.type == "human" and isinstance(message.content, str):
            return message.content
    return ""


def _tools_since_human(messages: list[BaseMessage]) -> list[BaseMessage]:
    collected: list[BaseMessage] = []
    for message in reversed(messages):
        if message.type == "human":
            break
        if message.type == "tool":
            collected.append(message)
    collected.reverse()
    return collected


def _ruta_supervisor(raw: str) -> AIMessage:
    data = json.loads(raw)
    investigacion = data["investigacion"]
    analisis = data["analisis"]
    if data["pasos"] > data["tope"]:
        return AIMessage(content="FINALIZAR")
    if investigacion is None:
        return AIMessage(content="Investigador")
    if analisis is None:
        return AIMessage(content="Analista")
    if analisis["suficiente"]:
        return AIMessage(content="FINALIZAR")
    if investigacion["muestra"] > analisis["muestra"]:
        return AIMessage(content="Analista")
    return AIMessage(content="Investigador")


def _ruta_investigador(messages: list[BaseMessage]) -> AIMessage:
    brief = _last_human(messages)
    produced = _tools_since_human(messages)
    names = [message.name for message in produced]
    if "buscar_resenas" not in names:
        consulta = "batería" if "muestra_actual: 0" in brief else "Notebook 14"
        return _call("buscar_resenas", {"consulta": consulta}, f"call-buscar-{consulta}")
    if "muestra_actual: 0" not in brief and "obtener_resena" not in names:
        payload = json.loads(produced[-1].content)
        return _call(
            "obtener_resena",
            {"resena_id": payload["resultados"][0]["id"]},
            "call-obtener",
        )
    return AIMessage(content="Listo.")


def _ruta_analista(messages: list[BaseMessage]) -> AIMessage:
    produced = _tools_since_human(messages)
    if any(message.name == "calcular_sentimiento" for message in produced):
        return AIMessage(content="Listo.")
    datos = json.loads(_last_human(messages).split("DATOS:", 1)[1])
    return _call(
        "calcular_sentimiento",
        {
            "producto": datos["producto"],
            "textos": datos["textos"],
            "umbral": datos["umbral"],
            "minimo_resenas": datos["minimo_resenas"],
        },
        "call-sentimiento",
    )


def _read(name: str) -> str:
    return (BASE_DIR / name).read_text(encoding="utf-8")


def _annotation_uses_add_messages() -> bool:
    hints = get_type_hints(AgentState, include_extras=True)
    metadata = getattr(hints["messages"], "__metadata__", ())
    return add_messages in metadata


def _class_bases(source: str, class_name: str) -> list[str]:
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == class_name)
    return [base.id for base in node.bases if isinstance(base, ast.Name)]


def collect_static_checks() -> list[Check]:
    state_source = _read("state.py")
    graph_source = _read("graph.py")
    research_source = _read("agents/research_agent.py")
    analyst_source = _read("agents/analyst_agent.py")
    readme = _read("README.md")
    env_example = _read(".env.example")
    requirements = _read("requirements.txt").lower()
    return [
        Check(
            "Estado hereda de MessagesState y acumula con add_messages",
            MessagesState in getattr(AgentState, "__orig_bases__", ()) and _annotation_uses_add_messages(),
            "AgentState(MessagesState); messages usa add_messages",
        ),
        Check(
            "La clase AgentState declara la herencia en el fuente",
            "MessagesState" in _class_bases(state_source, "AgentState"),
            "class AgentState(MessagesState)",
        ),
        Check(
            "El estado separa next, parcelas, pasos y cierre",
            all(token in state_source for token in ("next: Siguiente", "research:", "analysis:", "steps:", "task_completed:")),
            "next, research, analysis, steps, task_completed",
        ),
        Check(
            "Los artefactos validan score y textos con Pydantic",
            "ge=0, le=1" in state_source and "min_length=1" in state_source and "findings: list[str]" in state_source,
            "ResearchArtifact.findings y confidence; AnalysisArtifact.score",
        ),
        Check(
            "Grafo con supervisor, especialistas y arista condicional tipada",
            all(
                token in graph_source
                for token in (
                    "StateGraph(AgentState)",
                    'add_node("supervisor"',
                    'add_node("Investigador"',
                    'add_node("Analista"',
                    "add_conditional_edges",
                    "elegir_siguiente",
                    '"FINALIZAR": END',
                )
            ),
            "START -> supervisor -> Investigador | Analista | END",
        ),
        Check(
            "Cada especialista es un create_react_agent con sus herramientas",
            research_source.count("create_react_agent(") == 1
            and analyst_source.count("create_react_agent(") == 1
            and "buscar_resenas" in research_source
            and "obtener_resena" in research_source
            and "calcular_sentimiento" in analyst_source,
            "agents/research_agent.py y agents/analyst_agent.py",
        ),
        Check(
            "El investigador no escribe analysis y el analista no escribe research",
            'update["research"]' in research_source
            and '"analysis"' not in research_source
            and '"analysis":' in analyst_source
            and '["research"]' not in analyst_source,
            "cada nodo retorna solo su parcela",
        ),
        Check(
            "Las fichas se leen en paralelo",
            "asyncio.gather" in research_source,
            "buscar_resenas usa asyncio.gather",
        ),
        Check(
            "Un artefacto inválido se loguea y no se inyecta",
            "logger.warning" in research_source and "logger.warning" in analyst_source and "ValidationError" in research_source,
            "warning + parcela ausente",
        ),
        Check(
            "El supervisor tiene rúbrica, tope de pasos y síntesis",
            "Rúbrica" in graph_source and "max_steps" in graph_source and "def sintesis" in graph_source,
            "prompt de rúbrica y corte por pasos",
        ),
        Check(
            "Los briefs no arrastran el historial completo",
            "def brief_investigacion" in research_source and "def brief_analisis" in analyst_source and "def resumen_para_supervisor" in graph_source,
            "cada rol recibe su recorte",
        ),
        Check(
            "Sin secretos en el ejemplo de entorno",
            "sk-..." in env_example and "sk-" not in env_example.replace("sk-...", ""),
            ".env.example solo tiene el placeholder",
        ),
        Check(
            "Dependencias del grafo",
            "langgraph" in requirements and "langchain-openai" in requirements and "pydantic" in requirements,
            "requirements.txt",
        ),
        Check(
            "README explica la topología, el diagrama y la corrida",
            all(token in readme for token in ("```mermaid", "Jerárquica", "verificar_rubrica.py", "OPENAI_API_KEY")),
            "README.md",
        ),
    ]


def collect_trace_checks(trace: dict[str, Any], mermaid: str, loop: dict[str, Any]) -> list[Check]:
    eventos = trace["eventos"]
    llamadas = [event for event in eventos if event["tipo"] == "tool_call"]
    nombres = [event["nombre"] for event in llamadas]
    rutas = [event["content"] for event in eventos if event["tipo"] == "agente" and event["nombre"] == "Supervisor" and not str(event["content"]).startswith("Síntesis")]
    sintesis = next(event["content"] for event in eventos if event["tipo"] == "agente" and str(event["content"]).startswith("Síntesis"))
    research = trace["research"]
    analysis = trace["analysis"]
    busquedas = [event["args"]["consulta"] for event in llamadas if event["nombre"] == "buscar_resenas"]
    sentimiento = puntuar(
        research["findings"],
        producto=research["producto"],
        umbral=0.7,
        minimo_resenas=2,
    )
    return [
        Check(
            "El supervisor manda a investigar, analizar, refinar y cerrar",
            rutas == ["Investigador", "Analista", "Investigador", "Analista"],
            " -> ".join(rutas),
        ),
        Check(
            "La primera búsqueda es estrecha y la segunda abre el producto",
            busquedas == ["batería", "Notebook 14"] and "obtener_resena" in nombres,
            " -> ".join(nombres),
        ),
        Check(
            "La investigación final junta las tres reseñas del producto",
            research["muestra"] == 3
            and research["confidence"] == 0.9
            and research["fuentes"] == ["rev-nb-1", "rev-nb-2", "rev-nb-3"],
            ", ".join(research["fuentes"]),
        ),
        Check(
            "El análisis usa el score de la herramienta y alcanza el umbral",
            analysis["score"] == sentimiento["score"]
            and analysis["suficiente"] is True
            and analysis["destacar"] is True
            and analysis["sentimiento"] == "positivo"
            and trace["task_completed"] is True,
            f"score={analysis['score']} pasos={trace['steps']}",
        ),
        Check(
            "La síntesis cita la parcela y no inventa otro producto",
            "Notebook 14" in sintesis and f"{analysis['score']:.2f}" in sintesis and "Auriculares" not in sintesis,
            sintesis,
        ),
        Check(
            "Un supervisor que no corta igual frena en el tope",
            loop["next"] == "FINALIZAR" and loop["task_completed"] is False and loop["steps"] == 7,
            f"steps={loop['steps']} completed={loop['task_completed']}",
        ),
        Check(
            "El grafo compilado tiene las tres salidas del supervisor",
            all(token in mermaid for token in ("supervisor", "Investigador", "Analista")),
            "evidencia/grafo.mmd",
        ),
    ]


def collect_validation_checks() -> list[Check]:
    records: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Handler()
    logging.getLogger("orquestador.analista").addHandler(handler)
    invalido = ToolMessage(
        content=json.dumps(
            {
                "producto": "Notebook 14",
                "score": 2,
                "muestra": 2,
                "sentimiento": "positivo",
                "destacar": True,
                "suficiente": True,
            }
        ),
        name="calcular_sentimiento",
        tool_call_id="call-invalido",
    )
    try:
        artifact = armar_analisis([invalido])
    finally:
        logging.getLogger("orquestador.analista").removeHandler(handler)
    vacia = asyncio.run(buscar_resenas.ainvoke({"consulta": "producto-inexistente"}))
    payload = json.loads(vacia)
    sin_fuentes = armar_investigacion(
        [
            ToolMessage(content=vacia, name="buscar_resenas", tool_call_id="call-vacia"),
        ]
    )
    return [
        Check(
            "Un score fuera de rango no entra al estado y queda en el log",
            artifact is None and any("artefacto inválido" in message for message in records),
            records[-1] if records else "sin log",
        ),
        Check(
            "Una búsqueda vacía no fabrica reseñas",
            payload["muestra"] == 0 and "error" in payload and sin_fuentes is None,
            payload["error"],
        ),
    ]


async def _loop_trace() -> dict[str, Any]:
    app = build_graph(ModeloBucle())
    return await correr(app, modelo="ensayo-bucle", generador="verificar_rubrica.py")


def _write_report(checks: list[Check]) -> None:
    lines = ["Verificación local de la pre-entrega 6", ""]
    for check in checks:
        mark = "OK" if check.passed else "FALLO"
        lines.append(f"[{mark}] {check.criterion}")
        lines.append(f"    {check.evidence}")
    failed = [check for check in checks if not check.passed]
    lines.append("")
    lines.append(f"Resultado: {len(checks) - len(failed)}/{len(checks)}")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    static_checks = collect_static_checks()
    app = build_graph(ModeloEnsayo())
    mermaid = app.get_graph().draw_mermaid()
    MERMAID_PATH.parent.mkdir(parents=True, exist_ok=True)
    MERMAID_PATH.write_text(mermaid, encoding="utf-8")
    trace = asyncio.run(correr(app, modelo="ensayo-determinista", generador="verificar_rubrica.py"))
    loop = asyncio.run(_loop_trace())
    entrada.guardar(trace)
    checks = [
        *static_checks,
        *collect_trace_checks(trace, mermaid, loop),
        *collect_validation_checks(),
    ]
    _write_report(checks)
    for check in checks:
        mark = "OK" if check.passed else "FALLO"
        print(f"[{mark}] {check.criterion}")
        if not check.passed:
            print(f"      {check.evidence}")
    failed = [check for check in checks if not check.passed]
    if failed:
        raise SystemExit(f"{len(failed)} criterio(s) en fallo. Ver {REPORT_PATH}")
    print(render_log(trace))
    print(f"Trazos en {entrada.TRACE_PATH}")
    print(f"Informe en {REPORT_PATH}")


if __name__ == "__main__":
    main()
