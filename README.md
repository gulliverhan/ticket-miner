# Ticket Miner

A Python library that replicates how a human would investigate a Jira ticket by automatically mining all referenced content - linked tickets, Confluence pages, Help Center articles, and more - into a structured format suitable for Large Language Model processing.

## Overview

When troubleshooting or analyzing a ticket, a human would:
1. Read the ticket description and comments
2. Follow links to related Jira tickets
3. Check referenced Confluence documentation
4. Look up any Help Center or Developer Documentation pages
5. Analyze all this information together

This library automates this process by:
- Mining the main ticket content
- Following and extracting content from all references recursively
- Converting everything into a clean, structured JSON format
- Making the entire context available for LLM processing

The result is a comprehensive "knowledge bundle" containing all relevant information about a ticket and its context, perfect for:
- Ticket analysis and categorization by LLMs
- Automated troubleshooting
- Knowledge extraction and synthesis
- Pattern recognition across tickets
- Support workflow automation

## Features

- Comprehensive ticket content extraction:
  - Main ticket information (description, comments, metadata)
  - Linked Jira tickets (with their own references)
  - Referenced Confluence pages (with attachments)
  - Help Center articles
  - Developer documentation
  - External URLs
- Smart URL detection and categorization
- Configurable URL patterns and scraping rules
- Resource metadata extraction
- Flexible domain configuration
- Recursive reference processing
- Cycle detection to prevent infinite loops
- Structured output format optimized for LLM processing

## Installation

```bash
pip install ticket-miner
```

## Quick Start

First, set up your environment variables:

```bash
# .env file
BASE_DOMAIN=yourdomain.com
JIRA_URL=https://jira.yourdomain.com
CONFLUENCE_URL=https://confluence.yourdomain.com
JIRA_USERNAME=your_username
JIRA_API_TOKEN=your_api_token
```

Then mine a complete ticket bundle:

```python
from ticket_miner import TicketMiner
from ticket_miner.extractors import JiraExtractor, ConfluenceExtractor

# Initialize the miner with desired extractors
miner = TicketMiner(
    jira_extractor=JiraExtractor(),
    confluence_extractor=ConfluenceExtractor()
)

# Get complete ticket data with all references
ticket_data = miner.mine_ticket("PROJ-123")

# The ticket_data will contain everything a human would look at:
{
    # Main ticket information
    "id": "PROJ-123",
    "summary": "Example ticket",
    "description": "Ticket description...",
    "status": "Open",
    "priority": "High",
    "assignee": "John Smith",
    "reporter": "Jane Doe",
    "created": "2024-02-18T10:00:00.000Z",
    "updated": "2024-02-18T11:00:00.000Z",
    "labels": ["label1", "label2"],
    
    # Ticket comments in chronological order
    "comments": [
        {
            "author": "John Smith",
            "body": "Comment text...",
            "created": "2024-02-18T10:30:00.000Z",
            "is_support_team": true
        }
    ],
    
    # All referenced content
    "references": {
        # Documentation from Confluence
        "confluence_pages": [
            {
                "id": "12345",
                "title": "Documentation Page",
                "space_key": "DOCS",
                "content": "Page content in markdown...",
                "url": "https://confluence.example.com/pages/12345",
                "creator": "Jane Doe",
                "created": "2024-02-17T10:00:00.000Z",
                "updated": "2024-02-18T09:00:00.000Z",
                "attachments": [
                    {
                        "filename": "document.pdf",
                        "size": 1024,
                        "mediaType": "application/pdf"
                    }
                ]
            }
        ],
        
        # Other Jira tickets referenced (with their own references)
        "jira_tickets": [
            {
                "id": "PROJ-124",
                "summary": "Related ticket",
                "status": "Closed",
                "description": "Related ticket description...",
                "references": {
                    # Each linked ticket also includes its references
                    "confluence_pages": [...],
                    "jira_tickets": [...],
                    "scrapable_documentation": [...]
                }
            }
        ],
        
        # Help Center and Developer Documentation
        "scrapable_documentation": [
            {
                "url": "https://help.example.com/article/123",
                "title": "Help Article",
                "content": "Article content...",
                "author": "Support Team",
                "date": "2024-02-15"
            }
        ],
        
        # Any other referenced URLs
        "other_urls": [
            {
                "url": "https://example.com/some-page",
                "type": "external",
                "domain": "example.com",
                "context": "Referenced in comment"
            }
        ]
    }
}
```

## Configuration

### Environment Variables

The library uses environment variables for configuration. You can set these in a `.env` file:

```bash
# Base domain for your organization
BASE_DOMAIN=yourdomain.com

# Jira configuration
JIRA_URL=https://jira.yourdomain.com
JIRA_USERNAME=your_username
JIRA_API_TOKEN=your_api_token

# Confluence configuration
CONFLUENCE_URL=https://confluence.yourdomain.com
CONFLUENCE_USERNAME=your_username
CONFLUENCE_API_TOKEN=your_api_token
```

### Custom URL Patterns

Create a JSON file with your custom URL patterns:

```json
{
  "url_patterns": {
    "help_center": {
      "domains": ["help.yourdomain.com"],
      "scrape": true,
      "exclude_patterns": [
        "^/search(/.*)?$",
        "^/user(/.*)?$"
      ]
    }
  }
}
```

Initialize the analyzer with your patterns:

```python
analyzer = URLAnalyzer(patterns_file="path/to/patterns.json")
```

## Advanced Usage

### Controlling Reference Depth

You can control how deep the extractor follows references:

```python
# Only extract direct references
extractor = JiraExtractor(max_reference_depth=1)

# Extract references up to 3 levels deep (default is 2)
extractor = JiraExtractor(max_reference_depth=3)
```

### Async Support

For web applications or when processing multiple tickets:

```python
async def process_ticket():
    extractor = JiraExtractor()
    ticket_data = await extractor.get_ticket("PROJ-123")
    # Process the ticket data
```

## API Reference

### URLAnalyzer

The main class for URL analysis and extraction.

#### Methods

- `analyze_content(content: str, source_content_id: str, source_type: str = "description") -> List[URLMatch]`
  Analyzes content to find and categorize URLs.

- `is_scrapable_url(url: str, domain: str) -> bool`
  Checks if a URL should be scraped based on configuration.

- `print_summary()`
  Prints a summary of URL analysis statistics.

#### Configuration Options

- `base_domain`: Your organization's base domain
- `patterns_file`: Path to custom URL patterns JSON file

### URLMatch

Data class containing information about matched URLs.

#### Attributes

- `url`: The matched URL
- `url_type`: Type of URL (e.g., "collaboration", "help_center")
- `domain`: URL domain
- `path`: URL path
- `resource_metadata`: Extracted resource metadata
- `context`: Surrounding content context
- `source_content_id`: ID of source content
- `source_type`: Type of source content
- `should_scrape`: Whether URL should be scraped

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. 