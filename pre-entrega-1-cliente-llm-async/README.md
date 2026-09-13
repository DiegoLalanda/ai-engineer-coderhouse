# Pre-entrega 1: Cliente de LLM robusto y asíncrono

Curso **AI Engineer** (Coderhouse) — Módulo 1: *La interfaz base: conexión y abstracción de LLMs*.

**Unified Async LLM Client**: una capa de abstracción en Python 3.12 que permite instanciar OpenAI o Anthropic bajo una interfaz común, 100% asíncrona, con streaming, validación Pydantic y manejo controlado de errores.

## Qué implementa esta entrega

- **Intercambiabilidad**: `AsyncLLMManager` instancia OpenAI o Anthropic según `LLMConfig.provider`, bajo una interfaz común (`BaseLLMClient`), aplicando un patrón Factory (`_PROVIDERS: dict[str, type[BaseLLMClient]]`).
- **Asincronía real**: todas las llamadas a los modelos usan `await` sobre los SDKs asíncronos oficiales (`AsyncOpenAI`, `AsyncAnthropic`); nunca se bloquea el event loop con la versión síncrona.
- **Streaming**: `manager.stream(...)` es un generador asíncrono (`async for ... yield`) que entrega fragmentos de texto a medida que llegan del proveedor.
- **Validación con Pydantic**: `ChatMessage`, `LLMConfig` (temperatura 0–2, `max_tokens`, `top_p`, `timeout_s`, `max_retries`, `max_concurrency`) y `ModelResponse` están tipados y validados con Pydantic.
- **Configuración segura**: `Settings(BaseSettings)` (pydantic-settings) carga las API keys desde `.env` usando `SecretStr`, para que nunca aparezcan en logs, prints o tracebacks. El modelo de cada proveedor también es configurable por variable de entorno (`OPENAI_MODEL` / `ANTHROPIC_MODEL`), en vez de estar hardcodeado.
- **Resiliencia**: cada proveedor captura `RateLimitError`, `AuthenticationError`, `APIConnectionError`, `APITimeoutError` y `APIError` de su SDK y los traduce a `LLMClientError` (con un flag `retryable`); `AsyncLLMManager` reintenta con backoff exponencial y, si se agotan los reintentos, devuelve un `ModelResponse` de error en vez de crashear.

## Estructura del proyecto

```
pre-entrega-1-cliente-llm-async/
├── main.py                        # Script de validación (modo normal + streaming)
├── requirements.txt
├── .env.example
├── README.md
└── llm_client/
    ├── __init__.py                # Exporta la API pública del paquete
    ├── schemas.py                 # ChatMessage, LLMConfig, ModelResponse (Pydantic)
    ├── settings.py                # Settings(BaseSettings) -> API keys + modelos por defecto
    ├── errors.py                  # LLMClientError (jerarquía de errores controlados)
    ├── base_client.py             # BaseLLMClient (ABC): generate() y stream()
    ├── manager.py                 # AsyncLLMManager: Factory + retries + semáforo
    └── providers/
        ├── openai_client.py       # OpenAIClient (AsyncOpenAI)
        └── anthropic_client.py    # AnthropicClient (AsyncAnthropic)
```

### Cómo encajan las piezas

1. **`schemas.py`** — Define primero los datos (evita el "error de diccionarios anidados"): `ChatMessage(role, content)`, `LLMConfig(provider, model, temperature, max_tokens, top_p, timeout_s, max_retries, max_concurrency)` y `ModelResponse` (respuesta unificada). `usage_as_ints()` descarta los details anidados del SDK para que `usage` sea siempre `dict[str, int]`.
2. **`base_client.py`** — `BaseLLMClient` es la clase abstracta con `async def generate(...)` y `def stream(...) -> AsyncIterator[str]`.
3. **`providers/`** — `OpenAIClient` y `AnthropicClient` heredan de `BaseLLMClient`, usan `AsyncOpenAI` / `AsyncAnthropic` y devuelven siempre un `ModelResponse` (o levantan `LLMClientError`).
4. **`manager.py`** — `AsyncLLMManager` es la fachada única (**patrón Factory**): según `LLMConfig.provider`, instancia el cliente correcto (`_PROVIDERS: dict[str, type[BaseLLMClient]]`). Agregar un proveedor nuevo (ej. Gemini) es sumar una entrada a ese diccionario, sin tocar `main.py`.
5. **`main.py`** — Carga `.env`, arma un `AsyncLLMManager` por cada proveedor con API key disponible y prueba la pregunta *"¿Qué es la entropía?"* en modo normal y en streaming. Si hay más de un proveedor, los dispara en paralelo con `asyncio.gather(..., return_exceptions=True)`.

