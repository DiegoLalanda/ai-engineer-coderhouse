"""Trazas locales y, si hay colector, OpenTelemetry hacia Phoenix."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from app.settings import settings

logger = logging.getLogger("intelligence.trazas")


class _Memoria(SpanExporter):
    def __init__(self) -> None:
        self.spans: list = []

    def export(self, spans) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

    def clear(self) -> None:
        self.spans.clear()


_exporter = _Memoria()
_listo = False


class _JsonlExporter(SpanExporter):
    def export(self, spans) -> SpanExportResult:
        carpeta = settings.evidencia_dir
        carpeta.mkdir(parents=True, exist_ok=True)
        path = carpeta / "trazas.jsonl"
        with path.open("a", encoding="utf-8") as archivo:
            for span in spans:
                archivo.write(
                    json.dumps(
                        {
                            "nombre": span.name,
                            "atributos": {clave: _valor(valor) for clave, valor in span.attributes.items()},
                            "duracion_ns": (span.end_time or 0) - (span.start_time or 0),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


def configurar() -> _Memoria:
    global _listo
    if _listo:
        return _exporter
    proveedor = TracerProvider(resource=Resource.create({"service.name": "intelligence-system"}))
    proveedor.add_span_processor(SimpleSpanProcessor(_exporter))
    proveedor.add_span_processor(SimpleSpanProcessor(_JsonlExporter()))
    destino = settings.phoenix_collector_endpoint.strip()
    if destino:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        proveedor.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=destino)))
        logger.info("Trazas OTLP hacia %s.", destino)
    trace.set_tracer_provider(proveedor)
    _listo = True
    return _exporter


def spans_terminados() -> list:
    return list(_exporter.spans)


def limpiar() -> None:
    _exporter.clear()
    path = settings.evidencia_dir / "trazas.jsonl"
    if path.is_file():
        path.write_text("", encoding="utf-8")


@contextmanager
def tramo(nombre: str, **atributos: object) -> Iterator[None]:
    tracer = trace.get_tracer("intelligence")
    with tracer.start_as_current_span(nombre) as span:
        span.set_attribute("prompt.version", settings.prompt_template_version)
        for clave, valor in atributos.items():
            if valor is None:
                continue
            span.set_attribute(clave, valor if isinstance(valor, (str, bool, int, float)) else str(valor))
        yield


def _valor(valor: object) -> object:
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)
