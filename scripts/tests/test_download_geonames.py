from __future__ import annotations

import zipfile
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import download_geonames as dg

LISTING_HTML = """<html><body><pre>
<a href="?C=N;O=D">Name</a>
<a href="alternatenames/">alternatenames/</a>      2026-11-01 01:00    -
<a href="AD.zip">AD.zip</a>                     2026-11-01 01:00   96K
<a href="FR.zip">FR.zip</a>                     2026-11-01 01:00  8.6M
<a href="allCountries.zip">allCountries.zip</a> 2026-11-01 01:00  402M
<a href="readme.txt">readme.txt</a>             2026-11-01 01:00   77
</pre></body></html>"""


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache_file = tmp_path / "cache" / ".metadata_index.json"
    monkeypatch.setattr(dg, "CACHE_FILE", cache_file)
    monkeypatch.setattr(dg, "polite_pause", lambda: None)
    return cache_file


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_entry(path: Path, listing_size_str: str) -> dg.FileEntry:
    return dg.FileEntry(
        filename=path.name,
        relative_path=path.name,
        url=f"https://example.test/{path.name}",
        target_path=path,
        listing_size_str=listing_size_str,
        listing_size_bytes=dg.parse_size_to_bytes(listing_size_str),
        modified="2026-11-01 01:00",
    )


def write_zip(path: Path) -> int:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("data.txt", "hello")
    return path.stat().st_size


