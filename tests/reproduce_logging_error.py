import logging
import unittest.mock
import pytest

def test_logging_mock_error():
    logger = logging.getLogger("test_logger")
    
    # Create a mock handler
    mock_handler = unittest.mock.MagicMock()
    # If we don't set level, it will be a MagicMock
    # mock_handler.level = logging.INFO 
    
    logger.addHandler(mock_handler)
    
    try:
        logger.error("This is an error")
    except TypeError as e:
        print(f"Caught expected error: {e}")
        assert "'>=' not supported between instances of 'int' and 'MagicMock'" in str(e)
