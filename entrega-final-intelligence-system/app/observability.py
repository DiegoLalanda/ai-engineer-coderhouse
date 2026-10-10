"""Trazas locales y, si hay colector, OpenTelemetry hacia Phoenix."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult

from app.settings import settings

logger = logging.getLogger("api-agente.trazas")


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


class _JsonlExporter(SpanExporter):
    def export(self, spans) -> SpanExportResult:
        carpeta = settings.evidencia_dir
        carpeta.mkdir(parents=True, exist_ok=True)
        with (carpeta / "trazas.jsonl").open("a", encoding="utf-8") as archivo:
            for span in spans:
                archivo.write(
                    json.dumps(
                        {
                            "nombre": span.name,
                            "atributos": {
                                clave: _valor(valor) for clave, valor in (span.attributes or {}).items()
                            },
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_memoria = _Memoria()
_listo = False


def configurar() -> _Memoria:
    global _listo
    if _listo:
        return _memoria
    proveedor = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.phoenix_project_name,
                "openinference.project.name": settings.phoenix_project_name,
            }
        )
    )
    proveedor.add_span_processor(SimpleSpanProcessor(_memoria))
    proveedor.add_span_processor(SimpleSpanProcessor(_JsonlExporter()))
    destino = settings.phoenix_collector_endpoint.strip()
    if destino:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        proveedor.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=destino)))
        logger.info("Trazas OTLP hacia %s.", destino)
    _instrumentar_langchain(proveedor)
    trace.set_tracer_provider(proveedor)
    _listo = True
    return _memoria


def spans_terminados() -> list:
    return list(_memoria.spans)


def limpiar() -> None:
    _memoria.clear()
    path = settings.evidencia_dir / "trazas.jsonl"
    if path.is_file():
        path.write_text("", encoding="utf-8")


@contextmanager
def tramo(nombre: str, **atributos: object) -> Iterator[None]:
    tracer = trace.get_tracer("api-agente")
    with tracer.start_as_current_span(nombre) as span:
        span.set_attribute("prompt.version", settings.prompt_template_version)
        for clave, valor in atributos.items():
            if isinstance(valor, (str, bool, int, float)):
                span.set_attribute(clave, valor)
        yield


def _instrumentar_langchain(proveedor: TracerProvider) -> None:
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
    except ImportError:
        logger.info("OpenInference no está instalado. Quedan las trazas de cada nodo.")
        return
    LangChainInstrumentor().instrument(tracer_provider=proveedor)


def _valor(valor: object) -> object:
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)
