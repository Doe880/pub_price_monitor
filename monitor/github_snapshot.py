"""Read-only GitHub branch snapshots for Render's ephemeral filesystem.

GitHub contents:read token stays server-side. The snapshot includes only public
menu observations, not credentials. Local PyCharm mode never calls GitHub.
"""
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import requests

DEFAULT_REPO = "Doe880/pub_price_monitor"
DEFAULT_BRANCH = "price-data"
MAX_COMPRESSED_BYTES = 20_000_000
MAX_SQLITE_BYTES = 120_000_000


class SnapshotError(RuntimeError):
    pass


def _github_json(session, url, token):
    response = session.get(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=(8, 25),
        allow_redirects=False,
    )
    if response.status_code != 200:
        raise SnapshotError("GitHub snapshot unavailable (HTTP %s)" % response.status_code)
    try:
        return response.json()
    except (ValueError, TypeError) as exc:
        raise SnapshotError("Invalid GitHub snapshot response") from exc


def download_snapshot(token, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH, session=None):
    """Retrieve a private branch's blob by exact Git SHA (supports >1MB files)."""
    if not token:
        raise SnapshotError("GITHUB_READ_TOKEN is not configured")
    if repo != DEFAULT_REPO:
        raise SnapshotError("Unexpected GitHub repository")
    if branch != DEFAULT_BRANCH:
        raise SnapshotError("Unexpected data branch")
    session = session or requests.Session()
    api = "https://api.github.com/repos/" + repo
    tree = _github_json(session, api + "/git/trees/" + branch, token)
    candidates = [
        entry for entry in tree.get("tree", [])
        if entry.get("path") == "snapshot.sqlite3.gz" and entry.get("type") == "blob"
    ]
    if len(candidates) != 1:
        raise SnapshotError("No published price snapshot; run the GitHub collection workflow")
    entry = candidates[0]
    if int(entry.get("size", 0)) > MAX_COMPRESSED_BYTES:
        raise SnapshotError("Published snapshot exceeds size limit")
    blob = _github_json(session, api + "/git/blobs/" + entry["sha"], token)
    if blob.get("encoding") != "base64":
        raise SnapshotError("Unsupported GitHub blob encoding")
    try:
        data = base64.b64decode(blob["content"], validate=False)
    except (TypeError, ValueError) as exc:
        raise SnapshotError("Invalid encoded snapshot") from exc
    if len(data) > MAX_COMPRESSED_BYTES or hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != entry["sha"]:
        raise SnapshotError("Snapshot size or Git blob integrity check failed")
    return data, entry["sha"]


def validate_database(path):
    """Reject invalid or unexpected databases before replacing a good cache."""
    con = sqlite3.connect(str(path))
    try:
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SnapshotError("SQLite integrity check failed")
        required = {"sources", "checks", "observations"}
        present = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= present:
            raise SnapshotError("Missing expected snapshot tables")
        if con.execute("SELECT count(*) FROM sources WHERE enabled=1").fetchone()[0] < 1:
            raise SnapshotError("Snapshot contains no enabled price sources")
    except sqlite3.DatabaseError as exc:
        raise SnapshotError("Corrupt SQLite price database") from exc
    finally:
        con.close()


def install_snapshot(gzip_bytes, destination):
    """Verify gzip, size and SQLite integrity; atomically replace local cache."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".snapshot-", suffix=".sqlite3", dir=str(destination.parent))
    os.close(fd)
    try:
        decompressor = gzip.GzipFile(fileobj=__import__("io").BytesIO(gzip_bytes), mode="rb")
        with decompressor, open(tmp, "wb") as out:
            total = 0
            while chunk := decompressor.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_SQLITE_BYTES:
                    raise SnapshotError("Decompressed price snapshot too large")
                out.write(chunk)
        validate_database(tmp)
        os.replace(tmp, destination)
    except (OSError, EOFError, gzip.BadGzipFile, zlib_error()) as exc:
        raise SnapshotError("Damaged compressed price snapshot") from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def zlib_error():
    import zlib
    return zlib.error


def create_snapshot(database_path, output_path):
    """Make a consistent SQLite backup, then gzip without copying live WAL files."""
    src = Path(database_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".backup-", suffix=".sqlite3")
    os.close(fd)
    try:
        with sqlite3.connect(str(src)) as origin, sqlite3.connect(tmp) as backup:
            origin.backup(backup)
        validate_database(tmp)
        with open(tmp, "rb") as fh, gzip.open(output, "wb", compresslevel=6) as gz:
            while chunk := fh.read(1024 * 1024):
                gz.write(chunk)
        if output.stat().st_size > MAX_COMPRESSED_BYTES:
            output.unlink(missing_ok=True)
            raise SnapshotError("Snapshot too large for GitHub storage branch")
    finally:
        os.unlink(tmp)
    return {
        "compressed_bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("restore", "create"))
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "restore":
        install_snapshot(Path(args.input).read_bytes(), Path(args.output))
    else:
        print(json.dumps(create_snapshot(args.input, args.output)))


if __name__ == "__main__":
    main()
