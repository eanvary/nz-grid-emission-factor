"""
Writes DATA_MANIFEST.csv at the repository root: path (relative, forward slashes), size in
bytes and SHA-256 for every .csv and .parquet file directly in output/ and anywhere under
output/edgs/. Snapshot folders (names starting "_pre" or "_backup") are skipped: they hold
older copies kept for comparison, not database files. Rerun after any output changes.
"""
import csv
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "DATA_MANIFEST.csv"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def skipped(p):
    return any(part.startswith(("_pre", "_backup")) for part in p.relative_to(ROOT).parts)


files = [p for p in (ROOT / "output").glob("*") if p.suffix in (".csv", ".parquet") and p.is_file()]
files += [p for p in (ROOT / "output" / "edgs").rglob("*") if p.suffix in (".csv", ".parquet") and p.is_file() and not skipped(p)]
files = sorted(set(files))
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["path", "size_bytes", "sha256"])
    for p in files:
        w.writerow([p.relative_to(ROOT).as_posix(), p.stat().st_size, sha256(p)])
big = [p for p in files if p.stat().st_size > 100 * 1024 * 1024]
print(f"Wrote {OUT.name}: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e9:.2f} GB; "
      f"{len(big)} over 100 MB: {[p.relative_to(ROOT).as_posix() for p in big]}")
