"""Herramientas del agente. El modelo elige cuál llamar leyendo el docstring y el esquema."""

from __future__ import annotations

import asyncio
import json

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from orders_db import get_order, search_orders


class BuscarPedidosInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cliente_id: int = Field(
        gt=0,
        description=(
            "Identificador numérico del cliente, mayor que 0. "
            "Ejemplo: 102. No uses 0 ni un texto vacío."
        ),
    )


class ObtenerPedidoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pedido_id: str = Field(
        min_length=1,
        description=(
            "Identificador de un pedido ya devuelto por buscar_pedidos. "
            "Formato PED-102-3. No lo inventes."
        ),
    )


def _dump(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False)


@tool(args_schema=BuscarPedidosInput)
async def buscar_pedidos(cliente_id: int) -> str:
    """
    Busca en la base de pedidos cuántas compras hizo un cliente y cuál fue el total.

    Usala cuando pregunten por cantidad de pedidos, facturación o el identificador
    del primer o del último pedido. No devuelve productos: el campo completo queda
    en false y la nota indica que falta obtener_pedido.

    Límites: solo lectura. cliente_id tiene que ser un entero mayor que 0.
    No busca por nombre de cliente ni por producto.

    Returns:
        JSON con pedidos, total, total_texto, primer_pedido_id, ultimo_pedido_id
        y pedido_ids. Si el cliente no existe, JSON con error y completo=false
        para que pidas otro identificador o corrijas el argumento y vuelvas a llamar.
    """
    try:
        payload = await asyncio.to_thread(search_orders, cliente_id)
    except Exception as exc:
        payload = {
            "error": f"Error al consultar pedidos: {exc}",
            "completo": False,
        }
    return _dump(payload)


@tool(args_schema=ObtenerPedidoInput)
async def obtener_pedido(pedido_id: str) -> str:
    """
    Trae la fecha, el total y los productos de un pedido concreto.

    Usala después de buscar_pedidos, cuando la pregunta pida qué se compró,
    el detalle o el contenido del primer o del último pedido. El pedido_id
    tiene que salir de primer_pedido_id, ultimo_pedido_id o pedido_ids.

    Límites: solo lectura. No lista todos los pedidos de un cliente.
    Si el id no existe, el JSON trae error y completo=false: volvé a llamar
    con un id que sí haya devuelto buscar_pedidos, o pedí el dato al usuario.

    Returns:
        JSON con pedido_id, cliente_id, fecha, total, total_texto y productos
        (lista de producto y cantidad). completo=true cuando el detalle está.
    """
    try:
        payload = await asyncio.to_thread(get_order, pedido_id)
    except Exception as exc:
        payload = {
            "error": f"Error al consultar el pedido: {exc}",
            "completo": False,
        }
    return _dump(payload)


TOOLS = [buscar_pedidos, obtener_pedido]
