from google import genai
import json
import os
import re
import time
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.rfp import RFPDocument, AuditLog, RFPMetadata, RFPDraft, ChatHistory
from app.models.sections import RFPSection
from app.services.notification_service import create_notification
import openai

gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

# OpenAI Clients (Optional based on key availability)
openai_client = None
if settings.OPENAI_API_KEY:
    try:
        openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        print(f"OpenAI initialization failed: {e}")

azure_client = None
if settings.AZURE_OPENAI_API_KEY:
    try:
        azure_client = openai.AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
    except Exception as e:
        print(f"Azure OpenAI initialization failed: {e}")

class QuotaExhaustedError(Exception):
    """Raised when Gemini API quota is exhausted (429)."""
    pass

def clean_json(text):
    """
    Extracts and cleans JSON from AI response, handling markdown blocks and stray text.
    """
    if not text:
        return None
    # Remove markdown code blocks if present
    text = re.sub(r'```(?:json)?\s*(.*?)\s*```', r'\1', text, flags=re.DOTALL)
    # Find the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        text = text[start:end+1]
    
    # Basic cleaning of common AI artifacts
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def ensure_gemini_file(db: Session, rfp: RFPDocument):
    """
    Ensures a valid Gemini File reference exists. Re-uploads if the URI is invalid.
    """
    file_ref = None
    if rfp.gemini_file_uri:
        try:
            file_ref = gemini_client.files.get(name=rfp.gemini_file_uri)
        except Exception as e:
            print(f"Gemini File URI invalid for RFP {rfp.id}: {str(e)}. Re-uploading...")
            file_ref = None

    if not file_ref:
        if rfp.file_path and os.path.exists(rfp.file_path):
            try:
                print(f"Uploading file for RFP {rfp.id}: {rfp.file_path}")
                file_ref = gemini_client.files.upload(file=rfp.file_path, config={'display_name': rfp.file_name})
                
                # Wait for file to be active
                for _ in range(12): # Wait up to 60s
                    file_ref = gemini_client.files.get(name=file_ref.name)
                    if file_ref.state.name == "ACTIVE":
                        break
                    time.sleep(5)
                
                rfp.gemini_file_uri = file_ref.name
                db.commit()
            except Exception as ue:
                print(f"Error uploading file for RFP {rfp.id}: {str(ue)}")
                return None
        else:
            return None
    return file_ref

def get_or_create_cache(db: Session, rfp_id: int):
    """
    Implements On-Demand Cache. Uses DB-backed rehydration to reuse existing caches.
    """
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp or not rfp.full_text:
        return None

    # REHYDRATION CHECK
    if rfp.gemini_cache_id and rfp.cache_expiry:
        if rfp.cache_expiry > datetime.utcnow():
            if rfp.gemini_cache_id == "CACHING_UNAVAILABLE":
                return None
            return type('Cache', (), {'name': rfp.gemini_cache_id})

    # Only cache if text is large enough (>32k characters)
    if len(rfp.full_text) < 32000:
        return None

    try:
        from google.genai import types
        ttl_seconds = 3600
        cache = client.caches.create(
            model=settings.GEMINI_MODEL,
            config=types.CreateCachedContentConfig(
                display_name=f"rfp_cache_{rfp_id}",
                contents=[rfp.full_text],
                ttl=f"{ttl_seconds}s" 
            )
        )
        
        rfp.gemini_cache_id = cache.name
        rfp.cache_expiry = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        db.commit()
        return cache
    except Exception as e:
        # If caching specifically hits a quota/tier limit, we should mark it to avoid retrying every time
        error_str = str(e).lower()
        if "429" in error_str or "limit exceeded" in error_str:
            print(f"Context Caching not supported for this tier/document. Using fallback for RFP {rfp_id}.")
            # We temporarily set expiry to a short time in the future so the logic skips it
            rfp.cache_expiry = datetime.utcnow() + timedelta(minutes=10)
            rfp.gemini_cache_id = "CACHING_UNAVAILABLE" 
            db.commit()
        return None

def track_quota_usage(db: Session, is_error=False, error_msg="", tokens=0):
    from app.models.quota import QuotaUsage
    today = datetime.now().strftime("%Y-%m-%d")
    
    quota = db.query(QuotaUsage).filter(QuotaUsage.day == today).first()
    if not quota:
        quota = QuotaUsage(day=today, request_count=0, token_count=0)
        db.add(quota)
    
    if tokens > 0:
        quota.token_count += tokens
    else:
        quota.request_count += 1

    if is_error:
        error_msg_lower = error_msg.lower()
        if "429" in error_msg_lower or "quota" in error_msg_lower:
            quota.is_exhausted = True
    
    db.commit()

