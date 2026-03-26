#!/usr/bin/env python3
"""
Windows Browser Control MCP Server
Provides secure browser automation capabilities through MCP protocol
"""

import json
import asyncio
import traceback
import logging
import functools
from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from .browser_manager import BrowserManager

# Setup comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mcp_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def safe_tool_execution(func):
    """Decorator to safely execute tool functions and prevent server crashes"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            logger.info(f"Executing tool: {func.__name__} with args: {args}, kwargs: {kwargs}")
            result = func(*args, **kwargs)
            logger.info(f"Tool {func.__name__} completed successfully")
            return result
        except Exception as e:
            error_msg = f"Error in {func.__name__}: {str(e)}"
            logger.error(f"{error_msg}\nTraceback: {traceback.format_exc()}")
            return f"❌ {error_msg}"
    return wrapper

# Initialize FastMCP server
mcp = FastMCP("windows-browser", host="0.0.0.0", port=8000)

# Global browser manager instance with error handling
try:
    browser_manager = BrowserManager()
    logger.info("Browser manager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize browser manager: {e}")
    browser_manager = None

def ensure_browser_manager():
    """Ensure browser manager is available"""
    global browser_manager
    if browser_manager is None:
        try:
            browser_manager = BrowserManager()
            logger.info("Browser manager re-initialized")
        except Exception as e:
            logger.error(f"Failed to re-initialize browser manager: {e}")
            raise Exception("Browser manager initialization failed")
    return browser_manager

# Core Browser Control Tools

@mcp.tool()
@safe_tool_execution
def launch_browser(browser_type: str = "chrome", headless: bool = False) -> str:
    """
    Launch Chrome or Firefox browser with security settings.
    
    Args:
        browser_type: Browser to launch ("chrome" or "firefox")
        headless: Run browser in headless mode (default: False)
        
    Returns:
        Status message indicating success or failure
    """
    manager = ensure_browser_manager()
    return manager.launch_browser(browser_type, headless)

@mcp.tool()
@safe_tool_execution
def close_browser() -> str:
    """
    Close the browser and clean up resources.
    
    Returns:
        Status message indicating success or failure
    """
    return browser_manager.close_browser()

@mcp.tool()
@safe_tool_execution
def navigate_to(url: str) -> str:
    """
    Navigate to the specified URL.
    
    Args:
        url: The URL to navigate to
        
    Returns:
        Status message indicating success or failure
    """
    return browser_manager.navigate_to(url)

@mcp.tool()
def get_current_url() -> str:
    """
    Get the current page URL.
    
    Returns:
        Current URL or error message
    """
    return browser_manager.get_current_url()

@mcp.tool()
def get_page_title() -> str:
    """
    Get the current page title.
    
    Returns:
        Page title or error message
    """
    return browser_manager.get_page_title()

@mcp.tool()
def go_back() -> str:
    """
    Navigate back in browser history.
    
    Returns:
        Status message indicating success or failure
    """
    return browser_manager.go_back()

@mcp.tool()
def go_forward() -> str:
    """
    Navigate forward in browser history.
    
    Returns:
        Status message indicating success or failure
    """
    return browser_manager.go_forward()

@mcp.tool()
def refresh_page() -> str:
    """
    Refresh the current page.
    
    Returns:
        Status message indicating success or failure
    """
    return browser_manager.refresh_page()

@mcp.tool()
@safe_tool_execution
def take_screenshot(filename: Optional[str] = None) -> str:
    """
    Take a screenshot of the current page.
    
    Args:
        filename: Optional filename for the screenshot
        
    Returns:
        Status message with filename or error message
    """
    return browser_manager.take_screenshot(filename)

# Element Interaction Tools

@mcp.tool()
def click_element(selector: str, by_type: str = "css") -> str:
    """
    Click on an element specified by selector.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        
    Returns:
        Status message indicating success or failure
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        if not browser_manager.security.check_rate_limit():
            return "Rate limit exceeded"
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        
        element.click()
        browser_manager.security.log_operation("click_element", {"selector": selector, "by_type": by_type})
        return f"Successfully clicked element: {selector}"
        
    except Exception as e:
        return f"Error clicking element: {str(e)}"

