# contextos

**Your AI tools have different brains. ContextOS gives them one.**

Claude remembers Claude. ChatGPT remembers ChatGPT. Your custom agent remembers nothing.
ContextOS is the shared memory layer that runs on your machine — any LLM reads from it,
any LLM writes to it.

## Install

```bash
pip install contextos
```

## Start the server

```bash
pip install "contextos[cli]"
contextos start
```

Requires Docker. Starts Postgres, Redis, and the ContextOS API on `localhost:8000`.

## 5-line quickstart

```python
from contextos import ContextOS

client = ContextOS(api_key="sk-...")

# After a conversation — write memory
client.write(user_id="alice", conversation="User: I prefer async Python.\nAssistant: Got it.")

# Before the next LLM call — read memory
memory = client.query(user_id="alice", q=user_message)
system_prompt = f"You are helpful.\n\n{memory.prompt_block}"
```

## The cross-app story

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
