#!/usr/bin/env python3
"""Script de téléchargement et de vérification des exports GeoNames.

Fonctionnalités :
1. Téléchargement depuis https://download.geonames.org/export/dump/ vers ~/projets/geo_data/geonames/
2. Téléchargement depuis https://download.geonames.org/export/dump/alternatenames/ vers ~/projets/geo_data/geonames/alternatenames/
3. Ordre de téléchargement :
   - Fichiers dont le nom (sans extension) a plus de 2 caractères, triés par taille décroissante.
   - Fichiers pays (nom <= 2 caractères), triés par taille décroissante.
4. Reprise sur existant : saute les fichiers déjà présents lors de la passe initiale.
5. Mode poli : requêtes séquentielles avec pause aléatoire de 0.5s à 1.0s entre requêtes.
6. Téléchargement sécurisé via fichier temporaire (.part).
7. Phase de vérification d'intégrité :
   - Cohérence taille réelle sur disque vs Content-Length HTTP.
   - Cohérence Content-Length vs taille approximative affichée sur le listing GeoNames.
   - Intégrité de l'archive pour tous les fichiers .zip (testzip).
8. Interaction utilisateur : présentation du rapport d'anomalies et proposition de retry unitaire.
"""

from __future__ import annotations

import json
import random
import re
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import httpx

# Configuration
DUMP_BASE_URL = "https://download.geonames.org/export/dump/"
ALT_BASE_URL = "https://download.geonames.org/export/dump/alternatenames/"

BASE_DIR = Path(__file__).resolve().parent / "data" / "geonames"
ALT_DIR = BASE_DIR / "alternatenames"
CACHE_FILE = BASE_DIR / ".metadata_index.json"

CHUNK_SIZE = 64 * 1024  # 64 KB
USER_AGENT = "GeoDataDownloader/1.0 (+https://github.com/MarvinLeRouge)"


@dataclass
class FileEntry:
    filename: str
    relative_path: str  # e.g. "allCountries.zip" or "alternatenames/AD.zip"
    url: str
    target_path: Path
    listing_size_str: str
    listing_size_bytes: float
    modified: str


def parse_size_to_bytes(size_str: str) -> float:
    """Convertit la chaîne de taille Apache (ex: '402M', '96K', '77') en octets."""
    s = size_str.strip().upper()
    if s.endswith("G"):
        return float(s[:-1]) * (1024**3)
    if s.endswith("M"):
        return float(s[:-1]) * (1024**2)
    if s.endswith("K"):
        return float(s[:-1]) * 1024
    try:
        return float(s)
    except ValueError:
        return 0.0


def format_bytes(num_bytes: float) -> str:
    """Formate un nombre d'octets de façon lisible."""
    for unit in ["o", "Ko", "Mo", "Go"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}" if unit != "o" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} To"


def fetch_listing(client: httpx.Client, base_url: str, target_dir: Path, rel_prefix: str = "") -> list[FileEntry]:
    """Récupère et parse le listing HTML Apache autoindex de GeoNames."""
    print(f"Connexion au listing : {base_url} ...")
    resp = client.get(base_url)
    resp.raise_for_status()

    # Découpage du bloc <pre> contenant les liens de listing
    html = resp.text
    if "<pre>" in html:
        pre_content = html.split("<pre>", 1)[1].split("</pre>", 1)[0]
    else:
        pre_content = html

    pattern = re.compile(
        r"""<a\s+href="([^"?#/][^"]*)">.*?</a>\s+([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2})\s+([0-9.]+[KMG]?|-)\s*""",
        re.IGNORECASE,
    )

    entries: list[FileEntry] = []
    for match in pattern.finditer(pre_content):
        href, modified, size_str = match.groups()
        # Ignorer les sous-dossiers et entrées sans taille
        if href.endswith("/") or size_str == "-":
            continue

        rel_path = f"{rel_prefix}{href}" if rel_prefix else href
        target_path = target_dir / href

        entries.append(
            FileEntry(
                filename=href,
                relative_path=rel_path,
                url=base_url.rstrip("/") + "/" + href,
                target_path=target_path,
                listing_size_str=size_str,
                listing_size_bytes=parse_size_to_bytes(size_str),
                modified=modified,
            )
        )

    # Tri selon les consignes :
    # 1. Fichiers dont le nom sans extension > 2 caractères, par poids décroissant
    # 2. Fichiers pays (nom sans extension <= 2 caractères), par poids décroissant
    gt2 = [e for e in entries if len(e.filename.rsplit(".", 1)[0]) > 2]
    le2 = [e for e in entries if len(e.filename.rsplit(".", 1)[0]) <= 2]

    gt2.sort(key=lambda e: (e.listing_size_bytes, e.filename), reverse=True)
    le2.sort(key=lambda e: (e.listing_size_bytes, e.filename), reverse=True)

    sorted_entries = gt2 + le2
    print(
        f"  → {len(sorted_entries)} fichier(s) trouvé(s) "
        f"({len(gt2)} fichiers > 2 car., {len(le2)} fichiers pays <= 2 car.)"
    )
    return sorted_entries


