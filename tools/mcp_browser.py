# mcp_browser.py

import os
import asyncio
from mcp import StdioServerParameters
from smolagents import MCPClient, tool
from dotenv import load_dotenv
from typing import Optional
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_WAIT_TIME = 3
MAX_WAIT_TIME     = 30

MOOC_USERNAME = os.getenv("MOOC_USERNAME", "")
MOOC_PASSWORD = os.getenv("MOOC_PASSWORD", "")

_mcp_client: Optional[MCPClient] = None
_mcp_tools: dict = {}


def get_or_create_event_loop():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


async def init_mcp_async():
    global _mcp_client, _mcp_tools

    if _mcp_client is None:
        logger.info("Initializing MCP Playwright (headless) ...")
        server_parameters = StdioServerParameters(
            command="npx",
            args=["@playwright/mcp@latest", "--headless"],  # ← headless flag
        )
        _mcp_client = MCPClient(server_parameters, structured_output=False)
        for t in _mcp_client.get_tools():
            _mcp_tools[t.name] = t
        logger.info(f"MCP initialized with {len(_mcp_tools)} tools")

    return _mcp_tools


async def navigate_async(url: str) -> str:
    if not url or not url.startswith(('http://', 'https://')):
        return f"Error: Invalid URL '{url}'"
    tools = await init_mcp_async()
    try:
        logger.info(f"Navigating to: {url}")
        tools['browser_navigate'](url=url)
        await asyncio.sleep(DEFAULT_WAIT_TIME)
        logger.info(f"Successfully navigated to {url}")
        return f"Navigated to {url}"
    except Exception as e:
        error_msg = f"Navigation failed: {str(e)[:200]}"
        logger.error(error_msg)
        return error_msg


async def get_content_async() -> str:
    tools = await init_mcp_async()
    try:
        logger.info("Extracting page content...")
        if 'browser_snapshot' in tools:
            result = tools['browser_snapshot']()
            if result:
                logger.info(f"Got snapshot of {len(str(result))} chars")
                return str(result)
        if 'browser_get_content' in tools:
            result = tools['browser_get_content']()
            if result:
                return str(result)
        if 'browser_execute_script' in tools:
            result = tools['browser_execute_script'](javascript="return document.body.innerText;")
            if result:
                return str(result)
        return "Error: No content extracted"
    except Exception as e:
        logger.error(f"Content extraction failed: {str(e)[:200]}")
        return f"Error: {str(e)[:200]}"


async def wait_async(seconds: int = DEFAULT_WAIT_TIME) -> str:
    seconds = max(0, min(seconds, MAX_WAIT_TIME))
    logger.info(f"Waiting {seconds} seconds...")
    await asyncio.sleep(seconds)
    return f"Waited {seconds} seconds"


async def click_async(selector: str) -> str:
    tools = await init_mcp_async()
    try:
        logger.info(f"Clicking: {selector}")
        if 'browser_click' in tools:
            tools['browser_click'](selector=selector)
            await asyncio.sleep(1)
            return f"Clicked: {selector}"
        return "Error: Click tool not available"
    except Exception as e:
        logger.error(f"Click failed: {str(e)[:200]}")
        return f"Click failed: {str(e)[:200]}"


async def fill_async(selector: str, value: str) -> str:
    tools = await init_mcp_async()
    try:
        if 'browser_fill' in tools:
            tools['browser_fill'](selector=selector, value=value)
            logger.info(f"Filled '{selector}'")
            return f"Filled: {selector}"
        elif 'browser_type' in tools:
            tools['browser_type'](selector=selector, text=value)
            logger.info(f"Typed into '{selector}'")
            return f"Typed: {selector}"
        return "Error: No fill/type tool available"
    except Exception as e:
        logger.error(f"Fill failed: {str(e)[:200]}")
        return f"Fill failed: {str(e)[:200]}"


async def login_mooc_async() -> str:
    """Auto-login using MOOC_USERNAME / MOOC_PASSWORD from .env."""
    tools = await init_mcp_async()

    login_url = "https://lms.fun-mooc.fr/login"
    logger.info(f"Navigating to login page: {login_url}")
    tools['browser_navigate'](url=login_url)
    await asyncio.sleep(3)

    if MOOC_USERNAME and MOOC_PASSWORD:
        logger.info("Attempting automatic login ...")
        try:
            for sel in ['#login-email', 'input[name="email"]', 'input[type="email"]']:
                res = await fill_async(sel, MOOC_USERNAME)
                if "Error" not in res:
                    break

            await asyncio.sleep(0.5)

            for sel in ['#login-password', 'input[name="password"]', 'input[type="password"]']:
                res = await fill_async(sel, MOOC_PASSWORD)
                if "Error" not in res:
                    break

            await asyncio.sleep(0.5)

            submitted = False
            for sel in ['button[type="submit"]', 'input[type="submit"]', '.login-button', '#login-form button']:
                try:
                    res = await click_async(sel)
                    if "Error" not in res and "failed" not in res.lower():
                        submitted = True
                        break
                except Exception:
                    continue

            if not submitted and 'browser_press' in tools:
                tools['browser_press'](selector='input[type="password"]', key='Enter')

            await asyncio.sleep(4)

            snapshot = str(await get_content_async())
            if any(kw in snapshot.lower() for kw in ['dashboard', 'logout', 'déconnexion', 'sign out']):
                logger.info(" Automatic login successful")
            else:
                logger.info("Auto-login attempted — continuing (could not confirm dashboard)")

            return "Auto-login completed"

        except Exception as e:
            logger.error(f"Auto-login error: {e}")
            return f"Auto-login error: {e}"

    # Manual fallback
    logger.warning("No credentials in .env — manual login required (30 s)")
    print("\n" + "="*60)
    print("MANUAL LOGIN REQUIRED")
    print("Set MOOC_USERNAME and MOOC_PASSWORD in your .env file")
    print("You have 30 seconds to log in manually.")
    print("="*60 + "\n")
    await asyncio.sleep(30)
    return "Manual login completed"


def run_async_in_sync(coro):
    loop = get_or_create_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            return executor.submit(lambda: asyncio.run(coro)).result(timeout=90)
    return loop.run_until_complete(coro)


# ── Public tools ──────────────────────────────────────────────────────────────

@tool
def real_navigate_tool(url: str) -> str:
    """
    Navigate browser to a URL.

    Args:
        url: Full URL (must start with http:// or https://)

    Returns:
        Status message
    """
    return run_async_in_sync(navigate_async(url))


@tool
def real_get_content_tool() -> str:
    """
    Get accessibility snapshot of current browser page.

    Returns:
        Page content as text
    """
    return run_async_in_sync(get_content_async())


@tool
def real_wait_tool(seconds: int = DEFAULT_WAIT_TIME) -> str:
    """
    Wait for page to load or elements to appear.

    Args:
        seconds: Seconds to wait (default 3)

    Returns:
        Status message
    """
    return run_async_in_sync(wait_async(seconds))


@tool
def real_click_tool(selector: str) -> str:
    """
    Click an element on the page.

    Args:
        selector: CSS selector

    Returns:
        Status message
    """
    return run_async_in_sync(click_async(selector))


@tool
def real_login_tool() -> str:
    """
    Login to FUN-MOOC using MOOC_USERNAME and MOOC_PASSWORD from .env.
    Falls back to a 30-second manual window if credentials are missing.

    Returns:
        Status message
    """
    return run_async_in_sync(login_mooc_async())


if __name__ == "__main__":
    print(real_login_tool())
    content = real_get_content_tool()
    print(f"Content preview: {content[:300]}")