def call_gemini_with_retry(db: Session, content, model=None, config=None, max_retries=10, task_name="general"):
    if model is None:
        model = settings.GEMINI_MODEL
        
    print(f"Using Gemini model: {model}")
    print(f"Task: {task_name}")
    
    track_quota_usage(db)
    for i in range(max_retries):
        try:
            gen_config = config if config else {}
            response = gemini_client.models.generate_content(
                model=model,
                contents=content,
                config=gen_config
            )
            if response.usage_metadata:
                track_quota_usage(db, tokens=response.usage_metadata.total_token_count)
            return response
        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "quota" in error_str:
                print(f"Quota exhausted (429) for model {model}")
                track_quota_usage(db, is_error=True, error_msg=error_str)
                raise QuotaExhaustedError(f"Generation paused due to API quota. {str(e)}")
                
            if any(code in error_str for code in ["503", "unavailable", "overloaded"]):
                if i < max_retries - 1:
                    wait_time = (i + 1) * 5 
                    print(f"Retrying Gemini API in {wait_time}s... (Attempt {i+1})")
                    time.sleep(wait_time)
                    continue
            raise e

def detect_local_chat_intent(message: str, user_role: str = "PM") -> str:
    """
    Robust local intent detection. 
    Handles greetings, help requests, and basic confirmations without AI tokens.
    """
    import re
    # Normalization: lowercase, trim, remove punctuation
    msg = message.lower().strip()
    msg = re.sub(r'[^\w\s]', '', msg)
    
    # Collapse repeated letters (e.g., "hii", "hiii" -> "hi")
    # This is a bit tricky, but for simple common greetings:
    if re.match(r'^h+i+$', msg): msg = "hi"
    if re.match(r'^he+y+$', msg): msg = "hey"
    if re.match(r'^hello+$', msg): msg = "hello"
    
    greetings = ['hi', 'hello', 'hey', 'start']
    time_greetings = ['good morning', 'good afternoon', 'good evening']
    confirmations = ['thanks', 'thank you', 'ok', 'okay', 'yes', 'no', 'got it']
    help_cmds = ['help', 'who are you', 'what can you do', 'how can you help', 'guide me']
    
    pm_response = "Hi, I’m your RFP AI Advisor. I can help you review this RFP, identify risks, summarize compliance requirements, explain deadlines, and support go/no-go decisions. Try asking: ‘What are the biggest risks?’ or ‘Is the timeline feasible?’"
    sa_response = "Hi, I’m your Solution Architect AI Assistant. I can help refine technical sections, validate compliance coverage, improve architecture responses, and review generated proposal content."
    
    is_greeting = msg in greetings or any(tg in msg for tg in time_greetings)
    is_help = msg in help_cmds
    is_confirmation = msg in confirmations
    
    if is_greeting:
        return pm_response if user_role.upper() == "PM" or user_role.upper() == "CEO" else sa_response
    
    if is_help:
        return "I can analyze RFPs, extract deadlines, highlight risks, and explain requirements. Ask me anything about the document!"
        
    if is_confirmation:
        return "You're welcome! Let me know if you have specific questions about this RFP."
        
    return ""

def call_ai(db: Session, task_type: str, prompt: str, context: list = None, preferred_provider: str = None, cache_name: str = None):
    """
    Hybrid AI Abstraction. Routes request to Gemini or OpenAI based on availability and task.
    """
    if not preferred_provider:
        preferred_provider = settings.AI_PROVIDER_PRIMARY
        
    # Task specific routing overrides
    if task_type in ["chat_basic_db", "metadata_cleanup", "quality_check_summary"]:
        if azure_client: preferred_provider = "azure"
        elif openai_client: preferred_provider = "openai"
    elif task_type in ["draft_generation", "executive_summary"]:
        preferred_provider = "gemini" # Heavy reasoning tasks

    print(f"AI task: {task_type} | Provider used: {preferred_provider}")
    
    try:
        if preferred_provider == "azure" and azure_client:
            sys_prompt = "You are an expert RFP analyst."
            user_msg = prompt
            if context and isinstance(context, list) and isinstance(context[0], str):
                sys_prompt = "\n".join(context)
            
            response = azure_client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.2
            )
            tokens = response.usage.total_tokens if response.usage else 0
            return {
                "text": response.choices[0].message.content,
                "provider_used": "azure",
                "model_used": settings.AZURE_OPENAI_DEPLOYMENT,
                "tokens_used": tokens
            }

        if preferred_provider == "openai" and openai_client:
            sys_prompt = "You are an expert RFP analyst."
            user_msg = prompt
            if context and isinstance(context, list) and isinstance(context[0], str):
                sys_prompt = "\n".join(context)
            
            response = openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0.2
            )
            tokens = response.usage.total_tokens if response.usage else 0
            return {
                "text": response.choices[0].message.content,
                "provider_used": "openai",
                "model_used": settings.OPENAI_MODEL,
                "tokens_used": tokens
            }
    except Exception as e:
        print(f"Provider {preferred_provider} failed for task {task_type}: {e}")
        preferred_provider = "gemini" # Fallback to Gemini
        
    # Default to Gemini
    try:
        if cache_name:
            config = {"cached_content": cache_name}
            resp = call_gemini_with_retry(db, prompt, config=config, task_name=task_type)
        else:
            contents = []
            if context: contents.extend(context)
            contents.append(prompt)
            resp = call_gemini_with_retry(db, contents, task_name=task_type)
            
        tokens = resp.usage_metadata.total_token_count if resp.usage_metadata else 0
        return {
            "text": resp.text,
            "provider_used": "gemini",
            "model_used": settings.GEMINI_MODEL,
            "tokens_used": tokens
        }
    except QuotaExhaustedError as qe:
        if openai_client and task_type != "draft_generation":
            print(f"Gemini quota exhausted. Attempting OpenAI fallback for {task_type}...")
            return call_ai(db, task_type, prompt, context, "openai")
        raise qe

