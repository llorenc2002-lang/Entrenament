"""Local-only training dashboard backed by the existing Garmin export."""
from __future__ import annotations

import json
import base64
import hashlib
import hmac
import logging
import os
import posixpath
import re
import threading
import time
import secrets
import webbrowser
import zipfile
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
APP_DATA = DATA / "app"
ACTIVITIES = DATA / "activities"
DAILY = DATA / "daily"
WEB = ROOT / "app"
DEFAULT_WORKBOOK = Path(os.environ.get(
    "GARMIN_PLAN_FILE",
    str(ROOT / "serra-plan.xlsx"),
))
HOST = os.environ.get("SERRA_HOST", "0.0.0.0" if os.environ.get("RENDER") else "127.0.0.1")
PORT = int(os.environ.get("PORT", os.environ.get("SERRA_PORT", os.environ.get("GARMIN_APP_PORT", "8765"))))
PUBLIC_MODE = bool(os.environ.get("SERRA_APP_PASSWORD"))
LOGIN_FAILURES: dict[str, list[float]] = {}
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
APP_DATA.mkdir(parents=True, exist_ok=True)
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG_DIR / "local_app.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def col_index(reference: str) -> int:
    col = re.match(r"[A-Z]+", reference.upper())
    value = 0
    for ch in (col.group(0) if col else ""):
        value = value * 26 + ord(ch) - 64
    return value - 1


def parse_xlsx(path: Path) -> dict[str, list[list[object]]]:
    """Read cached cell values from an ordinary .xlsx using only Python's stdlib."""
    with zipfile.ZipFile(path) as book:
        if sum(item.file_size for item in book.infolist()) > 100 * 1024 * 1024:
            raise ValueError("El Excel supera el tamaño descomprimido permitido.")
        names = set(book.namelist())
        strings = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            strings = ["".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t"))
                       for si in root.findall("m:si", NS)]
        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relationships}
        sheets: dict[str, list[list[object]]] = {}
        for sheet in workbook.findall("m:sheets/m:sheet", NS):
            rel_id = sheet.attrib[f"{{{NS['r']}}}id"]
            target = targets[rel_id]
            target = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                        else posixpath.join("xl", target))
            root = ET.fromstring(book.read(target))
            rows = []
            for row in root.findall("m:sheetData/m:row", NS):
                cells: dict[int, object] = {}
                for cell in row.findall("m:c", NS):
                    typ = cell.attrib.get("t")
                    value = cell.find("m:v", NS)
                    if typ == "inlineStr":
                        parsed: object = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                    elif value is None or value.text is None:
                        parsed = ""
                    elif typ == "s":
                        parsed = strings[int(value.text)]
                    elif typ == "b":
                        parsed = value.text == "1"
                    else:
                        try:
                            number = float(value.text)
                            parsed = int(number) if number.is_integer() else number
                        except ValueError:
                            parsed = value.text
                    cells[col_index(cell.attrib.get("r", "A1"))] = parsed
                if cells:
                    rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
                else:
                    rows.append([])
            sheets[sheet.attrib["name"]] = rows
        return sheets


def as_excel_date(value) -> str | None:
    if isinstance(value, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(value))).date().isoformat()
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value[:10]).date().isoformat()
        except ValueError:
            for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(value, fmt).date().isoformat()
                except ValueError:
                    pass
    return None


