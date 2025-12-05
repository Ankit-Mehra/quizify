from typing import Optional, Dict, Any
from services.logger import db_logger as logger
from config import config


def get_supabase_service():
    """Get service role client (bypasses RLS - use for reads/analytics only)."""
    return config.get_supabase_client()


def get_supabase_authed(user_token: str):
    """Get authenticated client (enforces RLS - use for user data operations)."""
    return config.get_authenticated_supabase_client(user_token)


def create_document(
    user_id: str,
    title: str,
    source_type: str,
    original_content: str,
    token_count: int,
    word_count: int,
    user_token: str,
    source_reference: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a new document record in the database.
    
    Uses authenticated client to enforce RLS policies.
    
    Args:
        user_id: UUID of the document owner
        title: Document title
        source_type: 'file', 'url', or 'text'
        original_content: Full document content
        token_count: Number of tokens in content
        word_count: Number of words in content
        user_token: User's JWT for RLS enforcement
        source_reference: Optional file_id or URL
        metadata: Optional additional metadata
        
    Returns:
        Created document record
        
    Raises:
        Exception: If document creation fails
    """
    supabase = get_supabase_authed(user_token)
    
    data = {
        "user_id": user_id,
        "title": title,
        "source_type": source_type,
        "original_content": original_content,
        "token_count": token_count,
        "word_count": word_count,
        "source_reference": source_reference,
        "metadata": metadata or {}
    }
    
    try:
        result = supabase.table("documents").insert(data).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
        raise Exception("Failed to create document record")
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        raise


def get_document(document_id: str, user_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a document by ID.
    
    Uses authenticated client to enforce RLS (user can only see own documents).
    """
    supabase = get_supabase_authed(user_token)
    try:
        result = supabase.table("documents").select("*").eq("id", document_id).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"Error retrieving document {document_id}: {str(e)}")
        return None


def delete_document(document_id: str, user_token: str) -> bool:
    """
    Delete a document and its associated chunks/concepts (cascades via FK).
    
    Uses authenticated client to enforce RLS.
    """
    supabase = get_supabase_authed(user_token)
    try:
        supabase.table("documents").delete().eq("id", document_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        return False
