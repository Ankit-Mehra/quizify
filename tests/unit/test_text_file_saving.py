"""
Unit tests for text input file saving functionality.

Tests the new feature that saves text input as files in Supabase Storage,
ensuring consistency with file upload and URL-based quiz generation.

Focus: Testing sanitize_filename helper and MAX_FILE_SIZE constant.
Integration testing is done via contract tests in tests/contract/.
"""

import pytest


class TestSanitizeFilename:
    """Unit tests for sanitize_filename helper function."""
    
    def test_removes_special_characters(self):
        """Test that sanitize_filename removes special characters."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("Test@Quiz#2024!.pdf")
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result
        
    def test_replaces_spaces_with_underscores(self):
        """Test that spaces are replaced with underscores."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("My Test Quiz")
        assert " " not in result
        assert "_" in result
    
    def test_limits_length_to_50_characters(self):
        """Test that filename is limited to 50 characters."""
        from handlers.quiz_handlers import sanitize_filename
        
        long_name = "A" * 100
        result = sanitize_filename(long_name)
        assert len(result) <= 50
    
    def test_handles_empty_input(self):
        """Test that empty input returns default name."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("")
        assert result == "quiz_content"
    
    def test_handles_only_special_characters(self):
        """Test that string with only special characters returns default."""
        from handlers.quiz_handlers import sanitize_filename
        
        result = sanitize_filename("@#$%^&*()")
        assert result == "quiz_content"
    
    def test_produces_valid_storage_names(self):
        """Test that sanitize_filename produces valid names for Supabase storage."""
        from handlers.quiz_handlers import sanitize_filename
        
        test_cases = [
            "Normal Title",
            "Title@With#Special!Chars",
            "   Spaces   ",
            "Mixed 123 Numbers",
            "Unicode café naïve",
        ]
        
        for title in test_cases:
            result = sanitize_filename(title)
            assert result  # Should never be empty
            assert len(result) <= 50  # Length limit enforced
            # Should only contain alphanumeric, underscore, hyphen
            assert all(c.isalnum() or c in '_-' for c in result)


class TestFileSizeConstant:
    """Test file size limit constant."""
    
    def test_max_file_size_is_10mb(self):
        """Test that MAX_FILE_SIZE is set to 10MB."""
        from handlers.quiz_handlers import MAX_FILE_SIZE
        
        expected_size = 10 * 1024 * 1024  # 10MB in bytes
        assert MAX_FILE_SIZE == expected_size
        assert MAX_FILE_SIZE == 10485760  # 10MB in bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
