from fastapi import HTTPException, Depends, Path, Body
from services.db_services.supabase_file import save_file_to_supabase_async, delete_file_from_supabase
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from fastapi import UploadFile, File
from services.logger import app_logger as logger
from services.storage_service import validate_storage_quota_or_raise, format_bytes

# Maximum file size: 10 MB (validated before storage quota check)
MAX_FILE_SIZE_BYTES = 10_485_760  # 10 MB

# Allowed MIME types for file uploads
# Security: Strict allowlist to prevent malicious file uploads
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "application/msword": [".doc"],
    # Text
    "text/plain": [".txt"],
    "text/markdown": [".md"],
    # Presentations (for future support)
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
}

# Extension-based fallback for browsers that don't send proper MIME types
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".pptx"}


def _validate_file_type(filename: str, content_type: str) -> str:
    """
    Validate file type against allowlist.
    
    Args:
        filename: Original filename
        content_type: MIME type from upload
        
    Returns:
        Validated/normalized content type
        
    Raises:
        HTTPException: If file type is not allowed
    """
    # Normalize content_type (some browsers add charset)
    if content_type:
        content_type = content_type.split(";")[0].strip().lower()
    
    # Get file extension
    extension = ""
    if filename and "." in filename:
        extension = "." + filename.rsplit(".", 1)[-1].lower()
    
    # Check MIME type first
    if content_type in ALLOWED_MIME_TYPES:
        # Verify extension matches expected extensions for this MIME type
        expected_extensions = ALLOWED_MIME_TYPES[content_type]
        if extension and extension not in expected_extensions:
            logger.warning(
                f"MIME type mismatch: {content_type} but extension is {extension}"
            )
        return content_type
    
    # Fallback: Check extension if MIME type is generic (application/octet-stream)
    if content_type in ("application/octet-stream", None, ""):
        if extension in ALLOWED_EXTENSIONS:
            # Map extension back to MIME type
            for mime, exts in ALLOWED_MIME_TYPES.items():
                if extension in exts:
                    logger.info(f"Inferred MIME type {mime} from extension {extension}")
                    return mime
    
    # Reject unknown types
    logger.warning(
        f"Rejected file upload: unsupported type '{content_type}' with extension '{extension}'"
    )
    raise HTTPException(
        status_code=415,
        detail={
            "error": "unsupported_file_type",
            "message": (
                f"File type '{content_type or 'unknown'}' is not supported. "
                "Allowed types: PDF, DOCX, DOC, TXT, MD, PPTX"
            ),
            "content_type": content_type,
            "extension": extension,
            "allowed_types": list(ALLOWED_MIME_TYPES.keys()),
        }
    )


async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    try:
        logger.info(f"File upload initiated by user {user_id[:8]}...: {file.filename} ({file.content_type})")
        
        # Validate file type BEFORE reading content (fail fast)
        validated_content_type = _validate_file_type(file.filename, file.content_type)
        
        file_bytes = await file.read()
        file_size = len(file_bytes)
        logger.debug(f"Read {file_size} bytes from file {file.filename}")
        
        # Validate individual file size (10 MB limit)
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"File too large for user {user_id[:8]}...: "
                f"{format_bytes(file_size)} > {format_bytes(MAX_FILE_SIZE_BYTES)}"
            )
            raise HTTPException(
                status_code=413,
                detail={
                    "error": "file_too_large",
                    "message": f"File exceeds maximum size of 10 MB. Your file is {format_bytes(file_size)}.",
                    "file_size_bytes": file_size,
                    "max_size_bytes": MAX_FILE_SIZE_BYTES,
                }
            )
        
        # Validate storage quota (raises HTTP 402 if exceeded)
        quota_info = await validate_storage_quota_or_raise(user_id, file_size)
        logger.debug(
            f"Storage quota check passed for user {user_id[:8]}...: "
            f"used={quota_info['storage_used_formatted']}, "
            f"quota={quota_info['storage_quota_formatted']}"
        )
        
        # Use validated content type (may be inferred from extension)
        file_record = await save_file_to_supabase_async(user_id, file_bytes, file.filename, user_token, validated_content_type)
        logger.info(f"File successfully uploaded to Supabase: {file.filename} (ID: {file_record['file_id']})")
        
        return {
            "message": "File uploaded successfully",
            "file_id": file_record["file_id"],
            "filename": file.filename
        }
    except HTTPException:
        # Re-raise HTTP exceptions (storage quota, file size errors)
        raise
    except Exception as e:
        logger.error(f"Error uploading file {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
    
    
async def delete_file(
    file_id: str = Path(...),
    user_token: str = Depends(get_current_user_token),
    user_id: str = Depends(get_current_user_id),
    data: dict = Body(...)
):
    try:
        logger.info(f"File deletion initiated by user {user_id[:8]}...: {data.get('filename', 'unknown')}")
        delete_file_from_supabase(file_id, user_token, user_id, data["filename"])
        logger.info(f"File successfully deleted: {data.get('filename', 'unknown')}")
        return {"message": "File deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting file {data.get('filename', 'unknown')}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

