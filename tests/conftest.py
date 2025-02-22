import os
import tempfile
import sqlite3
import pytest
from pathlib import Path
import sys

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def tickets_dir():
    """Create a temporary directory for test ticket files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def db_path():
    """Create a temporary SQLite database file."""
    _, temp_db = tempfile.mkstemp(suffix='.db')
    yield temp_db
    os.unlink(temp_db)

@pytest.fixture
def db_connection(db_path):
    """Create and initialize the SQLite database with required tables."""
    conn = sqlite3.connect(db_path)
    
    # Create tables
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS url_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            urlType TEXT NOT NULL,
            domain TEXT NOT NULL,
            path TEXT NOT NULL,
            resourcePlatform TEXT,
            UNIQUE(url)
        );
        
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_content_type TEXT NOT NULL,
            source_content_id TEXT NOT NULL,
            target_content_type TEXT NOT NULL,
            target_content_id TEXT NOT NULL,
            UNIQUE(source_content_type, source_content_id, target_content_type, target_content_id)
        );
        
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            description TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            status TEXT,
            priority TEXT,
            labels TEXT
        );
    """)
    
    yield conn
    conn.close() 