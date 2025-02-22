import pytest
from unittest.mock import Mock, patch
from ticket_extractors import WebPageExtractor

@pytest.fixture
def mock_page():
    """Mock webpage content."""
    return """
    <html>
        <head>
            <title>Test Page</title>
            <meta name="description" content="Test description">
        </head>
        <body>
            <article>
                <h1>Test Article</h1>
                <p>Test content paragraph</p>
            </article>
        </body>
    </html>
    """

@pytest.fixture
def extractor():
    """Create a WebPageExtractor instance."""
    return WebPageExtractor()

@pytest.mark.asyncio
async def test_extract_webpage(extractor, mock_page):
    """Test extracting content from a webpage."""
    with patch('ticket_extractors.webpage_extractor.WebPageExtractor._fetch_page_content') as mock_fetch:
        mock_fetch.return_value = mock_page
        
        url = "https://example.com/test-page"
        page_data = await extractor.get_page_from_url(url)
        
        assert page_data is not None
        assert page_data['title'] == 'Test Page'
        assert 'Test content paragraph' in page_data['content']
        assert page_data['metadata']['url'] == url

@pytest.mark.asyncio
async def test_invalid_url(extractor):
    """Test handling of invalid URLs."""
    url = "not-a-valid-url"
    page_data = await extractor.get_page_from_url(url)
    assert page_data is None

@pytest.mark.asyncio
async def test_failed_fetch(extractor):
    """Test handling of failed page fetches."""
    with patch('ticket_extractors.webpage_extractor.WebPageExtractor._fetch_page_content') as mock_fetch:
        mock_fetch.side_effect = Exception("Failed to fetch")
        
        url = "https://example.com/test-page"
        page_data = await extractor.get_page_from_url(url)
        assert page_data is None

@pytest.mark.asyncio
async def test_empty_content(extractor):
    """Test handling of empty page content."""
    with patch('ticket_extractors.webpage_extractor.WebPageExtractor._fetch_page_content') as mock_fetch:
        mock_fetch.return_value = "<html></html>"
        
        url = "https://example.com/empty-page"
        page_data = await extractor.get_page_from_url(url)
        
        assert page_data is not None
        assert page_data['content'].strip() == "" 