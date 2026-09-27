# Firma HMAC de NimbusQueue

Todas las peticiones de producción llevan una firma HMAC-SHA256. El servidor rechaza un request sin firma aunque la API key sea válida. La firma no reemplaza a la API key: la clave identifica a la cuenta y la firma demuestra que el cuerpo no fue alterado en tránsito. El algoritmo no es HMAC-SHA1 ni una firma RSA. Usar otro algoritmo produce un 401 distinto de NQ-401, con el código `NQ-409` reservado a integridad. En esta guía el caso operativo sigue siendo la cabecera documentada abajo.

## Header X-Nimbus-Signature

La cabecera obligatoria se llama `X-Nimbus-Signature`. El valor tiene la forma `t=<unix>,v1=<hex>`. `t` es el timestamp en segundos. `v1` es el hexadecimal en minúsculas del HMAC-SHA256 calculado sobre la cadena `f"{timestamp}.{raw_body}"`. La clave del HMAC es el secreto de firma, que no es la API key. El secreto se obtiene en el panel con el nombre `signing_secret` y empieza con `nmb_sig_`.

El SDK arma la cabecera si se pasa `signing_secret` al constructor o si existe la variable `NIMBUS_SIGNING_SECRET`. No hay que setear `X-Nimbus-Signature` a mano cuando se usa `NimbusClient`. Un cliente HTTP externo sí debe calcularla. El servidor tolera un desfase de 300 segundos entre `t` y su reloj. Fuera de esa ventana responde que la firma expiró y no llega a evaluar el cuerpo.

El cuerpo firmado es el raw body exacto, con el mismo orden de bytes que se envía. Reordenar claves de un JSON antes de firmar y después de serializar cambia el HMAC. La recomendación es firmar los bytes ya serializados y enviar esos mismos bytes. No se incluye el path ni el método en la cadena firmada de la versión 1 del protocolo. Esa decisión está fijada: agregar el path rompería la compatibilidad con `v1`.

Los ejemplos del sandbox aceptan requests sin firma solo si la API key empieza con `nmb_test_`. En producción la ausencia de `X-Nimbus-Signature` nunca se perdona. Los logs del SDK imprimen el timestamp y el prefijo del secreto, nunca el HMAC completo ni el secreto.

## Rotación del signing secret

El panel puede tener dos secretos activos: `current` y `previous`. Durante veinticuatro horas el servidor acepta firmas de cualquiera de los dos. El SDK usa solo `NIMBUS_SIGNING_SECRET`, así que la rotación correcta es publicar el secreto nuevo en el gestor de secretos, reiniciar los publicadores y recién después revocar el anterior. Revocar primero produce 401 de integridad en todos los requests firmados con el secreto viejo.

No hay que reutilizar el secreto como API key ni al revés. Una API key `nmb_live_` dentro de `NIMBUS_SIGNING_SECRET` genera un HMAC que el servidor no puede verificar. El síntoma es constante y no depende del cuerpo. El header sigue llamándose `X-Nimbus-Signature` y el prefijo de versión sigue siendo `v1`. Un valor `v2=` se ignora en esta versión del protocolo y, si es el único, se trata como firma ausente.

Los relojes de los publicadores deben usar NTP. Un desfase mayor a 300 segundos no se corrige reintentando: hay que ajustar la hora del host. El campo `t` no es el `ingested_at` del recibo. `t` lo pone el cliente al firmar. `ingested_at` lo pone el broker al aceptar. Comparar los dos sirve para medir deriva, no para rearmar la firma.
