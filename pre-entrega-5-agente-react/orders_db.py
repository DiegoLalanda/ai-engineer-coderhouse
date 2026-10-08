"""Base SQLite de pedidos. La crea el proceso la primera vez que una herramienta consulta."""

from __future__ import annotations

import sqlite3
from typing import Any

from settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS pedidos (
    pedido_id TEXT PRIMARY KEY,
    cliente_id INTEGER NOT NULL,
    total INTEGER NOT NULL,
    fecha TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id TEXT NOT NULL,
    producto TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos (pedido_id)
);
"""

SEED_PEDIDOS: tuple[tuple[str, int, int, str], ...] = (
    ("PED-102-1", 102, 2000, "2025-03-02"),
    ("PED-102-2", 102, 4500, "2025-06-18"),
    ("PED-102-3", 102, 8000, "2025-09-01"),
    ("PED-215-1", 215, 3200, "2025-08-12"),
)

SEED_ITEMS: tuple[tuple[str, str, int], ...] = (
    ("PED-102-1", "Teclado mecánico", 1),
    ("PED-102-2", "Monitor 27 pulgadas", 1),
    ("PED-102-3", "Notebook 14 pulgadas", 1),
    ("PED-215-1", "Auriculares", 1),
)


def pesos(value: int) -> str:
    return "$" + f"{value:,}".replace(",", ".")


def init_orders_db() -> None:
    settings.orders_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.orders_db) as connection:
        connection.executescript(SCHEMA)
        existing = connection.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
        if existing:
            return
        connection.executemany(
            "INSERT INTO pedidos (pedido_id, cliente_id, total, fecha) VALUES (?, ?, ?, ?)",
            SEED_PEDIDOS,
        )
        connection.executemany(
            "INSERT INTO items (pedido_id, producto, cantidad) VALUES (?, ?, ?)",
            SEED_ITEMS,
        )
        total_102 = connection.execute(
            "SELECT COALESCE(SUM(total), 0) FROM pedidos WHERE cliente_id = 102"
        ).fetchone()[0]
        if total_102 != 14500:
            raise RuntimeError(f"El total del cliente 102 quedó en {total_102}, se esperaba 14500.")


def _connect() -> sqlite3.Connection:
    init_orders_db()
    connection = sqlite3.connect(settings.orders_db)
    connection.row_factory = sqlite3.Row
    return connection


def search_orders(cliente_id: int) -> dict[str, Any]:
    with _connect() as connection:
        rows = connection.execute(
            """
            SELECT pedido_id, total, fecha
            FROM pedidos
            WHERE cliente_id = ?
            ORDER BY fecha ASC, pedido_id ASC
            """,
            (cliente_id,),
        ).fetchall()
    if not rows:
        return {
            "error": (
                f"No hay pedidos para el cliente {cliente_id}. "
                "Confirmá el identificador antes de reintentar."
            ),
            "completo": False,
        }
    total = sum(int(row["total"]) for row in rows)
    pedido_ids = [str(row["pedido_id"]) for row in rows]
    return {
        "cliente_id": cliente_id,
        "pedidos": len(rows),
        "total": total,
        "total_texto": pesos(total),
        "moneda": "ARS",
        "primer_pedido_id": pedido_ids[0],
        "ultimo_pedido_id": pedido_ids[-1],
        "pedido_ids": pedido_ids,
        "productos": None,
        "completo": False,
        "nota": (
            "Información incompleta para listar productos. "
            "Llamá a obtener_pedido con un pedido_id de esta respuesta. "
            "No inventes el identificador."
        ),
    }


def get_order(pedido_id: str) -> dict[str, Any]:
    with _connect() as connection:
        order = connection.execute(
            """
            SELECT pedido_id, cliente_id, total, fecha
            FROM pedidos
            WHERE pedido_id = ?
            """,
            (pedido_id,),
        ).fetchone()
        if order is None:
            return {
                "error": (
                    f"No existe el pedido {pedido_id}. "
                    "Usá un pedido_id devuelto por buscar_pedidos."
                ),
                "completo": False,
            }
        items = connection.execute(
            """
            SELECT producto, cantidad
            FROM items
            WHERE pedido_id = ?
            ORDER BY id ASC
            """,
            (pedido_id,),
        ).fetchall()
    return {
        "pedido_id": str(order["pedido_id"]),
        "cliente_id": int(order["cliente_id"]),
        "fecha": str(order["fecha"]),
        "total": int(order["total"]),
        "total_texto": pesos(int(order["total"])),
        "moneda": "ARS",
        "productos": [
            {"producto": str(item["producto"]), "cantidad": int(item["cantidad"])}
            for item in items
        ],
        "completo": True,
    }
