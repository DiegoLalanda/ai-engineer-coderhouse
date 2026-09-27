# Cliente Python de NimbusQueue

NimbusClient es la clase pública del SDK `nimbusqueue` para publicar y consumir mensajes. Se importa desde `nimbusqueue.client` y no debe confundirse con el cliente HTTP interno `TransportSession`. La versión mínima compatible es Python 3.11. El constructor exige tres argumentos: `api_key`, `region` y `stream`. La región válida para esta documentación es `sa-east-1`. El stream de ejemplo del manual se llama `orders.created`.

La inicialización recomendada deja el cliente dentro de un context manager. Al salir del bloque se cierran las conexiones HTTP y se confirma el último ack pendiente. Si se instancia sin context manager, hay que llamar a `client.close()` en un bloque `finally`. Omitir ese cierre deja sockets en estado TIME_WAIT y el proceso puede agotar el límite de descriptores después de varios miles de publicaciones.

```python
from nimbusqueue.client import NimbusClient

with NimbusClient(
    api_key="nmb_live_example",
    region="sa-east-1",
    stream="orders.created",
) as client:
    receipt = client.publish({"order_id": "A-100"}, key="A-100")
    print(receipt.message_id)
```

`publish` devuelve un `PublishReceipt` con `message_id`, `sequence` y `ingested_at`. El `message_id` tiene el prefijo `msg_` y es el identificador que debe guardarse para soporte. La clave `key` ordena los mensajes de una misma entidad: dos publicaciones con la misma clave no se entregan en paralelo al mismo grupo de consumidores. No es una clave de cifrado.

El método `consume` devuelve un iterador de `Delivery`. Cada entrega expone `body`, `message_id`, `attempt` y `ack()`. Hay que llamar a `ack()` solo después de persistir el efecto de negocio. Si el proceso muere antes del ack, NimbusQueue vuelve a entregar el mensaje. El cuerpo llega como diccionario cuando se publicó un objeto JSON. Los bytes crudos se piden con `delivery.raw_body`.

El cliente reintenta errores de red transitorios tres veces, con esperas de 200, 400 y 800 milisegundos. No reintenta un error 422 de validación ni un 401 de credenciales. Esos códigos están documentados en el manual de errores y no deben capturarse como fallos genéricos de transporte. El timeout de cada request HTTP es de diez segundos y se configura aparte del ack timeout del consumidor.

Para pruebas locales existe `NimbusClient.for_tests()`, que no abre red y guarda los mensajes en memoria. No debe usarse en producción: no aplica la firma HMAC ni respeta la región. El método existe para tests unitarios del publicador, no para simular el servicio completo.

## Sesión y orden de entrega

`NimbusClient` mantiene un `consumer_group` opcional. Si no se pasa, el grupo se llama `default`. Dos procesos con el mismo grupo se reparten los mensajes de `orders.created`. Dos procesos con grupos distintos reciben una copia cada uno. Esa distinción importa cuando facturación y auditoría deben ver el mismo evento. No se configura con `NIMBUS_ACK_TIMEOUT`; ese valor solo controla el plazo de confirmación y está documentado en la página de configuración.

`publish` es sincrónico. No existe `publish_async` en la versión 2 del SDK. Quien necesite concurrencia abre varias tareas, cada una con su propio cliente, o publica en serie dentro de una tarea. Compartir un mismo `NimbusClient` entre hilos no es seguro: la sesión HTTP interna no usa candado. El síntoma de compartirlo es un `message_id` mezclado o un ack aplicado al delivery equivocado.

El recibo `PublishReceipt.sequence` es monótono por stream y por clave, no global. Sirve para detectar huecos de una misma `key`, no para ordenar todo el stream. El manual recomienda persistir `message_id` y tratar `sequence` como diagnóstico. Un consumidor que descarte duplicados debe usar `message_id`, porque un replay desde la DeadLetterQueue genera un identificador nuevo y no reutiliza el sequence original.
