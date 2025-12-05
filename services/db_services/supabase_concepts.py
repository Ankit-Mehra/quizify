from typing import List, Dict, Any, Optional
from services.logger import db_logger as logger
from config import config


def get_supabase_service():
    """Get service role client (bypasses RLS - use for reads/analytics only)."""
    return config.get_supabase_client()


def get_supabase_authed(user_token: str):
    """Get authenticated client (enforces RLS - use for user data operations)."""
    return config.get_authenticated_supabase_client(user_token)


def create_concepts(concepts_data: List[Dict[str, Any]], user_token: str) -> List[Dict[str, Any]]:
    """
    Batch insert concepts into the database.
    
    Uses authenticated client to enforce RLS policies.
    
    Args:
        concepts_data: List of concept dicts with document_id, user_id, name, embedding, etc.
        user_token: User's JWT for RLS enforcement
        
    Returns:
        List of created concept records
    """
    supabase = get_supabase_authed(user_token)
    
    try:
        # Batch insert to avoid hitting payload limits (embeddings are large)
        batch_size = 50
        all_results = []
        
        for i in range(0, len(concepts_data), batch_size):
            batch = concepts_data[i:i + batch_size]
            result = supabase.table("concepts").insert(batch).execute()
            if result.data:
                all_results.extend(result.data)
                
        return all_results
    except Exception as e:
        logger.error(f"Error creating concepts: {str(e)}")
        raise


def get_concepts_by_document(document_id: str, user_token: str) -> List[Dict[str, Any]]:
    """
    Retrieve all concepts for a specific document.
    
    Uses authenticated client to enforce RLS.
    """
    supabase = get_supabase_authed(user_token)
    try:
        result = supabase.table("concepts").select("*").eq("document_id", document_id).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error retrieving concepts for document {document_id}: {str(e)}")
        return []


def match_concepts(
    query_embedding: List[float],
    user_token: str,
    match_threshold: float = 0.6,
    match_count: int = 10,
    filter_user_id: Optional[str] = None,
    filter_document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector similarity search on concepts.
    
    Uses authenticated client for RLS enforcement.
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
        result = supabase.rpc("match_concepts", params).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error matching concepts: {str(e)}")
        return []


def get_concept(concept_id: str, user_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single concept by ID.
    
    Uses authenticated client to enforce RLS.
    """
    supabase = get_supabase_authed(user_token)
    try:
        result = supabase.table("concepts").select("*").eq("id", concept_id).single().execute()
        return result.data
    except Exception as e:
        logger.error(f"Error retrieving concept {concept_id}: {str(e)}")
        return None
