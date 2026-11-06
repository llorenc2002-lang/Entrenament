# Serra · entrenamiento y recuperación

Serra cruza un plan de entrenamiento con actividades y métricas de Garmin Connect. Incluye una interfaz adaptable a ordenador y móvil, importación de documentos y una pantalla de chat para consultar el plan y los datos sincronizados.

## Funciones

- Conexión de solo lectura con Garmin Connect mediante su Personal API Key.
- Importación de `.xlsx`, PDF con texto, Word `.docx`, texto, CSV/TSV, HTML y RTF.
- Gráficas para revisar el entrenamiento, la carga y la recuperación.
- Chat con ChatGPT. La modalidad con el plan ChatGPT depende de la disponibilidad de acceso para clientes de código abierto y de los permisos concedidos por OpenAI.
- Sincronización diaria a las 07:00, hora de Madrid, mientras el servidor está activo.

## Ejecutar localmente en Windows

Consulta [README_LOCAL_APP.md](README_LOCAL_APP.md). El flujo local mantiene los datos en `data/` y permite trabajar sin publicar la app.

## Publicar para uso personal

La guía para Render y para alojar la app en un servidor propio está en [README_DEPLOYMENT_PRIVATE.md](README_DEPLOYMENT_PRIVATE.md). La instancia está diseñada para un solo usuario y requiere contraseña. No es un servicio multiusuario.

Antes de conectar Garmin, iniciar sesión en la instancia privada. No publiques `data/`, `logs/`, `outputs/`, `work/`, secretos ni documentos personales. Al enviar una pregunta al chat, Serra comparte con OpenAI el resumen de Garmin, el plan y los documentos importados según el aviso de privacidad de la app.

## Licencia

MIT. Consulta [LICENSE](LICENSE).

