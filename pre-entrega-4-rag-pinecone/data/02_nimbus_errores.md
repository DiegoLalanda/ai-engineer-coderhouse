# Códigos de error de NimbusQueue

Los errores de la API usan el formato `NQ-XXX` en el campo `error.code` del JSON. El mensaje humano está en `error.message` y puede cambiar de redacción. Las integraciones deben ramificar por el código, nunca por el texto. Esta página documenta los tres códigos que el SDK expone de forma estable.

## NQ-401 Credencial rechazada

NQ-401 significa que la API key falta, está revocada o no pertenece a la región del request. La respuesta HTTP es 401. NimbusQueue no distingue a propósito entre una clave inexistente y una clave de otra cuenta, para no filtrar qué identificadores existen. El header `WWW-Authenticate` vale `Nimbus-Key`. El cliente debe dejar de publicar hasta rotar la credencial. Reintentar NQ-401 en un bucle quema el cupo de requests y no recupera el acceso.

La clave de producción empieza con `nmb_live_` y la de pruebas con `nmb_test_`. Usar una clave de pruebas contra el host de producción también responde NQ-401. El host de producción es `api.nimbusqueue.example`. El host de pruebas es `sandbox.nimbusqueue.example`.

## NQ-422 Mensaje inválido

NQ-422 significa que el cuerpo no cumple el contrato del stream. La respuesta HTTP es 422. `error.details` es una lista de rutas JSON, por ejemplo `body.order_id`. Las causas habituales son un campo obligatorio ausente, un tipo incorrecto o un payload mayor a 256 KiB. NQ-422 no es transitorio. Corregir el productor es la única resolución. El mensaje no entra a la cola ni a la DeadLetterQueue, porque nunca fue aceptado.

## NQ-503 Broker saturado

NQ-503 significa que el broker del stream no puede aceptar publicaciones en este momento. La respuesta HTTP es 503 e incluye el header `Retry-After` en segundos. El significado operativo es saturación de ingesta, no una caída total del plano de control. El SDK ya reintenta NQ-503 respetando `Retry-After`. Una aplicación solo debe tratarlo como incidente si el mismo código se sostiene durante más de cinco minutos. Durante la ventana de reintento no se debe abrir un segundo NimbusClient contra el mismo stream, porque duplica la presión sobre la partición saturada.

El código NQ-503 no aplica a los consumidores. Un consumidor lento no recibe este error: acumula lag y, si vence el ack, el mensaje se reentrega. Confundir NQ-503 con un timeout de ack lleva a escalar al equipo equivocado. La saturación de publicación se mira en la métrica `nimbus_publish_rejected_total` con la etiqueta `code=NQ-503`.

## Tabla operativa

| Código | HTTP | ¿Reintentar? | Destino del mensaje |
| --- | --- | --- | --- |
| NQ-401 | 401 | No | No se acepta |
| NQ-422 | 422 | No | No se acepta |
| NQ-503 | 503 | Sí, según Retry-After | No se acepta hasta un intento exitoso |

Ninguno de estos tres códigos escribe en `orders.created.dlq`. La DeadLetterQueue solo recibe entregas que el consumidor no confirmó después de cinco intentos. Un productor que vea NQ-422 y mueva el payload a una cola propia está implementando una cuarentena de aplicación, no la DLQ del broker. Hay que nombrarla distinto para no mezclar los procedimientos de `replay_dlq`.

El campo `error.request_id` empieza con `req_` y es lo que hay que pegar en un ticket. No alcanza con el `message_id`, porque en NQ-401 y NQ-422 nunca se llegó a crear un mensaje. El soporte busca primero `request_id` en el plano de control y solo después el stream. Incluir la API key en el ticket está prohibido. Incluir el código NQ y el request sí es obligatorio.
