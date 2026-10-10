# General

Use these OpenAI-compatible endpoints with any client that supports a custom base URL and Bearer API key.

## Base URL

`<SERVER_BASE_URL>`

## Endpoints

- `/tab/` — code completion (no `/v1` prefix)
- `/chat/` — chat / agent (no `/v1` prefix)

## Authentication

Send your personal token on every request:

```
Authorization: Bearer <YOUR_API_KEY>
```

## Example

```bash
curl -s -H "Authorization: Bearer <YOUR_API_KEY>" \
  '<SERVER_BASE_URL>/tab/models'
```
