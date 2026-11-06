# Lolo Training App · entrenamiento y recuperación

Lolo Training App cruza un plan de entrenamiento con actividades y métricas de Garmin Connect. Incluye una interfaz adaptable a ordenador y móvil, importación de documentos y una pantalla de chat para consultar el plan y los datos sincronizados.

## Funciones

- Conexión de solo lectura con Garmin Connect mediante su Personal API Key.
- Importación de `.xlsx`, PDF con texto, Word `.docx`, texto, CSV/TSV, HTML y RTF.
- Gráficas para revisar el entrenamiento, la carga y la recuperación.
- Chat con ChatGPT. La modalidad con el plan ChatGPT depende de la disponibilidad de acceso para clientes de código abierto y de los permisos concedidos por OpenAI.
- Sincronización diaria a las 07:00, hora de Madrid, mientras el servidor está activo.

## Ejecutar localmente en Windows

Consulta [README_LOCAL_APP.md](README_LOCAL_APP.md). El flujo local mantiene los datos en `data/` y permite trabajar sin publicar la app.

## Acceder desde PC y móvil sin pagar

Consulta [README_ACCESO_WEB_GRATIS.md](README_ACCESO_WEB_GRATIS.md) y ejecuta `INICIAR_APP_WEB.cmd`. Esto publica el servidor de este ordenador mediante una dirección HTTPS temporal; el ordenador debe quedarse encendido y conectado. La app pide un código al correo que indiques y una contraseña privada. No es un alojamiento permanente.

Para una dirección estable y disponibilidad continua haría falta una cuenta de alojamiento permanente y posiblemente un dominio. La app de uso personal no es multiusuario. No publiques `data/`, `logs/`, `outputs/`, `work/`, secretos ni documentos personales. Al enviar una pregunta al chat, Lolo Training App comparte con OpenAI el resumen de Garmin, el plan y los documentos importados según el aviso de privacidad de la app.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
