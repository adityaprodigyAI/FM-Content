"""push_archive — CLI for the GitHub Actions Path B WAF unblock.

Reads every JSON file in `data/runs/_pending-push/` whose `wp_post_id` is
null, pushes each via WP REST POST with HTTP basic auth (using
FM_WP_USER + FM_WP_APP_PASSWORD env vars), and writes the resulting
`wp_post_id` back to the file. Idempotent — re-running the same workflow
skips already-pushed drafts.

Usage:

    python -m tools.push_archive --apply
    python -m tools.push_archive --apply --dir data/runs/_pending-push

The expected GH Actions workflow flow:

    1. Trigger on push to `data/runs/_pending-push/*.json` (or workflow_dispatch).
    2. Set FM_WP_USER + FM_WP_APP_PASSWORD from repo secrets.
    3. Run `python -m tools.push_archive --apply`.
    4. Commit the modified JSON files with `[skip ci]` in the message.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .push_wp import (
    PENDING_PUSH_DIR,
    list_pending_pushes,
    push_via_app_password,
)


def _push_one(path: Path, *, user: str, app_password: str) -> bool:
    """Push one pending JSON file. Returns True on success.

    Skips files where `wp_post_id` is already set (idempotent).
    """
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    if data.get("wp_post_id"):
        print(f"skip (already pushed wp_post_id={data['wp_post_id']}): {path.name}")
        return True

    try:
        resp = push_via_app_password(data, user=user, app_password=app_password)
    except Exception as e:  # noqa: BLE001 — we want to log and move on
        print(f"FAIL {path.name}: {e}", file=sys.stderr)
        return False

    pid = resp.get("id") or resp.get("ID")
    if not pid:
        print(f"FAIL {path.name}: response had no id field; resp={resp}",
              file=sys.stderr)
        return False

    data["wp_post_id"] = int(pid)
    data["wp_link"] = resp.get("link")
    data["wp_status"] = resp.get("status")

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)
    print(f"OK   {path.name} -> wp_post_id={pid}")
    return True


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.push_archive")
    parser.add_argument("--apply", action="store_true",
                        help="Actually push (without this flag, just lists pending files)")
    parser.add_argument("--dir", default=str(PENDING_PUSH_DIR),
                        help="Pending-push dir (default: data/runs/_pending-push)")
    args = parser.parse_args(argv)

    pending = list_pending_pushes(Path(args.dir))
    if not pending:
        print("No pending pushes.")
        return 0

    print(f"{len(pending)} pending push(es) in {args.dir}")
    for p in pending:
        print(f"  - {p.name}")

    if not args.apply:
        print("\n(dry run; pass --apply to push)")
        return 0

    user = os.environ.get("FM_WP_USER")
    pwd = os.environ.get("FM_WP_APP_PASSWORD")
    if not user or not pwd:
        print("ERROR: FM_WP_USER and FM_WP_APP_PASSWORD must be set in env",
              file=sys.stderr)
        return 2

    failed = 0
    for path in pending:
        ok = _push_one(path, user=user, app_password=pwd)
        if not ok:
            failed += 1

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_main())
