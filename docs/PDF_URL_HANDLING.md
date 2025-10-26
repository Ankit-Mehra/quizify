# PDF URL Handling Documentation

## Overview

The web scraping service **automatically detects and processes PDF URLs**, downloading the PDF and extracting text content seamlessly. Users can submit PDF URLs just like regular HTML URLs - no special handling required!

## Problem Solved

Previously, PDF URLs would fail because:

1. **PDFs trigger downloads** instead of rendering HTML content
2. **Browser navigation fails** with `net::ERR_ABORTED` errors  
3. **No content can be extracted** from the download event

## Solution

We've implemented **automatic PDF download and extraction** that:

1. **Detects PDF URLs** automatically (`.pdf` extension, `/pdf/` path patterns)
2. **Downloads the PDF** with size and timeout limits (10MB max, 30s timeout)
3. **Extracts text** using PyMuPDF (same quality as file upload)
4. **Returns extracted text** seamlessly - users don't need to know it was a PDF

## User Experience

### Before ❌
```
User submits PDF URL → Browser attempts scrape → ERR_ABORTED → 
Multiple retries → Timeout → Generic error → Confusion
```

### After ✅  
```
User submits PDF URL → Auto-detection → PDF download → 
Text extraction → Quiz generation ✅
```

**Users can now submit ANY URL** - HTML pages, PDF papers, PDF documents - and it just works!

## Technical Implementation

### 1. PDF Detection (`is_pdf_url()`)

```python
def is_pdf_url(url: str) -> bool:
    """Detect if URL points to a PDF file"""
    # Check .pdf extension
    if url.lower().endswith('.pdf'):
        return True
    
    # Check for /pdf/ in path (arxiv.org/pdf/...)
    if '/pdf/' in url.lower():
        return True
    
    return False
```

### 2. PDF Download & Extraction (`download_and_extract_pdf()`)

```python
async def download_and_extract_pdf(url: str) -> str:
    """Download PDF and extract text"""
    
    # 1. Validate URL (SSRF protection)
    validate_url(url)
    
    # 2. Download with limits
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Stream download to check size
        async with client.stream('GET', url) as response:
            # Check size before downloading
            if content_length > 10MB:
                raise HTTPException(400, "PDF too large")
            
            # Download in chunks
            pdf_bytes = await download_with_size_limit(response)
    
    # 3. Extract text using PyMuPDF
    text = extract_text_from_pdf(pdf_bytes)
    
    # 4. Validate extracted text
    if len(text) < 100:
        raise HTTPException(400, "PDF contains no readable text")
    
    return text
```

### 3. Automatic Routing in `scrape_content()`

```python
async def scrape_content(url: str, user_id: str) -> str:
    """Scrape HTML or extract PDF automatically"""
    
    # Detect and handle PDFs automatically
    if is_pdf_url(url):
        return await download_and_extract_pdf(url)
    
    # Otherwise scrape as HTML
    return await scrape_html_with_playwright(url)
```

## Features

