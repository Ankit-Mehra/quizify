````markdown
# API Contract: File Upload with Tier and Size Validation

**Endpoint**: `POST /api/files/upload`  
**Purpose**: Upload file for quiz generation with tier-based type restrictions and size limits  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: File type must match user tier allowlist  
**Status**: ⚠️ PARTIALLY IMPLEMENTED (Missing tier and size validation)  
**Last Updated**: 2025-10-23

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data
```

### Body (multipart/form-data)
```
file: <binary file data>
```

### File Validation Rules (SPECIFIED - NOT IMPLEMENTED)

**Size Limit**: ❌ 10MB maximum (all tiers) - **NOT ENFORCED**

**Type Restrictions by Tier**: ❌ **NOT IMPLEMENTED**
- **Free tier**: 
  - `application/pdf` (PDF)
  - `text/plain` (TXT)
- **Basic tier**:
  - `application/pdf` (PDF)
  - `text/plain` (TXT)
  - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (DOCX)
- **Educator tier**:
  - `application/pdf` (PDF)
  - `text/plain` (TXT)
  - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (DOCX)

**ACTUAL BEHAVIOR**:
- ❌ No file size validation
- ❌ No tier-based file type restrictions
- ✅ Files are uploaded to Supabase Storage
- ✅ Basic authentication required

### Business Rules
- ❌ Validate file size BEFORE upload to storage - **NOT IMPLEMENTED**
- ❌ Validate file MIME type against tier allowlist - **NOT IMPLEMENTED**
- ❌ Reject disallowed types with upgrade message - **NOT IMPLEMENTED**
- ❌ Reject oversized files with clear limit message - **NOT IMPLEMENTED**

---

## Response

### Success (200 OK) - ACTUAL IMPLEMENTATION
```json
{
  "message": "File uploaded successfully",
  "file_id": "document.pdf"
}
```

**Note**: Actual response returns filename as `file_id`, NOT a UUID. Missing `filename`, `file_type`, and `file_size_bytes` fields.

### Errors (ACTUAL vs SPEC)

**403 Forbidden** (File type not allowed for tier) - ❌ **NOT IMPLEMENTED**
```json
{
  "detail": "DOCX files require basic or educator tier. Upgrade your account to upload this file type.",
  "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "user_tier": "free",
  "allowed_types": ["application/pdf", "text/plain"]
}
```

**413 Payload Too Large** (File size exceeds limit) - ❌ **NOT IMPLEMENTED**
```json
{
  "detail": "File size exceeds 10MB limit",
  "file_size_bytes": 12582912,
  "max_size_bytes": 10485760
}
```

**400 Bad Request** (Unsupported file type) - ⚠️ **PARTIAL**
```json
{
  "detail": "Unsupported file type: image/png. Supported types: PDF, TXT, DOCX"
}
```
**Note**: File type validation happens during quiz generation, NOT during upload

**400 Bad Request** (No file provided) - ⚠️ **UNKNOWN**
```json
{
  "detail": "No file provided in request"
}
```

**401 Unauthorized** - ✅ **IMPLEMENTED**
```json
{
  "detail": "Authentication required"
}
```

**500 Internal Server Error** - ✅ **IMPLEMENTED**
```json
{
  "detail": "<error_message>"
}
```

---

## Contract Test Scenarios

### Tier-Based File Type Tests

1. **Free tier uploads PDF** (allowed)
   - User tier: free
   - Upload PDF file (2MB)
   - Expect 200 OK

2. **Free tier uploads TXT** (allowed)
   - User tier: free
   - Upload TXT file (500KB)
   - Expect 200 OK

3. **Free tier uploads DOCX** (rejected)
   - User tier: free
   - Upload DOCX file (3MB)
   - Expect 403 Forbidden with upgrade message

4. **Basic tier uploads DOCX** (allowed)
   - User tier: basic
   - Upload DOCX file (5MB)
   - Expect 200 OK

5. **Educator tier uploads all types** (allowed)
   - User tier: educator
   - Upload PDF, TXT, DOCX separately
   - Expect 200 OK for all

### File Size Tests

6. **Upload 9MB file** (under limit)
   - Upload PDF file (9MB)
   - Expect 200 OK

7. **Upload exactly 10MB file** (at limit)
   - Upload PDF file (10485760 bytes)
   - Expect 200 OK

8. **Upload 11MB file** (over limit)
   - Upload PDF file (11MB)
   - Expect 413 Payload Too Large

9. **Upload 50MB file** (far over limit)
   - Upload PDF file (50MB)
   - Expect 413 Payload Too Large

### General Validation Tests

10. **Unsupported file type** (all tiers)
    - Upload PNG image file
    - Expect 400 Bad Request

11. **No file in request**
    - Send empty multipart request
    - Expect 400 Bad Request

12. **Missing authentication**
    - Omit Authorization header
    - Expect 401 Unauthorized

---

## OpenAPI Schema Updates

```yaml
/api/files/upload:
  post:
    summary: Upload file with tier and size validation
    tags:
      - File Management
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        multipart/form-data:
          schema:
            type: object
            required:
              - file
            properties:
              file:
                type: string
                format: binary
                description: File to upload (max 10MB)
    responses:
      '200':
        description: File uploaded successfully
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                file_id:
                  type: string
                  format: uuid
                filename:
                  type: string
                file_type:
                  type: string
                file_size_bytes:
                  type: integer
      '400':
        description: Bad request (unsupported type or no file)
      '401':
        description: Unauthorized
      '403':
        description: Forbidden (file type not allowed for tier)
        content:
          application/json:
            schema:
              type: object
              properties:
                detail:
                  type: string
                file_type:
                  type: string
                user_tier:
                  type: string
                  enum: [free, basic, educator]
                allowed_types:
                  type: array
                  items:
                    type: string
      '413':
        description: Payload too large (file exceeds 10MB)
        content:
          application/json:
            schema:
              type: object
              properties:
                detail:
                  type: string
                file_size_bytes:
                  type: integer
                max_size_bytes:
                  type: integer
