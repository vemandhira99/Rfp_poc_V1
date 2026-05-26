import re

# Regex for company claims
CLAIM_PATTERNS = [
    r'\bcmmi\s*(level\s*)?[1-5]?\b',
    r'\biso\s*\d+\b',
    r'\b100\s*(technical\s*)?staff\b',
    r'\b250\s*(technical\s*)?staff\b',
    r'\bcert-in\b',
    r'\bstqc\b',
    r'\bgovernment\s*cloud\b'
]
CLAIM_RE = re.compile('|'.join(CLAIM_PATTERNS), re.IGNORECASE)

def normalize_section_numbering(text: str) -> str:
    """Removes leading numbers from markdown subheadings if they conflict or are redundant."""
    if not text:
        return ""
    # Remove things like "## 1.1 " or "### 1.1.1 " and keep just the title
    # This prevents AI from messing up numbering
    return re.sub(r'^(#+)\s*(?:\d+\.)+\s+', r'\1 ', text, flags=re.MULTILINE)

def remove_markdown_artifacts(text: str) -> str:
    """Removes malformed markdown tables or artifact lines."""
    if not text:
        return ""
    # Some AI output includes raw raw table separators not within a valid table
    # We will let the DOCX exporter handle valid tables, but we can clean up loose separators
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # If it's a markdown table separator line and previous line wasn't a table header, it might be an artifact.
        # But this is tricky without full context. A safer approach is just stripping loose horizontal rules
        if re.match(r'^[-*_]{3,}$', stripped):
            continue # skip horizontal rules which might look like artifacts
        cleaned.append(line)
    return '\n'.join(cleaned)

def deduplicate_repeated_content(text: str) -> str:
    """Removes highly redundant marketing fluff or generic phrases."""
    if not text:
        return ""
    # Simply strip or tone down overused phrases
    fluff_phrases = [
        "transformative solution",
        "state-of-the-art",
        "unparalleled",
        "exceeds expectations"
    ]
    for phrase in fluff_phrases:
         text = re.sub(r'(?i)\b' + re.escape(phrase) + r'\b', "comprehensive solution", text)
         
    # Deduplicate exact paragraph repeats
    lines = text.split('\n')
    seen = set()
    cleaned = []
    for line in lines:
        if len(line.strip()) > 30: # Only check substantial paragraphs
            if line.strip() in seen:
                continue
            seen.add(line.strip())
        cleaned.append(line)
    return '\n'.join(cleaned)

def validate_company_claims(text: str) -> str:
    """Detects strong company claims and flags them for human review."""
    if not text:
        return ""
    
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if CLAIM_RE.search(line):
            if not line.endswith("[Requires Company Validation]"):
                lines[i] = line + " **[Requires Company Validation]**"
    return '\n'.join(lines)

def run_post_processing_pipeline(text: str) -> str:
    if not text:
        return ""
    text = normalize_section_numbering(text)
    text = remove_markdown_artifacts(text)
    text = deduplicate_repeated_content(text)
    text = validate_company_claims(text)
    return text