def number(value):
    try:
        if value in (None, "", "No mesurat", "No informat", "No aplicable", "-"):
            return None
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def import_workbook(path: Path) -> dict:
    sheets = parse_xlsx(path)
    if "Programacio diaria" not in sheets or "Registre entrenament" not in sheets:
        raise ValueError("No encuentro las hojas «Programacio diaria» y «Registre entrenament».")
    plan = []
    rows = sheets["Programacio diaria"]
    for index, row in enumerate(rows[5:], start=6):
        if len(row) < 15:
            continue
        day = as_excel_date(row[1])
        if not day:
            continue
        typ = str(row[4] or "Sesión planificada").strip()
        plan.append({
            "id": f"plan-{index}", "week": row[0], "date": day, "day_name": str(row[2] or ""),
            "phase": str(row[3] or ""), "type": typ, "time": str(row[5] or ""),
            "km": number(row[6]) or 0, "elevation": number(row[7]) or 0,
            "duration": str(row[8] or ""), "intensity": str(row[9] or ""),
            "terrain": str(row[10] or ""), "description": str(row[11] or ""),
            "fuel": str(row[12] or ""), "gear": str(row[13] or ""), "status": str(row[14] or ""),
        })
    diary = []
    rows = sheets["Registre entrenament"]
    for index, row in enumerate(rows[3:], start=4):
        if len(row) < 22:
            row = row + [""] * (22 - len(row))
        day = as_excel_date(row[0])
        comment, next_step = str(row[20] or "").strip(), str(row[21] or "").strip()
        # The workbook has many prefilled blank rows; actual notes distinguish genuine entries.
        if not day or not (comment or next_step):
            continue
        diary.append({
            "id": f"diary-{index}", "date": day, "planned": str(row[1] or ""),
            "planned_km": number(row[2]), "actual_km": number(row[3]),
            "elevation": number(row[4]), "minutes": number(row[5]), "rpe": number(row[6]),
            "glucose_start": str(row[7] or ""), "glucose_trend": str(row[8] or ""),
            "glucose_checks": str(row[9] or ""), "glucose_end": str(row[10] or ""),
            "carbs_g": number(row[11]), "fluid_ml": number(row[12]), "sodium_mg": number(row[13]),
            "fuel": str(row[14] or ""), "gi_symptoms": str(row[15] or ""),
            "hypoglycemia": str(row[16] or ""), "celiac_alert": str(row[17] or ""),
            "pain": number(row[18]), "sleep_hours": number(row[19]),
            "comment": comment, "next_step": next_step,
        })
    result = {"source": path.name, "source_path": str(path), "imported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
              "plan": plan, "diary": diary}
    atomic_json(APP_DATA / "workbook.json", result)
    return result


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return fallback


def deep_value(obj, names):
    wanted = set(names)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in wanted and value not in (None, ""):
                return value
        for value in obj.values():
            found = deep_value(value, names)
            if found not in (None, ""):
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = deep_value(value, names)
            if found not in (None, ""):
                return found
    return None


def load_activities() -> list[dict]:
    activities = []
    for path in ACTIVITIES.glob("*.json"):
        raw = read_json(path, None)
        if not isinstance(raw, dict):
            continue
        act_type = raw.get("activityType") or {}
        key = act_type.get("typeKey", "unknown") if isinstance(act_type, dict) else str(act_type)
        start = str(raw.get("startTimeLocal") or raw.get("startTimeGMT") or "")
        activities.append({
            "id": str(raw.get("activityId") or path.stem), "date": start[:10], "start": start,
            "name": str(raw.get("activityName") or key.replace("_", " ").title()), "type": key,
            "distance_km": round((number(raw.get("distance")) or 0) / 1000, 2),
            "minutes": round((number(raw.get("duration")) or 0) / 60, 1),
            "elevation_m": round(number(raw.get("elevationGain")) or 0),
            "avg_hr": number(raw.get("averageHR")), "max_hr": number(raw.get("maxHR")),
            "calories": number(raw.get("calories")),
        })
    activities.sort(key=lambda x: (x["date"], x["start"], x["id"]))
    return activities


def is_run(item: dict) -> bool:
    kind = item.get("type", "").lower()
    return any(token in kind for token in ("run", "running", "trail_run"))


