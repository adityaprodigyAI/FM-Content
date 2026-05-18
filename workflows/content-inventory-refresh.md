# Inventory refresh

> **Goal.** Rebuild `data/inventory/firstmovers-ai.json` so the cannibalization gate has accurate published-content data to compare against. Run weekly, or any time `python -m tools.inventory_refresh --check` returns non-zero.

> **Why this matters.** A degraded snapshot (missing `focus_keyword` or `organic_keywords`) silently breaks the cannibalization gate. The gate refuses to run on degraded data — but only if the snapshot is FRESHLY built. The W20 bug originated here.

---

## Step-by-step

### 1. Pull ALL WordPress published BLOG posts (every category, all pages)

The cannibalization gate must compare against EVERY published post — a post in
any category can own a focus keyword a new draft would collide with. Pull every
published post, with NO category filter, paginating until you have them all
(`per_page` maxes at 100; the live site has ~260 posts = ~3 pages):

```
# Repeat for page = 1, 2, 3, ... until a page returns fewer than per_page rows.
mcp__first-movers-wordpress__wp_posts_search(
  per_page=100,
  page=<1, then 2, 3, ...>,
  status="publish",
  _fields="id,slug,title,link,date,categories"
)
```

Concatenate every page into `wp_posts`.

> **Do NOT filter by category.** The old `categories="10,13,14,27,28,29,30"`
> filter (the categories new drafts use) silently dropped ~58 published posts in
> other categories — e.g. post 34171 `resource-based-economy` (category 11) —
> which caused the cannibalization gate to false-clear topics those posts
> already own. The gate needs the whole site.

### 2. Pull WordPress published PAGES

```
mcp__first-movers-wordpress__wp_pages_search(
  per_page=100,
  status="publish",
  _fields="id,slug,title,link,date"
)
```

Save the response as `wp_pages`.

**This is the W20 fix at the inventory layer.** Pages slipped past the v5 gate because they weren't in the snapshot. Always include them.

### 3. Pull Rank Math focus keyword PER post + page

For every id in `wp_posts + wp_pages`:

```
mcp__first-movers-wordpress__wp_get_post(id=<id>, meta=true)
```

Build a dict `rank_math_meta_by_id = {id: response, ...}`.

> If a post has no Rank Math focus keyword set in WP, the inventory builder falls back to a slug-derived sentinel ("agentic-ai-explained" -> "agentic ai explained") so the completeness check still passes. The slug-derived focus_kw is generally fine for the cannibalization gate's exact-match rule.

### 4. Pull Ahrefs organic keywords PER blog URL

For each blog (NOT each page) URL:

```
mcp__ahrefs__site-explorer-organic-keywords(
  target=<full url, e.g. https://firstmovers.ai/ai-inbox-automation/>,
  limit=10,
  order_by="organic_traffic:desc",
  country="us"
)
```

Build a dict `ahrefs_organic_by_url = {<url>: response, ...}`.

Pages are exempt — Ahrefs rarely tracks Tier-1 landing pages by keyword traffic the same way. The inventory completeness check accepts pages with empty `organic_keywords`.

### 5. Save the bundle and run the refresh

```python
import json, subprocess
bundle = {
    "wp_posts": wp_posts,
    "wp_pages": wp_pages,
    "rank_math_meta_by_id": rank_math_meta_by_id,
    "ahrefs_organic_by_url": ahrefs_organic_by_url,
}

# Pipe the bundle into the CLI:
proc = subprocess.run(
    ["python", "-m", "tools.inventory_refresh", "--from-stdin"],
    input=json.dumps(bundle),
    text=True,
    capture_output=True,
    check=False,
)
print(proc.stdout)
print(proc.stderr, file=__import__("sys").stderr)
assert proc.returncode == 0, "inventory refresh failed"
```

The refresh CLI:
- Parses the four payloads
- Joins everything by id and URL
- Asserts `inventory.assert_complete()` — refuses to save if any post has missing fields
- Atomically writes `data/inventory/firstmovers-ai.json`

### 6. Verify

```bash
python -m tools.inventory_refresh --check
# expected: "inventory: fresh (data/inventory/firstmovers-ai.json)"
```

Then commit the snapshot:

```bash
git add data/inventory/firstmovers-ai.json
git commit -m "chore(content): refresh inventory snapshot"
```

---

## Failure modes

- **`DegradedInventoryError` on save.** Some posts have `focus_keyword=None` AND `organic_keywords=[]`. Either Rank Math wasn't queried for those ids, or Ahrefs returned empty for those URLs. Re-run steps 3 and 4 for the failing ids.
- **Ahrefs API quota exhausted.** Skip step 4 with `ahrefs_organic_by_url = {}`. The build will still pass for pages but blogs will fail the completeness check. Wait until quota resets, then re-run.
- **WordPress search returns fewer than expected posts.** Check `per_page` (max 100). For >100 posts, paginate with `page=2,3,...` and concatenate.