@mcp.tool()
def type_text(selector: str, text: str, by_type: str = "css", clear_first: bool = True) -> str:
    """
    Type text into an input field.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        text: Text to type
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        clear_first: Clear field before typing (default: True)
        
    Returns:
        Status message indicating success or failure
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        if not browser_manager.security.check_rate_limit():
            return "Rate limit exceeded"
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        
        if clear_first:
            element.clear()
        
        element.send_keys(text)
        browser_manager.security.log_operation("type_text", {
            "selector": selector, 
            "by_type": by_type, 
            "text_length": len(text)
        })
        return f"Successfully typed text into element: {selector}"
        
    except Exception as e:
        return f"Error typing text: {str(e)}"

@mcp.tool()
def select_dropdown(selector: str, value: str, by_type: str = "css", select_by: str = "value") -> str:
    """
    Select option from dropdown menu.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        value: Value to select
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        select_by: How to select ("value", "text", "index")
        
    Returns:
        Status message indicating success or failure
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        if not browser_manager.security.check_rate_limit():
            return "Rate limit exceeded"
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        
        from selenium.webdriver.support.ui import Select
        select = Select(element)
        
        if select_by == "value":
            select.select_by_value(value)
        elif select_by == "text":
            select.select_by_visible_text(value)
        elif select_by == "index":
            select.select_by_index(int(value))
        else:
            return f"Invalid select_by parameter: {select_by}"
        
        browser_manager.security.log_operation("select_dropdown", {
            "selector": selector, 
            "value": value, 
            "select_by": select_by
        })
        return f"Successfully selected '{value}' from dropdown: {selector}"
        
    except Exception as e:
        return f"Error selecting dropdown: {str(e)}"

@mcp.tool()
def submit_form(selector: str, by_type: str = "css") -> str:
    """
    Submit a form.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name for form
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        
    Returns:
        Status message indicating success or failure
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        if not browser_manager.security.check_rate_limit():
            return "Rate limit exceeded"
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Form not found: {selector}"
        
        element.submit()
        browser_manager.security.log_operation("submit_form", {"selector": selector, "by_type": by_type})
        return f"Successfully submitted form: {selector}"
        
    except Exception as e:
        return f"Error submitting form: {str(e)}"

# Data Extraction Tools

@mcp.tool()
@safe_tool_execution
def get_element_text(selector: str, by_type: str = "css") -> str:
    """
    Get text content from an element.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        
    Returns:
        Element text or error message
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        
        text = element.text
        browser_manager.security.log_operation("get_element_text", {"selector": selector, "by_type": by_type})
        return text
        
    except Exception as e:
        return f"Error getting element text: {str(e)}"

@mcp.tool()
def get_element_attribute(selector: str, attribute: str, by_type: str = "css") -> str:
    """
    Get attribute value from an element.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        attribute: Attribute name to get
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        
    Returns:
        Attribute value or error message
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        element = browser_manager.find_element(selector, by_type)
        if not element:
            return f"Element not found: {selector}"
        
        attr_value = element.get_attribute(attribute)
        browser_manager.security.log_operation("get_element_attribute", {
            "selector": selector, 
            "attribute": attribute, 
            "by_type": by_type
        })
        return attr_value or ""
        
    except Exception as e:
        return f"Error getting element attribute: {str(e)}"

@mcp.tool()
def get_page_source() -> str:
    """
    Get the complete HTML source of the current page.
    
    Returns:
        HTML source or error message
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        source = browser_manager.driver.page_source
        browser_manager.security.log_operation("get_page_source", {"source_length": len(source)})
        return source
        
    except Exception as e:
        return f"Error getting page source: {str(e)}"