def daily_values() -> list[dict]:
    result: dict[str, dict] = {}
    for path in DAILY.glob("*.json"):
        if path.name.startswith("."):
            continue
        obj = read_json(path, {})
        name = obj.get("dataset")
        records = obj.get("data")
        if not isinstance(records, list):
            continue
        for item in records:
            if not isinstance(item, dict):
                continue
            day = str(item.get("calendarDate") or (item.get("data") or {}).get("calendarDate") or "")
            if not day:
                continue
            value = result.setdefault(day, {"date": day})
            nested = item.get("data") if isinstance(item.get("data"), dict) else item
            if name == "heart_rate":
                value["resting_hr"] = number(nested.get("restingHeartRate"))
                value["resting_hr_7d"] = number(nested.get("lastSevenDaysAvgRestingHeartRate"))
            elif name == "stress":
                value["stress"] = number(nested.get("avgStressLevel"))
            elif name == "sleep":
                values = item.get("values") if isinstance(item.get("values"), dict) else nested
                sec = number(values.get("totalSleepTimeInSeconds"))
                value["sleep_hours"] = round(sec / 3600, 2) if sec is not None else None
                value["sleep_score"] = number(values.get("sleepScore"))
                value["hrv"] = number(values.get("avgOvernightHrv") or values.get("averageHrv") or values.get("avgHrv"))
                if value["hrv"] is None:
                    value["hrv"] = number(values.get("hrvSummary", {}).get("weeklyAvg")) if isinstance(values.get("hrvSummary"), dict) else None
            elif name == "steps":
                value["steps"] = number(item.get("totalSteps"))
            elif name == "hrv":
                value["hrv"] = number(deep_value(item, ("weeklyAvg", "lastNightAvg", "lastNightAvgValue", "avgOvernightHrv")))
            elif name == "summaries":
                if value.get("steps") is None:
                    value["steps"] = number(deep_value(item, ("totalSteps", "steps")))
                if value.get("resting_hr") is None:
                    value["resting_hr"] = number(deep_value(item, ("restingHeartRate", "restingHR")))
                if value.get("stress") is None:
                    value["stress"] = number(deep_value(item, ("avgStressLevel", "averageStress")))
            if name == "sleep":
                values = item.get("values") if isinstance(item.get("values"), dict) else nested
                if value.get("sleep_hours") is None:
                    sec = number(deep_value(item, ("totalSleepTimeInSeconds", "sleepTimeSeconds", "totalSleepSeconds")))
                    value["sleep_hours"] = round(sec / 3600, 2) if sec is not None else None
                if value.get("sleep_score") is None:
                    value["sleep_score"] = number(deep_value(item, ("sleepScore", "overallSleepScore")))
                if value.get("hrv") is None:
                    value["hrv"] = number(deep_value(item, ("avgOvernightHrv", "averageHrv", "avgHrv")))
    return [result[k] for k in sorted(result)]


def load_matches() -> dict:
    value = read_json(APP_DATA / "matches.json", {"overrides": {}})
    return value if isinstance(value, dict) else {"overrides": {}}


def make_matches(plan: list[dict], activities: list[dict], diary: list[dict], overrides: dict) -> list[dict]:
    by_id = {a["id"]: a for a in activities}
    by_date: dict[str, list[dict]] = {}
    for act in activities:
        by_date.setdefault(act["date"], []).append(act)
    diary_by_date = {d["date"]: d for d in diary}
    reserved = {str(v) for v in overrides.values() if v and v != "skip"}
    results = []
    for item in plan:
        override = overrides.get(item["id"])
        chosen = by_id.get(str(override)) if override else None
        if override == "skip":
            chosen = None
        if chosen:
            reserved.add(chosen["id"])
            confidence, status = "manual", "Confirmado por ti"
        elif override == "skip":
            confidence, status = "skip", "Marcado sin coincidencia"
        else:
            candidates = [a for a in by_date.get(item["date"], []) if a["id"] not in reserved] if item["km"] > 0 else []
            compatible = [a for a in candidates if is_run(item) == is_run(a) and (item["km"] <= 0 or a["distance_km"] > 0)]
            candidates = compatible or candidates
            target = item["km"]
            chosen = min(candidates, key=lambda a: abs(a["distance_km"] - target) / max(target, 1)) if candidates and (target > 0 or len(candidates) == 1) else None
            ratio = abs(chosen["distance_km"] - target) / max(target, 1) if chosen and target > 0 else 0
            if chosen and (target == 0 or ratio <= 0.35):
                reserved.add(chosen["id"])
                confidence, status = "auto", "Coincidencia probable · revisar"
            elif chosen:
                confidence, status = "suggested", "Sugerencia · revisar"
            else:
                confidence, status = "none", "Sin actividad vinculada"
        results.append({**item, "activity": chosen, "confidence": confidence, "match_status": status,
                        "diary": diary_by_date.get(item["date"])} )
    unmatched = [a for a in activities if a["id"] not in reserved]
    return results, unmatched


