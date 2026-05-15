"""ga4 — direct GA4 Data + Admin API wrapper, bypassing analytics-mcp.

The analytics-mcp server hangs indefinitely on tools/call (verified
2026-04-27 via direct stdio JSON-RPC test, and again 2026-05-08 from
FM-Content where get_account_summaries ran for 49 minutes before being
cancelled). This module replaces the MCP entirely by calling the
google-analytics-data + google-analytics-admin SDKs directly.

ADC creds: $GOOGLE_APPLICATION_CREDENTIALS, default
~/AppData/Roaming/gcloud/application_default_credentials.json on Windows.

Refresh with:

    gcloud auth application-default login \\
        --client-id-file=config/ga-oauth-client.json \\
        --scopes=openid,https://www.googleapis.com/auth/userinfo.email,\\
                 https://www.googleapis.com/auth/cloud-platform,\\
                 https://www.googleapis.com/auth/analytics.readonly

Or use a service account JSON:

    set GOOGLE_APPLICATION_CREDENTIALS=C:\\path\\to\\service-account.json

Pure parsers + thin wrappers. Importing this module is free of network
side effects (clients are lazily imported).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

# Property ID — sourced from client_config.toml via identities.
# The constant name is kept stable for existing importers.
from .identities import GA4_PROPERTY_ID as FIRSTMOVERS_GA4_PROPERTY_ID


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PropertyDetails:
    property_id: str
    display_name: str
    create_time: str
    industry_category: str
    time_zone: str
    currency_code: str
    account: str


@dataclass(frozen=True)
class PageTraffic:
    page_path: str
    sessions: int
    screen_page_views: int
    engaged_sessions: int


@dataclass(frozen=True)
class ReportResult:
    rows: list[dict[str, Any]]
    row_count: int
    dimension_headers: list[str]
    metric_headers: list[str]


# ---------------------------------------------------------------------------
# Pure parsers (testable without network)
# ---------------------------------------------------------------------------


def parse_property_details(raw: Any) -> PropertyDetails:
    g = _getter(raw)
    name = str(g("name") or "")
    return PropertyDetails(
        property_id=name.split("/")[-1] if "/" in name else name,
        display_name=str(g("display_name") or g("displayName") or ""),
        create_time=str(g("create_time") or g("createTime") or ""),
        industry_category=str(g("industry_category") or g("industryCategory") or ""),
        time_zone=str(g("time_zone") or g("timeZone") or ""),
        currency_code=str(g("currency_code") or g("currencyCode") or ""),
        account=str(g("account") or ""),
    )


def parse_run_report(raw: Any) -> ReportResult:
    g = _getter(raw)
    dim_headers_raw = _unwrap_list(g("dimension_headers") or g("dimensionHeaders") or [])
    metric_headers_raw = _unwrap_list(g("metric_headers") or g("metricHeaders") or [])
    row_count = int(g("row_count") or g("rowCount") or 0)

    dim_names = [str(_getter(h)("name") or "") for h in dim_headers_raw]
    metric_names = [str(_getter(h)("name") or "") for h in metric_headers_raw]

    parsed_rows: list[dict[str, Any]] = []
    for row in _unwrap_list(g("rows") or []):
        rg = _getter(row)
        dim_values = [
            str(_getter(v)("value") or "")
            for v in _unwrap_list(rg("dimension_values") or rg("dimensionValues") or [])
        ]
        metric_values = [
            str(_getter(v)("value") or "")
            for v in _unwrap_list(rg("metric_values") or rg("metricValues") or [])
        ]
        parsed_rows.append(
            {
                **{name: val for name, val in zip(dim_names, dim_values)},
                **{name: val for name, val in zip(metric_names, metric_values)},
            }
        )

    return ReportResult(
        rows=parsed_rows,
        row_count=row_count or len(parsed_rows),
        dimension_headers=dim_names,
        metric_headers=metric_names,
    )


def parse_pageviews_report(report: ReportResult) -> dict[str, PageTraffic]:
    out: dict[str, PageTraffic] = {}
    for row in report.rows:
        path = (row.get("pagePath") or "").strip()
        if not path:
            continue
        slug = _slug_from_path(path)
        if not slug:
            continue
        out[slug] = PageTraffic(
            page_path=path,
            sessions=_to_int(row.get("sessions")),
            screen_page_views=_to_int(row.get("screenPageViews")),
            engaged_sessions=_to_int(row.get("engagedSessions")),
        )
    return out


# ---------------------------------------------------------------------------
# Thin client wrappers (the entry points to use in pipeline code)
# ---------------------------------------------------------------------------


def _admin_client():
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
    return AnalyticsAdminServiceClient()


def _data_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    return BetaAnalyticsDataClient()


def fetch_property_details(
    property_id: str = FIRSTMOVERS_GA4_PROPERTY_ID,
) -> PropertyDetails:
    client = _admin_client()
    raw = client.get_property(name=f"properties/{property_id}")
    return parse_property_details(raw)


def run_report(
    *,
    property_id: str = FIRSTMOVERS_GA4_PROPERTY_ID,
    dimensions: list[str],
    metrics: list[str],
    days: int = 28,
    end_date: date | None = None,
    limit: int = 10_000,
) -> ReportResult:
    """Run a GA4 Data API report. Date range = last `days` ending today (UTC)."""
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Metric,
        RunReportRequest,
    )
    end = end_date or date.today()
    start = end - timedelta(days=days)
    client = _data_client()
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        date_ranges=[DateRange(start_date=start.isoformat(), end_date=end.isoformat())],
        limit=limit,
    )
    raw = client.run_report(request=request)
    return parse_run_report(raw)


def fetch_pageviews_by_path(
    property_id: str = FIRSTMOVERS_GA4_PROPERTY_ID,
    days: int = 28,
    limit: int = 10_000,
) -> dict[str, PageTraffic]:
    report = run_report(
        property_id=property_id,
        dimensions=["pagePath"],
        metrics=["sessions", "screenPageViews", "engagedSessions"],
        days=days,
        limit=limit,
    )
    return parse_pageviews_report(report)


def fetch_high_traffic_with_growth(
    *,
    property_id: str = FIRSTMOVERS_GA4_PROPERTY_ID,
    window_days: int = 28,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Top pages by sessions with prior-period delta — feeds ga4_gap discovery.

    Runs two GA4 reports (current `window_days` + prior `window_days`) and
    merges by pagePath. Returns rows shaped for `tools.discover.ga4_gap.discover`:

        [{"pagePath": "/x/", "sessions": 500, "prior_sessions": 200}, ...]
    """
    end = date.today()
    cur_start = end - timedelta(days=window_days)
    prev_end = cur_start
    prev_start = prev_end - timedelta(days=window_days)

    cur = run_report(
        property_id=property_id,
        dimensions=["pagePath"],
        metrics=["sessions"],
        days=window_days,
        end_date=end,
        limit=limit,
    )
    prev = run_report(
        property_id=property_id,
        dimensions=["pagePath"],
        metrics=["sessions"],
        days=window_days,
        end_date=prev_end,
        limit=limit,
    )
    prev_by_path = {row.get("pagePath"): _to_int(row.get("sessions")) for row in prev.rows}

    out: list[dict[str, Any]] = []
    for row in cur.rows:
        path = row.get("pagePath") or ""
        if not path:
            continue
        out.append(
            {
                "pagePath": path,
                "sessions": _to_int(row.get("sessions")),
                "prior_sessions": prev_by_path.get(path, 0),
            }
        )
    return out


