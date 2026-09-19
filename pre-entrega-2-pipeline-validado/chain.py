"""Pipeline LCEL asíncrono para extracción técnica estructurada."""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI
from openai import APIError
from pydantic import ValidationError

from schemas import TechnicalEntityExtraction
from settings import settings

logger = logging.getLogger(__name__)

MAX_INPUT_CHARACTERS = 50_000
VALID_FINISH_REASONS = {None, "stop", "tool_calls"}


class PipelineError(Exception):
    """Error base controlado del pipeline."""


class ConfigurationError(PipelineError):
    """Falta una variable o configuración indispensable."""


class RetryableExtractionError(PipelineError):
    """La respuesta del modelo está truncada, incompleta o no valida."""


class PipelineExecutionError(PipelineError):
    """Se agotaron los intentos de procesamiento."""


prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Eres un analista senior de incidentes y arquitecturas de software.
Extrae información exclusivamente del texto recibido; no inventes tecnologías,
causas ni impacto.

Criterios de criticidad:
- alta: caída total, pérdida o corrupción de datos, brecha de seguridad,
  producción detenida o impacto masivo.
- media: degradación parcial, errores repetidos o riesgo operativo sin caída total.
- baja: descripción informativa, cambio planificado o problema sin impacto relevante.

Si no se menciona ninguna tecnología de manera explícita, devuelve una única
tecnología con el valor "No identificada". Resume incertidumbres como tales.
""".strip(),
        ),
        (
            "human",
            """
INSTRUCCIONES DE FORMATO:
{format_instructions}

TEXTO SIN PROCESAR:
{input_text}
""".strip(),
        ),
    ]
).partial(
    format_instructions=json.dumps(
        TechnicalEntityExtraction.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
)


def _validate_structured_output(payload: dict[str, Any]) -> TechnicalEntityExtraction:
    """Detecta truncamiento/parsing inválido y fuerza el retry de LCEL."""
    if not isinstance(payload, dict):
        logger.warning(
            "Salida inesperada (%s); se solicitará un reintento.",
            type(payload).__name__,
        )
        raise RetryableExtractionError(
            "with_structured_output no devolvió el contenedor esperado"
        )

    raw_message = payload.get("raw")
    response_metadata = getattr(raw_message, "response_metadata", {}) or {}
    finish_reason = response_metadata.get("finish_reason")
    if finish_reason is None:
        finish_reason = response_metadata.get("stop_reason")

    logger.debug("finish_reason recibido: %r", finish_reason)
    if finish_reason not in VALID_FINISH_REASONS:
        logger.warning(
            "Respuesta incompleta (finish_reason=%r); se solicitará un reintento.",
            finish_reason,
        )
        raise RetryableExtractionError(
            f"respuesta incompleta: finish_reason={finish_reason!r}"
        )

    parsing_error = payload.get("parsing_error")
    if parsing_error is not None:
        logger.warning(
            "La salida estructurada no pudo validarse (%s); "
            "se solicitará un reintento.",
            type(parsing_error).__name__,
        )
        raise RetryableExtractionError(
            f"JSON mal formado o esquema incompleto: {parsing_error}"
        ) from parsing_error

    parsed = payload.get("parsed")
    if parsed is None:
        logger.warning(
            "El modelo no devolvió un objeto parseado; se solicitará un reintento."
        )
        raise RetryableExtractionError("respuesta estructurada vacía")

    try:
        return TechnicalEntityExtraction.model_validate(parsed)
    except ValidationError as exc:
        logger.warning(
            "Pydantic rechazó la respuesta; se solicitará un reintento: %s",
            exc,
        )
        raise RetryableExtractionError(
            "la respuesta no cumple el contrato Pydantic"
        ) from exc


@lru_cache(maxsize=1)
def build_chain() -> Runnable[dict[str, str], TechnicalEntityExtraction]:
    """Construye una sola vez la cadena validada y resiliente."""
    if settings.openai_api_key is None:
        raise ConfigurationError(
            "Falta OPENAI_API_KEY. Copiá .env.example a .env y completá la clave."
        )

    model = ChatOpenAI(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=0,
        max_completion_tokens=settings.pipeline_max_completion_tokens,
        timeout=settings.pipeline_timeout_seconds,
        # El retry vive en LCEL para que también cubra parsing y validación.
        max_retries=0,
    )
    structured_model = model.with_structured_output(
        TechnicalEntityExtraction,
        method="json_schema",
        include_raw=True,
        strict=True,
    )

    base_chain = (
        prompt
        | structured_model
        | RunnableLambda(_validate_structured_output)
    )
    return base_chain.with_retry(
        retry_if_exception_type=(
            RetryableExtractionError,
            ValidationError,
            OutputParserException,
            APIError,
        ),
        wait_exponential_jitter=True,
        stop_after_attempt=settings.pipeline_max_attempts,
    )


async def process_text(text: str) -> TechnicalEntityExtraction:
    """Procesa texto con LCEL y devuelve siempre un modelo Pydantic validado."""
    if not isinstance(text, str):
        raise TypeError("text debe ser un string")

    normalized_text = re.sub(r"\s+", " ", text).strip()
    if len(normalized_text) < 10:
        raise ValueError("text debe contener al menos 10 caracteres útiles")
    if len(normalized_text) > MAX_INPUT_CHARACTERS:
        raise ValueError(
            f"text supera el máximo de {MAX_INPUT_CHARACTERS} caracteres"
        )

    chain = build_chain()
    logger.info(
        "Procesando %d caracteres con %s (máximo %d intentos).",
        len(normalized_text),
        settings.openai_model,
        settings.pipeline_max_attempts,
    )

    try:
        result = await chain.ainvoke({"input_text": normalized_text})
    except (
        RetryableExtractionError,
        ValidationError,
        OutputParserException,
        APIError,
    ) as exc:
        logger.error(
            "El pipeline agotó sus %d intentos: %s: %s",
            settings.pipeline_max_attempts,
            type(exc).__name__,
            exc,
        )
        raise PipelineExecutionError(
            "No fue posible obtener una extracción válida después de los reintentos."
        ) from exc
    except Exception as exc:
        logger.exception(
            "Fallo no recuperable durante el procesamiento: %s",
            type(exc).__name__,
        )
        raise PipelineExecutionError(
            "El pipeline falló por un error no recuperable."
        ) from exc

    logger.info(
        "Extracción validada: %d tecnologías, criticidad=%s.",
        len(result.tecnologias),
        result.nivel_de_criticidad.value,
    )
    return result


__all__ = [
    "ConfigurationError",
    "PipelineError",
    "PipelineExecutionError",
    "RetryableExtractionError",
    "build_chain",
    "process_text",
    "prompt",
]
