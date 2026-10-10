# Continue

[Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue) is a VS Code extension that can use both tab-completion and agent chat against this server.

1. Install the Continue extension in VS Code (if you have not already).
2. Download the config below and save it as `config.yaml` in Continue's config directory, replacing any existing configuration.
3. Reload VS Code / Continue so it picks up the new file.

The downloaded file points Continue at this server's tab-completion and chat endpoints using your personal token.

```yaml download=hound-coder-continue-config.yaml
name: HoundCoder
version: 1.0.0
schema: v1

models:
  - name: Tab Autocomplete (Qwen2.5 Coder 7B)
    provider: openai
    model: Qwen/Qwen2.5-Coder-7B
    apiBase: <SERVER_BASE_URL>/tab
    apiKey: <YOUR_API_KEY>
    roles: [autocomplete]
    defaultCompletionOptions:
      maxTokens: 128
      temperature: 0.2
    autocompleteOptions:
      debounceDelay: 325     # default is ~250 ms, slightly higher to reduce server load
      maxPromptTokens: 1024  # keep well under server's max-model-len
      modelTimeout: 2500     # ms
      multilineCompletions: auto
      useCache: true
      useImports: true
      useRecentlyEdited: true
      useRecentlyOpened: true
    # Python-specific tweaks to prevent the model from trailing off
    requestOptions:
      timeout: 5000
      extraBodyProperties:
        stop:
          - "\nclass "
          - "\ndef "
          - "\nif __name__"

  - name: Agent (Qwen3 Coder 30B)
    provider: openai
    model: Intel/Qwen3-Coder-30B-A3B-Instruct-int4-AutoRound
    apiBase: <SERVER_BASE_URL>/chat
    apiKey: <YOUR_API_KEY>
    roles: [chat, edit, apply, summarize]
    defaultCompletionOptions:
      contextLength: 32768

context:
  - provider: code
  - provider: open
  - provider: terminal
  - provider: file
  - provider: currentFile
  - provider: diff
  - provider: clipboard
  - provider: tree
  - provider: problems
  - provider: debugger
    params:
      stackDepth: 3
  - provider: repo-map
```
