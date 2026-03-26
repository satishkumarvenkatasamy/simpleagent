import json
import time
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse
import os

class SecurityManager:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.load_config()
        self.operation_history = []
        self.session_start_time = time.time()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('browser_automation.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self):
        """Load security configuration from JSON file"""
        try:
            # Use absolute path if config_path is relative
            if not os.path.isabs(self.config_path):
                self.config_path = os.path.join(os.path.dirname(__file__), self.config_path)
            
            print(f"Loading config from: {self.config_path}")
            print(f"Config file exists: {os.path.exists(self.config_path)}")
            
            # Read file content first for debugging
            with open(self.config_path, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                print(f"Config file size: {len(content)} characters")
                print(f"First 100 chars: {repr(content[:100])}")
                
                # Check for empty or whitespace-only file
                if not content:
                    raise ValueError("Config file is empty")
                
                config = json.loads(content)
                self.security_config = config.get('security', {})
                self.browser_config = config.get('browser_settings', {})
                print(f"Config loaded successfully: {len(self.security_config)} security settings")
                
        except FileNotFoundError:
            print(f"Config file {self.config_path} not found. Using defaults.")
            self._use_defaults()
        except json.JSONDecodeError as e:
            print(f"Invalid JSON in config file {self.config_path}: {e}")
            print(f"Error at position {e.pos if hasattr(e, 'pos') else 'unknown'}")
            self._use_defaults()
        except ValueError as e:
            print(f"Config file error: {e}")
            self._use_defaults()
        except Exception as e:
            print(f"Unexpected error loading config: {e}")
            self._use_defaults()
            
    def _use_defaults(self):
        """Set default configuration values"""
        self.security_config = {
            'allowed_domains': ['google.com', 'github.com', 'stackoverflow.com', 'wikipedia.org', 'example.com'],
            'blocked_domains': ['localhost', '127.0.0.1', '192.168.', '10.0.', '172.16.'],
            'max_operations_per_minute': 30,
            'session_timeout_minutes': 30,
            'enable_screenshots': True,
            'enable_downloads': False
        }
        self.browser_config = {
            'default_browser': 'chrome',
            'window_size': [1280, 720],
            'headless': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        print("Using default configuration values")
    
    def is_url_allowed(self, url: str) -> bool:
        """Check if URL is allowed based on whitelist/blacklist"""
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.lower()
            
            # Check blocked domains first
            blocked_domains = self.security_config.get('blocked_domains', [])
            for blocked in blocked_domains:
                if blocked.lower() in domain:
                    self.logger.warning(f"Blocked URL access attempt: {url}")
                    return False
            
            # Check allowed domains
            allowed_domains = self.security_config.get('allowed_domains', [])
            if not allowed_domains:  # If no whitelist, allow all (except blocked)
                return True
                
            for allowed in allowed_domains:
                if allowed.lower() in domain:
                    return True
            
            self.logger.warning(f"URL not in allowed domains: {url}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error validating URL {url}: {e}")
            return False
    
    def check_rate_limit(self) -> bool:
        """Check if operation rate limit is exceeded"""
        max_ops = self.security_config.get('max_operations_per_minute', 30)
        current_time = time.time()
        
        # Remove operations older than 1 minute
        self.operation_history = [
            op_time for op_time in self.operation_history 
            if current_time - op_time < 60
        ]
        
        if len(self.operation_history) >= max_ops:
            self.logger.warning("Rate limit exceeded")
            return False
        
        self.operation_history.append(current_time)
        return True
    
    def check_session_timeout(self) -> bool:
        """Check if session has timed out"""
        timeout_minutes = self.security_config.get('session_timeout_minutes', 30)
        current_time = time.time()
        
        if (current_time - self.session_start_time) > (timeout_minutes * 60):
            self.logger.warning("Session timed out")
            return True
        
        return False
    
    def log_operation(self, operation: str, details: Dict[str, Any]):
        """Log browser operation for audit trail"""
        log_entry = {
            'timestamp': time.time(),
            'operation': operation,
            'details': details
        }
        self.logger.info(f"Operation: {operation} - {details}")
    
    def validate_selector(self, selector: str) -> bool:
        """Validate CSS selector or XPath for safety"""
        # Block potentially dangerous selectors
        dangerous_patterns = [
            'javascript:',
            'data:',
            'vbscript:',
            'onload',
            'onerror',
            'onclick'
        ]
        
        selector_lower = selector.lower()
        for pattern in dangerous_patterns:
            if pattern in selector_lower:
                self.logger.warning(f"Dangerous selector blocked: {selector}")
                return False
        
        return True
    
    def can_take_screenshot(self) -> bool:
        """Check if screenshots are enabled"""
        return self.security_config.get('enable_screenshots', True)
    
    def can_download_files(self) -> bool:
        """Check if file downloads are enabled"""
        return self.security_config.get('enable_downloads', False)