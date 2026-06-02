"""One-shot helper for the polling-drafter MCP run.

Reads a JSON bundle from stdin (or arg path) with the shape:

    {
        "clickup_task_id": "...",
        "seo_title": "...",
        "meta_description": "...",
        "body_html": "...",
        "faq_items": [{"question": "...", "answer": "..."}, ...]
    }

Looks up the DailyState, runs prepare_brief + assemble + validate, writes the
assembled draft to data/runs/_drafts/<target_date>.json, then prints the
assembled payload (title, seo_title, meta_description, body_html, slug,
category_id) as JSON so the MCP-side wp_create_post call can use it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.daily import pending_drafts
from tools.draft import assemble, prepare_brief
from tools.inventory import load as load_inventory
from tools.rubric import FaqItem
from tools.slate import SlateProposal


def main() -> int:
    if len(sys.argv) < 2:
        bundle = json.load(sys.stdin)
    else:
        bundle = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    target_id = bundle["clickup_task_id"]
    state = next(
        (s for s in pending_drafts() if s.clickup_task_id == target_id), None
    )
    if state is None:
        print(f"error: no pending draft for clickup_task_id={target_id!r}",
              file=sys.stderr)
        return 2

    prop = SlateProposal(**state.proposal)
    inv = load_inventory()
    brief = prepare_brief(prop, inv)

    faq_items = [FaqItem(**f) for f in bundle["faq_items"]]
    assembled = assemble(
        brief,
        body_html=bundle["body_html"],
        faq_items=faq_items,
        seo_title=bundle["seo_title"],
        meta_description=bundle["meta_description"],
    )

    out = {
        "title": assembled.title,
        "seo_title": assembled.seo_title,
        "meta_description": assembled.meta_description,
        "focus_keyword": assembled.focus_keyword,
        "slug": assembled.slug,
        "category_id": assembled.category_id,
        "audience": assembled.audience,
        "excerpt": assembled.excerpt,
        "body_html": assembled.body_html,
        "word_count": len(assembled.body_html.split()),
        "faq_items": [{"question": f.question, "answer": f.answer}
                      for f in assembled.faq_items],
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
