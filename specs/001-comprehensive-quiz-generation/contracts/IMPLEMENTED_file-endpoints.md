# API Contract: File Management Endpoints (ACTUAL IMPLEMENTATION)

**Module**: File Upload & Management  
**Base Path**: `/files`  
**Status**: ✅ FULLY IMPLEMENTED  
**Last Updated**: 2025-10-28

---

## Overview

File management system for PDF and DOCX uploads used in quiz generation. Integrates with Supabase Storage for secure file storage and retrieval.

---

## Endpoint Summary

| Endpoint | Method | Response Model | Description |
|----------|--------|----------------|-------------|
| `/files/upload` | POST | `FileUploadResponse` | Upload PDF/DOCX file |
| `/files/metadata` | GET | `List[FileMetadataResponse]` | List user's uploaded files |
| `/files/{file_id}` | GET | Binary Stream | Download file content |
| `/files/{file_id}` | DELETE | `FileDeleteResponse` | Delete file |

---

## 1. POST /files/upload

**Purpose**: Upload a PDF or DOCX file for quiz generation

**Authentication**: Required (Bearer token)

**Response Model**: `FileUploadResponse`

**Request Format**: `multipart/form-data`

**Form Fields**:
- `file` (required): Binary file content
  - Allowed types: `.pdf`, `.docx`
  - Maximum size: 10 MB (10485760 bytes)

**Success Response (200)**:
```json
{
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "filename": "study-notes.pdf",
  "file_size_bytes": 2457600,
  "mime_type": "application/pdf",
  "storage_path": "user_files/760602fe-b19f-472a-b65e-060f9e195529/a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf",
  "uploaded_at": "2025-10-28T15:30:45.123456Z"
}
```

**Response Fields**:
- `file_id` (UUID string): Unique identifier for the file
- `filename` (string): Original filename
- `file_size_bytes` (int): File size in bytes
- `mime_type` (string): MIME type (`application/pdf` or `application/vnd.openxmlformats-officedocument.wordprocessingml.document`)
- `storage_path` (string): Path in Supabase Storage bucket
- `uploaded_at` (ISO timestamp): Upload timestamp

**Error Responses**:

**400 Bad Request** - File too large:
```json
{
  "detail": "File size exceeds 10MB limit"
}
```

**400 Bad Request** - Invalid file type:
```json
{
  "detail": "Only PDF and DOCX files are allowed"
}
```

**400 Bad Request** - No file provided:
```json
{
  "detail": "No file uploaded"
}
```

**401 Unauthorized** - Missing authentication:
```json
{
  "detail": "Not authenticated"
}
```

**500 Internal Server Error** - Storage failure:
```json
{
  "detail": "File upload failed: {error_details}"
}
```

**Implementation Details**:
- Validates file extension (`.pdf` or `.docx`)
- Checks file size ≤ 10,485,760 bytes (10 MB)
- Generates UUID for file_id
- Stores in Supabase Storage bucket: `user_files/{user_id}/{file_id}.{ext}`
- Creates record in `user_files` table with metadata
- User owns file (user_id set automatically)

**Storage Structure**:
```
Supabase Storage Bucket: user_files/
  ├── {user_id_1}/
  │   ├── {file_id_1}.pdf
  │   └── {file_id_2}.docx
  └── {user_id_2}/
      └── {file_id_3}.pdf
```

---

## 2. GET /files/metadata

**Purpose**: List all files uploaded by the authenticated user

**Authentication**: Required (Bearer token)

**Response Model**: `List[FileMetadataResponse]`

