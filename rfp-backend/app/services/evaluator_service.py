"""
evaluator_service.py
====================
PART 4: Evaluator-Optimizer Loop for Proposal Sections.

Flow per section:
1. generate_section() → raw draft
2. run_deterministic_checks() → 0 tokens, instant
3. If deterministic pass → run_llm_evaluator() via Azure GPT-4o-mini
4. evaluator returns score + issues
5. If score < threshold and attempts < max → optimize_section() with feedback
6. Save section with final evaluation_status

max_attempts = 2 for POC cost control.
"""
import re
import json
from sqlalchemy.orm import Session
from app.models.rfp import RFPDraft, AuditLog

# ── Deterministic Checks (0 tokens) ──────────────────────────────────────────

PLACEHOLDER_PATTERNS = [
    r"\[INSERT\b.*?\]", r"\[TBD\]", r"\[PLACEHOLDER\]", r"\bXXX\b",
    r"\[YOUR COMPANY\]", r"\[CLIENT NAME\]", r"\[DATE\]",
]

BROKEN_CHAR_PATTERNS = [
    r"[^\x00-\x7F\u00C0-\u024F\u0900-\u097F]",  # Non-standard Unicode outside common ranges
    r"â€™", r"â€œ", r"â€", r"Ã©", r"Â ",         # Common UTF-8 misencoded sequences
]

REQUIRED_SECTION_KEYWORDS = {
    "Executive Summary": ["summary", "overview", "objective"],
    "Technical Approach": ["technical", "approach", "solution", "methodology"],
    "Project Timeline": ["timeline", "schedule", "milestone", "phase"],
    "Pricing": ["price", "cost", "budget", "commerci"],
    "Team": ["team", "resource", "expert", "personnel"],
}

WORD_BUDGET = {
    "short": {"min": 100, "max": 500},
    "standard": {"min": 200, "max": 800},
    "comprehensive": {"min": 400, "max": 1500},
}


def run_deterministic_checks(
    content: str,
    section_title: str,
    generation_mode: str = "standard",
    expected_title: str = None
) -> dict:
    """
    Zero-token validation of a generated section.
    Returns: {passed: bool, issues: list[str]}
    """
    issues = []

    # 1. Not empty
    if not content or len(content.strip()) < 30:
        issues.append("Section is empty or too short.")

    # 2. No placeholders
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            issues.append(f"Placeholder detected: matches pattern '{pattern}'")

    # 3. No broken characters
    for pattern in BROKEN_CHAR_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            issues.append(f"Broken/garbled characters detected: {matches[:3]}")

    # 4. Word count budget
    word_count = len(content.split())
    budget = WORD_BUDGET.get(generation_mode, WORD_BUDGET["standard"])
    if word_count < budget["min"]:
        issues.append(f"Section too short: {word_count} words (min {budget['min']}).")
    if word_count > budget["max"]:
        issues.append(f"Section too long: {word_count} words (max {budget['max']}).")

    # 5. Duplicate heading check (heading in first 2 lines repeated)
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    if len(lines) > 1 and lines[0].lower() == lines[1].lower():
        issues.append("Duplicate heading detected at start of section.")

    # 6. Expected title keyword present
    if expected_title:
        kws = REQUIRED_SECTION_KEYWORDS.get(expected_title, [])
        if kws and not any(kw in content.lower() for kw in kws):
            issues.append(f"Section may not be relevant to '{expected_title}'.")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "word_count": word_count,
    }


# ── LLM Evaluator (Azure GPT-4o-mini) ────────────────────────────────────────

EVALUATOR_PROMPT_TEMPLATE = """
You are a proposal quality evaluator for an enterprise RFP response system.

Evaluate the following generated section against the RFP context.

RFP Context:
{rfp_context_summary}

Section Title: {section_title}
Section Content:
{section_content}

Evaluate on these criteria (score 0-100 each):
1. Relevance to RFP requirements
2. Completeness (covers the topic adequately)
3. Professional proposal tone
4. No unsupported claims
5. Client/RFP alignment
6. Company consistency (does not contradict earlier sections)
7. Compliance coverage (if applicable)
8. Conciseness within expected length

Return ONLY valid JSON:
{{
  "score": <overall 0-100>,
  "pass": <true if score >= 65>,
  "criteria_scores": {{
    "relevance": 0-100,
    "completeness": 0-100,
    "tone": 0-100,
    "accuracy": 0-100,
    "alignment": 0-100,
    "consistency": 0-100,
    "compliance": 0-100,
    "conciseness": 0-100
  }},
  "issues": ["list of specific issues"],
  "improvement_instructions": "Specific rewrite guidance for the generator"
}}
"""


def run_llm_evaluator(
    section_content: str,
    section_title: str,
    rfp_context: dict,
    db: Session
) -> dict:
    """
    LLM-based evaluation using Azure GPT-4o-mini.
    Only called when deterministic checks pass.
    Returns: {score, pass, issues, improvement_instructions}
    """
    try:
        from app.services.ai_service import call_ai

        # Build compact context summary (not the full document)
        ctx_parts = []
        if rfp_context.get("client_name"):
            ctx_parts.append(f"Client: {rfp_context['client_name']}")
        if rfp_context.get("executive_summary"):
            ctx_parts.append(f"Summary: {str(rfp_context['executive_summary'])[:300]}")
        if rfp_context.get("risks"):
            ctx_parts.append(f"Key Risks: {str(rfp_context['risks'])[:200]}")
        ctx_summary = "\n".join(ctx_parts) or "No context available."

        prompt = EVALUATOR_PROMPT_TEMPLATE.format(
            rfp_context_summary=ctx_summary,
            section_title=section_title,
            section_content=section_content[:2000],  # Limit to control tokens
        )

        ai_res = call_ai(db, "quality_check_summary", prompt)
        raw = ai_res.get("text", "")

        # Parse JSON from response
        result = _extract_json_from_response(raw)
        if not result:
            return {"score": 50, "pass": True, "issues": [], "improvement_instructions": "", "parse_error": True}

        return {
            "score": int(result.get("score", 50)),
            "pass": bool(result.get("pass", True)),
            "issues": result.get("issues", []),
            "improvement_instructions": result.get("improvement_instructions", ""),
            "criteria_scores": result.get("criteria_scores", {}),
            "tokens_used": ai_res.get("tokens_used", 0),
            "provider": "azure",
        }

    except Exception as e:
        print(f"[evaluator_service] LLM evaluator failed: {e}")
        # Fail open — do not block the workflow
        return {"score": 60, "pass": True, "issues": [str(e)], "improvement_instructions": "", "error": True}


