"""Export Garmin Connect activities and daily summaries to local JSON/TCX files."""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ACTIVITIES = DATA / "activities"
DAILY = DATA / "daily"
TOKEN_STORE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "GarminConnectExport" / "tokens"
LOG_DIR = ROOT / "logs"
LOGGER = logging.getLogger("garmin_export")


def setup_logging() -> None:
    logging.getLogger("garminconnect").setLevel(logging.CRITICAL)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_DIR / "sync.log", encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        temporary = Path(tmp.name)
    temporary.replace(path)


def login(interactive: bool) -> Garmin:
    TOKEN_STORE.mkdir(parents=True, exist_ok=True)
    client = Garmin()
    try:
        client.login(str(TOKEN_STORE))
        LOGGER.info("Authenticated with saved Garmin session.")
        return client
    except GarminConnectTooManyRequestsError:
        raise RuntimeError("Garmin rate limit reached; try again later.") from None
    except (GarminConnectAuthenticationError, GarminConnectConnectionError, FileNotFoundError, ValueError):
        if not interactive:
            raise RuntimeError("Saved Garmin session is unavailable or expired. Run sync_garmin.ps1 to sign in again.") from None

    print("First sign-in to Garmin Connect (or refresh the saved session).")
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (input hidden): ")
    client = Garmin(email=email, password=password, prompt_mfa=lambda: input("Garmin MFA code: ").strip())
    password = ""
    try:
        client.login(str(TOKEN_STORE))
    except GarminConnectTooManyRequestsError:
        raise RuntimeError("Garmin rate limit reached; try again later.") from None
    except (GarminConnectAuthenticationError, GarminConnectConnectionError):
        raise RuntimeError("Garmin sign-in failed. Check the credentials/MFA code or try again later.") from None
    LOGGER.info("Garmin sign-in succeeded; refreshable session tokens were saved locally.")
    return client


def export_activities(client: Garmin, since: date) -> int:
    count = 0
    start = 0
    page_size = 100
    while True:
        page = client.get_activities(start=start, limit=page_size) or []
        if not isinstance(page, list) or not page:
            break
        older_than_cutoff = False
        for activity in page:
            activity_day = str(activity.get("startTimeLocal") or activity.get("startTimeGMT") or "")[:10]
            try:
                if activity_day and date.fromisoformat(activity_day) < since:
                    older_than_cutoff = True
                    break
            except ValueError:
                pass
            activity_id = activity.get("activityId")
            if not activity_id:
                continue
            activity_id = str(activity_id)
            summary_path = ACTIVITIES / f"{activity_id}.json"
            if not summary_path.exists():
                atomic_write(summary_path, (json.dumps(activity, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            tcx_path = ACTIVITIES / f"{activity_id}.tcx"
            if not tcx_path.exists():
                try:
                    payload = client.download_activity(activity_id)
                    if payload:
                        atomic_write(tcx_path, payload)
                except GarminConnectTooManyRequestsError:
                    raise
                except Exception:
                    LOGGER.warning("Could not download activity file %s; will retry next run.", activity_id)
            count += 1
            if count % 20 == 0:
                LOGGER.info("Activity progress: %s activities processed.", count)
        if older_than_cutoff:
            break
        start += len(page)
        if len(page) < page_size:
            break
    return count


def export_daily(client: Garmin, days: int) -> int:
    today = date.today()
    DAILY.mkdir(parents=True, exist_ok=True)
    complete_marker = DAILY / f".initial_history_{days}_complete"
    # Retrieve the requested history once, then refresh the overlap where Garmin may backfill data.
    start_date = today - timedelta(days=6 if complete_marker.exists() else days - 1)
    start, end = start_date.isoformat(), today.isoformat()
    datasets = (
        ("summaries", "get_daily_summaries"),
        ("heart_rate", "get_daily_heart_rate_stats"),
        ("sleep", "get_sleep_daily"),
        ("steps", "get_daily_steps"),
        ("stress", "get_daily_stress_stats"),
    )
    saved = 0
    for name, method_name in datasets:
        try:
            records = getattr(client, method_name)(start, end)
        except GarminConnectTooManyRequestsError:
            raise
        except Exception as exc:
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            reason = type(exc).__name__
            if isinstance(status, int):
                reason += f" HTTP {status}"
            fallback_method = {"heart_rate": "get_heart_rates", "stress": "get_stress_data"}.get(name)
            if status == 400 and fallback_method:
                LOGGER.info("The %s range endpoint returned HTTP 400; trying the library's daily endpoint.", name)
                records = []
                consecutive_errors = 0
                fallback_reason = ""
                for offset in range((today - start_date).days + 1):
                    day = (start_date + timedelta(days=offset)).isoformat()
                    try:
                        daily_record = getattr(client, fallback_method)(day)
                    except GarminConnectTooManyRequestsError:
                        raise
                    except Exception as daily_exc:
                        daily_response = getattr(daily_exc, "response", None)
                        daily_status = getattr(daily_response, "status_code", None)
                        fallback_reason = type(daily_exc).__name__
                        if isinstance(daily_status, int):
                            fallback_reason += f" HTTP {daily_status}"
                        consecutive_errors += 1
                        if consecutive_errors >= 3:
                            break
                        continue
                    consecutive_errors = 0
                    if daily_record is not None:
                        records.append({"calendarDate": day, "data": daily_record})
                if consecutive_errors >= 3:
                    LOGGER.warning("Could not retrieve %s using the daily endpoint (%s); will retry next run.", name, fallback_reason)
                    continue
                LOGGER.info("Retrieved %s via per-day fallback (%s of %s dates returned data).", name, len(records), (today - start_date).days + 1)
            else:
                LOGGER.warning("Could not retrieve %s history for %s through %s (%s); will retry next run.", name, start, end, reason)
                continue
        path = DAILY / f"{name}_{start}_{end}.json"
        payload = {"dataset": name, "start_date": start, "end_date": end, "data": records}
        atomic_write(path, (json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8"))
        saved += 1
        LOGGER.info("Saved %s daily-data snapshot for %s through %s.", name, start, end)
    if saved == len(datasets):
        complete_marker.touch()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Garmin Connect data to the local data folder.")
    parser.add_argument("--interactive", action="store_true", help="prompt locally for Garmin sign-in and MFA")
    parser.add_argument("--since", default="2026-10-01", help="export activities on or after this date (default: 2026-10-01)")
    parser.add_argument("--days", type=int, default=36, help="daily health history to export (default: 36)")
    args = parser.parse_args()
    if args.days < 1 or args.days > 3650:
        parser.error("--days must be between 1 and 3650")
    try:
        since = date.fromisoformat(args.since)
    except ValueError:
        parser.error("--since must use YYYY-MM-DD")
    setup_logging()
    try:
        client = login(args.interactive)
        activities = export_activities(client, since)
        days = export_daily(client, args.days)
        LOGGER.info("Sync completed: %s activities checked; %s daily data snapshots written/refreshed.", activities, days)
        return 0
    except GarminConnectTooManyRequestsError:
        LOGGER.error("Garmin rate limit reached; sync stopped safely. It will retry on the next scheduled run.")
    except (GarminConnectConnectionError, RuntimeError):
        LOGGER.error("Sync could not complete. Run the interactive sign-in from the project folder for details.")
    except KeyboardInterrupt:
        LOGGER.info("Sync cancelled by user.")
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

