import os
import PyPDF2
from docx import Document

def extract_full_text(file_path: str, file_type: str) -> str:
    """
    Extracts the entire text content from a file based on its extension.
    Supported types: pdf, docx, txt
    """
    text = ""
    try:
        if file_type == "pdf":
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages_text = []
                for page in reader.pages:
                    content = page.extract_text()
                    if content:
                        pages_text.append(content)
                text = "\n".join(pages_text)
        
        elif file_type == "docx":
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
        
        elif file_type == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from {file_path}: {str(e)}")
        return ""