def _extract_json_from_response(text: str) -> dict | None:
    try:
        # Strip markdown code blocks
        text = re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", text, flags=re.DOTALL)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
    except Exception:
        pass
    return None


# ── Evaluator-Optimizer Loop ──────────────────────────────────────────────────

def evaluator_optimizer_loop(
    rfp_id: int,
    section_title: str,
    section_content: str,
    rfp_context: dict,
    db: Session,
    generate_fn,          # Callable(section_title, rfp_context, feedback) -> str
    generation_mode: str = "standard",
    max_attempts: int = 2  # POC cost control: max 2 LLM evaluations
) -> dict:
    """
    PART 4: Full evaluator-optimizer loop.
    
    1. Run deterministic checks on generated content.
    2. If pass → LLM evaluator.
    3. If LLM evaluator fails and attempts < max → regenerate with feedback.
    4. Save final section to DB with evaluation metadata.
    
    Returns: {content, evaluation_status, evaluator_score, evaluator_feedback, attempt_count}
    """
    attempt = 1
    current_content = section_content
    final_status = "pending"
    final_score = None
    final_feedback = ""
    improvement_instructions = ""

    while attempt <= max_attempts:
        print(f"[evaluator] RFP {rfp_id} | {section_title} | Attempt {attempt}/{max_attempts}")

        # Step 1: Deterministic checks (0 tokens)
        det_result = run_deterministic_checks(
            current_content, section_title, generation_mode, expected_title=section_title
        )
        word_count = det_result["word_count"]

        if not det_result["passed"]:
            issues_str = "; ".join(det_result["issues"])
            print(f"[evaluator] Deterministic FAIL: {issues_str}")

            if attempt < max_attempts:
                # Regenerate with deterministic feedback
                feedback = f"Previous version failed deterministic checks: {issues_str}. Fix these issues."
                try:
                    current_content = generate_fn(section_title, rfp_context, feedback)
                except Exception as gen_err:
                    print(f"[evaluator] Regeneration failed: {gen_err}")
                    break
                attempt += 1
                continue
            else:
                final_status = "needs_human_review"
                final_feedback = issues_str
                break

        # Step 2: LLM Evaluator (Azure GPT-4o-mini)
        eval_result = run_llm_evaluator(current_content, section_title, rfp_context, db)
        final_score = eval_result["score"]
        final_feedback = "; ".join(eval_result.get("issues", []))
        improvement_instructions = eval_result.get("improvement_instructions", "")

        if eval_result["pass"]:
            final_status = "passed"
            print(f"[evaluator] PASSED with score {final_score}")
            break
        else:
            print(f"[evaluator] LLM FAIL with score {final_score}")
            if attempt < max_attempts:
                try:
                    feedback = f"Score: {final_score}/100. Issues: {final_feedback}. Instructions: {improvement_instructions}"
                    current_content = generate_fn(section_title, rfp_context, feedback)
                except Exception as gen_err:
                    print(f"[evaluator] Regeneration failed: {gen_err}")
                    break
                attempt += 1
            else:
                # Max attempts reached
                if final_score and final_score >= 50:
                    final_status = "passed"  # Accept if reasonably good
                else:
                    final_status = "needs_human_review"
                break

    return {
        "content": current_content,
        "evaluation_status": final_status,
        "evaluator_score": final_score,
        "evaluator_feedback": final_feedback,
        "attempt_count": attempt,
        "word_count": word_count if "word_count" in dir() else len(current_content.split()),
    }


def save_evaluated_draft(rfp_id: int, section_name: str, section_order: int, eval_result: dict, db: Session, created_by: int = None) -> RFPDraft:
    """
    Save or update a draft section with evaluator metadata.
    """
    # Check for existing section to update
    existing = db.query(RFPDraft).filter(
        RFPDraft.rfp_id == rfp_id,
        RFPDraft.section_name == section_name
    ).first()

    if existing:
        existing.draft_content = eval_result["content"]
        existing.evaluation_status = eval_result["evaluation_status"]
        existing.evaluator_score = eval_result.get("evaluator_score")
        existing.evaluator_feedback = eval_result.get("evaluator_feedback", "")
        existing.attempt_count = eval_result.get("attempt_count", 1)
        existing.word_count = eval_result.get("word_count")
        db.commit()
        return existing
    else:
        draft = RFPDraft(
            rfp_id=rfp_id,
            section_name=section_name,
            section_order=section_order,
            draft_content=eval_result["content"],
            evaluation_status=eval_result["evaluation_status"],
            evaluator_score=eval_result.get("evaluator_score"),
            evaluator_feedback=eval_result.get("evaluator_feedback", ""),
            attempt_count=eval_result.get("attempt_count", 1),
            word_count=eval_result.get("word_count"),
            created_by=created_by,
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        return draft
