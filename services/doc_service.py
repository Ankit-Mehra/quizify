import fitz  # PyMuPDF
import os

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

def extract_text_from_plain_text(contents):
    return contents.decode("utf-8")