```

---

## Implementation Status

### Code Location
- **Route**: `api/file_routes.py` - `POST /files/upload`
- **Handler**: `handlers/file_handlers.py` - `upload_file()`
- **Service**: `services/db_services/supabase_file.py` - `save_file_to_supabase()`

### Actual Implementation
```python
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
        
        # NO VALIDATION HERE - Just uploads to Supabase
        save_file_to_supabase(user_id, file_bytes, file.filename, user_token, file_type)
        logger.info(f"File successfully uploaded to Supabase: {file.filename}")
        
        return {
            "message": "File uploaded successfully",
            "file_id": file.filename  # Returns filename, not UUID
        }
    except Exception as e:
        logger.error(f"Error uploading file {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

### Missing Features

| Feature | Status | Priority | Effort |
|---------|--------|----------|--------|
| File size validation (10MB) | ❌ Missing | 🔴 HIGH | 1 hour |
| Tier-based file type restrictions | ❌ Missing | 🟡 MEDIUM | 2 hours |
| Return file_size_bytes in response | ❌ Missing | 🟢 LOW | 15 min |
| Return UUID as file_id | ❌ Missing | 🟢 LOW | 30 min |
| Return filename separately | ❌ Missing | 🟢 LOW | 15 min |
| 413 Payload Too Large error | ❌ Missing | 🟡 MEDIUM | With size validation |
| 403 Forbidden for tier violations | ❌ Missing | 🟡 MEDIUM | With tier check |

### Recommendations

#### Option 1: Implement Full Spec (RECOMMENDED for Production)
Add validation to `upload_file()`:

```python
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    # Get user tier
    from services.db_services.supabase_quiz import get_user_tier_info
    tier_info = get_user_tier_info(user_id)
    user_tier = tier_info["account_tier"]
    
    # Read file
    file_bytes = await file.read()
    file_size = len(file_bytes)
    
    # Validate size (10MB = 10485760 bytes)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "detail": "File size exceeds 10MB limit",
                "file_size_bytes": file_size,
                "max_size_bytes": MAX_FILE_SIZE
            }
        )
    
    # Validate file type against tier
    TIER_ALLOWED_TYPES = {
        "free": ["application/pdf", "text/plain"],
        "basic": ["application/pdf", "text/plain", 
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        "educator": ["application/pdf", "text/plain",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
    }
    
    allowed_types = TIER_ALLOWED_TYPES.get(user_tier, TIER_ALLOWED_TYPES["free"])
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": f"File type {file.content_type} not allowed for {user_tier} tier. Upgrade to basic for DOCX support.",
                "file_type": file.content_type,
                "user_tier": user_tier,
                "allowed_types": allowed_types
            }
        )
    
    # Upload to Supabase
    file_id = str(uuid.uuid4())  # Generate UUID
    save_file_to_supabase(user_id, file_bytes, file.filename, user_token, file.content_type)
    
    return {
        "message": "File uploaded successfully",
        "file_id": file_id,
        "filename": file.filename,
        "file_type": file.content_type,
        "file_size_bytes": file_size
    }
```

**Effort**: ~3 hours  
**Value**: High (prevents abuse, improves UX with clear tier benefits)

#### Option 2: Update Spec to Match Current Implementation
Remove validation requirements, document actual behavior.

**Effort**: 30 minutes (documentation only)  
**Value**: Low (leaves security/UX gaps)

---

**Contract Version**: Updated 2025-10-23  
**Implementation Status**: ⚠️ PARTIAL - Upload works but lacks validation  
**Production Ready**: ⚠️ NO - Missing size limits (DoS risk) and tier enforcement  
**Recommended Action**: Implement Option 1 (add validation)

**Contract Test File**: `tests/contract/test_file_upload_validation.py`  
**Status**: Specification complete - ❌ **VALIDATION NOT IMPLEMENTED**

````
