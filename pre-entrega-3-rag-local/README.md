# Pre-entrega 3: Sistema de recuperación semántica local (RAG)

Curso **AI Engineer — Coderhouse**. Esta carpeta es la entrega completa.

## Archivos exigidos por la consigna

| Requisito | Archivo |
| --- | --- |
| 1. Script de ingesta (chunking + ChromaDB) | [ingest.py](./ingest.py) |
| 2. Script de la cadena RAG asíncrona | [rag.py](./rag.py), función `get_rag_response(query: str)` |
| 3. Dataset de ejemplo `.md` | [data/](./data) (4 manuales) |
| 4. Instrucciones de ejecución | este `README.md` |
| Dependencias | [requirements.txt](./requirements.txt): `langchain`, `chromadb`, `openai`, `pydantic` |
| Configuración sin secretos | [.env.example](./.env.example); el `.env` real no se versiona |

## Evidencia por criterio

Desde esta carpeta, después de instalar las dependencias:

```powershell
python verificar_rubrica.py
```

El comando comprueba la rúbrica y guarda el resultado en
[evidencia/verificacion.txt](./evidencia/verificacion.txt). Cubre ingesta,
chunking de 500 tokens con overlap 50, persistencia, embeddings coincidentes,
top-k, LCEL, `PydanticOutputParser`, el prompt «No lo sé.» y las dos preguntas.
No usa la API de OpenAI.

La generación grounded se evidencia con:

```powershell
copy .env.example .env
# Completar OPENAI_API_KEY
python ingest.py
python rag.py
```

`python rag.py` ejecuta la pregunta respondible y la pregunta trampa, e imprime
el JSON validado por `RAGResponse`.

El flujo ingesta documentos, los persiste en ChromaDB, recupera los fragmentos
relevantes y genera una respuesta asíncrona basada exclusivamente en ese
contexto.

El dataset describe la plataforma ficticia **AulaNova**. Incluye información
sobre acceso, pagos, certificados y soporte técnico. Al usar datos ficticios y
específicos, es fácil detectar si el modelo responde desde el contexto o
inventa información.

## Estructura

```text
pre-entrega-3-rag-local/
├── data/
│   ├── 01_acceso_y_seguridad.md
│   ├── 02_facturacion_y_reembolsos.md
│   ├── 03_certificados_y_evaluacion.md
│   └── 04_soporte_tecnico.md
├── config.py               # configuración común y validaciones
├── document_processor.py   # limpieza + chunking medido en tokens
├── vector_store.py         # persistencia y CRUD de ChromaDB
├── ingest.py               # ingesta incremental del dataset
├── rag.py                  # retriever + LCEL async + salida Pydantic
├── verificar_rubrica.py    # evidencia ejecutable de cada criterio
├── evidencia/verificacion.txt
├── .env.example
└── requirements.txt
```

La carpeta `vectorstore/` se crea al ejecutar la ingesta. Está ignorada por
Git porque es un artefacto reproducible a partir de `data/`.

## Arquitectura

```text
OFFLINE / SETUP
data/*.md
  -> limpieza de ruido
  -> RecursiveCharacterTextSplitter (500 tokens, overlap 50)
  -> embeddings locales DefaultEmbeddingFunction
  -> ChromaDB persistente

ONLINE / QUERY
pregunta
  -> mismo modelo local de embeddings
  -> búsqueda semántica top_k=4
  -> formateo de contexto y fuentes
  -> ChatPromptTemplate
  -> ChatOpenAI.ainvoke()
  -> PydanticOutputParser
  -> RAGResponse(respuesta, referencias)
```

La función de embeddings está centralizada en `vector_store.py` y se reutiliza
en ingesta y consulta. Esto evita comparar vectores creados por modelos
distintos.

## Requisitos

- Python 3.12+
- API key de OpenAI para la generación
- Conexión a Internet la primera vez que Chroma descarga su modelo local de
  embeddings

Desde esta carpeta, crear y activar un entorno virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

También se puede reutilizar el `.venv` ubicado en la raíz del monorepo.

## Variables de entorno

Crear el archivo local `.env`:

```powershell
copy .env.example .env
notepad .env
```

Completar:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

No se versiona `.env`. Los embeddings son locales; la clave de OpenAI se usa
únicamente para que el modelo redacte la respuesta final.

## 1. Ingestar el dataset

```powershell
python ingest.py
```

El proceso:

1. Lee recursivamente archivos `.md` y `.txt` de `data/`.
2. Elimina números de página, encabezados/pies marcados, caracteres rotos,
   saltos innecesarios y palabras cortadas por extracción de PDF.
