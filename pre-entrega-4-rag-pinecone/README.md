# Pre-entrega 4: Sistema RAG escalable en la nube con Pinecone

Curso **AI Engineer — Coderhouse**. Esta carpeta es la entrega completa.

El corpus documenta la librería ficticia **NimbusQueue**. Tiene códigos de error, variables de entorno y nombres de clases que una búsqueda solo semántica puede confundir, y que BM25 recupera por coincidencia exacta.

## Archivos exigidos por la consigna

| Requisito | Archivo |
| --- | --- |
| Pipeline de ingesta a Pinecone | [ingest.py](./ingest.py) |
| Índice serverless | [pinecone_index.py](./pinecone_index.py) |
| Recuperador híbrido BM25 + vectorial | [rag_system.py](./rag_system.py), clase `RAGSystem` |
| Evaluación Precision@5 y Recall@5 | [evaluate.py](./evaluate.py) |
| Golden set | [data/golden_set.json](./data/golden_set.json) |
| Dataset técnico | [data/](./data) (6 Markdown) |
| Réplica del índice | este `README.md` |
| Variables | [.env.example](./.env.example): `PINECONE_API_KEY`, `OPENAI_API_KEY`, `INDEX_NAME` |

## Cómo replicar el índice

Hace falta una cuenta de Pinecone y una API key de OpenAI. El índice no se versiona: se crea en la nube al correr la ingesta.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Completar:

```dotenv
PINECONE_API_KEY=pc-...
OPENAI_API_KEY=sk-...
INDEX_NAME=nimbus-rag
```

También se puede reutilizar el `.venv` de la raíz del monorepo. El archivo `.env` está ignorado por Git.

Desde esta carpeta:

```powershell
python ingest.py
python evaluate.py
```

`python ingest.py` hace, en orden:

1. Si `INDEX_NAME` no existe, crea un índice **serverless** en `aws/us-east-1`, con **1536** dimensiones y métrica **cosine**. Esas dimensiones son las de `text-embedding-3-small`. Si el índice ya existe con otra dimensión o métrica, el script se detiene: no mezcla espacios vectoriales.
2. Lee los Markdown de `data/`, los limpia y los parte con `RecursiveCharacterTextSplitter`. El tamaño es **600 tokens** y el overlap **80**, medidos con `tiktoken` (`cl100k_base`), dentro del rango de 500 a 800 tokens.
3. Genera embeddings con el mismo modelo que se usa para consultar.
4. Hace upsert en lotes de 100, dentro del namespace `nimbus-docs`. El namespace evita mezclar este corpus con otros datos del mismo índice.
5. Guarda en los metadatos el texto original (`text`), `source`, `page`, `category`, `document_id` y `chunk_index`. No hace falta otra base para recuperar el contenido.

La segunda ejecución no reembebe los chunks cuyo ID determinista ya está en el namespace. Para reconstruir ese namespace:

```powershell
python ingest.py --rebuild
```

`--rebuild` borra solo `nimbus-docs`, no otros namespaces del índice.

## Recuperación híbrida

`RAGSystem` arma un `EnsembleRetriever` con dos recuperadores:

- **BM25**, peso 0.4. Sirve para `NQ-503`, `NIMBUS_ACK_TIMEOUT`, `X-Nimbus-Signature` y `replay_dlq`.
- **Pinecone**, peso 0.6, `top_k=5`, mismo namespace y mismo modelo de embeddings.

La fusión es la del `EnsembleRetriever` de LangChain: Reciprocal Rank Fusion. No se suman el score de BM25 y la similitud coseno, porque no comparten escala. `retrieve()` devuelve como máximo 5 chunks únicos.

## Evaluación

`data/golden_set.json` tiene 5 preguntas y el `documento_id_esperado` de cada una.

```powershell
python evaluate.py
```

Imprime, por pregunta y como promedio:

- **Recall@5:** 1 si el documento esperado aparece entre los 5 recuperados; si no, 0.
- **Precision@5:** fracción de esos 5 chunks cuyo `document_id` es el esperado. Con una sola fuente correcta, el máximo por pregunta es 1 solo si los cinco chunks vinieran de ese documento. En este corpus el valor útil es más bajo y se lee junto con el recall.

## Verificación sin gastar API

```powershell
python verificar_rubrica.py
```

Comprueba la estructura, el chunking, el golden set, las fórmulas y que BM25 solo ya encuentra la fuente de las 5 preguntas. No crea el índice ni llama a OpenAI. El resultado queda en `evidencia/verificacion.txt`. La corrida contra Pinecone sigue siendo `python ingest.py` y `python evaluate.py`.

## Esquema de metadatos

Todos los chunks usan las mismas claves, para no mezclar `source` con otro nombre de fecha o de categoría:

| Clave | Ejemplo | Uso |
| --- | --- | --- |
| `text` | cuerpo del chunk | Lo escribe PineconeVectorStore. Evita una base relacional. |
| `source` | `02_nimbus_errores.md` | Archivo de origen. |
| `page` | `1` | Posición del chunk dentro del archivo. |
| `category` | `errores` | Filtro por tipo de documento. |
| `document_id` | `nimbus-errores` | Identidad que mide el golden set. |
| `chunk_index` | `0` | Parte del ID estable. |
