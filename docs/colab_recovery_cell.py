# PhishTriage runtime recovery (read-only): no API calls, no git writes, no resets. Writes ONE archive in /content.
import hashlib, io, json, os, re, subprocess, tarfile, time
from pathlib import Path, PurePosixPath

CONTENT = Path(os.environ.get("RECOVERY_CONTENT", "/content"))
REPO = CONTENT / "PhishTriage"
EXPECTED_REMOTE = "https://github.com/nishtrip14/PhishTriage.git"
SOURCE_DIRS, ROOT_FILES = ("phishtriage", "tests", "docs"), {"README.md", "CLAUDE.md", "COLAB_STATUS.md", ".gitignore"}
SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".cfg"}            # notebooks excluded: outputs may hold email text
SKIP_PARTS = {".git", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "data", "models", "raw", "manual", "audit"}
MAX_BYTES = 2_000_000
SECRET = re.compile(rb"AIza[0-9A-Za-z_\-]{20,}|GEMINI_API_KEY\s*=\s*['\"][^'\"]{8,}|sk-[A-Za-z0-9]{20,}")
included, excluded = [], []

def git(*args):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                       env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})       # no index refresh writes
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode()[:200]}")
    return r.stdout

def wanted(rel: str) -> bool:
    p = PurePosixPath(rel)
    return (p.suffix in SUFFIXES and not (set(p.parts) & SKIP_PARTS)
            and (p.parts[0] in SOURCE_DIRS or rel in ROOT_FILES))

def add(tar, arcname, data: bytes, source):
    if len(data) > MAX_BYTES:
        return excluded.append({"path": arcname, "reason": f"larger than {MAX_BYTES} bytes"})
    if SECRET.search(data):
        return excluded.append({"path": arcname, "reason": "matches a secret pattern (not archived)"})
    info = tarfile.TarInfo(f"recovery/{arcname}"); info.size, info.mtime = len(data), int(time.time())
    tar.addfile(info, io.BytesIO(data))
    included.append({"path": arcname, "source": source, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

assert (REPO / ".git").is_dir(), f"{REPO} is not a git checkout"
remote = git("remote", "get-url", "origin").decode().strip()
assert remote == EXPECTED_REMOTE, f"unexpected remote {remote!r}; refusing to archive"
base = git("rev-parse", "HEAD").decode().strip()
status = git("status", "--porcelain=v1", "-z", "--untracked-files=all").decode().split("\0")
changed, deleted, entries = [], [], iter(filter(None, status))
for entry in entries:
    code, rel = entry[:2], entry[3:]
    if code[0] in "RC":
        next(entries, None)                                  # -z lists the rename/copy source separately
    (deleted if "D" in code else changed).append(rel)
diff = git("diff", "HEAD", "--", ".", ":(exclude)*.ipynb")

stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
out = CONTENT / f"phishtriage_recovery_{stamp}.tar.gz"
with tarfile.open(out, "w:gz") as tar:
    for rel in sorted(changed):
        path = REPO / rel
        if wanted(rel) and path.is_file() and not path.is_symlink():
            add(tar, f"repo/{rel}", path.read_bytes(), "repo-modified-or-new")
        else:
            excluded.append({"path": f"repo/{rel}", "reason": "outside source/test/doc scope, notebook, or not a regular file"})
    add(tar, "git_diff_HEAD.patch", diff, "git diff HEAD (tracked, no notebooks)")
    for path in sorted(CONTENT.glob("*")):                   # loose files Gemini may have written next to the repo
        if path.is_file() and not path.is_symlink() and path.suffix in {".py", ".md"}:
            add(tar, f"content/{path.name}", path.read_bytes(), "content-root")
    handoff = CONTENT / "phishtriage_handoff_package.tar.gz"
    members = None
    if handoff.is_file():
        members = []
        with tarfile.open(handoff) as src:                   # inspect members; never extract to disk
            for m in src.getmembers():
                p = PurePosixPath(m.name)
                safe = m.isfile() and not p.is_absolute() and ".." not in p.parts
                members.append({"name": m.name, "size": m.size, "type": "file" if m.isfile() else "other", "safe": safe})
                if safe and p.suffix in SUFFIXES and not (set(p.parts) & SKIP_PARTS):
                    add(tar, f"handoff/{m.name}", src.extractfile(m).read(), "handoff-archive-member")
    manifest = {"created_utc": stamp, "repo": str(REPO), "remote": remote, "base_commit": base,
                "git_status_changed": changed, "git_status_deleted": deleted, "included": included,
                "excluded": excluded, "handoff_archive_members": members,
                "note": "Read-only recovery: no API calls, no git writes. Notebooks, data, models, caches excluded."}
    data = json.dumps(manifest, indent=2).encode()
    info = tarfile.TarInfo("recovery/MANIFEST.json"); info.size, info.mtime = len(data), int(time.time())
    tar.addfile(info, io.BytesIO(data))

print(f"base commit {base}\nchanged/new: {len(changed)}  deleted: {len(deleted)}  archived files: {len(included)}  "
      f"excluded: {len(excluded)}  handoff archive: {'found' if members is not None else 'not found'}")
for item in included:
    print("  +", item["path"])
for item in excluded:
    print("  -", item["path"], "->", item["reason"])
print("archive:", out, f"({out.stat().st_size:,} bytes)")
try:
    from google.colab import files
    files.download(str(out))
except ImportError:
    print("(not in Colab: download skipped)")
