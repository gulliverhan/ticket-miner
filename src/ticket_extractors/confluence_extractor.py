import os
import logging
from typing import Dict, Any, Optional, List
from atlassian import Confluence
from urllib.parse import urlparse, unquote
import json
import re
import html2text
from . import config
from .url_analyzer import URLAnalyzer
from .base_extractor import BaseExtractor

# Configure logging
logger = logging.getLogger(__name__)

class ConfluenceExtractor(BaseExtractor):
    def __init__(self):
        super().__init__()
        logger.info(f"Connecting to Confluence: {config.CONFLUENCE_URL}")
        
        try:
            self.confluence = Confluence(
                url=config.CONFLUENCE_URL,
                username=config.CONFLUENCE_USERNAME,
                password=config.CONFLUENCE_API_TOKEN
            )
            self.url_analyzer = URLAnalyzer()
        except Exception as e:
            logger.error(f"Confluence connection failed: {str(e)}")
            raise
            
        # Create sync versions of async methods
        self.get_page_from_url_sync = self._make_sync(self.get_page_from_url)

    async def get_page_from_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get a Confluence page from its URL."""
        try:
            # Extract page ID from URL
            page_id = self._extract_page_id_from_url(url)
            if not page_id:
                logger.warning(f"Could not extract page ID from URL: {url}")
                return None

            # Get the page content
            try:
                page = self.confluence.get_page_by_id(
                    page_id,
                    expand='body.storage,version,space,history,metadata.labels'
                )
            except Exception as e:
                logger.error(f"Failed to fetch Confluence page {page_id}: {str(e)}")
                return None

            if not page:
                logger.warning(f"Page not found: {page_id}")
                return None

            # Get attachments
            attachments = self._get_attachments(page_id)

            # Extract and clean the content
            content = self._clean_confluence_markup(page['body']['storage']['value'])

            return {
                'id': page['id'],
                'title': page['title'],
                'space_key': page['space']['key'],
                'content': content,
                'version': page['version']['number'],
                'created': page['history']['createdDate'],
                'updated': page['version']['when'],
                'creator': page['history']['createdBy']['displayName'],
                'last_modifier': page['version']['by']['displayName'],
                'labels': [label['name'] for label in page.get('metadata', {}).get('labels', {}).get('results', [])],
                'url': url,
                'attachments': attachments
            }

        except Exception as e:
            logger.error(f"Failed to fetch page from URL {url}: {str(e)}")
            return None

    def _extract_page_id_from_url(self, url: str) -> Optional[str]:
        """Extract the page ID from a Confluence URL."""
        try:
            parsed = urlparse(url)
            path = unquote(parsed.path)
            
            # Handle different URL patterns
            if '/pages/' in path:
                # Modern URL format: /wiki/spaces/KEY/pages/123456789
                return path.split('/pages/')[-1].split('/')[0]
            elif '/display/' in path:
                # Legacy URL format: /display/KEY/Page+Title
                # In this case, we need to get the page by title and space
                space_key = path.split('/display/')[-1].split('/')[0]
                title = path.split('/')[-1].replace('+', ' ')
                page = self.confluence.get_page_by_title(space_key, title)
                return page['id'] if page else None
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract page ID from URL {url}: {str(e)}")
            return None

    def _get_attachments(self, page_id: str) -> List[Dict[str, Any]]:
        """Get attachments for a page."""
        try:
            attachments = self.confluence.get_attachments_from_content(page_id)
            if not attachments or 'results' not in attachments:
                return []
                
            return [
                {
                    'id': attachment['id'],
                    'title': attachment['title'],
                    'filename': attachment['title'],
                    'mediaType': attachment.get('metadata', {}).get('mediaType', 'unknown'),
                    'size': attachment.get('extensions', {}).get('fileSize', 0),
                    'created': attachment['version']['when'],
                    'creator': attachment['version']['by']['displayName'],
                    'download_url': attachment['_links']['download']
                }
                for attachment in attachments['results']
            ]
        except Exception as e:
            logger.error(f"Failed to get attachments for page {page_id}: {str(e)}")
            return []

    def _clean_confluence_markup(self, content: str) -> str:
        """Clean Confluence storage format markup."""
        try:
            # Convert HTML to markdown
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_tables = False
            h.body_width = 0  # Don't wrap lines
            
            # Convert to markdown
            markdown = h.handle(content)
            
            # Clean up common issues
            markdown = re.sub(r'\n{3,}', '\n\n', markdown)  # Remove excess newlines
            markdown = markdown.strip()
            
            return markdown
            
        except Exception as e:
            logger.error(f"Failed to clean Confluence markup: {str(e)}")
            return content 