def write_crc_corrupt_zip(path: Path) -> int:
    """Writes a stored ZIP, then alters its payload so the header stays valid but the CRC fails."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("data.txt", "payload-ok")
    path.write_bytes(path.read_bytes().replace(b"payload-ok", b"payload-ko"))
    return path.stat().st_size


@pytest.mark.parametrize(
    ("size_str", "expected"),
    [("2G", 2 * 1024**3), ("402M", 402 * 1024**2), (" 96k ", 96 * 1024), ("77", 77.0), ("-", 0.0)],
)
def test_parse_size_to_bytes(size_str: str, expected: float):
    assert dg.parse_size_to_bytes(size_str) == expected


@pytest.mark.parametrize(
    ("num_bytes", "expected"),
    [(512, "512 o"), (2048, "2.0 Ko"), (5 * 1024**2, "5.0 Mo"), (3 * 1024**3, "3.0 Go"), (2 * 1024**4, "2.0 To")],
)
def test_format_bytes(num_bytes: float, expected: str):
    assert dg.format_bytes(num_bytes) == expected


@pytest.mark.parametrize(
    ("actual", "listing", "ok"),
    [
        (0, "0", True),
        (1, "0", False),
        (77, "77", True),
        (78, "77", False),
        (int(8.65 * 1024**2), "8.6M", True),
        (int(8.8 * 1024**2), "8.6M", False),
        (97 * 1024, "96K", True),
        (int(402 * 1.05 * 1024**2), "402M", True),
        (int(402 * 1.2 * 1024**2), "402M", False),
    ],
)
def test_check_approx_size_consistency(actual: int, listing: str, ok: bool):
    is_ok, message = dg.check_approx_size_consistency(actual, listing)
    assert is_ok is ok
    assert message


def test_fetch_listing_parses_filters_and_sorts(tmp_path: Path):
    client = make_client(lambda request: httpx.Response(200, text=LISTING_HTML))

    entries = dg.fetch_listing(client, "https://example.test/dump/", tmp_path, rel_prefix="dump/")

    # Long names first by size desc, then country files by size desc; folders and "-" sizes skipped.
    assert [e.filename for e in entries] == ["allCountries.zip", "readme.txt", "FR.zip", "AD.zip"]
    fr = entries[2]
    assert fr.relative_path == "dump/FR.zip"
    assert fr.url == "https://example.test/dump/FR.zip"
    assert fr.target_path == tmp_path / "FR.zip"
    assert fr.listing_size_bytes == pytest.approx(8.6 * 1024**2)
    assert fr.modified == "2026-11-01 01:00"


def test_fetch_listing_without_pre_block(tmp_path: Path):
    html = '<a href="AD.zip">AD.zip</a> 2026-11-01 01:00 96K'
    client = make_client(lambda request: httpx.Response(200, text=html))

    entries = dg.fetch_listing(client, "https://example.test/", tmp_path)

    assert [e.relative_path for e in entries] == ["AD.zip"]


def test_fetch_listing_raises_on_http_error(tmp_path: Path):
    client = make_client(lambda request: httpx.Response(500))

    with pytest.raises(httpx.HTTPStatusError):
        dg.fetch_listing(client, "https://example.test/", tmp_path)


def test_metadata_cache_round_trip(isolated_cache: Path):
    assert dg.load_metadata_cache() == {}

    dg.save_metadata_cache({"AD.zip": {"content_length": 42, "name": "Andorre"}})

    assert isolated_cache.exists()
    assert dg.load_metadata_cache() == {"AD.zip": {"content_length": 42, "name": "Andorre"}}


def test_load_metadata_cache_returns_empty_on_corrupt_file(isolated_cache: Path):
    isolated_cache.parent.mkdir(parents=True)
    isolated_cache.write_text("{not json", encoding="utf-8")

    assert dg.load_metadata_cache() == {}


def test_verify_entry_missing_file(tmp_path: Path):
    entry = make_entry(tmp_path / "AD.zip", "1K")

    assert dg.verify_entry(make_client(lambda r: httpx.Response(200)), entry, {}) == (
        False,
        ["Fichier absent du disque"],
    )


def test_verify_entry_valid_zip_uses_cached_content_length(tmp_path: Path):
    path = tmp_path / "AD.zip"
    size = write_zip(path)
    entry = make_entry(path, str(size))

    def fail(request):
        raise AssertionError("HEAD must not be called when the cache has the length")

    assert dg.verify_entry(make_client(fail), entry, {"AD.zip": {"content_length": size}}) == (True, [])


def test_verify_entry_head_fills_cache_and_detects_mismatch(tmp_path: Path, isolated_cache: Path):
    path = tmp_path / "AD.zip"
    size = write_zip(path)
    entry = make_entry(path, str(size))
    cache: dict[str, dict] = {}
    client = make_client(lambda request: httpx.Response(200, headers={"content-length": str(size + 1)}))

    ok, errors = dg.verify_entry(client, entry, cache)

    assert not ok
    assert len(errors) == 1
    assert "Content-Length" in errors[0]
    assert cache["AD.zip"] == {"content_length": size + 1, "listing_size_str": str(size)}
    assert dg.load_metadata_cache() == cache


def test_verify_entry_reports_head_failure_listing_mismatch_and_bad_zip(tmp_path: Path):
    path = tmp_path / "AD.zip"
    path.write_bytes(b"not a zip")
    entry = make_entry(path, "500")
    client = make_client(lambda request: httpx.Response(404))

    ok, errors = dg.verify_entry(client, entry, {})

    assert not ok
    assert len(errors) == 3
    assert errors[0].startswith("Impossible d'interroger Content-Length via HEAD")
    assert errors[1].startswith("Incohérence listing")
    assert "archive ZIP valide" in errors[2]


def test_verify_entry_skips_zip_check_for_non_zip(tmp_path: Path):
    path = tmp_path / "readme.txt"
    path.write_bytes(b"x" * 77)
    entry = make_entry(path, "77")

    assert dg.verify_entry(make_client(lambda r: httpx.Response(200)), entry, {"readme.txt": {"content_length": 77}}) == (
        True,
        [],
    )


def test_download_file_writes_target_and_updates_cache(tmp_path: Path):
    path = tmp_path / "sub" / "AD.zip"
    entry = make_entry(path, "1K")
    cache: dict[str, dict] = {}
    client = make_client(lambda request: httpx.Response(200, content=b"payload"))

    assert dg.download_file(client, entry, cache) == 7

    assert path.read_bytes() == b"payload"
    assert not path.with_name("AD.zip.part").exists()
    assert cache["AD.zip"]["content_length"] == 7
    assert cache["AD.zip"]["downloaded_bytes"] == 7
    assert cache["AD.zip"]["listing_size_str"] == "1K"
    assert dg.load_metadata_cache() == cache


def test_download_file_without_content_length(tmp_path: Path):
    path = tmp_path / "AD.zip"
    client = make_client(lambda request: httpx.Response(200, content=iter([b"ab", b"cd"])))
    cache: dict[str, dict] = {}

    assert dg.download_file(client, make_entry(path, "1K"), cache) is None

    assert path.read_bytes() == b"abcd"
    assert cache["AD.zip"]["content_length"] is None
    assert cache["AD.zip"]["downloaded_bytes"] == 4


def test_download_file_http_error_leaves_no_file_and_no_cache(tmp_path: Path, isolated_cache: Path):
    path = tmp_path / "AD.zip"
    cache: dict[str, dict] = {}
    client = make_client(lambda request: httpx.Response(404))

    with pytest.raises(httpx.HTTPStatusError):
        dg.download_file(client, make_entry(path, "1K"), cache)

    assert not path.exists()
    assert not path.with_name("AD.zip.part").exists()
    assert cache == {}
    assert not isolated_cache.exists()


def test_verify_entry_reports_crc_corrupt_zip_member(tmp_path: Path):
    path = tmp_path / "AD.zip"
    size = write_crc_corrupt_zip(path)
    client = make_client(lambda r: httpx.Response(200))
    ok, errors = dg.verify_entry(client, make_entry(path, str(size)), {"AD.zip": {"content_length": size}})
    assert (ok, errors) == (False, ["Archive ZIP corrompue (erreur CRC sur : data.txt)"])


def test_verify_entry_reports_unreadable_zip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = tmp_path / "AD.zip"
    size = write_zip(path)

    def unreadable(*args, **kwargs):
        raise zipfile.BadZipFile("truncated central directory")

    monkeypatch.setattr(dg.zipfile, "ZipFile", unreadable)
    client = make_client(lambda r: httpx.Response(200))
    ok, errors = dg.verify_entry(client, make_entry(path, str(size)), {"AD.zip": {"content_length": size}})
    assert (ok, errors) == (False, ["Échec de lecture du ZIP : truncated central directory"])


def test_download_file_prints_throttled_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(dg, "CHUNK_SIZE", 2)
    # time.time() calls: start, chunk 1 (+1.0 s, prints), chunk 2 (+0.2 s, throttled), cache timestamp.
    clock = iter([0.0, 1.0, 1.2, 5.0])
    monkeypatch.setattr(dg, "time", SimpleNamespace(time=lambda: next(clock)))
    client = make_client(lambda request: httpx.Response(200, content=b"abcd"))

    assert dg.download_file(client, make_entry(tmp_path / "AD.zip", "1K"), {}) == 4

    out = capsys.readouterr().out
    assert "\r    Téléchargement : 2 o (50%)..." in out
    assert "(100%)..." not in out
    assert out.endswith("\r    Téléchargement : 4 o (100%)       \n")
