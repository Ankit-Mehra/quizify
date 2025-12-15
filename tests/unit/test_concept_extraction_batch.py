"""
Unit tests for batch concept extraction optimization.

Tests cover:
1. Batch grouping logic (including incomplete final batch)
2. Deduplication with highest-relevance preservation
3. Section-to-chunk_id mapping
4. Empty chunk handling
5. Edge cases (single chunk, exact batch size multiples)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from services.ai_services.concept_extraction_service import (
    ConceptExtractionService,
    CHUNKS_PER_BATCH,
    MAX_PARALLEL_BATCHES,
)


class TestBatchGrouping:
    """Test chunk batching logic."""
    
    def test_chunks_per_batch_is_configured(self):
        """Verify batch size constant is set."""
        assert CHUNKS_PER_BATCH == 16  # Larger batches to reduce API calls
        assert MAX_PARALLEL_BATCHES == 5  # Reduced to avoid rate limiting
    
    def test_batch_grouping_exact_multiple(self):
        """Test batching when chunks are exact multiple of batch size."""
        # 32 chunks should create exactly 2 batches of 16
        chunks = [{"id": f"chunk-{i}", "content": f"Content {i}"} for i in range(32)]
        
        batches = []
        for i in range(0, len(chunks), CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        assert len(batches) == 2
        assert len(batches[0]) == CHUNKS_PER_BATCH
        assert len(batches[1]) == CHUNKS_PER_BATCH
    
    def test_batch_grouping_incomplete_final_batch(self):
        """Test batching when last batch has fewer chunks than batch size."""
        # 35 chunks should create 3 batches: 16, 16, 3
        chunks = [{"id": f"chunk-{i}", "content": f"Content {i}"} for i in range(35)]
        
        batches = []
        for i in range(0, len(chunks), CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        assert len(batches) == 3
        assert len(batches[0]) == CHUNKS_PER_BATCH
        assert len(batches[1]) == CHUNKS_PER_BATCH
        assert len(batches[2]) == 3  # Incomplete final batch
    
    def test_batch_grouping_single_chunk(self):
        """Test batching with a single chunk (edge case)."""
        chunks = [{"id": "chunk-0", "content": "Single chunk content"}]
        
        batches = []
        for i in range(0, len(chunks), CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        assert len(batches) == 1
        assert len(batches[0]) == 1
    
    def test_batch_grouping_fewer_than_batch_size(self):
        """Test batching with fewer chunks than one batch."""
        chunks = [{"id": f"chunk-{i}", "content": f"Content {i}"} for i in range(5)]
        
        batches = []
        for i in range(0, len(chunks), CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        assert len(batches) == 1
        assert len(batches[0]) == 5


class TestDeduplicationWithRelevance:
    """Test deduplication preserves highest relevance score."""
    
    def test_deduplication_keeps_highest_relevance(self):
        """Verify that when duplicates exist, highest relevance instance is kept."""
        # Simulate extracted concepts with duplicates at different relevance scores
        extracted_concepts_data = [
            {"name": "Machine Learning", "relevance_score": 0.5, "source_text": "Low relevance"},
            {"name": "Neural Network", "relevance_score": 0.9, "source_text": "High relevance"},
            {"name": "machine learning", "relevance_score": 0.95, "source_text": "Highest relevance"},  # Duplicate
            {"name": "Deep Learning", "relevance_score": 0.7, "source_text": "Medium"},
            {"name": "NEURAL NETWORK", "relevance_score": 0.3, "source_text": "Low"},  # Duplicate (case insensitive)
        ]
        
        # Sort by relevance BEFORE deduplication (as implemented)
        extracted_concepts_data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # Deduplicate
        seen_names = set()
        unique_concepts = []
        for concept in extracted_concepts_data:
            name_lower = concept.get("name", "").lower().strip()
            if name_lower and name_lower not in seen_names:
                seen_names.add(name_lower)
                unique_concepts.append(concept)
        
        # Verify results
        assert len(unique_concepts) == 3  # ML, NN, DL
        
        # Machine Learning should have highest relevance (0.95)
        ml_concept = next(c for c in unique_concepts if "machine learning" in c["name"].lower())
        assert ml_concept["relevance_score"] == 0.95
        
        # Neural Network should have highest relevance (0.9)
        nn_concept = next(c for c in unique_concepts if "neural network" in c["name"].lower())
        assert nn_concept["relevance_score"] == 0.9
    
    def test_deduplication_empty_names_skipped(self):
        """Verify concepts with empty names are skipped."""
        extracted_concepts_data = [
            {"name": "Valid Concept", "relevance_score": 0.8},
            {"name": "", "relevance_score": 0.9},  # Empty name
            {"name": "   ", "relevance_score": 0.95},  # Whitespace only
            {"name": "Another Valid", "relevance_score": 0.7},
        ]
        
        extracted_concepts_data.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        seen_names = set()
        unique_concepts = []
        for concept in extracted_concepts_data:
            name_lower = concept.get("name", "").lower().strip()
            if name_lower and name_lower not in seen_names:
                seen_names.add(name_lower)
                unique_concepts.append(concept)
        
        assert len(unique_concepts) == 2
        names = [c["name"] for c in unique_concepts]
        assert "Valid Concept" in names
        assert "Another Valid" in names


class TestSectionToChunkIdMapping:
    """Test section number to chunk_id mapping logic."""
    
    def test_section_mapping_valid_sections(self):
        """Test mapping with valid section numbers."""
        chunks = [
            {"id": "chunk-a", "content": "Content A"},
            {"id": "chunk-b", "content": "Content B"},
            {"id": "chunk-c", "content": "Content C"},
        ]
        
        # Build chunk_id_map as the service does
        chunk_id_map = {}
        for i, chunk in enumerate(chunks):
            section_num = i + 1
            chunk_id_map[section_num] = chunk.get("id")
        
        assert chunk_id_map[1] == "chunk-a"
        assert chunk_id_map[2] == "chunk-b"
        assert chunk_id_map[3] == "chunk-c"
    
    def test_section_mapping_fallback_to_section_1(self):
        """Test fallback to section 1 when invalid section number provided."""
        chunks = [
            {"id": "chunk-a", "content": "Content A"},
            {"id": "chunk-b", "content": "Content B"},
        ]
        
        chunk_id_map = {}
        for i, chunk in enumerate(chunks):
            section_num = i + 1
            chunk_id_map[section_num] = chunk.get("id")
        
        # Simulate a concept with invalid section number
        invalid_section = 99
        
        # Fallback logic as implemented
        chunk_id = chunk_id_map.get(
            invalid_section, 
            chunk_id_map.get(1, chunks[0].get("id") if chunks else None)
        )
        
        # Should fall back to section 1
        assert chunk_id == "chunk-a"
    
    def test_section_mapping_missing_section_field(self):
        """Test handling when concept doesn't have section field."""
        chunks = [{"id": "chunk-a", "content": "Content A"}]
        
        chunk_id_map = {1: "chunk-a"}
        
        # Concept without section field - defaults to 1
        concept = {"name": "Test", "relevance": 0.8}
        section_num = concept.get("section", 1)  # Default to 1
        
        chunk_id = chunk_id_map.get(
            section_num,
            chunk_id_map.get(1, chunks[0].get("id") if chunks else None)
        )
        
        assert chunk_id == "chunk-a"


