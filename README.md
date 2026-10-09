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
| [pre-entrega-4-rag-pinecone](./pre-entrega-4-rag-pinecone) | 4 · RAG en la nube | Pre-entrega | Índice Pinecone serverless, recuperador híbrido BM25 + vectores y evaluación Precision@5 / Recall@5. |
| [pre-entrega-5-agente-react](./pre-entrega-5-agente-react) | 5 · Agentes | Pre-entrega | Agente ReAct asíncrono, herramientas sobre SQLite y memoria con `AsyncSqliteSaver` + `thread_id`. |
| [pre-entrega-6-orquestador-multiagente](./pre-entrega-6-orquestador-multiagente) | 6 · Multi-agente | Pre-entrega | Supervisor jerárquico, investigador y analista con estado compartido y corte por pasos. |
| [pre-entrega-7-api-agente](./pre-entrega-7-api-agente) | 7 · API de producción | Pre-entrega | FastAPI asíncrona del orquestador, Redis, Phoenix y aprobación humana. |

Las entregas viven en carpetas hermanas. La pre-entrega 7 expone el orquestador del módulo 6 detrás de una API. No importa código de las carpetas anteriores.

## Entregas puntuales

Si un corrector necesita **solo** una actividad, puede entrar directo a su carpeta:

- Pre-entrega 1: [pre-entrega-1-cliente-llm-async](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-1-cliente-llm-async)
- Orquestador concurrente: [orquestador-concurrente](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/orquestador-concurrente)
- Refactorización a LCEL asíncrono: [refactorizacion-lcel-asincrono](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/refactorizacion-lcel-asincrono)
- Pre-entrega 2 — Pipeline validado: [pre-entrega-2-pipeline-validado](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-2-pipeline-validado)
- Pre-entrega 3 — RAG local: [pre-entrega-3-rag-local](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-3-rag-local)
- Pre-entrega 4 — RAG en Pinecone: [pre-entrega-4-rag-pinecone](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-4-rag-pinecone)
- Pre-entrega 5 — Agente ReAct: [pre-entrega-5-agente-react](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-5-agente-react)
- Pre-entrega 6 — Orquestador multi-agente: [pre-entrega-6-orquestador-multiagente](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-6-orquestador-multiagente)
- Pre-entrega 7 — API de producción: [pre-entrega-7-api-agente](https://github.com/DiegoLalanda/ai-engineer-coderhouse/tree/main/pre-entrega-7-api-agente)

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
python verificar_rubrica.py
```

Para la pre-entrega 4 (RAG en Pinecone):

```powershell
pip install -r pre-entrega-4-rag-pinecone\requirements.txt
cd pre-entrega-4-rag-pinecone
copy .env.example .env
python ingest.py
python evaluate.py
python verificar_rubrica.py
```

Para la pre-entrega 5 (agente ReAct):

```powershell
pip install -r pre-entrega-5-agente-react\requirements.txt
cd pre-entrega-5-agente-react
copy .env.example .env
python verificar_rubrica.py
python demo.py
```

Para la pre-entrega 6 (orquestador multi-agente):

```powershell
pip install -r pre-entrega-6-orquestador-multiagente\requirements.txt
cd pre-entrega-6-orquestador-multiagente
copy .env.example .env
python verificar_rubrica.py
python main.py
```

Para la pre-entrega 7 (API de producción):

```powershell
pip install -r pre-entrega-7-api-agente\requirements.txt
cd pre-entrega-7-api-agente
python verificar_rubrica.py
```

Con Docker, desde esa carpeta: `copy .env.example .env` y `.\run.ps1`.

## Autor

Diego Lalanda — curso AI Engineer, Coderhouse.