def generate_summary(db: Session, rfp_id: int) -> dict:
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        return {"error": "RFP not found"}

    if rfp.summary_json:
        try:
            sj = json.loads(rfp.summary_json)
            # Only skip if it's a real AI-generated summary
            if sj.get("executive_summary") or sj.get("project_overview"):
                return {"rfp_id": rfp_id, "status": "summary_generated", "summary": sj}
        except:
            pass 

    prompt = """
You are an expert RFP analyst. Analyze this RFP document and return a JSON response ONLY.
Return ONLY this JSON structure:
{
    "title": "RFP title",
    "client_name": "client or organization name",
    "project_overview": "2-3 sentence summary",
    "deadline": "YYYY-MM-DD or null",
    "value": "₹ amount or 'TBD'",
    "contract_length": "duration or 'TBD'",
    "payment_terms": "terms or 'TBD'",
    "effort_estimation": "effort or 'TBD'",
    "win_probability": 75,
    "complexity_score": 7,
    "complexity_reason": "reason",
    "key_requirements": ["req1", "req2"],
    "risks": [{"risk": "desc", "severity": "high/medium/low"}],
    "mandatory_clauses": ["clause1"],
    "recommended_action": "proceed/hold/reject",
    "recommendation_reason": "reason",
    "go_no_go": "GO or NO-GO",
    "executive_summary": "Professional summary...",
    "next_steps": "Recommended actions..."
}
"""
    try:
        # 4-Stage Pipeline Statuses
        rfp.current_status = "analyzing_structure"
        rfp.status_message = "Mapping document hierarchy..."
        db.commit()
        
        cache = get_or_create_cache(db, rfp_id)
        
        rfp.current_status = "extracting_metrics"
        rfp.status_message = "Identifying key values and deadlines..."
        db.commit()

        if cache:
            response = call_gemini_with_retry(db=db, content=prompt, config={"cached_content": cache.name}, task_name="summary_generation")
        else:
            file = ensure_gemini_file(db, rfp)
            if not file: return {"error": "Failed to load document."}
            response = call_gemini_with_retry(db=db, content=[file, prompt], task_name="summary_generation")
        
        rfp.current_status = "finalizing_insights"
        rfp.status_message = "Synthesizing recommendations..."
        db.commit()

        result = clean_json(response.text)
        if not result: raise ValueError("Invalid AI response format.")

        rfp.current_status = "pending-review" # Summary stage complete
        rfp.summary_json = json.dumps(result)
        
        # Update metadata
        metadata = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
        if not metadata:
            metadata = RFPMetadata(rfp_id=rfp_id)
            db.add(metadata)
        
        if result.get("client_name"): rfp.client_name = result["client_name"]
        if result.get("title"): rfp.title = result["title"]
        
        db.add(AuditLog(rfp_id=rfp_id, action="ai_summary_generated", new_value=rfp.summary_json))
        db.commit()

        return {"rfp_id": rfp_id, "status": "success", "summary": result}
    except Exception as e:
        rfp.current_status = "error"
        rfp.status_message = str(e)
        db.commit()
        return {"error": str(e)}

def generate_proposal_section(db: Session, rfp_id: int, section_name: str, section_order: int, user_id: int, version: int = 1):
    from app.models.rfp import RFPDraft
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    
    master_instruction = """
You are a top-tier Management Consultant. Generate a world-class, submission-ready RFP response.
Rules: EXTREME DEPTH (1500+ words), NO PLACEHOLDERS, TECHNICAL SPECIFICITY, VISUAL SCHEMATICS (Tables), PERSUASIVE TONE.
"""
    prompt = f"{master_instruction}\n\n### TARGET SECTION: {section_order}. {section_name}\nWrite the full detailed content as raw Markdown."

    try:
        cache = get_or_create_cache(db, rfp_id)
        if cache:
            response = call_gemini_with_retry(db=db, content=prompt, config={"cached_content": cache.name})
        else:
            file = ensure_gemini_file(db, rfp)
            if not file: return None
            # Primary try
            try:
                response = call_gemini_with_retry(db=db, content=[file, prompt], task_name="draft_generation")
            except Exception as e:
                print(f"Draft generation attempt failed: {e}")
                response = None
            
            if not response: return None
        
        content = response.text.strip()
        draft_section = RFPDraft(
            rfp_id=rfp_id, section_name=section_name, section_order=section_order,
            version=version, draft_content=content, created_by=user_id
        )
        db.add(draft_section)
        db.commit()
        return draft_section
    except Exception as e:
        db.rollback()
        print(f"Error generating section {section_name}: {str(e)}")
        return None

