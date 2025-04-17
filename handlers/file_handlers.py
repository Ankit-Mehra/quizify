from fastapi import HTTPException, Depends
from services.db_services.supabase_file import save_file_to_supabase
from dependencies.auth_helper import get_current_user_id, get_current_user_token
from fastapi import UploadFile, File

async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    try:
        file_bytes = await file.read()
        file_type = file.content_type
        save_file_to_supabase(user_id, file_bytes, file.filename, user_token, file_type)
        return {
            "message": "File uploaded successfully",
            "file_id": file.filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
    
    

