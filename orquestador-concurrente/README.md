# Ejercicio: Orquestador Concurrente de Modelos

Curso **AI Engineer** (Coderhouse) — Módulo 1: arquitectura asíncrona con Python 3.12.

Simula un backend que consulta varias fuentes de IA a la vez, con timeout de resiliencia y semáforo para no saturar el proveedor (rate limit).

## Requisitos

- Python 3.12+
- Solo biblioteca estándar (`asyncio`, `logging`, `time.perf_counter`)

## Entorno

Como no tiene dependencias externas, alcanza con cualquier Python 3.12. Si preferís reutilizar el entorno virtual compartido de `ai-engineer-coderhouse` (ubicado un nivel arriba de esta carpeta):

```powershell
cd ..
py -3.12 -m venv .venv          # si todavía no existe
.\.venv\Scripts\Activate.ps1
cd orquestador-concurrente
python orquestador_concurrente.py
```

## Qué cubre el script

| Paso del enunciado | Implementación |
| --- | --- |
| Simulación de llamadas | `gpt_4_call`, `claude_3_call`, `local_llama_call` con `await asyncio.sleep` (distintas latencias) |
| Orquestación | `asyncio.gather` dispara las 3 a la vez |
| Resiliencia | `async with asyncio.timeout(2.0)` sobre la ejecución **total**. `local_llama` tarda 2.8s → se captura `TimeoutError` y el programa sigue |
| Control de flujo | `asyncio.Semaphore(2)`: se encolan 10 simulaciones, solo 2 corren juntas |
| Anti-patrón | No se usa `time.sleep` (bloquearía el event loop) |

En los logs de la Parte A los tres `INICIO` aparecen casi al mismo `t=`. En la Parte B `concurrentes` nunca supera 2.