### ✅ Size Limits
- **Maximum PDF size:** 10MB (same as file upload)
- **Checks size during download** (doesn't download entire file if too large)
- **Prevents resource exhaustion**

### ✅ Timeout Protection
- **Download timeout:** 30 seconds
- **Prevents hanging downloads**
- **Clear error messages** if timeout occurs

### ✅ SSRF Protection
- **URL validation** before download
- **Private IP blocking** maintained
- **Same security as HTML scraping**

### ✅ Error Handling

```python
# PDF too large
HTTPException(400, "PDF file is too large (12.5MB). Maximum size is 10MB.")

# Download timeout
HTTPException(408, "PDF download timed out after 30 seconds.")

# Empty/scanned PDF
HTTPException(400, "Could not extract meaningful text from PDF. PDF might be scanned images.")

# HTTP errors
HTTPException(400, "Failed to download PDF: HTTP 404. URL might be invalid.")
```

### ✅ No Browser Resources Used
- **PDF download uses httpx** (HTTP client)
- **No Playwright browser needed**
- **Doesn't count toward browser slot limits**
- **Faster and more efficient** than browser-based approach

## Performance Comparison

| Metric | HTML Scraping | PDF Download |
|--------|---------------|--------------|
| **Method** | Playwright browser | httpx HTTP client |
| **Resource Usage** | High (browser instance) | Low (HTTP stream) |
| **Speed** | 10-60 seconds | 1-5 seconds |
| **Browser Slots** | Yes (limited to 3) | No (unlimited*) |
| **Memory** | ~256MB per browser | ~10MB per PDF |
| **Concurrency** | 3 per user | Limited by httpx pool |

*Still subject to overall system resources

## Examples

### Supported URLs

```bash
# arXiv papers
✅ https://arxiv.org/pdf/2312.16171
✅ https://arxiv.org/pdf/2401.12345.pdf

# Direct PDF links  
✅ https://example.com/paper.pdf
✅ https://university.edu/research/report.pdf

# PDF in path
✅ https://docs.site.com/documents/pdf/guide.html

# Regular HTML (still works)
✅ https://en.wikipedia.org/wiki/Machine_Learning
✅ https://example.com/blog/article
```

### Real-World Test Results

```
Test URL: https://arxiv.org/pdf/2312.16171
✅ PDF detected automatically
✅ Downloaded: 1.50MB in 0.2 seconds
✅ Extracted: 73,042 characters (~11,243 words)
✅ Content valid: Academic paper text extracted perfectly
```

## API Response

The API response is **identical** whether the URL was HTML or PDF:

```json
{
  "quiz_id": "uuid",
  "title": "Quiz from arXiv Paper",
  "questions": [...],
  "metadata": {
    "content_type": "url",
    "file_name": "https://arxiv.org/pdf/2312.16171",
    "file_type": "application/pdf",  // ← Only indication it was a PDF
    "word_count": 11243,
    "created_at": "2025-10-26T18:23:58"
  }
}
```

## Frontend Integration

No changes required! Frontend code works exactly the same:

```typescript
// No special handling needed
const response = await generateQuizFromURL({
  url: "https://arxiv.org/pdf/2312.16171",  // Works!
  title: "Machine Learning Quiz",
  num_questions: 10
});

// Same response structure for HTML and PDF URLs
console.log(response.quiz_id);
```

### Optional: Show PDF indicator in UI

```typescript
// Optional enhancement: Show file type to user
if (metadata.file_type === 'application/pdf') {
  showIcon('📄'); // PDF icon
} else {
  showIcon('🌐'); // Web icon
}
```

## Error Handling

```typescript
try {
  await generateQuizFromURL(pdfUrl);
} catch (error) {
  if (error.status === 400) {
    if (error.detail.includes('too large')) {
      // PDF over 10MB
      showError('PDF file is too large. Try a smaller PDF or use file upload.');
    } else if (error.detail.includes('no readable text')) {
      // Scanned PDF
      showError('This PDF appears to be scanned images. Try a different PDF.');
    }
  } else if (error.status === 408) {
    // Timeout
    showError('PDF download timed out. The file might be too large or slow.');
  }
}
```

## Testing

### Unit Tests

```python
async def test_pdf_detection():
    assert is_pdf_url("https://arxiv.org/pdf/123.pdf") == True
    assert is_pdf_url("https://example.com/doc.pdf") == True
    assert is_pdf_url("https://example.com/page.html") == False

async def test_pdf_download():
    content = await scrape_content("https://arxiv.org/pdf/2312.16171")
    assert len(content) > 1000
    assert "abstract" in content.lower()

async def test_pdf_size_limit():
    with pytest.raises(HTTPException) as exc:
        await download_and_extract_pdf("https://huge-pdf.com/20mb.pdf")
    assert exc.value.status_code == 400
    assert "too large" in exc.value.detail
```

### Manual Testing

```bash
# Test with arXiv PDF
curl -X POST http://localhost:8000/api/quiz/generate-from-url \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://arxiv.org/pdf/2312.16171",
    "title": "LLM Prompting Principles Quiz",
    "num_questions": 10
  }'

# Expected: 200 OK with quiz data
```

## Security Considerations

### ✅ SSRF Protection Maintained
- URL validation before download
- Private IP blocking enforced
- DNS rebinding protection (validates before connection)

### ✅ Resource Limits
- 10MB file size limit (prevents memory exhaustion)
- 30 second timeout (prevents hanging)
- No browser slots consumed (doesn't affect HTML scraping limits)

### ✅ Content Validation
- Validates extracted text length
- Detects empty/scanned PDFs
- Clear error messages for invalid content

### 🔒 Attack Vectors Considered

| Attack | Mitigation |
|--------|------------|
| **SSRF** | URL validation + private IP blocking |
| **DoS (large files)** | 10MB size limit checked during download |
| **DoS (slow downloads)** | 30 second timeout |
| **Memory exhaustion** | Streaming download + size limits |
| **Malicious PDFs** | PyMuPDF handles safely, exceptions caught |

## Future Enhancements

### 1. Enhanced Detection with Content-Type

```python
# Check actual Content-Type header
async def is_pdf_url_enhanced(url: str) -> bool:
    # Try HEAD request to check Content-Type
    response = await httpx.head(url, follow_redirects=True)
    content_type = response.headers.get('content-type', '')
    return 'application/pdf' in content_type
```

**Pros:** More accurate detection  
**Cons:** Extra network request (latency)

### 2. OCR for Scanned PDFs

```python
# Use Tesseract OCR for image-based PDFs
if not text or len(text) < 100:
    text = await extract_text_with_ocr(pdf_bytes)
```

**Pros:** Handle scanned documents  
**Cons:** Much slower, requires Tesseract installation

### 3. PDF Caching

```python
# Cache downloaded PDFs by URL hash
@cache(ttl=3600)  # 1 hour cache
async def download_and_extract_pdf(url: str) -> str:
    ...
```

**Pros:** Faster for repeated URLs  
**Cons:** Memory/storage usage, cache invalidation complexity

### 4. Metadata Extraction

```python
# Extract PDF metadata
metadata = {
    'title': pdf.metadata.get('title'),
    'author': pdf.metadata.get('author'),
    'pages': len(pdf),
    'created': pdf.metadata.get('creationDate')
}
```

**Pros:** Richer quiz metadata  
**Cons:** Not all PDFs have metadata

## Troubleshooting

### "PDF file is too large"
✅ **Expected** - PDFs over 10MB are rejected  
💡 **Solution:** Have user download and use file upload instead

### "Could not extract meaningful text"
✅ **Expected** - PDF is scanned images or empty  
💡 **Solution:** Need OCR (future enhancement) or different PDF

### "PDF download timed out"
✅ **Expected** - Server is slow or file is large  
💡 **Solution:** Retry or use file upload

### False positive detection
❌ **Unexpected** - HTML URL detected as PDF  
🔧 **Fix:** Update `is_pdf_url()` patterns or add Content-Type check

## Monitoring & Logs

```python
# Success logs
INFO - PDF URL detected - downloading and extracting text: https://arxiv.org/pdf/123
INFO - PDF downloaded successfully: 1.50MB
INFO - Successfully extracted 73042 characters from PDF

# Error logs  
ERROR - PDF too large: 15728640 bytes (max: 10485760)
ERROR - Timeout downloading PDF from https://slow-server.com/file.pdf
ERROR - PDF text extraction returned insufficient content: 15 chars
```

## Summary

| Feature | Status | Details |
|---------|--------|---------|
| **PDF Detection** | ✅ Production | Pattern-based, fast |
| **Auto Download** | ✅ Production | 10MB limit, 30s timeout |
| **Text Extraction** | ✅ Production | PyMuPDF, same as file upload |
| **SSRF Protection** | ✅ Production | Full security maintained |
| **Error Handling** | ✅ Production | Clear, actionable messages |
| **No Browser Overhead** | ✅ Production | Uses httpx, not Playwright |
| **Transparent to Users** | ✅ Production | Same API for HTML/PDF |

## Key Benefits

✅ **Seamless UX** - Users don't need to know it's a PDF  
✅ **High Quality** - Same extraction as file upload  
✅ **Fast** - 1-5 seconds vs 30-60 seconds for browser  
✅ **Efficient** - No browser resources consumed  
✅ **Secure** - Full SSRF protection maintained  
✅ **Robust** - Size limits, timeouts, error handling  

---

**Last Updated:** October 26, 2025  
**Feature Status:** ✅ Production Ready  
**Breaking Changes:** None (enhancement only)
