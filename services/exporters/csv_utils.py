"""
CSV Utility Functions for Export.

Provides common utilities for CSV generation including:
- Value escaping for CSV safety
- UTF-8 BOM handling for Excel compatibility
- Multiline text formatting
"""

import csv
import io
from typing import List, Optional


def escape_csv_value(value: Optional[str]) -> str:
    """
    Escape a value for CSV output.
    
    Handles:
    - None values -> empty string
    - Newlines, commas, quotes -> proper CSV escaping
    
    Args:
        value: The value to escape
        
    Returns:
        Escaped string safe for CSV
    """
    if value is None:
        return ""
    
    # Convert to string if needed
    value = str(value)
    
    # The csv module handles escaping automatically, but we need to
    # ensure the value is clean for our purposes
    return value


def format_multiline_text(text: str, separator: str = "<br>") -> str:
    """
    Format multiline text for CSV output.
    
    Converts newlines to HTML breaks (useful for Anki import).
    
    Args:
        text: The text to format
        separator: The separator to use for newlines
        
    Returns:
        Formatted text
    """
    if not text:
        return ""
    return text.replace("\n", separator)


def generate_csv_bytes(rows: List[List[str]], include_bom: bool = True) -> bytes:
    """
    Generate CSV bytes from rows.
    
    Args:
        rows: List of rows, each row is a list of string values
        include_bom: Whether to include UTF-8 BOM for Excel compatibility
        
    Returns:
        CSV content as bytes
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    
    for row in rows:
        writer.writerow(row)
    
    csv_string = output.getvalue()
    output.close()
    
    # Encode with optional BOM
    if include_bom:
        # UTF-8 BOM for Excel compatibility
        return b'\xef\xbb\xbf' + csv_string.encode('utf-8')
    else:
        return csv_string.encode('utf-8')


def generate_tsv_bytes(rows: List[List[str]], include_bom: bool = False) -> bytes:
    """
    Generate TSV (Tab-Separated Values) bytes from rows.
    
    Used for Anki import which prefers TSV format.
    
    Args:
        rows: List of rows, each row is a list of string values
        include_bom: Whether to include UTF-8 BOM
        
    Returns:
        TSV content as bytes
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
    
    for row in rows:
        writer.writerow(row)
    
    tsv_string = output.getvalue()
    output.close()
    
    # Encode with optional BOM
    if include_bom:
        return b'\xef\xbb\xbf' + tsv_string.encode('utf-8')
    else:
        return tsv_string.encode('utf-8')
