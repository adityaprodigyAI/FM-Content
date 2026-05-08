"""inventory_refresh — CLI that rebuilds the inventory snapshot from MCPs.

This module is intentionally MCP-shaped: each rebuild step is its own
function the agent calls with a raw MCP response. Run as a CLI to see
exactly what to gather, or call from a Claude session that pipes MCP
responses straight in.

Usage (agent loop):

    python -m tools.inventory_refresh --check       # exit 0/1/2 freshness
    python -m tools.inventory_refresh --plan        # print the MCP calls to make
    python -m tools.inventory_refresh --from-stdin  # read raw MCP payloads + write snapshot

The --from-stdin flow expects a single JSON document with the schema:

    {
      "wp_posts": [...wp_posts_search response...],
      "wp_pages": [...wp_pages_search response...],
      "rank_math_meta_by_id": {"<post_id>": {... wp_get_post(meta=true) response ...}, ...},
      "ahrefs_organic_by_url": {"<url>": {... ahrefs organic-keywords response ...}, ...}
    }

Why this shape: Claude (running as the cron agent) is the one with MCP
permissions. It collects the raw payloads, drops them in this dict, and
hands the bundle to this CLI which deterministically builds + saves the
snapshot. The dataflow is reproducible: anyone can rebuild from the same
raw bundle.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .inventory import (
    DegradedInventoryError,
    INVENTORY_PATH,
    StaleInventoryError,
    attach_ahrefs_organic_keywords,
    attach_rank_math_focus_keywords,
    build_inventory,
    load,
    merge,
    parse_wp_posts,
    save,
)


# ---------------------------------------------------------------------------
# Plan — what the agent must collect before it can run --from-stdin
# ---------------------------------------------------------------------------


PLAN_TEMPLATE = """\
Inventory refresh plan
======================

To rebuild data/inventory/firstmovers-ai.json, the agent must collect:

1. WordPress published BLOG posts (categories 10, 13, 14, 27, 28, 29, 30):
     mcp__first-movers-wordpress__wp_posts_search
       per_page=100
       status=publish
       _fields=id,slug,title,link,date,categories
     -> bundle["wp_posts"]

2. WordPress published PAGES (Tier-1 landing pages + everything in /pages/):
     mcp__first-movers-wordpress__wp_pages_search
       per_page=100
       status=publish
       _fields=id,slug,title,link,date
     -> bundle["wp_pages"]

   (THIS WAS THE W20 BUG ORIGIN — pages MUST be collected, otherwise
   resources like /resource-based-economy/ slip past the cannibalization gate.)

3. Rank Math focus keyword PER POST/PAGE, via:
     mcp__first-movers-wordpress__wp_get_post  (with meta=true)
   For each id in (wp_posts + wp_pages), record the response under:
     bundle["rank_math_meta_by_id"]["<id>"] = <response>

4. Ahrefs organic keywords PER URL (top 10 by traffic), via:
     mcp__ahrefs__site-explorer-organic-keywords
       target=<url>
       limit=10
       order_by=organic_traffic:desc
   For each blog URL, record the response under:
     bundle["ahrefs_organic_by_url"]["<url>"] = <response>

   Pages are exempt — Ahrefs rarely tracks Tier-1 landing pages by keyword
   traffic the same way, and the cannibalization gate's completeness check
   accepts pages with no organic_keywords.

Then assemble the bundle JSON and pipe to:
     python -m tools.inventory_refresh --from-stdin
"""


# ---------------------------------------------------------------------------
# Public refresh function (callable from a script or test)
# ---------------------------------------------------------------------------


def refresh_from_bundle(bundle: dict[str, Any], path: Path = INVENTORY_PATH) -> Path:
    """Rebuild and save the snapshot from a bundle of raw MCP responses."""
    blogs = parse_wp_posts(bundle.get("wp_posts", []), kind="blog")
    pages = parse_wp_posts(bundle.get("wp_pages", []), kind="page")
    posts = merge(blogs, pages)

    rank_math_meta_by_id_raw = bundle.get("rank_math_meta_by_id", {}) or {}
    rank_math_meta_by_id = {int(k): v for k, v in rank_math_meta_by_id_raw.items()}
    posts = attach_rank_math_focus_keywords(posts, rank_math_meta_by_id)

    ahrefs_by_url = bundle.get("ahrefs_organic_by_url", {}) or {}
    posts = attach_ahrefs_organic_keywords(posts, ahrefs_by_url, top_n=10)

    inventory = build_inventory(posts)

    # Validate loud BEFORE persisting — if the bundle is degraded, refuse to
    # save (otherwise the next slate run loads a known-bad snapshot and the
    # gate refuses to run anyway, but with worse error attribution).
    inventory.assert_complete()

    return save(inventory, path)


# ---------------------------------------------------------------------------
# Freshness check (returns process exit code)
# ---------------------------------------------------------------------------


def freshness_check(path: Path = INVENTORY_PATH, max_age_days: int = 7) -> int:
    """0 = fresh; 1 = stale; 2 = missing or corrupt."""
    try:
        inventory = load(path)
    except FileNotFoundError:
        return 2
    except (OSError, json.JSONDecodeError, ValueError):
        return 2
    try:
        inventory.assert_fresh(max_age_days=max_age_days)
    except StaleInventoryError:
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.inventory_refresh")
    parser.add_argument("--check", action="store_true",
                        help="Exit 0=fresh, 1=stale (>7d), 2=missing")
    parser.add_argument("--plan", action="store_true",
                        help="Print the MCP collection plan and exit")
    parser.add_argument("--from-stdin", action="store_true",
                        help="Read raw MCP bundle JSON from stdin, save snapshot")
    parser.add_argument("--path", default=str(INVENTORY_PATH),
                        help="Snapshot path (default: data/inventory/firstmovers-ai.json)")
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args(argv)

    path = Path(args.path)

    if args.plan:
        print(PLAN_TEMPLATE)
        return 0

    if args.check:
        code = freshness_check(path, max_age_days=args.max_age_days)
        msg = {0: "fresh", 1: "stale", 2: "missing"}[code]
        print(f"inventory: {msg} ({path})")
        return code

    if args.from_stdin:
        try:
            bundle = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"error: stdin is not valid JSON: {e}", file=sys.stderr)
            return 2
        try:
            written = refresh_from_bundle(bundle, path)
        except DegradedInventoryError as e:
            print(f"error: refusing to save degraded snapshot:\n{e}", file=sys.stderr)
            return 3
        print(f"wrote {written}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
