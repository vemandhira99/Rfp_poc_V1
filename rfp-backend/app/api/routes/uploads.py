from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.api.routes.auth import get_current_user
from app.models.rfp import RFPDocument, AuditLog
from app.services.parsing_service import run_parsing
from app.services.ai_service import generate_summary
from app.utils.text_extraction import extract_full_text
import os, time

router = APIRouter(prefix="/uploads", tags=["Uploads"])

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt"
}

@router.post("/rfp")
async def upload_rfp(
    title: str = Form(...),
    client_name: str = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, TXT files allowed")

    contents = await file.read()
    size_kb = len(contents) / 1024
    if size_kb > (settings.MAX_FILE_SIZE_MB * 1024):
        raise HTTPException(status_code=400, detail=f"File too large. Max {settings.MAX_FILE_SIZE_MB}MB")

    ext = ALLOWED_TYPES[file.content_type]
    safe_name = f"{int(time.time())}_{file.filename.replace(' ', '_')}"
    file_path = os.path.join(settings.UPLOAD_DIR, safe_name)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(contents)

    rfp = RFPDocument(
        title=title, client_name=client_name, uploaded_by=current_user.id,
        file_path=file_path, file_name=file.filename, file_type=ext,
        file_size_kb=int(size_kb), current_status="uploaded"
    )
    db.add(rfp)
    log = AuditLog(user_id=current_user.id, action="rfp_uploaded", new_value=title)
    db.add(log)
    db.commit()
    db.refresh(rfp)

    return {
        "message": "RFP uploaded successfully",
        "document_id": rfp.id,
        "file_name": rfp.file_name,
        "file_type": rfp.file_type,
        "size_kb": rfp.file_size_kb,
        "status": rfp.current_status
    }

def process_rfp_background(rfp_id: int):
    from app.core.database import SessionLocal
    from app.core.config import settings
    from app.models.rfp import BackgroundJob, RFPMetadata, RFPRequirement, RFPDocument
    from google import genai
    from app.services.ai_service import ensure_gemini_file, call_ai, clean_json
    from app.utils.text_extraction import extract_full_text
    from app.services.ai_service import generate_summary
    from datetime import datetime
    
    db = SessionLocal()
    try:
        rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
        if not rfp: return

        # 1. Initialize Job
        job = db.query(BackgroundJob).filter(BackgroundJob.rfp_id == rfp_id, BackgroundJob.job_type == "analysis").first()
        if not job:
            job = BackgroundJob(rfp_id=rfp_id, job_type="analysis", status="running", total_steps=5, current_step="Starting analysis", progress_percentage=10)
            db.add(job)
        else:
            job.status = "running"
            job.progress_percentage = 10
        db.commit()

        rfp.current_status = "analysis_running"
        db.commit()


        # Stage 1: Full text extraction (Fast)
        job.current_step = "Extracting text"
        job.progress_percentage = 20
        db.commit()
        if not rfp.full_text:
            rfp.full_text = extract_full_text(rfp.file_path, rfp.file_type)
            db.commit()

        # Stage 2: Basic metadata extraction (Fast, Hybrid)
        job.current_step = "Extracting basic metadata"
        job.progress_percentage = 40
        db.commit()
        
        prompt = """Extract basic metadata from this text as JSON: 
{"title": "...", "client_name": "...", "deadline": "YYYY-MM-DD", "value": "...", "project_overview": "..."}"""
        
        metadata_res = call_ai(db, "metadata_extraction", prompt, context=[rfp.full_text[:30000] if rfp.full_text else ""])
        try:
            m_json = clean_json(metadata_res["text"])
            if m_json:
                rfp.title = m_json.get("title", rfp.title)
                rfp.client_name = m_json.get("client_name", rfp.client_name)
                
                # Save to RFPMetadata
                m_data = db.query(RFPMetadata).filter(RFPMetadata.rfp_id == rfp_id).first()
                if not m_data:
                    m_data = RFPMetadata(rfp_id=rfp_id)
                    db.add(m_data)
                
                if m_json.get("value"):
                    try:
                        import re
                        num = re.sub(r'[^\d.]', '', m_json["value"])
                        if num: m_data.estimated_value = float(num)
                    except: pass
                db.commit()
        except Exception as e:
            print("Metadata extraction error:", e)

        # Stage 3: Deep Document Reasoning (Gemini)
        job.current_step = "Uploading to deep analysis engine"
        job.progress_percentage = 60
        db.commit()
        
        ensure_gemini_file(db, rfp)
        
        job.current_step = "Synthesizing executive summary"
        job.progress_percentage = 80
        db.commit()
        
        summary_result = generate_summary(db, rfp_id)
        if summary_result.get("status") == "error":
            raise Exception(summary_result.get("error"))

        # Stage 4: Requirements & Compliance Extracted
        job.current_step = "Finalizing analysis"
        job.progress_percentage = 95
        db.commit()

        # We can extract compliance requirements here or let it be on-demand
        from app.services.ai_service import extract_compliance_matrix
        extract_compliance_matrix(db, rfp_id)

        # Stage 5: Done
        job.current_step = "Analysis complete"
        job.progress_percentage = 100
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        
        rfp.current_status = "ready_for_pm_review"
        db.commit()

    except Exception as e:
        print(f"Background processing failed for RFP {rfp_id}: {str(e)}")
        if 'job' in locals() and job:
            job.status = "failed"
            job.internal_error = str(e)
            job.failed_at = datetime.utcnow()
        rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
        if rfp:
            rfp.current_status = "error"
            rfp.status_message = "Analysis failed. Please try again."
        db.commit()
    finally:
        db.close()

@router.post("/rfp/{rfp_id}/parse")
def parse_rfp(rfp_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
              current_user = Depends(get_current_user)):
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp:
        raise HTTPException(status_code=404, detail="RFP not found")

    # Step 1: Run parsing synchronously (extracts text & calculates richness)
    parse_result = run_parsing(db, rfp_id)
    
    # Reload RFP since run_parsing modified it
    db.refresh(rfp)
    
    if "error" in parse_result:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {parse_result['error']}")

    quality = parse_result.get("quality", "insufficient_rfp_detail")
    
    # Step 2: Quality Guards
    if quality == "insufficient_rfp_detail":
        return {
            "message": "Document contains insufficient detail for full analysis.",
            "rfp_id": rfp_id,
            "status": "needs_more_detail",
            "quality": "insufficient_rfp_detail"
        }
    
    if quality == "extraction_failed_or_scanned_pdf":
        return {
            "message": "Text extraction failed or document is scanned/image-based.",
            "rfp_id": rfp_id,
            "status": "extraction_needs_review",
            "quality": "extraction_failed_or_scanned_pdf"
        }

    # Step 3: Valid Document -> Queue Analysis
    rfp.current_status = "analysis_queued"
    db.commit()
    
    background_tasks.add_task(process_rfp_background, rfp_id)

    
    return {"message": "RFP analysis started in background.", "rfp_id": rfp_id, "status": "analysis_queued", "quality": quality}



@router.get("/rfp/{rfp_id}/sections")
def get_sections(rfp_id: int, db: Session = Depends(get_db),
                 current_user = Depends(get_current_user)):
    from app.models.sections import RFPSection
    sections = db.query(RFPSection).filter(RFPSection.rfp_id == rfp_id).all()
    return [{"id": s.id, "section_name": s.section_name,
             "section_text": s.section_text[:200] + "..." if s.section_text and len(s.section_text) > 200 else s.section_text,
             "page_number": s.page_number, "confidence": float(s.confidence or 0)} for s in sections]

@router.get("/rfp/{rfp_id}/download")
def download_rfp(rfp_id: int, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    rfp = db.query(RFPDocument).filter(RFPDocument.id == rfp_id).first()
    if not rfp or not rfp.file_path or not os.path.exists(rfp.file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(rfp.file_path, filename=rfp.file_name)