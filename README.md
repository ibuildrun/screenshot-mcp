# screenshot-mcp

MCP server for capturing screenshots of desktop windows on Windows. Allows AI assistants to see what's on screen — useful for UI development, debugging visual issues, and iterating on designs.

## Features

- **screenshot_window** — capture a specific window by title (partial match)
- **screenshot_screen** — capture the entire screen
- **screenshot_region** — capture a specific screen region (x, y, width, height)
- **list_windows** — list all visible windows with titles and sizes

Returns images as base64-encoded PNG that AI can analyze.

## Requirements

- Windows 10/11
- Python 3.10+

## Installation

```bash
pip install screenshot-mcp
```

Or install from source:
```bash
git clone https://github.com/ibuildrun/screenshot-mcp.git
cd screenshot-mcp
pip install -e .
```

## MCP Configuration

Add to your `.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "screenshot": {
      "command": "screenshot-mcp",
      "disabled": false
    }
  }
}
```

Or with uvx (no install needed):
```json
{
  "mcpServers": {
    "screenshot": {
      "command": "uvx",
      "args": ["screenshot-mcp"],
      "disabled": false
    }
  }
}
```

## Usage Examples

```
> list_windows
> screenshot_window "Teeworlds"
> screenshot_screen
> screenshot_region 0 0 800 600
```

## License

MIT
