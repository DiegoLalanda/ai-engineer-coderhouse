"""Comprueba la rúbrica sin API key y deja la traza del ciclo en evidencia/.

    python verificar_rubrica.py
"""

from __future__ import annotations

import ast
import asyncio
import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import get_type_hints

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages

import demo
from demo import TURNOS
from graph import AgentState, build_graph, recent_messages
from session import Turno
from orders_db import get_order, init_orders_db, search_orders
from session import correr_turnos
from settings import BASE_DIR

REPORT_PATH = BASE_DIR / "evidencia" / "verificacion.txt"


@dataclass
class Check:
    criterion: str
    passed: bool
    evidence: str


class ModeloEnsayo:
    """Sustituto determinista para ejercer el grafo real sin gastar API."""

    def bind_tools(self, tools: object, **kwargs: object) -> ModeloEnsayo:
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        text = _last_human(messages).lower()
        produced = _tools_since_human(messages)
        names = [message.name for message in produced]
        history_has_102 = _history_has_client(messages)

        if "primero" in text:
            if not history_has_102:
                return AIMessage(content="¿De qué cliente es el primer pedido?")
            if "obtener_pedido" not in names:
                return _call("obtener_pedido", {"pedido_id": "PED-102-1"}, "call-primero")
            return AIMessage(content=_detalle(produced[-1].content, "El primer pedido"))

        if "999" in text:
            if "buscar_pedidos" not in names:
                return _call("buscar_pedidos", {"cliente_id": 999}, "call-999")
            return AIMessage(
                content=(
                    "No hay pedidos para el cliente 999. "
                    "Pasame otro identificador si querés que vuelva a buscar."
                )
            )

        if "compr" in text and "102" in text:
            if "buscar_pedidos" not in names:
                return _call("buscar_pedidos", {"cliente_id": 102}, "call-buscar")
            if "obtener_pedido" not in names:
                payload = json.loads(produced[-1].content)
                return _call(
                    "obtener_pedido",
                    {"pedido_id": payload["ultimo_pedido_id"]},
                    "call-ultimo",
                )
            search = json.loads(produced[0].content)
            detail = json.loads(produced[-1].content)
            product = detail["productos"][0]["producto"]
            return AIMessage(
                content=(
                    f"El cliente 102 tuvo {search['pedidos']} pedidos "
                    f"por un total de {search['total_texto']}. "
                    f"En el último, {detail['pedido_id']}, se compró {product}."
                )
            )

        if "102" in text and "total" in text:
            successful = _successful_search(produced)
            if successful is None and "buscar_pedidos" not in names:
                return _call("buscar_pedidos", {"cliente_id": 0}, "call-invalido")
            if successful is None:
                return _call("buscar_pedidos", {"cliente_id": 102}, "call-reintento")
            return AIMessage(
                content=(
                    f"El cliente 102 tuvo {successful['pedidos']} pedidos "
                    f"por un total de {successful['total_texto']}."
                )
            )

        if "ultimo" in text or "último" in text:
            if not history_has_102 and "102" not in text:
                return AIMessage(
                    content="¿De qué cliente? Necesito el identificador numérico."
                )
            if "obtener_pedido" not in names:
                return _call("obtener_pedido", {"pedido_id": "PED-102-3"}, "call-ultimo-suelto")
            return AIMessage(content=_detalle(produced[-1].content, "El último pedido"))

        return AIMessage(content="¿De qué cliente querés que consulte los pedidos?")


