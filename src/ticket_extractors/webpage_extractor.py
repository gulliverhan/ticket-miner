import os
import logging
from typing import Dict, Any, Optional
from playwright.async_api import async_playwright
import html2text
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import json
from datetime import datetime
from .base_extractor import BaseExtractor

# Configure logging
logger = logging.getLogger(__name__)

class WebPageExtractor(BaseExtractor):
    def __init__(self):
        super().__init__()
        self.h = html2text.HTML2Text()
        self.h.ignore_links = False
        self.h.ignore_images = False
        self.h.ignore_tables = False
        self.h.body_width = 0  # Don't wrap lines
        
        # Create sync versions of async methods
        self.get_page_from_url_sync = self._make_sync(self.get_page_from_url)
        self._fetch_page_content_sync = self._make_sync(self._fetch_page_content)

    async def _fetch_page_content(self, url: str) -> Optional[str]:
        """
        Fetch raw page content using Playwright.
        
        Args:
            url: The URL to fetch
            
        Returns:
            Raw HTML content or None if failed
        """
        try:
            async with async_playwright() as p:
                # Launch browser with specific options for reliability
                browser = await p.chromium.launch(
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-notifications',
                        '--disable-geolocation',
                        '--disable-infobars',
                        '--disable-web-security',
                        '--disable-features=IsolateOrigins,site-per-process',
                        '--disable-site-isolation-trials'
                    ]
                )
                
                # Create a new page with viewport settings and block trackers
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 1024},
                    bypass_csp=True,
                    java_script_enabled=True,
                    accept_downloads=False,
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'DNT': '1'  # Do Not Track
                    }
                )
                
                # Add cookie to bypass consent
                await context.add_cookies([{
                    'name': 'CookieConsent',
                    'value': 'true',
                    'domain': '.criteo.com',
                    'path': '/'
                }])
                
                page = await context.new_page()
                
                # Set default timeout for all operations
                page.set_default_timeout(30000)  # 30 second timeout
                
                logger.info(f"Fetching page: {url}")
                
                # Go to URL and wait for content to load
                await page.goto(url, wait_until='networkidle')
                
                # Wait for any dynamic content to load
                await page.wait_for_timeout(2000)  # 2 second wait for dynamic content
                
                # Get page content
                content = await page.content()
                
                # Close browser
                await browser.close()
                
                return content
                
        except Exception as e:
            logger.error(f"Failed to fetch page {url}: {str(e)}")
            return None

    async def get_page_from_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch and extract content from a web page.
        
        Args:
            url: The URL to fetch
            
        Returns:
            Dict containing the page data or None if failed
        """
        try:
            # Validate URL
            parsed_url = urlparse(url)
            if not all([parsed_url.scheme, parsed_url.netloc]):
                logger.error(f"Invalid URL: {url}")
                return None

            # Fetch page content
            content = await self._fetch_page_content(url)
            if not content:
                return None

            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract metadata
            title = self._extract_title(soup)
            description = self._extract_description(soup)
            author = self._extract_author(soup)
            date = self._extract_date(soup)
            
            # Clean content
            cleaned_content = self._clean_content(soup)
            
            # Create page data
            page_data = {
                'url': url,
                'title': title,
                'description': description,
                'author': author,
                'date': date,
                'content': cleaned_content,
                'metadata': {
                    'url': url,
                    'domain': parsed_url.netloc,
                    'extracted_at': datetime.now().isoformat(),
                    'content_type': 'documentation'
                }
            }
            
            return page_data
                
        except Exception as e:
            logger.error(f"Failed to process page {url}: {str(e)}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title."""
        # Try page title first
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            if title:
                return title

        # Try article title
        article_title = soup.find('article', {'class': ['article', 'post']})
        if article_title:
            title_elem = article_title.find(['h1', 'h2'])
            if title_elem:
                return title_elem.get_text(strip=True)
        
        # Try main heading
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)
        
        return "Untitled Page"

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page description."""
        # Try meta description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')
        
        # Try article description/summary
        article_desc = soup.find(['div', 'p'], {'class': ['description', 'summary', 'excerpt']})
        if article_desc:
            return article_desc.get_text(strip=True)
        
        # Try first paragraph
        first_p = soup.find('p')
        if first_p:
            return first_p.get_text(strip=True)
        
        return None

    def _extract_author(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract author information."""
        # Try meta author
        meta_author = soup.find('meta', {'name': 'author'})
        if meta_author:
            return meta_author.get('content', '')
        
        # Try article author
        author_elem = soup.find(['span', 'div', 'p'], {'class': ['author', 'byline']})
        if author_elem:
            return author_elem.get_text(strip=True)
        
        return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract publication/update date."""
        # Try meta date
        meta_date = soup.find('meta', {'property': ['article:published_time', 'article:modified_time']})
        if meta_date:
            return meta_date.get('content', '')
        
        # Try time element
        time_elem = soup.find('time')
        if time_elem:
            return time_elem.get('datetime', time_elem.get_text(strip=True))
        
        # Try date class
        date_elem = soup.find(['span', 'div', 'p'], {'class': ['date', 'published', 'updated']})
        if date_elem:
            return date_elem.get_text(strip=True)
        
        return None

    def _clean_content(self, soup: BeautifulSoup) -> str:
        """Clean and extract main content."""
        # Remove unwanted elements
        for elem in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            elem.decompose()
        
        # Try to find main content
        main_content = None
        
        # Try article element
        article = soup.find('article')
        if article:
            main_content = article
        
        # Try main element
        if not main_content:
            main = soup.find('main')
            if main:
                main_content = main
        
        # Try content div
        if not main_content:
            content_div = soup.find(['div', 'section'], {'class': ['content', 'article', 'post']})
            if content_div:
                main_content = content_div
        
        # Fall back to body
        if not main_content:
            main_content = soup.find('body')
        
        # Convert to markdown
        if main_content:
            return self.h.handle(str(main_content))
        
        return self.h.handle(str(soup)) 