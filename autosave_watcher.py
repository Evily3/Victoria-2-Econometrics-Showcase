"""Archive Victoria II saves before the game overwrites them.

Polls the save folder; whenever a .v2 file has changed and has been left alone for a few
seconds (the game has finished writing), it is copied into an archive folder under a name
that includes the in-game date, and logged in manifest.csv. Identical content is never
archived twice (SHA-256 check). Standard library only.

    python autosave_watcher.py                 # run until Ctrl+C
    python autosave_watcher.py --once          # single pass, then exit (good for Task Scheduler)
    python autosave_watcher.py --src "D:\\other\\save games" --dst "D:\\archive"
"""
import argparse, csv, hashlib, re, shutil, time
from datetime import datetime
from pathlib import Path

DEFAULT_SRC = Path(r"C:\Users\Evan\Documents\Paradox Interactive\Victoria II\TGC\save games")
DEFAULT_DST = DEFAULT_SRC.parent / "save_archive"       # sibling folder, so the game never lists it
MANIFEST_COLS = ["archived_at", "source_file", "archived_file", "game_date", "player", "sha256"]

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def peek_header(path):
    """Saves start with date="Y.M.D" and player="TAG"; read just the first few hundred bytes."""
    with open(path, "rb") as f:
        head = f.read(400).decode("cp1252", errors="replace")
    d = re.search(r'date="(\d+)\.(\d+)\.(\d+)"', head)
    p = re.search(r'player="([^"]*)"', head)
    date = f"{int(d[1]):04d}-{int(d[2]):02d}-{int(d[3]):02d}" if d else "unknown-date"
    return date, (p[1] if p else "UNK")

def load_seen(manifest):
    if not manifest.exists():
        return set()
    with open(manifest, newline="", encoding="utf-8") as f:
        return {row["sha256"] for row in csv.DictReader(f)}

def archive(path, dst, manifest, seen):
    digest = sha256(path)
    if digest in seen:
        return False
    date, player = peek_header(path)
    safe_stem = re.sub(r"[^\w.-]+", "_", path.stem)
    out = dst / f"{player}_{date}_{safe_stem}_{digest[:8]}{path.suffix}"
    shutil.copy2(path, out)
    new = not manifest.exists()
    with open(manifest, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(MANIFEST_COLS)
        w.writerow([datetime.now().isoformat(timespec="seconds"), path.name, out.name, date, player, digest])
    seen.add(digest)
    print(f"[{datetime.now():%H:%M:%S}] archived {path.name} -> {out.name}")
    # Hook for later: run the extractor here, e.g. extract_snapshot(out) -> append to panel table.
    return True

def scan(src, dst, manifest, seen, last_sig, settle):
    for p in sorted(src.glob("*.v2")):
        try:
            st = p.stat()
            sig = (st.st_mtime_ns, st.st_size)
            if last_sig.get(p) == sig:
                continue                                  # unchanged since last look
            if time.time() - st.st_mtime < settle:
                continue                                  # game may still be writing; retry next poll
            archive(p, dst, manifest, seen)
            last_sig[p] = sig
        except (PermissionError, FileNotFoundError, OSError) as e:
            print(f"  skipped {p.name} (will retry): {e}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--poll", type=float, default=5.0, help="seconds between checks (default 5)")
    ap.add_argument("--settle", type=float, default=5.0, help="file must be untouched this long (default 5)")
    ap.add_argument("--once", action="store_true", help="scan once and exit")
    a = ap.parse_args()

    if not a.src.is_dir():
        raise SystemExit(f"Save folder not found: {a.src}")
    a.dst.mkdir(parents=True, exist_ok=True)
    manifest = a.dst / "manifest.csv"
    seen, last_sig = load_seen(manifest), {}
    print(f"Watching {a.src}\nArchive  {a.dst}\n({len(seen)} saves already archived)  Ctrl+C to stop.")
    try:
        while True:
            scan(a.src, a.dst, manifest, seen, last_sig, a.settle)
            if a.once:
                break
            time.sleep(a.poll)
    except KeyboardInterrupt:
        print("Stopped.")

if __name__ == "__main__":
    main()