@mcp.tool()
@safe_tool_execution
def check_element_exists(selector: str, by_type: str = "css") -> bool:
    """
    Check if an element exists on the page.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        
    Returns:
        True if element exists, False otherwise
    """
    try:
        if not browser_manager.driver:
            return False
        
        element = browser_manager.find_element(selector, by_type)
        exists = element is not None
        browser_manager.security.log_operation("check_element_exists", {
            "selector": selector, 
            "exists": exists
        })
        return exists
        
    except Exception as e:
        return False

@mcp.tool()
def wait_for_element(selector: str, by_type: str = "css", timeout: int = 10) -> bool:
    """
    Wait for an element to be present on the page.
    
    Args:
        selector: CSS selector, XPath, ID, name, or class name
        by_type: Type of selector ("css", "xpath", "id", "name", "class")
        timeout: Maximum time to wait in seconds
        
    Returns:
        True if element appeared, False if timeout
    """
    try:
        if not browser_manager.driver:
            return False
        
        result = browser_manager.wait_for_element(selector, by_type, timeout)
        browser_manager.security.log_operation("wait_for_element", {
            "selector": selector, 
            "timeout": timeout, 
            "found": result
        })
        return result
        
    except Exception as e:
        return False

# Cookie Management Tools

@mcp.tool()
def get_cookies() -> str:
    """
    Get all cookies from the current domain.
    
    Returns:
        JSON string of cookies or error message
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        cookies = browser_manager.driver.get_cookies()
        browser_manager.security.log_operation("get_cookies", {"cookie_count": len(cookies)})
        return json.dumps(cookies, indent=2)
        
    except Exception as e:
        return f"Error getting cookies: {str(e)}"

@mcp.tool()
def set_cookie(name: str, value: str, domain: Optional[str] = None) -> str:
    """
    Set a cookie.
    
    Args:
        name: Cookie name
        value: Cookie value
        domain: Cookie domain (optional)
        
    Returns:
        Status message indicating success or failure
    """
    try:
        if not browser_manager.driver:
            return "No browser is running. Launch browser first."
        
        cookie_dict = {"name": name, "value": value}
        if domain:
            cookie_dict["domain"] = domain
        
        browser_manager.driver.add_cookie(cookie_dict)
        browser_manager.security.log_operation("set_cookie", {"name": name, "domain": domain})
        return f"Successfully set cookie: {name}"
        
    except Exception as e:
        return f"Error setting cookie: {str(e)}"

# Status and Information Tools

@mcp.tool()
def get_browser_status() -> str:
    """
    Get current browser status and session information.
    
    Returns:
        JSON string with browser status information
    """
    try:
        status = {
            "browser_running": browser_manager.driver is not None,
            "browser_type": browser_manager.browser_type,
            "session_active": browser_manager.session_active,
            "current_url": browser_manager.get_current_url() if browser_manager.driver else None,
            "page_title": browser_manager.get_page_title() if browser_manager.driver else None,
            "security_settings": {
                "allowed_domains": browser_manager.security.security_config.get('allowed_domains', []),
                "screenshots_enabled": browser_manager.security.can_take_screenshot(),
                "downloads_enabled": browser_manager.security.can_download_files()
            }
        }
        
        return json.dumps(status, indent=2)
        
    except Exception as e:
        return f"Error getting browser status: {str(e)}"

# Resources for configuration and help

@mcp.resource("browser://config")
def get_browser_config() -> str:
    """
    Get current browser configuration.
    
    Returns:
        Current configuration as markdown
    """
    try:
        with open("config.json", 'r') as f:
            config = json.load(f)
        
        content = "# Browser Configuration\n\n"
        content += "## Security Settings\n\n"
        
        security = config.get('security', {})
        content += f"- **Allowed Domains**: {', '.join(security.get('allowed_domains', []))}\n"
        content += f"- **Max Operations/Minute**: {security.get('max_operations_per_minute', 30)}\n"
        content += f"- **Session Timeout**: {security.get('session_timeout_minutes', 30)} minutes\n"
        content += f"- **Screenshots Enabled**: {security.get('enable_screenshots', True)}\n"
        content += f"- **Downloads Enabled**: {security.get('enable_downloads', False)}\n\n"
        
        content += "## Browser Settings\n\n"
        browser_settings = config.get('browser_settings', {})
        content += f"- **Default Browser**: {browser_settings.get('default_browser', 'chrome')}\n"
        content += f"- **Window Size**: {browser_settings.get('window_size', [1280, 720])}\n"
        content += f"- **Headless Mode**: {browser_settings.get('headless', False)}\n"
        
        return content
        
    except Exception as e:
        return f"Error reading configuration: {str(e)}"

@mcp.resource("browser://help")
def get_help() -> str:
    """
    Get help documentation for browser automation tools.
    
    Returns:
        Help documentation as markdown
    """
    return """# Windows Browser Control MCP Server