**Query Parameters**:
- None (returns all user's files)

**Success Response (200)**:
```json
[
  {
    "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "filename": "study-notes.pdf",
    "file_size_bytes": 2457600,
    "mime_type": "application/pdf",
    "uploaded_at": "2025-10-28T15:30:45.123456Z"
  },
  {
    "file_id": "b2c3d4e5-f6a7-8901-bcde-fa2345678901",
    "filename": "lecture-slides.docx",
    "file_size_bytes": 512000,
    "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "uploaded_at": "2025-10-27T10:15:30.987654Z"
  }
]
```

**Response Fields**:
- `file_id` (UUID string): Unique identifier
- `filename` (string): Original filename
- `file_size_bytes` (int): File size in bytes
- `mime_type` (string): File MIME type
- `uploaded_at` (ISO timestamp): Upload timestamp

**Error Responses**:
- `401 Unauthorized`: No valid token
- `500 Internal Server Error`: Database error

**Implementation Details**:
- Queries `user_files` table filtered by authenticated user_id
- Row-Level Security (RLS) enforces user can only see their own files
- Returns files sorted by `uploaded_at` DESC (newest first)
- Empty array returned if user has no files

---

## 3. GET /files/{file_id}

**Purpose**: Download file content

**Authentication**: Required (Bearer token)

**Response Model**: Binary stream (not JSON)

**Path Parameters**:
- `file_id` (UUID, required): File identifier from upload

**Success Response (200)**:
- **Content-Type**: `application/pdf` or `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- **Content-Disposition**: `attachment; filename="{original_filename}"`
- **Body**: Binary file content

**Error Responses**:

**401 Unauthorized**:
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden**:
```json
{
  "detail": "You do not have permission to access this file"
}
```

**404 Not Found**:
```json
{
  "detail": "File not found"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "File download failed: {error_details}"
}
```

**Implementation Details**:
- Verifies file belongs to authenticated user (RLS check)
- Retrieves file from Supabase Storage
- Streams binary content directly (no JSON wrapping)
- Sets appropriate Content-Type header based on file extension
- Sets Content-Disposition to suggest download with original filename

**Security Features**:
- User can only download their own files
- File ownership enforced via RLS policies
- No directory traversal vulnerabilities (uses UUIDs)

---

## 4. DELETE /files/{file_id}

**Purpose**: Delete a file from storage and database

**Authentication**: Required (Bearer token)

**Response Model**: `FileDeleteResponse`

**Path Parameters**:
- `file_id` (UUID, required): File identifier to delete

**Success Response (200)**:
```json
{
  "message": "File deleted successfully",
  "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Error Responses**:

**401 Unauthorized**:
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden**:
```json
{
  "detail": "You do not have permission to delete this file"
}
```

**404 Not Found**:
```json
{
  "detail": "File not found"
}
```

**500 Internal Server Error**:
```json
{
  "detail": "File deletion failed: {error_details}"
}
```

**Implementation Details**:
- Verifies file belongs to authenticated user
- Deletes from Supabase Storage bucket
- Deletes metadata record from `user_files` table
- **Note**: Quizzes generated from this file remain intact (file reference becomes stale)

**Side Effects**:
- File permanently deleted from storage (cannot be recovered)
- Quizzes with `content_source_reference = file_id` still exist but reference is broken
- No cascade delete of associated quizzes (intentional design)

---

## Response Schemas Reference

### FileUploadResponse
```python
class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_size_bytes: int
    mime_type: str
    storage_path: str
    uploaded_at: str
```

### FileMetadataResponse
```python
class FileMetadataResponse(BaseModel):
    file_id: str
    filename: str
    file_size_bytes: int
    mime_type: str
    uploaded_at: str
```

### FileDeleteResponse
```python
class FileDeleteResponse(BaseModel):
    message: str
    file_id: str
```

---

## Security Features

### File Type Validation
- **Allowlist Approach**: Only `.pdf` and `.docx` extensions allowed
- **MIME Type Verification**: Validates based on file extension
- **Prevents**: Malicious file uploads (scripts, executables)

### File Size Limits
- **Maximum**: 10 MB (10,485,760 bytes)
- **Prevents**: Storage exhaustion, DoS attacks
- **Enforcement**: Checked before storage upload

### Access Control
- **Row-Level Security (RLS)**: Enforced on `user_files` table
- **Ownership Check**: Users can only access their own files
- **No Public Access**: All files require authentication

### Storage Isolation
- **User Subdirectories**: `user_files/{user_id}/`
- **UUID Filenames**: Prevents name collisions and guessing
- **No Path Traversal**: Uses UUIDs, not user-supplied paths

---

## Common Error Patterns

### 400 File Too Large
**Cause**: File exceeds 10 MB limit  
**Solution**: Compress file or split content

### 400 Invalid File Type
**Cause**: File extension not `.pdf` or `.docx`  
**Solution**: Convert to supported format

### 403 Forbidden
**Cause**: User trying to access another user's file  
**Solution**: Use correct file_id from `/files/metadata`

### 404 Not Found
**Cause**: File_id doesn't exist or was deleted  
**Solution**: Re-upload file if needed

---

## Usage Examples

### 1. Upload PDF File
```bash
curl -X POST "/files/upload" \
  -H "Authorization: Bearer {access_token}" \
  -F "file=@study-notes.pdf"
```

### 2. List User's Files
```bash
curl -X GET "/files/metadata" \
  -H "Authorization: Bearer {access_token}"
```

### 3. Download File
```bash
curl -X GET "/files/{file_id}" \
  -H "Authorization: Bearer {access_token}" \
  -o downloaded-file.pdf
```

### 4. Delete File
```bash
curl -X DELETE "/files/{file_id}" \
  -H "Authorization: Bearer {access_token}"
```

---

## Integration with Quiz Generation

### Workflow
1. **Upload File**: `POST /files/upload` → Get `file_id`
2. **Generate Quiz**: `POST /quiz/generate/file` with `file_id`
3. **Quiz Metadata**: Quiz record includes `content_source_reference = file_id`
4. **Optional Cleanup**: `DELETE /files/{file_id}` after quiz generation

### File Reference Persistence
```json
// Quiz record after generation
{
  "quiz_id": "...",
  "content_source_type": "file",
  "content_source_reference": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Study Notes Quiz"
}
```

**Important**: If file is deleted, quiz remains but source file is unavailable for regeneration.

---

## Database Schema Dependencies

### Tables Used
- `user_files`: File metadata storage
  - `file_id` (UUID, PK)
  - `user_id` (UUID, FK to auth.users)
  - `filename` (text)
  - `file_size_bytes` (bigint)
  - `mime_type` (text)
  - `storage_path` (text)
  - `uploaded_at` (timestamp)

### RLS Policies
- Users can only SELECT their own files
- Users can only INSERT files for themselves
- Users can only DELETE their own files

---

## Testing Considerations

### Test Cases
- ✅ Upload valid PDF file
- ✅ Upload valid DOCX file
- ✅ Reject file > 10 MB
- ✅ Reject unsupported file type (.txt, .exe, etc.)
- ✅ List files returns only user's files
- ✅ Download file returns correct content
- ✅ Cannot download another user's file
- ✅ Delete file removes from storage and database
- ✅ Cannot delete another user's file

### Test Data
- Small PDF (<1 MB)
- Large PDF (~9.5 MB, within limit)
- Oversized PDF (>10 MB)
- DOCX file
- Invalid file type (.txt)

---

## Performance Considerations

### File Size Impact
- 10 MB max keeps processing time reasonable
- PDF parsing can be memory-intensive for large files
- DOCX processing generally faster than PDF

### Storage Quotas
- No per-user storage limit enforced (yet)
- Supabase Storage has project-level quotas
- Consider implementing per-user storage limits in future

---

## Future Enhancements

- [ ] File processing status tracking
- [ ] Automatic file deletion after quiz generation (optional)
- [ ] Image extraction from PDFs
- [ ] Preview/thumbnail generation
- [ ] Virus scanning integration
- [ ] Per-user storage quota enforcement
- [ ] File versioning support
- [ ] Bulk file upload
- [ ] OCR for scanned PDFs

---

**Contract Status**: ✅ Complete  
**Security Audit**: ✅ Passed  
**Production Ready**: ✅ Yes  
**RLS Enforcement**: ✅ Active
