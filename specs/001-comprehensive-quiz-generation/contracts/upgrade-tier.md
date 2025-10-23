````markdown
# API Contract: User Tier Management

**Endpoint**: `POST /api/auth/upgrade-tier`  
**Purpose**: Upgrade user account tier from free to basic or educator  
**Authentication**: Required (Bearer token or cookie)  
**Authorization**: Self-service with verification token (admin approval for MVP)  
**Status**: ❌ NOT IMPLEMENTED  
**Last Updated**: 2025-10-23

---

## ⚠️ IMPLEMENTATION STATUS

**This endpoint does NOT exist in the codebase.**

Tier upgrades are currently handled via:
- **Admin Route**: `PUT /api/admin/users/{user_id}/tier` (admin-only, requires admin JWT)
- **Manual Database Update**: Direct update to `profiles` table

No self-service upgrade endpoint exists.

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

## Actual Implementation

### Admin-Only Tier Updates

**Endpoint**: `PUT /api/admin/users/{user_id}/tier`  
**Route**: `api/admin_routes.py` - Line ~40  
**Handler**: `handlers/admin_handlers.py` - `update_user_tier()`  
**Authentication**: Required (Bearer token)  
**Authorization**: Admin role required

**Request Body**:
```json
{
  "new_tier": "basic" | "educator" | "free"
}
```

**Response** (200 OK):
```json
{
  "message": "User tier updated successfully",
  "user_id": "uuid",
  "old_tier": "free",
  "new_tier": "basic"
}
```

**Errors**:
- `401 Unauthorized`: Missing/invalid token
- `403 Forbidden`: User is not admin
- `404 Not Found`: User ID not found
- `500 Internal Server Error`: Database update failed

### Implementation Code
```python
async def update_user_tier(
    user_id: str = Path(...),
    data: UserTierUpdate = Body(...),
    current_user_id: str = Depends(get_current_user_id),
    user_token: str = Depends(get_current_user_token)
):
    """Update user tier (admin only)."""
    # Check admin authorization
    user_info = get_user_tier_info(current_user_id)
    if user_info.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get old tier
    old_tier_info = get_user_tier_info(user_id)
    old_tier = old_tier_info["account_tier"]
    
    # Update tier in profiles table
    result = supabase.table("profiles")\
        .update({"account_tier": data.new_tier})\
        .eq("id", user_id)\
        .execute()
    
    return {
        "message": "User tier updated successfully",
        "user_id": user_id,
        "old_tier": old_tier,
        "new_tier": data.new_tier
    }
```

---

## Missing Self-Service Endpoint

### Why Not Implemented?
1. **Payment Integration Missing**: No Stripe/payment gateway integrated
2. **Email Verification Missing**: No .edu email verification for educator tier
3. **Security Concerns**: Self-service upgrades without payment/verification would be abused
4. **MVP Decision**: Admin approval workflow is sufficient for initial launch

### Recommendations

#### Option 1: Implement Self-Service with Payment (PRODUCTION)
- Integrate Stripe for paid tier upgrades (basic/educator)
- Add webhook handler for payment confirmation
- Generate verification tokens after successful payment
- Implement endpoint per original spec

**Effort**: 2-3 weeks  
**Value**: High (enables monetization, improves UX)  
**Dependencies**: Stripe account, payment processing setup

#### Option 2: Implement Self-Service with Manual Approval (MVP+)
- Users request upgrade via form
- Generate verification tokens manually
- Admin approves/rejects via dashboard
- Implement endpoint with token validation

**Effort**: 1 week  
**Value**: Medium (better than pure admin-only, but still manual)

#### Option 3: Keep Admin-Only (CURRENT)
- Document existing admin endpoint as the official method
- Remove self-service endpoint from spec
- Users contact support for tier upgrades

**Effort**: 30 minutes (documentation only)  
**Value**: Low (poor UX, doesn't scale)

---

## Alternative: Tier Upgrade via Support

**Current Workflow**:
1. User contacts support/admin requesting tier upgrade
2. Admin logs into system
3. Admin calls `PUT /api/admin/users/{user_id}/tier` with new tier
4. User receives confirmation email (manual or automated)

**Pros**: Simple, no payment integration needed  
**Cons**: Doesn't scale, poor UX, manual process

---

**Contract Status**: ❌ **NOT IMPLEMENTED**  
**Alternative**: Admin-only tier management exists  
**Production Ready**: ⚠️ NO - Self-service upgrades required for scaling  
**Recommended Action**: Implement Option 1 (Stripe integration) or Option 2 (manual approval) for production

**Contract Test File**: `tests/contract/test_upgrade_tier.py`  
**Status**: ❌ **ENDPOINT DOES NOT EXIST**

````
