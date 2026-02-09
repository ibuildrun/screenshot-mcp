"""MCP server for capturing screenshots of desktop windows on Windows."""

import base64
import io
import subprocess
import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("screenshot-mcp")


def _find_window_by_title(title: str):
    """Find a window handle by partial title match."""
    import win32gui

    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            text = win32gui.GetWindowText(hwnd)
            if text and title.lower() in text.lower():
                result.append((hwnd, text))

    win32gui.EnumWindows(callback, None)
    return result


def _capture_window(hwnd) -> bytes:
    """Capture a window as PNG bytes using PrintWindow."""
    import win32gui
    import win32ui
    import win32con
    from PIL import Image

    rect = win32gui.GetWindowRect(hwnd)
    w = rect[2] - rect[0]
    h = rect[3] - rect[1]

    if w <= 0 or h <= 0:
        raise ValueError(f"Window has invalid size: {w}x{h}")

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    save_dc = mfc_dc.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(mfc_dc, w, h)
    save_dc.SelectObject(bitmap)

    # PW_RENDERFULLCONTENT = 2 for better capture
    result = save_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)

    bmp_info = bitmap.GetInfo()
    bmp_bits = bitmap.GetBitmapBits(True)

    img = Image.frombuffer("RGB", (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                           bmp_bits, "raw", "BGRX", 0, 1)

    save_dc.DeleteDC()
    mfc_dc.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwnd_dc)
    win32gui.DeleteObject(bitmap.GetHandle())

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _capture_full_screen() -> bytes:
    """Capture the entire screen as PNG bytes."""
    from PIL import ImageGrab

    img = ImageGrab.grab()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@mcp.tool()
def list_windows() -> str:
    """List all visible windows with their titles. Use this to find the window you want to screenshot."""
    import win32gui

    windows = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                windows.append(f"  [{hwnd}] {title} ({w}x{h})")

    win32gui.EnumWindows(callback, None)
    return "Visible windows:\n" + "\n".join(windows) if windows else "No visible windows found."


@mcp.tool()
def screenshot_window(title: str) -> list:
    """Capture a screenshot of a window by partial title match.
    Returns the screenshot as a base64-encoded PNG image.

    Args:
        title: Partial window title to match (case-insensitive).
    """
    matches = _find_window_by_title(title)
    if not matches:
        return [{"type": "text", "text": f"No window found matching '{title}'. Use list_windows to see available windows."}]

    hwnd, full_title = matches[0]
    try:
        png_bytes = _capture_window(hwnd)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return [
            {"type": "text", "text": f"Screenshot of '{full_title}' ({len(png_bytes)} bytes):"},
            {"type": "image", "data": b64, "mimeType": "image/png"},
        ]
    except Exception as e:
        return [{"type": "text", "text": f"Failed to capture '{full_title}': {e}"}]


@mcp.tool()
def screenshot_screen() -> list:
    """Capture a screenshot of the entire screen.
    Returns the screenshot as a base64-encoded PNG image.
    """
    try:
        png_bytes = _capture_full_screen()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return [
            {"type": "text", "text": f"Full screen screenshot ({len(png_bytes)} bytes):"},
            {"type": "image", "data": b64, "mimeType": "image/png"},
        ]
    except Exception as e:
        return [{"type": "text", "text": f"Failed to capture screen: {e}"}]


@mcp.tool()
def screenshot_region(x: int, y: int, width: int, height: int) -> list:
    """Capture a screenshot of a specific screen region.

    Args:
        x: Left coordinate.
        y: Top coordinate.
        width: Width of the region.
        height: Height of the region.
    """
    from PIL import ImageGrab

    try:
        img = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        b64 = base64.b64encode(png_bytes).decode("ascii")
        return [
            {"type": "text", "text": f"Region screenshot ({width}x{height} at {x},{y}, {len(png_bytes)} bytes):"},
            {"type": "image", "data": b64, "mimeType": "image/png"},
        ]
    except Exception as e:
        return [{"type": "text", "text": f"Failed to capture region: {e}"}]


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
