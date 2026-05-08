"""Tests for tools/ga4.py — pure parsers only (no network)."""

from __future__ import annotations

from tools.ga4 import (
    PageTraffic,
    PropertyDetails,
    ReportResult,
    parse_pageviews_report,
    parse_property_details,
    parse_run_report,
    _slug_from_path,
    _to_int,
)


# ---------- parse_property_details ----------


def test_parse_property_details_handles_dict_response():
    raw = {
        "name": "properties/466054145",
        "displayName": "FirstMovers AI",
        "createTime": "2024-01-01T00:00:00Z",
        "industryCategory": "TECHNOLOGY",
        "timeZone": "America/Phoenix",
        "currencyCode": "USD",
        "account": "accounts/123",
    }
    p = parse_property_details(raw)
    assert isinstance(p, PropertyDetails)
    assert p.property_id == "466054145"
    assert p.display_name == "FirstMovers AI"
    assert p.time_zone == "America/Phoenix"


def test_parse_property_details_pulls_id_from_full_resource_name():
    raw = {"name": "properties/999"}
    p = parse_property_details(raw)
    assert p.property_id == "999"


# ---------- parse_run_report ----------


def test_parse_run_report_extracts_dimensions_and_metrics():
    raw = {
        "dimensionHeaders": [{"name": "pagePath"}],
        "metricHeaders": [{"name": "sessions"}, {"name": "screenPageViews"}],
        "rowCount": 2,
        "rows": [
            {
                "dimensionValues": [{"value": "/consulting/"}],
                "metricValues": [{"value": "800"}, {"value": "1200"}],
            },
            {
                "dimensionValues": [{"value": "/labs/"}],
                "metricValues": [{"value": "400"}, {"value": "600"}],
            },
        ],
    }
    report = parse_run_report(raw)
    assert isinstance(report, ReportResult)
    assert report.row_count == 2
    assert report.dimension_headers == ["pagePath"]
    assert report.metric_headers == ["sessions", "screenPageViews"]
    assert report.rows[0]["pagePath"] == "/consulting/"
    assert report.rows[0]["sessions"] == "800"
    assert report.rows[1]["pagePath"] == "/labs/"


def test_parse_run_report_handles_empty_response():
    raw = {"dimensionHeaders": [], "metricHeaders": [], "rows": []}
    report = parse_run_report(raw)
    assert report.row_count == 0
    assert report.rows == []


# ---------- parse_pageviews_report ----------


def test_parse_pageviews_extracts_slug_keyed_traffic():
    report = ReportResult(
        rows=[
            {"pagePath": "/consulting/", "sessions": "800",
             "screenPageViews": "1200", "engagedSessions": "600"},
            {"pagePath": "/labs/", "sessions": "400",
             "screenPageViews": "500", "engagedSessions": "300"},
        ],
        row_count=2,
        dimension_headers=["pagePath"],
        metric_headers=["sessions", "screenPageViews", "engagedSessions"],
    )
    out = parse_pageviews_report(report)
    assert "consulting" in out
    assert isinstance(out["consulting"], PageTraffic)
    assert out["consulting"].sessions == 800
    assert out["consulting"].screen_page_views == 1200
    assert out["labs"].sessions == 400


def test_parse_pageviews_skips_root_paths():
    report = ReportResult(
        rows=[
            {"pagePath": "/", "sessions": "1000",
             "screenPageViews": "1500", "engagedSessions": "800"},
            {"pagePath": "/consulting/", "sessions": "100",
             "screenPageViews": "150", "engagedSessions": "80"},
        ],
        row_count=2,
        dimension_headers=["pagePath"],
        metric_headers=["sessions", "screenPageViews", "engagedSessions"],
    )
    out = parse_pageviews_report(report)
    assert "consulting" in out
    assert "" not in out


# ---------- helpers ----------


def test_slug_from_path():
    assert _slug_from_path("/consulting/") == "consulting"
    assert _slug_from_path("/blog/agentic-ai") == "agentic-ai"
    assert _slug_from_path("/blog/agentic-ai/") == "agentic-ai"
    assert _slug_from_path("/") == ""
    assert _slug_from_path("") == ""


def test_to_int():
    assert _to_int("123") == 123
    assert _to_int(123) == 123
    assert _to_int("") == 0
    assert _to_int(None) == 0
    assert _to_int("not a number") == 0
