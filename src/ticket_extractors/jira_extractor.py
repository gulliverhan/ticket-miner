import os
import json
import logging
from typing import Dict, List, Any, Optional, Set
from atlassian import Jira
from datetime import datetime
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from . import config
from .confluence_extractor import ConfluenceExtractor
from .webpage_extractor import WebPageExtractor
from .url_analyzer import URLAnalyzer
from .base_extractor import BaseExtractor
from .rate_limiter import rate_limited, RateLimitConfig
from .memory_manager import memory_managed, MemoryManager, MemoryConfig
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger(__name__)

def truncate_for_logging(text: str, max_length: int = 100) -> str:
    """Truncate text for logging purposes."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."

class JiraExtractor(BaseExtractor):
    def __init__(self, jira=None, max_reference_depth: int = 2, support_team_file: str = None):
        """Initialize the JiraExtractor.
        
        Args:
            jira: Optional Jira client instance. If not provided, one will be created using environment variables.
            max_reference_depth: Maximum depth for recursive reference processing.
            support_team_file: Optional path to a JSON file containing support team member information.
        """
        super().__init__()
        if jira is None:
            logger.info(f"Connecting to Jira: {config.JIRA_URL}")
            
            try:
                self.jira = Jira(
                    url=config.JIRA_URL,
                    username=config.JIRA_USERNAME,
                    password=config.JIRA_API_TOKEN
                )
            except Exception as e:
                logger.error(f"Jira connection failed: {str(e)}")
                raise
        else:
            self.jira = jira
            
        self.confluence_extractor = ConfluenceExtractor()
        self.webpage_extractor = WebPageExtractor()
        self.url_analyzer = URLAnalyzer()
        self.max_reference_depth = max_reference_depth
        
        # Load support team members
        self.support_team = self._load_support_team(support_team_file)
        
        # Track processed content to avoid cycles
        self.processed_ids = set()
        self.failed_urls = []
        
        # Statistics for reference tracking
        self.reference_stats = {
            'total_references': 0,
            'by_type': {},
            'by_depth': {},
            'failed_fetches': 0
        }
        
        # Create sync versions of async methods
        self.get_ticket_sync = self._make_sync(self.get_ticket)
    
    def _load_support_team(self, support_team_file: str = None) -> set:
        """Load support team members from config file."""
        try:
            if support_team_file:
                with open(support_team_file, 'r') as f:
                    config = json.load(f)
                    return set(config.get('support_team', []))
            return set()
        except Exception as e:
            logger.warning(f"Failed to load support team config: {str(e)}")
            return set()

    async def get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """
        Extract a single ticket and all its referenced content.
        
        Args:
            ticket_id: The Jira ticket ID (e.g., "PROJ-123")
            
        Returns:
            Dict containing the ticket data and all referenced content
        """
        logger.info(f"Extracting ticket: {ticket_id}")
        return await self._get_ticket_with_references(ticket_id, depth=0)

    async def _get_ticket_with_references(self, ticket_id: str, depth: int = 0, parent_id: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch a Jira ticket by its ID and recursively process its references.
        
        Args:
            ticket_id: The Jira ticket ID (e.g., 'SUPPORT-123')
            depth: Current depth in reference chain
            parent_id: ID of the parent ticket to create placeholder references
            
        Returns:
            Dict containing the ticket data and its references, or a reference to an already processed ticket
        """
        # If this is a reference to the parent ticket, return a placeholder reference
        if parent_id and ticket_id == parent_id:
            logger.info(f"Creating placeholder reference for parent ticket {parent_id}")
            return {
                'id': ticket_id,
                'url': f"{config.JIRA_URL}/browse/{ticket_id}",
                'context': "Previously processed ticket",
                'metadata': {
                    'platform': 'knowledge_base',
                    'resource_type': 'jira_ticket',
                    'resource_id': ticket_id,
                    'ticket_id': ticket_id,
                    'is_parent_reference': True,
                    'is_processed_reference': True
                }
            }
            
        # Check if we've already processed this ticket
        if ticket_id in self.processed_ids:
            logger.info(f"Creating placeholder reference for {'parent' if ticket_id == parent_id else 'already processed'} ticket {ticket_id}")
            # Return a reference to the already processed ticket
            return {
                'id': ticket_id,
                'url': f"{config.JIRA_URL}/browse/{ticket_id}",
                'context': "Previously processed ticket",
                'metadata': {
                    'platform': 'knowledge_base',
                    'resource_type': 'jira_ticket',
                    'resource_id': ticket_id,
                    'ticket_id': ticket_id,
                    'is_parent_reference': ticket_id == parent_id,
                    'is_processed_reference': True
                }
            }
            
        # Check depth limit
        if depth > self.max_reference_depth:
            logger.info(f"Reached max depth ({self.max_reference_depth}) for {ticket_id}")
            return None
            
        try:
            issue = self.jira.issue(ticket_id)
            
            # Extract the most important fields
            ticket_data = {
                'id': issue['key'],
                'summary': issue['fields']['summary'],
                'description': issue['fields']['description'],
                'status': issue['fields']['status']['name'],
                'created': issue['fields']['created'],
                'updated': issue['fields']['updated'],
                'priority': issue['fields']['priority']['name'] if 'priority' in issue['fields'] else 'None',
                'assignee': issue['fields']['assignee']['displayName'] if issue['fields'].get('assignee') else 'Unassigned',
                'reporter': issue['fields']['reporter']['displayName'] if issue['fields'].get('reporter') else 'Unknown',
                'labels': issue['fields'].get('labels', []),
                'comments': [],
                'references': {
                    'confluence_pages': [],
                    'jira_tickets': [],
                    'other_urls': [],
                    'scrapable_documentation': []
                }
            }
            
            # Mark as processed BEFORE processing references to avoid cycles
            self.processed_ids.add(ticket_id)
            
            # Track unique references by URL to avoid duplicates
            processed_urls = set()
            
            # Process description URLs
            if ticket_data['description']:
                url_matches = await self.url_analyzer.analyze_content(ticket_data['description'])
                for match in url_matches:
                    if match.url not in processed_urls:
                        processed_urls.add(match.url)
                        if match.url_type == 'jira':
                            referenced_ticket = await self._get_ticket_with_references(
                                match.resource_metadata.resource_id,
                                depth=depth + 1,
                                parent_id=ticket_id
                            )
                            if referenced_ticket:
                                ticket_data['references']['jira_tickets'].append(referenced_ticket)
                        elif match.url_type == 'confluence':
                            ticket_data['references']['confluence_pages'].append({
                                'id': match.resource_metadata.resource_id,
                                'url': match.url,
                                'context': match.context or 'Found in description',
                                'metadata': match.resource_metadata
                            })
                        elif match.url_type == 'documentation':
                            ticket_data['references']['scrapable_documentation'].append({
                                'url': match.url,
                                'context': match.context or 'Found in description',
                                'metadata': match.resource_metadata
                            })
                        else:
                            ticket_data['references']['other_urls'].append({
                                'url': match.url,
                                'context': match.context or 'Found in description',
                                'metadata': match.resource_metadata
                            })
            
            # Process comments
            comments = self.jira.issue_get_comments(ticket_id)
            for comment in comments.get('comments', []):
                # Skip bot comments
                if comment['author']['displayName'].lower().endswith('bot'):
                    continue
                    
                comment_data = {
                    'author': comment['author']['displayName'],
                    'body': comment['body'],
                    'created': comment['created']
                }
                ticket_data['comments'].append(comment_data)
                
                # Process URLs in comment
                url_matches = await self.url_analyzer.analyze_content(comment['body'])
                for match in url_matches:
                    if match.url not in processed_urls:
                        processed_urls.add(match.url)
                        if match.url_type == 'jira':
                            referenced_ticket = await self._get_ticket_with_references(
                                match.resource_metadata.resource_id,
                                depth=depth + 1,
                                parent_id=ticket_id
                            )
                            if referenced_ticket:
                                ticket_data['references']['jira_tickets'].append(referenced_ticket)
                        elif match.url_type == 'confluence':
                            ticket_data['references']['confluence_pages'].append({
                                'id': match.resource_metadata.resource_id,
                                'url': match.url,
                                'context': match.context or f"Found in comment by {comment['author']['displayName']}",
                                'metadata': match.resource_metadata
                            })
                        elif match.url_type == 'documentation':
                            ticket_data['references']['scrapable_documentation'].append({
                                'url': match.url,
                                'context': match.context or f"Found in comment by {comment['author']['displayName']}",
                                'metadata': match.resource_metadata
                            })
                        else:
                            ticket_data['references']['other_urls'].append({
                                'url': match.url,
                                'context': match.context or f"Found in comment by {comment['author']['displayName']}",
                                'metadata': match.resource_metadata
                            })
            
            # Process direct issue links
            if 'issuelinks' in issue['fields']:
                for link in issue['fields']['issuelinks']:
                    linked_issue = None
                    link_type = link.get('type', {}).get('name', 'linked')
                    
                    if 'inwardIssue' in link:
                        linked_issue = link['inwardIssue']
                    elif 'outwardIssue' in link:
                        linked_issue = link['outwardIssue']
                    
                    if linked_issue:
                        url = f"{config.JIRA_URL}/browse/{linked_issue['key']}"
                        if url not in processed_urls:
                            processed_urls.add(url)
                            referenced_ticket = await self._get_ticket_with_references(
                                linked_issue['key'],
                                depth=depth + 1,
                                parent_id=ticket_id
                            )
                            if referenced_ticket:
                                ticket_data['references']['jira_tickets'].append(referenced_ticket)
            
            return ticket_data
            
        except Exception as e:
            logger.error(f"Error processing ticket {ticket_id}: {str(e)}")
            return None

    def _extract_ticket_data(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Extract basic ticket data from a Jira issue."""
        return {
            'id': issue['key'],
            'summary': issue['fields']['summary'],
            'description': issue['fields']['description'],
            'status': issue['fields']['status']['name'],
            'created': issue['fields']['created'],
            'updated': issue['fields']['updated'],
            'priority': issue['fields']['priority']['name'] if 'priority' in issue['fields'] else 'None',
            'assignee': issue['fields']['assignee']['displayName'] if issue['fields'].get('assignee') else 'Unassigned',
            'reporter': issue['fields']['reporter']['displayName'] if issue['fields'].get('reporter') else 'Unknown',
            'labels': issue['fields'].get('labels', []),
            'comments': [],
            'references': {
                'confluence_pages': [],
                'jira_tickets': [],
                'other_urls': [],
                'scrapable_documentation': []
            }
        }

    def _create_ticket_reference(self, ticket_id: str, parent_id: str = None) -> Dict[str, Any]:
        """Create a reference to an already processed ticket."""
        is_parent = ticket_id == parent_id
        url = f"{config.JIRA_URL}/browse/{ticket_id}"
        
        return {
            'id': ticket_id,
            'url': url,
            'context': "Reference to parent ticket" if is_parent else "Previously processed ticket",
            'metadata': {
                'platform': 'knowledge_base',
                'resource_type': 'jira_ticket',
                'resource_id': ticket_id,
                'ticket_id': ticket_id,
                'is_parent_reference': is_parent,
                'is_processed_reference': True
            }
        }

    @memory_managed("process_issue_links")
    async def _process_issue_links(self, issue: Dict[str, Any], ticket_data: Dict[str, Any], depth: int, parent_id: str = None) -> None:
        """Process issue links with memory management."""
        if 'issuelinks' not in issue['fields']:
            return

        # Process links in chunks
        for chunk in self._memory_manager.chunk_generator(issue['fields']['issuelinks']):
            for link in chunk:
                linked_issue = None
                link_type = link.get('type', {}).get('name', 'linked')
                
                if 'inwardIssue' in link:
                    linked_issue = link['inwardIssue']
                elif 'outwardIssue' in link:
                    linked_issue = link['outwardIssue']
                
                if not linked_issue:
                    continue

                try:
                    url = f"{config.JIRA_URL}/browse/{linked_issue['key']}"
                    url_data = {
                        'url': url,
                        'type': 'jira',
                        'domain': config.BASE_DOMAIN,
                        'context': f"Direct issue link ({link_type})",
                        'resource_metadata': {
                            'platform': 'knowledge_base',
                            'resource_type': 'jira_ticket',
                            'resource_id': linked_issue['key'],
                            'ticket_id': linked_issue['key']
                        }
                    }
                    
                    # Handle self-reference
                    if linked_issue['key'] == ticket_data['id']:
                        ticket_data['references']['jira_tickets'].append(
                            self._create_ticket_reference(linked_issue['key'], parent_id)
                        )
                        continue
                    
                    # Try to fetch the linked ticket if not already processed
                    referenced_ticket = None
                    if linked_issue['key'] not in self.processed_ids:
                        referenced_ticket = await self._get_ticket_with_references(
                            linked_issue['key'], 
                            depth=depth + 1, 
                            parent_id=ticket_data['id']
                        )
                    
                    if referenced_ticket:
                        if referenced_ticket.get('metadata', {}).get('is_parent_reference'):
                            ticket_data['references']['jira_tickets'].append(
                                self._create_ticket_reference(ticket_data['id'], parent_id)
                            )
                        else:
                            # Add full ticket data
                            ticket_data['references']['jira_tickets'].append({
                                'id': referenced_ticket['id'],
                                'summary': referenced_ticket['summary'],
                                'status': referenced_ticket['status'],
                                'url': url,
                                'context': url_data['context'],
                                'metadata': url_data,
                                'description': referenced_ticket['description'],
                                'comments': referenced_ticket['comments'],
                                'created': referenced_ticket['created'],
                                'updated': referenced_ticket['updated'],
                                'priority': referenced_ticket['priority'],
                                'assignee': referenced_ticket['assignee'],
                                'reporter': referenced_ticket['reporter'],
                                'labels': referenced_ticket['labels'],
                                'references': referenced_ticket['references']
                            })
                            self._update_stats('jira', depth)
                    else:
                        # Add placeholder reference for already processed tickets
                        if linked_issue['key'] in self.processed_ids:
                            ticket_data['references']['jira_tickets'].append(
                                self._create_ticket_reference(linked_issue['key'], parent_id)
                            )
                
                except Exception as e:
                    logger.error(f"Failed to process linked ticket {linked_issue['key']}: {str(e)}")
                    ticket_data['references']['jira_tickets'].append({
                        'id': linked_issue['key'],
                        'url': url,
                        'context': f"Direct issue link ({link_type})",
                        'metadata': url_data,
                        'error': str(e)
                    })
                
                self._memory_manager.check_memory()

    def _check_duplicate_reference(self, references: Dict[str, List[Dict[str, Any]]], ref_type: str, item: Dict[str, Any]) -> bool:
        """Check if a reference already exists in the references list."""
        if ref_type == 'jira_tickets':
            return any(ref.get('ticket_id') == item.get('ticket_id') for ref in references[ref_type])
        elif ref_type == 'confluence_pages':
            return any(ref.get('page_id') == item.get('page_id') for ref in references[ref_type])
        else:
            return any(ref.get('url') == item.get('url') for ref in references[ref_type])

    @memory_managed("process_content_references")
    async def _process_content_references(
        self,
        content: str,
        source_id: str,
        source_type: str,
        depth: int,
        references: Dict[str, List[Dict[str, Any]]],
        author: str = None
    ) -> None:
        """Process content references with memory management."""
        try:
            # Analyze URLs in content
            urls = await self.url_analyzer.analyze_content(content, source_id)

            # Process each URL match
            for url_match in urls:
                try:
                    if url_match.url_type == 'jira':
                        # Extract ticket ID from URL
                        ticket_id = url_match.resource_metadata.resource_id if url_match.resource_metadata else None
                        if ticket_id:
                            # Skip self-references
                            if ticket_id == source_id:
                                continue

                            # Add to references if not already present
                            if not any(ref.get('ticket_id') == ticket_id for ref in references['jira_tickets']):
                                try:
                                    ticket_data = await self._get_ticket_with_references(ticket_id, depth + 1)
                                    if ticket_data:
                                        references['jira_tickets'].append({
                                            'type': 'jira',
                                            'ticket_id': ticket_id,
                                            'context': source_type,
                                            'url': url_match.url,
                                            'data': ticket_data
                                        })
                                except Exception as e:
                                    logger.error(f"Failed to fetch ticket {ticket_id}: {str(e)}")
                                    references['jira_tickets'].append({
                                        'type': 'jira',
                                        'ticket_id': ticket_id,
                                        'context': source_type,
                                        'url': url_match.url,
                                        'error': str(e)
                                    })

                    elif url_match.url_type == 'confluence':
                        # Extract page ID from URL
                        page_id = url_match.resource_metadata.resource_id if url_match.resource_metadata else None
                        if page_id:
                            # Add to references if not already present
                            if not any(ref.get('page_id') == page_id for ref in references['confluence_pages']):
                                try:
                                    page_data = await self.confluence_extractor.get_page_from_url(url_match.url)
                                    if page_data:
                                        references['confluence_pages'].append({
                                            'type': 'confluence',
                                            'page_id': page_id,
                                            'context': source_type,
                                            'url': url_match.url,
                                            'data': page_data
                                        })
                                except Exception as e:
                                    logger.error(f"Failed to fetch Confluence page {page_id}: {str(e)}")
                                    references['confluence_pages'].append({
                                        'type': 'confluence',
                                        'page_id': page_id,
                                        'context': source_type,
                                        'url': url_match.url,
                                        'error': str(e)
                                    })

                    elif url_match.should_scrape:
                        # Add to scrapable documentation if not already present
                        if not any(ref.get('url') == url_match.url for ref in references['scrapable_documentation']):
                            try:
                                content = await self.webpage_extractor.get_page_from_url(url_match.url)
                                if content:
                                    references['scrapable_documentation'].append({
                                        'type': 'webpage',
                                        'url': url_match.url,
                                        'context': source_type,
                                        'data': content
                                    })
                            except Exception as e:
                                logger.error(f"Failed to fetch webpage {url_match.url}: {str(e)}")
                                references['scrapable_documentation'].append({
                                    'type': 'webpage',
                                    'url': url_match.url,
                                    'context': source_type,
                                    'error': str(e)
                                })

                    else:
                        # Add to other URLs if not already present
                        if not any(ref.get('url') == url_match.url for ref in references['other_urls']):
                            references['other_urls'].append({
                                'type': 'external',
                                'url': url_match.url,
                                'context': source_type
                            })

                except Exception as e:
                    logger.error(f"Failed to process URL {url_match.url}: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Failed to process content references: {str(e)}")
            raise

    def _update_stats(self, ref_type: str, depth: int) -> None:
        """Update reference statistics."""
        self.reference_stats['total_references'] += 1
        self.reference_stats['by_type'][ref_type] = self.reference_stats['by_type'].get(ref_type, 0) + 1
        self.reference_stats['by_depth'][depth] = self.reference_stats['by_depth'].get(depth, 0) + 1

    def _make_sync(self, async_func):
        """Convert an async function to sync."""
        def wrapper(*args, **kwargs):
            import asyncio
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_func(*args, **kwargs))
        return wrapper