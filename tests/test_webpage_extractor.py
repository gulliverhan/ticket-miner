import pytest
from unittest.mock import patch, AsyncMock
from ticket_extractors.webpage_extractor import WebPageExtractor

@pytest.fixture
def extractor():
    return WebPageExtractor()

@pytest.fixture
def mock_html_content():
    return """
    <html>
        <head>
            <title>Example Page</title>
            <meta name="description" content="This is an example page">
            <meta name="author" content="Test Author">
            <meta property="article:published_time" content="2024-03-20">
        </head>
        <body>
            <article>
                <h1>Example Article</h1>
                <p>This is the main content of the article.</p>
            </article>
        </body>
    </html>
    """

@pytest.mark.asyncio
async def test_get_page_from_url_async(extractor, mock_html_content):
    with patch.object(extractor, '_fetch_page_content', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_html_content
        url = "https://example.com"
        result = await extractor.get_page_from_url(url)
        
        assert result is not None
        assert isinstance(result, dict)
        assert result["url"] == url
        assert result["title"] == "Example Page"
        assert result["description"] == "This is an example page"
        assert result["author"] == "Test Author"
        assert result["date"] == "2024-03-20"
        assert "content" in result
        assert "This is the main content of the article" in result["content"]

def test_get_page_from_url_sync(extractor, mock_html_content):
    with patch.object(extractor, '_fetch_page_content', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_html_content
        url = "https://example.com"
        result = extractor.get_page_from_url_sync(url)
        
        assert result is not None
        assert isinstance(result, dict)
        assert result["url"] == url
        assert result["title"] == "Example Page"
        assert result["description"] == "This is an example page"
        assert result["author"] == "Test Author"
        assert result["date"] == "2024-03-20"
        assert "content" in result
        assert "This is the main content of the article" in result["content"]

@pytest.mark.asyncio
async def test_invalid_url_async(extractor):
    url = "invalid_url"
    result = await extractor.get_page_from_url(url)
    assert result is None

def test_invalid_url_sync(extractor):
    url = "invalid_url"
    result = extractor.get_page_from_url_sync(url)
    assert result is None

@pytest.mark.asyncio
async def test_nonexistent_page_async(extractor):
    with patch.object(extractor, '_fetch_page_content', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = None
        url = "https://nonexistent.example.com"
        result = await extractor.get_page_from_url(url)
        assert result is None

def test_nonexistent_page_sync(extractor):
    with patch.object(extractor, '_fetch_page_content_sync') as mock_fetch:
        mock_fetch.return_value = None
        url = "https://nonexistent.example.com"
        result = extractor.get_page_from_url_sync(url)
        assert result is None 