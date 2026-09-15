#!/usr/bin/env python3
"""Script de téléchargement et de vérification des archives geoBoundaries.

Fonctionnalités :
1. Connexion au listing https://www.geoboundaries.org/countryDownloads.html
   et extraction dynamique de l'API Tabulator (gbOpen/ALL/ALL/).
2. Téléchargement des archives complètes ZIP (staticDownloadLink) dans l'ordre,
   classées dans des sous-dossiers par code pays (ISO-3) :
   ~/projets/geo_data/data/geoboundaries/{ISO3}/{filename}.zip
3. Reprise sur existant : saut des fichiers déjà présents sur disque en phase 1.
4. Téléchargement poli et sécurisé :
   - Requêtes séquentielles avec pause aléatoire de 0.5s à 1.0s.
   - Téléchargement en streaming via fichier temporaire (.part) puis renommage atomique.
5. Phase de vérification :
   - Cohérence de la taille réelle sur disque avec le Content-Length HTTP.
   - Validité et intégrité de l'archive ZIP via testzip() (contrôle CRC32).
6. Interaction utilisateur :
   - Présentation de la liste des fichiers en anomalie.
   - Invite interactive de confirmation avant relance.
   - Réessai unitaire avec affichage du statut final pour chaque fichier.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

PAGE_URL = "https://www.geoboundaries.org/countryDownloads.html"
FALLBACK_API_URL = "https://www.geoboundaries.org/api/current/gbOpen/ALL/ALL/"

BASE_DIR = Path(__file__).resolve().parent / "data" / "geoboundaries"
CACHE_FILE = BASE_DIR / ".metadata_index.json"

CHUNK_SIZE = 64 * 1024  # 64 KB
USER_AGENT = "GeoBoundariesDownloader/1.0 (+https://github.com/MarvinLeRouge)"


@dataclass
class BoundaryEntry:
    boundary_id: str
    country_name: str
    iso: str
    boundary_type: str
    filename: str
    relative_path: str  # e.g. "FRA/geoBoundaries-FRA-ADM1-all.zip"
    url: str
    target_path: Path


def polite_pause() -> None:
    """Marque une pause aléatoire entre 0.5s et 1.0s (zéro agressivité)."""
    delay = random.uniform(0.5, 1.0)
    time.sleep(delay)


def format_bytes(num_bytes: float) -> str:
    """Formate un nombre d'octets de façon lisible."""
    for unit in ["o", "Ko", "Mo", "Go"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}" if unit != "o" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} To"


def discover_api_url(client: httpx.Client, page_url: str) -> str:
    """Récupère la page HTML et extrait l'URL de l'API appelée par Tabulator."""
    print(f"Connexion à la page : {page_url} ...")
    try:
        resp = client.get(page_url)
        resp.raise_for_status()
        match = re.search(r"""ajaxURL:\s*["']([^"']+)["']""", resp.text)
        if match:
            api_url = match.group(1)
            print(f"  → Endpoint API extrait avec succès : {api_url}")
            return api_url
    except Exception as e:
        print(f"  [WARN] Impossible d'extraire dynamiquement l'URL ({e}), utilisation du fallback.")

    return FALLBACK_API_URL


def fetch_entries(client: httpx.Client, api_url: str) -> list[BoundaryEntry]:
    """Interroge l'API geoBoundaries et construit la liste ordonnée des fichiers à télécharger."""
    print(f"Récupération de la liste des frontières depuis : {api_url} ...")
    resp = client.get(api_url)
    resp.raise_for_status()
    raw_data = resp.json()

    entries: list[BoundaryEntry] = []
    seen_urls: set[str] = set()

    for item in raw_data:
        url = item.get("staticDownloadLink")
        if not url or not url.endswith(".zip"):
            continue

        # Déduplication si la même URL est présente plusieurs fois dans la réponse de l'API
        if url in seen_urls:
            continue
        seen_urls.add(url)

        iso = item.get("boundaryISO") or item.get("shapeGroup") or "UNKNOWN"
        iso = iso.strip().upper()
        country_name = item.get("boundaryName", "Unknown")
        boundary_type = item.get("boundaryType", "ADM")
        boundary_id = item.get("boundaryID", "")

        filename = url.split("/")[-1]
        relative_path = f"{iso}/{filename}"
        target_path = BASE_DIR / iso / filename

        entries.append(
            BoundaryEntry(
                boundary_id=boundary_id,
                country_name=country_name,
                iso=iso,
                boundary_type=boundary_type,
                filename=filename,
                relative_path=relative_path,
                url=url,
                target_path=target_path,
            )
        )

    print(f"  → {len(entries)} fichier(s) ZIP à télécharger trouvés.")
    return entries


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


def download_file(client: httpx.Client, entry: BoundaryEntry, cache: dict[str, dict]) -> int | None:
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

    # Remplacement atomique une fois le fichier complètement téléchargé
    part_path.replace(entry.target_path)

    # Mise à jour du cache
    cache[entry.relative_path] = {
        "content_length": content_length,
        "downloaded_bytes": downloaded,
        "downloaded_at": time.time(),
        "url": entry.url,
    }
    save_metadata_cache(cache)
    return content_length


