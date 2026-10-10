"""Recuperación híbrida de las políticas. Chroma aporta el vector y el léxico, el otro ranking."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb
from chromadb.api.types import EmbeddingFunction

from app.settings import settings

logger = logging.getLogger("intelligence.conocimiento")

_DIM = 64
_RRF_K = 60
_TOKEN = re.compile(r"[a-záéíóúüñ0-9]+", re.IGNORECASE)
_VACIAS = frozenset({"para", "como", "esta", "este", "tiene", "solo", "cuando", "donde", "desde", "hasta", "sobre"})


class EmbeddingLocal(EmbeddingFunction):
    """Vector estable por token. No usa la red."""

    def __init__(self, dim: int = _DIM) -> None:
        self.dim = dim

    @staticmethod
    def name() -> str:
        return "hashing-local"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._vector(texto) for texto in input]

    def _vector(self, texto: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _tokens(texto)
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "little") % self.dim] += 1.0
        norma = sum(valor * valor for valor in vector) ** 0.5 or 1.0
        return [valor / norma for valor in vector]


@dataclass(frozen=True)
class Documento:
    fuente: str
    texto: str


class IndiceConocimiento:
    def __init__(self) -> None:
        self._documentos: list[Documento] = []
        self._collection = None

    def cargar(self) -> int:
        documentos = _leer_politicas()
        self._documentos = documentos
        cliente = _cliente()
        try:
            cliente.delete_collection(settings.chroma_collection)
        except Exception:
            logger.debug("La colección %s todavía no existía.", settings.chroma_collection)
        collection = cliente.get_or_create_collection(
            name=settings.chroma_collection,
            embedding_function=_embedder(),
            metadata={"hnsw:space": "cosine"},
        )
        if documentos:
            collection.add(
                ids=[doc.fuente for doc in documentos],
                documents=[doc.texto for doc in documentos],
                metadatas=[{"fuente": doc.fuente, "document_id": doc.fuente} for doc in documentos],
            )
        self._collection = collection
        logger.info("Índice %s con %s políticas.", settings.chroma_collection, len(documentos))
        return len(documentos)

    def buscar(self, consulta: str, top_k: int | None = None) -> list[dict[str, str]]:
        if self._collection is None:
            self.cargar()
        if not self._documentos:
            return []
        limite = top_k or settings.retrieval_top_k
        fusion = _rrf(self._ranking_vectorial(consulta), self._ranking_lexico(consulta))
        salida: list[dict[str, str]] = []
        for fuente, _puntaje in fusion[:limite]:
            texto = next(doc.texto for doc in self._documentos if doc.fuente == fuente)
            salida.append({"fuente": fuente, "texto": texto})
        return salida

    def _ranking_vectorial(self, consulta: str) -> list[str]:
        cantidad = min(len(self._documentos), max(settings.retrieval_top_k, 3))
        resultado = self._collection.query(query_texts=[consulta], n_results=cantidad)
        ids = (resultado.get("ids") or [[]])[0]
        return [str(item) for item in ids]

    def _ranking_lexico(self, consulta: str) -> list[str]:
        claves = [token for token in _tokens(consulta) if len(token) >= 4 and token not in _VACIAS]
        puntajes: list[tuple[int, str]] = []
        for doc in self._documentos:
            blob = _normalizar(doc.texto + " " + doc.fuente)
            puntajes.append((sum(1 for clave in claves if clave in blob), doc.fuente))
        puntajes.sort(key=lambda item: item[0], reverse=True)
        return [fuente for puntaje, fuente in puntajes if puntaje > 0]


def _embedder():
    if settings.embedding_provider.strip().lower() == "openai":
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

        return OpenAIEmbeddingFunction(
            api_key=settings.openai_api_key or None,
            model_name=settings.embedding_model,
        )
    return EmbeddingLocal()


def _cliente():
    ruta = settings.chroma_path.strip()
    if not ruta:
        return chromadb.EphemeralClient()
    return chromadb.PersistentClient(path=ruta)


def _leer_politicas() -> list[Documento]:
    carpeta = settings.conocimiento_dir
    if not carpeta.is_dir():
        return []
    documentos: list[Documento] = []
    for path in sorted(carpeta.glob("*.md")):
        texto = path.read_text(encoding="utf-8").strip()
        if texto:
            documentos.append(Documento(fuente=path.name, texto=texto))
    return documentos


def _tokens(texto: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(texto)]


def _normalizar(texto: str) -> str:
    return " ".join(_tokens(texto))


def _rrf(*rankings: list[str]) -> list[tuple[str, float]]:
    puntajes: dict[str, float] = {}
    for ranking in rankings:
        for posicion, fuente in enumerate(ranking):
            puntajes[fuente] = puntajes.get(fuente, 0.0) + 1.0 / (_RRF_K + posicion + 1)
    return sorted(puntajes.items(), key=lambda item: item[1], reverse=True)


indice = IndiceConocimiento()
