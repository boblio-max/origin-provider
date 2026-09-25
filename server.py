import json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == "/v1/models":
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"object": "list", "data": [{"id": "stub-chat", "object": "model"}]}).encode())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Not Found'}).encode())
    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path != "/v1/chat/completions":
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "not found", "type": "invalid_request_error"}}).encode())
            return
        if self.headers.get("Authorization", "") != "Bearer sk-test-123":
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "invalid api key", "type": "invalid_request_error"}}).encode())
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "invalid json", "type": "invalid_request_error"}}).encode())
            return
        tools = body.get("tools", [])
        has_tool_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        if tools and not has_tool_result:
            first = (tools[0].get("function", {}))
            reply = {"role": "assistant", "content": None,
                    "tool_calls": [{"id": "call_stub_1", "type": "function",
                                    "function": {"name": first.get("name", "get_time"),
                                                "arguments": "{}"}}]}
            finish = "tool_calls"
        else:
            text = ""
            for m in reversed(body.get("messages", [])):
                if m.get("role") == "user":
                    c = m.get("content", "")
                    text = c if isinstance(c, str) else " ".join(
                        p.get("text", "") for p in c if p.get("type") == "text")
                    break
            reply = {"role": "assistant", "content": f"stub reply to '{text[:200]}'"}
            finish = "stop"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "id": "chatcmpl-stub-1", "object": "chat.completion",
            "created": int(time.time()), "model": "stub-chat",
            "choices": [{"index": 0, "message": reply, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode())
if __name__ == '__main__':
    server_address = ('127.0.0.1', 8771)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    print('Server is running at http://127.0.0.1:8771')
    print('Starting server on port 8771...')
    
    httpd.serve_forever()