"""Fichas de reseña. La búsqueda es por solapamiento de tokens, en paralelo entre archivos."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from app.settings import settings

_TOKEN = re.compile(r"[a-záéíóúüñ0-9]+", re.IGNORECASE)
_VACIAS = frozenset(
    {
        "para",
        "como",
        "esta",
        "este",
        "tiene",
        "solo",
        "cuando",
        "donde",
        "desde",
        "hasta",
        "sobre",
        "entre",
        "porque",
        "cual",
        "cuál",
        "pero",
        "tambien",
        "también",
        "hay",
        "son",
        "las",
        "los",
        "del",
        "una",
        "uno",
        "que",
        "con",
        "por",
    }
)


async def buscar_fichas(consulta: str) -> list[dict]:
    carpeta = settings.corpus_dir
    if not carpeta.is_dir():
        return []
    archivos = sorted(carpeta.glob("*.json"))
    fichas = await asyncio.gather(*(_leer(path) for path in archivos))
    claves = [token for token in _tokens(consulta) if len(token) >= 4 and token not in _VACIAS]
    if not claves:
        return []
    coincidencias: list[tuple[int, dict]] = []
    for ficha in fichas:
        if ficha is None:
            continue
        blob = _normalizar(
            " ".join(
                [
                    str(ficha.get("producto", "")),
                    str(ficha.get("texto", "")),
                    " ".join(ficha.get("aspectos") or []),
                ]
            )
        )
        puntaje = sum(1 for clave in claves if clave in blob)
        if puntaje:
            coincidencias.append((puntaje, ficha))
    coincidencias.sort(key=lambda item: item[0], reverse=True)
    return [ficha for _puntaje, ficha in coincidencias]


async def leer_ficha(resena_id: str) -> dict | None:
    path = settings.corpus_dir / f"{resena_id}.json"
    return await _leer(path)


async def _leer(path: Path) -> dict | None:
    if not path.is_file():
        return None

    def _cargar() -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    return await asyncio.to_thread(_cargar)


def _tokens(texto: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(texto)]


def _normalizar(texto: str) -> str:
    return " ".join(_tokens(texto))
