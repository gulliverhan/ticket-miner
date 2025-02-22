import pytest
from unittest.mock import Mock, patch
from ticket_extractors import ConfluenceExtractor

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
            'when': '2024-02-18T10:00:00.000Z',
            'by': {'displayName': 'Test Modifier'}
        },
        'history': {
            'createdBy': {'displayName': 'Test Creator'},
            'createdDate': '2024-02-18T09:00:00.000Z'
        },
        'metadata': {'labels': {'results': []}}
    }
    
    # Mock attachments response
    mock_attachments = {
        'results': [
            {
                'id': 'att1',
                'title': 'test.txt',
                'metadata': {'mediaType': 'text/plain'},
                'extensions': {'fileSize': 1024},
                'version': {
                    'when': '2024-02-18T10:00:00.000Z',
                    'by': {'displayName': 'Test Creator'}
                },
                '_links': {'download': '/download/attachments/12345/test.txt'}
            }
        ]
    }
    
    def mock_get_page_by_id(page_id, expand=None):
        if page_id == '12345':
            return mock_page
        raise Exception(f"Page {page_id} not found")
    
    def mock_get_attachments_from_content(page_id):
        if page_id == '12345':
            return mock_attachments
        return {'results': []}
    
    mock.get_page_by_id = mock_get_page_by_id
    mock.get_attachments_from_content = mock_get_attachments_from_content
    return mock

@pytest.fixture
def extractor(mock_confluence):
    """Create a ConfluenceExtractor with mock client."""
    with patch('ticket_extractors.confluence_extractor.Confluence') as mock_class:
        mock_class.return_value = mock_confluence
        return ConfluenceExtractor()

@pytest.mark.asyncio
async def test_get_page_from_url(extractor):
    """Test extracting a page from URL."""
    url = "https://example.atlassian.net/wiki/spaces/TEST/pages/12345"
    page_data = await extractor.get_page_from_url(url)
    
    assert page_data['id'] == '12345'
    assert page_data['title'] == 'Test Page'
    assert page_data['space_key'] == 'TEST'
    assert page_data['content'] == 'Test content'
    assert page_data['creator'] == 'Test Creator'
    assert page_data['last_modifier'] == 'Test Modifier'
    assert len(page_data['attachments']) == 1
    assert page_data['attachments'][0]['filename'] == 'test.txt'

@pytest.mark.asyncio
async def test_invalid_url(extractor):
    """Test handling of invalid URLs."""
    url = "https://example.com/not-confluence"
    page_data = await extractor.get_page_from_url(url)
    assert page_data is None

@pytest.mark.asyncio
async def test_page_not_found(extractor):
    """Test handling of non-existent pages."""
    url = "https://example.atlassian.net/wiki/spaces/TEST/pages/99999"
    page_data = await extractor.get_page_from_url(url)
    assert page_data is None 