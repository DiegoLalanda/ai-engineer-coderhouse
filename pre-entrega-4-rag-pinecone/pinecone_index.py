"""Crea o valida el índice serverless de Pinecone."""

from __future__ import annotations

from pinecone import Pinecone, ServerlessSpec

from config import settings


class IndexConfigurationError(RuntimeError):
    """El índice existe, pero no coincide con el modelo de embeddings."""


def pinecone_client() -> Pinecone:
    settings.require_cloud_credentials()
    return Pinecone(api_key=settings.pinecone_api_key)


def _index_names(client: Pinecone) -> set[str]:
    listed = client.list_indexes()
    if hasattr(listed, "names"):
        return set(listed.names())
    names: set[str] = set()
    for item in listed:
        name = item["name"] if isinstance(item, dict) else item.name
        names.add(name)
    return names


def _read_dimension(description: object) -> int:
    dimension = getattr(description, "dimension", None)
    if dimension is None and isinstance(description, dict):
        dimension = description.get("dimension")
    if dimension is None:
        raise IndexConfigurationError("Pinecone no informó la dimensión del índice.")
    return int(dimension)


def _read_metric(description: object) -> str:
    metric = getattr(description, "metric", None)
    if metric is None and isinstance(description, dict):
        metric = description.get("metric")
    return str(metric or "")


def ensure_index(client: Pinecone | None = None):
    """Verifica el índice y lo crea en modo serverless si no existe."""
    client = client or pinecone_client()
    name = settings.index_name
    if name not in _index_names(client):
        print(
            f"Creando índice serverless '{name}' "
            f"({settings.embedding_dimension} dimensiones, métrica {settings.metric}, "
            f"{settings.cloud}/{settings.region})."
        )
        client.create_index(
            name=name,
            dimension=settings.embedding_dimension,
            metric=settings.metric,
            spec=ServerlessSpec(cloud=settings.cloud, region=settings.region),
        )
    else:
        print(f"El índice '{name}' ya existe. No se vuelve a crear.")

    description = client.describe_index(name)
    dimension = _read_dimension(description)
    metric = _read_metric(description).lower()
    if dimension != settings.embedding_dimension:
        raise IndexConfigurationError(
            f"El índice '{name}' tiene dimensión {dimension}, pero "
            f"{settings.embedding_model} exige {settings.embedding_dimension}. "
            "No se mezclan embeddings de distinto tamaño."
        )
    if metric and metric != settings.metric:
        raise IndexConfigurationError(
            f"El índice '{name}' usa la métrica '{metric}'. "
            f"Esta entrega requiere '{settings.metric}'."
        )
    print(
        f"Índice listo: dimensión {dimension}, métrica {metric or settings.metric}, "
        f"namespace '{settings.namespace}'."
    )
    return client.Index(name)
