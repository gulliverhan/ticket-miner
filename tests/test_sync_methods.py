import pytest
from unittest.mock import Mock, patch, AsyncMock
from ticket_extractors import JiraExtractor, ConfluenceExtractor, WebPageExtractor
from ticket_extractors.url_analyzer import URLMatch, ResourceMetadata

@pytest.fixture
def mock_jira():
    """Create a mock Jira client."""
    mock = Mock()
    
    # Mock ticket data
    mock_ticket = {
        'key': 'TEST-123',
        'fields': {
            'summary': 'Test Ticket',
            'description': 'Test Description',
            'status': {'name': 'Open'},
            'priority': {'name': 'High'},
            'assignee': {'displayName': 'John Smith'},
            'reporter': {'displayName': 'Jane Doe'},
            'created': '2024-03-20T10:00:00.000+0000',
            'updated': '2024-03-20T11:00:00.000+0000',
            'labels': ['test'],
            'issuelinks': []
        }
    }
    
    def mock_issue(key):
        if key == 'TEST-123':
            return mock_ticket
        raise Exception(f"Issue {key} not found")
    
    def mock_comments(key):
        return {'comments': []}
    
    mock.issue = mock_issue
    mock.issue_get_comments = mock_comments
    return mock

@pytest.fixture
def mock_url_analyzer():
    """Create a mock URLAnalyzer that returns empty matches."""
    mock = Mock()
    
    async def mock_analyze_content(content, *args, **kwargs):
        return []  # Return empty list of matches for simplicity
    
    mock.analyze_content = mock_analyze_content
    return mock

@pytest.fixture
def mock_confluence():
    """Create a mock Confluence client."""
    mock = Mock()
    
    # Mock page data
    mock_page = {
        'id': '12345',
        'title': 'Test Page',
        'body': {'storage': {'value': '<p>Test content</p>'}},
        'space': {'key': 'TEST'},
        'version': {
            'number': 1,
            'when': '2024-03-20T10:00:00.000Z',
            'by': {'displayName': 'Test Modifier'}
        },
        'history': {
            'createdBy': {'displayName': 'Test Creator'},
            'createdDate': '2024-03-20T09:00:00.000Z'
        },
        'metadata': {'labels': {'results': []}}
    }
    
    def mock_get_page_by_id(page_id, expand=None):
        if page_id == '12345':
            return mock_page
        raise Exception(f"Page {page_id} not found")
    
    mock.get_page_by_id = mock_get_page_by_id
    mock.get_attachments_from_content = lambda x: {'results': []}
    return mock

def test_jira_sync(mock_jira, mock_url_analyzer):
    """Test synchronous Jira ticket extraction."""
    with patch('ticket_extractors.jira_extractor.Jira') as mock_class:
        mock_class.return_value = mock_jira
        extractor = JiraExtractor()
        extractor.url_analyzer = mock_url_analyzer  # Use our mock URL analyzer
        
        # Test sync method
        result = extractor.get_ticket_sync("TEST-123")
        
        assert result is not None
        assert result['id'] == 'TEST-123'
        assert result['summary'] == 'Test Ticket'
        assert result['status'] == 'Open'
        assert result['priority'] == 'High'
        assert result['assignee'] == 'John Smith'
        assert result['reporter'] == 'Jane Doe'
        assert len(result['comments']) == 0
        assert 'references' in result

def test_confluence_sync(mock_confluence):
    """Test synchronous Confluence page extraction."""
    with patch('ticket_extractors.confluence_extractor.Confluence') as mock_class:
        mock_class.return_value = mock_confluence
        extractor = ConfluenceExtractor()
        
        # Test sync method
        url = "https://example.atlassian.net/wiki/spaces/TEST/pages/12345"
        result = extractor.get_page_from_url_sync(url)
        
        assert result is not None
        assert result['id'] == '12345'
        assert result['title'] == 'Test Page'
        assert result['space_key'] == 'TEST'
        assert result['content'] == 'Test content'
        assert result['creator'] == 'Test Creator'
        assert result['last_modifier'] == 'Test Modifier'
        assert len(result['attachments']) == 0

def test_webpage_sync():
    """Test synchronous webpage extraction."""
    mock_html = """
    <html>
        <head>
            <title>Example Page</title>
            <meta name="description" content="Test Description">
            <meta name="author" content="Test Author">
            <meta property="article:published_time" content="2024-03-20">
        </head>
        <body>
            <article>
                <h1>Example Article</h1>
                <p>Test content</p>
            </article>
        </body>
    </html>
    """
    
    with patch.object(WebPageExtractor, '_fetch_page_content', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_html
        extractor = WebPageExtractor()
        
        # Test sync method
        url = "https://example.com"
        result = extractor.get_page_from_url_sync(url)
        
        assert result is not None
        assert result['url'] == url
        assert result['title'] == 'Example Page'
        assert result['description'] == 'Test Description'
        assert result['author'] == 'Test Author'
        assert result['date'] == '2024-03-20'
        assert 'Test content' in result['content']

def test_sync_error_handling():
    """Test error handling in sync methods."""
    # Test Jira error handling
    with patch('ticket_extractors.jira_extractor.Jira') as mock_jira:
        mock_jira.return_value.issue.side_effect = Exception("Jira API error")
        extractor = JiraExtractor(jira=mock_jira.return_value)
        
        with pytest.raises(Exception):
            extractor.get_ticket_sync("TEST-123")
    
    # Test Confluence error handling
    with patch('ticket_extractors.confluence_extractor.Confluence') as mock_confluence:
        mock_confluence.return_value.get_page_by_id.side_effect = Exception("Confluence API error")
        extractor = ConfluenceExtractor()
        
        result = extractor.get_page_from_url_sync("https://example.atlassian.net/wiki/spaces/TEST/pages/12345")
        assert result is None
    
    # Test WebPage error handling
    with patch.object(WebPageExtractor, '_fetch_page_content', new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("Failed to fetch page")
        extractor = WebPageExtractor()
        
        result = extractor.get_page_from_url_sync("https://example.com")
        assert result is None 