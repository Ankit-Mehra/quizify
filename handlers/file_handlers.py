from fastapi import HTTPException, Depends, Path, Body
from services.db_services.supabase_file import save_file_to_supabase, delete_file_from_supabase
from dependencies.auth_dependencies import get_current_user_id, get_current_user_token
from fastapi import UploadFile, File
from services.logger import app_logger as logger

async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    try:
        logger.info(f"File upload initiated by user {user_id}: {file.filename} ({file.content_type})")
        file_bytes = await file.read()
        file_size = len(file_bytes)
        file_type = file.content_type
        logger.debug(f"Read {file_size} bytes from file {file.filename}")
        
        save_file_to_supabase(user_id, file_bytes, file.filename, user_token, file_type)
        logger.info(f"File successfully uploaded to Supabase: {file.filename}")
        
        return {
            "message": "File uploaded successfully",
            "file_id": file.filename
        }
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
        delete_file_from_supabase(file_id, user_token, user_id, data["filename"])
        return {"message": "File deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

