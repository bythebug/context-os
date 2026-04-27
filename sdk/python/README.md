# contextos

**Your AI tools have different brains. ContextOS gives them one.**

Claude remembers Claude. ChatGPT remembers ChatGPT. Your custom agent remembers nothing.
ContextOS is the shared memory layer that runs on your machine — any LLM reads from it,
any LLM writes to it.

## Install

```bash
pip install "contextos[cli]"
```

## One-time setup

```bash
contextos init
```

This starts the server, creates an API key, and saves config to `~/.contextos/config.json`. Takes 30 seconds.

## Add 2 lines to your existing app

```python
import contextos
import anthropic

contextos.init()             # reads config saved by `contextos init`
contextos.set_user("alice")  # set before each LLM call

# Your existing code — UNCHANGED
response = anthropic.Anthropic().messages.create(
    model="claude-opus-4-6",
    system="You are helpful.",
    messages=[{"role": "user", "content": message}]
)
# ContextOS automatically:
#   → injects Alice's memory into the system prompt
#   → captures the conversation in the background
```

Works with OpenAI too — zero changes to your `openai.OpenAI().chat.completions.create(...)` calls.

## Manual API (full control)

```python
# In your Claude app
claude_client = ContextOS(api_key="sk-...")
claude_client.write(user_id="alice", conversation="...", source_client="claude-app")

# In your GPT app — reads memory written by the Claude app
gpt_client = ContextOS(api_key="sk-...")
memory = gpt_client.query(user_id="alice", q="what does alice prefer?")
# → Alice never re-introduced herself. Your GPT app already knows her.
```

Same `user_id`. Same server. One brain.

## Create an API key

```bash
contextos keys create --app-name myapp \
  --database-url postgresql://contextos:contextos@localhost:5433/contextos
```

## API

```python
client.write(user_id, conversation, source_client=None)   # → session_id
client.query(user_id, q, top_k=10, scope="global")        # → MemoryResponse
client.delete(fragment_id)

# Async versions
await client.awrite(...)
await client.aquery(...)
await client.adelete(...)
```

`MemoryResponse.prompt_block` is a pre-formatted string you paste directly into your system prompt. No processing needed.

## CLI

```bash
contextos start          # start server
contextos stop           # stop server
contextos logs -f        # follow logs
contextos health         # check status
contextos keys create    # create API key
contextos keys list      # list apps
```

## Links

- [GitHub](https://github.com/bythebug/context-os)
- [Docs](https://bythebug.github.io/context-os/)
- [MIT License](https://github.com/bythebug/context-os/blob/main/LICENSE)
