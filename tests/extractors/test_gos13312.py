import pytest
from unittest.mock import Mock, patch
from ticket_extractors.jira_extractor import JiraExtractor
from ticket_extractors.url_analyzer import URLMatch, ResourceMetadata
import json
import os

@pytest.fixture
def mock_jira():
    with open('tests/extractors/mock_data/ticket_PROJ-1234_20250214_122143.json', 'r') as f:
        mock_data = json.load(f)
    
    mock_client = Mock()
    mock_client.issue.return_value = mock_data['ticket']
    mock_client.issue_get_comments.return_value = mock_data['comments']
    return mock_client

@pytest.fixture
def mock_url_analyzer():
    """Create a mock URLAnalyzer that returns predefined matches."""
    mock = Mock()
    
    async def mock_analyze_content(content, *args, **kwargs):
        matches = []
        if "confluence.example.com/display/TEST/Page1" in content:
            matches.append(URLMatch(
                url="https://confluence.example.com/display/TEST/Page1",
                url_type='confluence',
                should_scrape=True,
                context='Found in content',
                resource_metadata=ResourceMetadata(
                    resource_type='confluence_page',
                    resource_id='Page1'
                )
            ))
        return matches
    
    mock.analyze_content = mock_analyze_content
    return mock

@pytest.fixture
def mock_confluence():
    mock_client = Mock()
    mock_client.get_page_by_id.return_value = {
        'id': 'Page1',
        'title': 'Example Documentation Page',
        'body': {'storage': {'value': 'Test content'}},
        'space': {'key': 'TEST'},
        'version': {'number': 1},
        'history': {
            'createdDate': '2025-02-14T12:00:00.000+0000',
            'createdBy': {'displayName': 'Alice Smith'},
            'lastUpdated': {'when': '2025-02-14T13:00:00.000+0000'},
            'by': {'displayName': 'Bob Jones'}
        },
        'metadata': {
            'labels': {
                'results': [
                    {'name': 'test'},
                    {'name': 'documentation'}
                ]
            }
        }
    }
    return mock_client

@pytest.mark.asyncio
async def test_gos13312_confluence_link(mock_jira, mock_confluence, mock_url_analyzer):
    # Load mock data to get the ticket ID
    with open('tests/extractors/mock_data/ticket_PROJ-1234_20250214_122143.json', 'r') as f:
        mock_data = json.load(f)
    ticket_id = mock_data['ticket']['key']
    
    extractor = JiraExtractor(jira=mock_jira, max_reference_depth=2)
    extractor.url_analyzer = mock_url_analyzer  # Use our mock URL analyzer
    ticket_data = await extractor.get_ticket(ticket_id)
    
    assert ticket_data is not None
    assert 'references' in ticket_data
    
    # Find Confluence reference in the references section
    confluence_refs = ticket_data['references']['confluence_pages']
    assert len(confluence_refs) > 0
    
    confluence_ref = confluence_refs[0]
    assert confluence_ref['id'] == 'Page1'
    assert confluence_ref['url'].startswith('https://confluence.example.com/')
    assert confluence_ref['context'] == 'Found in content'
    assert confluence_ref['metadata'].resource_type == 'confluence_page'
    assert confluence_ref['metadata'].resource_id == 'Page1' 