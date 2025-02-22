import re
import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
from datetime import datetime
import os
from pathlib import Path
from . import config
from .rate_limiter import rate_limited
from .memory_manager import MemoryManager

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class ResourceMetadata:
    """Metadata about a resource extracted from a URL."""
    resource_type: str
    resource_id: str
    parent_id: Optional[str] = None

@dataclass
class URLMatch:
    """A matched URL with its metadata."""
    url: str
    url_type: str
    should_scrape: bool
    resource_metadata: Optional[ResourceMetadata] = None
    context: Optional[str] = None

class URLAnalyzer:
    """Analyzes URLs to determine their type and whether they should be scraped."""

    def __init__(self, patterns_file: Optional[str] = None):
        """Initialize the URL analyzer.

        Args:
            patterns_file: Optional path to a JSON file containing custom URL patterns.
        """
        self.domain_to_platform = {}
        self.platform_patterns = {}
        self.scraping_config = {}
        self.resource_patterns = {}
        self.memory_manager = MemoryManager()

        # Load configuration
        self.config = config.load_config()
        self.base_domain = self.config.base_domain

        # Load patterns
        if patterns_file:
            self._load_custom_patterns(patterns_file)
        else:
            self._load_builtin_patterns()

    def _load_builtin_patterns(self):
        """Load built-in patterns for Jira and Confluence."""
        # Default Jira domains based on common patterns
        jira_domains = [
            f"jira.{self.base_domain}",  # Standard subdomain
            f"issues.{self.base_domain}",  # Alternative subdomain
            "atlassian.net"  # Cloud instance
        ]
        
        self.platform_patterns["jira"] = {
            "domains": jira_domains,
            "scrape": True,
            "resource_patterns": [
                {
                    "pattern": r"/browse/([A-Z]+-[0-9]+)",
                    "type": "jira_ticket",
                    "extract_id": "$1"
                }
            ]
        }
        
        # Default Confluence domains based on common patterns
        confluence_domains = [
            f"confluence.{self.base_domain}",  # Standard subdomain
            f"wiki.{self.base_domain}",        # Alternative subdomain
            "atlassian.net"  # Cloud instance
        ]
        
        self.platform_patterns["confluence"] = {
            "domains": confluence_domains,
            "scrape": True,
            "resource_patterns": [
                {
                    "pattern": r"/display/([^/]+)/([^/]+)",
                    "type": "confluence_page",
                    "extract_id": "$2"
                }
            ]
        }
        
        # Update domain mappings
        for platform, config in self.platform_patterns.items():
            for domain in config["domains"]:
                self.domain_to_platform[domain] = platform

    def _load_custom_patterns(self, patterns_file: str):
        """Load custom URL patterns from a JSON file."""
        with open(patterns_file) as f:
            patterns = json.load(f)
            
        if "url_patterns" in patterns:
            for platform, config in patterns["url_patterns"].items():
                self.platform_patterns[platform] = config
                for domain in config["domains"]:
                    self.domain_to_platform[domain] = platform

    def _should_scrape(self, platform: str, path: str) -> bool:
        """Determine if a URL should be scraped based on platform config."""
        config = self.platform_patterns.get(platform)
        if not config:
            return False
            
        # Check if scraping is enabled for this platform
        if not config.get("scrape", False):
            return False
            
        # Check exclude patterns
        exclude_patterns = config.get("exclude_patterns", [])
        for pattern in exclude_patterns:
            # Use re.match to ensure pattern matches from the start of the path
            # and compile the pattern first for better performance
            try:
                logger.info(f"Checking pattern '{pattern}' against path '{path}'")
                if re.match(pattern, path):
                    logger.info(f"Pattern '{pattern}' matched path '{path}', excluding from scraping")
                    return False
            except re.error:
                # If the pattern is invalid, log a warning and continue
                logger.warning(f"Invalid exclude pattern: {pattern}")
                continue
                
        return True

    def _extract_resource_metadata(self, platform: str, path: str) -> Optional[ResourceMetadata]:
        """Extract resource metadata from a URL path using platform-specific patterns."""
        config = self.platform_patterns.get(platform)
        if not config or "resource_patterns" not in config:
            return None
            
        # Sort patterns by length (descending) to match most specific patterns first
        patterns = sorted(
            config["resource_patterns"],
            key=lambda p: len(p["pattern"]),
            reverse=True
        )
        
        for pattern_config in patterns:
            match = re.search(pattern_config["pattern"], path)
            if match:
                # Extract resource ID and parent ID if specified
                resource_id = pattern_config["extract_id"]
                parent_id = pattern_config.get("parent_id")
                
                # Replace capture group references ($1, $2, etc.) with actual values
                for i, group in enumerate(match.groups(), 1):
                    resource_id = resource_id.replace(f"${i}", group)
                    if parent_id:
                        parent_id = parent_id.replace(f"${i}", group)
                
                return ResourceMetadata(
                    resource_type=pattern_config["type"],
                    resource_id=resource_id,
                    parent_id=parent_id
                )
                
        return None

    @rate_limited()
    async def analyze_content(self, content: str, source_id: str) -> List[URLMatch]:
        """Analyze content to find and categorize URLs.

        Args:
            content: The text content to analyze
            source_id: ID of the source content (e.g. ticket ID)

        Returns:
            List of URLMatch objects containing information about each URL found

        Raises:
            MemoryError: If memory usage exceeds configured limits
        """
        matches = []
        
        # Find all URLs in the content
        urls = re.finditer(r'https?://[^\s<>"]+|www\.[^\s<>"]+', content)
        
        for url_match in urls:
            # Check memory usage before processing each URL
            self.memory_manager.check_memory()
            
            url = url_match.group()
            
            # Normalize URL
            if url.startswith('www.'):
                url = f'https://{url}'
                
            try:
                # Parse URL
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                path = parsed.path.rstrip('/')
                
                # Default values
                url_type = 'external'
                platform = None
                should_scrape = False
                resource_metadata = None
                
                # Check if it's a help center URL
                if any(pattern in domain.lower() for pattern in [f"help.{self.base_domain}", f"support.{self.base_domain}", 'help.', 'support.']):
                    url_type = 'help_center'
                    platform = 'help_center'
                # Check if it's a developer docs URL
                elif any(pattern in domain.lower() for pattern in [
                    f"developers.{self.base_domain}",
                    f"developer.{self.base_domain}",
                    f"docs.{self.base_domain}",
                    f"documentation.{self.base_domain}",
                    'developers.',
                    'developer.',
                    'docs.',
                    'documentation.'
                ]):
                    url_type = 'documentation'
                    platform = 'documentation'
                # Check if it's a collaboration tool URL
                elif domain.endswith('atlassian.net') or any(domain.endswith(d) for d in [
                    f"jira.{self.base_domain}",
                    f"confluence.{self.base_domain}",
                    f"wiki.{self.base_domain}"
                ]):
                    if '/browse/' in path or '/issues/' in path:
                        url_type = 'jira'
                        platform = 'jira'
                        # Extract ticket ID
                        match = re.search(r'/browse/([A-Z]+-[0-9]+)', path)
                        if match:
                            resource_metadata = ResourceMetadata(
                                resource_type='jira_ticket',
                                resource_id=match.group(1)
                            )
                    elif '/display/' in path or '/spaces/' in path or '/wiki/' in path:
                        url_type = 'confluence'
                        platform = 'confluence'
                        # Extract page ID
                        if '/pages/' in path:
                            page_id = path.split('/pages/')[-1].split('/')[0]
                            resource_metadata = ResourceMetadata(
                                resource_type='confluence_page',
                                resource_id=page_id
                            )
                
                # Check if domain is in our platform mappings
                if domain in self.domain_to_platform:
                    platform = self.domain_to_platform[domain]
                    url_type = platform
                
                # Determine if URL should be scraped
                if platform:
                    should_scrape = self._should_scrape(platform, path)
                    if not resource_metadata:
                        resource_metadata = self._extract_resource_metadata(platform, path)
                
                matches.append(URLMatch(
                    url=url,
                    url_type=url_type,
                    should_scrape=should_scrape,
                    resource_metadata=resource_metadata
                ))
                
            except Exception as e:
                logger.error(f"Error analyzing URL {url}: {str(e)}")
                continue
        
        return matches

    def _clean_url(self, url: str) -> str:
        """Clean and normalize a URL."""
        # Handle Confluence/Jira smart-link format
        if '|' in url:
            url = url.split('|')[0]
        
        # Remove any trailing punctuation or brackets
        url = re.sub(r'[\]\)\.\,]+$', '', url)
        
        # Remove any markdown link formatting
        url = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'\2', url)
        
        # Parse URL to handle encoding and fragments
        parsed = urlparse(url.strip())
        # Remove fragment and normalize path
        cleaned_url = urljoin(
            f"{parsed.scheme}://{parsed.netloc}",
            parsed.path.replace(' ', '%20')  # Properly encode spaces
        )
        # Add back query parameters if they exist
        if parsed.query:
            cleaned_url += '?' + parsed.query
            
        return cleaned_url

    def reset_stats(self):
        """Reset URL statistics."""
        self.url_stats = {
            'total_urls': 0,
            'by_type': {},
            'by_resource_type': {},
            'unique_domains': set(),
            'unmatched_urls': [],
            'resource_relationships': {}
        }

    def _update_stats(self, match: URLMatch):
        """Update URL statistics with a new match."""
        self.url_stats['total_urls'] += 1
        self.url_stats['by_type'][match.url_type] = \
            self.url_stats['by_type'].get(match.url_type, 0) + 1
        self.url_stats['unique_domains'].add(match.domain)
        
        if match.resource_metadata:
            resource_type = match.resource_metadata.resource_type
            self.url_stats['by_resource_type'][resource_type] = \
                self.url_stats['by_resource_type'].get(resource_type, 0) + 1
            
            # Track relationships
            relationship_key = f"{match.source_type}_{resource_type}"
            self.url_stats['resource_relationships'][relationship_key] = \
                self.url_stats['resource_relationships'].get(relationship_key, 0) + 1

    def is_scrapable_url(self, url: str, domain: str) -> bool:
        """Check if a URL is scrapable based on its domain and path."""
        # Check if it's a known documentation domain
        platform = self.domain_to_platform.get(domain)
        if platform in ['developer_docs', 'help_center']:
            return True
            
        # Check if it's a public documentation URL
        if any(pattern in domain.lower() for pattern in ['docs.', 'documentation.', 'help.', 'support.']):
            return True
            
        return False

    def print_summary(self):
        """Print a summary of URL analysis."""
        print("\nURL Analysis Summary:")
        print(f"Total URLs found: {self.url_stats['total_urls']}")
        
        if self.url_stats['by_type']:
            print("\nBy type:")
            for url_type, count in self.url_stats['by_type'].items():
                print(f"- {url_type}: {count}")
        
        if self.url_stats['by_resource_type']:
            print("\nBy resource type:")
            for resource_type, count in self.url_stats['by_resource_type'].items():
                print(f"- {resource_type}: {count}")
        
        if self.url_stats['unique_domains']:
            print("\nUnique domains:")
            for domain in sorted(self.url_stats['unique_domains']):
                print(f"- {domain}")
        
        if self.url_stats['resource_relationships']:
            print("\nResource relationships:")
            for relationship, count in self.url_stats['resource_relationships'].items():
                print(f"- {relationship}: {count}")

    def _organize_urls_by_type(self, url_matches: List[URLMatch]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Organize URLs by their type into appropriate sections.
        
        Args:
            url_matches: List of URLMatch objects to organize
            
        Returns:
            Dict with URLs organized by type (confluence_pages, jira_tickets, other_urls, etc.)
        """
        organized = {
            'confluence_pages': [],
            'jira_tickets': [],
            'other_urls': [],
            'scrapable_documentation': []
        }
        
        for match in url_matches:
            url_data = {
                'id': match.resource_metadata.resource_id if match.resource_metadata else None,
                'url': match.url,
                'context': match.context,
                'metadata': {
                    'url': match.url,
                    'type': match.url_type,
                    'domain': match.domain,
                    'context': match.context,
                    'resource_metadata': vars(match.resource_metadata) if match.resource_metadata else None
                }
            }
            
            # Add title and content for Confluence pages
            if match.url_type == 'confluence':
                organized['confluence_pages'].append(url_data)
            # Add summary and status for Jira tickets
            elif match.url_type == 'jira':
                organized['jira_tickets'].append(url_data)
            # Add scrapable documentation
            elif self.is_scrapable_url(match.url, match.domain):
                organized['scrapable_documentation'].append(url_data)
            # Add other URLs
            else:
                organized['other_urls'].append(url_data)
        
        return organized 

    def _get_url_type(self, domain: str, path: str) -> str:
        """Determine the type of URL based on domain and path."""
        # Check if domain is in any of our platform configurations
        for platform, config in self.platform_patterns.items():
            if domain in config.get('domains', []):
                return platform

        # Check for Jira and Confluence URLs
        if domain.endswith('atlassian.net'):
            if '/browse/' in path or '/issues/' in path:
                return 'collaboration'  # Jira
            elif '/wiki/' in path or '/display/' in path:
                return 'collaboration'  # Confluence

        # Default to external for unrecognized URLs
        return 'external' 