def verify_entry(
    client: httpx.Client, entry: BoundaryEntry, cache: dict[str, dict]
) -> tuple[bool, list[str]]:
    """Vérifie un fichier ZIP : présence, taille vs Content-Length, intégrité ZIP."""
    errors: list[str] = []

    if not entry.target_path.exists():
        return False, ["Fichier absent du disque"]

    file_size = entry.target_path.stat().st_size
    if file_size == 0:
        return False, ["Fichier vide (0 octet)"]

    # 1. Récupération du Content-Length attendu (depuis le cache ou via HEAD HTTP poli)
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
                cache[entry.relative_path] = cached_info
                save_metadata_cache(cache)
            polite_pause()
        except Exception as e:
            errors.append(f"Impossible d'obtenir Content-Length via HEAD : {e}")

    # 2. Vérification de cohérence de taille disque vs Content-Length
    if content_length is not None and file_size != content_length:
        errors.append(
            f"Incohérence de taille Content-Length : attendu {content_length} octets ({format_bytes(content_length)}), "
            f"fichier disque fait {file_size} octets ({format_bytes(file_size)})"
        )

    # 3. Vérification de l'intégrité de l'archive ZIP
    if not zipfile.is_zipfile(entry.target_path):
        errors.append("Le fichier n'est pas une archive ZIP valide (en-tête corrompu)")
    else:
        try:
            with zipfile.ZipFile(entry.target_path, "r") as zf:
                bad_member = zf.testzip()
                if bad_member is not None:
                    errors.append(f"Archive ZIP corrompue (erreur CRC32 sur : {bad_member})")
        except Exception as e:
            errors.append(f"Échec de lecture du ZIP : {e}")

    return len(errors) == 0, errors


def main() -> None:
    """Point d'entrée principal du script."""
    parser = argparse.ArgumentParser(
        description="Téléchargement et vérification des archives geoBoundaries."
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
    print("  TÉLÉCHARGEMENT & VÉRIFICATION DES ARCHIVES GEOBOUNDARIES")
    print(f"  Dossier cible : {BASE_DIR}")
    if args.dry_run:
        print("  MODE : DRY-RUN (simulation sans téléchargement)")
    print("=" * 80)

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_metadata_cache()

    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=120.0, follow_redirects=True) as client:
        # Étape 1 : Récupération du listing via la page puis l'API
        api_url = discover_api_url(client, PAGE_URL)
        polite_pause()

        entries = fetch_entries(client, api_url)
        if args.limit > 0:
            entries = entries[: args.limit]
        total_files = len(entries)

        if args.dry_run:
            print("\n" + "-" * 80)
            print(f"SIMULATION : Liste ordonnée des fichiers ({total_files} au total) :")
            print("-" * 80)
            for idx, entry in enumerate(entries, 1):
                print(
                    f"[{idx:3d}/{total_files}] {entry.relative_path:<45} | "
                    f"{entry.country_name} ({entry.boundary_type})"
                )
            return

        # Étape 2 : Phase initiale de téléchargement (reprise sur existant)
        if not args.verify_only:
            print("\n" + "-" * 80)
            print("PHASE 1 : TÉLÉCHARGEMENT INITIAL (saut des fichiers déjà présents)")
            print("-" * 80)

            skipped_count = 0
            downloaded_count = 0

            for idx, entry in enumerate(entries, 1):
                prefix = f"[{idx}/{total_files}]"
                if entry.target_path.exists() and entry.target_path.stat().st_size > 0:
                    size_disp = format_bytes(entry.target_path.stat().st_size)
                    print(f"{prefix} [SKIP] {entry.relative_path} (déjà présent, {size_disp})")
                    skipped_count += 1
                    continue

                print(f"{prefix} [DOWN] {entry.relative_path} ({entry.country_name} - {entry.boundary_type})")
                try:
                    download_file(client, entry, cache)
                    downloaded_count += 1
                except Exception as e:
                    print(f"    [ERREUR] Échec du téléchargement : {e}")

                polite_pause()

            print(f"\nFin de la phase de téléchargement : {downloaded_count} téléchargé(s), {skipped_count} sauté(s).")

        # Étape 3 : Phase de vérification d'intégrité de tous les fichiers
        print("\n" + "-" * 80)
        print("PHASE 2 : VÉRIFICATION DE LA COHÉRENCE DES TAILLES ET DE L'INTÉGRITÉ DES ZIPS")
        print("-" * 80)

        broken_entries: list[tuple[BoundaryEntry, list[str]]] = []

        for idx, entry in enumerate(entries, 1):
            prefix = f"[{idx}/{total_files}]"
            is_valid, errors = verify_entry(client, entry, cache)
            if is_valid:
                size_disp = format_bytes(entry.target_path.stat().st_size)
                print(f"{prefix} [OK] {entry.relative_path} ({size_disp} - zip valide)")
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
        # Permet de piper proprement vers head ou less
        sys.stderr.close()
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nInterruption du script par l'utilisateur.")
        sys.exit(130)
