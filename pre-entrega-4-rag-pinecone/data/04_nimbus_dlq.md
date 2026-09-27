# DeadLetterQueue de NimbusQueue

La DeadLetterQueue, abreviada DLQ, guarda mensajes que agotaron los reintentos de entrega. No guarda publicaciones rechazadas con NQ-422, porque esas nunca ingresaron al stream. El nombre de la cola derivada es el stream original más el sufijo `.dlq`. Para `orders.created` la cola es `orders.created.dlq`. Se consulta con la misma API key y la misma región.

Un mensaje pasa a la DLQ cuando `attempt` llega a 5. El contador incluye la entrega original. El primer vencimiento de `NIMBUS_ACK_TIMEOUT` incrementa `attempt`, pero no mueve el mensaje todavía. Recién el quinto intento fallido crea el registro en la DLQ y lo saca de la cola principal. El registro conserva `message_id`, `body`, `first_failed_at` y `last_error`.

## Reproceso

Para reprocesar un mensaje de la DeadLetterQueue se usa `client.replay_dlq(message_id)`. El método vuelve a publicar el cuerpo en el stream original, con un `message_id` nuevo y `attempt` en 1. El registro viejo queda marcado como `replayed` y no se vuelve a entregar desde la DLQ. Reprocesar sin corregir la causa vuelve a llenar la cola. El procedimiento operativo es corregir el consumidor, desplegarlo y después llamar a `replay_dlq`.

```python
from nimbusqueue.client import NimbusClient

with NimbusClient(region="sa-east-1", stream="orders.created") as client:
    moved = client.replay_dlq("msg_01HZXDLQ")
    print(moved.message_id)
```

`replay_dlq` exige el `message_id` completo, con el prefijo `msg_`. No acepta el sequence number. Si el identificador no está en la DLQ, responde con un error de aplicación `DLQMessageNotFound`. Ese error es local del SDK cuando el broker contesta 404 sobre el recurso de la DLQ. No es NQ-503 ni NQ-401.

La DLQ retiene mensajes durante catorce días. Después se purgan aunque no se hayan reprocesado. No hay forma de extender la retención desde el cliente. Un replay dentro de ese plazo no reinicia los catorce días del registro original, porque el registro original pasa a `replayed` y el mensaje nuevo vive en el stream principal con su propio reloj.

## Inspección antes del replay

`client.list_dlq(limit=50)` devuelve los registros en estado `waiting`, del más antiguo al más nuevo. Cada item trae `message_id`, `attempt` y `last_error`. El listado no saca los mensajes de la cola. Sirve para decidir si el fallo es sistemático, por ejemplo el mismo `last_error` en todos, o un caso aislado. Reprocesar con `replay_dlq` un lote completo se hace iterando ese listado. No existe `replay_all` justamente para evitar un replay ciego.

Si `last_error` menciona un timeout de base de datos, el replay inmediato repite el incidente. La guía operativa pide una ventana de estabilidad de quince minutos en el consumidor nuevo antes del primer `replay_dlq`. Durante esa ventana el stream principal sigue recibiendo tráfico nuevo. Los mensajes de la DLQ no bloquean ese tráfico: ya salieron de la cola principal cuando cumplieron cinco intentos.

Un `message_id` marcado `replayed` responde `DLQMessageNotFound` si se intenta un segundo replay. Hay que usar el `message_id` nuevo que devolvió el primer replay si ese también terminó en la DLQ. Guardar solo el identificador original impide rastrear la segunda falla. El campo `replayed_as` del registro viejo contiene ese identificador nuevo.