def log_file_time(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="minutes")
    except OSError:
        return None


def last_completed_sync(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if "INFO Sync completed:" in line:
            stamp = line.split(" INFO ", 1)[0]
            try:
                return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f").astimezone().isoformat(timespec="minutes")
            except ValueError:
                continue
    return None


def app_payload() -> dict:
    workbook = read_json(APP_DATA / "workbook.json", {"plan": [], "diary": []})
    plan, diary = workbook.get("plan", []), workbook.get("diary", [])
    activities = load_activities()
    matches = load_matches()
    rows, unmatched = make_matches(plan, activities, diary, matches.get("overrides", {}))
    sync_log = ROOT / "logs" / "sync.log"
    local_log = ROOT / "logs" / "local_app.log"
    personal_sync = read_json(APP_DATA / "garmin_sync.json", {})
    last_sync = personal_sync.get("synced_at") or last_completed_sync(sync_log)
    return {"plan": plan, "diary": diary, "activities": activities, "matches": rows,
            "unmatched": unmatched, "daily": daily_values(), "workbook": {
                "source": workbook.get("source"), "imported_at": workbook.get("imported_at"),
                "count": len(plan), "diary_count": len(diary)},
            "sync": {"last_sync": last_sync, "activity_count": len(activities)},
            "version": "0.1.0"}


def is_loopback(handler) -> bool:
    try:
        return handler.client_address[0] in ("127.0.0.1", "::1")
    except Exception:
        return False


def _session_secret() -> bytes:
    value = os.environ.get("SERRA_SESSION_SECRET", "")
    return value.encode("utf-8") if len(value) >= 32 else b""


def _session_cookie(handler) -> str:
    raw = handler.headers.get("Cookie", "")
    for item in raw.split(";"):
        name, sep, value = item.strip().partition("=")
        if name == "serra_session" and sep:
            return value
    return ""


def _valid_session(handler) -> bool:
    if not PUBLIC_MODE:
        return is_loopback(handler)
    secret = _session_secret()
    if not secret:
        return False
    token = _session_cookie(handler)
    try:
        stamp, sig = token.split(".", 1)
        issued = int(stamp)
    except (ValueError, TypeError):
        return False
    if issued > int(time.time()) or int(time.time()) - issued > 7 * 86400:
        return False
    expected = hmac.new(secret, stamp.encode(), hashlib.sha256).digest()
    try:
        return hmac.compare_digest(expected, base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)))
    except (ValueError, TypeError):
        return False


def _session_token() -> str:
    stamp = str(int(time.time()))
    sig = hmac.new(_session_secret(), stamp.encode(), hashlib.sha256).digest()
    return stamp + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _login_html(error: str = "") -> bytes:
    message = f'<p role="alert" style="color:#a43232">{error}</p>' if error else ""
    return ("<!doctype html><html lang=es><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Acceso · Serra</title><body style='font:16px system-ui;background:#f4f6f3;display:grid;min-height:95vh;place-items:center'>"
            "<form method=post action=/login style='background:white;padding:28px;border-radius:16px;width:min(360px,86vw);box-shadow:0 6px 30px #0001'>"
            "<h1 style='font-size:22px'>Serra · Entrenamiento</h1><p>Accede a tu panel privado.</p>" + message +
            "<label>Contraseña<input name=password type=password required autocomplete=current-password style='display:block;width:100%;padding:12px;margin:8px 0 16px'></label>"
            "<button style='padding:11px 16px;background:#18744d;color:white;border:0;border-radius:8px'>Entrar</button></form></body></html>").encode("utf-8")


