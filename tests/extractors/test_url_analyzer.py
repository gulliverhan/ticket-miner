import pytest
from ticket_extractors import URLAnalyzer
from ticket_extractors.config import JIRA_URL, CONFLUENCE_URL, BASE_DOMAIN
from ticket_extractors.rate_limiter import RateLimitConfig
from ticket_extractors.memory_manager import MemoryConfig

@pytest.fixture
def analyzer():
    """Create a URLAnalyzer instance with rate limiting and memory management."""
    rate_config = RateLimitConfig(
        calls_per_second=2.0,
        max_retries=3,
        initial_retry_delay=1.0,
        max_retry_delay=60.0
    )
    
    memory_config = MemoryConfig(
        max_memory_percent=80.0,
        cleanup_threshold=70.0,
        chunk_size=50
    )
    
    return URLAnalyzer()

@pytest.fixture
def mock_rate_limiter(mocker):
    """Mock rate limiter to avoid actual delays in tests."""
    async def async_call(func, *args, **kwargs):
        result = await func(*args, **kwargs)
        return result
    
    mock = mocker.patch('ticket_extractors.rate_limiter.APIRateLimiter.call')
    mock.side_effect = async_call
    return mock

@pytest.fixture
def mock_memory_manager(mocker):
    """Mock memory manager to avoid actual memory checks in tests."""
    mock = mocker.patch('ticket_extractors.memory_manager.MemoryManager.check_memory')
    return mock

@pytest.mark.asyncio
async def test_analyze_jira_urls(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test analysis of Jira URLs with rate limiting."""
    content = f"""
    Here are some Jira tickets:
    - {JIRA_URL}/browse/PROJ-123
    - {JIRA_URL}/browse/TEST-456
    - https://jira.{BASE_DOMAIN}/browse/PROJ-789
    """
    
    result = await analyzer.analyze_content(content, "TEST-789")
    
    assert len(result) == 3
    for match in result:
        assert match.url_type == "jira"
        assert match.resource_metadata.resource_type == "jira_ticket"
        assert match.should_scrape == True

@pytest.mark.asyncio
async def test_analyze_confluence_urls(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test analysis of Confluence URLs with rate limiting."""
    content = f"""
    Check these Confluence pages:
    - {CONFLUENCE_URL}/wiki/spaces/TEST/pages/12345
    - {CONFLUENCE_URL}/display/TEST/Page+Title
    - https://confluence.{BASE_DOMAIN}/display/TEST/Another+Page
    """
    
    result = await analyzer.analyze_content(content, "TEST-789")
    
    assert len(result) == 3
    for match in result:
        assert match.url_type == "confluence"
        assert match.resource_metadata.resource_type == "confluence_page"
        assert match.should_scrape == True

@pytest.mark.asyncio
async def test_analyze_help_center_urls(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test analysis of help center URLs with rate limiting."""
    content = """
    See documentation:
    - https://help.example.com/article/123
    - https://developers.example.com/docs/example
    """
    
    result = await analyzer.analyze_content(content, "TEST-789")
    
    assert len(result) == 2
    assert any(match.url_type == "help_center" for match in result)
    assert any(match.url_type == "documentation" for match in result)

@pytest.mark.asyncio
async def test_analyze_mixed_content(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test analysis of content with mixed URL types with rate limiting."""
    content = f"""
    Please check:
    1. Ticket: {JIRA_URL}/browse/PROJ-123
    2. Doc: https://help.example.com/article/123
    3. Random: https://other.example.com/page
    4. Confluence: {CONFLUENCE_URL}/wiki/spaces/TEST/pages/12345
    """
    
    result = await analyzer.analyze_content(content, "TEST-789")
    
    url_types = [match.url_type for match in result]
    assert len(result) == 4
    assert "jira" in url_types
    assert "confluence" in url_types
    assert "help_center" in url_types
    assert "external" in url_types

@pytest.mark.asyncio
async def test_invalid_urls(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test handling of invalid URLs with rate limiting."""
    content = """
    Invalid URLs:
    - not-a-url
    - http://
    - https://
    """
    
    matches = await analyzer.analyze_content(content, "TEST-789")
    assert len(matches) == 0

@pytest.mark.asyncio
async def test_url_context(analyzer, mock_rate_limiter, mock_memory_manager):
    """Test URL context extraction with rate limiting."""
    content = f"""
    Important ticket: {JIRA_URL}/browse/PROJ-123
    """
    
    matches = await analyzer.analyze_content(content, "TEST-789")
    assert len(matches) == 1
    assert matches[0].url_type == "jira"
    assert matches[0].resource_metadata.resource_type == "jira_ticket"

@pytest.mark.asyncio
async def test_rate_limit_exceeded(analyzer, mocker):
    """Test handling of rate limit exceeded errors."""
    from aiohttp import ClientResponseError
    from yarl import URL
    
    # Mock rate limiter to simulate rate limit exceeded
    mock_call = mocker.patch('ticket_extractors.rate_limiter.APIRateLimiter.call')
    mock_call.side_effect = ClientResponseError(
        request_info=mocker.Mock(real_url=URL('http://example.com')),
        history=(),
        status=429,
        headers={'Retry-After': '1'}
    )
    
    content = f"{JIRA_URL}/browse/PROJ-123"
    
    with pytest.raises(ClientResponseError) as exc_info:
        await analyzer.analyze_content(content, "TEST-789")
    assert exc_info.value.status == 429

@pytest.mark.asyncio
async def test_memory_limit_exceeded(analyzer, mocker):
    """Test handling of memory limit exceeded errors."""
    # Mock memory manager to simulate memory limit exceeded
    mock_check = mocker.patch('ticket_extractors.memory_manager.MemoryManager.check_memory')
    mock_check.side_effect = MemoryError("Memory usage exceeds maximum limit")
    
    content = f"{JIRA_URL}/browse/PROJ-123"
    
    with pytest.raises(MemoryError):
        await analyzer.analyze_content(content, "TEST-789")