def generate_architect_draft(db: Session, rfp_id: int) -> dict:
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp: return {"error": "RFP not found"}

    # Stop other ongoing generations
    others = db.query(RFPDocument).filter(RFPDocument.id != rfp_id, RFPDocument.current_status == "generating_draft").all()
    for other in others:
        other.current_status = "on_hold"
    db.commit()

    sections = [
        "Executive Summary", "Strategic Vision and Project Objectives", "Comprehensive Understanding of Functional Requirements",
        "Comprehensive Understanding of Non-Functional Requirements", "Proposed Solution Architecture: Logical View",
        "Proposed Solution Architecture: Technical Stack & Infrastructure", "Proposed Solution Architecture: Module Integration & Workflow",
        "Detailed Functional Architecture: Budget Management", "Detailed Functional Architecture: Commitment Control & Fund Management",
        "Detailed Functional Architecture: Contract Management", "Detailed Functional Architecture: Sanction Management",
        "Detailed Functional Architecture: Payroll & Compensation Management", "Detailed Functional Architecture: Pension & Retirement Benefits",
        "Detailed Functional Architecture: HR & Talent Management", "Detailed Functional Architecture: Recruitment & Induction",
        "Detailed Functional Architecture: Receipt Management & Banking Interface", "Detailed Functional Architecture: Payment Processing & Audit Trails",
        "Detailed Functional Architecture: Grant Management & Utilization Certificates", "Detailed Functional Architecture: Project Monitoring & Management",
        "Detailed Functional Architecture: Asset Management & Inventory", "Detailed Functional Architecture: General Ledger & Financial Accounting",
        "Detailed Functional Architecture: Data Analytics & Executive Dashboards", "Detailed Functional Architecture: Master Data Management & Governance",
        "Detailed Functional Requirement Specification (FRS) Compliance Matrix", "Integration Architecture: Internal System Gateways",
        "Integration Architecture: External Banking & Government Portals", "Data Migration Strategy: ETL Framework & Tools",
        "Data Migration Strategy: Data Cleaning, Validation & Reconciliation", "Implementation Strategy: Phased Rollout Plan",
        "Implementation Strategy: Detailed Project Timeline (Milestone-wise)", "Implementation Strategy: Training & Knowledge Transfer Plan",
        "Project Governance: Organizational Structure & Resource Deployment", "Project Governance: Risk Management & Mitigation Framework",
        "Testing Strategy: Unit, Integration & UAT Framework", "Testing Strategy: Performance, Security & Stress Testing",
        "Change Management & Adoption Strategy", "Operations & Maintenance: Support Model & Helpdesk",
        "Security Framework: Application, Network & Data Security", "Compliance Framework: Statutory & Regulatory Compliance",
        "Service Level Agreements (SLA), KPIs & Conclusion"
    ]

    from sqlalchemy import desc
    latest_v = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).order_by(desc(RFPDraft.version)).first()
    next_version = (latest_v.version + 1) if (latest_v and db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id, RFPDraft.version == latest_v.version).count() >= len(sections)) else (latest_v.version if latest_v else 1)

    try:
        rfp.current_status = "generating_draft"
        db.commit()

        for i, title in enumerate(sections):
            db.refresh(rfp)
            if rfp.current_status != "generating_draft": break
            
            # Resume check
            if db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id, RFPDraft.version == next_version, RFPDraft.section_name == title).first():
                continue

            # NEW: Robust retry logic for automatic document completion
            max_section_retries = 5
            for attempt in range(max_section_retries):
                res = generate_proposal_section(db, rfp_id, title, i+1, rfp.uploaded_by, version=next_version)
                if res is not None:
                    break
                
                if attempt < max_section_retries - 1:
                    wait_time = 30 * (attempt + 1)
                    print(f"Section '{title}' failed. Retrying in {wait_time}s... (Attempt {attempt+1})")
                    time.sleep(wait_time)
                else:
                    # Only if all retries fail, then we stop
                    rfp.current_status = "rate_limit_error"
                    db.commit()
                    return {"error": "Generation failed after multiple retries at section " + title}
            
            # Standard delay between successful sections to maintain RPM
            time.sleep(15) 

        create_notification(db, user_id=rfp.uploaded_by, message=f"Drafting complete for {rfp.title}.", rfp_id=rfp_id, type="success")
        return {"status": "success", "rfp_id": rfp_id}
    except Exception as e:
        return {"error": str(e)}

