# origin-provider — full pipeline: how OpenCode calls your models

How a keystroke in OpenCode becomes an HTTP request to this server, what your
server must return, and what is left to implement. Written to be read offline.

## 1. Big picture

```
You press Enter in OpenCode TUI
  → OpenCode core assembles: system prompt + conversation history + tool schemas
  → AI SDK (@ai-sdk/openai-compatible) builds POST /v1/chat/completions
  → HTTPS to YOUR server (baseURL from opencode.json, key from auth.json/env)
  → Your server replies: text chunks and/or tool_calls
  → OpenCode executes tool calls LOCALLY (read/bash/edit on your machine)
  → Tool results go back into messages, request repeats until finish_reason = "stop"
  → Final text rendered in the TUI
```

Key insight: **your server never touches files or tools.** It only produces
*decisions* (text + tool_calls). OpenCode does the acting. Your job is purely:
authenticate → understand messages+tools → return correctly-shaped JSON.

## 2. Startup: how OpenCode finds your provider

`opencode.json` (user's machine, never in this repo):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "origin": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Origin Provider",
      "options": { "baseURL": "http://localhost:8771/v1" },
      "models": {
        "stub-chat": { "name": "Stub Chat",
          "limit": { "context": 128000, "output": 16384 } }
      }
    }
  }
}
```

- `npm` selects the client driver (chat-completions dialect).
- `baseURL` is prefixed onto every path: `POST {baseURL}/chat/completions`.
- The key comes from `/connect` (stored in `~/.local/share/opencode/auth.json`)
  or `options.apiKey: "{env:ORIGIN_API_KEY}"`. Sent as
  `Authorization: Bearer <key>` on EVERY request — this is what `server.py`
  checks against `sk-test-123` today.
- `GET /v1/models` is how `/models` in the TUI discovers you (done, Lesson 2).
  The `id` here (`stub-chat`) must equal the key under `"models"` above.

## 3. The per-turn loop (the heart of it)

One user message triggers this loop, which repeats until `finish_reason: "stop"`:

```
POST /v1/chat/completions, stream: true
  messages = [system, ...history, user,
              (assistant tool_calls…, tool results…)...]
  tools    = [{type:"function", function:{name, description, parameters}}...]
```

Your server answers with **one** of:

| finish_reason | Meaning | OpenCode does next |
|---|---|---|
| `"stop"` | Final text in `message.content` | Renders text, turn ends |
| `"tool_calls"` | `message.tool_calls[]` lists calls | Executes each locally, appends results, **loops** (new POST) |
| `"length"` | Hit `max_tokens` | Truncates/errors to user |
| `"content_filter"` | Refused | Shows refusal |

The loop bound is on OpenCode's side (max steps setting). Your server is
stateless: every POST carries the FULL message history, including prior
`assistant.tool_calls` and `role:"tool"` results. You never remember anything
between requests — the conversation IS the request.

## 4. Exact HTTP contract

### 4a. Non-streaming (`"stream": false`) — DONE in server.py

Request fields OpenCode sends: `model, messages, temperature, max_tokens,
tools, tool_choice, stream`.

Reply `200`:

```json
{"id":"chatcmpl-stub-1","object":"chat.completion","created":1710000000,"model":"stub-chat",
 "choices":[{"index":0,
   "message":{"role":"assistant","content":"... or null",
     "tool_calls":[{"id":"call_stub_1","type":"function",
       "function":{"name":"read","arguments":"{\"path\":\"x.py\"}"}}]},
   "finish_reason":"stop"}],
 "usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}
```

Rules: `content` is a string for text, **null** when tool_calls present.
`arguments` is a **JSON string**, not an object. `tool_calls[].id` (`call_...`)
is echoed back later in `role:"tool"` messages as `tool_call_id` — that id
linkage is how OpenCode matches results to calls. Break it and tools fail.

### 4b. Streaming (`"stream": true`) — TODO (Lesson 4)

Same request with `"stream": true`. Reply headers:
`Content-Type: text/event-stream`, flush after every write. Body = lines of:

```
data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"...",
  "choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}
data: {"choices":[{"index":0,"delta":{"content":"word "}}]}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_stub_1",
  "type":"function","function":{"name":"read","arguments":""}}]}}]}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,
  "function":{"arguments":"{\"pa"}}]}}]}