def _daily_garmin_sync():
    """Run one cloud sync at 07:00 Madrid time on each day the app is up."""
    def worker():
        madrid = ZoneInfo("Europe/Madrid")
        while True:
            now = datetime.now(madrid)
            next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            time.sleep(max(60, (next_run - now).total_seconds()))
            try:
                from app.services import GARMIN_KEY_FILE, sync_garmin
                if GARMIN_KEY_FILE.exists():
                    summary = sync_garmin()
                    logging.info("Scheduled Garmin Personal API sync completed: %s activities, %s daily warnings.",
                                 summary["activities"], len(summary.get("failures", [])))
            except Exception as exc:
                # Avoid logging exception text: requests can include remote URLs and identifiers.
                logging.warning("Scheduled Garmin Personal API sync failed (%s).", type(exc).__name__)
    threading.Thread(target=worker, daemon=True, name="serra-garmin-daily-sync").start()


class Handler(BaseHTTPRequestHandler):
    server_version = "Serra/0.2"

    def log_message(self, fmt, *args):
        logging.info("%s %s", self.client_address[0], fmt % args)

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, target: str):
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _body(self, limit=20 * 1024 * 1024):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > limit:
            raise ValueError("El archivo es demasiado grande (máximo 20 MB).")
        return self.rfile.read(length)

    def _local_post(self) -> bool:
        origin = self.headers.get("Origin")
        return is_loopback(self) and (not origin or origin in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"))

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/health":
            return self._json(200, {"ok": True})
        if PUBLIC_MODE and not _session_secret():
            return self._json(503, {"error": "El acceso remoto no está listo: configura una clave de sesión segura."})
        if PUBLIC_MODE and not _valid_session(self):
            if route == "/login":
                return self._html(200, _login_html())
            if route.startswith("/api/"):
                return self._json(401, {"error": "Inicia sesión para continuar."})
            return self._redirect("/login")
        if not PUBLIC_MODE and not is_loopback(self):
            return self._json(403, {"error": "Solo se permite acceso desde este equipo."})
        if route == "/api/data":
            return self._json(200, app_payload())
        if route == "/api/integrations":
            try:
                from app.services import chatgpt_status, integration_status
                return self._json(200, {**integration_status(), "chatgpt": chatgpt_status(), "local": not PUBLIC_MODE})
            except RuntimeError as exc:
                return self._json(200, {"garmin": {"connected": False}, "chatgpt": {"connected": False}, "configuration_error": str(exc)})
        static_files = {"/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
                        "/icon.svg": ("icon.svg", "image/svg+xml"), "/sw.js": ("sw.js", "text/javascript; charset=utf-8")}
        if route in static_files:
            filename, content_type = static_files[route]
            body = (WEB / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-cache" if route == "/sw.js" else "public, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if route == "/logout":
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "serra_session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/" or route == "/index.html":
            path = WEB / "index.html"
            if not path.exists():
                return self._json(500, {"error": "Falta la interfaz app/index.html"})
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return self._json(404, {"error": "No encontrado"})

    def do_POST(self):
        route = urlparse(self.path).path
        if PUBLIC_MODE:
            if not _session_secret():
                return self._json(503, {"error": "El acceso remoto no está configurado."})
            if route == "/login":
                body = self._body(8192)
                form = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(body.decode("utf-8", "replace"))
                supplied = (form.get("password") or [""])[0]
                expected = os.environ.get("SERRA_APP_PASSWORD", "")
                forwarded = self.headers.get("X-Forwarded-For", "")
                peer = forwarded.split(",")[-1].strip() if forwarded else self.client_address[0]
                now = time.time()
                LOGIN_FAILURES[peer] = [x for x in LOGIN_FAILURES.get(peer, []) if now - x < 900]
                if len(LOGIN_FAILURES[peer]) >= 5:
                    return self._html(429, _login_html("Demasiados intentos. Espera 15 minutos."))
                if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
                    LOGIN_FAILURES[peer].append(now)
                    return self._html(401, _login_html("La contraseña no es correcta."))
                LOGIN_FAILURES.pop(peer, None)
                self.send_response(303)
                self.send_header("Location", "/")
                secure = "; Secure" if os.environ.get("SERRA_COOKIE_SECURE", "1") == "1" else ""
                self.send_header("Set-Cookie", f"serra_session={_session_token()}; Path=/; Max-Age=604800; HttpOnly; SameSite=Strict{secure}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not _valid_session(self):
                return self._json(401, {"error": "Inicia sesión para continuar."})
            # Browsers send Origin for scripted cross-site POSTs. Require exact same origin.
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if origin and urlparse(origin).netloc != host:
                return self._json(403, {"error": "Origen no permitido."})
        elif not self._local_post():
            return self._json(403, {"error": "Solo se aceptan acciones desde esta app local."})
        try:
            body = self._body()
            if route == "/api/import":
                # The browser sends only the selected workbook bytes; credentials are never handled here.
                content_type = self.headers.get("Content-Type", "").lower()
                filename = unquote(self.headers.get("X-Filename", "")).replace("\\", "/").rsplit("/", 1)[-1]
                if "spreadsheetml.sheet" not in content_type or not filename.lower().endswith(".xlsx"):
                    return self._json(400, {"error": "Selecciona un archivo Excel .xlsx."})
                temp = APP_DATA / "incoming.xlsx"
                temp.write_bytes(body)
                try:
                    try:
                        imported = import_workbook(temp)
                    except ValueError as exc:
                        if "No encuentro las hojas" not in str(exc):
                            raise
                        from app.services import save_document
                        sheets = parse_xlsx(temp)
                        lines = []
                        for sheet_name, rows in sheets.items():
                            lines.append(f"## {sheet_name}")
                            lines.extend(" | ".join(str(cell) for cell in row if cell not in (None, "")) for row in rows)
                        doc = save_document(filename, "\n".join(lines)[:300_000])
                        return self._json(200, {"ok": True, "mode": "document", **doc})
                    imported["source"] = filename
                    imported["source_path"] = filename
                    atomic_json(APP_DATA / "workbook.json", imported)
                finally:
                    temp.unlink(missing_ok=True)
                return self._json(200, {"ok": True, "source": imported["source"],
                                        "plan_count": len(imported["plan"]), "diary_count": len(imported["diary"])})
            if route == "/api/documents/import":
                from app.services import parse_document, save_document
                filename = unquote(self.headers.get("X-Filename", "documento")).replace("\\", "/").rsplit("/", 1)[-1]
                text = parse_document(filename, body)
                result = save_document(filename, text)
                return self._json(200, {"ok": True, **result})
            if route == "/api/garmin/connect":
                from app.services import save_garmin_key
                request = json.loads(body or b"{}")
                save_garmin_key(str(request.get("api_key", "")))
                return self._json(200, {"ok": True, "connected": True})
            if route == "/api/chatgpt/import":
                from app.services import set_chatgpt_credentials, unseal_chatgpt_bundle
                passphrase = self.headers.get("X-Transfer-Passphrase", "")
                credentials = unseal_chatgpt_bundle(body, passphrase)
                set_chatgpt_credentials(credentials)
                return self._json(200, {"ok": True, "connected": True, "email": credentials.get("email")})
            if route == "/api/garmin/sync":
                from app.services import sync_garmin
                summary = sync_garmin()
                logging.info("Garmin Personal API sync completed: %s activities, %s daily datasets, %s warnings.",
                             summary["activities"], len(summary["daily"]), len(summary.get("failures", [])))
                return self._json(200, {"ok": True, **summary})
            if route == "/api/chat":
                from app.services import ask_chatgpt
                request = json.loads(body or b"{}")
                payload = app_payload()
                today = date.today().isoformat()
                cutoff = (date.today() - timedelta(days=90)).isoformat()
                docs_dir = APP_DATA / "documents"
                docs = []
                remaining_chars = 60_000
                for file in sorted(docs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if docs_dir.exists() else []:
                    if remaining_chars <= 0 or len(docs) >= 8:
                        break
                    doc = read_json(file, {})
                    text = str(doc.get("text", ""))[:min(20_000, remaining_chars)]
                    remaining_chars -= len(text)
                    docs.append({"name": doc.get("filename"), "text": text})
                context = {"fecha_actual": today,
                           "plan_proximas_90_dias": [x for x in payload["plan"] if cutoff <= x["date"] <= (date.today()+timedelta(days=90)).isoformat()],
                           "actividades_ultimos_90_dias": [x for x in payload["activities"] if x["date"] >= cutoff],
                           "recuperacion_ultimos_90_dias": [x for x in payload["daily"] if x["date"] >= cutoff],
                           "notas_de_entrenamiento": [x for x in payload["diary"] if x["date"] >= cutoff],
                           "documentos_importados": docs}
                answer = ask_chatgpt(str(request.get("message", "")), context)
                return self._json(200, {"ok": True, "answer": answer})
            if route == "/api/match":
                request = json.loads(body or b"{}")
                plan_id, activity_id = str(request.get("plan_id", "")), str(request.get("activity_id", ""))
                payload = app_payload()
                valid_plan = {str(x["id"]) for x in payload["plan"]}
                valid_activity = {x["id"] for x in payload["activities"]}
                if plan_id not in valid_plan or (activity_id not in valid_activity and activity_id not in ("", "skip")):
                    return self._json(400, {"error": "No encuentro esa sesión o actividad."})
                state = load_matches()
                if activity_id and activity_id != "skip" and any(
                    key != plan_id and value == activity_id for key, value in state.get("overrides", {}).items()
                ):
                    return self._json(409, {"error": "Esa actividad ya está vinculada manualmente a otra sesión. Desvincúlala primero."})
                state.setdefault("overrides", {})[plan_id] = activity_id or "skip"
                state["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                atomic_json(APP_DATA / "matches.json", state)
                return self._json(200, {"ok": True})
            if route == "/api/shutdown":
                if PUBLIC_MODE:
                    return self._json(404, {"error": "No encontrado"})
                self._json(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            return self._json(404, {"error": "No encontrado"})
        except (ValueError, KeyError, zipfile.BadZipFile, ET.ParseError, RuntimeError) as exc:
            logging.warning("Request failed: %s", type(exc).__name__)
            return self._json(400, {"error": str(exc)[:300]})
        except Exception as exc:
            logging.error("App request failed (%s).", type(exc).__name__)
            return self._json(500, {"error": "No se pudo completar la acción. Consulta logs/local_app.log."})


def main():
    workbook_path = DEFAULT_WORKBOOK
    current = read_json(APP_DATA / "workbook.json", {})
    if workbook_path.exists():
        try:
            last_import = current.get("imported_at", "")
            source_name = current.get("source")
            changed = not current.get("plan") or (current.get("source_path") == str(workbook_path)
                      and (not last_import or workbook_path.stat().st_mtime > datetime.fromisoformat(last_import).timestamp()))
            if changed:
                result = import_workbook(workbook_path)
                logging.info("Imported workbook %s (%s plan rows, %s log entries).", result["source"], len(result["plan"]), len(result["diary"]))
        except Exception as exc:
            logging.warning("Could not load default workbook (%s). Select it in the app to retry.", type(exc).__name__)
    if PUBLIC_MODE and not _session_secret():
        raise RuntimeError("El modo de alojamiento necesita SERRA_SESSION_SECRET (32 caracteres como mínimo).")
    if PUBLIC_MODE and len(os.environ.get("SERRA_APP_PASSWORD", "")) < 20:
        raise RuntimeError("La contraseña remota debe tener al menos 20 caracteres.")
    if PUBLIC_MODE and HOST in ("127.0.0.1", "localhost", "::1"):
        logging.warning("SERRA_APP_PASSWORD está definido pero SERRA_HOST sigue siendo loopback; el alojamiento no será accesible externamente.")
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        logging.error("Could not bind the local dashboard at %s:%s (%s).", HOST, PORT, type(exc).__name__)
        raise
    server.daemon_threads = True
    logging.info("Training dashboard listening at %s:%s (public mode=%s).", HOST, PORT, PUBLIC_MODE)
    _daily_garmin_sync()
    if os.environ.get("GARMIN_APP_OPEN", "0") == "1":
        threading.Thread(target=lambda: (time.sleep(1.1), webbrowser.open(f"http://{HOST}:{PORT}")), daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logging.info("Local dashboard stopped.")


if __name__ == "__main__":
    main()


