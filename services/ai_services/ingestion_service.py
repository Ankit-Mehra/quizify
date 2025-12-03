import time
from typing import List, Dict, Any, Optional
from uuid import uuid4
import tiktoken

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

from config import config
from services.logger import ai_logger as logger
from services.db_services.supabase_documents import create_document
from services.db_services.supabase_chunks import create_chunks
from services.ai_services.openai_service import get_openai_client
from services.db_services.supabase_llm_analytics import track_llm_call
from services.ai_services.pricing import calculate_cost


class IngestionService:
    """
    Service for ingesting content into the RAG pipeline.
    
    Handles document creation, semantic chunking via LlamaIndex,
    embedding generation, and storage in Supabase pgvector.
    """
    
    def __init__(self):
        self.client = get_openai_client()
        self.splitter = SentenceSplitter(
            chunk_size=config.CHUNK_SIZE,
            chunk_overlap=config.CHUNK_OVERLAP
        )
        self.encoding = tiktoken.get_encoding("cl100k_base")

    async def _get_embeddings(self, texts: List[str], user_id: str, trace_id: str) -> List[List[float]]:
        """Generate embeddings using OpenAI client (with PostHog tracking)."""
        embeddings = []
        
        # Process in batches
        batch_size = config.EMBEDDING_BATCH_SIZE
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            start_time = time.time()
            
            try:
                # Use the wrapped client for PostHog analytics
                response = await self.client.embeddings.create(
                    input=batch,
                    model=config.EMBEDDING_MODEL,
                    dimensions=config.EMBEDDING_DIMENSIONS
                )
                
                # Extract embeddings (ensure order is preserved)
                batch_embeddings = [data.embedding for data in response.data]
                embeddings.extend(batch_embeddings)
                
                # Track analytics (Supabase)
                latency_ms = int((time.time() - start_time) * 1000)
                track_llm_call(
                    user_id=user_id,
                    trace_id=trace_id,
                    call_type="embedding",
                    model=config.EMBEDDING_MODEL,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    cost_usd=calculate_cost(config.EMBEDDING_MODEL, response.usage.prompt_tokens, 0)
                )
                
            except Exception as e:
                logger.error(f"Embedding generation failed: {str(e)}")
                raise
                
        return embeddings

    async def ingest_content(
        self,
        user_id: str,
        user_token: str,
        content: str,
        title: str,
        source_type: str,
        source_reference: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ingest content: create document, chunk it, embed it, store chunks.
        
        Args:
            user_id: UUID of the user
            user_token: JWT token for RLS enforcement
            content: Text content to ingest
            title: Document title
            source_type: 'file', 'url', or 'text'
            source_reference: Optional file_id or URL
            metadata: Optional additional metadata
            trace_id: Optional trace ID for analytics
            
        Returns:
            Dict with document_id, chunks_count, total_tokens
        """
        try:
            logger.info(f"Starting ingestion for user {user_id[:8]}..., title: {title}")
            
            # 1. Calculate stats
            tokens = self.encoding.encode(content)
            token_count = len(tokens)
            word_count = len(content.split())
            
            # 2. Create Document Record (with user_token for RLS)
            document = create_document(
                user_id=user_id,
                title=title,
                source_type=source_type,
                original_content=content,
                token_count=token_count,
                word_count=word_count,
                user_token=user_token,
                source_reference=source_reference,
                metadata=metadata
            )
            document_id = document["id"]
            logger.debug(f"Created document {document_id}")
            
            # 3. Chunk Content using LlamaIndex SentenceSplitter
            doc_obj = Document(text=content, metadata={"document_id": document_id})
            nodes = self.splitter.get_nodes_from_documents([doc_obj])
            logger.debug(f"Split into {len(nodes)} chunks")
            
            # Limit chunks per document to prevent abuse
            if len(nodes) > config.MAX_CHUNKS_PER_DOCUMENT:
                logger.warning(f"Document has {len(nodes)} chunks, limiting to {config.MAX_CHUNKS_PER_DOCUMENT}")
                nodes = nodes[:config.MAX_CHUNKS_PER_DOCUMENT]
            
            # 4. Generate Embeddings (batch async)
            texts = [node.text for node in nodes]
            trace_id = trace_id or str(uuid4())
            embeddings = await self._get_embeddings(texts, user_id, trace_id)
            
            # 5. Prepare Chunks for DB
            chunks_data = []
            for i, node in enumerate(nodes):
                chunk_tokens = len(self.encoding.encode(node.text))
                chunks_data.append({
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_index": i,
                    "content": node.text,
                    "token_count": chunk_tokens,
                    "embedding": embeddings[i],
                    "metadata": node.metadata or {}
                })
            
            # 6. Store Chunks (with user_token for RLS)
            stored_chunks = create_chunks(chunks_data, user_token)
            logger.info(f"Stored {len(stored_chunks)} chunks for document {document_id}")
            
            return {
                "document_id": document_id,
                "chunks": stored_chunks,
                "chunks_count": len(stored_chunks),
                "total_tokens": token_count
            }
            
        except Exception as e:
            logger.error(f"Ingestion failed: {str(e)}")
            raise
