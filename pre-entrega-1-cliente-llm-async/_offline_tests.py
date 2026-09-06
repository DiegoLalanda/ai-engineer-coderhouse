"""Suite offline: valida la pre-entrega 1 sin API keys reales.

Cubre esquemas Pydantic, Settings/SecretStr, factory, resiliencia
(reintentos, errores controlados) y el camino de main.py sin .env.
Los SDKs se mockean: no se llama a OpenAI ni Anthropic.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import SecretStr, ValidationError

from llm_client import AsyncLLMManager, ChatMessage, LLMClientError, LLMConfig, ModelResponse
from llm_client.errors import ConfigurationError
from llm_client.providers.anthropic_client import AnthropicClient
from llm_client.providers.openai_client import OpenAIClient
from llm_client.schemas import usage_as_ints
from llm_client.settings import Settings


class FakeSettings:
    """Settings mínimo para inyectar keys de prueba sin tocar .env."""

    def __init__(self, openai: str | None = "sk-test-openai", anthropic: str | None = "sk-test-anthropic") -> None:
        self.openai_api_key = SecretStr(openai) if openai else None
        self.anthropic_api_key = SecretStr(anthropic) if anthropic else None
        self.openai_model = "gpt-4o-mini"
        self.anthropic_model = "claude-3-5-sonnet-latest"

    def api_key_for(self, provider: str) -> SecretStr | None:
        return {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key}.get(provider)

    def default_model_for(self, provider: str) -> str:
        return {"openai": self.openai_model, "anthropic": self.anthropic_model}[provider]


class SchemaTests(unittest.TestCase):
    def test_chat_message_valido(self) -> None:
        msg = ChatMessage(role="user", content="¿Qué es la entropía?")
        self.assertEqual(msg.role, "user")
        self.assertTrue(msg.content)

    def test_chat_message_content_vacio_falla(self) -> None:
        with self.assertRaises(ValidationError):
            ChatMessage(role="user", content="")

    def test_chat_message_rol_invalido_falla(self) -> None:
        with self.assertRaises(ValidationError):
            ChatMessage(role="admin", content="hola")  # type: ignore[arg-type]

    def test_chat_message_inmutable(self) -> None:
        msg = ChatMessage(role="user", content="hola")
        with self.assertRaises(ValidationError):
            msg.content = "otro"  # type: ignore[misc]

    def test_llm_config_rangos(self) -> None:
        ok = LLMConfig(provider="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=256)
        self.assertEqual(ok.temperature, 0.7)
        with self.assertRaises(ValidationError):
            LLMConfig(provider="openai", model="x", temperature=2.5)
        with self.assertRaises(ValidationError):
            LLMConfig(provider="openai", model="x", temperature=-0.1)
        with self.assertRaises(ValidationError):
            LLMConfig(provider="openai", model="x", max_tokens=0)
        with self.assertRaises(ValidationError):
            LLMConfig(provider="openai", model="x", top_p=1.5)
        with self.assertRaises(ValidationError):
            LLMConfig(provider="gemini", model="x")  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            LLMConfig(provider="openai", model="x", max_concurrency=0)

    def test_model_response_error_flag(self) -> None:
        resp = ModelResponse(
            provider="openai",
            model="gpt-4o-mini",
            content="falló",
            is_error=True,
            raw_error="rate limit",
        )
        self.assertTrue(resp.is_error)
        self.assertIn("ERROR", str(resp))


class SettingsTests(unittest.TestCase):
    def test_secret_str_no_filtra_key(self) -> None:
        settings = Settings(openai_api_key=SecretStr("sk-super-secreta-123"), anthropic_api_key=None)
        dumped = repr(settings)
        self.assertNotIn("sk-super-secreta-123", dumped)
        self.assertIn("**********", dumped)

    def test_api_key_for_y_modelos_default(self) -> None:
        settings = Settings(openai_api_key=None, anthropic_api_key=None)
        self.assertIsNone(settings.api_key_for("openai"))
        self.assertEqual(settings.default_model_for("openai"), "gpt-4o-mini")
        self.assertEqual(settings.default_model_for("anthropic"), "claude-3-5-sonnet-latest")


class FactoryTests(unittest.TestCase):
    def test_proveedor_desconocido_levanta_value_error(self) -> None:
        config = LLMConfig(provider="openai", model="x")
        object.__setattr__(config, "provider", "gemini")
        with self.assertRaises(ValueError) as ctx:
            AsyncLLMManager(config, FakeSettings())
        self.assertIn("desconocido", str(ctx.exception).lower())

    def test_falta_openai_key_no_crashea_con_excepcion_cruda(self) -> None:
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        with self.assertRaises(ConfigurationError) as ctx:
            AsyncLLMManager(config, FakeSettings(openai=None))
        self.assertFalse(ctx.exception.retryable)
        self.assertIn("OPENAI_API_KEY", ctx.exception.message)

    def test_falta_anthropic_key(self) -> None:
        config = LLMConfig(provider="anthropic", model="claude-3-5-sonnet-latest")
        with self.assertRaises(ConfigurationError) as ctx:
            AsyncLLMManager(config, FakeSettings(anthropic=None))
        self.assertFalse(ctx.exception.retryable)

    def test_factory_instancia_openai_y_anthropic(self) -> None:
        openai_mgr = AsyncLLMManager(LLMConfig(provider="openai", model="gpt-4o-mini"), FakeSettings())
        anthropic_mgr = AsyncLLMManager(
            LLMConfig(provider="anthropic", model="claude-3-5-sonnet-latest"), FakeSettings()
        )
        self.assertIsInstance(openai_mgr._client, OpenAIClient)
        self.assertIsInstance(anthropic_mgr._client, AnthropicClient)

    def test_configuration_error_es_subclase_de_llm_client_error(self) -> None:
        self.assertTrue(issubclass(ConfigurationError, LLMClientError))


class AnthropicMappingTests(unittest.TestCase):
    def test_system_se_separa_del_historial(self) -> None:
        messages = [
            ChatMessage(role="system", content="Respondé en español."),
            ChatMessage(role="user", content="¿Qué es la entropía?"),
        ]
        system, chat = AnthropicClient._split_messages(messages)
        self.assertEqual(system, "Respondé en español.")
        self.assertEqual(chat, [{"role": "user", "content": "¿Qué es la entropía?"}])
        self.assertTrue(all(m["role"] != "system" for m in chat))

    def test_openai_mapea_roles_tal_cual(self) -> None:
        messages = [
            ChatMessage(role="system", content="sé breve"),
            ChatMessage(role="user", content="hola"),
        ]
        mapped = OpenAIClient._to_openai_messages(messages)
        self.assertEqual(mapped[0]["role"], "system")
        self.assertEqual(len(mapped), 2)


class _FakeRetryableClient:
    def __init__(self, fails: int) -> None:
        self.fails = fails
        self.calls = 0

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        self.calls += 1
        if self.calls <= self.fails:
            raise LLMClientError("openai", "Rate limit alcanzado", retryable=True)
        return ModelResponse(provider="openai", model="gpt-4o-mini", content="ok")

    async def stream(self, messages: list[ChatMessage]):
        if False:
            yield ""
        raise LLMClientError("openai", "Rate limit durante streaming", retryable=True)


class _FakeAuthFailClient:
    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        raise LLMClientError("openai", "API key inválida", retryable=False)

    async def stream(self, messages: list[ChatMessage]):
        raise LLMClientError("openai", "API key inválida", retryable=False)
        yield ""  # pragma: no cover — hace del método un async generator


class _HangingStreamClient:
    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        return ModelResponse(provider="openai", model="gpt-4o-mini", content="ok")

    async def stream(self, messages: list[ChatMessage]):
        await asyncio.sleep(30)
        yield "nunca"


class _SlowGenerateClient:
    current = 0
    peak = 0

    async def generate(self, messages: list[ChatMessage]) -> ModelResponse:
        _SlowGenerateClient.current += 1
        _SlowGenerateClient.peak = max(_SlowGenerateClient.peak, _SlowGenerateClient.current)
        await asyncio.sleep(0.05)
        _SlowGenerateClient.current -= 1
        return ModelResponse(provider="openai", model="gpt-4o-mini", content="ok")

    async def stream(self, messages: list[ChatMessage]):
        if False:
            yield ""


class ManagerResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_reintenta_errores_retryable_y_luego_ok(self) -> None:
        mgr = AsyncLLMManager(LLMConfig(provider="openai", model="gpt-4o-mini", max_retries=2), FakeSettings())
        fake = _FakeRetryableClient(fails=2)
        mgr._client = fake  # type: ignore[assignment]
        with patch("llm_client.manager.asyncio.sleep", new=AsyncMock()):
            resp = await mgr.generate([ChatMessage(role="user", content="hola")])
        self.assertFalse(resp.is_error)
        self.assertEqual(resp.content, "ok")
        self.assertEqual(fake.calls, 3)

    async def test_agota_reintentos_devuelve_model_response_error(self) -> None:
        mgr = AsyncLLMManager(LLMConfig(provider="openai", model="gpt-4o-mini", max_retries=1), FakeSettings())
        fake = _FakeRetryableClient(fails=99)
        mgr._client = fake  # type: ignore[assignment]
        with patch("llm_client.manager.asyncio.sleep", new=AsyncMock()):
            resp = await mgr.generate([ChatMessage(role="user", content="hola")])
        self.assertTrue(resp.is_error)
        self.assertEqual(resp.finish_reason, "error")
        self.assertIn("Rate limit", resp.raw_error or "")
        self.assertEqual(fake.calls, 2)  # 1 inicial + 1 retry

    async def test_error_no_retryable_no_reintenta(self) -> None:
        mgr = AsyncLLMManager(LLMConfig(provider="openai", model="gpt-4o-mini", max_retries=3), FakeSettings())
        mgr._client = _FakeAuthFailClient()  # type: ignore[assignment]
        with patch("llm_client.manager.asyncio.sleep", new=AsyncMock()) as sleep:
            resp = await mgr.generate([ChatMessage(role="user", content="hola")])
        self.assertTrue(resp.is_error)
        sleep.assert_not_called()

    async def test_stream_error_no_tumba_el_generador(self) -> None:
        mgr = AsyncLLMManager(LLMConfig(provider="openai", model="gpt-4o-mini"), FakeSettings())
        mgr._client = _FakeAuthFailClient()  # type: ignore[assignment]
        chunks: list[str] = []
        async for chunk in mgr.stream([ChatMessage(role="user", content="hola")]):
            chunks.append(chunk)
        self.assertEqual(len(chunks), 1)
        self.assertIn("[ERROR:openai]", chunks[0])

    async def test_stream_timeout_devuelve_error_controlado(self) -> None:
        mgr = AsyncLLMManager(
            LLMConfig(provider="openai", model="gpt-4o-mini", timeout_s=0.05),
            FakeSettings(),
        )
        mgr._client = _HangingStreamClient()  # type: ignore[assignment]
        chunks: list[str] = []
        async for chunk in mgr.stream([ChatMessage(role="user", content="hola")]):
            chunks.append(chunk)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Timeout", chunks[0])

    async def test_semaforo_limita_concurrencia(self) -> None:
        _SlowGenerateClient.current = 0
        _SlowGenerateClient.peak = 0
        mgr = AsyncLLMManager(
            LLMConfig(provider="openai", model="gpt-4o-mini", max_concurrency=2, max_retries=0),
            FakeSettings(),
        )
        mgr._client = _SlowGenerateClient()  # type: ignore[assignment]
        messages = [ChatMessage(role="user", content="hola")]
        resultados = await asyncio.gather(*(mgr.generate(messages) for _ in range(5)))
        self.assertTrue(all(not r.is_error for r in resultados))
        self.assertEqual(len(resultados), 5)
        self.assertLessEqual(_SlowGenerateClient.peak, 2)


class OpenAIUsageTests(unittest.IsolatedAsyncioTestCase):
    async def test_usage_anidado_del_sdk_se_aplana_a_enteros(self) -> None:
        """openai 3.x mete details anidados; usage_as_ints los descarta."""
        config = LLMConfig(provider="openai", model="gpt-4o-mini")
        client = OpenAIClient(config, FakeSettings())

        usage = MagicMock()
        usage.model_dump.return_value = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "prompt_tokens_details": {"cached_tokens": 0},
            "completion_tokens_details": {"reasoning_tokens": 0},
        }
        choice = MagicMock()
        choice.message.content = "La entropía es..."
        choice.finish_reason = "stop"
        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        response.model = "gpt-4o-mini"

        client._client = MagicMock()
        client._client.chat.completions.create = AsyncMock(return_value=response)

        resp = await client.generate([ChatMessage(role="user", content="¿Qué es la entropía?")])
        self.assertFalse(resp.is_error)
        self.assertEqual(resp.usage, {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})


class UsageHelperTests(unittest.TestCase):
    def test_usage_as_ints_ignora_anidados_y_none(self) -> None:
        self.assertIsNone(usage_as_ints(None))
        dumped = MagicMock()
        dumped.model_dump.return_value = {
            "input_tokens": 4,
            "output_tokens": 8,
            "output_tokens_details": {"reasoning_tokens": 1},
        }
        self.assertEqual(usage_as_ints(dumped), {"input_tokens": 4, "output_tokens": 8})


class MainOfflineTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_sin_keys_termina_sin_crash(self) -> None:
        import main as main_mod

        fake_settings = Settings(openai_api_key=None, anthropic_api_key=None)
        with patch.object(main_mod, "Settings", return_value=fake_settings), patch.object(
            main_mod, "load_dotenv"
        ):
            await main_mod.main()


def run() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    print()
    print("=" * 70)
    print(f"Tests: {result.testsRun}  |  OK: {result.testsRun - len(result.failures) - len(result.errors)}  |  FAIL: {len(result.failures)}  |  ERROR: {len(result.errors)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run())
