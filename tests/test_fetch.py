import json

import pandas as pd
import pytest

import common
import fetch_all
import fetch_fred

SECRET = "abc123secretkey"


@pytest.fixture
def fred_env(tmp_path, monkeypatch, cfg):
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FRED_API_KEY", SECRET)
    return cfg


def test_fred_api_used_when_key_set(fred_env, monkeypatch):
    monkeypatch.setattr(fetch_fred, "fetch_api", lambda sid, start, key, cfg: pd.DataFrame(
        {"date": pd.to_datetime(["2026-07-01", "2026-08-01"]), "value": [100.0, 101.0]}))
    monkeypatch.setattr(fetch_fred, "fetch_csv", lambda *a: pytest.fail("CSV ei saa olla käytössä"))
    info = fetch_fred.update_series("M2SL", "m2", fred_env)
    assert info["via"] == "api" and info["rows"] == 2


def test_fred_falls_back_to_csv_and_hides_key(fred_env, monkeypatch):
    def api_fail(sid, start, key, cfg):
        raise ConnectionError(f"400 for url: https://api.stlouisfed.org/?api_key={key}")

    monkeypatch.setattr(fetch_fred, "fetch_api", api_fail)
    monkeypatch.setattr(fetch_fred, "fetch_csv", lambda sid, start, cfg: pd.DataFrame(
        {"date": pd.to_datetime(["2026-08-01"]), "value": [5.0]}))
    assert fetch_fred.update_series("M2SL", "m2", fred_env)["via"] == "csv"

    def csv_fail(sid, start, cfg):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(fetch_fred, "fetch_csv", csv_fail)
    with pytest.raises(RuntimeError) as exc:
        fetch_fred.update_series("M2SL", "m2", fred_env)
    msg = str(exc.value)
    assert SECRET not in msg and "***" in msg and "read timed out" in msg


def test_failing_source_does_not_crash(tmp_path, monkeypatch):
    status_path = tmp_path / "fetch_status.json"
    status_path.write_text(json.dumps({"fng": {"ok": True, "last_success": "2026-01-01T06:00:00Z",
                                               "last_date": "2026-01-01"}}), encoding="utf-8")
    monkeypatch.setattr(common, "STATUS_PATH", status_path)
    monkeypatch.setattr(common, "DATA_DIR", tmp_path)

    def boom(cfg):
        raise ConnectionError("palvelin alhaalla")

    monkeypatch.setattr(fetch_all, "SOURCES", {"fng": boom, "m2": lambda cfg: {"rows": 1, "added": 0,
                                                                                  "last_date": "2026-08-01"}})
    fetch_all.main()  # ei saa nostaa poikkeusta
    st = json.loads(status_path.read_text(encoding="utf-8"))
    assert st["fng"]["ok"] is False and "palvelin alhaalla" in st["fng"]["error"]
    assert st["fng"]["last_success"] == "2026-01-01T06:00:00Z"  # viimeisin onnistunut säilyy
    assert st["fng"]["last_date"] == "2026-01-01"
    assert st["m2"]["ok"] is True
