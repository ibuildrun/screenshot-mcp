"""MCP server for capturing screenshots of desktop windows on Windows."""

import base64
import io
import logging
import os
import sys
import time as _time
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("screenshot-mcp")

mcp = FastMCP("screenshot-mcp")

# Keep screenshots small so base64 doesn't blow up Kiro's context
MAX_DIMENSION = 800
JPEG_QUALITY = 50

# Save screenshots to a local directory relative to working dir
SCREENSHOT_DIR = os.path.join(os.getcwd(), "screenshots")


def _ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def _resize_if_needed(img):
    """Resize image if it exceeds MAX_DIMENSION, preserving aspect ratio."""
    from PIL import Image
    w, h = img.size
    if w <= MAX_DIMENSION and h <= MAX_DIMENSION:
        return img
    ratio = min(MAX_DIMENSION / w, MAX_DIMENSION / h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    logger.info(f"Resizing from {w}x{h} to {new_w}x{new_h}")
    return img.resize((new_w, new_h), Image.LANCZOS)


def _to_rgb(img):
    if img.mode in ("RGBA", "LA", "P"):
        return img.convert("RGB")
    return img


def _img_to_base64(img) -> str:
    """Convert PIL Image to base64 JPEG string, resized and compressed."""
    img = _resize_if_needed(img)
    img = _to_rgb(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = buf.getvalue()
    logger.info(f"JPEG size: {len(data)} bytes")
    return base64.b64encode(data).decode("ascii")


def _save_to_disk(img, name: str) -> str:
    """Save screenshot to disk as JPEG, return path."""
    _ensure_screenshot_dir()
    img = _resize_if_needed(img)
    img = _to_rgb(img)
    ts = _time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = os.path.join(SCREENSHOT_DIR, f"{safe}_{ts}.jpg")
    img.save(path, format="JPEG", quality=70, optimize=True)
    logger.info(f"Saved to {path}")
    return path


def _find_window_by_title(title: str):
    import win32gui
    result = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if text and title.lower() in text.lower():
                result.append((hwnd, text))
    win32gui.EnumWindows(callback, None)
    # prefer exact match over partial
    exact = [(h, t) for h, t in result if t.lower() == title.lower()]
    if exact:
        return exact
    # prefer shorter titles (more likely the actual app window)
    result.sort(key=lambda x: len(x[1]))
    return result


def _restore_and_focus(hwnd):
    import win32gui, win32con, time
    placement = win32gui.GetWindowPlacement(hwnd)
    if placement[1] == win32con.SW_SHOWMINIMIZED:
        logger.info(f"Window {hwnd} minimized, restoring...")
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.5)
    win32gui.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def _capture_window(hwnd):
    """Capture a window as PIL Image using PrintWindow API.
    Works even if the window is behind other windows (unlike BitBlt/ImageGrab)."""
    import win32gui, win32ui, win32con
    import ctypes
    from PIL import Image

    _restore_and_focus(hwnd)

    # Use client rect for content only (no title bar/borders)
    client_rect = win32gui.GetClientRect(hwnd)
    w = client_rect[2] - client_rect[0]
    h = client_rect[3] - client_rect[1]
    if w <= 0 or h <= 0:
        raise ValueError(f"Window has invalid client size: {w}x{h}")

    logger.info(f"Capturing window {hwnd} client area: {w}x{h}")
    hwnd_dc = win32gui.GetDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)

    # PrintWindow with PW_CLIENTONLY|PW_RENDERFULLCONTENT (flags=3)
    # captures window content even if occluded by other windows
    ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

    bmp_info = bitmap.GetInfo()
    bmp_bits = bitmap.GetBitmapBits(True)
    img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                           bmp_bits, "raw", "BGRX", 0, 1)

    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bitmap.GetHandle())
    return img


def _capture_full_screen():
    from PIL import ImageGrab
    logger.info("Capturing full screen")
    return ImageGrab.grab()


@mcp.tool()
def list_windows() -> str:
    """List all visible windows with their titles. Use this to find the window you want to screenshot."""
    import win32gui
    logger.info("Listing visible windows")
    windows = []
    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                windows.append(f"  [{hwnd}] {title} ({w}x{h})")
    win32gui.EnumWindows(callback, None)
    return "Visible windows:\n" + "\n".join(windows) if windows else "No visible windows found."