def extract_compliance_matrix(db: Session, rfp_id: int) -> dict:
    from app.models.rfp import RFPRequirement
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp or not rfp.gemini_file_uri: return {"error": "Document context missing"}

    # Compliance extraction happens during 'generating_draft' or 'extracting_metrics' phase
    # We keep the status stable to avoid UI flickering during the fast compliance step
    # but we can update the message.
    rfp.status_message = "Extracting compliance requirements..."
    db.commit()

    prompt = """
Analyze this RFP and extract a compliance matrix. Return ONLY a JSON list:
[{"requirement_text": "...", "status": "compliant", "response_strategy": "...", "notes": "...", "category": "..."}]
"""
    try:
        file = ensure_gemini_file(db, rfp)
        response = call_gemini_with_retry(db=db, content=[file, prompt], task_name="compliance_extraction")
        items = clean_json(response.text)
        if not items: items = []

        db.query(RFPRequirement).filter(RFPRequirement.rfp_id == rfp_id).delete()
        for item in items:
            req = RFPRequirement(
                rfp_id=rfp_id, requirement_text=item.get("requirement_text"),
                status=item.get("status", "pending"), response_strategy=item.get("response_strategy"),
                notes=item.get("notes"), category=item.get("category", "technical")
            )
            db.add(req)
        
        db.commit()
        return {"status": "success", "count": len(items)}
    except Exception as e:
        db.rollback()
        print(f"Compliance failed: {str(e)}")
        return {"error": str(e)}

