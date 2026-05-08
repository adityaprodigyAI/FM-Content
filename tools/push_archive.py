"""push_archive — CLI for the GitHub Actions Path B WAF unblock.

Reads every JSON file in `data/runs/_pending-push/` whose `wp_post_id` is
null, pushes each via WP REST POST with HTTP basic auth (using
FM_WP_USER + FM_WP_APP_PASSWORD env vars), and writes the resulting
`wp_post_id` back to the file. Idempotent — re-running the same workflow
skips already-pushed drafts.

Usage:

    python -m tools.push_archive --apply
    python -m tools.push_archive --apply --dir data/runs/_pending-push
    python -m tools.push_archive --verify-auth   # GET /users/me to confirm creds

The expected GH Actions workflow flow:

    1. Trigger on push to `data/runs/_pending-push/*.json` (or workflow_dispatch).
    2. Set FM_WP_USER + FM_WP_APP_PASSWORD from repo secrets.
    3. Run `python -m tools.push_archive --apply`.
    4. Commit the modified JSON files with `[skip ci]` in the message.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .identities import SITE_BASE_URL
from .push_wp import (
    PENDING_PUSH_DIR,
    list_pending_pushes,
    push_via_app_password,
)


def _verify_auth(*, user: str, app_password: str,
                 site_base_url: str = SITE_BASE_URL,
                 timeout: int = 15) -> int:
    """Hit /wp-json/wp/v2/users/me with basic auth. Returns process exit code.

    0 = auth OK, prints user id + slug + roles
    2 = auth failed (HTTP 401/403), prints body
    3 = network or other error
    """
    pair = base64.b64encode(f"{user}:{app_password}".encode("utf-8")).decode("ascii")
    url = site_base_url.rstrip("/") + "/wp-json/wp/v2/users/me?context=edit"
    req = Request(
        url,
        headers={
            "Authorization": "Basic " + pair,
            "User-Agent": "fm-content/0.1 (+verify-auth)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known host
            text = resp.read().decode("utf-8")
            data = json.loads(text)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")[:600]
        except Exception:  # noqa: BLE001
            pass
        print(f"AUTH FAIL: HTTP {e.code} {e.reason}", file=sys.stderr)
        if body:
            print(body, file=sys.stderr)
        return 2
    except URLError as e:
        print(f"NETWORK ERROR: {e}", file=sys.stderr)
        return 3
    except json.JSONDecodeError as e:
        print(f"PARSE ERROR: {e}", file=sys.stderr)
        return 3

    pid = data.get("id")
    slug = data.get("slug")
    name = data.get("name")
    roles = data.get("roles") or []
    print(f"AUTH OK")
    print(f"  user id : {pid}")
    print(f"  slug    : {slug}")
    print(f"  name    : {name}")
    print(f"  roles   : {', '.join(roles)}")
    if pid != 3:
        print(f"  note    : you authenticated as user {pid}, NOT Josh (3).")
        print("            Set FM_WP_AUTHOR_ID=3 to force Josh as the post author.")
    else:
        print(f"  note    : authenticated as Josh McCoy (id 3) — no override needed.")
    return 0


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
    parser.add_argument("--verify-auth", action="store_true",
                        help="GET /wp-json/wp/v2/users/me to confirm WP App Password auth")
    parser.add_argument("--dir", default=str(PENDING_PUSH_DIR),
                        help="Pending-push dir (default: data/runs/_pending-push)")
    args = parser.parse_args(argv)

    if args.verify_auth:
        user = os.environ.get("FM_WP_USER")
        pwd = os.environ.get("FM_WP_APP_PASSWORD")
        if not user or not pwd:
            print("ERROR: FM_WP_USER and FM_WP_APP_PASSWORD must be set in env",
                  file=sys.stderr)
            return 2
        return _verify_auth(user=user, app_password=pwd)

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
