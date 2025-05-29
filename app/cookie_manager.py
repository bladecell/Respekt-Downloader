import nodriver as uc
import time
from tamga import Tamga
import json


class SessionCookieManager:
    
    def __init__(self, headless: bool = False, logger: Tamga = None):
        self.headless = headless
        self.browser = None
        self.logger = logger or Tamga(
            logToFile=False,
            logToJSON=False,
            logToConsole=True
        )
    
    async def start_browser(self):
        try:
            self.browser = await uc.start(headless=self.headless)
            self.logger.success("Browser started successfully")
            return self.browser
        except Exception as e:
            self.logger.error(f"Failed to start browser: {e}")
            raise
    
    async def login(self, email: str, password: str):
        if not self.browser:
            await self.start_browser()
        
        try:
            self.logger.info("Navigating to login page")
            page = await self.browser.get('https://audioteka.com/cz/prihlaseni/?redirectTo=%2Fcz%2Fpolicka%2F')
            
            
            self.logger.debug("Looking for cookie consent button")
            cookie_bar_accept = await page.find("SOUHLASÍM A POKRAČOVAT", best_match=True)
            if cookie_bar_accept:
                await cookie_bar_accept.click()
                self.logger.debug("Cookie consent accepted")
            
            
            self.logger.info("Filling login form")
            mail = await page.select("[type=email]")
            await mail.send_keys(email)
            
            pwd = await page.select("[type=password]")
            await pwd.send_keys(password)
            
            login_button = await page.select("button[type=submit]")
            await login_button.click()
            
            self.logger.info("Login submitted, waiting for response")
            time.sleep(2)
            
            
            cookies = await self.browser.cookies.get_all(requests_cookie_format=True)
            self.logger.success(f"Successfully captured {len(cookies)} cookies")
            return cookies
            
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            raise
        finally:
            if self.browser:
                self.logger.info("Closing browser")
                self.browser.stop()

async def get_cookies(email, password):
    
    
    logger = Tamga(
        logToFile=True,
        logToJSON=True,
        logToConsole=True
    )
    
    cookie_manager = SessionCookieManager(headless=False, logger=logger)
    cookies = await cookie_manager.login(email, password)
    
    logger.info(f"Got {len(cookies)} cookies")

    return cookies


if __name__ == '__main__':
    password = "your_password_here"
    email = "your_email_here"
    uc.loop().run_until_complete(get_cookies(email, password))