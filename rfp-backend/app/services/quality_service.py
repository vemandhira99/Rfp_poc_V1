"""
quality_service.py
──────────────────
Runs quality checks on generated RFP proposal drafts before marking as ready.
Returns a structured quality_status JSON that the SA workspace displays.
"""
import json
import re
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.rfp import RFPDocument, RFPDraft, RFPRequirement

# Known placeholder patterns to flag
PLACEHOLDER_PATTERNS = [
    r'\[Your Company Name\]',
    r'\[Company Name\]',
    r'\[Insert Name\]',
    r'\[Company Address\]',
    r'\[Date\]',
    r'\[Name\]',
    r'\[Contact\]',
    r'\[Your Name\]',
    r'\[Signatory\]',
    r'\[TBD\]',
    r'\[XX\]',
    r'\[placeholder\]',
]

PLACEHOLDER_RE = re.compile('|'.join(PLACEHOLDER_PATTERNS), re.IGNORECASE)

# Broken / corrupted character patterns
BROKEN_CHAR_PATTERNS = [
    r'â€™',   # smart quote corruption
    r'â€œ',   # smart quote corruption
    r'Ã¢',    # encoding artifact
    r'\\u[0-9a-f]{4}',  # raw unicode escapes in text
    r'\x00',  # null bytes
]
BROKEN_RE = re.compile('|'.join(BROKEN_CHAR_PATTERNS))


