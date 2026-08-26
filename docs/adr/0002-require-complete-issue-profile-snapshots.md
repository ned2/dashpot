---
status: accepted
---

# Require complete Issue profile snapshots

Dashpot Issue adapters must produce a complete versioned Issue profile or fail
the source refresh with a diagnostic. `null` and empty collections mean known
absence; they never mean unsupported, not fetched, permission denied, or
malformed. This rejects more partial data at the adapter seam, but prevents
uncertainty from spreading through every Project, correlation, JSON, and UI
caller and prevents partially fetched Issues from masquerading as valid source
deletions.

Semantic equivalence canonicalizes set-like collections and excludes only
source provenance and actionable location. A different reference, Project,
lifecycle fact, or profile version remains an observable Issue change.
