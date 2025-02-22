import pytest
import json
import tempfile
from ticket_extractors import PersonAnalyzer

@pytest.fixture
def mock_ticket():
    """Create a mock ticket with various person activities."""
    return {
        'id': 'TEST-123',
        'assignee': 'John Smith',
        'reporter': 'Jane Doe',
        'created': '2024-02-18T10:00:00.000Z',
        'updated': '2024-02-18T11:00:00.000Z',
        'comments': [
            {
                'author': 'John Smith',
                'body': 'First comment',
                'created': '2024-02-18T10:30:00.000Z'
            },
            {
                'author': 'Support Team Member',
                'body': 'Support response',
                'created': '2024-02-18T10:45:00.000Z'
            }
        ]
    }

@pytest.fixture
def support_team_file(tmp_path):
    """Create a temporary support team JSON file."""
    config = {
        'support_team': ['Support Team Member']
    }
    file_path = tmp_path / "support_team.json"
    with open(file_path, 'w') as f:
        json.dump(config, f)
    return str(file_path)

def test_analyze_ticket_basic():
    """Test basic ticket analysis without support team."""
    analyzer = PersonAnalyzer()
    ticket = {
        'id': 'TEST-123',
        'assignee': 'John Smith',
        'reporter': 'Jane Doe',
        'created': '2024-02-18T10:00:00.000Z',
        'updated': '2024-02-18T11:00:00.000Z',
        'comments': []
    }
    
    analyzer.analyze_ticket(ticket)
    
    assert len(analyzer.people_database['people']) == 2
    assert 'John Smith' in analyzer.people_database['people']
    assert 'Jane Doe' in analyzer.people_database['people']
    assert not analyzer.has_team_config
    assert not analyzer.is_team_member('John Smith')

def test_analyze_ticket_with_support_team(mock_ticket, support_team_file):
    """Test ticket analysis with support team configuration."""
    analyzer = PersonAnalyzer(support_team_file=support_team_file)
    analyzer.analyze_ticket(mock_ticket)
    
    # Check support team identification
    assert analyzer.has_team_config
    assert analyzer.is_team_member('Support Team Member')
    assert not analyzer.is_team_member('John Smith')
    
    # Check activity tracking
    people = analyzer.people_database['people']
    assert len(people) == 3  # John Smith, Jane Doe, Support Team Member
    
    # Check statistics
    stats = analyzer.people_database['statistics']
    assert stats['total_activities'] == 4  # assignee, reporter, 2 comments

def test_analyze_ticket_comments():
    """Test analysis of ticket comments."""
    analyzer = PersonAnalyzer()
    ticket = {
        'id': 'TEST-123',
        'assignee': 'John Smith',
        'reporter': 'John Smith',
        'created': '2024-02-18T10:00:00.000Z',
        'updated': '2024-02-18T11:00:00.000Z',
        'comments': [
            {
                'author': 'John Smith',
                'body': 'First comment',
                'created': '2024-02-18T10:30:00.000Z'
            }
        ]
    }
    
    analyzer.analyze_ticket(ticket)
    
    # Check that activities are properly tracked for the same person
    john_data = analyzer.people_database['people']['John Smith']
    assert len(john_data['activities']) == 3  # assignee, reporter, comment
    assert len(john_data['activity_types']) == 3
    assert john_data['tickets_involved'] == {'TEST-123'}

def test_missing_support_team_file():
    """Test behavior when support team file doesn't exist."""
    analyzer = PersonAnalyzer(support_team_file="nonexistent.json")
    assert not analyzer.has_team_config
    assert not analyzer.is_team_member('Anyone') 