@mcp.tool()
def screenshot_window(title: str) -> list:
    """Capture a screenshot of a window by partial title match.
    Saves the screenshot as a JPEG file and returns the file path.

    Args:
        title: Partial window title to match (case-insensitive).
    """
    logger.info(f"screenshot_window called with title='{title}'")
    matches = _find_window_by_title(title)
    if not matches:
        return [{"type": "text", "text": f"No window found matching '{title}'. Use list_windows to see available windows."}]

    hwnd, full_title = matches[0]
    try:
        img = _capture_window(hwnd)
        # Save to disk for reference
        filepath = _save_to_disk(img, full_title)
        # Return base64 image inline like Puppeteer does
        b64 = _img_to_base64(img)
        return [
            {"type": "text", "text": f"Screenshot of '{full_title}' (also saved to {filepath}):"},
            {"type": "image", "data": b64, "mimeType": "image/jpeg"},
        ]
    except Exception as e:
        logger.error(f"Failed to capture '{full_title}': {e}", exc_info=True)
        return [{"type": "text", "text": f"Failed to capture '{full_title}': {e}"}]


@mcp.tool()
def screenshot_screen() -> list:
    """Capture a screenshot of the entire screen.
    Saves the screenshot as a JPEG file and returns the file path.
    """
    logger.info("screenshot_screen called")
    try:
        img = _capture_full_screen()
        filepath = _save_to_disk(img, "fullscreen")
        b64 = _img_to_base64(img)
        return [
            {"type": "text", "text": f"Full screen screenshot (also saved to {filepath}):"},
            {"type": "image", "data": b64, "mimeType": "image/jpeg"},
        ]
    except Exception as e:
        logger.error(f"Failed to capture screen: {e}", exc_info=True)
        return [{"type": "text", "text": f"Failed to capture screen: {e}"}]


@mcp.tool()
def screenshot_region(x: int, y: int, width: int, height: int) -> list:
    """Capture a screenshot of a specific screen region.
    Saves the screenshot as a JPEG file and returns the file path.

    Args:
        x: Left coordinate.
        y: Top coordinate.
        width: Width of the region.
        height: Height of the region.
    """
    from PIL import ImageGrab
    logger.info(f"screenshot_region called: ({x},{y}) {width}x{height}")
    try:
        img = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        filepath = _save_to_disk(img, f"region_{width}x{height}")
        b64 = _img_to_base64(img)
        return [
            {"type": "text", "text": f"Region screenshot ({width}x{height}, saved to {filepath}):"},
            {"type": "image", "data": b64, "mimeType": "image/jpeg"},
        ]
    except Exception as e:
        logger.error(f"Failed to capture region: {e}", exc_info=True)
        return [{"type": "text", "text": f"Failed to capture region: {e}"}]


@mcp.tool()
def click_window(title: str, x: int, y: int) -> str:
    """Click at position (x, y) inside a window's client area.
    Coordinates are relative to the window's top-left client corner.

    Args:
        title: Window title to match (case-insensitive).
        x: X coordinate relative to window client area.
        y: Y coordinate relative to window client area.
    """
    import win32gui, win32api, win32con
    import ctypes
    import time

    logger.info(f"click_window called: title='{title}' x={x} y={y}")
    matches = _find_window_by_title(title)
    if not matches:
        return f"No window found matching '{title}'."

    hwnd, full_title = matches[0]
    _restore_and_focus(hwnd)
    time.sleep(0.2)

    # Convert client coords to screen coords
    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (x, y))
    logger.info(f"Clicking screen coords ({screen_x}, {screen_y}) in '{full_title}'")

    # Move cursor and click
    ctypes.windll.user32.SetCursorPos(screen_x, screen_y)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)
    time.sleep(0.3)

    return f"Clicked at ({x}, {y}) in '{full_title}' (screen: {screen_x}, {screen_y})"


@mcp.tool()
def get_window_size(title: str) -> str:
    """Get the client area size of a window. Useful for calculating click coordinates.

    Args:
        title: Window title to match (case-insensitive).
    """
    import win32gui
    logger.info(f"get_window_size called: title='{title}'")
    matches = _find_window_by_title(title)
    if not matches:
        return f"No window found matching '{title}'."

    hwnd, full_title = matches[0]
    rect = win32gui.GetClientRect(hwnd)
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    return f"Window '{full_title}': client area {w}x{h}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
