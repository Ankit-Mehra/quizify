# API Contract: File Upload with Tier and Size Validation

**Endpoint**: `POST /api/files/upload`  
**Purpose**: Upload file for quiz generation with tier-based type restrictions and size limits  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: File type must match user tier allowlist

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

### File Validation Rules (NEW)

**Size Limit**: 10MB maximum (all tiers)

**Type Restrictions by Tier**:
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

### Business Rules
- Validate file size BEFORE upload to storage
- Validate file MIME type against tier allowlist
- Reject disallowed types with upgrade message
- Reject oversized files with clear limit message

---

## Response

### Success (200 OK)
```json
{
  "message": "File uploaded successfully",
  "file_id": "uuid",
  "filename": "textbook-chapter5.pdf",
  "file_type": "application/pdf",
  "file_size_bytes": 2457600
}
```

### Errors

**403 Forbidden** (File type not allowed for tier - NEW)
```json
{
  "detail": "DOCX files require basic or educator tier. Upgrade your account to upload this file type.",
  "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "user_tier": "free",
  "allowed_types": ["application/pdf", "text/plain"]
}
```

**413 Payload Too Large** (File size exceeds limit - NEW)
```json
{
  "detail": "File size exceeds 10MB limit",
  "file_size_bytes": 12582912,
  "max_size_bytes": 10485760
}
```

**400 Bad Request** (Unsupported file type)
```json
{
  "detail": "Unsupported file type: image/png. Supported types: PDF, TXT, DOCX"
}
```

**400 Bad Request** (No file provided)
```json
{
  "detail": "No file provided in request"
}
```

**401 Unauthorized**
```json
{
  "detail": "Authentication required"
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

**Contract Test File**: `tests/contract/test_file_upload_validation.py`  
**Status**: Specification complete - ready for test generation
