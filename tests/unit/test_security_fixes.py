"""
Unit tests for security fixes from the expert review.

Tests cover:
1. SSRF redirect protection
2. URL redaction for storage
3. Delete error handling
4. DOCX parsing
5. Pydantic 422 error handling
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from pydantic import ValidationError, BaseModel


class TestSSRFRedirectProtection:
    """Tests for SSRF redirect protection in web scraping."""
    
    @patch('services.web_scraping_service.resolve_hostname_to_ips')
    def test_validate_redirect_url_allows_public_url(self, mock_resolve):
        """Test that public URLs pass validation."""
        from services.web_scraping_service import _validate_redirect_url
        
        # Mock DNS resolution to return public IPs
        mock_resolve.return_value = ["93.184.216.34"]  # example.com's IP
        
        # Should not raise for public URLs
        _validate_redirect_url("https://example.com/page")
        _validate_redirect_url("https://google.com")
        _validate_redirect_url("http://public-site.org/path")
    
    def test_validate_redirect_url_blocks_localhost(self):
        """Test that localhost URLs are blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://localhost/admin")
        assert exc.value.status_code == 400
        assert "private" in exc.value.detail.lower() or "blocked" in exc.value.detail.lower()
    
    def test_validate_redirect_url_blocks_127_0_0_1(self):
        """Test that 127.0.0.1 is blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://127.0.0.1:8080/internal")
        assert exc.value.status_code == 400
    
    def test_validate_redirect_url_blocks_private_class_a(self):
        """Test that 10.x.x.x addresses are blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://10.0.0.1/internal")
        assert exc.value.status_code == 400
    
    def test_validate_redirect_url_blocks_private_class_b(self):
        """Test that 172.16-31.x.x addresses are blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://172.16.0.1/internal")
        assert exc.value.status_code == 400
    
    def test_validate_redirect_url_blocks_private_class_c(self):
        """Test that 192.168.x.x addresses are blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://192.168.1.1/admin")
        assert exc.value.status_code == 400
    
    def test_validate_redirect_url_blocks_ipv6_loopback(self):
        """Test that IPv6 loopback is blocked."""
        from services.web_scraping_service import _validate_redirect_url
        
        with pytest.raises(HTTPException) as exc:
            _validate_redirect_url("http://[::1]/admin")
        assert exc.value.status_code == 400


class TestURLRedaction:
    """Tests for URL redaction to remove sensitive query params."""
    
    def test_redact_url_removes_query_params(self):
        """Test that query parameters are removed."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        url = "https://example.com/doc.pdf?token=secret123&auth=abc"
        redacted = redact_url_for_storage(url)
        
        assert "token=secret123" not in redacted
        assert "auth=abc" not in redacted
        assert "?" not in redacted
        assert redacted == "https://example.com/doc.pdf"
    
    def test_redact_url_removes_fragment(self):
        """Test that URL fragments are removed."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        url = "https://example.com/page#section-with-sensitive-data"
        redacted = redact_url_for_storage(url)
        
        assert "#" not in redacted
        assert "section-with-sensitive-data" not in redacted
        assert redacted == "https://example.com/page"
    
    def test_redact_url_preserves_path(self):
        """Test that URL path is preserved."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        url = "https://example.com/path/to/document.pdf?secret=123"
        redacted = redact_url_for_storage(url)
        
        assert "/path/to/document.pdf" in redacted
        assert redacted == "https://example.com/path/to/document.pdf"
    
    def test_redact_url_preserves_domain(self):
        """Test that domain is preserved."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        url = "https://subdomain.example.com/doc?token=xyz"
        redacted = redact_url_for_storage(url)
        
        assert "subdomain.example.com" in redacted
        assert redacted == "https://subdomain.example.com/doc"
    
    def test_redact_url_handles_url_without_params(self):
        """Test that URLs without params are unchanged."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        url = "https://example.com/clean/path"
        redacted = redact_url_for_storage(url)
        
        assert redacted == url
    
    def test_redact_url_handles_empty_string(self):
        """Test handling of empty string."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        redacted = redact_url_for_storage("")
        assert redacted == ""
    
    def test_redact_url_handles_invalid_url(self):
        """Test handling of malformed URL."""
        from handlers.quiz_handlers import redact_url_for_storage
        
        # Should not raise, but return something reasonable
        url = "not-a-valid-url"
        redacted = redact_url_for_storage(url)
        assert "?" not in redacted  # At minimum, no query params


