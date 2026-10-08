import json

import common
import fetch_all


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
