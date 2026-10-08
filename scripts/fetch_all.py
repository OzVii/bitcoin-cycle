"""Hakee kaikki lähteet. Yksittäisen lähteen virhe ei kaada ajoa: vanha data jää käyttöön
ja virhe kirjataan data/fetch_status.json-tiedostoon, josta sivu näyttää varoituksen."""
import traceback
from datetime import datetime, timezone

import fetch_coinmetrics
import fetch_fng
import fetch_fred
import fetch_ohlc
from common import load_config, load_status, save_status

SOURCES = {
    "coinmetrics": fetch_coinmetrics.update,
    "ohlc_daily": fetch_ohlc.update,
    "fng": fetch_fng.update,
    "m2": fetch_fred.update_m2,
    "dollar": fetch_fred.update_dollar,
}


def main():
    cfg = load_config()
    status = load_status()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, fn in SOURCES.items():
        entry = status.get(name, {})
        entry["checked_at"] = now
        try:
            info = fn(cfg)
            entry.update(ok=True, last_success=now, error=None, **info)
            print(f"[OK]   {name}: {info}")
        except Exception as e:  # noqa: BLE001
            entry.update(ok=False, error=f"{type(e).__name__}: {e}")
            print(f"[FAIL] {name}: {e}")
            traceback.print_exc()
        status[name] = entry
    save_status(status)


if __name__ == "__main__":
    main()