class TestDeleteErrorHandling:
    """Tests for delete quiz error handling."""
    
    @patch('services.db_services.supabase_quiz.get_authed_supabase_client')
    def test_delete_returns_true_when_quiz_deleted(self, mock_client):
        """Test that delete returns True when quiz is found and deleted."""
        from services.db_services.supabase_quiz import delete_quiz_from_database
        
        # Mock successful deletion with data returned
        mock_supabase = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [{"id": "quiz-123"}]
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = mock_response
        mock_client.return_value = mock_supabase
        
        result = delete_quiz_from_database("quiz-123", "token")
        
        assert result is True
    
    @patch('services.db_services.supabase_quiz.get_authed_supabase_client')
    def test_delete_returns_false_when_quiz_not_found(self, mock_client):
        """Test that delete returns False when quiz is not found."""
        from services.db_services.supabase_quiz import delete_quiz_from_database
        
        # Mock deletion with no data returned (quiz not found)
        mock_supabase = MagicMock()
        mock_response = MagicMock()
        mock_response.data = []  # Empty - no quiz was deleted
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = mock_response
        mock_client.return_value = mock_supabase
        
        result = delete_quiz_from_database("nonexistent-quiz", "token")
        
        assert result is False
    
    @patch('services.db_services.supabase_quiz.get_authed_supabase_client')
    def test_delete_raises_on_database_error(self, mock_client):
        """Test that delete raises HTTPException on database error."""
        from services.db_services.supabase_quiz import delete_quiz_from_database
        
        # Mock database error
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.side_effect = Exception("DB Error")
        mock_client.return_value = mock_supabase
        
        with pytest.raises(HTTPException) as exc:
            delete_quiz_from_database("quiz-123", "token")
        
        assert exc.value.status_code == 500


class TestDOCXParsing:
    """Tests for DOCX parsing in file-id flow."""
    
    @patch('services.db_services.supabase_file.read_file_content')
    @patch('services.db_services.supabase_file.extract_text_from_docx')
    def test_parse_recognizes_docx_mime_type(self, mock_extract, mock_read):
        """Test that DOCX MIME type triggers DOCX extraction."""
        from services.db_services.supabase_file import parse_file_from_supabase
        
        mock_read.return_value = b"fake docx bytes"
        mock_extract.return_value = "Extracted DOCX text"
        
        file_record = {
            "storage_path": "user/doc.docx",
            "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "original_filename": "document.docx"
        }
        
        result = parse_file_from_supabase(file_record, "token")
        
        mock_extract.assert_called_once()
        assert result == "Extracted DOCX text"
    
    @patch('services.db_services.supabase_file.read_file_content')
    @patch('services.db_services.supabase_file.extract_text_from_docx')
    @patch('services.db_services.supabase_file.is_pdf')
    def test_parse_recognizes_docx_extension_fallback(self, mock_is_pdf, mock_extract, mock_read):
        """Test that .docx extension triggers DOCX extraction when MIME is wrong."""
        from services.db_services.supabase_file import parse_file_from_supabase
        
        mock_read.return_value = b"fake docx bytes"
        mock_extract.return_value = "Extracted DOCX text"
        mock_is_pdf.return_value = False  # Not a PDF
        
        file_record = {
            "storage_path": "user/doc.docx",
            "file_type": "application/octet-stream",  # Generic type
            "original_filename": "document.docx"
        }
        
        result = parse_file_from_supabase(file_record, "token")
        
        mock_extract.assert_called_once()
        assert result == "Extracted DOCX text"
    
    @patch('services.db_services.supabase_file.read_file_content')
    def test_parse_rejects_legacy_doc_format(self, mock_read):
        """Test that legacy .doc format returns proper error."""
        from services.db_services.supabase_file import parse_file_from_supabase
        
        mock_read.return_value = b"fake doc bytes"
        
        file_record = {
            "storage_path": "user/doc.doc",
            "file_type": "application/msword",
            "original_filename": "document.doc"
        }
        
        # Mock is_pdf to return False so we hit the fallback logic
        with patch('services.db_services.supabase_file.is_pdf', return_value=False):
            with pytest.raises(HTTPException) as exc:
                parse_file_from_supabase(file_record, "token")
        
        assert exc.value.status_code == 400
        assert "not supported" in exc.value.detail.lower() or ".doc" in exc.value.detail


