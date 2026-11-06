# Garmin Connect · sincronización local de respaldo

La app Lolo Training App usa la **Personal API oficial de Garmin** con una clave personal. Para conectarla, sigue [README_LOCAL_APP.md](README_LOCAL_APP.md). Esta es la vía principal y no necesita la contraseña de Garmin.

El exportador `sync_garmin.py` con `python-garminconnect` se conserva como método local de respaldo para los datos históricos existentes. Accede a Garmin Connect en la nube; no empareja el reloj por USB ni Bluetooth.
