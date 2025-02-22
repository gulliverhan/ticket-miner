import pytest
from unittest.mock import Mock, patch
from ticket_extractors import JiraExtractor
from ticket_extractors.url_analyzer import URLMatch
from ticket_extractors import config
import json
from datetime import datetime, timezone
import os
from dataclasses import dataclass

# Load mock data from file
MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), 'mock_data/ticket_PROJ-1234_20250214_122143.json')
with open(MOCK_DATA_PATH) as f:
    MOCK_DATA = json.load(f)

MOCK_MAIN_TICKET = MOCK_DATA['ticket']
MOCK_COMMENTS = MOCK_DATA['comments']['comments']
MOCK_REFERENCED_TICKETS = MOCK_DATA['referenced_tickets']

@dataclass
class MockResourceMetadata:
    platform: str
    resource_type: str
    resource_id: str
    type: str = None  # For backward compatibility
    
    def __post_init__(self):
        self.type = self.resource_type
    
    def __getitem__(self, key):
        return getattr(self, key)

@pytest.fixture
def mock_url_analyzer():
    """Create a mock URLAnalyzer that returns predefined matches."""
    mock = Mock()
    
    async def mock_analyze_content(content):
        matches = []
        # Look for Jira ticket references
        if "PROJ-5678" in content:
            matches.append(URLMatch(
                url=f"{config.JIRA_URL}/browse/PROJ-5678",
                url_type='jira',
                should_scrape=True,
                context='Found in content',
                resource_metadata=MockResourceMetadata(
                    platform='knowledge_base',
                    resource_type='jira_ticket',
                    resource_id='PROJ-5678'
                )
            ))
        if "PROJ-9012" in content:
            matches.append(URLMatch(
                url=f"{config.JIRA_URL}/browse/PROJ-9012",
                url_type='jira',
                should_scrape=True,
                context='Found in content',
                resource_metadata=MockResourceMetadata(
                    platform='knowledge_base',
                    resource_type='jira_ticket',
                    resource_id='PROJ-9012'
                )
            ))
        if "confluence.example.com" in content:
            matches.append(URLMatch(
                url="https://confluence.example.com/display/TEST/Page1",
                url_type='confluence',
                should_scrape=True,
                context='Found in content',
                resource_metadata=MockResourceMetadata(
                    platform='knowledge_base',
                    resource_type='confluence_page',
                    resource_id='TEST/Page1'
                )
            ))
        return matches
    
    mock.analyze_content = mock_analyze_content
    return mock

@pytest.fixture
def mock_jira():
    """Create a mock Jira client that returns our test data."""
    mock = Mock()
    
    def mock_issue(key):
        if key == MOCK_MAIN_TICKET['key']:
            return MOCK_MAIN_TICKET
        elif key in MOCK_REFERENCED_TICKETS:
            return MOCK_REFERENCED_TICKETS[key]['ticket']
        raise Exception(f"Issue {key} not found")
    
    def mock_comments(key):
        if key == MOCK_MAIN_TICKET['key']:
            return {'comments': MOCK_COMMENTS}
        elif key in MOCK_REFERENCED_TICKETS:
            return {'comments': MOCK_REFERENCED_TICKETS[key].get('comments', [])}
        return {'comments': []}
    
    mock.issue = mock_issue
    mock.issue_get_comments = mock_comments
    return mock

@pytest.fixture
def extractor(mock_jira, mock_url_analyzer):
    """Create a JiraExtractor instance with our mock clients."""
    extractor = JiraExtractor(jira=mock_jira, max_reference_depth=2)
    extractor.url_analyzer = mock_url_analyzer
    return extractor

@pytest.mark.asyncio
async def test_extract_basic_fields(extractor):
    """Test extraction of basic ticket fields."""
    ticket_id = MOCK_MAIN_TICKET['key']
    ticket_data = await extractor.get_ticket(ticket_id)
    
    assert ticket_data['id'] == ticket_id
    assert ticket_data['summary'] == MOCK_MAIN_TICKET['fields']['summary']
    assert ticket_data['description'] == MOCK_MAIN_TICKET['fields']['description']
    assert ticket_data['status'] == MOCK_MAIN_TICKET['fields']['status']['name']
    assert ticket_data['priority'] == MOCK_MAIN_TICKET['fields']['priority']['name']
    assert ticket_data['assignee'] == MOCK_MAIN_TICKET['fields']['assignee']['displayName']
    assert ticket_data['reporter'] == MOCK_MAIN_TICKET['fields']['reporter']['displayName']
    assert set(ticket_data['labels']) == set(MOCK_MAIN_TICKET['fields']['labels'])

