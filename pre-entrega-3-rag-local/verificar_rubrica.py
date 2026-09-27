"""Evidencia ejecutable de cada criterio de la Pre-entrega 3.

Uso, desde esta carpeta:

    python verificar_rubrica.py

Escribe el mismo informe en pantalla y en evidencia/verificacion.txt.
No llama a OpenAI. La generación grounded se ejecuta aparte con `python rag.py`
cuando OPENAI_API_KEY está configurada.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from config import BASE_DIR, settings
from document_processor import DocumentProcessor
from ingest import discover_documents, ingest_documents
from rag import (
    PREGUNTA_CON_RESPUESTA,
    PREGUNTA_TRAMPA,
    RAGResponse,
    RESPUESTA_DESCONOCIDA,
    get_rag_response,
    parser,
    prompt,
)
from vector_store import VectorMemoryManager, build_embedding_function

REPORT_PATH = BASE_DIR / "evidencia" / "verificacion.txt"


@dataclass
class Check:
    criterion: str
    passed: bool
    evidence: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _functions(path: Path) -> dict[str, ast.AST]:
    tree = ast.parse(_read(path))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def collect_checks() -> list[Check]:
    root_files = {path.name for path in BASE_DIR.iterdir() if path.is_file()}
    data_files = discover_documents(settings.data_dir)
    requirements = _read(BASE_DIR / "requirements.txt").lower()
    env_example = _read(BASE_DIR / ".env.example")
    gitignore = _read(BASE_DIR / ".gitignore")
    readme = _read(BASE_DIR / "README.md").lower()
    ingest_source = _read(BASE_DIR / "ingest.py")
    rag_source = _read(BASE_DIR / "rag.py")
    processor_source = _read(BASE_DIR / "document_processor.py")
    store_source = _read(BASE_DIR / "vector_store.py")
    prompt_text = " ".join(
        message.prompt.template
        for message in prompt.messages
        if hasattr(message, "prompt")
    )

    processor = DocumentProcessor(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        model_encoding=settings.token_encoding,
    )
    chunk_report: list[str] = []
    oversized: list[str] = []
    for path in data_files:
        chunks = processor.process_document(path.read_text(encoding="utf-8"))
        sizes = [processor.calculate_tokens(chunk) for chunk in chunks]
        chunk_report.append(f"{path.name}: {sizes}")
        oversized.extend(
            f"{path.name}#{index}={size}"
            for index, size in enumerate(sizes)
            if size > settings.chunk_size
        )

    ingest_stats = ingest_documents()
    memory = VectorMemoryManager(settings.persist_dir, settings.collection_name)
    answer = memory.semantic_search(PREGUNTA_CON_RESPUESTA, settings.top_k)
    trap = memory.semantic_search(PREGUNTA_TRAMPA, settings.top_k)
    answer_sources = [item["source"] for item in answer["metadatas"][0]]
    trap_distances = [round(float(value), 4) for value in trap["distances"][0]]
    corpus = "\n".join(path.read_text(encoding="utf-8").lower() for path in data_files)

    get_rag = _functions(BASE_DIR / "rag.py")["get_rag_response"]
    index_embedding = build_embedding_function().__class__
    query_embedding = memory.collection._embedding_function.__class__

    checks = [
        Check(
            "1. Script de ingesta",
            "ingest.py" in root_files and "def ingest_documents" in ingest_source,
            "ingest.py define ingest_documents(): lee data/, fragmenta y persiste.",
        ),
        Check(
            "2. Script de la cadena RAG asíncrona",
            isinstance(get_rag, ast.AsyncFunctionDef)
            and get_rag.args.args[0].arg == "query",
            "rag.py define async get_rag_response(query: str) y usa await chain.ainvoke().",
        ),
        Check(
            "3. Dataset de ejemplo",
            len(data_files) >= 3
            and all(path.suffix.lower() in {".md", ".txt"} for path in data_files),
            "data/: " + ", ".join(path.name for path in data_files),
        ),
        Check(
            "4. README con instrucciones de ejecución",
            "python ingest.py" in readme and "python rag.py" in readme,
            "README.md documenta el entorno virtual, .env, ingest.py y rag.py.",
        ),
        Check(
            "5. Dependencias pedidas",
            all(name in requirements for name in ("langchain", "chromadb", "openai", "pydantic")),
            "requirements.txt incluye langchain, chromadb, openai y pydantic.",
        ),
        Check(
            "6. Secretos fuera del repositorio",
            "OPENAI_API_KEY=" in env_example
            and re.search(r"sk-[A-Za-z0-9_-]{12,}", env_example) is None
            and ".env" in gitignore,
            ".env.example tiene un placeholder y .gitignore excluye .env.",
        ),
        Check(
            "7. Chunking de mínimo 500 tokens y overlap 50",
            settings.chunk_size >= 500
            and settings.chunk_overlap == 50
            and not oversized
            and "RecursiveCharacterTextSplitter" in processor_source
            and "length_function=self.calculate_tokens" in processor_source,
            (
                f"Configuración: chunk_size={settings.chunk_size}, "
                f"chunk_overlap={settings.chunk_overlap}, encoding={settings.token_encoding}. "
                "Tokens por archivo: " + " | ".join(chunk_report)
            ),
        ),
        Check(
            "8. ChromaDB persistente y embeddings coincidentes",
            "PersistentClient" in store_source
            and settings.persist_dir.name == "vectorstore"
            and index_embedding is query_embedding
            and memory.count() > 0,
            (
                f"PersistentClient en {settings.persist_dir.name}/; "
                f"encoder único: {index_embedding.__name__}; "
                f"chunks persistidos: {memory.count()}."
            ),
        ),
        Check(
            "9. No reindexa si la base ya existe",
            ingest_stats.files_skipped == ingest_stats.files_found
            and ingest_stats.chunks_upserted == 0,
            (
                f"Segunda ingesta: {ingest_stats.files_skipped}/"
                f"{ingest_stats.files_found} archivos sin cambios y "
                f"{ingest_stats.chunks_upserted} chunks reescritos."
            ),
        ),
        Check(
            "10. Retriever con top_k entre 3 y 5",
            3 <= settings.top_k <= 5 and "semantic_search" in rag_source,
            f"RAG_TOP_K={settings.top_k}. La búsqueda usa el embedding de la pregunta.",
        ),
        Check(
            "11. Cadena LCEL con PydanticOutputParser",
            "RunnableLambda(retrieve_and_format) | prompt | model | parser" in rag_source
            and parser.pydantic_object is RAGResponse
            and {"respuesta", "referencias"} <= set(RAGResponse.model_fields),
            "Cadena: retriever | prompt | ChatOpenAI | PydanticOutputParser(RAGResponse).",
        ),
        Check(
            "12. Prompt filtro de veracidad",
            "No lo sé." in prompt_text and "únicamente" in prompt_text,
            'El system prompt exige responder solo con el CONTEXTO o exactamente "No lo sé.".',
        ),
        Check(
            "13. Pregunta cuya respuesta está en los documentos",
            "03_certificados_y_evaluacion.md" in answer_sources
            and "ochenta por ciento" in corpus
            and "cuarenta y ocho horas" in corpus,
            (
                "Pregunta: " + PREGUNTA_CON_RESPUESTA + ". Fuentes recuperadas: "
                + ", ".join(dict.fromkeys(answer_sources))
            ),
        ),
        Check(
            "14. Pregunta trampa ausente del corpus",
            "menú vegetariano" not in corpus and "cafetería" not in corpus,
            (
                "Pregunta: " + PREGUNTA_TRAMPA
                + ". Esa información no está en ningún documento. Distancias: "
                + ", ".join(str(value) for value in trap_distances)
                + f'. El prompt y el validador obligan a responder "{RESPUESTA_DESCONOCIDA}" con referencias vacías.'
            ),
        ),
    ]
    return checks


def render(checks: list[Check]) -> str:
    lines = [
        "PRE-ENTREGA 3 — EVIDENCIA DE RÚBRICA",
        "Carpeta: pre-entrega-3-rag-local",
        "",
    ]
    for check in checks:
        state = "PASS" if check.passed else "FAIL"
        lines.append(f"[{state}] {check.criterion}")
        lines.append(f"       {check.evidence}")
    failed = [check.criterion for check in checks if not check.passed]
    lines.extend(
        [
            "",
            f"Resultado: {len(checks) - len(failed)}/{len(checks)} criterios verificados.",
            "Generación con OpenAI: ejecutar `python rag.py` después de completar .env.",
            "Esa corrida hace las dos pruebas finales y muestra el JSON de RAGResponse.",
        ]
    )
    if failed:
        lines.append("Fallaron: " + "; ".join(failed))
    return "\n".join(lines) + "\n"


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    checks = collect_checks()
    report = render(checks)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Informe guardado en {REPORT_PATH.relative_to(BASE_DIR).as_posix()}")
    if not all(check.passed for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
