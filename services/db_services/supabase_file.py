import httpx
import uuid
from fastapi import HTTPException, Depends
from datetime import datetime
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from services.ai_services.doc_service import extract_text_from_pdf, is_pdf
import logging
from config import config

logger = logging.getLogger(__name__)

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return config.get_supabase_client()

# Use centralized configuration
STORAGE_NAME = config.STORAGE_NAME
SUPABASE_URL = config.SUPABASE_URL

def save_file_to_supabase(user_id: str, file_bytes: bytes, original_filename: str, token: str, file_type: str):
    try:
        # Use authenticated client for RLS enforcement on database operations
        from config import config as app_config
        supabase = app_config.get_authenticated_supabase_client(token)
        logger.info(f"Using authenticated client to save file for user {user_id}")
        
        #genereate a unique ID
        unique_id = str(uuid.uuid4())
        file_name = f"{unique_id}_{original_filename}"
        path = f"{user_id}/{file_name}"

        # Upload to storage using httpx with explicit auth header
        # This ensures the user token is sent for storage bucket RLS policies
        try:
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": file_type
            }
            
            logger.info(f"Uploading file to storage: {upload_url}")
            response = httpx.post(upload_url, headers=headers, content=file_bytes)
            
            if response.status_code != 200:
                logger.error(f"Storage upload failed with status {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to upload file to storage: {response.text}"
                )
            
            logger.info(f"File uploaded successfully to storage: {path}")
            
        except HTTPException:
            raise
        except Exception as storage_error:
            logger.error(f"Storage upload error: {str(storage_error)}")
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to upload file to storage: {str(storage_error)}"
            )

        #save metadata to db using authenticated client
        if supabase is None:
            raise HTTPException(status_code=500, detail="Supabase client is not initialized. Check your configuration.")
        
        file_size = len(file_bytes)
        logger.info(f"Saving file metadata to database for file {unique_id}")
        supabase.table("user_files").insert({
            "id": unique_id,
            "user_id": user_id,
            "original_filename": original_filename,
            "file_type": file_type,
            "file_size_bytes": file_size,  # Add file size
            "storage_path": path,
            "uploaded_at": datetime.now().isoformat()
        }).execute()
        
        logger.info("File metadata saved successfully")
        
        # Return the file_id so caller can link it to quiz
        return {"file_id": unique_id, "storage_path": path}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in save_file_to_supabase: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def get_file_metadata(user_id: str = Depends(get_current_user_id)):
    try:
        supabase = get_supabase()
        if supabase is None:
            raise HTTPException(status_code=500, detail="Supabase client is not initialized. Check your configuration.")
        metadata = supabase.table("user_files").select("*").eq("user_id", user_id).execute()
        return {
            "files": metadata.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_file_record(file_id: str):
    try:
        supabase = get_supabase()
        if supabase is None:
            raise HTTPException(status_code=500, detail="Supabase client is not initialized. Check your configuration.")
        file_data = supabase.table("user_files").select("*").eq("id", file_id).execute()
        
        # Check if we got any results
        if not file_data.data or len(file_data.data) == 0:
            logger.warning(f"No file found with ID: {file_id}")
            return None
            
        # Return the first record as a dictionary
        return file_data.data[0]
    except Exception as e:
        logger.error(f"Error retrieving file record: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving file record: {str(e)}")
    
def create_presigned_url(file_id: str, user_id: str = Depends(get_current_user_id), token: str = Depends(get_current_user_token)):
    try:
        logger.info(f"Creating presigned URL for file {file_id}")
        logger.info(f"User ID: {user_id}")

        file_record = get_file_record(file_id)
        logger.info(f"File data: {file_record}")
        
        if not file_record:
            logger.error("File record not found in database")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Verify user has access to this file
        if file_record["user_id"] != user_id:
            logger.error("User not authorized to access this file")
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Get storage path
        storage_path = file_record["storage_path"]
        logger.info(f"Storage path: {storage_path}")
        
        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            response = httpx.post(
                f"{SUPABASE_URL}/storage/v1/object/sign/{STORAGE_NAME}/{storage_path}",
                headers=headers,
                json={
                    "expiresIn": 300,
                    "download": True
                }
            )
            
            response.raise_for_status()
            return {
                "url": f"{SUPABASE_URL}/storage/v1{response.json()['signedURL']}",
                "expires_in": 300
            }
        
        except Exception as e:
            logger.error(f"Detailed storage error: {str(e)}")
            
            # Check if this is a 404 error (file not found)
            error_str = str(e)
            if "'statusCode': 404" in error_str and "Object not found" in error_str:
                logger.error("File exists in database but not in storage")
                # Return a more user-friendly message
                raise HTTPException(
                    status_code=404, 
                    detail="The file could not be found in storage. It may have been deleted or moved."
                )
            
            if isinstance(e, httpx.HTTPStatusError) and hasattr(e.response, 'content'):
                logger.error(f"Error response content: {e.response.content}")
            raise HTTPException(status_code=500, detail=f"Error accessing file: {str(e)}")
    
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Unexpected error in create_presigned_url: {str(e)}")
        if hasattr(e, '__dict__'):
            logger.error(f"Error details: {e.__dict__}")
        raise HTTPException(status_code=500, detail=str(e))
    
def read_file_content(path: str, token: str):
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }

        response = httpx.get(url, headers=headers)
        
        if response.status_code == 404:
            raise HTTPException(
                status_code=404, 
                detail=f"File not found in storage. Please check if it was deleted or the path is correct: {path}"
            )
            
        response.raise_for_status()
        
        # Successful retrieval

        return response.content
    
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404, 
                detail="File not found in storage"
            )
        raise HTTPException(status_code=e.response.status_code, detail=f"Storage service error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_file_from_supabase(file_record: dict, user_token: str) -> str:
    """
    Returns the text from either a PDF or text file stored in supabase
    based on the file's content type or extension.
    """
    try:
        if not file_record or not isinstance(file_record, dict):
            raise Exception("Invalid or missing file record")
            
        if "storage_path" not in file_record:
            raise Exception("File record is missing storage_path")
            
        file_path = file_record["storage_path"]
        file_type = file_record.get("file_type", "")  # e.g. 'application/pdf'
        
        try:
            file_bytes = read_file_content(file_path, user_token)
            
            if not file_bytes:
                raise Exception("Could not read file content from storage")
    
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
        except HTTPException as he:
            if he.status_code == 404:
                # File not found in storage - provide a clear error
                logger.error(f"File not found in storage: {file_path}")
                raise HTTPException(
                    status_code=404,
                    detail="The file could not be found in storage. It may have been deleted."
                )
            # Re-raise other HTTP exceptions
            raise he
            
    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he
    except Exception as e:
        logger.error(f"Error parsing file content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error parsing file content: {str(e)}")

def delete_file_from_supabase(file_id: str, token: str, user_id: str, original_filename: str):
    try:
        supabase = get_supabase()
        if supabase is None:
            raise HTTPException(status_code=500, detail="Supabase client is not initialized. Check your configuration.")
        supabase.table("user_files").delete().eq("id", file_id).execute()
        delete_file_from_supabase_storage(file_id, token, user_id, original_filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def delete_file_from_supabase_storage(file_id: str, token: str, user_id: str, original_filename: str):
    try:
        file_name = f"{file_id}_{original_filename}"
        path = f"{user_id}/{file_name}"
        #using httpx to delete the file from supabase storage
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }
        response = httpx.delete(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))