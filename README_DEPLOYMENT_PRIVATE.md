# Publicar Serra como app privada

## Alojamiento recomendado: Render

El proyecto incluye `render.yaml` para crear un servicio web Docker en Frankfurt con HTTPS de Render y un disco persistente de 1 GB montado en `/app/data`. Usa el subdominio gratuito `onrender.com`; no hace falta comprar dominio. Para que la app no se suspenda y guarde los datos, el servicio y el disco son de pago. No conectes el Garmin ni importes tus documentos hasta que el servicio esté protegido con una contraseña.

1. Publica este código en un repositorio **público y limpio**, sin `data/`, `logs/`, `.env`, `.venv/`, `outputs/` ni documentos personales. `.gitignore` los excluye.
2. Crea una cuenta en Render, elige **New → Blueprint**, conecta el repositorio y deja que lea `render.yaml`. Usa la región Frankfurt y conserva el plan `starter` y disco de 1 GB configurados; el plan gratuito no es adecuado porque no ofrece el almacenamiento persistente necesario.
3. En PowerShell, ejecuta `.PREPARAR_RENDER.ps1`. Copia `SERRA_APP_PASSWORD` y `SERRA_ENCRYPTION_KEY` desde el archivo local `render-secrets.txt` a **Environment** en Render. Render genera por sí mismo `SERRA_SESSION_SECRET`. No pegues secretos en GitHub, tickets ni chats. Guarda la contraseña y la clave de cifrado en un gestor seguro y elimina el archivo local una vez guardados.
4. Espera a que el despliegue quede listo y abre la URL `https://serra-training.onrender.com` que muestra Render. Inicia sesión con la contraseña. Si el nombre ya está ocupado, Render permitirá cambiar el nombre del servicio; usa la URL que aparezca en tu panel.
5. Importa los documentos desde la app. Después, conecta Garmin con tu Personal API Key y sincroniza. Los datos que importes o sincronices se escribirán en el disco privado de Render. Tus datos del ordenador no se copian solos.

Render ofrece almacenamiento persistente y crea snapshots diarios conservados durante siete días. Aun así, descarga copias propias periódicamente. La instancia es para un usuario y no debe compartirse; la app queda accesible por Internet y protegida con una única contraseña.

El código abierto se distribuye bajo la licencia MIT (`LICENSE`). La publicación incluye solo el programa y su configuración, nunca los datos del usuario ni las claves.

## Alojamiento propio con Docker/Caddy

Si más adelante quieres usar un VPS y un dominio propios, siguen disponibles los pasos de Docker Compose y Caddy de esta guía.

La versión alojable sirve el panel a PC y móvil tras iniciar sesión. Se recomienda una máquina virtual Linux con Docker y un dominio propio. El código escucha solo dentro de la red privada de Docker; Caddy ofrece HTTPS y expone únicamente los puertos web 80 y 443.

## Preparar el servidor

1. Crea una máquina Linux con Docker Compose, una dirección IP pública y almacenamiento persistente. Apunta los registros DNS `A` y/o `AAAA` de tu dominio a esa máquina.
2. Si todavía no existe `.venv`, en PowerShell ejecuta `py -3.12 -m venv .venv` y `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. Después ejecuta `PREPARAR_PUBLICACION.cmd` con doble clic. El script crea `.env`, genera las claves localmente y muestra una contraseña aleatoria para la app. Guárdala en un gestor de contraseñas.
3. Copia el proyecto y `.env` al servidor por SSH/SFTP. No subas `.env` a GitHub. Permite en el cortafuegos solo SSH y los puertos 80/443; el puerto interno 8765 no se publica.
4. En el servidor, ejecuta `docker compose up -d --build`. Caddy solicitará y renovará automáticamente el certificado HTTPS cuando el dominio apunte al servidor.
5. Abre `https://tu-dominio`, inicia sesión con la contraseña generada e importa tu Excel si el plan aún no aparece.

