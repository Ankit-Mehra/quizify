import os
import httpx
import uuid
from fastapi import HTTPException, Depends
from supabase import create_client, Client
from datetime import datetime
from dependencies.auth_helper import get_current_user_id
from services.ai_services.doc_service import extract_text_from_pdf, is_pdf
STORAGE_NAME = os.getenv("SUPABASE_STORAGE_NAME")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(
    supabase_url=SUPABASE_URL,
    supabase_key=SUPABASE_KEY
)

def save_file_to_supabase(user_id: str, file_bytes: bytes, original_filename: str, token: str, file_type: str):
    try:
        #genereate a unique ID
        unique_id = str(uuid.uuid4())
        file_name = f"{unique_id}_{original_filename}"
        path = f"{user_id}/{file_name}"

        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }

        response = httpx.post(url, content=file_bytes, headers=headers)
        response.raise_for_status()

        #save metadata to db
        supabase.table("user_files").insert({
            "id": unique_id,
            "user_id": user_id,
            "original_filename": original_filename,
            "file_type": file_type,
            "storage_path": path,
            "uploaded_at": datetime.now().isoformat()
        }).execute()
        return response.json()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_file_metadata(user_id: str = Depends(get_current_user_id)):
    try:
        metadata = supabase.table("user_files").select("*").eq("user_id", user_id).execute()
        return {
            "files": metadata.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_file_record(file_id: str):
    try:
        file_data = supabase.table("user_files").select("*").eq("id", file_id).single().execute()
        return file_data.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def create_presigned_url(file_id: str, user_id: str = Depends(get_current_user_id)):
    try:
        file_data = get_file_record(file_id)
        if not file_data:
            raise HTTPException(status_code=404, detail="File not found")
        
        if file_data[0]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized")

        path = file_data[0]["storage_path"]
        signed_url = supabase.storage.from_(STORAGE_NAME).create_signed_url(path, expires_in=300)
        return {
            "url": signed_url["signedURL"],
            "expires_in": 300
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
def read_file_content(path: str, token: str):
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }

        response = httpx.get(url, headers=headers)
        response.raise_for_status()
        return response.content
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_file_from_supabase(file_record: dict, user_token: str) -> str:
    """
    Returns the text from either a PDF or text file stored in supabase
    based on the file's content type or extension.
    """
    file_path = file_record["storage_path"]
    file_type = file_record.get("file_type", "")  # e.g. 'application/pdf'

    file_bytes = read_file_content(file_path, user_token)

    # Approach A: Use stored mime-type or extension
    if file_type == "application/pdf":
        return extract_text_from_pdf(file_bytes)
    elif file_type.startswith("text/"):
        return file_bytes.decode("utf-8", errors="ignore")
    else:
        # fallback: check the raw bytes
        if is_pdf(file_bytes):
            return extract_text_from_pdf(file_bytes)
        else:
            # assume text or handle docx, etc.
            return file_bytes.decode("utf-8", errors="ignore")
