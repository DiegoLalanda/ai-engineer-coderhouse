# Variables de configuración de NimbusQueue

El SDK lee la configuración desde variables de entorno y permite pisarla con argumentos del constructor. Si una variable y un argumento coexisten, gana el argumento. Los nombres de entorno usan el prefijo `NIMBUS_` y están en mayúsculas. No se aceptan alias antiguos como `NMB_TIMEOUT`.

## NIMBUS_ACK_TIMEOUT

`NIMBUS_ACK_TIMEOUT` define cuántos segundos puede retener un consumidor un mensaje antes de confirmarlo. El valor por defecto es 30. El mínimo aceptado es 5 y el máximo es 900. Se expresa como un entero, sin sufijo de unidad: `NIMBUS_ACK_TIMEOUT=45` significa cuarenta y cinco segundos. Si el trabajador no llama a `ack()` dentro de ese plazo, el broker considera la entrega vencida y vuelve a enviar el mensaje. No borra el mensaje ni lo mueve a la DeadLetterQueue en el primer vencimiento.

Hay que subir `NIMBUS_ACK_TIMEOUT` cuando el procesamiento incluye una llamada externa lenta, por ejemplo una autorización de pago. Hay que bajarlo cuando el consumidor solo persiste en una base local y se quiere detectar rápido un proceso colgado. Cambiar la variable exige reiniciar el proceso: el cliente la lee una sola vez al construir `NimbusClient`. Un valor no numérico impide arrancar y lanza `ConfigError` antes de abrir la red.

## NIMBUS_REGION y NIMBUS_STREAM

`NIMBUS_REGION` selecciona el plano de datos. Para esta guía el valor esperado es `sa-east-1`. Una región distinta con una API key de `sa-east-1` termina en NQ-401. `NIMBUS_STREAM` es el nombre lógico del stream, por ejemplo `orders.created`. El nombre distingue mayúsculas y no puede contener espacios. `NIMBUS_API_KEY` transporta el secreto. No debe commitearse ni imprimirse en logs. El helper `client.redacted_config()` muestra la región y el stream, y enmascara la clave.

`NIMBUS_MAX_IN_FLIGHT` limita cuántas entregas sin ack puede tener un consumidor. El valor por defecto es 16. Subirlo aumenta el throughput y también la cantidad de duplicados posibles si el proceso se cae. No reemplaza a `NIMBUS_ACK_TIMEOUT`: una entrega cuenta contra ambos límites a la vez.

## Precedencia y errores de arranque

La precedencia completa es: argumento del constructor, después variable de entorno, después el default documentado. Un archivo `.env` lo carga la aplicación, no el SDK. Si la aplicación no llama a su loader, `NIMBUS_ACK_TIMEOUT` puede quedar invisible y el proceso usa 30 segundos sin avisar. Por eso el log de arranque de `NimbusClient` imprime la configuración efectiva ya resuelta, con la clave enmascarada.

`ConfigError` aparece antes de cualquier request cuando el valor es ilegible: `NIMBUS_ACK_TIMEOUT=45s` es inválido porque sobra el sufijo, y `NIMBUS_REGION=` vacío también. Un valor fuera de rango, como 2 o 2000 segundos, lanza el mismo error con el límite permitido en el mensaje. No se traduce a NQ-422. NQ-422 es un rechazo del broker sobre un mensaje. `ConfigError` es local y significa que el proceso ni siquiera intentó conectar.

Cambiar `NIMBUS_STREAM` de `orders.created` a otro nombre no migra mensajes. El stream nuevo empieza vacío. La DLQ tampoco se copia. El procedimiento de renombre es crear el stream destino, publicar en doble escritura durante la migración y recién después apagar el consumidor viejo. No hay un flag `NIMBUS_MIGRATE` en esta versión.
