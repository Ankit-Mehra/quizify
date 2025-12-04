from typing import Dict, Any, List
from services.db_services.supabase_chunks import get_chunk, match_chunks
from services.logger import ai_logger as logger


class ContextService:
    """
    Manages context retrieval for RAG-based question generation.
    
    Always retrieves chunk + related chunks for rich context.
    For matching questions, aggregates context from multiple concepts.
    """
    
    def get_context_for_concept(
        self,
        concept: Dict[str, Any],
        user_token: str
    ) -> str:
        """
        Retrieve context for a concept (chunk + related chunks).
        
        Args:
            concept: Concept dict with chunk_id, embedding, etc.
            user_token: JWT token for RLS enforcement
            
        Returns:
            Context string with primary chunk and related chunks
        """
        chunk_id = concept.get("chunk_id")
        if not chunk_id:
            logger.warning(f"No chunk_id for concept {concept.get('id')}, using source_text")
            return concept.get("source_text", "")
            
        # Get the main chunk
        main_chunk = get_chunk(chunk_id, user_token)
        if not main_chunk:
            logger.warning(f"Chunk {chunk_id} not found for concept {concept.get('id')}")
            return concept.get("source_text", "")
            
        context = f"Primary Source:\n{main_chunk['content']}\n"
        
        # Find related chunks for richer context
        if concept.get("embedding"):
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
    
    def get_aggregated_context_for_matching(
        self,
        concepts: List[Dict[str, Any]],
        user_token: str
    ) -> str:
        """
        Aggregate context from multiple concepts for matching questions.
        
        Matching questions need 4 pairs, so we combine context from 4 concepts
        to give the LLM enough material to create meaningful matches.
        
        Args:
            concepts: List of 4 concept dicts to aggregate
            user_token: JWT token for RLS enforcement
            
        Returns:
            Aggregated context string from all concepts
        """
        if not concepts:
            return ""
            
        aggregated_parts = []
        seen_chunk_ids = set()
        
        for i, concept in enumerate(concepts[:4]):  # Limit to 4 concepts
            chunk_id = concept.get("chunk_id")
            
            # Skip if we've already included this chunk
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            
            concept_name = concept.get("name", f"Concept {i+1}")
            
            if not chunk_id:
                # Fallback to source_text if no chunk_id
                source_text = concept.get("source_text", "")
                if source_text:
                    aggregated_parts.append(f"=== {concept_name} ===\n{source_text}")
                continue
                
            # Get the chunk content
            chunk = get_chunk(chunk_id, user_token)
            if chunk:
                aggregated_parts.append(f"=== {concept_name} ===\n{chunk['content']}")
            else:
                # Fallback to source_text
                source_text = concept.get("source_text", "")
                if source_text:
                    aggregated_parts.append(f"=== {concept_name} ===\n{source_text}")
        
        if not aggregated_parts:
            logger.warning("No content found for matching question aggregation")
            return ""
            
        context = "Use the following sources to create 4 matching pairs:\n\n"
        context += "\n\n".join(aggregated_parts)
        
        logger.debug(f"Aggregated context from {len(aggregated_parts)} concepts for matching")
        return context