def _call(name: str, args: dict[str, object], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


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


def _history_has_client(messages: list[BaseMessage]) -> bool:
    last_human_seen = False
    for message in reversed(messages):
        if message.type == "human" and not last_human_seen:
            last_human_seen = True
            continue
        if message.type == "tool" and isinstance(message.content, str) and '"cliente_id": 102' in message.content:
            return True
    return False


def _successful_search(messages: list[BaseMessage]) -> dict[str, object] | None:
    for message in messages:
        if message.name != "buscar_pedidos" or not isinstance(message.content, str):
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            continue
        if "pedidos" in payload:
            return payload
    return None


def _detalle(raw: str, label: str) -> str:
    payload = json.loads(raw)
    product = payload["productos"][0]["producto"]
    return (
        f"{label} {payload['pedido_id']} es del cliente {payload['cliente_id']} "
        f"e incluye {product}, por {payload['total_texto']}."
    )


def _read(name: str) -> str:
    return (BASE_DIR / name).read_text(encoding="utf-8")


def _annotation_uses_add_messages() -> bool:
    hints = get_type_hints(AgentState, include_extras=True)
    metadata = getattr(hints["messages"], "__metadata__", ())
    return add_messages in metadata


def _window_keeps_tool_pair() -> bool:
    calls = AIMessage(
        content="",
        tool_calls=[{"name": "buscar_pedidos", "args": {"cliente_id": 102}, "id": "1", "type": "tool_call"}],
    )
    from langchain_core.messages import ToolMessage

    messages: list[BaseMessage] = [
        AIMessage(content=f"relleno {index}") for index in range(20)
    ]
    messages.extend(
        [
            calls,
            ToolMessage(content="{}", name="buscar_pedidos", tool_call_id="1"),
        ]
    )
    window = recent_messages(messages, limit=2)
    return window[0] is calls and window[1].type == "tool"


async def _run_graph(checkpoint: Path) -> dict[str, object]:
    retry = [
        *TURNOS,
        Turno(
            nombre="reintento tras dato invalido",
            thread_id="sesion-reintento",
            pregunta="¿Cuántos pedidos tuvo el cliente 102 y cuál fue el total?",
        ),
    ]
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint)) as checkpointer:
        app = build_graph(checkpointer, ModeloEnsayo())
        trace = await correr_turnos(
            app,
            retry,
            modelo="ensayo-determinista",
            generador="verificar_rubrica.py",
        )
    return trace


def _case(trace: dict[str, object], name: str) -> dict[str, object]:
    for case in trace["casos"]:  # type: ignore[index]
        if case["nombre"] == name:
            return case
    raise KeyError(name)


def collect_static_checks() -> list[Check]:
    graph_source = _read("graph.py")
    tools_source = _read("tools.py")
    demo_source = _read("demo.py")
    env_example = _read(".env.example")
    readme = _read("README.md")
    requirements = _read("requirements.txt").lower()
    graph_tree = ast.parse(graph_source)
    agent_state = next(
        node
        for node in graph_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "AgentState"
    )
    summary = search_orders(102)
    missing = search_orders(999)
    detail = get_order("PED-102-3")
    return [
        Check(
            "Estado hereda de MessagesState y acumula con add_messages",
            MessagesState in getattr(AgentState, "__orig_bases__", ()) and _annotation_uses_add_messages(),
            "AgentState(MessagesState); messages usa add_messages",
        ),
        Check(
            "La clase AgentState declara la herencia en el fuente",
            any(isinstance(base, ast.Name) and base.id == "MessagesState" for base in agent_state.bases),
            "class AgentState(MessagesState)",
        ),
        Check(
            "Grafo con nodo agent, ToolNode y tools_condition hacia END",
            all(
                token in graph_source
                for token in (
                    "StateGraph(AgentState)",
                    'add_node("agent"',
                    'add_node("tools"',
                    "tools_condition",
                    "ToolNode",
                    "END",
                )
            ),
            "START -> agent -> tools_condition -> tools -> agent, o END",
        ),
        Check(
            "Persistencia SQLite asíncrona y recursion_limit",
            "AsyncSqliteSaver" in demo_source
            and "SqliteSaver" in demo_source
            and "recursion_limit" in graph_source,
            "AsyncSqliteSaver.from_conn_string; SqliteSaver síncrono no sirve para ainvoke",
        ),
        Check(
            "Herramientas con @tool, esquema y docstring",
            tools_source.count("@tool(args_schema=") == 2
            and "gt=0" in tools_source
            and "min_length=1" in tools_source
            and "Returns:" in tools_source
            and "except Exception" in tools_source,
            "buscar_pedidos y obtener_pedido",
        ),
        Check(
            "LLM real vinculado en la corrida con API",
            "ChatOpenAI" in demo_source and "bind_tools" in graph_source,
            "demo.py instancia ChatOpenAI; build_graph hace bind_tools",
        ),
        Check(
            "Sin secretos en el ejemplo de entorno",
            "sk-..." in env_example and "sk-" not in env_example.replace("sk-...", ""),
            ".env.example solo tiene el placeholder",
        ),
        Check(
            "Dependencias del grafo y del checkpointer",
            "langgraph" in requirements and "langgraph-checkpoint-sqlite" in requirements,
            "requirements.txt",
        ),
        Check(
            "README explica entorno, thread_id y traza",
            all(token in readme for token in ("OPENAI_API_KEY", "thread_id", "traza_react.json", "verificar_rubrica.py")),
            "README.md",
        ),
        Check(
            "La base del cliente 102 suma 3 pedidos y $14.500",
            summary["pedidos"] == 3 and summary["total"] == 14500 and summary["completo"] is False,
            f"ultimo={summary['ultimo_pedido_id']} total={summary['total_texto']}",
        ),
        Check(
            "Un cliente inexistente vuelve como error, no como excepción",
            "error" in missing and missing["completo"] is False,
            str(missing["error"]),
        ),
        Check(
            "El detalle del último pedido trae el producto",
            detail["completo"] is True and detail["productos"][0]["producto"] == "Notebook 14 pulgadas",
            detail["pedido_id"],
        ),
        Check(
            "La ventana de contexto no corta un par herramienta",
            _window_keeps_tool_pair(),
            "recent_messages retrocede si el corte cae en un ToolMessage",
        ),
    ]


