from fastapi import APIRouter
from services.db_services.supabase_file import get_file_metadata, create_presigned_url
from schemas.files import FileMetadataResponse, FileDownloadResponse, FileUploadResponse, FileDeleteResponse
from handlers.file_handlers import upload_file, delete_file
from services.logger import app_logger as logger

router = APIRouter(prefix="/files", tags=["Files"])
logger.info("File routes initialized")

router.add_api_route(
    path="/metadata",
    endpoint=get_file_metadata,
    methods=["GET"],
    response_model=FileMetadataResponse,
    summary="Get File Metadata",
    tags=["Files"]
)

# === Get file by ID ===
router.add_api_route(
    path="/{file_id}",
    endpoint=create_presigned_url,
    methods=["GET"],
    response_model=FileDownloadResponse,
    summary="Download File by ID",
    tags=["Files"]
)

# === Upload file ===
router.add_api_route(
    path="/upload",
    endpoint=upload_file,
    methods=["POST"],
    response_model=FileUploadResponse,
    summary="Upload File",
    tags=["Files"]
)

# === Delete file by ID ===
router.add_api_route(
    path="/{file_id}",
    endpoint=delete_file,
    methods=["DELETE"],
    response_model=FileDeleteResponse,
    summary="Delete File by ID",
    tags=["Files"]
)