def run_quality_check(db: Session, rfp_id: int) -> dict:
    """
    Run all quality checks on generated sections for the latest draft version.
    Returns a quality_status dict and saves it to the RFP record.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}

    # Get latest version sections
    latest = db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id
    ).order_by(desc(RFPDraft.version)).first()

    if not latest:
        status = {
            "structure": {"passed": False, "detail": "No draft sections generated yet"},
            "placeholders": {"passed": False, "detail": "No content to check"},
            "broken_chars": {"passed": False, "detail": "No content to check"},
            "toc": {"passed": False, "detail": "No sections found"},
            "compliance_matrix": {"passed": False, "detail": "No compliance matrix found"},
            "empty_sections": {"passed": False, "detail": "No sections found"},
            "duplicate_headings": {"passed": True, "detail": "No sections to check"},
            "human_review": {"required": True, "detail": "SA must review before final submission"},
            "overall": "not_ready",
            "is_final_check": False
        }
        _save_quality(db, rfp, status)
        return status

    version = latest.version
    sections = db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id,
        RFPDraft.version == version
    ).order_by(RFPDraft.section_order).all()

    section_names = [s.section_name for s in sections if s.section_name]
    all_text = "\n".join(s.draft_content or "" for s in sections)

    # ── 1. Structure Check ────────────────────────────────────────────────────
    from app.services.generation_service import get_sections_for_mode
    mode = rfp.generation_mode or "short"
    mode_sections = get_sections_for_mode(mode)
    target_count = len(mode_sections)
    
    structure_ok = len(sections) >= target_count
    structure = {
        "passed": structure_ok,
        "detail": f"{len(sections)}/{target_count} sections generated",
        "generated_count": len(sections),
        "required_count": target_count,
    }
    
    is_complete = structure_ok # 100% generated

    # ── 2. Placeholder Check ──────────────────────────────────────────────────
    placeholder_matches = PLACEHOLDER_RE.findall(all_text)
    placeholder_ok = len(placeholder_matches) == 0
    placeholders = {
        "passed": placeholder_ok,
        "detail": f"{len(placeholder_matches)} placeholder(s) found" if not placeholder_ok else "No placeholders found",
        "found": list(set(placeholder_matches))[:10],
    }

    # ── 3. Broken Characters Check ────────────────────────────────────────────
    broken_matches = BROKEN_RE.findall(all_text)
    broken_ok = len(broken_matches) == 0
    broken_chars = {
        "passed": broken_ok,
        "detail": f"{len(broken_matches)} broken character sequence(s) found" if not broken_ok else "No broken characters",
    }

    # ── 4. TOC Check — requires "Table of Contents" text and list of sections ──
    # For POC, we accept static TOC text.
    has_toc_text = "table of contents" in all_text.lower()
    toc_sections_found = len(set(section_names))
    # Lenient: just need the text and at least 80% of sections listed or a reasonable minimum
    toc_ok = has_toc_text and toc_sections_found >= (target_count - 2)
    toc = {
        "passed": toc_ok,
        "detail": f"{'Found' if has_toc_text else 'Missing'} 'Table of Contents' text, {toc_sections_found} sections identified",
    }

    # ── 5. Compliance Matrix Check ─────────────────────────────────────────────
    # In short mode, we look for "Compliance Summary"
    comp_keywords = ["compliance matrix", "compliance summary", "compliance coverage"]
    compliance_section_obj = next((s for s in sections if any(k in (s.section_name or "").lower() for k in comp_keywords)), None)
    
    has_compliance_content = False
    if compliance_section_obj:
        content_len = len((compliance_section_obj.draft_content or "").strip())
        # Short mode summary can be shorter (e.g. 150 words)
        min_len = 150 if mode == "short" else 400
        has_compliance_content = content_len >= min_len

    if has_compliance_content:
        compliance_ok = True
        comp_detail = "Compliance section found with sufficient content"
    elif compliance_section_obj:
        compliance_ok = False # Needs Review
        comp_detail = "Compliance section exists but content appears too short"
    else:
        compliance_ok = False
        comp_detail = "Compliance Matrix/Summary section is missing"

    compliance_matrix = {
        "passed": compliance_ok,
        "detail": comp_detail,
        "needs_review": compliance_section_obj is not None and not has_compliance_content
    }

    # ── 6. Empty Sections Check ───────────────────────────────────────────────
    empty = [s.section_name for s in sections if not (s.draft_content or "").strip()]
    empty_ok = len(empty) == 0
    empty_sections = {
        "passed": empty_ok,
        "detail": f"{len(empty)} empty section(s)" if not empty_ok else "All sections have content",
        "empty_list": empty[:5],
    }

    # ── 7. Duplicate Heading Check (Across Sections) ──────────────────────────
    from collections import Counter
    name_counts = Counter(section_names)
    duplicates = [name for name, count in name_counts.items() if count > 1]
    
    # NEW: Check for duplicate headings INSIDE markdown body
    internal_dupes = []
    for s in sections:
        headings = re.findall(r'^#+ (.+)$', s.draft_content or "", re.MULTILINE)
        h_counts = Counter(headings)
        s_dupes = [h for h, c in h_counts.items() if c > 1]
        if s_dupes:
            internal_dupes.append(f"{s.section_name}: {s_dupes[0]}")

    dup_ok = len(duplicates) == 0 and len(internal_dupes) == 0
    duplicate_headings = {
        "passed": dup_ok,
        "detail": f"{len(duplicates)} section dupes, {len(internal_dupes)} internal dupes found" if not dup_ok else "No duplicate headings",
        "duplicates": (duplicates + internal_dupes)[:5],
    }

    # ── 9. Malformed Table Check ──────────────────────────────────────────────
    # Look for broken table separators like ":---" with no pipe or missing rows
    malformed_tables = re.findall(r'^[|]?\s*[: \-]+\s*[|]?\s*$', all_text, re.MULTILINE)
    table_ok = len(malformed_tables) == 0
    tables = {
        "passed": table_ok,
        "detail": f"Detected {len(malformed_tables)} potentially malformed table separator(s)" if not table_ok else "Tables look well-formatted",
    }

    # ── 10. Over-Expansion Check ──────────────────────────────────────────────
    # If source is tiny but generated is huge
    source_words = 0
    if rfp.summary_json:
        try: source_words = json.loads(rfp.summary_json).get("word_count", 0)
        except: pass
    
    generated_words = len(all_text.split())
    # If generated is 30x larger than source and source is tiny, flag it
    expansion_ratio = (generated_words / max(1, source_words))
    over_expanded = source_words < 500 and expansion_ratio > 30
    expansion = {
        "passed": not over_expanded,
        "detail": f"Expansion ratio {expansion_ratio:.1f}x. Source: {source_words}w, Gen: {generated_words}w" if over_expanded else "Content expansion is within reasonable limits",
        "ratio": expansion_ratio
    }

    # ── 11. Missing Client Details Check ──────────────────────────────────────
    missing_client = rfp.client_name is None or "tbd" in (rfp.client_name or "").lower() or "client" in (rfp.client_name or "").lower()
    client_check = {
        "passed": not missing_client,
        "detail": "Client details identified" if not missing_client else "Specific client name may be missing from document",
    }

    # ── 8. Human Review (always required) ─────────────────────────────────────
    human_review = {
        "required": True,
        "detail": "SA must review and approve before PM submission",
    }

    # ── 12. Claims Validation Check ───────────────────────────────────────────
    from app.services.post_processing_service import CLAIM_RE
    claims_matches = CLAIM_RE.findall(all_text)
    claims_ok = len(claims_matches) == 0
    company_claims = {
        "passed": claims_ok,
        "detail": f"{len(claims_matches)} strong claim(s) detected requiring validation" if not claims_ok else "No specific risky claims detected",
        "needs_review": not claims_ok
    }

    # ── 13. Numbering Consistency Check ───────────────────────────────────────
    # Looking for markdown headings that have a leading number
    numbering_matches = re.findall(r'^#+\s*\d+\.\d*\s+', all_text, re.MULTILINE)
    numbering_ok = len(numbering_matches) == 0
    numbering_consistency = {
        "passed": numbering_ok,
        "detail": f"{len(numbering_matches)} heading(s) with conflicting numbering" if not numbering_ok else "Heading numbering is clean"
    }

    # ── Overall Status ────────────────────────────────────────────────────────
    # Only "pass" if all critical checks are true and it's complete
    critical_checks = [structure_ok, empty_ok, dup_ok, table_ok]
    warnings = [placeholder_ok, compliance_ok, broken_ok, toc_ok, not over_expanded, not missing_client, numbering_ok]

    if is_complete and all(critical_checks) and all(warnings):
        overall = "passed"
    elif is_complete and all(critical_checks):
        overall = "passed_with_warnings"
    else:
        overall = "needs_review"

    status = {
        "structure": structure,
        "placeholders": placeholders,
        "broken_chars": broken_chars,
        "toc": toc,
        "compliance_matrix": compliance_matrix,
        "empty_sections": empty_sections,
        "duplicate_headings": duplicate_headings,
        "malformed_tables": tables,
        "expansion": expansion,
        "client_check": client_check,
        "human_review": human_review,
        "company_claims": company_claims,
        "numbering_consistency": numbering_consistency,
        "overall": overall,
        "version_checked": version,
        "is_final_check": structure_ok # If structure is 100%, consider it a final check
    }

    _save_quality(db, rfp, status)
    return status



def _save_quality(db: Session, rfp: RFPDocument, status: dict):
    """Persist quality_status JSON to the RFP record."""
    try:
        rfp.quality_status = json.dumps(status)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[quality_service] Failed to save quality status: {e}")
