"""
Email Screenshot Service using Playwright.

Renders email HTML content and captures full-page screenshots.
"""

import asyncio
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotResult:
    """Result of screenshot capture."""
    email_id: str
    success: bool
    image_bytes: Optional[bytes] = None
    error: Optional[str] = None
    width: int = 0
    height: int = 0


class EmailScreenshotService:
    """
    Playwright-based email screenshot generation.

    Renders email HTML in headless Chromium and captures full-page PNG screenshots.
    """

    # Base styles to inject for consistent rendering
    BASE_STYLES = """
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        }
        img {
            max-width: 100%;
            height: auto;
        }
        /* Ensure all images load before screenshot */
        img[src] {
            opacity: 1;
        }
    </style>
    """

    def __init__(
        self,
        viewport_width: int = 800,
        viewport_height: int = 1200,
        format: str = "png",
        jpeg_quality: int = 85,
        timeout_ms: int = 30000
    ):
        """
        Initialize screenshot service.

        Args:
            viewport_width: Browser viewport width in pixels
            viewport_height: Browser viewport height in pixels
            format: Output format ("png" or "jpeg")
            jpeg_quality: JPEG quality (1-100), only used if format is jpeg
            timeout_ms: Page load timeout in milliseconds
        """
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.format = format.lower()
        self.jpeg_quality = jpeg_quality
        self.timeout_ms = timeout_ms
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        """Async context manager entry - launch browser."""
        await self._start_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close browser."""
        await self._stop_browser()

    async def _start_browser(self):
        """Launch headless Chromium browser."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
        logger.info("Playwright browser launched")

    async def _stop_browser(self):
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright browser closed")

    async def capture_screenshot(
        self,
        html_content: str,
        email_id: str
    ) -> ScreenshotResult:
        """
        Render HTML email and capture full-page screenshot.

        Args:
            html_content: HTML content of the email
            email_id: Unique identifier for the email

        Returns:
            ScreenshotResult with image bytes or error
        """
        if not self._browser:
            await self._start_browser()

        page = None
        try:
            # Create new page with viewport
            page = await self._browser.new_page(
                viewport={
                    'width': self.viewport_width,
                    'height': self.viewport_height
                }
            )

            # Inject base styles and set content
            styled_html = self._inject_styles(html_content)
            await page.set_content(styled_html, wait_until='networkidle', timeout=self.timeout_ms)

            # Wait for images to load
            await self._wait_for_images(page)

            # Capture full-page screenshot
            screenshot_bytes = await page.screenshot(
                full_page=True,
                type=self.format,
                quality=self.jpeg_quality if self.format == 'jpeg' else None
            )

            # Get dimensions
            dimensions = await page.evaluate("""
                () => ({
                    width: document.body.scrollWidth,
                    height: document.body.scrollHeight
                })
            """)

            logger.debug(f"Screenshot captured for {email_id}: {len(screenshot_bytes)} bytes")

            return ScreenshotResult(
                email_id=email_id,
                success=True,
                image_bytes=screenshot_bytes,
                width=dimensions.get('width', self.viewport_width),
                height=dimensions.get('height', self.viewport_height)
            )

        except Exception as e:
            logger.error(f"Screenshot failed for {email_id}: {e}")
            return ScreenshotResult(
                email_id=email_id,
                success=False,
                error=str(e)
            )

        finally:
            if page:
                await page.close()

    async def _wait_for_images(self, page, timeout_ms: int = 5000):
        """
        Wait for all images to load.

        Args:
            page: Playwright page object
            timeout_ms: Maximum time to wait for images
        """
        try:
            await page.evaluate("""
                () => {
                    const images = document.querySelectorAll('img[src]');
                    const promises = Array.from(images).map(img => {
                        if (img.complete) return Promise.resolve();
                        return new Promise((resolve, reject) => {
                            img.addEventListener('load', resolve);
                            img.addEventListener('error', resolve); // Resolve even on error
                            setTimeout(resolve, 5000); // Timeout per image
                        });
                    });
                    return Promise.all(promises);
                }
            """)
        except Exception as e:
            logger.warning(f"Image wait failed: {e}")

    def _inject_styles(self, html_content: str) -> str:
        """
        Inject base styles into HTML content.

        Args:
            html_content: Original HTML

        Returns:
            HTML with injected styles
        """
        # Check if HTML has head tag
        if '<head>' in html_content.lower():
            # Insert styles after head tag
            return html_content.replace(
                '<head>', f'<head>{self.BASE_STYLES}', 1
            ).replace(
                '<HEAD>', f'<HEAD>{self.BASE_STYLES}', 1
            )
        elif '<html>' in html_content.lower():
            # Insert styles after html tag
            return html_content.replace(
                '<html>', f'<html><head>{self.BASE_STYLES}</head>', 1
            ).replace(
                '<HTML>', f'<HTML><head>{self.BASE_STYLES}</head>', 1
            )
        else:
            # Wrap in complete HTML document
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                {self.BASE_STYLES}
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

    async def capture_batch(
        self,
        emails: List[Tuple[str, str]],
        max_concurrent: int = 5
    ) -> List[ScreenshotResult]:
        """
        Capture screenshots for multiple emails concurrently.

        Args:
            emails: List of (html_content, email_id) tuples
            max_concurrent: Maximum concurrent screenshot operations

        Returns:
            List of ScreenshotResult objects
        """
        if not self._browser:
            await self._start_browser()

        semaphore = asyncio.Semaphore(max_concurrent)

        async def capture_with_semaphore(html: str, email_id: str) -> ScreenshotResult:
            async with semaphore:
                return await self.capture_screenshot(html, email_id)

        tasks = [
            capture_with_semaphore(html, email_id)
            for html, email_id in emails
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to ScreenshotResult
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                email_id = emails[i][1] if i < len(emails) else 'unknown'
                processed_results.append(ScreenshotResult(
                    email_id=email_id,
                    success=False,
                    error=str(result)
                ))
            else:
                processed_results.append(result)

        successful = sum(1 for r in processed_results if r.success)
        logger.info(f"Batch screenshot complete: {successful}/{len(emails)} successful")

        return processed_results


async def capture_email_screenshots(
    emails: List[Tuple[str, str]],
    viewport_width: int = 800,
    viewport_height: int = 1200,
    format: str = "png",
    max_concurrent: int = 5
) -> List[ScreenshotResult]:
    """
    Convenience function to capture screenshots for multiple emails.

    Args:
        emails: List of (html_content, email_id) tuples
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height
        format: Output format ("png" or "jpeg")
        max_concurrent: Maximum concurrent operations

    Returns:
        List of ScreenshotResult objects
    """
    async with EmailScreenshotService(
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        format=format
    ) as service:
        return await service.capture_batch(emails, max_concurrent=max_concurrent)
