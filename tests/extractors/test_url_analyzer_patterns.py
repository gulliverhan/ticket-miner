import pytest
from ticket_extractors import URLAnalyzer
from ticket_extractors.config import BASE_DOMAIN
from ticket_extractors.rate_limiter import RateLimitConfig
from ticket_extractors.memory_manager import MemoryConfig
import json
from pathlib import Path

@pytest.fixture
def test_patterns():
    """Create test URL patterns."""
    return {
        "url_patterns": {
            "help_center": {
                "domains": [f"help.{BASE_DOMAIN}"],
                "scrape": True,
                "exclude_patterns": [
                    "^/search(/.*)?$",
                    "^/user(/.*)?$"
                ]
            },
            "platform": {
                "domains": [f"app.{BASE_DOMAIN}"],
                "scrape": False,
                "resource_patterns": [
                    {
                        "pattern": "/campaign/([0-9]+)",
                        "type": "campaign",
                        "extract_id": "$1"
                    },
                    {
                        "pattern": "/campaign/([0-9]+)/ideas/([0-9]+)",
                        "type": "campaign_idea",
                        "extract_id": "$2",
                        "parent_id": "$1"
                    }
                ]
            }
        }
    }

@pytest.fixture
def test_patterns_file(tmp_path, test_patterns):
    """Create a temporary test patterns file."""
    patterns_file = tmp_path / "test_patterns.json"
    with open(patterns_file, "w") as f:
        json.dump(test_patterns, f)
    return patterns_file

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
async def test_load_custom_patterns(test_patterns_file, mock_rate_limiter, mock_memory_manager):
    """Test loading custom URL patterns with rate limiting."""
    analyzer = URLAnalyzer(test_patterns_file)
    assert f"help.{BASE_DOMAIN}" in analyzer.domain_to_platform
    assert f"app.{BASE_DOMAIN}" in analyzer.domain_to_platform

@pytest.mark.asyncio
async def test_scraping_configuration(test_patterns_file, mock_rate_limiter, mock_memory_manager):
    """Test URL scraping configuration with rate limiting."""
    analyzer = URLAnalyzer(test_patterns_file)
    
    # Test help center URL that should be scraped
    matches = await analyzer.analyze_content(
        f"Check this article: https://help.{BASE_DOMAIN}/article/123",
        "TEST-1"
    )
    assert len(matches) == 1
    assert matches[0].should_scrape == True
    
    # Test help center search URL that should not be scraped
    matches = await analyzer.analyze_content(
        f"Search results: https://help.{BASE_DOMAIN}/search?q=test",
        "TEST-1"
    )
    assert len(matches) == 1
    assert matches[0].should_scrape == False
    
    # Test platform URL that should not be scraped
    matches = await analyzer.analyze_content(
        f"Campaign link: https://app.{BASE_DOMAIN}/campaign/123",
        "TEST-1"
    )
    assert len(matches) == 1
    assert matches[0].should_scrape == False

@pytest.mark.asyncio
async def test_resource_pattern_matching(test_patterns_file, mock_rate_limiter, mock_memory_manager):
    """Test matching and extracting resource information with rate limiting."""
    analyzer = URLAnalyzer(test_patterns_file)
    
    # Test simple campaign URL
    matches = await analyzer.analyze_content(
        f"Campaign: https://app.{BASE_DOMAIN}/campaign/123",
        "TEST-1"
    )
    assert len(matches) == 1
    assert matches[0].resource_metadata is not None
    assert matches[0].resource_metadata.resource_type == "campaign"
    assert matches[0].resource_metadata.resource_id == "123"
    assert matches[0].resource_metadata.parent_id is None
    
    # Test nested campaign idea URL
    matches = await analyzer.analyze_content(
        f"Idea: https://app.{BASE_DOMAIN}/campaign/123/ideas/456",
        "TEST-1"
    )
    assert len(matches) == 1
    assert matches[0].resource_metadata is not None
    assert matches[0].resource_metadata.resource_type == "campaign_idea"
    assert matches[0].resource_metadata.resource_id == "456"
    assert matches[0].resource_metadata.parent_id == "123"

@pytest.mark.asyncio
async def test_mixed_urls(test_patterns_file, mock_rate_limiter, mock_memory_manager):
    """Test handling a mix of different URL types with rate limiting."""
    analyzer = URLAnalyzer(test_patterns_file)
    
    content = f"""
    Please check:
    1. Help article: https://help.{BASE_DOMAIN}/article/123
    2. Campaign: https://app.{BASE_DOMAIN}/campaign/456
    3. Search: https://help.{BASE_DOMAIN}/search?q=test
    4. Idea: https://app.{BASE_DOMAIN}/campaign/456/ideas/789
    5. Random: https://other.{BASE_DOMAIN}/page
    """
    
    matches = await analyzer.analyze_content(content, "TEST-1")
    
    assert len(matches) == 5
    
    # Help article (should be scraped)
    assert matches[0].should_scrape == True
    assert matches[0].url_type == "help_center"
    
    # Campaign
    assert matches[1].should_scrape == False
    assert matches[1].resource_metadata.resource_type == "campaign"
    assert matches[1].resource_metadata.resource_id == "456"
    
    # Search (should not be scraped)
    assert matches[2].should_scrape == False
    
    # Campaign idea
    assert matches[3].should_scrape == False
    assert matches[3].resource_metadata.resource_type == "campaign_idea"
    assert matches[3].resource_metadata.resource_id == "789"
    assert matches[3].resource_metadata.parent_id == "456"
    
    # Random external URL
    assert matches[4].url_type == "external"
    assert matches[4].should_scrape == False

@pytest.mark.asyncio
async def test_rate_limit_exceeded(test_patterns_file, mocker):
    """Test handling of rate limit exceeded errors."""
    from aiohttp import ClientResponseError
    from yarl import URL
    
    analyzer = URLAnalyzer(test_patterns_file)
    
    # Mock rate limiter to simulate rate limit exceeded
    mock_call = mocker.patch('ticket_extractors.rate_limiter.APIRateLimiter.call')
    mock_call.side_effect = ClientResponseError(
        request_info=mocker.Mock(real_url=URL('http://example.com')),
        history=(),
        status=429,
        headers={'Retry-After': '1'}
    )
    
    content = f"https://app.{BASE_DOMAIN}/campaign/123"
    
    with pytest.raises(ClientResponseError) as exc_info:
        await analyzer.analyze_content(content, "TEST-1")
    assert exc_info.value.status == 429

@pytest.mark.asyncio
async def test_memory_limit_exceeded(test_patterns_file, mocker):
    """Test handling of memory limit exceeded errors."""
    analyzer = URLAnalyzer(test_patterns_file)
    
    # Mock memory manager to simulate memory limit exceeded
    mock_check = mocker.patch('ticket_extractors.memory_manager.MemoryManager.check_memory')
    mock_check.side_effect = MemoryError("Memory usage exceeds maximum limit")
    
    content = f"https://app.{BASE_DOMAIN}/campaign/123"
    
    with pytest.raises(MemoryError):
        await analyzer.analyze_content(content, "TEST-1") 