## Resiliencia y manejo de errores

- **Nunca se bloquea el event loop**: todas las llamadas usan `await` sobre los SDKs asíncronos (`AsyncOpenAI`, `AsyncAnthropic`), nunca la versión síncrona.
- **Timeout por llamada**: `generate()` y `stream()` están envueltos en `asyncio.timeout(config.timeout_s)` (por defecto 30s).
- **Semáforo de concurrencia**: `AsyncLLMManager` limita las llamadas simultáneas con `asyncio.Semaphore(config.max_concurrency)` (por defecto 5) para no disparar un 429 al encolar un lote.
- **Reintentos con backoff exponencial**: `AsyncLLMManager.generate()` reintenta automáticamente los errores marcados como `retryable` (rate limit, timeout, problemas de red) hasta `config.max_retries` veces, duplicando la espera en cada intento (1s, 2s, 4s...).
- **Fuga de excepciones controlada**: si se agotan los reintentos, o el error no es reintentable (ej. API key inválida), `generate()` **no lanza la excepción**: devuelve un `ModelResponse(is_error=True, raw_error=...)`. El programa principal sigue corriendo.
- En **streaming**, si el proveedor falla a mitad de camino, el generador loguea el error y agrega un fragmento `"[ERROR:<provider>] ..."` en vez de propagar el crash; lo ya emitido antes del fallo no se pierde.
- Las API keys viven en `SecretStr` de punta a punta: no aparecen en logs, prints ni tracebacks (`repr(settings)` muestra `SecretStr('**********')`).

## Requisitos

- Python 3.12+
- Cuenta y API key de OpenAI y/o Anthropic (con al menos una alcanza para probar)

## Instalación y ejecución (PowerShell)

Este proyecto reutiliza el entorno virtual ya creado en `ai-engineer-coderhouse/.venv`. Desde la carpeta `ai-engineer-coderhouse`:

```powershell
py -3.12 -m venv .venv          # si todavía no existe
.\.venv\Scripts\Activate.ps1
pip install -r pre-entrega-1-cliente-llm-async\requirements.txt
```

Luego, dentro de `pre-entrega-1-cliente-llm-async`:

```powershell
cd pre-entrega-1-cliente-llm-async
copy .env.example .env
notepad .env    # completá OPENAI_API_KEY y/o ANTHROPIC_API_KEY
python main.py
```

## Variables de entorno (`.env`)

| Variable | Obligatoria | Descripción |
| --- | --- | --- |
| `OPENAI_API_KEY` | Una de las dos | API key de OpenAI (https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Una de las dos | API key de Anthropic (https://console.anthropic.com/settings/keys) |
| `OPENAI_MODEL` | No (default `gpt-4o-mini`) | Modelo de OpenAI a usar |
| `ANTHROPIC_MODEL` | No (default `claude-3-5-sonnet-latest`) | Modelo de Anthropic a usar |

Si falta una de las dos API keys, `main.py` omite ese proveedor con un warning en el log, en vez de fallar.

## Qué hace `main.py`

Para cada proveedor con API key configurada:

1. **Modo normal**: `await manager.generate(messages)` → imprime la respuesta completa, la latencia y si hubo error controlado.
2. **Modo streaming**: `async for fragmento in manager.stream(messages):` → imprime cada fragmento de texto apenas llega, simulando el efecto "token a token" de un chat en vivo.

Pregunta usada en ambos modos: **"¿Qué es la entropía?"**

## Uso programático (fuera de `main.py`)

```python
from llm_client import AsyncLLMManager, ChatMessage, LLMConfig
from llm_client.settings import Settings

settings = Settings()  # lee .env
config = LLMConfig(provider="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=300)
manager = AsyncLLMManager(config, settings)

messages = [ChatMessage(role="user", content="¿Qué es la entropía?")]

# Modo normal
respuesta = await manager.generate(messages)
print(respuesta.content)

# Streaming
async for fragmento in manager.stream(messages):
    print(fragmento, end="", flush=True)
```

Cambiar de proveedor es cambiar un string: `LLMConfig(provider="anthropic", model="claude-3-5-sonnet-latest")`.

## Próximos pasos (fuera del alcance de esta pre-entrega)

El siguiente ejercicio del curso (Módulo 2) refactoriza esta llamada al SDK crudo a una cadena LCEL: [refactorizacion-lcel-asincrono](../refactorizacion-lcel-asincrono).

Mejoras posibles de este cliente, si se retoma más adelante:

- Sumar reintentos con jitter y métricas de latencia agregadas.
- Persistir el historial de `ChatMessage` para conversaciones multi-turno.
- Extender `ModelResponse` con conteo de costos estimados por proveedor.