`data/` y `logs/` se excluyen de la imagen. Así no se publica accidentalmente tu información. El servicio usa `serra-data/` y `serra-logs/` en el servidor. Antes del primer arranque, crea las carpetas y asígnalas al usuario del contenedor: `sudo mkdir -p serra-data serra-logs && sudo chown -R 10001:10001 serra-data serra-logs`. Para conservar el histórico de este ordenador, copia el contenido de su carpeta `data/` a `serra-data/` mediante SSH/SFTP y vuelve a aplicar `sudo chown -R 10001:10001 serra-data`. Esa carpeta contiene entrenamientos y notas personales; no la adjuntes a un chat ni la subas a un repositorio. La primera sincronización de Garmin descarga hasta 365 días y conserva los JSON históricos que ya existan.

Haz copias de seguridad periódicas de los volúmenes `serra-data`, `serra-logs`, `caddy-data` y `caddy-config`; conserva `.env` por separado y cifrado. Sin `SERRA_ENCRYPTION_KEY` no se pueden recuperar las credenciales cifradas de Garmin ni ChatGPT.

## Conectar Garmin

1. En Garmin Connect Web, abre [Personal API Key](https://connect.garmin.com/app/settings/personalApiToken), crea la clave y guarda el valor que aparece una sola vez.
2. En Serra → **Conexiones**, pega la clave en el campo local de la app y pulsa **Conectar y guardar**. La clave se cifra antes de persistirla; no la escribas en el chat.
3. Pulsa **Sincronizar ahora** para la primera descarga. Después el servidor sincroniza cada día a las 07:00, hora de Madrid, mientras está funcionando. La clave de Garmin puede caducar en la fecha que elegiste; genera otra en Garmin y reemplázala aquí cuando toque.

Garmin Personal API sirve para consultar los datos de tu propia cuenta. Esta instancia está protegida y configurada para un solo usuario; no debe reutilizarse como integración Garmin para cuentas de otras personas.

## Conectar ChatGPT

La modalidad de uso del plan ChatGPT está disponible para clientes de código abierto elegibles y requiere que concedas `chatgpt.tokens.use.direct`. Las peticiones usan Responses API con `store:false` y `stream:true`. En cada pregunta se envían a OpenAI los datos recientes, las notas, el plan y los documentos importados que aparecen en el aviso de la pantalla. La app no conserva la conversación.

1. En este ordenador, abre PowerShell en la carpeta del proyecto y ejecuta `.\.venv\Scripts\python.exe .\connect_chatgpt.py`.
2. Autoriza Serra en el navegador y crea una frase de paso de transferencia de al menos 12 caracteres cuando el script la solicite en PowerShell.
3. El script crea `outputs\serra-chatgpt-credentials.enc`. En la app alojada, ve a **Conexiones**, selecciona ese archivo e introduce la frase de paso.
4. Cuando aparezca como conectado, elimina el archivo `.enc` del ordenador. El servidor conserva las credenciales cifradas usando la clave de `.env` y renueva los tokens de acceso.

La autorización local es necesaria porque la URL de retorno oficial usa `127.0.0.1`; la guía de OpenAI indica que los servidores remotos reciben la sesión mediante transferencia protegida. Si la cuenta no permite la modalidad o no concede el permiso de uso del plan, el chat no funcionará con la suscripción ChatGPT. Una clave de API convencional sería una alternativa separada y facturada aparte; esta app no la pide ni la almacena.

## Importar documentos

La app admite `.xlsx`, PDF con texto seleccionable, `.docx`, `.txt`, `.md`, `.csv`, `.tsv`, `.html`, `.htm` y `.rtf`. Un PDF escaneado o una imagen requieren OCR, que no está incluido. Los documentos solo se envían a OpenAI al hacer una pregunta en el chat.

## Límites de esta versión

- Acceso web con una contraseña compartida de alta entropía; no hay gestión de varios perfiles ni segundo factor.
- La app debe estar ejecutándose para sincronizar cada día.
- La biblioteca Personal API de Garmin es de solo lectura; no se cargan entrenamientos al reloj.
- No hay publicación automatizada desde este equipo: hace falta provisionar el servidor, dominio y DNS de tu cuenta. Este paquete incluye la configuración Docker/Caddy para ese paso.

