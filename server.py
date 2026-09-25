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
    
        
if __name__ == '__main__':
    server_address = ('127.0.0.1', 8771)
    httpd = ThreadingHTTPServer(server_address, RequestHandler)
    print('Server is running at http://127.0.0.1:8771')
    print('Starting server on port 8771...')
    
    httpd.serve_forever()