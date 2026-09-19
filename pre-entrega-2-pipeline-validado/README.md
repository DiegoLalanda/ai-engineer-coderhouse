# Pre-entrega 2: Pipeline de procesamiento validado

Curso **AI Engineer — Coderhouse**. Pipeline asíncrono que recibe texto sin
procesar, extrae entidades técnicas con un LLM y devuelve un objeto validado
por Pydantic.

## Estructura

```text
pre-entrega-2-pipeline-validado/
├── schemas.py       # contrato Pydantic y validadores
├── settings.py      # variables de entorno y secretos tipados
├── chain.py         # Prompt + structured output + validación + retry
├── demo.py          # prueba normal y caso ambiguo
├── .env.example
└── requirements.txt
```

## Flujo

```text
texto crudo
  -> ChatPromptTemplate
  -> ChatOpenAI.with_structured_output(TechnicalEntityExtraction)
  -> control de finish_reason y parsing_error
  -> validación Pydantic
  -> TechnicalEntityExtraction
```

La composición LCEL se construye así:

```python
base_chain = (
    prompt
    | structured_model
    | RunnableLambda(_validate_structured_output)
)
chain = base_chain.with_retry(stop_after_attempt=3)
```

El retry envuelve también la validación posterior. Por eso un JSON truncado,
mal formado o incompleto vuelve a ejecutar el modelo, no solo el parser.

## Contrato de salida

`TechnicalEntityExtraction` define:

- `tecnologias`: entre 1 y 20 nombres, limpios y sin duplicados.
- `nivel_de_criticidad`: enum `baja`, `media` o `alta`.
- `resumen_tecnico`: entre 20 y 600 caracteres.
- Campos adicionales: prohibidos mediante `extra="forbid"`.

Si el texto no menciona tecnologías, el modelo debe devolver únicamente
`"No identificada"`; así se mantiene el contrato sin inventar herramientas.

## Instalación

Desde esta carpeta:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

También se puede reutilizar el entorno virtual ubicado en la raíz del
monorepo:

```powershell
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Completar la clave en `.env`:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

El archivo `.env` está ignorado por Git.

## Ejecutar

```powershell
python demo.py
```

El mini-script procesa dos entradas:

1. Un incidente de producción con FastAPI, Redis y PostgreSQL.
2. Un texto ambiguo sin tecnología explícita ni impacto confirmado.

Salida esperada para el primer caso:

```json
{
  "tecnologias": [
    "FastAPI",
    "Redis",
    "PostgreSQL",
    "HTTP"
  ],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "La API de pagos devuelve HTTP 503: Redis está al 98 % de memoria y el pool de PostgreSQL está agotado, impidiendo completar compras."
}
```

La redacción exacta puede variar, pero el esquema y los valores permitidos no.

## Uso como módulo

```python
import asyncio

from chain import process_text


async def main() -> None:
    result = await process_text(
        "Un worker de Celery perdió conexión con RabbitMQ y dejó tareas pendientes."
    )
    print(result.model_dump_json(indent=2))


asyncio.run(main())
```

`process_text()` usa `await chain.ainvoke(...)` y retorna
`TechnicalEntityExtraction`, no un diccionario sin validar.

## Resiliencia

- `with_structured_output(..., method="json_schema", strict=True)` solicita al
  proveedor una salida compatible con el esquema.
- `include_raw=True` permite revisar el mensaje antes de aceptarlo.
- `finish_reason="length"` o cualquier terminación anormal se considera
  respuesta incompleta.
- `parsing_error`, objeto vacío o `ValidationError` disparan
  `RetryableExtractionError`.
- `.with_retry()` realiza hasta tres intentos con espera exponencial y jitter.
- `ChatOpenAI(max_retries=0)` evita reintentos duplicados dentro del SDK.
- Tras agotar los intentos se lanza `PipelineExecutionError`, que el caller
  puede manejar sin derribar su aplicación.

Los logs muestran el comienzo, la validación, los fallos que provocan retry y
el resultado final sin imprimir la API key ni el texto completo.

## Configuración opcional

- `PIPELINE_MAX_ATTEMPTS`: entre 2 y 5; default `3`.
- `PIPELINE_MAX_COMPLETION_TOKENS`: entre 256 y 4096; default `800`.
- `PIPELINE_TIMEOUT_SECONDS`: entre 0 y 120; default `30`.
- `LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING` o `ERROR`.
