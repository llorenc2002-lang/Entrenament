# Serra · panel personal de entrenamiento

## Uso local en Windows

1. Ejecuta `START_LOCAL_APP.cmd` con doble clic. Se abre el panel en `http://127.0.0.1:8765`.
2. En **Conexiones**, crea en Garmin Connect una clave Personal API y pégala en la app; no la envíes por correo o chat.
3. Pulsa **Sincronizar ahora** para descargar actividades y datos diarios. Después la app intenta sincronizar cada día a las 07:00 de Madrid mientras está abierta. El programa antiguo `sync_garmin.py` sigue disponible como copia local/fallback.
4. Importa el plan en Excel o cualquier documento compatible desde el botón superior.
5. Para cerrar el servidor local, usa **Conexiones → Cerrar la app local**.

Garmin Personal API es la conexión principal y de solo lectura. La clave se guarda cifrada dentro de `data\app`; en modo local la app crea automáticamente una clave de cifrado en esa carpeta. El Excel original no se modifica.

## ChatGPT

Para usar tu plan ChatGPT, ejecuta `.\.venv\Scripts\python.exe .\connect_chatgpt.py` en PowerShell. El asistente local abre el navegador, valida la autorización de OpenAI y crea un archivo cifrado en `outputs\serra-chatgpt-credentials.enc`. En Conexiones, importa ese archivo y escribe la frase de paso que acabas de crear. Elimina el archivo después de importarlo.

Cuando envías una pregunta, el sistema comparte con OpenAI la planificación, las notas de entrenamiento, actividades y recuperación recientes, además de los documentos importados. No se guarda el historial del chat y la respuesta usa `store:false`. La opción de plan ChatGPT depende de que OpenAI habilite el permiso correspondiente en tu cuenta.

## Documentos

Admite Excel `.xlsx`, PDF con texto seleccionable, Word `.docx`, texto `.txt`, Markdown, CSV/TSV, HTML y RTF. Los PDF escaneados e imágenes requieren OCR no incluido. Los documentos se guardan localmente y solo se envían a OpenAI al preguntar desde el chat.

## Modo alojado

El paquete incluye una plantilla para Render y Docker + Caddy para usar la app en un servidor propio con HTTPS, contraseña y almacenamiento persistente. Consulta [README_DEPLOYMENT_PRIVATE.md](README_DEPLOYMENT_PRIVATE.md). No publiques `data/`, `logs/`, `outputs/`, `work/` ni `.env` en un repositorio. Garmin Personal API está pensado para la cuenta personal de un único usuario.

