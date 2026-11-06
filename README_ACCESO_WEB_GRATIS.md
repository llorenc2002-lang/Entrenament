# Acceso web gratuito · Lolo Training App

## Qué hace

El servidor de la app y sus datos permanecen en este ordenador. `INICIAR_APP_WEB.cmd` arranca el servidor con inicio de sesión, crea un túnel HTTPS temporal protegido por código de correo y abre la dirección pública. Garmin se sincroniza desde la app directamente con Garmin Connect; no hace falta ejecutar el exportador manual.

La primera vez descarga `cloudflared` desde la publicación oficial de Cloudflare y comprueba su SHA-256 antes de ejecutarlo. En la ventana de PowerShell eliges una contraseña de 20 caracteres o más; se escribe oculta y queda cifrada con Windows DPAPI en `%LOCALAPPDATA%\LoloTrainingApp`. La clave de sesión se guarda allí del mismo modo. La clave que cifra las credenciales de Garmin y ChatGPT se conserva en `data/app/local_encryption.key`, junto a los datos y fuera del repositorio. Las claves no se incluyen en los registros.

## Iniciar

1. En la carpeta de la app, haz doble clic en `INICIAR_APP_WEB.cmd`.
2. En la ventana que se abre, crea la contraseña de la app en la entrada oculta y escribe el correo al que tienes acceso desde el móvil. Cloudflare enviará un código al abrir el enlace.
3. Copia en el móvil la dirección `https://….trycloudflare.com` que aparece y guárdala en favoritos. Introduce el código del correo y, después, la contraseña que elegiste para Lolo Training App.
4. En **Conexiones**, conecta Garmin, sincroniza y carga el Excel si todavía no aparece.
5. Para cortar el acceso web, vuelve a la ventana del iniciador y pulsa **Intro**.

Mantén el ordenador encendido, conectado a internet y con esa ventana abierta mientras uses la app. Al cerrar o reiniciar el túnel, la dirección cambia; vuelve a abrir el iniciador y guarda la nueva dirección. El ordenador conserva los datos. No borres `data/` ni `%LOCALAPPDATA%\LoloTrainingApp`.

## Instalar en el móvil

Abre la dirección vigente en Chrome o Edge mientras el túnel está activo y usa **Instalar aplicación** o **Añadir a pantalla de inicio**. Como la dirección temporal cambia al reiniciar, puede hacer falta instalarla de nuevo con el enlace nuevo.

## Restablecer la contraseña de la app

Cierra el iniciador. Borra únicamente `%LOCALAPPDATA%\LoloTrainingApp\app-password.dpapi`; en la siguiente ejecución se generará una contraseña nueva. No borres `data/app/local_encryption.key`: sin esa clave no se pueden descifrar la conexión Garmin y la conexión ChatGPT guardadas localmente.

## Límites del alojamiento gratuito

El subdominio `trycloudflare.com` es temporal y Cloudflare lo ofrece para pruebas y desarrollo; no promete disponibilidad continua. La app solo está accesible mientras el ordenador y el iniciador están activos. El nombre cambia en cada inicio. Para una web siempre disponible y una dirección estable hace falta migrar el servidor a un alojamiento permanente y configurar una cuenta y un dominio.
