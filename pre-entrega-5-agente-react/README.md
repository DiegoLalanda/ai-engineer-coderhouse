# Pre-entrega 5: Agente de razonamiento cíclico con memoria persistente

Curso **AI Engineer — Coderhouse**. Agente ReAct asíncrono que consulta una base SQLite de pedidos, decide solo cuándo usar cada herramienta y retoma la sesión con `thread_id`.

## Estructura

```text
pre-entrega-5-agente-react/
├── graph.py                 # AgentState(MessagesState) y StateGraph
├── tools.py                 # buscar_pedidos y obtener_pedido
├── orders_db.py             # SQLite de pedidos, creada al consultar
├── session.py               # corrida y traza
├── demo.py                  # ChatOpenAI + AsyncSqliteSaver
├── verificar_rubrica.py     # ciclo completo sin API key
├── settings.py
├── evidencia/traza_react.json
├── evidencia/traza_react.log
├── .env.example
└── requirements.txt
```

## Ciclo

```text
START -> agent -> tools_condition
                 |-- hay tool_calls -> tools -> agent
                 `-- no hay tool_calls -> END
```

No hay un `if/else` que elija la herramienta. `tools_condition` solo mira si el último mensaje del modelo trae `tool_calls`. El modelo lee los docstrings.

`buscar_pedidos` devuelve cantidad, total e ids, y marca `completo: false`. Si la pregunta pide productos, el modelo tiene que volver a entrar al ciclo y llamar a `obtener_pedido` con el id que acaba de recibir. Un error de validación o un cliente inexistente vuelve como observación; el agente reintenta o pide el dato.

`recursion_limit` está en 10.

## Memoria

El checkpointer es `AsyncSqliteSaver`. El `SqliteSaver` síncrono del mismo paquete no implementa `aget_tuple`, así que `ainvoke` usa la variante asíncrona. Cada sesión es un `thread_id`. El historial se acumula con `add_messages`.

El modelo no recibe el historial entero: `recent_messages` le pasa una ventana y, si el corte cae en un resultado de herramienta, incluye también la llamada que lo originó. El checkpoint sigue guardando la sesión.

## Instalación

Desde esta carpeta, con el entorno de la raíz del monorepo o con uno nuevo:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Si ya existe el `.venv` de la raíz:

```powershell
..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

`.env`:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
RECURSION_LIMIT=10
```

La clave no se versiona. El `.gitignore` de la raíz ignora `.env` y los `*.sqlite`.

## Cómo correrlo

Sin API, sobre el grafo, las herramientas y SQLite reales. El modelo de esta corrida es determinista: sirve para versionar la traza y para ver el ciclo, el reintento y los dos `thread_id`.

```powershell
python verificar_rubrica.py
```

Con OpenAI, la misma secuencia de preguntas. `demo.py` reemplaza la traza.

```powershell
python demo.py
```

Preguntas:

1. `sesion-102`: cuántos pedidos tuvo el cliente 102, el total y qué se compró en el último. Ahí la herramienta entra dos veces.
2. La misma sesión: `¿y el primero?` El usuario no repite el cliente.
3. `sesion-vacia`: `¿y el último?` No hereda la otra sesión.
4. `sesion-999`: un cliente que no existe. La herramienta devuelve el error y el agente pide otro id.

Para retomar después de cerrar el proceso:

```powershell
python demo.py --reanudar
```

Eso solo manda `¿y el primero?` al `thread_id` `sesion-102` ya guardado en `data/checkpoints.sqlite`.

## Traza

`evidencia/traza_react.json` y `evidencia/traza_react.log`.

La copia versionada sale de `python verificar_rubrica.py`. Después de `python demo.py`, el mismo archivo queda con la corrida de `gpt-4o-mini`.

## Base de pedidos

Se crea en `data/pedidos.sqlite` la primera vez que una herramienta consulta.

| Pedido | Cliente | Total | Producto |
| --- | --- | --- | --- |
| PED-102-1 | 102 | $2.000 | Teclado mecánico |
| PED-102-2 | 102 | $4.500 | Monitor 27 pulgadas |
| PED-102-3 | 102 | $8.000 | Notebook 14 pulgadas |
| PED-215-1 | 215 | $3.200 | Auriculares |

El cliente 102 tiene 3 pedidos y un total de $14.500. Borrar `data/pedidos.sqlite` vuelve a sembrar esos datos.
