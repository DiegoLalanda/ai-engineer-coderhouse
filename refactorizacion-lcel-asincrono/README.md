# Ejercicio: Refactorización a LCEL Asíncrono

Curso **AI Engineer** (Coderhouse) — Módulo 2: *Encadenamiento lógico: orquestación con LangChain*.

Migra la llamada **imperativa** al SDK del Módulo 1 (`AsyncOpenAI` / `AsyncLLMManager`) a una cadena **declarativa** con LCEL: `ChatPromptTemplate | ChatOpenAI | StrOutputParser`, ejecutada con `await chain.ainvoke(...)`.

## Requisitos

- Python 3.12+
- API key de OpenAI (`OPENAI_API_KEY`)

## Entorno

Este proyecto reutiliza el entorno virtual de `ai-engineer-coderhouse/.venv`. Desde la carpeta raíz del repo:

```powershell
py -3.12 -m venv .venv          # si todavía no existe
.\.venv\Scripts\Activate.ps1
pip install -r refactorizacion-lcel-asincrono\requirements.txt
```

Después, dentro de esta carpeta:

```powershell
cd refactorizacion-lcel-asincrono
copy .env.example .env
notepad .env    # completá OPENAI_API_KEY (podés reutilizar la de la pre-entrega 1)
python main.py
```

## Variables de entorno (`.env`)

| Variable | Obligatoria | Descripción |
| --- | --- | --- |
| `OPENAI_API_KEY` | Sí | API key de OpenAI |
| `OPENAI_MODEL` | No (default `gpt-4o-mini`) | Modelo que usa `ChatOpenAI` |

## Qué cubre el script

| Paso del enunciado | Implementación |
| --- | --- |
| Sustituir el SDK crudo | `ChatOpenAI(model=..., temperature=0)` en lugar de `AsyncOpenAI` |
| Prompt con roles | `ChatPromptTemplate.from_messages` con `system` y `human` |
| Variable de entrada | `{pregunta}` en el mensaje human; `ainvoke({"pregunta": "..."})` |
| Cadena LCEL | `chain = prompt \| model \| parser` |
| Texto plano | `StrOutputParser()` extrae `.content` del `AIMessage` |
| Ejecución async | `async def main` + `await chain.ainvoke(...)` + `asyncio.run` |

La pregunta de prueba es: *"¿Qué ventaja tiene LCEL frente a llamar al SDK de OpenAI a mano?"*

## Cómo encaja con el Módulo 1

En [pre-entrega-1-cliente-llm-async](../pre-entrega-1-cliente-llm-async) el flujo era: armar mensajes a mano → `await manager.generate(...)` → leer `respuesta.content`. Acá LangChain orquesta el mismo camino (formatear prompt, llamar al modelo, parsear) con el operador `|`. El `ainvoke` sigue siendo async, como el cliente del Módulo 1: no se bloquea el event loop mientras OpenAI responde.

## Criterios de aceptación

- El flujo principal usa solo LCEL (`|`), no un `if`/`for` que arme la llamada al modelo.
- La cadena se ejecuta con `await chain.ainvoke(...)`.
- La salida impresa es un **string** (gracias a `StrOutputParser`), no un `AIMessage`.
- El prompt define roles System y Human.
