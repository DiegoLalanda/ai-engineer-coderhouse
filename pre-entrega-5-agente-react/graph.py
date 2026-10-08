"""StateGraph ReAct. El modelo decide las herramientas; el grafo solo enruta."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from settings import settings
from tools import TOOLS

SYSTEM_PROMPT = """
Sos un agente de consultas comerciales. Respondé en español, corto y con los datos de las herramientas.

Elegí vos qué herramienta llamar. No hay una ruta fija.
- buscar_pedidos devuelve cantidad, total e identificadores. No devuelve productos.
- Si preguntan qué se compró, el detalle, el primero o el último, y buscar_pedidos
  dice que la información está incompleta, llamá a obtener_pedido con el pedido_id
  que acaba de devolverte. No inventes ese id.
- Si una herramienta devuelve error, argumentos inválidos o completo=false,
  corregí la llamada y reintentá, o pedile al usuario el dato que falta.
- No reutilices un cliente de otra conversación. Si esta sesión no lo menciona,
  preguntá el identificador.
- No inventes pedidos, totales ni productos.
""".strip()

CONTEXT_WINDOW = 20


class AgentState(MessagesState):
    """Historial de la sesión. messages se acumula con add_messages, no se pisa."""

    messages: Annotated[list[BaseMessage], add_messages]


def recent_messages(messages: Sequence[BaseMessage], limit: int = CONTEXT_WINDOW) -> list[BaseMessage]:
    """Recorta lo que ve el modelo. El checkpoint conserva la sesión completa."""
    if len(messages) <= limit:
        return list(messages)
    start = len(messages) - limit
    while start > 0 and messages[start].type == "tool":
        start -= 1
    return list(messages[start:])


def build_graph(
    checkpointer: BaseCheckpointSaver[Any],
    chat_model: BaseChatModel | Runnable[Any, Any],
) -> CompiledStateGraph[AgentState, Any, AgentState, AgentState]:
    bound_model = chat_model.bind_tools(TOOLS, parallel_tool_calls=False)
    tool_node = ToolNode(TOOLS, handle_tool_errors=True)

    async def call_model(state: AgentState) -> dict[str, list[AIMessage]]:
        response = await bound_model.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), *recent_messages(state["messages"])]
        )
        return {"messages": [response]}

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "tools", END: END},
    )
    workflow.add_edge("tools", "agent")
    return workflow.compile(checkpointer=checkpointer)


def config_for(thread_id: str) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": settings.recursion_limit,
    }