# ---------------------------------------------------------------------------
# CLI — `python -m tools.ga4 --check`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    """Verify ADC credentials work against the FM GA4 property.

    Usage:
        python -m tools.ga4 --check          # auth + property details only
        python -m tools.ga4 --top-pages      # also pull top 20 pages by sessions
    """
    import argparse

    parser = argparse.ArgumentParser(prog="tools.ga4")
    parser.add_argument("--property-id", default=FIRSTMOVERS_GA4_PROPERTY_ID)
    parser.add_argument("--check", action="store_true",
                        help="Verify auth + read property details")
    parser.add_argument("--top-pages", action="store_true",
                        help="Pull top 20 pages by sessions over last 28d")
    parser.add_argument("--high-traffic", action="store_true",
                        help="Pull top-50 with current + prior period for ga4_gap discovery")
    args = parser.parse_args(argv)

    if not (args.check or args.top_pages or args.high_traffic):
        parser.print_help()
        return 0

    try:
        details = fetch_property_details(args.property_id)
    except Exception as e:  # noqa: BLE001
        print(f"AUTH FAIL ({type(e).__name__}): {e}")
        print()
        print("Set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON, or run:")
        print("  gcloud auth application-default login \\")
        print("    --scopes=openid,https://www.googleapis.com/auth/userinfo.email,\\")
        print("             https://www.googleapis.com/auth/analytics.readonly")
        return 2

    print(f"AUTH OK")
    print(f"  property_id      : {details.property_id}")
    print(f"  display_name     : {details.display_name}")
    print(f"  industry_category: {details.industry_category}")
    print(f"  time_zone        : {details.time_zone}")
    print(f"  currency_code    : {details.currency_code}")

    if args.top_pages:
        print()
        print("Top 20 pages by sessions (last 28d):")
        traffic = fetch_pageviews_by_path(args.property_id, days=28, limit=20)
        rows = sorted(traffic.values(), key=lambda t: -t.sessions)
        for t in rows[:20]:
            print(f"  {t.sessions:6d}  {t.page_path}")

    if args.high_traffic:
        print()
        print("Top 50 pages with prior-period sessions (for ga4_gap discovery):")
        rows = fetch_high_traffic_with_growth(
            property_id=args.property_id, window_days=28, limit=50,
        )
        rows.sort(key=lambda r: -r["sessions"])
        for r in rows[:20]:
            growth = (r["sessions"] / r["prior_sessions"]) if r["prior_sessions"] else float("inf")
            growth_str = f"{growth:5.2f}x" if growth != float("inf") else "  new"
            print(f"  {r['sessions']:5d}  ({r['prior_sessions']:5d} prior, {growth_str})  {r['pagePath']}")

    return 0


# ---------------------------------------------------------------------------
# Helpers (proto-or-dict accessors)
# ---------------------------------------------------------------------------


def _getter(obj: Any):
    """Return a callable that fetches a key/attr from obj, dict-or-proto agnostic."""
    if isinstance(obj, dict):
        return lambda k: obj.get(k)
    def _attr(k: str) -> Any:
        return getattr(obj, k, None)
    return _attr


def _unwrap_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return list(value)
    except TypeError:
        return []


def _to_int(v: Any) -> int:
    if v is None or v == "":
        return 0
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def _slug_from_path(path: str) -> str:
    cleaned = path.strip().rstrip("/").lower()
    if cleaned in ("", "/"):
        return ""
    if "/" not in cleaned:
        return cleaned
    return cleaned.rsplit("/", 1)[-1]


if __name__ == "__main__":
    raise SystemExit(_main())
