"""Ubuntu Archive ls-lR Indexer, Watchdog Baseline & Package Resolver.

Streams a 352MB+ Ubuntu Launchpad `ls-lR` index into a fast searchable SQLite
database (`crow_archive_index.db`) and generates a 10-year structural baseline
(`archive_intel_summary.json`) for AtAA Watchdog & on-demand package downloads.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LSLR = Path(r"C:\Users\Owner\OneDrive\Desktop\MINE\games\ls-lR")
DB_PATH = BASE_DIR / "crow_archive_index.db"
SUMMARY_PATH = BASE_DIR / "archive_intel_summary.json"
ARCHIVE_BASE_URL = "https://archive.ubuntu.com/ubuntu/"

LINE_RE = re.compile(
    r"^([\-dlcbps])([rwxstST\-]{9})\s+\d+\s+\S+\s+\S+\s+(\d+)\s+"
    r"([A-Z][a-z]{2}\s+\d+\s+(?:\d{4}|\d{2}:\d{2}))\s+(.+)$"
)


def parse_component(rel_dir: str) -> str:
    parts = rel_dir.strip("./").split("/")
    if len(parts) >= 2 and parts[0] == "pool":
        return parts[1]
    if parts and parts[0]:
        return parts[0]
    return "root"


def parse_ext(filename: str) -> str:
    for ext in (".deb", ".udeb", ".ddeb", ".dsc", ".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst", ".gz", ".xz", ".zst"):
        if filename.endswith(ext):
            return ext
    return Path(filename).suffix or "other"


def extract_year(ts_str: str) -> str:
    tokens = ts_str.split()
    if len(tokens) == 3 and len(tokens[2]) == 4 and tokens[2].isdigit():
        return tokens[2]
    return "recent"


def build_index(lslr_path: Path, db_path: Path, summary_path: Path) -> None:
    if not lslr_path.exists():
        raise FileNotFoundError(f"ls-lR file not found: {lslr_path}")

    t0 = time.perf_counter()
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            component TEXT,
            dir_path TEXT,
            filename TEXT,
            package TEXT,
            ext TEXT,
            size_bytes INTEGER,
            perms TEXT,
            ts_str TEXT,
            rel_path TEXT
        )
        """
    )

    cur_dir = "."
    dir_count = 0
    file_count = 0
    total_bytes = 0
    comp_counts: Counter[str] = Counter()
    ext_counts: Counter[str] = Counter()
    year_counts: Counter[str] = Counter()
    distro_tracks: set[str] = set()
    perm_anomalies: list[dict[str, str]] = []
    batch: list[tuple] = []

    with lslr_path.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line or line.startswith("total "):
                continue
            if line.endswith(":") and (line.startswith("./") or line == ".:"):
                cur_dir = line[:-1]
                dir_count += 1
                if cur_dir.startswith("./dists/") and cur_dir.count("/") == 2:
                    distro_tracks.add(cur_dir.split("/")[2])
                continue

            m = LINE_RE.match(line)
            if not m:
                continue
            ftype, perms, size_str, ts_str, name = m.groups()
            if ftype != "-":
                continue

            size_bytes = int(size_str)
            clean_dir = cur_dir.lstrip("./")
            rel_path = f"{clean_dir}/{name}" if clean_dir else name
            component = parse_component(cur_dir)
            ext = parse_ext(name)
            package = name.split("_", 1)[0]
            year = extract_year(ts_str)

            file_count += 1
            total_bytes += size_bytes
            comp_counts[component] += 1
            ext_counts[ext] += 1
            year_counts[year] += 1

            # Watchdog baseline check: world-writable or setuid/setgid regular files
            if perms[7] == "w" or "s" in perms.lower():
                if len(perm_anomalies) < 50:
                    perm_anomalies.append({"path": rel_path, "perms": perms, "size": str(size_bytes)})

            batch.append((component, clean_dir, name, package, ext, size_bytes, perms, ts_str, rel_path))
            if len(batch) >= 25000:
                conn.executemany(
                    "INSERT INTO files (component, dir_path, filename, package, ext, size_bytes, perms, ts_str, rel_path) VALUES (?,?,?,?,?,?,?,?,?)",
                    batch,
                )
                batch.clear()

    if batch:
        conn.executemany(
            "INSERT INTO files (component, dir_path, filename, package, ext, size_bytes, perms, ts_str, rel_path) VALUES (?,?,?,?,?,?,?,?,?)",
            batch,
        )

    conn.execute("CREATE INDEX idx_package ON files(package)")
    conn.execute("CREATE INDEX idx_filename ON files(filename)")
    conn.execute("CREATE INDEX idx_component_ext ON files(component, ext)")
    conn.commit()
    conn.close()

    elapsed = round(time.perf_counter() - t0, 2)
    summary = {
        "source_file": str(lslr_path),
        "source_bytes": lslr_path.stat().st_size,
        "archive_base_url": ARCHIVE_BASE_URL,
        "indexed_seconds": elapsed,
        "directories": dir_count,
        "files": file_count,
        "total_archive_tb": round(total_bytes / (1024**4), 3),
        "components": dict(comp_counts.most_common(12)),
        "extensions": dict(ext_counts.most_common(12)),
        "years": dict(sorted(year_counts.items())),
        "distro_tracks_count": len(distro_tracks),
        "distro_tracks_sample": sorted(distro_tracks)[:30],
        "watchdog_perm_anomalies_count": len(perm_anomalies),
        "watchdog_perm_anomalies_sample": perm_anomalies[:10],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def search_index(query: str, limit: int = 15) -> None:
    if not DB_PATH.exists():
        print("Index not built yet. Run: python archive_intel.py build", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        """
        SELECT component, filename, size_bytes, ts_str, rel_path
        FROM files
        WHERE package LIKE ? OR filename LIKE ?
        ORDER BY ext = '.deb' DESC, size_bytes DESC
        LIMIT ?
        """,
        (f"{query}%", f"%{query}%", limit),
    ).fetchall()
    conn.close()
    for comp, fname, size_b, ts_str, rel in rows:
        mb = size_b / (1024 * 1024)
        print(f"[{comp}] {fname} ({mb:.2f} MB, {ts_str})")
        print(f"   -> {ARCHIVE_BASE_URL}{rel}")


def download_package(query: str, out_dir: Path) -> None:
    if not DB_PATH.exists():
        print("Index not built yet. Run: python archive_intel.py build", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT filename, rel_path, size_bytes FROM files WHERE filename = ? OR package LIKE ? ORDER BY ext = '.deb' DESC LIMIT 1",
        (query, f"{query}%"),
    ).fetchone()
    conn.close()
    if not row:
        print(f"No package matched '{query}'", file=sys.stderr)
        sys.exit(1)
    fname, rel, size_b = row
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / fname
    urls = [f"{ARCHIVE_BASE_URL}{rel}", f"https://old-releases.ubuntu.com/ubuntu/{rel}"]
    last_err: Exception | None = None
    for url in urls:
        try:
            print(f"Downloading {url} ({size_b} bytes) -> {dest}")
            urllib.request.urlretrieve(url, dest)
            print(f"Saved: {dest} ({os.path.getsize(dest)} bytes)")
            return
        except Exception as exc:
            last_err = exc
            print(f"Mirror fallback ({url} failed: {exc})")
    print(f"Download failed on all mirrors: {last_err}", file=sys.stderr)
    sys.exit(1)


def package_timeline(pkg: str) -> None:
    if not DB_PATH.exists():
        print("Index not built yet. Run: python archive_intel.py build", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT component, filename, ext, size_bytes, ts_str, rel_path FROM files WHERE package = ? OR package LIKE ?",
        (pkg, f"{pkg}%"),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"No package history found for '{pkg}'")
        return
    years: Counter[str] = Counter()
    comps: Counter[str] = Counter()
    exts: Counter[str] = Counter()
    deb_sizes: list[tuple[str, int, str]] = []
    for comp, fname, ext, size_b, ts_str, rel in rows:
        years[extract_year(ts_str)] += 1
        comps[comp] += 1
        exts[ext] += 1
        if ext == ".deb":
            deb_sizes.append((fname, size_b, rel))
    deb_sizes.sort(key=lambda x: x[1])
    report = {
        "query": pkg,
        "total_artifacts": len(rows),
        "components": dict(comps),
        "extensions": dict(exts.most_common(8)),
        "years": dict(sorted(years.items())),
        "smallest_deb": {"file": deb_sizes[0][0], "bytes": deb_sizes[0][1], "url": f"{ARCHIVE_BASE_URL}{deb_sizes[0][2]}"} if deb_sizes else None,
        "largest_deb": {"file": deb_sizes[-1][0], "bytes": deb_sizes[-1][1], "url": f"{ARCHIVE_BASE_URL}{deb_sizes[-1][2]}"} if deb_sizes else None,
    }
    print(json.dumps(report, indent=2))


def verify_artifact(filename: str, expected_bytes: int | None = None) -> None:
    if not DB_PATH.exists():
        print("Index not built yet. Run: python archive_intel.py build", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT component, filename, size_bytes, perms, ts_str, rel_path FROM files WHERE filename = ? LIMIT 1",
        (filename,),
    ).fetchone()
    conn.close()
    if not row:
        print(json.dumps({"verified": False, "status": "UNKNOWN_ARTIFACT", "filename": filename}, indent=2))
        return
    comp, fname, size_b, perms, ts_str, rel = row
    size_ok = expected_bytes is None or expected_bytes == size_b
    print(json.dumps({
        "verified": size_ok,
        "status": "MATCH" if size_ok else "SIZE_MISMATCH",
        "component": comp,
        "filename": fname,
        "expected_bytes": size_b,
        "actual_bytes": expected_bytes,
        "perms": perms,
        "timestamp": ts_str,
        "url": f"{ARCHIVE_BASE_URL}{rel}",
        "fallback_url": f"https://old-releases.ubuntu.com/ubuntu/{rel}",
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ubuntu ls-lR Decade Archive Indexer & Resolver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Index ls-lR into SQLite + Watchdog baseline JSON")
    p_build.add_argument("--input", type=Path, default=DEFAULT_LSLR)

    p_search = sub.add_parser("search", help="Search indexed packages & resolve download URLs")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    p_dl = sub.add_parser("download", help="Download a package from archive.ubuntu.com (or old-releases fallback)")
    p_dl.add_argument("query")
    p_dl.add_argument("--out", type=Path, default=BASE_DIR / "downloads")

    p_tl = sub.add_parser("timeline", help="Show 20-year release timeline & size range for a package")
    p_tl.add_argument("package")

    p_vf = sub.add_parser("verify", help="Watchdog supply-chain verification against ls-lR baseline")
    p_vf.add_argument("filename")
    p_vf.add_argument("bytes", type=int, nargs="?", default=None)

    args = parser.parse_args()
    if args.cmd == "build":
        build_index(args.input, DB_PATH, SUMMARY_PATH)
    elif args.cmd == "search":
        search_index(args.query, args.limit)
    elif args.cmd == "download":
        download_package(args.query, args.out)
    elif args.cmd == "timeline":
        package_timeline(args.package)
    elif args.cmd == "verify":
        verify_artifact(args.filename, args.bytes)


if __name__ == "__main__":
    main()