## Available Tools

### Browser Control
- `launch_browser(browser_type, headless)` - Launch Chrome or Firefox
- `close_browser()` - Close browser and cleanup
- `navigate_to(url)` - Navigate to URL
- `go_back()` - Browser back button
- `go_forward()` - Browser forward button
- `refresh_page()` - Refresh current page
- `take_screenshot(filename)` - Take page screenshot

### Element Interaction
- `click_element(selector, by_type)` - Click on element
- `type_text(selector, text, by_type, clear_first)` - Type text into field
- `select_dropdown(selector, value, by_type, select_by)` - Select dropdown option
- `submit_form(selector, by_type)` - Submit form

### Data Extraction
- `get_element_text(selector, by_type)` - Get element text
- `get_element_attribute(selector, attribute, by_type)` - Get element attribute
- `get_page_source()` - Get full HTML source
- `get_current_url()` - Get current URL
- `get_page_title()` - Get page title

### Element Utilities
- `check_element_exists(selector, by_type)` - Check if element exists
- `wait_for_element(selector, by_type, timeout)` - Wait for element

### Cookie Management
- `get_cookies()` - Get all cookies
- `set_cookie(name, value, domain)` - Set cookie

### Status
- `get_browser_status()` - Get browser and session status

## Selector Types
- `css` - CSS selectors (default)
- `xpath` - XPath expressions
- `id` - Element ID
- `name` - Element name attribute
- `class` - Element class name

## Security Features
- URL whitelisting/blacklisting
- Rate limiting
- Session timeouts
- Operation logging
- Safe element selector validation

## Usage Example
1. `launch_browser("chrome")`
2. `navigate_to("https://example.com")`
3. `click_element("#submit-button", "css")`
4. `take_screenshot()`
5. `close_browser()`
"""

async def handle_server_error(exc, context):
    """Global error handler for the MCP server"""
    logger.error(f"Server error: {exc}")
    logger.error(f"Context: {context}")
    logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    import argparse
    import signal
    import sys
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal, cleaning up...")
        try:
            if browser_manager and browser_manager.driver:
                browser_manager.close_browser()
                logger.info("Browser closed during shutdown")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description='Windows Browser MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse'], default='stdio',
                       help='Transport protocol (stdio for local, sse for remote)')
    
    args = parser.parse_args()
    
    try:
        if args.transport == 'sse':
            logger.info("Starting MCP server with SSE transport on 0.0.0.0:8000")
            print("Starting MCP server with SSE transport")
            print("⚠️  Note: SSE transport configuration depends on FastMCP implementation")
            print("⚠️  For remote access, you may need additional configuration")
            mcp.run(transport='sse')
        else:
            logger.info("Starting MCP server with stdio transport (local only)")
            print("Starting MCP server with stdio transport (local only)")
            mcp.run(transport='stdio')
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)
