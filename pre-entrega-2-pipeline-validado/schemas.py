"""Contrato Pydantic para la extracción de entidades técnicas."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

TechnologyName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
]


class Criticidad(str, Enum):
    """Impacto operativo inferido exclusivamente desde el texto."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class TechnicalEntityExtraction(BaseModel):
    """Salida estructurada y validada del pipeline."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    tecnologias: list[TechnologyName] = Field(
        min_length=1,
        max_length=20,
        description=(
            "Tecnologías, frameworks, servicios, bases de datos, protocolos o "
            "herramientas mencionados explícitamente. Usar 'No identificada' "
            "si el texto no nombra ninguna."
        ),
    )
    nivel_de_criticidad: Criticidad = Field(
        description="Nivel de impacto operativo: baja, media o alta."
    )
    resumen_tecnico: str = Field(
        min_length=20,
        max_length=600,
        description=(
            "Resumen técnico conciso del sistema, síntoma, impacto y causa "
            "cuando esté disponible."
        ),
    )

    @field_validator("tecnologias")
    @classmethod
    def normalize_technologies(
        cls,
        values: list[str],
    ) -> list[str]:
        """Normaliza, deduplica sin distinguir mayúsculas y prohíbe vacíos."""
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = re.sub(r"\s+", " ", value).strip(" ,;.")
            if not cleaned:
                continue
            deduplication_key = cleaned.casefold()
            if deduplication_key not in seen:
                seen.add(deduplication_key)
                normalized.append(cleaned)

        if not normalized:
            raise ValueError("tecnologias no puede estar vacía")
        if "no identificada" in seen and len(normalized) > 1:
            raise ValueError(
                "'No identificada' no puede combinarse con tecnologías reales"
            )
        return normalized

    @field_validator("resumen_tecnico")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        """Evita saltos y espacios accidentales en la salida final."""
        normalized = re.sub(r"\s+", " ", value).strip()
        if len(normalized) < 20:
            raise ValueError("resumen_tecnico debe tener al menos 20 caracteres")
        return normalized
