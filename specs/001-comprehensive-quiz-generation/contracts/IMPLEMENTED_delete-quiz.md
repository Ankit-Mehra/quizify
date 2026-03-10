# API Contract: Delete Quiz (ACTUAL IMPLEMENTATION)

**Endpoint**: `DELETE /quiz/{quiz_id}`  
**Module**: Quiz Management  
**Status**: ✅ FULLY IMPLEMENTED  
**Last Updated**: 2025-10-28

---

## Overview

Permanently delete a quiz and all associated submissions. This is a destructive operation that cannot be undone.

---

## Request Specification

**Authentication**: Required (Bearer token)

**Path Parameters**:
- `quiz_id` (UUID, required): Unique identifier of the quiz to delete

**Headers**:
```
Authorization: Bearer {access_token}
```

**Request Body**: None

---

## Response Specification

**Response Model**: `DeleteQuizResponse`

**HTTP Status**: 200 OK

**Success Response**:
```json
{
  "message": "Quiz deleted successfully",
  "quiz_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Response Fields**:
- `message` (string): Confirmation message
- `quiz_id` (string): UUID of the deleted quiz

---

## Error Responses

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```
**Cause**: Missing or invalid Bearer token

### 403 Forbidden
```json
{
  "detail": "You do not have permission to delete this quiz"
}
```
**Cause**: User trying to delete another user's quiz

### 404 Not Found
```json
{
  "detail": "Quiz not found"
}
```
**Cause**: Quiz ID doesn't exist or already deleted

### 500 Internal Server Error
```json
{
  "detail": "Failed to delete quiz: {error_details}"
}
```
**Cause**: Database error during deletion

---

## Security Features

### Ownership Verification
- User can only delete their own quizzes
- Enforced by Row-Level Security (RLS) policies
- Uses authenticated Supabase client

### Authorization Flow
1. Verify user is authenticated
2. Check quiz exists
3. Check quiz belongs to user (RLS automatic)
4. Proceed with deletion

---

## Implementation Details

### Deletion Behavior

**What Gets Deleted**:
- ✅ Quiz record from `quizzes` table
- ✅ All submissions for this quiz from `submissions` table
- ✅ Quiz metadata references

**What Remains**:
- ⚠️ Source file (if quiz was from file upload) - not deleted
- ⚠️ User quota count - NOT decremented (intentional)

### Cascade Deletion
Database configured with cascading deletes:
```sql
-- submissions table has ON DELETE CASCADE
FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) ON DELETE CASCADE
```

**Result**: When quiz is deleted, all submissions automatically deleted.

### Quota Impact
- `current_quiz_count` is NOT decremented
- Deletion doesn't free up quota space
- User must upgrade tier for more quizzes
- **Rationale**: Prevents quota gaming (create/delete/repeat)

### Handler Function
Located in: `handlers/quiz_handlers.py::delete_quiz_by_id_handler()`

---

## Usage Examples

### Delete Quiz via cURL
```bash
curl -X DELETE "/quiz/a1b2c3d4-e5f6-7890-abcd-ef1234567890" \
  -H "Authorization: Bearer {access_token}"
```

### Delete Quiz via JavaScript
```javascript
async function deleteQuiz(quizId, accessToken) {
  const response = await fetch(`/quiz/${quizId}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${accessToken}`
    }
  });
  
  if (!response.ok) {
    throw new Error('Failed to delete quiz');
  }
  
  const result = await response.json();
  console.log(result.message); // "Quiz deleted successfully"
  return result;
}
```

---

## Response Schema Reference

### DeleteQuizResponse
```python
class DeleteQuizResponse(BaseModel):
    message: str
    quiz_id: str
```

---

## Integration Points

### Quiz Management Flow
1. **List Quizzes**: `GET /quiz/my-quizzes`
2. **Confirm Deletion**: Show warning to user
3. **Delete Quiz**: `DELETE /quiz/{quiz_id}`
4. **Refresh List**: Re-fetch quiz list

### Related Endpoints
- `GET /quiz/my-quizzes` - List shows remaining quizzes after deletion
- `GET /quiz/{quiz_id}` - Will return 404 after deletion
- `POST /quiz/{quiz_id}/submit` - Cannot submit to deleted quiz
- `GET /quiz/{quiz_id}/submissions` - Returns 404 (quiz gone)

---

## Side Effects & Warnings

### ⚠️ Permanent Deletion
- **No undo**: Quiz cannot be recovered after deletion
- **No soft delete**: Record completely removed from database
- **No backup**: No automatic backup created

### 📊 Submission Loss
- **All submissions deleted**: Users who took quiz lose their results
- **No notification**: Submission owners not notified of deletion
- **Impact**: Consider if quiz has submissions before deleting

