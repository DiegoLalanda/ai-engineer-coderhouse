"""Comprueba la rúbrica sin API key: cola, grafo, HITL, checkpointer y trazas.

    python verificar_rubrica.py
"""

from __future__ import annotations

import ast
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
os.environ["CHROMA_PATH"] = ""
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
from app.graph import build_graph
from app.main import create_app
from app.observability import limpiar, spans_terminados
from app.reviews import buscar_fichas
from app.settings import settings
from app.state import AnalysisArtifact, ResearchArtifact

logging.basicConfig(level=logging.WARNING)

CONSULTA_NOTEBOOK = "Investigá las reseñas de la Notebook 14 y decime si hay que destacarla según la política."
CONSULTA_AURICULARES = "¿Qué dicen las reseñas de los auriculares?"
CONSULTA_POLITICA = "¿Cuál es la política para destacar un producto en la home?"
CONSULTA_WIDGET = "¿Qué reseñas hay del producto Widget 9000?"
CONSULTA_VIDRIERA = "Quiero saber si la Notebook 14 se puede destacar en la vidriera."
CONSULTAS = [
    CONSULTA_NOTEBOOK,
    CONSULTA_AURICULARES,
    CONSULTA_POLITICA,
    CONSULTA_WIDGET,
    CONSULTA_VIDRIERA,
]


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
    research_src = _read("app/agents/research.py")
    analyst_src = _read("app/agents/analyst.py")
    state_src = _read("app/state.py")
    check_src = _read("app/checkpointer.py")
    knowledge_src = _read("app/knowledge.py")
    readme = _read("README.md")
    dockerfile = _read("Dockerfile")
    compose = _read("docker-compose.yml")
    requirements = _read("requirements.txt").lower()
    env_example = _read(".env.example")
    arbol = ast.parse(worker_src + "\n" + main_src + "\n" + research_src)
    funciones_async = [
        nodo.name
        for nodo in ast.walk(arbol)
        if isinstance(nodo, ast.AsyncFunctionDef)
    ]
    return [
        Check("Python 3.12 o superior", sys.version_info >= (3, 12), sys.version.split()[0]),
        Check(
            "La API valida la entrada con Pydantic",
            "TareaEntrada" in main_src and "response_model=TareaEstado" in main_src,
            "POST /tasks y GET /tasks/{id}",
        ),
        Check(
            "Las herramientas declaran args_schema",
            research_src.count("args_schema=") == 3 and "args_schema=CalcularSentimientoInput" in analyst_src,
            "buscar_conocimiento, buscar_resenas, obtener_resena, calcular_sentimiento",
        ),
        Check(
            "El estado y los artefactos son modelos Pydantic",
            "class ResearchArtifact(BaseModel)" in state_src and "class AnalysisArtifact(BaseModel)" in state_src,
            "ResearchArtifact, AnalysisArtifact, TareaEntrada",
        ),
        Check(
            "La comunicación del worker y las búsquedas es async",
            "loop" in funciones_async
            and "async def buscar_fichas" in _read("app/reviews.py")
            and "import requests" not in (worker_src + research_src + main_src),
            "async def loop, buscar_fichas; sin requests",
        ),
        Check(
            "El estado se escribe antes de encolar",
            "await _guardar" in jobs_src.split("async def pedir_reanudacion", 1)[0]
            and jobs_src.split("async def pedir_reanudacion", 1)[0].find("await _guardar")
            < jobs_src.split("async def pedir_reanudacion", 1)[0].find("await cliente.rpush"),
            "jobs.crear: SET status y después RPUSH",
        ),
        Check(
            "El grafo tiene supervisor, especialistas y aprobación",
            all(
                token in graph_src
                for token in (
                    "StateGraph(AgentState)",
                    'add_node("supervisor"',
                    'add_node("Investigador"',
                    'add_node("Analista"',
                    'add_node("Aprobacion"',
                    "add_conditional_edges",
                    '"FINALIZAR": END',
                )
            ),
            "START -> supervisor -> Investigador | Analista | Aprobacion | END",
        ),
        Check(
            "Cada especialista es un create_react_agent",
            research_src.count("create_react_agent(") == 1 and analyst_src.count("create_react_agent(") == 1,
            "investigador y analista",
        ),
        Check(
            "La acción crítica usa interrupt y el checkpointer puede ser Redis",
            "interrupt(" in hitl_src and "AsyncRedisSaver" in check_src and "asetup" in check_src,
            "hitl.interrupt; AsyncRedisSaver.asetup",
        ),
        Check(
            "El conocimiento combina vector y léxico",
            "EmbeddingLocal" in knowledge_src and "_rrf" in knowledge_src and "chromadb" in knowledge_src,
            "Chroma + RRF",
        ),
        Check(
            "El README documenta el grafo y el arranque",
            "```mermaid" in readme and "docker compose" in readme and "thread_id" in readme,
            "mermaid, docker compose, thread_id",
        ),
        Check(
            "El despliegue local es una sola instrucción y usa Python 3.12",
            "python:3.12" in dockerfile and "redis/redis-stack-server" in compose and "uvicorn" in dockerfile,
            "Dockerfile y docker-compose.yml",
        ),
        Check(
            "El modelo, Redis y Phoenix salen de variables de entorno",
            all(token in env_example for token in ("OPENAI_MODEL", "REDIS_URL", "PHOENIX_COLLECTOR_ENDPOINT", "CHROMA_COLLECTION"))
            and "pinecone" not in (graph_src + knowledge_src).lower(),
            ".env.example",
        ),
        Check(
            "requirements declara el runtime",
            all(token in requirements for token in ("fastapi", "redis", "langgraph", "chromadb", "opentelemetry-sdk")),
            "requirements.txt",
        ),
    ]


