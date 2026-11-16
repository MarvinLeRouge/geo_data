from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pytest

import download_geoboundaries as dgb


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache_file = tmp_path / "cache" / ".metadata_index.json"
    monkeypatch.setattr(dgb, "CACHE_FILE", cache_file)
    monkeypatch.setattr(dgb, "BASE_DIR", tmp_path / "boundaries")
    monkeypatch.setattr(dgb, "polite_pause", lambda: None)
    return cache_file


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_entry(path: Path) -> dgb.BoundaryEntry:
    return dgb.BoundaryEntry(
        boundary_id="FRA-ADM1",
        country_name="France",
        iso="FRA",
        boundary_type="ADM1",
        filename=path.name,
        relative_path=f"FRA/{path.name}",
        url=f"https://example.test/{path.name}",
        target_path=path,
    )


def write_zip(path: Path) -> int:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("data.geojson", "{}")
    return path.stat().st_size


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [(512, "512 o"), (2048, "2.0 Ko"), (5 * 1024**2, "5.0 Mo"), (3 * 1024**3, "3.0 Go"), (2 * 1024**4, "2.0 To")],
)
def test_format_bytes(num_bytes: float, expected: str):
    assert dgb.format_bytes(num_bytes) == expected


def test_discover_api_url_extracts_ajax_url():
    html = "<script>new Tabulator('#t', { ajaxURL: 'https://api.test/gbOpen/ALL/ALL/' });</script>"
    client = make_client(lambda request: httpx.Response(200, text=html))

    assert dgb.discover_api_url(client, "https://page.test/") == "https://api.test/gbOpen/ALL/ALL/"


def test_discover_api_url_falls_back_when_absent():
    client = make_client(lambda request: httpx.Response(200, text="<html></html>"))

    assert dgb.discover_api_url(client, "https://page.test/") == dgb.FALLBACK_API_URL


def test_discover_api_url_falls_back_on_http_error():
    client = make_client(lambda request: httpx.Response(503))

    assert dgb.discover_api_url(client, "https://page.test/") == dgb.FALLBACK_API_URL


def test_fetch_entries_filters_dedupes_and_normalizes(tmp_path: Path):
    url = "https://data.test/FRA/geoBoundaries-FRA-ADM1-all.zip"
    payload = [
        {
            "staticDownloadLink": url,
            "boundaryISO": " fra ",
            "boundaryName": "France",
            "boundaryType": "ADM1",
            "boundaryID": "FRA-ADM1-1",
        },
        {"staticDownloadLink": url, "boundaryISO": "FRA"},
        {"staticDownloadLink": "https://data.test/x.geojson", "boundaryISO": "FRA"},
        {"boundaryISO": "FRA"},
        {"staticDownloadLink": "https://data.test/ITA/it.zip", "shapeGroup": "ita"},
        {"staticDownloadLink": "https://data.test/unk.zip"},
    ]
    client = make_client(lambda request: httpx.Response(200, json=payload))

    entries = dgb.fetch_entries(client, "https://api.test/")

    assert [(e.iso, e.relative_path) for e in entries] == [
        ("FRA", "FRA/geoBoundaries-FRA-ADM1-all.zip"),
        ("ITA", "ITA/it.zip"),
        ("UNKNOWN", "UNKNOWN/unk.zip"),
    ]
    fra = entries[0]
    assert (fra.country_name, fra.boundary_type, fra.boundary_id) == ("France", "ADM1", "FRA-ADM1-1")
    assert fra.target_path == tmp_path / "boundaries" / "FRA" / "geoBoundaries-FRA-ADM1-all.zip"
    ita = entries[1]
    assert (ita.country_name, ita.boundary_type, ita.boundary_id) == ("Unknown", "ADM", "")


def test_fetch_entries_raises_on_http_error():
    client = make_client(lambda request: httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        dgb.fetch_entries(client, "https://api.test/")


def test_metadata_cache_round_trip(isolated_paths: Path):
    assert dgb.load_metadata_cache() == {}

    dgb.save_metadata_cache({"FRA/a.zip": {"content_length": 42}})

    assert dgb.load_metadata_cache() == {"FRA/a.zip": {"content_length": 42}}


def test_load_metadata_cache_returns_empty_on_corrupt_file(isolated_paths: Path):
    isolated_paths.parent.mkdir(parents=True)
    isolated_paths.write_text("[broken", encoding="utf-8")

    assert dgb.load_metadata_cache() == {}


def test_verify_entry_missing_file(tmp_path: Path):
    entry = make_entry(tmp_path / "a.zip")

    assert dgb.verify_entry(make_client(lambda r: httpx.Response(200)), entry, {}) == (
        False,
        ["Fichier absent du disque"],
    )


def test_verify_entry_empty_file(tmp_path: Path):
    path = tmp_path / "a.zip"
    path.touch()

    assert dgb.verify_entry(make_client(lambda r: httpx.Response(200)), make_entry(path), {}) == (
        False,
        ["Fichier vide (0 octet)"],
    )


def test_verify_entry_valid_zip_uses_cached_content_length(tmp_path: Path):
    path = tmp_path / "a.zip"
    size = write_zip(path)

    def fail(request):
        raise AssertionError("HEAD must not be called when the cache has the length")

    cache = {"FRA/a.zip": {"content_length": size}}
    assert dgb.verify_entry(make_client(fail), make_entry(path), cache) == (True, [])


def test_verify_entry_head_fills_cache_and_detects_mismatch(tmp_path: Path):
    path = tmp_path / "a.zip"
    size = write_zip(path)
    cache: dict[str, dict] = {}
    client = make_client(lambda request: httpx.Response(200, headers={"content-length": str(size + 10)}))

    ok, errors = dgb.verify_entry(client, make_entry(path), cache)

    assert not ok
    assert len(errors) == 1
    assert "Content-Length" in errors[0]
    assert cache == {"FRA/a.zip": {"content_length": size + 10}}
    assert dgb.load_metadata_cache() == cache


def test_verify_entry_reports_head_failure_and_bad_zip(tmp_path: Path):
    path = tmp_path / "a.zip"
    path.write_bytes(b"not a zip")
    client = make_client(lambda request: httpx.Response(404))

    ok, errors = dgb.verify_entry(client, make_entry(path), {})

    assert not ok
    assert len(errors) == 2
    assert errors[0].startswith("Impossible d'obtenir Content-Length via HEAD")
    assert "archive ZIP valide" in errors[1]
