# Acceso y seguridad de la cuenta AulaNova

## Inicio de sesión

Cada estudiante ingresa con el correo usado durante la inscripción. La cuenta
es personal y no debe compartirse. La contraseña debe tener al menos doce
caracteres, una mayúscula, una minúscula y un número. AulaNova no solicita la
contraseña completa por correo, chat ni teléfono.

Si el usuario conoce su contraseña pero desea cambiarla, debe abrir **Mi
perfil**, entrar en **Seguridad** y seleccionar **Cambiar contraseña**. El
sistema pide la clave actual y luego la combinación nueva dos veces. Al
confirmar el cambio se cierran todas las sesiones, excepto la del dispositivo
desde el cual se realizó la operación.

## Recuperación de acceso

Cuando una persona no recuerda su contraseña debe elegir **Olvidé mi
contraseña** en la pantalla de ingreso. Luego debe escribir el correo de su
cuenta. AulaNova envía un enlace de recuperación si el correo existe, pero
muestra el mismo mensaje genérico cuando no existe para evitar revelar
usuarios registrados.

El enlace de recuperación dura quince minutos y solo puede usarse una vez. Si
vence, hay que solicitar uno nuevo; el enlace anterior queda invalidado. El
correo suele llegar en menos de dos minutos. Antes de abrir un ticket se
recomienda revisar las carpetas de spam, promociones y correo no deseado, y
confirmar que el dominio `aulanova.example` no esté bloqueado.

Después de tres intentos fallidos consecutivos, el formulario de recuperación
se bloquea durante treinta minutos. Este límite protege contra ataques
automatizados. El equipo de soporte no puede acortar la espera ni informar la
contraseña anterior, porque las claves se almacenan mediante hashes y no se
pueden leer.

## Doble factor de autenticación

El segundo factor es opcional para estudiantes y obligatorio para docentes y
administradores. Se configura desde **Mi perfil > Seguridad > Verificación en
dos pasos** mediante una aplicación autenticadora compatible con TOTP. Al
activarlo, el sistema entrega ocho códigos de respaldo de un solo uso. Esos
códigos deben guardarse fuera del dispositivo principal.

Si el usuario conserva la contraseña pero perdió el teléfono, puede ingresar
con uno de los códigos de respaldo. Si perdió tanto el segundo factor como los
códigos, debe contactar a soporte. La verificación manual pide el correo de la
cuenta, nombre completo, fecha aproximada de inscripción y los últimos cuatro
dígitos del documento registrado. El análisis puede tardar hasta dos días
hábiles.

## Cambio de correo

El correo principal no puede modificarse desde el perfil si la cuenta tiene
una compra activa. En ese caso se debe crear un ticket de categoría
**Cuenta > Cambio de correo**. El pedido tiene que enviarse desde la dirección
actual. Si ya no se tiene acceso a ella, se aplica el mismo proceso de
verificación manual utilizado para recuperar el segundo factor.

## Sesiones y dispositivos

La sección **Dispositivos activos** muestra el navegador, la ubicación
aproximada y la fecha del último uso de cada sesión. El botón **Cerrar todas
las sesiones** invalida los accesos en un plazo máximo de cinco minutos. Si se
detecta una ubicación desconocida, la recomendación es cerrar las sesiones,
cambiar la contraseña y activar el segundo factor.

Soporte nunca pide instalar programas de acceso remoto para resolver un
problema de contraseña. Cualquier mensaje que solicite la clave completa, un
código TOTP vigente o control remoto del equipo debe reportarse como intento
de fraude.
