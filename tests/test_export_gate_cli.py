"""D2: export-gate CLI merges media itself, gates md+html, writes the report."""
import pathlib
import subprocess
import sys

import yaml

from scripts.validate_artifact import validate_file
from tests.mech_fixtures import build_full_trip, write_artifact

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "scripts" / "export_gate.py"


def _run(trip_dir):
    return subprocess.run([sys.executable, str(CLI), str(trip_dir)],
                          capture_output=True, text=True)


def _report(t):
    return yaml.safe_load((t / "export-gate-report.yaml").read_text(encoding="utf-8"))


def test_pass_writes_valid_report(tmp_path):
    t, _ = build_full_trip(tmp_path)
    r = _run(t)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "family-public contract: not run" in r.stdout
    rep = _report(t)
    assert rep["status"] == "pass" and rep["retryable"] is True
    assert validate_file(t / "export-gate-report.yaml")[0] == 0


def test_family_public_contract_is_merged_and_can_fail(tmp_path):
    t, _ = build_full_trip(tmp_path)
    write_artifact(t / "family-public-contract.yaml", {
        "min_days": 1,
        "expected_location_keys": ["poi-1"],
        "required_meal_ids": ["lunch"],
    })
    r = _run(t)
    assert r.returncode == 1
    assert "family-public contract: fail" in r.stdout
    rep = _report(t)
    assert rep["status"] == "fail"
    assert rep["retryable"] is False
    assert any(c["name"] == "family_location_photos" and not c["passed"]
               for c in rep["checks"])
    assert any(f.startswith("family: missing family location photo keys")
               for f in rep["failures"])


def test_family_public_contract_can_pass(tmp_path):
    t, _ = build_full_trip(tmp_path)
    write_artifact(t / "family-public-contract.yaml", {
        "min_days": 1,
        "expected_location_keys": ["poi-1"],
        "required_meal_ids": ["lunch"],
    })
    html = t / "exports" / f"{t.name}-itinerary.html"
    restaurant = (
        '<article class="restaurant-card" data-restaurant-id="r{n}">'
        '菜系 距離 來源 地圖 特色 為什麼選 招牌 人均</article>'
    )
    html.write_text(
        '<h2>D1 8/1（週六）</h2>'
        '<div class="day-card"></div><div class="day-card"></div>'
        '<figure data-location-key="poi-1">'
        '<img src="https://img.example/poi.jpg" alt="poi">'
        '<figcaption class="photo-credit">source</figcaption></figure>'
        '<section class="meal-options" data-meal-id="lunch">'
        + "".join(restaurant.format(n=i) for i in range(3))
        + '</section>',
        encoding="utf-8",
    )
    r = _run(t)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "family-public contract: pass" in r.stdout
    rep = _report(t)
    assert rep["retryable"] is True
    assert any(c["name"] == "family_location_photos" and c["passed"]
               for c in rep["checks"])


def test_naked_dollar_fails_retryable(tmp_path):
    t, _ = build_full_trip(tmp_path)
    md = t / "exports" / f"{t.name}-itinerary.md"
    md.write_text(md.read_text(encoding="utf-8") + "\n門票 $120 很划算\n",
                  encoding="utf-8")
    r = _run(t)
    assert r.returncode == 1
    rep = _report(t)
    assert rep["retryable"] is True          # render-fixable → re-render loop OK


def test_media_present_but_zero_img_fails(tmp_path):
    t, _ = build_full_trip(tmp_path)
    write_artifact(t / "verified-pois-media.yaml", {"media": {"poi-1": {
        "photo": "https://img.example/goryokaku.jpg",
        "photo_attribution": {"author": "a", "license": "CC-BY-4.0",
                              "source_url": "https://img.example/page"},
        "photo_source": "wiki"}}})
    # html deliverable has 0 <img> — the P8 dropped-apply_media case
    r = _run(t)
    assert r.returncode == 1
    assert any("0 photos" in f for f in _report(t)["failures"])


def test_photo_without_attribution_fails_nonretryable(tmp_path):
    t, _ = build_full_trip(tmp_path)
    write_artifact(t / "verified-pois-media.yaml", {"media": {"poi-1": {
        "photo": "https://img.example/goryokaku.jpg", "photo_source": "wiki"}}})
    html = t / "exports" / f"{t.name}-itinerary.html"
    html.write_text(html.read_text(encoding="utf-8")
                    + '<img src="https://img.example/goryokaku.jpg">',
                    encoding="utf-8")
    r = _run(t)
    assert r.returncode == 1
    rep = _report(t)
    assert rep["retryable"] is False         # DATA defect → stop-and-ask


def test_missing_deliverable_exits_two(tmp_path):
    t, _ = build_full_trip(tmp_path)
    (t / "exports" / f"{t.name}-itinerary.md").unlink()
    assert _run(t).returncode == 2


def test_malformed_optional_artifact_exits_two_without_report(tmp_path):
    t, _ = build_full_trip(tmp_path)
    (t / "accommodations.yaml").write_text(
        "stops:\n  bad indent: [\n", encoding="utf-8")
    (t / "export-gate-report.yaml").unlink(missing_ok=True)
    r = _run(t)
    assert r.returncode == 2, r.stderr + r.stdout
    assert not (t / "export-gate-report.yaml").exists()