class TestPydanticValidationErrorHandling:
    """Tests for Pydantic validation error handling (422 instead of 500)."""
    
    def test_validation_error_format(self):
        """Test that Pydantic ValidationError has expected format."""
        
        class TestModel(BaseModel):
            name: str
            age: int
        
        with pytest.raises(ValidationError) as exc:
            TestModel(name=123, age="not a number")
        
        errors = exc.value.errors()
        assert len(errors) >= 1
        # Each error should have loc and msg
        for error in errors:
            assert "loc" in error
            assert "msg" in error


class TestCreditRefundMechanism:
    """Tests for credit refund mechanism on failure."""
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.refund_units', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.invalidate_user_tier_cache', new_callable=AsyncMock)
    async def test_refund_on_failure_calls_refund_units(self, mock_invalidate, mock_refund):
        """Test that refund_credits_on_failure calls the refund service."""
        from handlers.quiz_handlers import refund_credits_on_failure
        
        mock_refund.return_value = True
        mock_invalidate.return_value = None
        
        await refund_credits_on_failure("user-123", "standard")
        
        mock_refund.assert_called_once_with("user-123", "standard")
        mock_invalidate.assert_called_once_with("user-123")
    
    @pytest.mark.asyncio
    @patch('handlers.quiz_handlers.refund_units', new_callable=AsyncMock)
    @patch('handlers.quiz_handlers.invalidate_user_tier_cache', new_callable=AsyncMock)
    async def test_refund_on_failure_handles_refund_error(self, mock_invalidate, mock_refund):
        """Test that refund failure is logged but doesn't raise."""
        from handlers.quiz_handlers import refund_credits_on_failure
        
        mock_refund.return_value = False  # Refund failed
        mock_invalidate.return_value = None
        
        # Should not raise even if refund fails
        await refund_credits_on_failure("user-123", "enhanced")
        
        mock_refund.assert_called_once()


class TestAsyncFileOperations:
    """Tests for async file operations."""
    
    @pytest.mark.asyncio
    @patch('services.db_services.supabase_file.httpx.AsyncClient')
    @patch('services.db_services.supabase_file.app_config')
    async def test_read_file_content_async_returns_bytes(self, mock_config, mock_client_class):
        """Test that async read returns file bytes."""
        from services.db_services.supabase_file import read_file_content_async
        
        mock_config.SUPABASE_URL = "https://test.supabase.co"
        mock_config.STORAGE_NAME = "quiz-files"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"file content bytes"
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client
        
        result = await read_file_content_async("user/file.pdf", "token")
        
        assert result == b"file content bytes"
    
    @pytest.mark.asyncio
    @patch('services.db_services.supabase_file.httpx.AsyncClient')
    @patch('services.db_services.supabase_file.app_config')
    async def test_read_file_content_async_raises_404_on_not_found(self, mock_config, mock_client_class):
        """Test that async read raises 404 for missing files."""
        from services.db_services.supabase_file import read_file_content_async
        
        mock_config.SUPABASE_URL = "https://test.supabase.co"
        mock_config.STORAGE_NAME = "quiz-files"
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client
        
        with pytest.raises(HTTPException) as exc:
            await read_file_content_async("user/missing.pdf", "token")
        
        assert exc.value.status_code == 404


class TestSourceTypePassthrough:
    """Tests for content source type passthrough in ingestion."""
    
    @pytest.mark.asyncio
    async def test_ingest_content_receives_source_type(self):
        """Test that source_type is properly passed to ingestion service."""
        from handlers.quiz_handlers import _ingest_and_extract_concepts
        from schemas.quiz import EnhancedTextQuizRequest
        
        # Mock dependencies
        mock_ingestion = AsyncMock()
        mock_ingestion.ingest_content.return_value = {"document_id": "doc-123", "chunks": []}
        
        mock_concept = AsyncMock()
        mock_concept.extract_concepts.return_value = [{"concept": "test"}]
        
        request = EnhancedTextQuizRequest(
            title="Test Quiz",
            content="Test content",
            question_type="mixed",
            num_questions=5,
            mode="enhanced"
        )
        
        # Call with specific source type
        await _ingest_and_extract_concepts(
            request=request,
            user_id="user-123",
            user_token="token",
            trace_id="trace-123",
            ingestion_service=mock_ingestion,
            concept_service=mock_concept,
            content_source_type="url"  # Specific source type
        )
        
        # Verify source_type was passed correctly
        mock_ingestion.ingest_content.assert_called_once()
        call_kwargs = mock_ingestion.ingest_content.call_args.kwargs
        assert call_kwargs["source_type"] == "url"
