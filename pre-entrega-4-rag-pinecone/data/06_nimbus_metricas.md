# Métricas de NimbusQueue

El plano de datos expone métricas en formato Prometheus bajo `/metrics` del sidecar `nimbus-agent`. No se consultan con el SDK de publicación. El agente corre al lado del consumidor y lee el lag desde el broker usando credenciales de solo lectura. Mezclar la API key de publicación con el agente no está soportado.

## Lag del consumidor

La serie `nimbus_consumer_lag_messages` indica cuántos mensajes confirmados por el broker todavía no recibieron `ack`. Las etiquetas son `stream`, `consumer_group` y `region`. Un lag creciente con throughput estable significa que el consumidor procesa más lento de lo que se publica. No significa por sí solo que haya un NQ-503. NQ-503 mide rechazo de publicaciones, no atraso de lectura.

La alerta recomendada dispara cuando el lag se mantiene por encima de 1000 mensajes durante diez minutos. El grupo de ejemplo del manual se llama `billing-workers`. Una alerta sin la etiqueta `consumer_group` mezcla grupos y genera falsos positivos. El lag en la DLQ usa otra serie, `nimbus_dlq_depth_messages`, y no debe entrar en la misma regla.

## Publicaciones rechazadas

`nimbus_publish_rejected_total` es un contador. La etiqueta `code` separa `NQ-401`, `NQ-422` y `NQ-503`. Un aumento de `NQ-422` apunta a un deploy de un productor incompatible. Un aumento de `NQ-503` apunta a saturación del stream. El cuantil de latencia de publicación exitosa está en `nimbus_publish_latency_seconds`. El objetivo interno del manual es mantener el percentil 99 por debajo de 250 milisegundos en `sa-east-1`.

El dashboard de referencia se llama `Nimbus / Stream health` y asume que las tres series anteriores existen. No incluye métricas de negocio como pedidos pagados. Esas pertenecen a la aplicación, no al broker. Renombrar las series rompe las alertas empaquetadas con `nimbus-agent` 2.4.

## Sidecar y cardinalidad

`nimbus-agent` 2.4 escucha en `127.0.0.1:9474`. No debe publicarse a internet. El scrape de Prometheus usa ese puerto y la ruta `/metrics`. Si el agente no puede autenticarse contra el broker, la serie `nimbus_agent_up` vale 0 y el resto de las series desaparece. No se reemplazan por ceros. Una alerta de lag tiene que exigir `nimbus_agent_up == 1` para no interpretar un agente caído como un stream vacío.

La etiqueta `region` en este manual es siempre `sa-east-1`. Agregar regiones nuevas multiplica la cardinalidad. El agente rechaza etiquetas con el identificador de un mensaje, porque un `message_id` distinto por entrega haría crecer la base de Prometheus sin límite. Por eso `nimbus_consumer_lag_messages` no tiene etiqueta `message_id`. El detalle de un mensaje puntual se consulta por API, no por métricas.

El percentil 99 de `nimbus_publish_latency_seconds` se calcula sobre publicaciones aceptadas. Los rechazos NQ-503 no entran en ese histograma. Mirar solo la latencia durante una saturación esconde el incidente. La señal de saturación es el contador `nimbus_publish_rejected_total` con `code=NQ-503`, cruzada con el lag únicamente si el problema también afecta a los consumidores.
