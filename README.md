# origin-provider

tiny stub server that pretends to be an AI model API so OpenCode can talk to custom models. implements just enough of the OpenAI protocol (`GET /v1/models`, `POST /v1/chat/completions`) for OpenCode's custom-provider config to connect — with a hardcoded `Bearer sk-test-123` and canned text + a single tool-call round-trip. no real inference happens here, it's scaffolding for the real provider work.

## how it actually works

- `server.py` (81 lines) — stdlib-only `ThreadingHTTPServer`, zero dependencies. serves the model catalog from `models.json` (currently `muse-glimmer-30b`) and fakes chat completions.
- `PIPELINE.md` (186 lines) — the actual protocol doc describing the request/response shapes.
- `hf_pull.py` — empty, reserved for future Hugging Face model pulling.

```bash
python server.py
# point OpenCode at http://localhost:8080/v1 as a custom provider
```

see [OpenCode custom providers](https://opencode.ai/docs/providers/#custom-provider) for the config side.

## stack

Python stdlib only. deliberately minimal — the point is the protocol, not the models.
