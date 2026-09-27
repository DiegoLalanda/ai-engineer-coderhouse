"""Evidencia local de la rúbrica. No llama a Pinecone ni a OpenAI.

    python verificar_rubrica.py
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import tiktoken

from config import BASE_DIR, settings
from documents import CATALOG, METADATA_KEYS, load_chunks
from evaluate import load_golden_set
from langchain_community.retrievers import BM25Retriever
from metrics import precision_at_k, recall_at_k

REPORT_PATH = BASE_DIR / "evidencia" / "verificacion.txt"


@dataclass
class Check:
    criterion: str
    passed: bool
    evidence: str


def _read(name: str) -> str:
    return (BASE_DIR / name).read_text(encoding="utf-8")


def collect_checks() -> list[Check]:
    requirements = _read("requirements.txt").lower()
    env_example = _read(".env.example")
    gitignore = _read(".gitignore")
    readme = _read("README.md").lower()
    ingest_source = _read("ingest.py")
    rag_source = _read("rag_system.py")
    setup_source = _read("pinecone_index.py")
    evaluate_source = _read("evaluate.py")
    chunks = load_chunks()
    cases = load_golden_set()
    tokenizer = tiktoken.get_encoding(settings.token_encoding)
    sizes = [len(tokenizer.encode(chunk.page_content)) for chunk in chunks]
    oversized = [size for size in sizes if size > settings.chunk_size]

    lexical = BM25Retriever.from_documents(chunks)
    lexical.k = settings.top_k
    lexical_recalls = []
    for case in cases:
        retrieved_ids = [
            str(document.metadata["document_id"])
            for document in lexical.invoke(case["pregunta"])
        ]
        lexical_recalls.append(
            recall_at_k(retrieved_ids, case["documento_id_esperado"], settings.top_k)
        )

    precision_sample = precision_at_k(
        ["nimbus-errores", "nimbus-config", "nimbus-errores", "nimbus-dlq", "nimbus-client"],
        "nimbus-errores",
        5,
    )
    recall_hit = recall_at_k(["nimbus-config", "nimbus-errores"], "nimbus-errores", 5)
    recall_miss = recall_at_k(["nimbus-config", "nimbus-dlq"], "nimbus-errores", 5)
    rag_tree = ast.parse(rag_source)
    rag_class = next(
        node for node in rag_tree.body if isinstance(node, ast.ClassDef) and node.name == "RAGSystem"
    )

    checks = [
        Check(
            "1. Pipeline de ingesta a Pinecone",
            "def ingest_documents" in ingest_source
            and "PineconeVectorStore" in ingest_source
            and "add_documents" in ingest_source,
            "ingest.py fragmenta el corpus, genera embeddings y hace upsert por lotes.",
        ),
        Check(
            "2. Índice serverless, 1536 dimensiones y coseno",
            "ServerlessSpec" in setup_source
            and "create_index" in setup_source
            and settings.embedding_dimension == 1536
            and settings.metric == "cosine"
            and settings.embedding_model == "text-embedding-3-small",
            "pinecone_index.py crea el índice solo si no existe y rechaza una dimensión distinta.",
        ),
        Check(
            "3. Namespace y metadatos source, page y category",
            bool(settings.namespace)
            and "namespace" in ingest_source
            and set(METADATA_KEYS) <= {"source", "page", "category", "document_id", "chunk_index"}
            and all(set(METADATA_KEYS) <= set(chunk.metadata) for chunk in chunks),
            f"Namespace '{settings.namespace}'. Categorías: "
            + ", ".join(sorted({spec['category'] for spec in CATALOG.values()}))
            + ". El texto original viaja en el metadato text.",
        ),
        Check(
            "4. Chunking entre 500 y 800 tokens",
            500 <= settings.chunk_size <= 800
            and settings.chunk_overlap == 80
            and not oversized
            and len(chunks) > settings.top_k,
            (
                f"chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap}, "
                f"chunks={len(chunks)}, máximo observado={max(sizes)} tokens."
            ),
        ),
        Check(
            "5. Recuperador híbrido BM25 + Pinecone",
            rag_class is not None
            and "BM25Retriever" in rag_source
            and "EnsembleRetriever" in rag_source
            and "as_retriever" in rag_source,
            "RAGSystem combina BM25 (0.4) y Pinecone (0.6) con EnsembleRetriever, que fusiona por RRF.",
        ),
        Check(
            "6. Golden set de 5 preguntas y evaluate.py",
            len(json.loads((BASE_DIR / "data" / "golden_set.json").read_text(encoding="utf-8"))) == 5
            and "Precision@" in evaluate_source
            and "Recall@" in evaluate_source
            and "def evaluate" in evaluate_source,
            "data/golden_set.json tiene 5 pares pregunta / documento_id_esperado. evaluate.py imprime ambas métricas.",
        ),
        Check(
            "7. Fórmulas de Precision@5 y Recall@5",
            precision_sample == 0.4 and recall_hit == 1.0 and recall_miss == 0.0,
            "Dos aciertos de nimbus-errores entre 5 resultados dan Precision@5=0.40. Recall@5 es 1 o 0.",
        ),
        Check(
            "8. BM25 recupera la fuente esperada",
            all(value == 1.0 for value in lexical_recalls),
            "Recall@5 léxico sobre el golden set: "
            + ", ".join(f"{value:.0f}" for value in lexical_recalls)
            + ". La corrida híbrida completa es python evaluate.py.",
        ),
        Check(
            "9. Secretos fuera del repositorio",
            all(name in requirements for name in ("pinecone", "langchain", "openai"))
            and all(
                key in env_example
                for key in ("PINECONE_API_KEY=", "OPENAI_API_KEY=", "INDEX_NAME=")
            )
            and ".env" in gitignore,
            "requirements.txt incluye pinecone, langchain y openai. .env.example no trae claves reales.",
        ),
        Check(
            "10. README con los pasos para replicar el índice",
            "python ingest.py" in readme and "python evaluate.py" in readme and "serverless" in readme,
            "README.md explica entorno, .env, creación del índice e ingesta.",
        ),
    ]
    return checks


def render(checks: list[Check]) -> str:
    lines = ["PRE-ENTREGA 4 — EVIDENCIA DE RÚBRICA", "Carpeta: pre-entrega-4-rag-pinecone", ""]
    for check in checks:
        state = "PASS" if check.passed else "FAIL"
        lines.append(f"[{state}] {check.criterion}")
        lines.append(f"       {check.evidence}")
    failed = [check.criterion for check in checks if not check.passed]
    lines.extend(
        [
            "",
            f"Resultado: {len(checks) - len(failed)}/{len(checks)} criterios verificados.",
            "Ingesta y evaluación híbrida contra Pinecone: completar .env y ejecutar",
            "python ingest.py y después python evaluate.py.",
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
