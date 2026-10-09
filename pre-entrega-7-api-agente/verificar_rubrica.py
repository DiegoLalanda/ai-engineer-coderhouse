"""Comprueba la rúbrica sin API key: cola, Redis de estado, HITL y trazas.

    python verificar_rubrica.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ["FORCE_ENSAYO"] = "1"
os.environ["CHECKPOINT_BACKEND"] = "sqlite"
os.environ["REDIS_URL"] = "fakeredis://"
os.environ["OPENAI_API_KEY"] = ""
os.environ["SQLITE_PATH"] = str(BASE_DIR / "data" / "verificacion.sqlite")
os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = ""
sys.path.insert(0, str(BASE_DIR))

import httpx
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app import jobs
from app.checkpointer import abrir_checkpointer
from app.ensayo import ModeloEnsayo
from app.graph import PEDIDO_DEMO, build_graph
from app.observability import limpiar, spans_terminados
from app.settings import settings

logging.basicConfig(level=logging.WARNING)


@dataclass
class Check:
    criterion: str
    passed: bool
    evidence: str


def _read(relativo: str) -> str:
    return (BASE_DIR / relativo).read_text(encoding="utf-8")


def collect_static_checks() -> list[Check]:
    main_src = _read("app/main.py")
    worker_src = _read("app/worker.py")
    jobs_src = _read("app/jobs.py")
    graph_src = _read("app/graph.py")
    hitl_src = _read("app/hitl.py")
    obs_src = _read("app/observability.py")
    check_src = _read("app/checkpointer.py")
    readme = _read("README.md")
    compose = _read("docker-compose.yml")
    requirements = _read("requirements.txt").lower()
    env_example = _read(".env.example")
    alta = jobs_src.split("async def pedir_reanudacion", 1)[0]
    return [
        Check("Python 3.12 o superior", sys.version_info >= (3, 12), sys.version.split()[0]),
        Check(
            "POST /tasks encola y responde 202 sin correr el grafo",
            "status_code=202" in main_src and "await jobs.crear" in main_src and "ainvoke" not in main_src,
            "main.crear_tarea",
        ),
        Check(
            "El estado se escribe en Redis antes del RPUSH",
            alta.find("await _guardar") < alta.find("await cliente.rpush"),
            "jobs.crear",
        ),
        Check(
            "Una excepción del worker pasa el trabajo a failed",
            'await jobs.marcar(cliente, job_id, "failed"' in worker_src,
            "worker.procesar",
        ),
        Check(
            "Los checkpoints de producción usan AsyncRedisSaver",
            "AsyncRedisSaver" in check_src and "asetup" in check_src and "compile(checkpointer=checkpointer)" in graph_src,
            "checkpointer.py y graph.compile",
        ),
        Check(
            "La publicación crítica usa interrupt y el efecto queda después",
            "interrupt(" in hitl_src.split("def nodo_aprobacion", 1)[1]
            and hitl_src.split("def nodo_aprobacion", 1)[1].find("interrupt(")
            < hitl_src.split("def nodo_aprobacion", 1)[1].find("publicar_destacado("),
            "hitl.nodo_aprobacion",
        ),
        Check(
            "Hay trazas por nodo y un instrumentador de LangChain",
            "def tramo" in obs_src and "LangChainInstrumentor" in obs_src and 'tramo("supervisor"' in graph_src,
            "observability.py",
        ),
        Check(
            "El README explica Redis, las 5 peticiones y las capturas",
            all(token in readme for token in ("docker compose", "cargar.py", "p95", "screenshots")),
            "README.md",
        ),
        Check(
            "Redis, el modelo y Phoenix salen del entorno",
            all(token in env_example for token in ("REDIS_URL", "OPENAI_MODEL", "PHOENIX_COLLECTOR_ENDPOINT"))
            and "sk-" in env_example,
            ".env.example",
        ),
        Check(
            "requirements y compose cubren la API, Redis Stack y Phoenix",
            "fastapi" in requirements
            and "langgraph-checkpoint-redis" in requirements
            and "redis/redis-stack-server" in compose
            and "arizephoenix/phoenix" in compose,
            "requirements.txt y docker-compose.yml",
        ),
        Check(
            "Los endpoints y el worker son async y no usan requests",
            "async def loop" in worker_src
            and "async def crear_tarea" in main_src
            and "import requests" not in (main_src + worker_src + _read("app/agents/research_agent.py")),
            "main.py y worker.py",
        ),
    ]


async def _esperar(client: httpx.AsyncClient, job_id: str, finales: set[str]) -> dict:
    ultimo: dict = {}
    for _ in range(100):
        ultimo = (await client.get(f"/tasks/{job_id}")).json()
        if ultimo["status"] in finales:
            return ultimo
        await asyncio.sleep(0.1)
    return ultimo


async def prueba_orden_cola() -> Check:
    from fakeredis.aioredis import FakeRedis

    cliente = FakeRedis(decode_responses=True)
    orden: list[str] = []
    set_original = cliente.set
    rpush_original = cliente.rpush

    async def set_espia(*args, **kwargs):
        orden.append("set")
        return await set_original(*args, **kwargs)

    async def rpush_espia(*args, **kwargs):
        orden.append("rpush")
        return await rpush_original(*args, **kwargs)

    cliente.set = set_espia
    cliente.rpush = rpush_espia
    await jobs.crear(cliente, PEDIDO_DEMO)
    return Check("Un alta deja pending antes del RPUSH", orden[:2] == ["set", "rpush"], " ".join(orden[:2]))


async def prueba_reinicio() -> Check:
    async with abrir_checkpointer() as saver:
        grafo = build_graph(ModeloEnsayo(), saver)
        config = {"configurable": {"thread_id": "hilo-reinicio"}, "recursion_limit": settings.recursion_limit}
        await grafo.ainvoke({"messages": [HumanMessage(content=PEDIDO_DEMO)]}, config)
    async with AsyncSqliteSaver.from_conn_string(str(settings.sqlite_path)) as saver:
        restaurado = build_graph(ModeloEnsayo(), saver)
        snapshot = await restaurado.aget_state({"configurable": {"thread_id": "hilo-reinicio"}})
    valores = snapshot.values or {}
    interrumpido = bool(snapshot.next) or bool(valores.get("messages"))
    return Check(
        "El checkpointer conserva el hilo después de cerrar el grafo",
        interrumpido and bool(valores.get("research")),
        f"next={snapshot.next} research={bool(valores.get('research'))}",
    )


async def prueba_api() -> list[Check]:
    from app.main import create_app

    app = create_app()
    checks: list[Check] = []
    publicaciones = settings.evidencia_dir / "publicaciones.jsonl"
    if publicaciones.exists():
        publicaciones.unlink()
    async with app.router.lifespan_context(app):
        (BASE_DIR / "evidencia").mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "evidencia" / "grafo.mmd").write_text(app.state.graph.get_graph().draw_mermaid(), encoding="utf-8")
        limpiar()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            vacia = await client.post("/tasks", json={"query": ""})
            checks.append(Check("Una consulta vacía responde 422", vacia.status_code == 422, str(vacia.status_code)))
            faltante = await client.get(f"/tasks/{uuid.uuid4()}")
            checks.append(Check("Un id desconocido responde 404", faltante.status_code == 404, str(faltante.status_code)))

            creados = await asyncio.gather(
                *[client.post("/tasks", json={"query": PEDIDO_DEMO}) for _ in range(5)]
            )
            codes = [respuesta.status_code for respuesta in creados]
            ids = [respuesta.json()["job_id"] for respuesta in creados]
            checks.append(
                Check(
                    "Cinco altas concurrentes responden 202 con job_id",
                    codes == [202, 202, 202, 202, 202] and len(set(ids)) == 5,
                    " ".join(str(code) for code in codes),
                )
            )
            estados = await asyncio.gather(
                *[_esperar(client, job_id, {"waiting_approval", "done", "failed"}) for job_id in ids]
            )
            checks.append(
                Check(
                    "Las cinco corridas pausan la publicación con score 0.89",
                    all(
                        estado["status"] == "waiting_approval"
                        and estado["approval"]["score"] == 0.89
                        and estado["approval"]["accion"] == "publicar_destacado"
                        for estado in estados
                    ),
                    str(estados[0].get("approval")),
                )
            )
            rechazo = await client.post(f"/tasks/{ids[0]}/approve", json={"approved": False})
            publica = await client.post(f"/tasks/{ids[1]}/approve", json={"approved": True})
            checks.append(
                Check(
                    "La aprobación se encola y el POST no corre el grafo",
                    rechazo.status_code == 200 and publica.status_code == 200 and "ainvoke" not in _read("app/main.py"),
                    f"{rechazo.status_code} {publica.status_code}",
                )
            )
            final_rechazo, final_publica = await asyncio.gather(
                _esperar(client, ids[0], {"done", "failed"}),
                _esperar(client, ids[1], {"done", "failed"}),
            )
            checks.append(
                Check(
                    "Un rechazo no publica el destacado",
                    final_rechazo["status"] == "done" and "rechazó" in final_rechazo["result"],
                    final_rechazo["result"],
                )
            )
            publicado = publicaciones.read_text(encoding="utf-8") if publicaciones.is_file() else ""
            checks.append(
                Check(
                    "Una aprobación ejecuta publicar_destacado y cierra en done",
                    final_publica["status"] == "done" and "se publica" in final_publica["result"] and "Notebook 14" in publicado,
                    final_publica["result"],
                )
            )
            conflicto = await client.post(f"/tasks/{ids[1]}/approve", json={"approved": True})
            checks.append(Check("Aprobar un trabajo ya cerrado responde 409", conflicto.status_code == 409, str(conflicto.status_code)))

            original = app.state.graph.ainvoke

            async def ainvoke_fallido(entrada, *args, **kwargs):
                if isinstance(entrada, dict):
                    texto = " ".join(str(getattr(mensaje, "content", "")) for mensaje in entrada.get("messages") or [])
                    if "FORZAR-FALLO" in texto:
                        raise RuntimeError("fallo de prueba")
                return await original(entrada, *args, **kwargs)

            app.state.graph.ainvoke = ainvoke_fallido
            fallo = await client.post("/tasks", json={"query": "FORZAR-FALLO en el worker"})
            estado_fallo = await _esperar(client, fallo.json()["job_id"], {"done", "failed", "waiting_approval"})
            checks.append(
                Check(
                    "Una excepción del worker marca failed",
                    estado_fallo["status"] == "failed" and "fallo de prueba" in estado_fallo["error"],
                    estado_fallo["error"],
                )
            )

        trazas = spans_terminados()
        tareas = [span for span in trazas if span.name == "tarea"]
        nodos = {span.name for span in trazas}
        checks.append(
            Check(
                "Hay al menos cinco trazas y un tramo por nodo del grafo",
                len(tareas) >= 5 and {"supervisor", "Investigador", "Analista", "Aprobacion"} <= nodos,
                f"tareas={len(tareas)} nodos={sorted(nodos)}",
            )
        )
        archivo = BASE_DIR / "evidencia" / "trazas.jsonl"
        checks.append(
            Check(
                "Las trazas quedan en evidencia/trazas.jsonl",
                archivo.is_file() and len(archivo.read_text(encoding="utf-8").splitlines()) >= 5,
                str(archivo),
            )
        )
    return checks


def main() -> None:
    if settings.sqlite_path.exists():
        settings.sqlite_path.unlink()
    checks = collect_static_checks()
    checks.extend(asyncio.run(_corrida()))
    reporte = BASE_DIR / "evidencia" / "verificacion.txt"
    reporte.parent.mkdir(parents=True, exist_ok=True)
    lineas = []
    fallos = 0
    for check in checks:
        estado = "OK" if check.passed else "FALLO"
        fallos += 0 if check.passed else 1
        lineas.append(f"[{estado}] {check.criterion} — {check.evidence}")
        print(lineas[-1])
    reporte.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if fallos:
        raise SystemExit(f"{fallos} criterios fallaron. Detalle en {reporte}")
    print(f"{len(checks)} criterios OK. Detalle en {reporte}")


async def _corrida() -> list[Check]:
    return [await prueba_orden_cola(), await prueba_reinicio(), *(await prueba_api())]


if __name__ == "__main__":
    main()
