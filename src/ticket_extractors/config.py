"""Configuration module for ticket extractors."""
import os
import logging
from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlparse
from dotenv import load_dotenv

# Configure logging
logger = logging.getLogger(__name__)

class ConfigurationError(Exception):
    """Raised when there is an issue with the configuration."""
    pass

@dataclass
class JiraConfig:
    """Jira configuration settings."""
    url: str
    username: Optional[str]
    api_token: Optional[str]
    domain: str

@dataclass
class ConfluenceConfig:
    """Confluence configuration settings."""
    url: str
    username: Optional[str]
    api_token: Optional[str]
    domain: str

@dataclass
class Configuration:
    """Main configuration class."""
    base_domain: str
    jira: JiraConfig
    confluence: ConfluenceConfig
    environment: str = "production"
    log_level: str = "INFO"

def _normalize_url(url: str) -> str:
    """Normalize URL by ensuring it has https:// prefix and no trailing slash.
    
    Args:
        url: The URL to normalize
        
    Returns:
        Normalized URL
        
    Raises:
        ConfigurationError: If the URL is invalid
    """
    try:
        url = url.strip().rstrip('/')
        url = url.replace('https://', '')  # Remove any existing https:// prefix
        normalized = f"https://{url}"
        # Validate the URL
        parsed = urlparse(normalized)
        if not all([parsed.scheme, parsed.netloc]):
            raise ValueError("Invalid URL format")
        return normalized
    except Exception as e:
        raise ConfigurationError(f"Invalid URL format: {url}") from e

def _validate_domain(domain: str) -> None:
    """Validate a domain string.
    
    Args:
        domain: Domain to validate
        
    Raises:
        ConfigurationError: If the domain is invalid
    """
    if not domain or '.' not in domain:
        raise ConfigurationError(f"Invalid domain format: {domain}")

def load_config() -> Configuration:
    """Load and validate configuration from environment variables.
    
    Returns:
        Configuration object
        
    Raises:
        ConfigurationError: If required configuration is missing or invalid
    """
    # Load environment variables
    load_dotenv()
    
    # Get environment
    env = os.getenv('ENVIRONMENT', 'production').lower()
    if env not in ['development', 'staging', 'production']:
        logger.warning(f"Invalid environment '{env}', defaulting to 'production'")
        env = 'production'
    
    # Get and validate base domain
    base_domain = os.getenv('BASE_DOMAIN', 'example.com')
    try:
        _validate_domain(base_domain)
    except ConfigurationError as e:
        logger.error(f"Invalid BASE_DOMAIN: {e}")
        base_domain = 'example.com'
    
    # Configure logging
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    if log_level not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        logger.warning(f"Invalid log level '{log_level}', defaulting to 'INFO'")
        log_level = 'INFO'
    
    try:
        # Load Jira configuration
        jira_url = _normalize_url(os.getenv('JIRA_URL', f'https://jira.{base_domain}'))
        jira_config = JiraConfig(
            url=jira_url,
            username=os.getenv('JIRA_USERNAME'),
            api_token=os.getenv('JIRA_API_TOKEN'),
            domain=urlparse(jira_url).netloc
        )
        
        # Load Confluence configuration
        confluence_url = _normalize_url(os.getenv('CONFLUENCE_URL', f'https://confluence.{base_domain}'))
        confluence_config = ConfluenceConfig(
            url=confluence_url,
            username=os.getenv('CONFLUENCE_USERNAME'),
            api_token=os.getenv('CONFLUENCE_API_TOKEN'),
            domain=urlparse(confluence_url).netloc
        )
        
        # Create configuration object
        config = Configuration(
            base_domain=base_domain,
            jira=jira_config,
            confluence=confluence_config,
            environment=env,
            log_level=log_level
        )
        
        # Validate credentials in non-development environments
        if env != 'development':
            if not all([config.jira.username, config.jira.api_token]):
                raise ConfigurationError("Jira credentials are required in non-development environments")
            if not all([config.confluence.username, config.confluence.api_token]):
                raise ConfigurationError("Confluence credentials are required in non-development environments")
        
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {str(e)}")
        raise ConfigurationError("Failed to load configuration") from e

# Load configuration
try:
    config = load_config()
    
    # Export commonly used values
    BASE_DOMAIN = config.base_domain
    JIRA_URL = config.jira.url
    JIRA_USERNAME = config.jira.username
    JIRA_API_TOKEN = config.jira.api_token
    JIRA_DOMAIN = config.jira.domain
    CONFLUENCE_URL = config.confluence.url
    CONFLUENCE_USERNAME = config.confluence.username
    CONFLUENCE_API_TOKEN = config.confluence.api_token
    CONFLUENCE_DOMAIN = config.confluence.domain
    
except ConfigurationError as e:
    logger.error(f"Configuration error: {str(e)}")
    raise 