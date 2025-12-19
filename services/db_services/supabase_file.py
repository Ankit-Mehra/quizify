import httpx
import uuid
from fastapi import HTTPException, Depends
from datetime import datetime
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from services.ai_services.doc_service import extract_text_from_pdf, is_pdf, extract_text_from_docx
import logging
from config import config as app_config

logger = logging.getLogger(__name__)

# Lazy load Supabase client to avoid initialization issues in tests
def get_supabase():
    """Get Supabase client (lazy loaded)"""
    return app_config.get_supabase_client()

# Use centralized configuration
STORAGE_NAME = app_config.STORAGE_NAME
SUPABASE_URL = app_config.SUPABASE_URL

def save_file_to_supabase(user_id: str, file_bytes: bytes, original_filename: str, token: str, file_type: str):
    """
    Synchronous wrapper for async file save operation.
    Maintained for backward compatibility with sync callers.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, we need to run in thread pool
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    save_file_to_supabase_async(user_id, file_bytes, original_filename, token, file_type)
                )
                return future.result()
        else:
            return loop.run_until_complete(
                save_file_to_supabase_async(user_id, file_bytes, original_filename, token, file_type)
            )
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(
            save_file_to_supabase_async(user_id, file_bytes, original_filename, token, file_type)
        )


async def save_file_to_supabase_async(user_id: str, file_bytes: bytes, original_filename: str, token: str, file_type: str):
    """
    Async version of file save to Supabase.
    Prefer this function in async contexts.
    """
    try:
        # Use authenticated client for RLS enforcement on database operations
        supabase = app_config.get_authenticated_supabase_client(token)
        logger.debug(f"Using authenticated client to save file for user {user_id}")
        
        #genereate a unique ID
        unique_id = str(uuid.uuid4())
        file_name = f"{unique_id}_{original_filename}"
        path = f"{user_id}/{file_name}"

        # Upload to storage using async httpx
        try:
            upload_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": file_type
            }
            
            logger.debug(f"Uploading file to storage: {upload_url}")
            async with httpx.AsyncClient() as client:
                response = await client.post(upload_url, headers=headers, content=file_bytes)
            
            if response.status_code != 200:
                logger.error(f"Storage upload failed with status {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to upload file to storage: {response.text}"
                )
            
            logger.debug(f"File uploaded successfully to storage: {path}")
            
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
        logger.debug(f"Saving file metadata to database for file {unique_id}")
        supabase.table("user_files").insert({
            "id": unique_id,
            "user_id": user_id,
            "original_filename": original_filename,
            "file_type": file_type,
            "file_size_bytes": file_size,  # Add file size
            "storage_path": path,
            "uploaded_at": datetime.now().isoformat()
        }).execute()
        
        logger.debug("File metadata saved successfully")
        
        # Return the file_id so caller can link it to quiz
        return {"file_id": unique_id, "storage_path": path}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in save_file_to_supabase: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def get_file_metadata(user_id: str = Depends(get_current_user_id), user_token: str = Depends(get_current_user_token)):
    """
    Get file metadata for a user.
    
    Args:
        user_id: The user ID to fetch files for (from auth dependency)
        user_token: User's authentication token for RLS enforcement (from auth dependency)
    """
    try:
        # Use authenticated client (enforces RLS)
        supabase = app_config.get_authenticated_supabase_client(user_token)
        
        if supabase is None:
            raise HTTPException(status_code=500, detail="Supabase client is not initialized. Check your configuration.")
        metadata = supabase.table("user_files").select("*").eq("user_id", user_id).execute()
        return {
            "files": metadata.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_file_record(file_id: str, user_token: str = None):
    """
    Get a file record by its ID.
    
    Args:
        file_id: The file ID to fetch
        user_token: User's authentication token for RLS enforcement (recommended)
                    If None, uses service role (bypasses RLS - use with caution)
    """
    try:
        # Use authenticated client if token provided (enforces RLS)
        if user_token:
            supabase = app_config.get_authenticated_supabase_client(user_token)
        else:
            supabase = get_supabase()  # Service role - bypasses RLS
        
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
        logger.debug(f"Creating presigned URL for file {file_id}")
        logger.debug(f"User ID: {user_id}")

        # Use authenticated client to fetch file record (enforces RLS)
        file_record = get_file_record(file_id, token)
        logger.debug(f"File data: {file_record}")
        
        if not file_record:
            logger.error("File record not found in database")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Verify user has access to this file
        if file_record["user_id"] != user_id:
            logger.error("User not authorized to access this file")
            raise HTTPException(status_code=403, detail="Unauthorized")

        # Get storage path
        storage_path = file_record["storage_path"]
        logger.debug(f"Storage path: {storage_path}")

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
    
async def read_file_content_async(path: str, token: str) -> bytes:
    """
    Async version of file content reading from Supabase storage.
    """
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_NAME}/{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
        
        if response.status_code == 404:
            raise HTTPException(
                status_code=404, 
                detail=f"File not found in storage. Please check if it was deleted or the path is correct: {path}"
            )
            
        response.raise_for_status()
        
        return response.content
    
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=404, 
                detail="File not found in storage"
            )
        raise HTTPException(status_code=e.response.status_code, detail=f"Storage service error: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def read_file_content(path: str, token: str) -> bytes:
    """
    Synchronous wrapper for backward compatibility.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    read_file_content_async(path, token)
                )
                return future.result()
        else:
            return loop.run_until_complete(read_file_content_async(path, token))
    except RuntimeError:
        return asyncio.run(read_file_content_async(path, token))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_file_from_supabase(file_record: dict, user_token: str) -> str:
    """
    Returns the text from a file stored in Supabase based on the file's content type.
    
    Supported formats:
    - PDF: application/pdf
    - DOCX: application/vnd.openxmlformats-officedocument.wordprocessingml.document
    - Text files: text/*
    
    Args:
        file_record: Dictionary containing file metadata including storage_path and file_type
        user_token: User's authentication token for storage access
        
    Returns:
        str: Extracted text content from the file
        
    Raises:
        HTTPException: 404 if file not found, 400 if unsupported format, 500 for other errors
    """
    try:
        if not file_record or not isinstance(file_record, dict):
            raise HTTPException(status_code=400, detail="Invalid or missing file record")
            
        if "storage_path" not in file_record:
            raise HTTPException(status_code=400, detail="File record is missing storage_path")
            
        file_path = file_record["storage_path"]
        file_type = file_record.get("file_type", "").lower()  # e.g. 'application/pdf'
        file_name = file_record.get("original_filename", "").lower()
        
        try:
            file_bytes = read_file_content(file_path, user_token)
            
            if not file_bytes:
                raise HTTPException(status_code=404, detail="Could not read file content from storage")
    
            # Handle by MIME type first
            if file_type == "application/pdf":
                logger.debug(f"Parsing PDF file: {file_name}")
                return extract_text_from_pdf(file_bytes)
            
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                logger.debug(f"Parsing DOCX file: {file_name}")
                return extract_text_from_docx(file_bytes)
            
            elif file_type.startswith("text/"):
                logger.debug(f"Parsing text file: {file_name}")
                return file_bytes.decode("utf-8", errors="ignore")
            
            else:
                # Fallback: check file extension and raw bytes
                if file_name.endswith('.pdf') or is_pdf(file_bytes):
                    logger.debug(f"Parsing PDF file (fallback detection): {file_name}")
                    return extract_text_from_pdf(file_bytes)
                
                elif file_name.endswith('.docx'):
                    logger.debug(f"Parsing DOCX file (fallback detection): {file_name}")
                    return extract_text_from_docx(file_bytes)
                
                elif file_name.endswith('.doc'):
                    # Legacy .doc format not supported
                    logger.warning(f"Legacy .doc format not supported: {file_name}")
                    raise HTTPException(
                        status_code=400,
                        detail="Legacy .doc format is not supported. Please convert to .docx or PDF."
                    )
                
                elif file_name.endswith(('.txt', '.md', '.csv', '.json', '.xml', '.html')):
                    logger.debug(f"Parsing text file (fallback detection): {file_name}")
                    return file_bytes.decode("utf-8", errors="ignore")
                
                else:
                    # Unknown format - try to decode as text
                    logger.warning(f"Unknown file type '{file_type}' for file '{file_name}', attempting text decode")
                    try:
                        return file_bytes.decode("utf-8", errors="ignore")
                    except Exception:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unsupported file format: {file_type or 'unknown'}. Supported formats: PDF, DOCX, TXT."
                        )
                        
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
    """
    Delete a file from Supabase (both database record and storage).
    
    Args:
        file_id: The file ID to delete
        token: User's authentication token for RLS enforcement
        user_id: The user ID (for authorization)
        original_filename: The original filename
    """
    try:
        # Use authenticated client (enforces RLS)
        supabase = app_config.get_authenticated_supabase_client(token)
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