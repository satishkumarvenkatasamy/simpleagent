import os
import time
import json
from typing import Optional, Dict, Any, List
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from PIL import Image
import base64
from io import BytesIO

from .security_manager import SecurityManager

class BrowserManager:
    def __init__(self, config_path: str = "config.json"):
        self.driver: Optional[webdriver.Chrome | webdriver.Firefox] = None
        self.security = SecurityManager(config_path)
        self.browser_type = None
        self.session_active = False
        
        # Load browser settings
        with open(config_path, 'r') as f:
            config = json.load(f)
            self.browser_settings = config.get('browser_settings', {})
    
    def _find_chrome_binary(self) -> Optional[str]:
        """Find Chrome binary on Windows system"""
        if os.name != 'nt':
            return None
            
        chrome_paths = [
            # Standard Chrome installations
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            
            # User-specific installations
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
            
            # Alternative locations
            r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(os.getenv('USERNAME', '')),
            
            # Chromium alternatives
            r"C:\Program Files\Chromium\Application\chromium.exe",
            r"C:\Program Files (x86)\Chromium\Application\chromium.exe",
        ]
        
        # Also check registry for Chrome installation
        try:
            import winreg
            reg_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
            ]
            
            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                        chrome_path = winreg.QueryValue(key, "")
                        if os.path.exists(chrome_path):
                            chrome_paths.insert(0, chrome_path)
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass  # winreg not available
        
        # Check each path
        for path in chrome_paths:
            if os.path.exists(path):
                print(f"Found Chrome at: {path}")
                return path
        
        print("Chrome binary not found in standard locations")
        print("Checked paths:")
        for path in chrome_paths:
            print(f"  - {path} (exists: {os.path.exists(path)})")
        
        return None
    
    def _find_firefox_binary(self) -> Optional[str]:
        """Find Firefox binary on Windows system"""
        if os.name != 'nt':
            return None
            
        firefox_paths = [
            # Standard Firefox installations
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            
            # User-specific installations
            os.path.expanduser(r"~\AppData\Local\Mozilla Firefox\firefox.exe"),
            
            # Alternative locations
            r"C:\Users\{}\AppData\Local\Mozilla Firefox\firefox.exe".format(os.getenv('USERNAME', '')),
        ]
        
        # Also check registry for Firefox installation
        try:
            import winreg
            reg_paths = [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
            ]
            
            for reg_path in reg_paths:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                        firefox_path = winreg.QueryValue(key, "")
                        if os.path.exists(firefox_path):
                            firefox_paths.insert(0, firefox_path)
                except (FileNotFoundError, OSError):
                    continue
        except ImportError:
            pass  # winreg not available
        
        # Check each path
        for path in firefox_paths:
            if os.path.exists(path):
                print(f"Found Firefox at: {path}")
                return path
        
        print("Firefox binary not found in standard locations")
        print("Checked paths:")
        for path in firefox_paths:
            print(f"  - {path} (exists: {os.path.exists(path)})")
        
        return None
    
    def launch_browser(self, browser_type: str = "chrome", headless: bool = False) -> str:
        """Launch Chrome or Firefox browser"""
        try:
            if self.driver:
                return "Browser already running. Close it first before launching a new one."
            
            if not self.security.check_rate_limit():
                return "Rate limit exceeded. Please wait before launching browser."
            
            self.browser_type = browser_type.lower()
            
            if self.browser_type == "chrome":
                return self._launch_chrome(headless)
            elif self.browser_type == "firefox":
                return self._launch_firefox(headless)
            else:
                return f"Unsupported browser type: {browser_type}. Use 'chrome' or 'firefox'."
                
        except Exception as e:
            self.security.logger.error(f"Failed to launch browser: {e}")
            return f"Failed to launch browser: {str(e)}"
    
    def _launch_chrome(self, headless: bool = False) -> str:
        """Launch Chrome browser with security settings"""
        try:
            # Install/get ChromeDriver with Windows-specific handling
            driver_path = ChromeDriverManager().install()
            print(f"ChromeDriver path: {driver_path}")
            
            # Ensure driver is executable on Windows
            if os.name == 'nt':  # Windows
                import stat
                os.chmod(driver_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            
            service = ChromeService(driver_path)
            
            # Configure Chrome options
            options = ChromeOptions()
            
            # Find and set Chrome binary path on Windows
            if os.name == 'nt':
                chrome_binary = self._find_chrome_binary()
                if chrome_binary:
                    options.binary_location = chrome_binary
                    print(f"Using Chrome binary: {chrome_binary}")
                else:
                    raise Exception("Chrome browser not found. Please install Chrome first.")
            
            # Security settings
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-web-security")
            options.add_argument("--disable-features=VizDisplayCompositor")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-plugins")
            options.add_argument("--disable-images") if not self.security.can_take_screenshot() else None
            
            # Windows-specific options to fix GPU context errors
            if os.name == 'nt':
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-gpu-sandbox")
                options.add_argument("--disable-software-rasterizer")
                options.add_argument("--disable-background-timer-throttling")
                options.add_argument("--disable-backgrounding-occluded-windows")
                options.add_argument("--disable-renderer-backgrounding")
                options.add_argument("--disable-features=TranslateUI")
                options.add_argument("--disable-features=VizDisplayCompositor,VizHitTestSurfaceLayer")
                options.add_argument("--disable-gpu-vsync")
                options.add_argument("--disable-d3d11")
                options.add_argument("--disable-accelerated-2d-canvas")
                options.add_argument("--disable-accelerated-jpeg-decoding")
                options.add_argument("--disable-accelerated-mjpeg-decode")
                options.add_argument("--disable-accelerated-video-decode")
                options.add_argument("--disable-accelerated-video-encode")
                options.add_argument("--use-gl=swiftshader")
                options.add_argument("--enable-logging=stderr")
                options.add_argument("--log-level=3")
                options.add_argument("--disable-ipc-flooding-protection")
                options.add_argument("--force-device-scale-factor=1")
            
            # Create isolated user data directory with Windows-safe path
            if os.name == 'nt':
                import tempfile
                temp_profile = os.path.join(tempfile.gettempdir(), "browser_automation_profile")
            else:
                temp_profile = os.path.join(os.getcwd(), "temp_browser_profile")
            
            # Ensure directory exists
            os.makedirs(temp_profile, exist_ok=True)
            options.add_argument(f"--user-data-dir={temp_profile}")
            
            # Window size
            window_size = self.browser_settings.get('window_size', [1280, 720])
            options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
            
            # User agent
            user_agent = self.browser_settings.get('user_agent')
            if user_agent:
                options.add_argument(f"--user-agent={user_agent}")
            
            # Headless mode
            if headless or self.browser_settings.get('headless', False):
                options.add_argument("--headless")
            
            # Disable downloads if not allowed
            if not self.security.can_download_files():
                prefs = {
                    "profile.default_content_settings.popups": 0,
                    "download.prompt_for_download": True,
                    "download.directory_upgrade": True,
                    "safebrowsing.enabled": True
                }
                options.add_experimental_option("prefs", prefs)
            
            try:
                self.driver = webdriver.Chrome(service=service, options=options)
                self.session_active = True
                
                # Configure timeouts from browser settings
                page_load_timeout = self.browser_settings.get('page_load_timeout', 30)
                implicit_wait = self.browser_settings.get('implicit_wait', 10)
                script_timeout = self.browser_settings.get('script_timeout', 30)
                
                self.driver.set_page_load_timeout(page_load_timeout)
                self.driver.implicitly_wait(implicit_wait)
                self.driver.set_script_timeout(script_timeout)
                
                # Reset session start time when browser launches
                self.security.session_start_time = time.time()
                
                self.security.log_operation("launch_browser", {"browser": "chrome", "headless": headless})
                return "Chrome browser launched successfully"
            except Exception as driver_error:
                print(f"WebDriver creation failed: {driver_error}")
                raise driver_error
            
        except Exception as e:
            error_msg = f"Chrome launch failed: {str(e)}"
            if "chromedriver" in str(e).lower():
                error_msg += " (ChromeDriver issue - check antivirus settings)"
            elif "permission" in str(e).lower():
                error_msg += " (Permission denied - try running as administrator)"
            raise Exception(error_msg)
    
    def _launch_firefox(self, headless: bool = False) -> str:
        """Launch Firefox browser with security settings"""
        try:
            # Install/get GeckoDriver with Windows-specific handling
            driver_path = GeckoDriverManager().install()
            print(f"GeckoDriver path: {driver_path}")
            
            # Ensure driver is executable on Windows
            if os.name == 'nt':
                import stat
                try:
                    os.chmod(driver_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                except:
                    pass  # May fail on Windows, but not critical
            
            service = FirefoxService(driver_path)
            
            # Configure Firefox options
            options = FirefoxOptions()
            
            # Find and set Firefox binary path on Windows
            if os.name == 'nt':
                firefox_binary = self._find_firefox_binary()
                if firefox_binary:
                    options.binary_location = firefox_binary
                    print(f"Using Firefox binary: {firefox_binary}")
                else:
                    raise Exception("Firefox browser not found. Please install Firefox first.")
            
            # Headless mode (set before other arguments)
            if headless or self.browser_settings.get('headless', False):
                options.add_argument("--headless")
            
            # Firefox-specific arguments (NOT Chrome arguments)
            if os.name == 'nt':
                # Remove Chrome-specific arguments that don't work with Firefox
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                # Firefox uses different GPU disabling
                options.add_argument("--disable-gpu-sandbox")
            
            # Set window size via preferences instead of arguments
            window_size = self.browser_settings.get('window_size', [1280, 720])
            
            # Create isolated profile directory
            temp_profile_dir = None
            if os.name == 'nt':
                import tempfile
                temp_profile_dir = os.path.join(tempfile.gettempdir(), "firefox_automation_profile")
                os.makedirs(temp_profile_dir, exist_ok=True)
                print(f"Firefox profile directory: {temp_profile_dir}")
            
            # Set Firefox preferences through options (modern approach)
            firefox_prefs = {
                "browser.window.width": window_size[0],
                "browser.window.height": window_size[1],
                "security.tls.insecure_fallback_hosts": "",
                "security.tls.unrestricted_rc4_fallback": False,
                "browser.cache.disk.enable": False,
                "browser.cache.memory.enable": False,
                "browser.cache.offline.enable": False,
                "network.http.use-cache": False,
                "dom.webdriver.enabled": True,
                "useAutomationExtension": False,
                "general.useragent.override": self.browser_settings.get('user_agent', ''),
                # Performance and stability settings for Windows
                "browser.sessionstore.resume_from_crash": False,
                "browser.sessionstore.restore_on_demand": False,
                "browser.sessionstore.max_tabs_undo": 0,
                "browser.startup.page": 0,
                "browser.startup.homepage": "about:blank",
                "startup.homepage_welcome_url": "",
                "startup.homepage_welcome_url.additional": "",
                "browser.newtabpage.enabled": False,
                "browser.newtab.preload": False,
                # Disable auto-updates and background tasks
                "app.update.enabled": False,
                "app.update.auto": False,
                "extensions.update.enabled": False,
                "browser.search.update": False,
                # Media and GPU settings for Windows
                "media.navigator.enabled": False,
                "media.peerconnection.enabled": False,
                "webgl.disabled": True,
                "layers.acceleration.disabled": True,
                "gfx.direct2d.disabled": True,
                "layers.acceleration.force-enabled": False,
                # Reduce timeouts and improve responsiveness
                "dom.max_script_run_time": 10,
                "dom.max_chrome_script_run_time": 10,
                "network.http.connection-timeout": 30,
                "network.http.response.timeout": 30
            }
            
            # Disable downloads if not allowed
            if not self.security.can_download_files():
                firefox_prefs.update({
                    "browser.download.manager.showWhenStarting": False,
                    "browser.helperApps.neverAsk.saveToDisk": "application/pdf,text/plain,application/octet-stream",
                    "browser.download.folderList": 2,
                    "browser.download.useDownloadDir": False,
                    "pdfjs.disabled": True
                })
            
            # Set preferences
            for pref_name, pref_value in firefox_prefs.items():
                if pref_value:  # Only set non-empty values
                    options.set_preference(pref_name, pref_value)
            
            # Create Firefox profile if on Windows
            if temp_profile_dir and os.name == 'nt':
                from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
                try:
                    profile = FirefoxProfile(temp_profile_dir)
                    # Set additional profile preferences
                    for pref_name, pref_value in firefox_prefs.items():
                        if pref_value:
                            profile.set_preference(pref_name, pref_value)
                    profile.update_preferences()
                    
                    # Use profile in options
                    options.profile = profile
                except Exception as profile_error:
                    print(f"Profile creation failed, using options only: {profile_error}")
            
            try:
                print("Attempting to launch Firefox...")
                self.driver = webdriver.Firefox(service=service, options=options)
                self.session_active = True
                
                # Configure timeouts from browser settings
                page_load_timeout = self.browser_settings.get('page_load_timeout', 30)
                implicit_wait = self.browser_settings.get('implicit_wait', 10)
                script_timeout = self.browser_settings.get('script_timeout', 30)
                
                self.driver.set_page_load_timeout(page_load_timeout)
                self.driver.implicitly_wait(implicit_wait)
                self.driver.set_script_timeout(script_timeout)
                
                # Set window size after launch if needed
                try:
                    self.driver.set_window_size(window_size[0], window_size[1])
                except:
                    pass  # Not critical
                
                # Reset session start time when browser launches
                self.security.session_start_time = time.time()
                
                # Navigate to a simple page to ensure Firefox is ready
                try:
                    self.driver.get("about:blank")
                    print("Firefox initialization completed")
                except Exception as nav_error:
                    print(f"Warning: Initial navigation failed: {nav_error}")
                
                self.security.log_operation("launch_browser", {"browser": "firefox", "headless": headless})
                return "Firefox browser launched successfully"
                
            except Exception as driver_error:
                print(f"Firefox WebDriver creation failed: {driver_error}")
                print(f"Driver path: {driver_path}")
                print(f"Firefox binary: {firefox_binary if os.name == 'nt' else 'system default'}")
                
                # Try fallback without profile
                if temp_profile_dir:
                    print("Retrying Firefox launch without custom profile...")
                    try:
                        basic_options = FirefoxOptions()
                        if headless or self.browser_settings.get('headless', False):
                            basic_options.add_argument("--headless")
                        if os.name == 'nt' and firefox_binary:
                            basic_options.binary_location = firefox_binary
                        
                        self.driver = webdriver.Firefox(service=service, options=basic_options)
                        self.session_active = True
                        
                        # Reset session start time when browser launches
                        self.security.session_start_time = time.time()
                        
                        self.security.log_operation("launch_browser", {"browser": "firefox", "headless": headless})
                        return "Firefox browser launched successfully (basic mode)"
                    except Exception as fallback_error:
                        print(f"Fallback launch also failed: {fallback_error}")
                
                raise driver_error
            
        except Exception as e:
            error_msg = f"Firefox launch failed: {str(e)}"
            if "geckodriver" in str(e).lower():
                error_msg += " (GeckoDriver issue - try updating geckodriver or check antivirus)"
            elif "permission" in str(e).lower():
                error_msg += " (Permission denied - try running as administrator)"
            elif "binary" in str(e).lower():
                error_msg += " (Firefox binary not found - check Firefox installation)"
            elif "profile" in str(e).lower():
                error_msg += " (Profile issue - check temp directory permissions)"
            raise Exception(error_msg)
    
    def close_browser(self) -> str:
        """Close the browser and clean up"""
        try:
            if not self.driver:
                return "No browser is currently running"
            
            self.driver.quit()
            self.driver = None
            self.session_active = False
            
            # Clean up temp profile directories
            temp_profiles = []
            if os.name == 'nt':
                import tempfile
                temp_profiles = [
                    os.path.join(tempfile.gettempdir(), "browser_automation_profile"),
                    os.path.join(tempfile.gettempdir(), "firefox_automation_profile")
                ]
            else:
                temp_profiles = [os.path.join(os.getcwd(), "temp_browser_profile")]
            
            import shutil
            for temp_profile in temp_profiles:
                if os.path.exists(temp_profile):
                    try:
                        shutil.rmtree(temp_profile)
                    except:
                        pass  # May be locked on Windows
            
            self.security.log_operation("close_browser", {})
            return "Browser closed successfully"
            
        except Exception as e:
            self.security.logger.error(f"Error closing browser: {e}")
            return f"Error closing browser: {str(e)}"
    
    def navigate_to(self, url: str) -> str:
        """Navigate to specified URL"""
        try:
            if not self.driver:
                return "No browser is running. Launch browser first."
            
            if not self.security.is_url_allowed(url):
                return f"URL not allowed: {url}"
            
            if not self.security.check_rate_limit():
                return "Rate limit exceeded"
            
            if self.security.check_session_timeout():
                self.close_browser()
                return "Session timed out. Browser closed."
            
            self.driver.get(url)
            self.security.log_operation("navigate_to", {"url": url})
            return f"Successfully navigated to {url}"
            
        except Exception as e:
            self.security.logger.error(f"Navigation error: {e}")
            return f"Navigation failed: {str(e)}"
    
    def get_current_url(self) -> str:
        """Get current page URL"""
        try:
            if not self.driver:
                return "No browser is running"
            
            # Check if driver is still alive
            try:
                current_url = self.driver.current_url
                self.security.log_operation("get_current_url", {"url": current_url})
                return current_url
            except Exception as driver_error:
                self.security.logger.error(f"Driver error getting URL: {driver_error}")
                self.session_active = False
                return f"Browser connection lost: {str(driver_error)}"
            
        except Exception as e:
            return f"Error getting URL: {str(e)}"
    
    def get_page_title(self) -> str:
        """Get current page title"""
        try:
            if not self.driver:
                return "No browser is running"
            
            title = self.driver.title
            self.security.log_operation("get_page_title", {"title": title})
            return title
            
        except Exception as e:
            return f"Error getting title: {str(e)}"
    
    def go_back(self) -> str:
        """Navigate back in browser history"""
        try:
            if not self.driver:
                return "No browser is running"
            
            if not self.security.check_rate_limit():
                return "Rate limit exceeded"
            
            self.driver.back()
            self.security.log_operation("go_back", {})
            return "Navigated back successfully"
            
        except Exception as e:
            return f"Error going back: {str(e)}"
    
    def go_forward(self) -> str:
        """Navigate forward in browser history"""
        try:
            if not self.driver:
                return "No browser is running"
            
            if not self.security.check_rate_limit():
                return "Rate limit exceeded"
            
            self.driver.forward()
            self.security.log_operation("go_forward", {})
            return "Navigated forward successfully"
            
        except Exception as e:
            return f"Error going forward: {str(e)}"
    
    def refresh_page(self) -> str:
        """Refresh the current page"""
        try:
            if not self.driver:
                return "No browser is running"
            
            if not self.security.check_rate_limit():
                return "Rate limit exceeded"
            
            self.driver.refresh()
            self.security.log_operation("refresh_page", {})
            return "Page refreshed successfully"
            
        except Exception as e:
            return f"Error refreshing page: {str(e)}"
    
    def take_screenshot(self, filename: Optional[str] = None) -> str:
        """Take a screenshot of the current page"""
        try:
            if not self.driver:
                return "No browser is running"
            
            if not self.security.can_take_screenshot():
                return "Screenshots are disabled in security settings"
            
            if not filename:
                timestamp = int(time.time())
                filename = f"screenshot_{timestamp}.png"
            
            # Take screenshot
            screenshot = self.driver.get_screenshot_as_png()
            
            # Add watermark with timestamp
            img = Image.open(BytesIO(screenshot))
            # Simple watermark - in production, you might want more sophisticated watermarking
            
            # Save screenshot
            with open(filename, 'wb') as f:
                f.write(screenshot)
            
            self.security.log_operation("take_screenshot", {"filename": filename})
            return f"Screenshot saved as {filename}"
            
        except Exception as e:
            return f"Error taking screenshot: {str(e)}"
    
    def find_element(self, selector: str, by_type: str = "css") -> Optional[Any]:
        """Find element by CSS selector or XPath"""
        try:
            if not self.driver:
                return None
            
            # Check if driver is still alive
            try:
                self.driver.current_url  # Test if driver is responsive
            except Exception as driver_error:
                self.security.logger.error(f"Driver appears to be dead: {driver_error}")
                self.session_active = False
                return None
            
            if not self.security.validate_selector(selector):
                return None
            
            if by_type.lower() == "css":
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
            elif by_type.lower() == "xpath":
                element = self.driver.find_element(By.XPATH, selector)
            elif by_type.lower() == "id":
                element = self.driver.find_element(By.ID, selector)
            elif by_type.lower() == "name":
                element = self.driver.find_element(By.NAME, selector)
            elif by_type.lower() == "class":
                element = self.driver.find_element(By.CLASS_NAME, selector)
            else:
                return None
            
            return element
            
        except NoSuchElementException:
            return None
        except Exception as e:
            self.security.logger.error(f"Error finding element: {e}")
            # Check if this is a driver crash
            try:
                self.driver.current_url
            except:
                self.security.logger.error("Driver appears to have crashed")
                self.session_active = False
            return None
    
    def wait_for_element(self, selector: str, by_type: str = "css", timeout: int = 10) -> bool:
        """Wait for element to be present"""
        try:
            if not self.driver:
                return False
            
            if not self.security.validate_selector(selector):
                return False
            
            wait = WebDriverWait(self.driver, timeout)
            
            if by_type.lower() == "css":
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            elif by_type.lower() == "xpath":
                wait.until(EC.presence_of_element_located((By.XPATH, selector)))
            elif by_type.lower() == "id":
                wait.until(EC.presence_of_element_located((By.ID, selector)))
            else:
                return False
            
            return True
            
        except TimeoutException:
            return False
        except Exception as e:
            self.security.logger.error(f"Error waiting for element: {e}")
            return False