async def _esperar(client: httpx.AsyncClient, job_id: str, finales: set[str]) -> dict:
    ultimo: dict = {}
    for _ in range(80):
        ultimo = (await client.get(f"/tasks/{job_id}")).json()
        if ultimo["status"] in finales:
            return ultimo
        await asyncio.sleep(0.1)
    return ultimo


async def prueba_reinicio() -> Check:
    async with abrir_checkpointer() as saver:
        grafo = build_graph(ModeloEnsayo(), saver)
        config = {"configurable": {"thread_id": "hilo-reinicio"}, "recursion_limit": settings.recursion_limit}
        await grafo.ainvoke({"messages": [HumanMessage(content=CONSULTA_AURICULARES)]}, config)
    async with AsyncSqliteSaver.from_conn_string(str(settings.sqlite_path)) as saver:
        restaurado = build_graph(ModeloEnsayo(), saver)
        snapshot = await restaurado.aget_state({"configurable": {"thread_id": "hilo-reinicio"}})
    valores = snapshot.values or {}
    ok = bool(valores.get("messages")) and valores.get("task_completed") is True
    return Check(
        "El checkpointer conserva el hilo después de cerrar el grafo",
        ok,
        f"task_completed={valores.get('task_completed')} mensajes={len(valores.get('messages') or [])}",
    )


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
    await jobs.crear(cliente, "pedido de prueba")
    return Check(
        "Un alta deja el estado pending antes del RPUSH",
        orden[:2] == ["set", "rpush"],
        " ".join(orden[:2]),
    )


