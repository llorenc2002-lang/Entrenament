# Garmin Connect · sincronización local de respaldo

La pantalla Serra ahora usa la **Personal API oficial de Garmin** con clave personal. Para conectarla, sigue [README_LOCAL_APP.md](README_LOCAL_APP.md). Esa es la vía principal; no necesita el inicio de sesión con contraseña de abajo.

El exportador `sync_garmin.py` con `python-garminconnect` se conserva solo como método local de respaldo y para los datos históricos existentes.

---

# Exportador local de respaldo (Windows)

This project exports data from Garmin Connect cloud through `python-garminconnect`. It does not pair or communicate with a watch over USB or Bluetooth.

## First sign-in or reauthentication

Open PowerShell in this project folder and run:

```powershell
& ".\.venv\Scripts\python.exe" ".\sync_garmin.py" --interactive
```

Enter your Garmin email and hidden password in that Terminal. Enter the MFA code there if requested. Leave the window open until the export completes. This bypasses PowerShell's script-execution policy by invoking the project's Python environment directly.

The current sync uses the existing Garmin export through September as its historical boundary: activities on or after 1 October 2026, plus 36 days of daily summaries, heart rate, sleep, steps, and stress. The Garmin archive folder is read-only for this setup and is not modified.

The library stores refreshable session tokens under `%LOCALAPPDATA%\GarminConnectExport\tokens`; it does not store the Garmin password. If the session expires, rerun the interactive command above. Scheduled runs never prompt and stop with a reauthentication message if the saved session is no longer valid.

## Output and schedule

- `data\activities\`: one JSON summary and one TCX file per activity; missing files are retried on later runs.
- `data\daily\`: JSON snapshots for daily summaries, heart rate, sleep, steps, and stress. The initial sync fetches the requested history; later runs refresh the most recent seven days.
- `logs\sync.log`: sync progress and sanitized exception class/HTTP code; credentials, token contents, and health values are not logged. Activity progress is reported every 20 records.
- Windows Task Scheduler runs `run_garmin_sync.ps1` daily at 07:00 local time while this Windows account is signed in. If the computer is off, the next sign-in starts a catch-up run.

To sync manually using the saved session without prompting, run:

```powershell
& ".\.venv\Scripts\python.exe" ".\sync_garmin.py"
```

The export is a local copy of personal health and location data. Keep the project folder and token folder private.


