# AI Engineer — Coderhouse

Monorepo con las actividades, ejercicios y pre-entregas del curso **AI Engineer** (Coderhouse).

Cada unidad vive en su propia carpeta, con su `README.md` y sus dependencias. El entorno virtual compartido está en la raíz (`.venv`, Python 3.12) y no se versiona.

**Repo:** [github.com/DiegoLalanda/ai-engineer-coderhouse](https://github.com/DiegoLalanda/ai-engineer-coderhouse)

## Cómo está organizado

| Carpeta | Módulo | Tipo | Qué es |
| --- | --- | --- | --- |
| [orquestador-concurrente](./orquestador-concurrente) | 1 · Arquitectura asíncrona | Ejercicio | Orquestador con `asyncio.gather`, timeout y semáforo (sin API keys). |
| [pre-entrega-1-cliente-llm-async](./pre-entrega-1-cliente-llm-async) | 1 · Interfaz base de LLMs | Pre-entrega | Unified Async LLM Client: OpenAI + Anthropic, streaming, Pydantic y errores controlados. |
| [refactorizacion-lcel-asincrono](./refactorizacion-lcel-asincrono) | 2 · Encadenamiento lógico | Ejercicio | Cadena LCEL asíncrona: `ChatPromptTemplate \| ChatOpenAI \| StrOutputParser` con `ainvoke`. |
| [pre-entrega-2-pipeline-validado](./pre-entrega-2-pipeline-validado) | 2 · Salidas estructuradas | Pre-entrega | Extracción técnica asíncrona con LCEL, Pydantic, structured output y reintentos de validación. |
| [pre-entrega-3-rag-local](./pre-entrega-3-rag-local) | 2 · RAG y memoria vectorial | Pre-entrega | Ingesta incremental, ChromaDB persistente, retrieval local y generación grounded asíncrona con LCEL + Pydantic. |

Las próximas pre-entregas (LangChain, RAG, agentes, multi-agente, API de producción y el capstone) se irán sumando como carpetas hermanas, sin mezclar código entre actividades.

## Entregas puntuales

Si un corrector necesita **solo** una actividad, puede entrar directo a su carpeta:

- Pre-entrega 1: [pre-entrega-1-cliente-llm-async](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-1-cliente-llm-async)
- Orquestador concurrente: [orquestador-concurrente](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/orquestador-concurrente)
- Refactorización a LCEL asíncrono: [refactorizacion-lcel-asincrono](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/refactorizacion-lcel-asincrono)
- Pre-entrega 2 — Pipeline validado: [pre-entrega-2-pipeline-validado](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-2-pipeline-validado)
- Pre-entrega 3 — RAG local: [pre-entrega-3-rag-local](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-3-rag-local)

La explicación de cómo correr cada una (variables de entorno, dependencias, comando de prueba) está en el `README.md` de esa carpeta. No hay informe aparte.

## Entorno compartido

Desde la raíz del repo:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Después, instalá las dependencias de la actividad que vayas a correr. Por ejemplo, para la pre-entrega 1:

```powershell
pip install -r pre-entrega-1-cliente-llm-async\requirements.txt
cd pre-entrega-1-cliente-llm-async
copy .env.example .env
python main.py
```

El orquestador no tiene dependencias externas: alcanza con Python 3.12.

```powershell
cd orquestador-concurrente
python orquestador_concurrente.py
```

Para el ejercicio de LCEL (Módulo 2):

```powershell
pip install -r refactorizacion-lcel-asincrono\requirements.txt
cd refactorizacion-lcel-asincrono
copy .env.example .env
python main.py
```

Para la pre-entrega 2 (pipeline validado):

```powershell
pip install -r pre-entrega-2-pipeline-validado\requirements.txt
cd pre-entrega-2-pipeline-validado
copy .env.example .env
python demo.py
```

Para la pre-entrega 3 (RAG local):

```powershell
pip install -r pre-entrega-3-rag-local\requirements.txt
cd pre-entrega-3-rag-local
copy .env.example .env
python ingest.py
python rag.py
```

## Autor

Diego Lalanda — curso AI Engineer, Coderhouse.
