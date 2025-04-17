import fitz  # PyMuPDF
import os
import tempfile
from docx import Document
from services.logger import app_logger as logger

logger.info("Doc service initialized")

def extract_text_from_pdf(contents):
    logger.info("Extracting text from PDF")
    with open("temp.pdf", "wb") as f:
        f.write(contents)

    text = ""
    doc = fitz.open("temp.pdf")
    for page in doc:
        text += page.get_text()
    doc.close()
    os.remove("temp.pdf")
    
    return text

def extract_text_from_docx(contents):
    # Create a temporary file to save the binary content
    logger.info("Extracting text from DOCX")
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp:
        temp.write(contents)
        temp_path = temp.name
    
    try:
        # Open the document and extract text
        doc = Document(temp_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        return f"Failed to extract text from document: {str(e)}"
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

def extract_text_from_plain_text(contents):
    logger.info("Extracting text from plain text")
    # Try different encodings to handle various file types
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            return contents.decode(encoding)
        except UnicodeDecodeError:
            continue
    
    # If all encodings fail, use a fallback that ignores errors
    return contents.decode('utf-8', errors='replace')

def is_pdf(bytes_data: bytes) -> bool:
    logger.info("Checking if file is PDF")
    return bytes_data.startswith(b"%PDF")