async def prueba_api() -> list[Check]:
    app = create_app()
    checks: list[Check] = []
    async with app.router.lifespan_context(app):
        (BASE_DIR / "evidencia").mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "evidencia" / "grafo.mmd").write_text(
            app.state.graph.get_graph().draw_mermaid(),
            encoding="utf-8",
        )
        limpiar()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=30) as client:
            vacia = await client.post("/tasks", json={"query": ""})
            checks.append(Check("Una consulta vacía responde 422", vacia.status_code == 422, str(vacia.status_code)))
            faltante = await client.get(f"/tasks/{uuid.uuid4()}")
            checks.append(Check("Un id desconocido responde 404", faltante.status_code == 404, str(faltante.status_code)))
            salud = await client.get("/health")
            checks.append(Check("El healthcheck responde 200", salud.status_code == 200, salud.text))

            creados = await asyncio.gather(*[client.post("/tasks", json={"query": consulta}) for consulta in CONSULTAS])
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
                *[_esperar(client, job_id, {"waiting_approval", "completed", "failed"}) for job_id in ids]
            )
            notebook, auriculares, politica, widget, vidriera = estados
            checks.append(
                Check(
                    "La Notebook 14 queda en aprobación con score 0.89 y 3 reseñas",
                    notebook["status"] == "waiting_approval"
                    and notebook["approval"]["score"] == 0.89
                    and notebook["approval"]["muestra"] == 3,
                    str(notebook["approval"]),
                )
            )
            checks.append(
                Check(
                    "Los auriculares se cierran sin destacar",
                    auriculares["status"] == "completed" and "No se destaca" in auriculares["result"] and "0.00" in auriculares["result"],
                    auriculares["result"],
                )
            )
            checks.append(
                Check(
                    "La pregunta de política cita conocimiento y no inventa reseñas",
                    politica["status"] == "completed" and "no hay reseñas" in politica["result"] and "01-destacados.md" in politica["result"],
                    politica["result"],
                )
            )
            checks.append(
                Check(
                    "Un producto inexistente no fabrica fichas",
                    widget["status"] == "completed" and "no hay reseñas" in widget["result"],
                    widget["result"],
                )
            )
            checks.append(
                Check(
                    "La segunda consulta de la Notebook también espera aprobación",
                    vidriera["status"] == "waiting_approval",
                    vidriera["status"],
                )
            )
            conflicto = await client.post(f"/tasks/{ids[1]}/approve", json={"approved": True})
            checks.append(
                Check(
                    "Aprobar un trabajo ya cerrado responde 409",
                    conflicto.status_code == 409,
                    str(conflicto.status_code),
                )
            )
            rechazo = await client.post(f"/tasks/{ids[0]}/approve", json={"approved": False})
            publica = await client.post(f"/tasks/{ids[4]}/approve", json={"approved": True})
            checks.append(
                Check(
                    "La aprobación se encola y responde 200",
                    rechazo.status_code == 200 and publica.status_code == 200,
                    f"{rechazo.status_code} {publica.status_code}",
                )
            )
            final_rechazo, final_publica = await asyncio.gather(
                _esperar(client, ids[0], {"completed", "failed"}),
                _esperar(client, ids[4], {"completed", "failed"}),
            )
            checks.append(
                Check(
                    "Un rechazo deja el destacado sin publicar",
                    final_rechazo["status"] == "completed" and "rechazó" in final_rechazo["result"],
                    final_rechazo["result"],
                )
            )
            checks.append(
                Check(
                    "Una aprobación publica el destacado y cita las reseñas",
                    final_publica["status"] == "completed" and "se publica" in final_publica["result"],
                    final_publica["result"],
                )
            )

            original = app.state.graph.ainvoke

            async def ainvoke_fallido(entrada, *args, **kwargs):
                if isinstance(entrada, dict):
                    texto = " ".join(str(getattr(mensaje, "content", "")) for mensaje in entrada.get("messages") or [])
                    if "FORZAR-FALLO" in texto:
                        raise RuntimeError("fallo de prueba")
                return await original(entrada, *args, **kwargs)

            app.state.graph.ainvoke = ainvoke_fallido
            fallo = await client.post("/tasks", json={"query": "FORZAR-FALLO en el worker"})
            estado_fallo = await _esperar(client, fallo.json()["job_id"], {"completed", "failed", "waiting_approval"})
            checks.append(
                Check(
                    "Una excepción del worker marca el trabajo como failed",
                    estado_fallo["status"] == "failed" and "fallo de prueba" in estado_fallo["error"],
                    estado_fallo["error"],
                )
            )

            hilo = await app.state.graph.aget_state({"configurable": {"thread_id": ids[1]}})
            checks.append(
                Check(
                    "El thread_id del trabajo queda en el checkpointer",
                    bool((hilo.values or {}).get("messages")),
                    f"mensajes={len((hilo.values or {}).get('messages') or [])}",
                )
            )

        trazas = spans_terminados()
        tareas = [span for span in trazas if span.name == "tarea"]
        versiones = {span.attributes.get("prompt.version") for span in trazas}
        checks.append(
            Check(
                "Hay al menos cinco trazas de tarea con la versión del prompt",
                len(tareas) >= 5 and settings.prompt_template_version in versiones,
                f"tareas={len(tareas)} spans={len(trazas)} version={settings.prompt_template_version}",
            )
        )
        archivo = BASE_DIR / "evidencia" / "trazas.jsonl"
        checks.append(
            Check(
                "Las trazas también quedan en evidencia/trazas.jsonl",
                archivo.is_file() and len(archivo.read_text(encoding="utf-8").splitlines()) >= 5,
                str(archivo),
            )
        )
    return checks


async def prueba_contrato() -> list[Check]:
    fichas = await buscar_fichas("Widget 9000")
    score_invalido = False
    try:
        AnalysisArtifact(
            producto="x",
            score=2,
            muestra=1,
            sentimiento="positivo",
            destacar=True,
            suficiente=True,
        )
    except Exception:
        score_invalido = True
    consulta_invalida = False
    try:
        ResearchArtifact(consulta="", producto="", findings=[], fuentes=[], fragmentos=[], muestra=0, confidence=0)
    except Exception:
        consulta_invalida = True
    return [
        Check("Una búsqueda sin fichas no inventa reseñas", fichas == [], str(len(fichas))),
        Check("Pydantic rechaza un score fuera de 0 a 1", score_invalido, "score=2"),
        Check("Pydantic rechaza una investigación sin consulta", consulta_invalida, "consulta vacía"),
    ]


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
        if not check.passed:
            fallos += 1
        lineas.append(f"[{estado}] {check.criterion} — {check.evidence}")
        print(lineas[-1])
    reporte.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    if fallos:
        raise SystemExit(f"{fallos} criterios fallaron. Detalle en {reporte}")
    print(f"{len(checks)} criterios OK. Detalle en {reporte}")


async def _corrida() -> list[Check]:
    return [
        *(await prueba_contrato()),
        await prueba_orden_cola(),
        await prueba_reinicio(),
        *(await prueba_api()),
    ]


if __name__ == "__main__":
    main()
