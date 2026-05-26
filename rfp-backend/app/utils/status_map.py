"""
status_map.py
─────────────
Maps raw internal backend statuses to clean, user-facing display labels.
Never expose technical error names (RATE_LIMIT_ERROR, quota, etc.) to business users.
"""

# Internal status -> { display_label, display_class }
STATUS_MAP = {
    # Upload / Initial processing
    "uploaded":               {"label": "Uploaded",              "class": "blue"},
    "queued_for_processing":  {"label": "AI Analyzing",          "class": "blue-pulse"},
    "processing_summary":     {"label": "AI Analyzing",          "class": "blue-pulse"},
    "analyzing_structure":    {"label": "AI Analyzing",          "class": "blue-pulse"},
    "extracting_metrics":     {"label": "AI Analyzing",          "class": "blue-pulse"},
    "finalizing_insights":    {"label": "AI Analyzing",          "class": "blue-pulse"},

    # Analysis complete / awaiting PM
    "summary_generated":      {"label": "Ready for PM Review",   "class": "indigo"},
    "pending-review":         {"label": "Ready for PM Review",   "class": "indigo"},
    "under_review":           {"label": "Under PM Review",       "class": "amber"},
    "awaiting_ceo_decision":  {"label": "Needs PM Decision",     "class": "amber"},

    # PM decisions
    "approved":               {"label": "Approved by PM",        "class": "emerald"},
    "rejected":               {"label": "Rejected",              "class": "red"},
    "on-hold":                {"label": "On Hold",               "class": "gray"},
    "on_hold":                {"label": "On Hold",               "class": "gray"},

    # Assignment / Draft generation
    "assigned_to_sa":         {"label": "Assigned to Architect", "class": "indigo"},
    "in_drafting":            {"label": "Draft In Progress",     "class": "purple-pulse"},
    "generating_draft":       {"label": "Draft In Progress",     "class": "purple-pulse"},

    # Draft complete
    "ai_draft_ready":         {"label": "AI Draft Ready",        "class": "emerald"},
    "draft_complete":         {"label": "AI Draft Ready",        "class": "emerald"},
    "under_sa_review":        {"label": "Under SA Review",       "class": "amber"},
    "finalized":              {"label": "Final Output Ready",     "class": "emerald"},
    "submitted_for_review":   {"label": "Submitted for PM Review","class": "indigo"},
    "revision_requested":     {"label": "Revision Requested",    "class": "orange"},
    "final_approved":         {"label": "Final Approved ✓",       "class": "emerald"},

    # Error states — never show raw error to users
    "error":                  {"label": "Needs Attention",       "class": "rose"},
    "rate_limit_error":       {"label": "Generation Paused",     "class": "rose"},
    "quota_exceeded":         {"label": "Generation Paused",     "class": "rose"},
    "generation_paused":      {"label": "Generation Paused",     "class": "rose"},
    "failed":                 {"label": "Needs Attention",       "class": "rose"},
}

DEFAULT_STATUS = {"label": "Processing", "class": "gray"}


def map_status(internal_status: str) -> dict:
    """Return user-facing status dict for any internal status string."""
    if not internal_status:
        return DEFAULT_STATUS
    key = internal_status.lower().strip()
    return STATUS_MAP.get(key, DEFAULT_STATUS)


def get_display_label(internal_status: str, progress_pct: int = 0) -> str:
    # If 100% and internal status is still drafting, show Draft Ready
    if progress_pct >= 100 and internal_status in ["generating_draft", "in_drafting"]:
        return "AI Draft Ready"
    return map_status(internal_status)["label"]


def get_display_class(internal_status: str) -> str:
    return map_status(internal_status)["class"]