def polite_pause() -> None:
    """Marque une pause aléatoire entre 0.5s et 1.0s (zéro agressivité)."""
    delay = random.uniform(0.5, 1.0)
    time.sleep(delay)


def load_metadata_cache() -> dict[str, dict]:
    """Charge le cache des métadonnées téléchargées."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_metadata_cache(cache: dict[str, dict]) -> None:
    """Enregistre le cache des métadonnées."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def download_file(client: httpx.Client, entry: FileEntry, cache: dict[str, dict]) -> int | None:
    """Télécharge un fichier avec gestion streaming, fichier .part et mise à jour du cache.

    Retourne le Content-Length reçu, ou None en cas d'erreur.
    """
    entry.target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = entry.target_path.with_name(entry.target_path.name + ".part")

    with client.stream("GET", entry.url) as response:
        response.raise_for_status()
        header_len = response.headers.get("content-length")
        content_length = int(header_len) if header_len and header_len.isdigit() else None

        downloaded = 0
        last_print = time.time()
        with open(part_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if now - last_print > 0.5:
                        pct = f" ({downloaded * 100 // content_length}%)" if content_length else ""
                        sys.stdout.write(
                            f"\r    Téléchargement : {format_bytes(downloaded)}{pct}..."
                        )
                        sys.stdout.flush()
                        last_print = now

        sys.stdout.write(f"\r    Téléchargement : {format_bytes(downloaded)} (100%)       \n")
        sys.stdout.flush()

    # Remplacement atomique une fois le téléchargement complet
    part_path.replace(entry.target_path)

    # Mémorisation dans le cache
    cache[entry.relative_path] = {
        "content_length": content_length,
        "listing_size_str": entry.listing_size_str,
        "downloaded_bytes": downloaded,
        "downloaded_at": time.time(),
    }
    save_metadata_cache(cache)
    return content_length


def check_approx_size_consistency(actual_bytes: int, listing_str: str) -> tuple[bool, str]:
    """Vérifie la cohérence entre la taille réelle et la chaîne arrondie du listing Apache."""
    s = listing_str.strip().upper()
    if s == "0":
        return actual_bytes == 0, f"Attendu 0 octet, obtenu {actual_bytes}"
    if s.isdigit():
        expected = int(s)
        # Pour les petites tailles en octets purs, Apache donne la valeur exacte
        ok = actual_bytes == expected
        return ok, f"Listing exact: {expected} o vs Réel: {actual_bytes} o"

    # Tailles en K, M ou G
    val = float(s[:-1])
    unit = s[-1]
    multiplier = {"K": 1024, "M": 1024**2, "G": 1024**3}[unit]
    expected_bytes = val * multiplier

    # Tolérance pour l'arrondi d'affichage Apache :
    # Si affiché avec décimale (ex: 8.6M), tolérance ±0.1 unité.
    # Si entier (ex: 96K, 402M), tolérance ±1 unité d'arrondi ou 10%.
    has_decimal = "." in s[:-1]
    if has_decimal:
        margin = 0.1 * multiplier
    else:
        margin = max(1.0 * multiplier, expected_bytes * 0.08)

    min_bound = max(0.0, expected_bytes - margin)
    max_bound = expected_bytes + margin

    is_ok = min_bound <= actual_bytes <= max_bound
    return is_ok, f"Listing approx: {listing_str} (~{format_bytes(expected_bytes)}) vs Réel: {format_bytes(actual_bytes)}"


def verify_entry(
    client: httpx.Client, entry: FileEntry, cache: dict[str, dict]
) -> tuple[bool, list[str]]:
    """Vérifie un fichier : présence, taille vs Content-Length, taille vs listing, et intégrité zip."""
    errors: list[str] = []

    if not entry.target_path.exists():
        return False, ["Fichier absent du disque"]

    file_size = entry.target_path.stat().st_size

    # 1. Récupération du Content-Length (depuis le cache ou via HEAD poli)
    cached_info = cache.get(entry.relative_path, {})
    content_length = cached_info.get("content_length")

    if content_length is None:
        try:
            head_resp = client.head(entry.url)
            head_resp.raise_for_status()
            hlen = head_resp.headers.get("content-length")
            if hlen and hlen.isdigit():
                content_length = int(hlen)
                cached_info["content_length"] = content_length
                cached_info["listing_size_str"] = entry.listing_size_str
                cache[entry.relative_path] = cached_info
                save_metadata_cache(cache)
            polite_pause()
        except Exception as e:
            errors.append(f"Impossible d'interroger Content-Length via HEAD: {e}")

    # 2. Vérification taille fichier disque vs Content-Length HTTP
    if content_length is not None and file_size != content_length:
        errors.append(
            f"Incohérence Content-Length : attendu {content_length} octets, fichier disque fait {file_size} octets"
        )

    # 3. Vérification taille fichier vs valeur approx listing
    ok_listing, msg_listing = check_approx_size_consistency(file_size, entry.listing_size_str)
    if not ok_listing:
        errors.append(f"Incohérence listing : {msg_listing}")

    # 4. Vérification d'intégrité pour les fichiers ZIP
    if entry.filename.lower().endswith(".zip"):
        if not zipfile.is_zipfile(entry.target_path):
            errors.append("Le fichier n'est pas une archive ZIP valide (en-tête invalide)")
        else:
            try:
                with zipfile.ZipFile(entry.target_path, "r") as zf:
                    bad_member = zf.testzip()
                    if bad_member is not None:
                        errors.append(f"Archive ZIP corrompue (erreur CRC sur : {bad_member})")
            except Exception as e:
                errors.append(f"Échec de lecture du ZIP : {e}")

    return len(errors) == 0, errors


def main() -> None:
    """Point d'entrée principal du script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Téléchargement et vérification des exports GeoNames."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche uniquement l'ordre des fichiers sans effectuer de téléchargement.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Saute la phase de téléchargement initial et lance directement la vérification.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limite le nombre de fichiers traités (utile pour tester).",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("  TÉLÉCHARGEMENT & VÉRIFICATION DES DUMPS GEONAMES")
    print(f"  Dossier cible dump          : {BASE_DIR}")
    print(f"  Dossier cible alternatenames: {ALT_DIR}")
    if args.dry_run:
        print("  MODE : DRY-RUN (simulation sans téléchargement)")
    print("=" * 80)

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    ALT_DIR.mkdir(parents=True, exist_ok=True)

    cache = load_metadata_cache()

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=120.0, follow_redirects=True) as client:
        # Étape 1 : Récupération des listings
        dump_entries = fetch_listing(client, DUMP_BASE_URL, BASE_DIR, rel_prefix="")
        polite_pause()
        alt_entries = fetch_listing(client, ALT_BASE_URL, ALT_DIR, rel_prefix="alternatenames/")
        polite_pause()

        all_entries = dump_entries + alt_entries
        if args.limit > 0:
            all_entries = all_entries[: args.limit]
        total_files = len(all_entries)

        if args.dry_run:
            print("\n" + "-" * 80)
            print(f"SIMULATION : Ordre de traitement des fichiers ({total_files} au total) :")
            print("-" * 80)
            for idx, entry in enumerate(all_entries, 1):
                name_stem = entry.filename.rsplit(".", 1)[0]
                cat = "> 2 car." if len(name_stem) > 2 else "<= 2 car. (pays)"
                print(f"[{idx:3d}/{total_files}] {entry.relative_path:<38} | {entry.listing_size_str:>6} | {cat}")
            return

        # Étape 2 : Phase initiale de téléchargement (reprise sur existant)
        if not args.verify_only:
            print("\n" + "-" * 80)
            print("PHASE 1 : TÉLÉCHARGEMENT INITIAL (saut des fichiers déjà présents)")
            print("-" * 80)

            skipped_count = 0
            downloaded_count = 0

            for idx, entry in enumerate(all_entries, 1):
                prefix = f"[{idx}/{total_files}]"
                if entry.target_path.exists() and entry.target_path.stat().st_size > 0:
                    print(
                        f"{prefix} [SKIP] {entry.relative_path} (déjà présent, {format_bytes(entry.target_path.stat().st_size)})"
                    )
                    skipped_count += 1
                    continue

                print(f"{prefix} [DOWN] {entry.relative_path} ({entry.listing_size_str})")
                try:
                    download_file(client, entry, cache)
                    downloaded_count += 1
                except Exception as e:
                    print(f"    [ERREUR] Échec du téléchargement : {e}")

                polite_pause()

            print(f"\nFin de la phase de téléchargement : {downloaded_count} téléchargé(s), {skipped_count} sauté(s).")


        # Étape 3 : Phase de vérification d'intégrité de tous les fichiers
        print("\n" + "-" * 80)
        print("PHASE 2 : VÉRIFICATION DE LA COHÉRENCE ET DE L'INTÉGRITÉ DES FICHIERS")
        print("-" * 80)

        broken_entries: list[tuple[FileEntry, list[str]]] = []

        for idx, entry in enumerate(all_entries, 1):
            prefix = f"[{idx}/{total_files}]"
            is_valid, errors = verify_entry(client, entry, cache)
            if is_valid:
                size_disp = format_bytes(entry.target_path.stat().st_size)
                is_zip = entry.filename.lower().endswith(".zip")
                zip_tag = " - zip OK" if is_zip else ""
                print(f"{prefix} [OK] {entry.relative_path} ({size_disp}{zip_tag})")
            else:
                print(f"{prefix} [ANOMALIE] {entry.relative_path} :")
                for err in errors:
                    print(f"       ✖ {err}")
                broken_entries.append((entry, errors))

        # Étape 4 : Rapport et interaction utilisateur
        print("\n" + "=" * 80)
        if not broken_entries:
            print("RAPPORT FINAL : SUCCÈS")
            print(f"Tous les {total_files} fichiers sont présents, valides et intègres.")
            print("=" * 80)
            return

        print(f"RAPPORT FINAL : {len(broken_entries)} fichier(s) en anomalie / cassé(s) :")
        print("-" * 80)
        for entry, errs in broken_entries:
            print(f" • {entry.relative_path} : {'; '.join(errs)}")
        print("=" * 80)

        # Invite interactive
        try:
            choice = input(
                f"\nSouhaitez-vous relancer le téléchargement des {len(broken_entries)} fichier(s) en anomalie ? [O/n] : "
            ).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nOpération annulée par l'utilisateur.")
            return

        if choice not in ("", "o", "oui", "y", "yes"):
            print("Aucun retry effectué. Fin du script.")
            return

        # Étape 5 : Réessai unitaire avec affichage du statut final
        print("\n" + "-" * 80)
        print("PHASE 3 : NOUVELLE TENTATIVE POUR LES FICHIERS EN ANOMALIE")
        print("-" * 80)

        retry_success = 0
        retry_failed = 0

        for idx, (entry, _) in enumerate(broken_entries, 1):
            print(f"[{idx}/{len(broken_entries)}] Retry : {entry.relative_path} ...")
            if entry.target_path.exists():
                entry.target_path.unlink()

            try:
                download_file(client, entry, cache)
                polite_pause()
                is_valid, errors = verify_entry(client, entry, cache)
                if is_valid:
                    print(f"  → [STATUT FINAL : SUCCÈS] {entry.relative_path} réessayé et validé avec succès.")
                    retry_success += 1
                else:
                    print(f"  → [STATUT FINAL : ÉCHEC] {entry.relative_path} toujours en anomalie : {'; '.join(errors)}")
                    retry_failed += 1
            except Exception as e:
                print(f"  → [STATUT FINAL : ÉCHEC] Erreur lors du retéléchargement : {e}")
                retry_failed += 1

            polite_pause()

        print("\n" + "=" * 80)
        print("BILAN DES NOUVELLES TENTATIVES :")
        print(f" • Succès : {retry_success}")
        print(f" • Échecs : {retry_failed}")
        print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.stderr.close()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nInterruption du script par l'utilisateur.")
        sys.exit(130)