@pytest.mark.asyncio
async def test_extract_timestamps(extractor):
    """Test extraction and parsing of timestamp fields."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Convert the returned timestamps to datetime objects for comparison
    ticket_created = datetime.strptime(ticket_data['created'], '%Y-%m-%dT%H:%M:%S.%f%z')
    ticket_updated = datetime.strptime(ticket_data['updated'], '%Y-%m-%dT%H:%M:%S.%f%z')
    
    expected_created = datetime.strptime(MOCK_MAIN_TICKET['fields']['created'], '%Y-%m-%dT%H:%M:%S.%f%z')
    expected_updated = datetime.strptime(MOCK_MAIN_TICKET['fields']['updated'], '%Y-%m-%dT%H:%M:%S.%f%z')
    
    assert ticket_created == expected_created
    assert ticket_updated == expected_updated

@pytest.mark.asyncio
async def test_extract_references(extractor):
    """Test extraction of ticket references from description and comments."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Check that references from description are captured
    jira_refs = ticket_data['references']['jira_tickets']
    ref_ids = [ref['id'] for ref in jira_refs]
    
    assert 'PROJ-5678' in ref_ids
    assert 'PROJ-9012' in ref_ids
    
    # Check that references from issue links are captured
    for link in MOCK_MAIN_TICKET['fields']['issuelinks']:
        if 'outwardIssue' in link:
            assert link['outwardIssue']['key'] in ref_ids
        if 'inwardIssue' in link:
            assert link['inwardIssue']['key'] in ref_ids

@pytest.mark.asyncio
async def test_extract_comments(extractor):
    """Test extraction and processing of comments."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Filter out bot comments from mock data for comparison
    non_bot_comments = [
        comment for comment in MOCK_COMMENTS 
        if not comment['author']['displayName'].lower().endswith('bot')
    ]
    
    assert len(ticket_data['comments']) == len(non_bot_comments)
    for i, comment in enumerate(non_bot_comments):
        assert ticket_data['comments'][i]['author'] == comment['author']['displayName']
        assert ticket_data['comments'][i]['body'] == comment['body']
        assert ticket_data['comments'][i]['created'] == comment['created']

@pytest.mark.asyncio
async def test_no_self_references(extractor):
    """Test that references to the main ticket are handled as placeholders."""
    ticket_id = MOCK_MAIN_TICKET['key']
    ticket_data = await extractor.get_ticket(ticket_id)
    
    # Check references to the main ticket
    parent_refs = [
        ref for ref in ticket_data['references']['jira_tickets']
        if ref['id'] == ticket_id
    ]
    
    # If there are references to the main ticket, they should be placeholders
    for ref in parent_refs:
        assert ref['context'] == "Previously processed ticket"
        assert ref['metadata']['is_parent_reference'] is True
        assert ref['metadata']['is_processed_reference'] is True

@pytest.mark.asyncio
async def test_unique_references(extractor):
    """Test that references are unique even if mentioned multiple times."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Get all Jira ticket IDs from references
    ref_ids = [ref['id'] for ref in ticket_data['references']['jira_tickets']]
    # Convert to set and back to list to check for duplicates
    assert len(ref_ids) == len(set(ref_ids))

@pytest.mark.asyncio
async def test_confluence_references(extractor):
    """Test extraction of Confluence page references."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Check for Confluence URLs in references
    confluence_refs = ticket_data['references']['confluence_pages']
    assert len(confluence_refs) > 0
    
    # Verify the structure of Confluence references
    for ref in confluence_refs:
        assert 'id' in ref
        assert 'url' in ref
        assert 'context' in ref
        assert 'metadata' in ref
        assert ref['metadata']['type'] == 'confluence_page'
        assert ref['metadata']['resource_type'] == 'confluence_page'

@pytest.mark.asyncio
async def test_external_urls(extractor):
    """Test extraction of external URLs."""
    ticket_data = await extractor.get_ticket(MOCK_MAIN_TICKET['key'])
    
    # Check that we have references
    assert 'references' in ticket_data
    
    # Check that all reference categories exist
    assert 'other_urls' in ticket_data['references']
    assert 'confluence_pages' in ticket_data['references']
    assert 'jira_tickets' in ticket_data['references']
    assert 'scrapable_documentation' in ticket_data['references']
    
    # Verify the structure of external URLs
    for url in ticket_data['references']['other_urls']:
        assert 'url' in url
        assert 'context' in url
        assert 'metadata' in url
        assert url['metadata']['type'] == 'external'
        assert url['metadata']['resource_type'] == 'external_url' 