def collect_trace_checks(trace: dict[str, object], checkpoint: Path) -> list[Check]:
    multi = _case(trace, "razonamiento multi-paso")
    memory = _case(trace, "misma sesion")
    other = _case(trace, "otra sesion")
    error = _case(trace, "error y aclaracion")
    retry = _case(trace, "reintento tras dato invalido")
    multi_names = [event["nombre"] for event in multi["eventos"] if event["tipo"] == "tool_call"]
    retry_args = [event["args"] for event in retry["eventos"] if event["tipo"] == "tool_call"]
    with sqlite3.connect(checkpoint) as connection:
        threads = {
            row[0]
            for row in connection.execute("SELECT DISTINCT thread_id FROM checkpoints")
        }
    answer_multi = next(event["content"] for event in multi["eventos"] if event["tipo"] == "respuesta")
    answer_memory = next(event["content"] for event in memory["eventos"] if event["tipo"] == "respuesta")
    answer_other = next(event["content"] for event in other["eventos"] if event["tipo"] == "respuesta")
    answer_error = next(event["content"] for event in error["eventos"] if event["tipo"] == "respuesta")
    return [
        Check(
            "Un turno llama herramientas dos veces antes de cerrar",
            multi["herramientas_invocadas"] >= 2 and multi_names == ["buscar_pedidos", "obtener_pedido"],
            " -> ".join(multi_names),
        ),
        Check(
            "La respuesta usa el total y el producto devueltos por la base",
            "14.500" in answer_multi and "Notebook 14 pulgadas" in answer_multi,
            answer_multi,
        ),
        Check(
            "El mismo thread_id recuerda el cliente y busca el primer pedido",
            memory["thread_id"] == multi["thread_id"]
            and memory["herramientas_invocadas"] == 1
            and "Teclado mecánico" in answer_memory
            and "102" in answer_memory,
            answer_memory,
        ),
        Check(
            "Otro thread_id no hereda la sesión y pide el cliente",
            other["thread_id"] != multi["thread_id"]
            and other["herramientas_invocadas"] == 0
            and "102" not in answer_other,
            answer_other,
        ),
        Check(
            "Un error de la herramienta vuelve al agente, que pide una aclaración",
            error["herramientas_invocadas"] == 1 and "999" in answer_error,
            answer_error,
        ),
        Check(
            "Un argumento inválido se reintenta en el ciclo, sin if/else de ruteo",
            [args.get("cliente_id") for args in retry_args] == [0, 102],
            str(retry_args),
        ),
        Check(
            "Sqlite guarda los thread_id por separado",
            {"sesion-102", "sesion-vacia", "sesion-999", "sesion-reintento"} <= threads,
            ", ".join(sorted(threads)),
        ),
    ]


def _write_report(checks: list[Check]) -> None:
    lines = ["Verificación local de la pre-entrega 5", ""]
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
    init_orders_db()
    static_checks = collect_static_checks()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        checkpoint = Path(directory) / "checkpoints.sqlite"
        trace = asyncio.run(_run_graph(checkpoint))
        trace_checks = collect_trace_checks(trace, checkpoint)
    demo.guardar(trace)
    checks = [*static_checks, *trace_checks]
    _write_report(checks)
    for check in checks:
        mark = "OK" if check.passed else "FALLO"
        print(f"[{mark}] {check.criterion}")
        if not check.passed:
            print(f"      {check.evidence}")
    failed = [check for check in checks if not check.passed]
    if failed:
        raise SystemExit(f"{len(failed)} criterio(s) en fallo. Ver {REPORT_PATH}")
    print(f"Trazos en {demo.TRACE_PATH}")
    print(f"Informe en {REPORT_PATH}")


if __name__ == "__main__":
    main()