def chat_with_document(db: Session, rfp_id: int, user_id: int, message: str, knowledge_mode: str = "hybrid", history: list = None) -> dict:
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    user_role = user.role if user else "PM"

    # 1. Local Intent Check
    local_reply = detect_local_chat_intent(message, user_role)
    if local_reply:
        chat_log = ChatHistory(
            rfp_id=rfp_id, user_id=user_id, role="user", message=message,
            response=local_reply, source_context_used="local", handled_locally=True, tokens_used=0, provider_used="local"
        )
        db.add(chat_log)
        db.commit()
        return {"reply": local_reply, "metadata": {"source": "local", "handled_locally": True, "tokens_used": 0, "provider": "local"}}

    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp: return {"reply": "Error: Document not found."}

    # PART 1: Ensure Gemini file is available before any deep reasoning (re-upload if expired)
    try:
        from app.services.context_service import ensure_gemini_file_available
        ensure_gemini_file_available(rfp_id, db)
        db.refresh(rfp)
    except Exception as gu:
        print(f"[ai_service] Gemini URI pre-check failed (non-fatal): {gu}")

    # 1b. Local Fact Check (Simple DB fields)

    msg_lower = message.lower()
    try:
        if any(k in msg_lower for k in ['deadline', 'due date', 'when is it due']):
            metadata = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
            if metadata and metadata.deadline:
                deadline_str = metadata.deadline.strftime("%Y-%m-%d")
                reply = f"The deadline for this RFP is {deadline_str}."
            else:
                reply = "The deadline was not confidently extracted from this RFP. Please verify it from the uploaded document."
            
            chat_log = ChatHistory(rfp_id=rfp_id, user_id=user_id, role="user", message=message, response=reply, source_context_used="postgres", handled_locally=True, tokens_used=0, provider_used="local_db")
            db.add(chat_log); db.commit()
            return {"reply": reply, "metadata": {"source": "postgres", "handled_locally": True, "tokens_used": 0, "provider": "local_db"}}
        
        if any(k in msg_lower for k in ['client', 'organization', 'who is this for']):
            client_name_val = rfp.client_name if rfp.client_name else "not clearly identified"
            reply = f"This RFP is for {client_name_val}."
            chat_log = ChatHistory(rfp_id=rfp_id, user_id=user_id, role="user", message=message, response=reply, source_context_used="postgres", handled_locally=True, tokens_used=0, provider_used="local_db")
            db.add(chat_log); db.commit()
            return {"reply": reply, "metadata": {"source": "postgres", "handled_locally": True, "tokens_used": 0, "provider": "local_db"}}
    except Exception as e:
        print(f"Error in local fact check: {e}")
        # Fall through to intelligence/AI path

    # 1c. Stored RFP Intelligence Check (Summary JSON)
    intelligence_hits = {
        'risk': 'risks', 'compliance': 'compliance_summary', 'mandatory': 'mandatory_clauses',
        'commercial': 'commercial_terms', 'payment': 'commercial_terms', 
        'effort': 'effort_estimate', 'estimate': 'effort_estimate',
        'executive summary': 'executive_summary', 'recommend': 'recommended_action',
        'go-no-go': 'go_no_go', 'next steps': 'next_steps'
    }
    
    matched_key = next((k for k in intelligence_hits if k in msg_lower), None)
    if matched_key and rfp.summary_json:
        try:
            summary_data = json.loads(rfp.summary_json)
            field_name = intelligence_hits[matched_key]
            field_value = summary_data.get(field_name)
            
            if field_value:
                source_used = "stored_intelligence"
                # Use Azure for wording/explanation of stored context
                azure_prompt = f"The following is extracted intelligence from the RFP for '{field_name}': {json.dumps(field_value)}\n\nUser Question: {message}\n\nPlease explain or summarize this clearly for the user. Mention that this is based on pre-extracted document insights."
                
                ai_res = None
                try:
                    ai_res = call_ai(db, "chat_basic_db", azure_prompt)
                except Exception as az_err:
                    print(f"Azure Intelligence Path failed: {az_err}. Falling back to raw DB content.")
                
                if ai_res:
                    reply_text = ai_res["text"]
                    provider_final = "azure"
                    tokens_final = ai_res.get("tokens_used", 0)
                else:
                    # Raw DB fallback
                    reply_text = f"I found the stored RFP analysis for {field_name}, but the explanation service is temporarily unavailable. Here are the extracted details:\n\n{json.dumps(field_value, indent=2)}"
                    provider_final = "stored_intelligence_fallback"
                    tokens_final = 0

                chat_log = ChatHistory(
                    rfp_id=rfp_id, user_id=user_id, role="user", message=message,
                    response=reply_text, source_context_used=source_used, handled_locally=False,
                    tokens_used=tokens_final, provider_used=provider_final
                )
                db.add(chat_log); db.commit()
                return {
                    "reply": reply_text, 
                    "metadata": {
                        "source": source_used, 
                        "handled_locally": False, 
                        "tokens_used": tokens_final, 
                        "provider": provider_final
                    }
                }
        except Exception as e:
            print(f"Error in intelligence routing: {e}")


    # 2. Context Layering for general chat
    context_parts = []
    source_used = "db"
    task_type = "chat_basic_db"
    
    # Layer 1: PostgreSQL Metadata
    metadata = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
    if rfp.summary_json:
        context_parts.append("RFP Intelligence Summary:\n" + rfp.summary_json)
    if metadata and metadata.budget:
        context_parts.append(f"Budget: {metadata.budget} {metadata.currency}")
    
    # Layer 2: Generated Drafts (if any)
    drafts = db.query(RFPDraft).filter(RFPDraft.rfp_id == rfp_id).all()
    if drafts:
        source_used = "generated_sections"
        draft_summary = "\n".join([f"Section {d.section_name}: {len(d.draft_content.split())} words" for d in drafts])
        context_parts.append(f"Generated Sections Info:\n{draft_summary}")

    # Layer 3: Deep Document Reasoning
    # Gemini only for clause-level lookup or full original document reasoning
    deep_triggers = ['clause', 'section number', 'find all', 'compare', 'verify', 'extract full text']
    needs_deep = any(t in msg_lower for t in deep_triggers) or "hybrid" in knowledge_mode.lower()
    
    is_insufficient = False
    if rfp.summary_json:
        try: is_insufficient = json.loads(rfp.summary_json).get("document_quality") == "insufficient_rfp_detail"
        except: pass
    if is_insufficient: needs_deep = False
    
    system_prompt = f"You are an AI {user_role}. Answer based on the provided context. Format with Markdown."
    
    prompt_parts = [f"Instruction: {system_prompt}"]
    if history:
        history_text = "\n".join([f"{m['role'].upper()}: {m['text']}" for m in history if m.get('text')])
        prompt_parts.append(f"History:\n{history_text}")
        
    prompt_parts.append(f"User Context:\n" + "\n".join(context_parts))
    prompt_parts.append(f"User: {message}")
    
    try:
        # Decide provider
        if needs_deep:
            source_used = "gemini_file"
            task_type = "chat_deep_rfp"
            cache = get_or_create_cache(db, rfp_id)
            if cache:
                ai_res = call_ai(db, task_type, "\n".join(prompt_parts), cache_name=cache.name)
            else:
                file = ensure_gemini_file(db, rfp)
                if file:
                    ai_res = call_ai(db, task_type, "\n".join(prompt_parts), context=[file])
                else:
                    ai_res = call_ai(db, "chat_basic_db", "\n".join(prompt_parts))
        else:
            # Default to Azure for general context-based questions
            ai_res = call_ai(db, task_type, "\n".join(prompt_parts))

        # 3. Save History
        chat_log = ChatHistory(
            rfp_id=rfp_id, user_id=user_id, role="user", message=message,
            response=ai_res["text"], source_context_used=source_used, handled_locally=False, 
            tokens_used=ai_res.get("tokens_used", 0), provider_used=ai_res.get("provider_used", "unknown")
        )
        db.add(chat_log)
        db.commit()

        return {
            "reply": ai_res["text"], 
            "metadata": {
                "source": source_used, 
                "handled_locally": False, 
                "tokens_used": ai_res.get("tokens_used", 0), 
                "provider": ai_res.get("provider_used", "unknown"),
                "model": ai_res.get("model_used", ""),
                "fallback_used": ai_res.get("fallback_used", False)
            }
        }
    except Exception as e:
        print(f"Chat error for RFP {rfp_id}: {str(e)}")
        error_reply = "I couldn’t reach the AI provider for this request. Please try again, or use stored RFP insights while the provider is unavailable."
        return {"reply": error_reply, "metadata": {"source": "error", "error": True}}


