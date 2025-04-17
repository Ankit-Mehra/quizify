import fitz  # PyMuPDF
import os
import tempfile
from docx import Document

def extract_text_from_pdf(contents):
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
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as temp:
        temp.write(contents)
        temp_path = temp.name
    
    try:
        # Open the document and extract text
        doc = Document(temp_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        print(f"Error extracting text from DOCX: {str(e)}")
        return "Failed to extract text from document"
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)

def extract_text_from_plain_text(contents):
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
    return bytes_data.startswith(b"%PDF")

