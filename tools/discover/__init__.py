"""discover — turns raw MCP responses into Candidate records.

Five sources today:
  - gsc_striking_distance      tools/discover/gsc.py
  - ahrefs_competitor_gap      tools/discover/ahrefs_gap.py
  - searchable_prompt          tools/discover/searchable_aeo.py
  - ga4_high_traffic_gap       tools/discover/ga4_gap.py

Every Candidate carries mandatory provenance (discovery_source +
discovery_id + discovery_evidence). The W19 bug pattern (agent improvising
candidates from general SEO knowledge) is structurally impossible because
no candidate exists outside an extractor in this package.

Pure parsing — zero I/O. The agent makes the MCP calls; this package
consumes responses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final, Literal

DiscoverySource = Literal[
    "gsc_striking_distance",
    "ahrefs_competitor_gap",
    "searchable_prompt",
    "searchable_competitor_topic",
    "ga4_high_traffic_gap",
]

Audience = Literal["done-for-you", "diy"]
Intent = Literal["transactional", "commercial", "informational", "navigational"]

# Score weights — multipliers applied to raw signal strength. Calibrated
# against post-publish performance: striking-distance and competitor-gap
# convert at higher rates than AEO prompts, but AEO drives Searchable
# visibility growth which compounds over months.
SOURCE_WEIGHTS: Final[dict[DiscoverySource, float]] = {
    "gsc_striking_distance": 1.4,
    "ahrefs_competitor_gap": 1.2,
    "searchable_prompt": 1.0,
    "searchable_competitor_topic": 1.0,
    "ga4_high_traffic_gap": 1.1,
}


@dataclass(frozen=True)
class Candidate:
    """A topic candidate WITH mandatory provenance.

    No Candidate exists without (discovery_source, discovery_id,
    discovery_evidence). validate_and_emit asserts this on every brief.
    """

    focus_keyword: str
    suggested_title_seed: str
    audience: Audience
    category_id: int
    intent: Intent
    score: float
    rationale: str
    discovery_source: DiscoverySource
    discovery_id: str
    discovery_evidence: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "Audience",
    "Candidate",
    "DiscoverySource",
    "Intent",
    "SOURCE_WEIGHTS",
]