### 📁 File Retention
- **Source file remains**: If quiz was from uploaded file, file NOT deleted
- **Manual cleanup**: User must separately delete file via `DELETE /files/{file_id}`
- **Orphaned reference**: `content_source_reference` becomes stale

### 🔢 Quota Behavior
- **Count unchanged**: `current_quiz_count` stays the same
- **No quota regain**: Deleting doesn't free quota space
- **Prevents abuse**: Users can't cycle through quota by deleting

---

## Best Practices

### Before Deleting
1. **Confirm with user**: Show "Are you sure?" dialog
2. **Show impact**: Display submission count (if any)
3. **Suggest alternative**: Consider keeping quiz private instead
4. **Check dependencies**: Warn if quiz has submissions

### After Deleting
1. **Update UI**: Remove quiz from list immediately
2. **Show confirmation**: Display success message
3. **Handle errors**: Gracefully handle 403/404 errors
4. **Cleanup files**: Prompt to delete associated files

---

## Common Use Cases

### 1. Accidental Quiz Creation
User creates quiz by mistake and wants to remove it:
```bash
# Immediately after creation
DELETE /quiz/{quiz_id}
```

### 2. Quiz Cleanup
User wants to remove old or unused quizzes:
```bash
# Get old quizzes
GET /quiz/my-quizzes
# Delete unwanted ones
DELETE /quiz/{old_quiz_id}
```

### 3. Content Refresh
User wants to regenerate quiz with updated content:
```bash
# Delete old version
DELETE /quiz/{old_quiz_id}
# Generate new version
POST /quiz/generate/text
```

---

## Testing Considerations

### Test Cases
- ✅ Delete own quiz successfully
- ✅ Cannot delete another user's quiz (403)
- ✅ Cannot delete non-existent quiz (404)
- ✅ Submissions cascade deleted
- ✅ Quota count unchanged after deletion
- ✅ Source file NOT deleted
- ✅ Quiz no longer appears in my-quizzes list

### Test Data Setup
```sql
-- Create test quiz
INSERT INTO quizzes (quiz_id, user_id, title, quiz_data)
VALUES ('test-quiz-id', 'test-user-id', 'Test Quiz', '{}');

-- Create test submission
INSERT INTO submissions (quiz_id, user_id, score)
VALUES ('test-quiz-id', 'other-user-id', 80);
```

### Test Assertions
```python
# After deletion
assert quiz_no_longer_exists(quiz_id)
assert submissions_deleted(quiz_id)
assert quota_unchanged(user_id)
assert file_still_exists(file_id)  # if quiz was from file
```

---

## Error Handling Patterns

### Frontend Error Handling
```javascript
try {
  await deleteQuiz(quizId, token);
  showSuccess("Quiz deleted successfully");
  refreshQuizList();
} catch (error) {
  if (error.status === 403) {
    showError("You cannot delete this quiz");
  } else if (error.status === 404) {
    showError("Quiz not found or already deleted");
    refreshQuizList(); // Still refresh to remove from UI
  } else {
    showError("Failed to delete quiz. Please try again.");
  }
}
```

---

## Performance Considerations

- **Speed**: ~100-200ms (includes cascade deletion of submissions)
- **Locks**: Brief write lock on quizzes and submissions tables
- **Scalability**: O(n) where n = number of submissions (usually small)

---

## Database Schema Dependencies

### Tables Affected
- `quizzes`: Quiz record deleted
- `submissions`: All submissions for quiz deleted (cascade)
- `user_files`: NOT affected (file remains if quiz was from file)

### Constraints
```sql
-- submissions.quiz_id foreign key
FOREIGN KEY (quiz_id) REFERENCES quizzes(quiz_id) 
  ON DELETE CASCADE

-- Ensures automatic cleanup
```

---

## Known Limitations

- No undo/recovery mechanism
- No notification to submission owners
- Quota not reclaimed
- Source files not automatically deleted
- No deletion audit log

---

## Future Enhancements

- [ ] Soft delete (mark as deleted instead of removing)
- [ ] Trash/recycle bin (30-day recovery period)
- [ ] Notify submission owners of deletion
- [ ] Batch delete multiple quizzes
- [ ] Optional cascade delete of source file
- [ ] Deletion audit log for admins
- [ ] Quota reclaim option (admin only)

---

**Contract Status**: ✅ Complete  
**Security Audit**: ✅ Passed  
**RLS Enforcement**: ✅ Active  
**Production Ready**: ✅ Yes  
**⚠️ Destructive Operation**: Permanent deletion - use with caution
