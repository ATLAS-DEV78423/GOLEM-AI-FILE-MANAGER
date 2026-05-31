# AI Providers

GOLEM supports multiple AI backends for metadata extraction and search reranking.

## Supported providers

- Groq
- OpenAI / ChatGPT
- OpenRouter
- Anthropic / Claude
- Google Gemini
- xAI
- NVIDIA NIM
- Custom OpenAI-compatible endpoints
- Heuristic mode with no external API

## How it works

GOLEM uses the selected provider for:

- file metadata generation
- optional reranking when local search confidence is low

If no key is provided, GOLEM falls back to heuristic mode.

## Provider notes

- OpenAI-compatible providers use `POST /chat/completions`
- Anthropic uses the Messages API
- Gemini uses `generateContent`
- OpenRouter works with an OpenAI-compatible API shape

## Practical advice

- Use heuristic mode if you want offline indexing only.
- Use OpenAI-compatible providers if you already have a chat-completions style endpoint.
- Use custom provider settings only if you know the base URL and model name are correct.