data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,
  "function":{"arguments":"th\":\"x\"}"}}]}}]}
data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}
data: [DONE]
```

Reassembly rules the client follows (so your chunks must obey them):
- Group deltas by `tool_calls[].index`, concatenate `arguments` strings in order.
- Final assembled `arguments` must parse as JSON.
- `finish_reason` arrives on its own final chunk; `[DONE]` is a bare sentinel
  line, not JSON. Every line ends `\n`, chunks separated by `\n` (i.e. blank
  line after each `data:` line).

### 4c. Tool message shape (what comes BACK to you)

After OpenCode runs your requested tools, the next POST's messages end with:

```json
{"role":"assistant","content":null,"tool_calls":[{...same ids you sent...}]},
{"role":"tool","tool_call_id":"call_stub_1","content":"<tool stdout>"},
{"role":"tool","tool_call_id":"call_stub_2","content":"<tool stdout>"}
```

Your branch rule (already implemented): tools present + no `role:"tool"`
message → emit a call; otherwise emit final text. The stub always calls the
first tool with `"{}"`; a real model decides name+arguments from context.

### 4d. Errors

| Code | When | Body | Client behavior |
|---|---|---|---|
| 401 | Bad/missing Bearer key (done) | `{"error":{"message":...,"type":"invalid_request_error"}}` | Prompts to fix key, no retry |
| 400 | Malformed JSON (done) | same envelope | Surfaces error, no retry |
| 404 | Unknown path (done) | same envelope | Surfaces error |
| 429 | Rate limited (future) | same envelope + `Retry-After` header respected | Waits, retries |
| 5xx | Your crash (future) | — | Retries with backoff, then surfaces |

## 5. Context windows and usage

- `limit.context` / `limit.output` in `opencode.json` are OpenCode's guardrails:
  it counts tokens client-side and stops sending history past the limit (oldest
  messages compacted/summarized first). Your `usage` reply feeds its meter.
- The stub reports `1/1/2` — fine for protocol testing, must become real
  counts once a model sits behind this (count words/tokens of prompt+completion).

## 6. Auth, keys, and your key-gen code

- Wire format is fixed: `Authorization: Bearer <key>` per request. Your future
  key-gen code decides what a valid `<key>` is (HMAC, DB lookup, prefix match —
  your design). `server.py`'s `!= "Bearer sk-test-123"` line is the single
  seam where that plugs in.
- Never accept keys in query params or log them. Never commit real keys (see
  repo root guidance: `.env`/real configs stay gitignored).

## 7. Status and offline checklist

Done: `GET /v1/models` + routing + 404s · Bearer `401` · POST non-streaming
(final text + tool_calls + round-trip rule) · `400` on bad JSON · verified
`stop`/`tool_calls`/`stop` against the live server.

Todo, in order:
1. **SSE streaming** (4b) — role chunk, content/tool deltas, finish chunk, `[DONE]`.
2. **Streaming tool-call reassembly test** — split `arguments` across chunks, verify client-side concat (test with curl raw output, eyeball the pieces).
3. **Point real OpenCode at it**: `/connect` → Other → id `origin`, key
   `sk-test-123` → add the `opencode.json` block from §2 → `/models` → select
   `stub-chat` → send "hi" → expect `stub reply to 'hi'`.
4. **Real `usage` counts** + **429/Retry-After** (only when serving real traffic).
5. **Key management**: replace `sk-test-123` with your key-gen system.
6. **Swap the stub brain for inference** — everything above stays identical;
   only the reply-construction logic changes.

Have fun — when you're back, Lesson 4 (SSE) is the next session.
