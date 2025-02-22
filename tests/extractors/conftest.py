import pytest
import json
import os
from pathlib import Path
import tempfile
import sqlite3
import sys

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def sample_ticket():
    """Basic ticket fixture with common fields."""
    return {
        "id": "TEST-123",
        "key": "TEST-123",
        "description": "This is a test ticket with a https://example.com link and a confluence link: https://confluence.example.com/display/TEST/Page",
        "comments": [
            {
                "id": "1",
                "body": "Comment with a JIRA link: https://jira.example.com/browse/TEST-456",
                "author": "test@example.com",
                "created": "2024-02-10T12:30:00.000+0000"
            }
        ],
        "created": "2024-02-10T12:00:00.000+0000",
        "updated": "2024-02-10T13:00:00.000+0000",
        "status": {"name": "Open"},
        "assignee": "assignee@example.com",
        "reporter": "reporter@example.com"
    }

@pytest.fixture
def test_data_dir():
    """Fixture providing path to test data directory."""
    return Path(__file__).parent / "data" / "samples"

@pytest.fixture
def save_sample_ticket(test_data_dir, sample_ticket):
    """Save a sample ticket to the test data directory."""
    test_data_dir.mkdir(parents=True, exist_ok=True)
    ticket_path = test_data_dir / "TEST-123.json"
    
    with open(ticket_path, "w") as f:
        json.dump(sample_ticket, f, indent=2)
    
    return ticket_path 