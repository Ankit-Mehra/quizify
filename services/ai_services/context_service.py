from typing import Literal, Dict, Any
from services.db_services.supabase_chunks import get_chunk, match_chunks
from services.logger import ai_logger as logger


class ContextService:
    """
    Manages context retrieval for question generation.
    
    Two modes:
    - standard: Uses only the source chunk (~500 tokens) - fast, cheap
    - enhanced: Uses chunk + related chunks (~1500 tokens) - for comparison questions
    """
    
    def get_context_for_concept(
        self,
        concept: Dict[str, Any],
        user_token: str,
        mode: Literal["standard", "enhanced"] = "standard"
    ) -> str:
        """
        Retrieve context for a concept based on the selected mode.
        
        Args:
            concept: Concept dict with chunk_id, embedding, etc.
            user_token: JWT token for RLS enforcement
            mode: "standard" (chunk only) or "enhanced" (chunk + related)
            
        Returns:
            Context string for question generation
        """
        chunk_id = concept.get("chunk_id")
        if not chunk_id:
            # Fallback if no chunk_id (shouldn't happen in normal flow)
            logger.warning(f"No chunk_id for concept {concept.get('id')}, using source_text")
            return concept.get("source_text", "")
            
        # Get the main chunk
        main_chunk = get_chunk(chunk_id, user_token)
        if not main_chunk:
            logger.warning(f"Chunk {chunk_id} not found for concept {concept.get('id')}")
            return concept.get("source_text", "")
            
        context = f"Primary Source:\n{main_chunk['content']}\n"
        
        # If standard mode, we are done
        if mode == "standard":
            return context
            
        # Enhanced mode: find related chunks for cross-referencing
        if mode == "enhanced" and concept.get("embedding"):
            related_chunks = match_chunks(
                query_embedding=concept["embedding"],
                user_token=user_token,
                match_threshold=0.6,
                match_count=3,
                filter_document_id=concept.get("document_id") 
            )
            
            # Filter out the main chunk (avoid redundancy)
            related_chunks = [c for c in related_chunks if c["id"] != chunk_id]
            
            if related_chunks:
                context += "\nRelated Context:\n"
                for i, chunk in enumerate(related_chunks[:2]):  # Limit to 2 related
                    context += f"--- Related Source {i+1} ---\n{chunk['content']}\n"
                    
        return context
    
    def determine_context_mode(
        self,
        question_type: str,
        bloom_level: str = None,
        user_preference: str = None
    ) -> Literal["standard", "enhanced"]:
        """
        Determine whether to use standard or enhanced context mode.
        
        Standard Mode (~80% of questions):
            - Faster (no similarity search)
            - Cheaper (~$0.0003/question)
            - Good for: define, explain, apply, create questions
        
        Enhanced Mode (~20% of questions):
            - Slower (+100-200ms for similarity search)
            - More expensive (~$0.0008/question)
            - Good for: compare, contrast, relationship questions
        """
        # User can force enhanced mode
        if user_preference == "enhanced":
            return "enhanced"
        
        # Analyze bloom level - "analyze" often needs cross-references
        if bloom_level == "analyze":
            return "enhanced"
        
        # Check question type for comparison indicators
        comparison_keywords = ["compare", "contrast", "versus", "difference", 
                              "similarity", "relationship", "distinguish"]
        if any(kw in question_type.lower() for kw in comparison_keywords):
            return "enhanced"
        
        # Default to standard (covers 80% of cases well)
        return "standard"
