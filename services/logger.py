import logging
import os
from logging.handlers import RotatingFileHandler
import sys

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

def setup_logger(name, log_file, level=logging.INFO):
    """Function to setup a logger with both file and console handlers"""
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Create file handler that logs all messages
    file_handler = RotatingFileHandler(
        os.path.join('logs', log_file), 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # Create console handler with same log level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # Get or create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Only add handlers if they don't exist
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    # Prevent logging from propagating to the root logger
    logger.propagate = False
    
    return logger

# Create main application loggers
ai_logger = setup_logger('ai_services', 'ai_services.log')
db_logger = setup_logger('db_services', 'db_services.log')
app_logger = setup_logger('app', 'app.log')

# Placeholder for any additional loggers
# auth_logger = setup_logger('auth', 'auth.log') 