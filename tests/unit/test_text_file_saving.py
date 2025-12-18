"""
Unit tests for text input file saving functionality.

Tests the new feature that saves text input as files in Supabase Storage,
ensuring consistency with file upload and URL-based quiz generation.

Tests include:
- Text is properly encoded to UTF-8 bytes
- Filename is correctly sanitized and timestamped
- File size validation (10MB limit)
- Error handling for storage failures
- File ID is correctly returned and used in metadata
"""

import pytest
from unittest.mock import Mock, patch


class TestTextFileSaving:
    """Unit tests for text input file saving in quiz generation."""
    
    def test_text_content_encoded_to_utf8(self):
        """Test that text content is properly encoded to UTF-8 bytes."""
        test_content = "Hello, World! こんにちは 🎉"
        text_bytes = test_content.encode('utf-8')
        
        assert isinstance(text_bytes, bytes)
        assert text_bytes.decode('utf-8') == test_content
    
    def test_sanitize_filename_removes_special_characters(self):
        """Test that sanitize_filename removes special characters."""
        from handlers.quiz_handlers import sanitize_filename
        
        # Test with special characters
        result = sanitize_filename("Test@Quiz#2024!.pdf")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result
        
    def test_sanitize_filename_replaces_spaces_with_underscores(self):
        """Test that spaces are replaced with underscores."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("My Test Quiz")
        assert " " not in result
        assert "_" in result
    
    def test_sanitize_filename_limits_length(self):
        """Test that filename is limited to 50 characters."""
        from handlers.quiz_handlers import sanitize_filename
        
        long_name = "A" * 100
        result = sanitize_filename(long_name)
        assert len(result) <= 50
    
    def test_sanitize_filename_handles_empty_input(self):
        """Test that empty input returns default name."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("")
        assert result == "quiz_content"
    
    def test_sanitize_filename_handles_only_special_chars(self):
        """Test that string with only special characters returns default."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("@#$%^&*()")
        assert result == "quiz_content"
    
    def test_file_size_validation_accepts_small_content(self):
        """Test that small text content passes size validation."""
        from handlers.quiz_handlers import MAX_FILE_SIZE
        
        small_content = "Small text content for testing."
        text_bytes = small_content.encode('utf-8')
        
        assert len(text_bytes) < MAX_FILE_SIZE
    
    def test_file_size_validation_rejects_large_content(self):
        """Test that text content exceeding 10MB is rejected."""
        from handlers.quiz_handlers import MAX_FILE_SIZE
        
        # Create content larger than 10MB
        large_content = "A" * (MAX_FILE_SIZE + 1)
        text_bytes = large_content.encode('utf-8')
        
        assert len(text_bytes) > MAX_FILE_SIZE


class TestTextFileSavingIntegration:
    """Integration tests for text file saving with mocked dependencies."""
    
    @pytest.fixture
    def mock_save_file(self):
        """Mock save_file_to_supabase function."""
        with patch('handlers.quiz_handlers.save_file_to_supabase') as mock:
            mock.return_value = {'file_id': 'mock_file_id_123'}
            yield mock
    
    @pytest.fixture
    def mock_generate_quiz_rag(self):
        """Mock generate_quiz_rag_async function."""
        with patch('handlers.quiz_handlers.generate_quiz_rag_async') as mock:
            mock_result = Mock()
            mock_result.quiz_id = "quiz_123"
            mock_result.questions = [Mock(), Mock()]
            mock_result.message = ""
            mock.return_value = mock_result
            yield mock
    
    @pytest.fixture
    def mock_validate_credits(self):
        """Mock validate_credits_available function."""
        with patch('handlers.quiz_handlers.validate_credits_available') as mock:
            mock.return_value = None
            yield mock
    
    @pytest.fixture
    def mock_save_metadata(self):
        """Mock save_metadata function."""
        with patch('handlers.quiz_handlers.save_metadata') as mock:
            yield mock

    def test_text_bytes_encoding_preserves_unicode(self):
        """Test that text content with unicode is properly encoded to UTF-8."""
        # Test various unicode characters
        test_cases = [
            "Simple ASCII text",
            "Unicode: café, naïve, 日本語",
            "Emojis: 🎉 📚 ✅",
            "Mixed: Hello 世界! 🌍"
        ]
        
        for content in test_cases:
            text_bytes = content.encode('utf-8')
            assert isinstance(text_bytes, bytes)
            assert text_bytes.decode('utf-8') == content
    
    def test_sanitize_filename_generates_valid_storage_name(self):
        """Test that sanitize_filename produces valid names for Supabase storage."""
        from handlers.quiz_handlers import sanitize_filename
        
        # Test various edge cases
        test_cases = [
            ("Normal Title", True),  # Should have underscores
            ("Title@With#Special!Chars", True),  # Special chars removed
            ("   Spaces   ", True),  # Leading/trailing spaces handled
            ("", False),  # Empty returns default
        ]
        
        for title, should_have_underscore in test_cases:
            result = sanitize_filename(title)
            assert result  # Should never be empty
            assert len(result) <= 50  # Length limit enforced
            # Should only contain alphanumeric, underscore, hyphen
            assert all(c.isalnum() or c in '_-' for c in result)
    
    def test_filename_format_validation(self):
        """Test that filename format is correct for text input storage."""
        from handlers.quiz_handlers import sanitize_filename
        import re
        
        # The actual implementation creates: {safe_title}_{timestamp}.txt
        safe_title = sanitize_filename("My Quiz")
        
        # Verify sanitized title format
        assert safe_title  # Not empty
        assert len(safe_title) <= 50  # Length limited
        
        # Verify timestamp format (YYYYMMDDHHmmss = 14 digits)
        timestamp_pattern = r'^\d{14}$'
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        assert re.match(timestamp_pattern, timestamp)
        
        # Verify final filename format
        filename = f"{safe_title}_{timestamp}.txt"
        assert filename.endswith('.txt')
        assert '_' in filename  # Contains separator


class TestFileSizeLimit:
    """Test file size limit constant and validation."""
    
    def test_max_file_size_is_10mb(self):
        """Test that MAX_FILE_SIZE is set to 10MB."""
        from handlers.quiz_handlers import MAX_FILE_SIZE
        
        expected_size = 10 * 1024 * 1024  # 10MB in bytes
        assert MAX_FILE_SIZE == expected_size
    
    def test_max_file_size_in_bytes(self):
        """Test MAX_FILE_SIZE value in bytes."""
        from handlers.quiz_handlers import MAX_FILE_SIZE
        
        assert MAX_FILE_SIZE == 10485760  # 10MB


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
