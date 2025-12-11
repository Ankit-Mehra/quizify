from fastapi import HTTPException, Depends, Path, Body
from services.db_services.supabase_file import save_file_to_supabase, delete_file_from_supabase
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from fastapi import UploadFile, File
from services.logger import app_logger as logger
from services.storage_service import validate_storage_quota_or_raise, format_bytes

# Maximum file size: 10 MB (validated before storage quota check)
MAX_FILE_SIZE_BYTES = 10_485_760  # 10 MB


async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    try:
        logger.info(f"File upload initiated by user {user_id[:8]}...: {file.filename} ({file.content_type})")
        file_bytes = await file.read()
        file_size = len(file_bytes)
        file_type = file.content_type
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
        
        save_file_to_supabase(user_id, file_bytes, file.filename, user_token, file_type)
        logger.info(f"File successfully uploaded to Supabase: {file.filename}")
        
        return {
            "message": "File uploaded successfully",
            "file_id": file.filename
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