def stream_chat_with_document(db: Session, rfp_id: int, user_id: int, message: str, knowledge_mode: str = "hybrid", history: list = None):
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    user_role = user.role if user else "PM"

    # 1. Local Intent Check (Greetings/Help)
    local_reply = detect_local_chat_intent(message, user_role)

    # 1b. Local Fact Check (Simple DB fields)
    msg_lower = message.lower()
    if not local_reply:
        try:
            if any(k in msg_lower for k in ['deadline', 'due date', 'when is it due']):
                metadata = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
                if metadata and metadata.deadline:
                    deadline_str = metadata.deadline.strftime("%Y-%m-%d")
                    local_reply = f"The deadline for this RFP is {deadline_str}."
                else:
                    local_reply = "The deadline was not confidently extracted from this RFP. Please verify it from the uploaded document."
            elif any(k in msg_lower for k in ['client', 'organization', 'who is this for']):
                rfp_tmp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
                client_name_val = rfp_tmp.client_name if rfp_tmp and rfp_tmp.client_name else "not clearly identified"
                local_reply = f"This RFP is for {client_name_val}."
        except Exception as e:
            print(f"Error in stream local fact check: {e}")

    if local_reply:
        print(f"Chat handled locally before streaming provider call. provider=local tokens=0")
        chat_log = ChatHistory(
            rfp_id=rfp_id, user_id=user_id, role="user", message=message,
            response=local_reply, source_context_used="local", handled_locally=True, tokens_used=0, provider_used="local"
        )
        db.add(chat_log); db.commit()
        # Use module-level json (no inline import — that caused the UnboundLocalError)
        yield f"event: message\ndata: {json.dumps({'content': local_reply, 'provider_used': 'local', 'tokens_used': 0, 'handled_locally': True})}\n\n"
        yield f"event: done\ndata: {json.dumps({'provider_used': 'local', 'tokens_used': 0, 'handled_locally': True})}\n\n"
        return

    # 1c. Stored RFP Intelligence Check (Summary JSON)
    # BUG 2 FIX: Intelligence hits NEVER fall through to Gemini.
    # If they fail, return a clean fallback — not Gemini full-document.
    intelligence_hits = {
        'risk': 'risks', 'compliance': 'compliance_summary', 'mandatory': 'mandatory_clauses',
        'commercial': 'commercial_terms', 'payment': 'commercial_terms',
        'effort': 'effort_estimate', 'estimate': 'effort_estimate',
        'executive summary': 'executive_summary', 'recommend': 'recommended_action',
        'go-no-go': 'go_no_go', 'next steps': 'next_steps'
    }

    matched_key = next((k for k in intelligence_hits if k in msg_lower), None)
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()

    if matched_key and rfp:
        # This is an intelligence query — NEVER fall through to Gemini
        field_name = intelligence_hits[matched_key]
        intelligence_reply = None
        provider_final = "stored_intelligence_fallback"
        tokens_final = 0

        if rfp.summary_json:
            try:
                # BUG 1 FIX: Use module-level json, not inline import
                summary_data = json.loads(rfp.summary_json)
                field_value = summary_data.get(field_name)

                if field_value:
                    # Try Azure explanation
                    azure_prompt = (
                        f"The following is extracted intelligence from the RFP for '{field_name}': "
                        f"{json.dumps(field_value)}\n\nUser Question: {message}\n\n"
                        f"Please explain or summarize this clearly for the user. Mention that this is based on pre-extracted document insights."
                    )
                    try:
                        ai_res = call_ai(db, "chat_basic_db", azure_prompt)
                        intelligence_reply = ai_res["text"]
                        provider_final = "azure"
                        tokens_final = ai_res.get("tokens_used", 0)
                    except Exception as az_err:
                        print(f"[stream] Azure Intelligence Path failed: {az_err}. Using raw DB content.")
                        print("[stream] Stored intelligence fallback used. Gemini skipped.")
                        intelligence_reply = (
                            f"Based on pre-extracted insights from this RFP:\n\n"
                            f"**{field_name.replace('_', ' ').title()}:**\n\n"
                            f"{json.dumps(field_value, indent=2)}"
                        )
                        provider_final = "stored_intelligence_fallback"
                else:
                    intelligence_reply = (
                        f"{field_name.replace('_', ' ').title()} data was not extracted from this RFP. "
                        f"Please run the analysis or verify the uploaded document."
                    )
            except Exception as parse_err:
                print(f"[stream] Error parsing summary_json: {parse_err}")
                intelligence_reply = (
                    f"Stored analysis data could not be read for '{field_name}'. "
                    f"Please re-run the RFP analysis."
                )
        else:
            intelligence_reply = (
                f"{field_name.replace('_', ' ').title()} analysis is not available yet. "
                f"Please run analysis or verify the uploaded RFP."
            )

        # Save and yield — do NOT fall through to Gemini
        try:
            chat_log = ChatHistory(
                rfp_id=rfp_id, user_id=user_id, role="user", message=message,
                response=intelligence_reply, source_context_used="stored_intelligence",
                handled_locally=False, tokens_used=tokens_final, provider_used=provider_final
            )
            db.add(chat_log); db.commit()
        except Exception as log_err:
            print(f"[stream] Chat log save failed (non-fatal): {log_err}")

        print(f"[stream] Stored intelligence fallback used. Gemini skipped. provider={provider_final}")
        yield f"event: message\ndata: {json.dumps({'content': intelligence_reply, 'provider_used': provider_final, 'tokens_used': tokens_final, 'handled_locally': False})}\n\n"
        yield f"event: done\ndata: {json.dumps({'provider_used': provider_final, 'tokens_used': tokens_final, 'handled_locally': False})}\n\n"
        return

    if not rfp:
        yield "event: message\ndata: {\"content\": \"Error: Document not found.\"}\n\n"
        yield "event: done\ndata: {}\n\n"
        return

    # 2. Deep document reasoning — Gemini ONLY for explicit clause/section queries
    deep_triggers = ['clause', 'section number', 'find all', 'compare', 'verify', 'extract full text', 'analyze section', 'search full']
    needs_deep = any(t in msg_lower for t in deep_triggers)
    
    is_insufficient = False
    if rfp.summary_json:
        try: is_insufficient = json.loads(rfp.summary_json).get("document_quality") == "insufficient_rfp_detail"
        except: pass
    if is_insufficient: needs_deep = False

    system_prompt = f"You are an AI {user_role}. Use the context to answer."
    try:
        prompt_parts = [f"Instruction: {system_prompt}"]

        context_parts = []
        if rfp.summary_json:
            context_parts.append("RFP Intelligence Summary:\n" + rfp.summary_json)

        if history:
            history_text = "\n".join([f"{m['role'].upper()}: {m['text']}" for m in history if m.get('text')])
            prompt_parts.append(f"History:\n{history_text}")

        prompt_parts.append("User Context:\n" + "\n".join(context_parts))
        prompt_parts.append(f"User: {message}")

        if needs_deep:
            # Gemini allowed for deep document reasoning
            print(f"Using Gemini model: {settings.GEMINI_MODEL} (Streaming) — deep document query")
            print(f"Task: chat_stream_deep")
            track_quota_usage(db)
            cache = get_or_create_cache(db, rfp_id)
            if cache:
                response = gemini_client.models.generate_content_stream(
                    model=settings.GEMINI_MODEL, contents=prompt_parts,
                    config={"cached_content": cache.name}
                )
            else:
                file = ensure_gemini_file(db, rfp)
                if file:
                    response = gemini_client.models.generate_content_stream(
                        model=settings.GEMINI_MODEL, contents=[file] + prompt_parts
                    )
                else:
                    response = gemini_client.models.generate_content_stream(
                        model=settings.GEMINI_MODEL, contents=prompt_parts
                    )
        else:
            # General context question — use Azure (not Gemini)
            print(f"Task: chat_stream_azure — general context question, using Azure")
            combined_prompt = "\n".join(prompt_parts)
            ai_res = call_ai(db, "chat_basic_db", combined_prompt)
            reply_text = ai_res.get("text", "")
            chat_log = ChatHistory(
                rfp_id=rfp_id, user_id=user_id, role="user", message=message,
                response=reply_text, source_context_used="db", handled_locally=False,
                tokens_used=ai_res.get("tokens_used", 0), provider_used=ai_res.get("provider_used", "azure")
            )
            db.add(chat_log); db.commit()
            yield f"event: message\ndata: {json.dumps({'content': reply_text, 'provider_used': 'azure', 'tokens_used': ai_res.get('tokens_used', 0), 'handled_locally': False})}\n\n"
            yield f"event: done\ndata: {json.dumps({'provider_used': 'azure'})}\n\n"
            return

        acc_text = ""
        for chunk in response:
            if chunk.text:
                acc_text += chunk.text
                yield chunk.text

        chat_log = ChatHistory(
            rfp_id=rfp_id, user_id=user_id, role="user", message=message,
            response=acc_text, source_context_used="gemini_stream", handled_locally=False,
            tokens_used=0, provider_used="gemini"
        )
        db.add(chat_log); db.commit()

    except Exception as e:
        yield f"Error: {str(e)}"



