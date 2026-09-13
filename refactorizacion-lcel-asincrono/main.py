"""
Ejercicio: Refactorización a LCEL Asíncrono
Curso AI Engineer — Coderhouse (Módulo 2 · Encadenamiento lógico)

Migra la llamada imperativa al SDK (Módulo 1) a una cadena declarativa LCEL:
ChatPromptTemplate → ChatOpenAI → StrOutputParser, ejecutada con ainvoke.

Ejecutar:
    python main.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv(Path(__file__).resolve().parent / ".env")

# ---------------------------------------------------------------------------
# 1. Prompt con roles (System / Human) y una variable de entrada
# ---------------------------------------------------------------------------
# from_messages (no from_template): el system fija el comportamiento y el
# human inyecta {pregunta}. Esa clave tiene que coincidir con el dict de ainvoke.
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Sos un tutor de AI Engineering. Respondé en español, en un "
            "párrafo breve y claro, sin listas ni títulos.",
        ),
        ("human", "{pregunta}"),
    ]
)

# Extrae .content del AIMessage. Sin esto, ainvoke devolvería el objeto, no texto.
parser = StrOutputParser()


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Falta OPENAI_API_KEY. Copiá .env.example a .env y completá la clave.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ChatOpenAI reemplaza al SDK crudo del Módulo 1. Lee OPENAI_API_KEY del
    # entorno. `model` es el nombre actual del parámetro (`model_name` es alias).
    model = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0,
    )

    # Cadena LCEL: la salida de cada Runnable es la entrada del siguiente.
    chain = prompt | model | parser

    # El dict tiene que matchear las {variables} del prompt. await es obligatorio:
    # sin él, ainvoke devuelve una corrutina, no el string.
    resultado = await chain.ainvoke(
        {"pregunta": "¿Qué ventaja tiene LCEL frente a llamar al SDK de OpenAI a mano?"}
    )
    print(resultado)


if __name__ == "__main__":
    asyncio.run(main())
