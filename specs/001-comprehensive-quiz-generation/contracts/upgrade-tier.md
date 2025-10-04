# API Contract: User Tier Management

**Endpoint**: `POST /api/auth/upgrade-tier`  
**Purpose**: Upgrade user account tier from free to basic or educator  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: Self-service with verification token (admin approval for MVP)

---

## Request

### Headers
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Body
```json
{
  "target_tier": "basic" | "educator",
  "verification_token": "string"
}
```

### Field Validation
- `target_tier`: **Required**, must be "basic" or "educator" (cannot upgrade to "free")
- `verification_token`: **Required**, string (admin-issued token for MVP; future: payment confirmation or .edu verification)

### Business Rules
- User must be authenticated
- Current tier must be "free" (no lateral moves basic↔educator in MVP)
- Verification token must be valid
- Upgrade is idempotent (upgrading to current tier = no-op)

---

## Response

### Success (200 OK)
```json
{
  "message": "Account upgraded successfully",
  "user_id": "uuid",
  "new_tier": "basic",
  "quota": 100
}
```

### Errors

**401 Unauthorized**
```json
{
  "detail": "Authentication required"
}
```

**403 Forbidden**
```json
{
  "detail": "Invalid verification token"
}
```

**400 Bad Request**
```json
{
  "detail": "Cannot upgrade from basic to basic (already at this tier)"
}
```

**400 Bad Request** (invalid target tier)
```json
{
  "detail": "Invalid target_tier. Must be 'basic' or 'educator'"
}
```

---

## Contract Test Scenarios

1. **Valid upgrade** (free → basic)
   - Send valid verification token
   - Expect 200 with new_tier="basic", quota=100
   
2. **Valid upgrade** (free → educator)
   - Send valid verification token
   - Expect 200 with new_tier="educator", quota=500

3. **Invalid verification token**
   - Send wrong token
   - Expect 403 Forbidden

4. **Missing authentication**
   - Omit Authorization header
   - Expect 401 Unauthorized

5. **Invalid tier value**
   - Send target_tier="premium"
   - Expect 400 Bad Request with validation error

6. **Idempotent upgrade**
   - Upgrade free → basic (success)
   - Upgrade basic → basic (no error, returns current state)

---

## OpenAPI Schema

```yaml
/api/auth/upgrade-tier:
  post:
    summary: Upgrade user account tier
    tags:
      - Authentication
    security:
      - BearerAuth: []
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - target_tier
              - verification_token
            properties:
              target_tier:
                type: string
                enum: [basic, educator]
              verification_token:
                type: string
    responses:
      '200':
        description: Upgrade successful
        content:
          application/json:
            schema:
              type: object
              properties:
                message:
                  type: string
                user_id:
                  type: string
                  format: uuid
                new_tier:
                  type: string
                  enum: [basic, educator]
                quota:
                  type: integer
      '400':
        description: Bad request (invalid tier or already at tier)
      '401':
        description: Unauthorized (missing or invalid token)
      '403':
        description: Forbidden (invalid verification token)
```

---

**Contract Test File**: `tests/contract/test_upgrade_tier.py`  
**Status**: Specification complete - ready for test generation