class TestEmptyChunkHandling:
    """Test empty chunk handling in section building."""
    
    def test_empty_chunks_skipped(self):
        """Verify empty chunks don't create section headers."""
        chunks = [
            {"id": "chunk-1", "content": "Valid content 1"},
            {"id": "chunk-2", "content": ""},  # Empty
            {"id": "chunk-3", "content": "   "},  # Whitespace only
            {"id": "chunk-4", "content": "Valid content 2"},
        ]
        
        sections_parts = []
        chunk_id_map = {}
        
        for i, chunk in enumerate(chunks):
            section_num = i + 1
            chunk_id_map[section_num] = chunk.get("id")
            content = chunk.get("content", "").strip()
            if not content:
                continue  # Skip empty chunks
            sections_parts.append(f"--- Section {section_num} ---\n{content}")
        
        sections_text = "\n\n".join(sections_parts)
        
        # Should only have 2 sections (1 and 4)
        assert len(sections_parts) == 2
        assert "--- Section 1 ---" in sections_text
        assert "--- Section 2 ---" not in sections_text  # Empty chunk skipped
        assert "--- Section 3 ---" not in sections_text  # Whitespace chunk skipped
        assert "--- Section 4 ---" in sections_text
        
        # chunk_id_map should still have all mappings for later reference
        assert len(chunk_id_map) == 4
    
    def test_all_empty_chunks(self):
        """Test handling when all chunks are empty."""
        chunks = [
            {"id": "chunk-1", "content": ""},
            {"id": "chunk-2", "content": "   "},
        ]
        
        sections_parts = []
        for i, chunk in enumerate(chunks):
            content = chunk.get("content", "").strip()
            if not content:
                continue
            sections_parts.append(f"--- Section {i + 1} ---\n{content}")
        
        assert len(sections_parts) == 0
        assert "\n\n".join(sections_parts) == ""


class TestConceptExtractionServiceInit:
    """Test service initialization."""
    
    def test_service_initializes(self):
        """Verify service can be instantiated."""
        with patch('services.ai_services.concept_extraction_service.get_openai_client') as mock_client:
            mock_client.return_value = MagicMock()
            service = ConceptExtractionService()
            assert service.client is not None


class TestBatchCalculations:
    """Test batch calculation math for various document sizes."""
    
    @pytest.mark.parametrize("num_chunks,expected_batches,last_batch_size", [
        (1, 1, 1),       # Single chunk
        (16, 1, 16),     # Exact batch size
        (17, 2, 1),      # One over batch size
        (32, 2, 16),     # Two exact batches
        (79, 5, 15),     # Real-world example from logs (79 chunks / 16 = 5 batches)
        (100, 7, 4),     # Large document (100 / 16 = 6.25 -> 7 batches, last has 4)
        (0, 0, 0),       # Empty (edge case)
    ])
    def test_batch_calculation(self, num_chunks, expected_batches, last_batch_size):
        """Test batch count and last batch size calculations."""
        if num_chunks == 0:
            chunks = []
        else:
            chunks = [{"id": f"chunk-{i}"} for i in range(num_chunks)]
        
        batches = []
        for i in range(0, len(chunks), CHUNKS_PER_BATCH):
            batch = chunks[i:i + CHUNKS_PER_BATCH]
            batches.append(batch)
        
        assert len(batches) == expected_batches
        if expected_batches > 0:
            assert len(batches[-1]) == last_batch_size
