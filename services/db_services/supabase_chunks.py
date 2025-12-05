from typing import List, Dict, Any, Optional
from services.logger import db_logger as logger
from config import config


def get_supabase_service():
    """Get service role client (bypasses RLS - use for reads/analytics only)."""
    return config.get_supabase_client()


def get_supabase_authed(user_token: str):
    """Get authenticated client (enforces RLS - use for user data operations)."""
    return config.get_authenticated_supabase_client(user_token)


def create_chunks(chunks_data: List[Dict[str, Any]], user_token: str) -> List[Dict[str, Any]]:
    """
    Batch insert chunks into the database.
    
    Uses authenticated client to enforce RLS policies.
    
    Args:
        chunks_data: List of chunk dicts with document_id, user_id, content, embedding, etc.
        user_token: User's JWT for RLS enforcement
        
    Returns:
        List of created chunk records
    """
    supabase = get_supabase_authed(user_token)
    
    try:
        # Supabase has a limit on request size, batch if too many
        batch_size = 50  # Reduced for embeddings which are large
        all_results = []
        
        for i in range(0, len(chunks_data), batch_size):
            batch = chunks_data[i:i + batch_size]
            result = supabase.table("chunks").insert(batch).execute()
            if result.data:
                all_results.extend(result.data)
                
        return all_results
    except Exception as e:
        logger.error(f"Error creating chunks: {str(e)}")
        raise


def get_chunks_by_document(document_id: str, user_token: str) -> List[Dict[str, Any]]:
    """
    Retrieve all chunks for a specific document.
    
    Uses authenticated client to enforce RLS.
    """
    supabase = get_supabase_authed(user_token)
    try:
        result = supabase.table("chunks").select("*").eq("document_id", document_id).order("chunk_index").execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error retrieving chunks for document {document_id}: {str(e)}")
        return []


def match_chunks(
    query_embedding: List[float],
    user_token: str,
    match_threshold: float = 0.7,
    match_count: int = 5,
    filter_user_id: Optional[str] = None,
    filter_document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector similarity search on chunks.
    
    Uses authenticated client for RLS enforcement.
    Note: The RPC function also filters by user_id for additional security.
    """
    supabase = get_supabase_authed(user_token)
    
    params = {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
        "filter_user_id": filter_user_id,
        "filter_document_id": filter_document_id
    }
    
    try:
        result = supabase.rpc("match_chunks", params).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error matching chunks: {str(e)}")
        return []


def get_chunk(chunk_id: str, user_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single chunk by ID.
    
    Uses authenticated client to enforce RLS.
    """
    supabase = get_supabase_authed(user_token)
    try:
        result = supabase.table("chunks").select("*").eq("id", chunk_id).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"Error retrieving chunk {chunk_id}: {str(e)}")
        return None
