"""ahrefs — direct Ahrefs API v3 wrapper, bypassing the MCP layer.

Used by remote `/schedule` routines that don't have the local Ahrefs MCP
available. Mirrors the pattern in `tools/ga4.py`: pure parsers, lazy
network calls, single env-var auth.

The local Ahrefs MCP and the v3 REST API return the same response shape
(keys / keywords / positions arrays). The discovery extractors in
`tools/discover/ahrefs_gap.py` and prose pipeline in
`tools/draft.py` accept both without changes.

Auth: bearer token in `Authorization` header. Set the AHREFS_API_TOKEN
env var, or pass api_token= to each fetch function. Generate the token
in your Ahrefs dashboard at https://ahrefs.com/api/profile.

Endpoints used:
  - GET /v3/site-explorer/organic-keywords  (competitor-gap discovery + inventory join)
  - GET /v3/serp-overview                   (prose-generation SERP intent)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from typing import Any, Final
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AHREFS_API_BASE: Final[str] = "https://api.ahrefs.com/v3"
AHREFS_API_TOKEN_ENV: Final[str] = "AHREFS_API_TOKEN"
DEFAULT_TIMEOUT_SECONDS: Final[int] = 30


# ---------------------------------------------------------------------------
# Public fetch functions — match the MCP response shape so callers are
# drop-in compatible with discover/ahrefs_gap and the SERP step in draft
# ---------------------------------------------------------------------------


def fetch_organic_keywords(
    target: str,
    *,
    date_str: str | None = None,
    select: str = "keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty",
    mode: str = "subdomains",
    limit: int = 100,
    order_by: str = "sum_traffic:desc",
    country: str | None = None,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fetch organic-keywords for a domain or URL.

    Returns a dict with a `keywords` array. Each row matches the MCP shape:
      {keyword, best_position, best_position_url, sum_traffic, volume,
       keyword_difficulty}

    Use this for:
      - competitor-gap discovery (target=competitor.com, mode=subdomains)
      - inventory joins (target=full URL, limit=10 per URL)
    """
    params: dict[str, Any] = {
        "target": target,
        "date": date_str or date.today().isoformat(),
        "select": select,
        "mode": mode,
        "limit": limit,
        "order_by": order_by,
        "output": "json",
        "protocol": "both",
    }
    if country:
        params["country"] = country
    return _get(
        "/site-explorer/organic-keywords",
        params,
        api_token=api_token,
        timeout=timeout,
    )


def fetch_serp_overview(
    keyword: str,
    *,
    country: str = "us",
    select: str = "title,url,position,domain_rating,backlinks,traffic,top_keyword",
    top_positions: int = 10,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fetch SERP overview for a keyword.

    Returns a dict with a `positions` array. Each row:
      {title, url, position, domain_rating, backlinks, traffic, top_keyword}

    Used in prose generation to inform the model about competing pages.
    """
    params = {
        "keyword": keyword,
        "country": country,
        "select": select,
        "top_positions": top_positions,
        "output": "json",
    }
    return _get(
        "/serp-overview",
        params,
        api_token=api_token,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _get_token(api_token: str | None = None) -> str:
    if api_token:
        return api_token
    token = os.environ.get(AHREFS_API_TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"Ahrefs API token not set. Pass api_token=, or set ${AHREFS_API_TOKEN_ENV}. "
            f"Generate one at https://ahrefs.com/api/profile."
        )
    return token


def _get(
    path: str,
    params: dict[str, Any],
    *,
    api_token: str | None,
    timeout: int,
) -> dict[str, Any]:
    token = _get_token(api_token)
    url = AHREFS_API_BASE + path + "?" + urlencode(params)
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "fm-content/0.1 (+ahrefs-bypass)",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known host
            text = resp.read().decode("utf-8")
            return json.loads(text)
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"Ahrefs API HTTP {e.code} {e.reason}: {body}"
        ) from e
    except URLError as e:
        raise RuntimeError(f"Ahrefs API network error: {e}") from e


# ---------------------------------------------------------------------------
# CLI — `python -m tools.ahrefs {check|organic-keywords|serp}`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.ahrefs",
        description="Direct Ahrefs API v3 wrapper (bypasses the MCP layer).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "check",
        help="Verify auth by hitting the cheapest endpoint with a known target",
    )

    kw = sub.add_parser(
        "organic-keywords",
        help="Pull organic keywords for a domain or URL",
    )
    kw.add_argument("--target", required=True,
                    help="Domain (e.g. mckinsey.com) or full URL")
    kw.add_argument("--date", default=date.today().isoformat(),
                    help="YYYY-MM-DD (default: today)")
    kw.add_argument("--mode", default="subdomains",
                    choices=("subdomains", "domain", "exact"))
    kw.add_argument("--limit", type=int, default=100)
    kw.add_argument("--country", default=None)

    serp = sub.add_parser("serp", help="SERP overview for a keyword")
    serp.add_argument("--keyword", required=True)
    serp.add_argument("--country", default="us")
    serp.add_argument("--top-positions", type=int, default=10)

    args = parser.parse_args(argv)

    try:
        if args.cmd == "check":
            # Cheapest possible call — 1 keyword for our own domain
            result = fetch_organic_keywords(
                "firstmovers.ai", limit=1, mode="subdomains",
            )
            n = len(result.get("keywords", []))
            print(f"AUTH OK ({n} keyword returned for firstmovers.ai sanity check)")
            return 0

        if args.cmd == "organic-keywords":
            result = fetch_organic_keywords(
                args.target,
                date_str=args.date,
                mode=args.mode,
                limit=args.limit,
                country=args.country,
            )
        else:  # serp
            result = fetch_serp_overview(
                args.keyword,
                country=args.country,
                top_positions=args.top_positions,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