3. Divide por párrafos, líneas, oraciones (`.`), palabras y, solo como último
   recurso, caracteres.
4. Mide tamaño y overlap con `tiktoken`, no con cantidad de caracteres.
5. Guarda documento, embedding y metadatos en `./vectorstore`.

Cada chunk usa el esquema de metadatos `source`, `date`, `type`, `title`,
`document_hash`, `chunk_index`, `chunk_total` y `token_count`. Su ID es un
SHA-256 determinista de fuente, posición y contenido.

La ingesta es incremental. Al ejecutarla otra vez, compara el hash del archivo
y omite documentos sin cambios:

```text
[sin cambios] 01_acceso_y_seguridad.md
...
Resumen: 0 archivos indexados, 4 sin cambios ...
```

Si cambia un archivo, elimina sus chunks anteriores y hace `upsert` solo de la
nueva versión. Si un archivo desaparece de `data/`, también elimina sus
vectores. Para reconstruir toda la colección:

```powershell
python ingest.py --rebuild
```

## 2. Ejecutar las dos pruebas

Después de la ingesta:

```powershell
python rag.py
```

El script ejecuta:

1. **Pregunta respondible:** «¿Qué requisitos debo cumplir para obtener el
   certificado y cuánto tarda en emitirse?».
2. **Pregunta trampa:** «¿Cuál es el menú vegetariano de la cafetería de
   AulaNova?».

La primera debe recuperar `03_certificados_y_evaluacion.md` y mencionar el
80 % de asistencia, la nota mínima de 70/100 y la emisión dentro de 48 horas.
La segunda no existe en el dataset y debe devolver exactamente:

```json
{
  "respuesta": "No lo sé.",
  "referencias": []
}
```

También se puede hacer una consulta individual:

```powershell
python rag.py --query "¿Cuánto dura el enlace para cambiar mi contraseña?"
```

Ejemplo con filtro por el metadato `type`:

```powershell
python rag.py --query "¿Cuándo se emite el certificado?" --type markdown
```

## Decisiones de implementación

### Chunking estratégico

`DocumentProcessor` configura `chunk_size=500` y `chunk_overlap=50`, ambos
medidos con `cl100k_base`. El punto está incluido en la jerarquía de
separadores para respetar límites de oraciones. Los valores se validan al
iniciar: el tamaño no puede ser menor a 500, `RAG_TOP_K` debe estar entre 3 y
5 y `RAG_MAX_DISTANCE` debe ser una distancia coseno válida.

### Persistencia y CRUD

`VectorMemoryManager` encapsula:

- **Create/Update:** `upsert_documents`.
- **Read exacto:** `get_by_ids` y `get_by_metadata`.
- **Read semántico:** `semantic_search`, con soporte para `where`.
- **Delete:** `delete_by_ids` y `delete_by_metadata`.

Las operaciones capturan errores de disco o colección y los convierten en
mensajes con contexto. `PersistentClient` conserva los vectores entre
reinicios.

### Recuperación asíncrona

ChromaDB expone una API síncrona. `get_rag_response()` ejecuta la búsqueda con
`asyncio.to_thread` para no bloquear el event loop. La llamada al LLM usa
`ainvoke`.

La cadena LCEL completa es:

```python
RunnableLambda(retrieve_and_format) | prompt | model | parser
```

El `PydanticOutputParser` valida que el resultado tenga texto y referencias.
Como defensa adicional, el código elimina cualquier referencia que no esté
entre los fragmentos recuperados.

### Grounding

El prompt prohíbe usar conocimiento externo y exige «No lo sé.» cuando el
contexto no alcanza. Se recuperan como máximo cuatro fragmentos para evitar el
problema de contexto infinito o *Lost in the Middle*. Además, los resultados
con distancia coseno mayor a `RAG_MAX_DISTANCE=0.75` se descartan antes del
prompt. Si ninguno supera el umbral, la salida se normaliza a «No lo sé.» con
referencias vacías.

## Solución de problemas

- **“La colección está vacía”**: ejecutar primero `python ingest.py`.
- **Falta `OPENAI_API_KEY`**: copiar `.env.example` a `.env` y completar la
  clave.
- **Cambio de embeddings**: reconstruir con `python ingest.py --rebuild`. No
  consultar una colección creada con otro modelo.
- **Primera ingesta lenta**: Chroma descarga el modelo local una sola vez.
- **Resultados viejos**: confirmar que `RAG_DATA_DIR` y
  `CHROMA_PERSIST_DIR` apunten a esta entrega y ejecutar `--rebuild`.
