from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import List, Optional

class FileMetadata(BaseModel):
    id: str
    user_id: str
    original_filename: str
    file_type: str
    storage_path: str
    uploaded_at: datetime
    file_size_bytes: Optional[int] = None  # NEW: file size for 10MB validation

class FileMetadataResponse(BaseModel):
    model_config = ConfigDict(strict=True)
    files: List[FileMetadata]

class FileDownloadResponse(BaseModel):
    url: str
    expires_in: int

class FileUploadResponse(BaseModel):
    message: str
    file_id: str

class FileQuizRequest(BaseModel):
    title: str
    num_questions: int

