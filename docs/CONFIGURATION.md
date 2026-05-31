# Configuration

GOLEM stores configuration in its local SQLite settings table.

## Settings

- watched folder
- vault folder
- AI provider
- API key
- model name
- custom base URL
- dry-run mode
- watch enabled
- confidence threshold
- default category
- Terms version and acceptance state

## Provider selection

Supported provider keys:

- `heuristic`
- `groq`
- `openai`
- `openrouter`
- `anthropic`
- `gemini`
- `xai`
- `nvidia_nim`
- `custom_openai`

## Environment variables

- `GOLEM_DATA_DIR` - override the app data directory
- `GOLEM_PAYLOAD_DIR` - override installer payload source
- `GOLEM_INSTALL_DIR` - override installer install target
- `GOLEM_START_MENU_DIR` - override Start Menu target
- `GOLEM_DESKTOP_DIR` - override Desktop target
- `GOLEM_SKIP_REGISTRY` - skip Windows registry install entries

## Secret handling

API keys are stored in the local database and encrypted on Windows with DPAPI.

