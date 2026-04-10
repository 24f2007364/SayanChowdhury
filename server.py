import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", "8000"))

# Option 1: set an environment variable named GEMINI_API_KEY
# Option 2: paste your key below while testing locally
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip() or "PASTE_YOUR_GEMINI_API_KEY_HERE"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


class PortfolioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_POST(self):
        if self.path == "/api/chat":
            self.handle_chat()
            return

        self.send_json({"error": "Not found."}, status=404)

    def handle_chat(self):
        if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_GEMINI_API_KEY_HERE":
            self.send_json(
                {
                    "error": "Gemini API key is missing. Add it in server.py or set GEMINI_API_KEY before starting the server."
                },
                status=500,
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = json.loads(raw_body.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self.send_json({"error": "Invalid JSON body."}, status=400)
            return

        history = payload.get("history", [])
        system_prompt = str(payload.get("systemPrompt", "")).strip()

        if not isinstance(history, list) or not history:
            self.send_json({"error": "Chat history is required."}, status=400)
            return

        gemini_payload = {"contents": history}
        if system_prompt:
            gemini_payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        request = urllib.request.Request(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            data=json.dumps(gemini_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = self.read_error_details(exc)
            self.send_json(
                {
                    "error": "Gemini request failed.",
                    "details": details,
                },
                status=502,
            )
            return
        except urllib.error.URLError as exc:
            self.send_json(
                {
                    "error": "Could not reach Gemini.",
                    "details": str(exc.reason),
                },
                status=502,
            )
            return

        reply = self.extract_reply(data)
        if not reply:
            self.send_json(
                {
                    "error": "Gemini returned no text response.",
                    "details": data,
                },
                status=502,
            )
            return

        self.send_json({"reply": reply})

    @staticmethod
    def extract_reply(data):
        candidates = data.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                text = part.get("text")
                if text:
                    return text
        return None

    @staticmethod
    def read_error_details(exc):
        try:
            payload = exc.read().decode("utf-8")
            return json.loads(payload)
        except Exception:
            return str(exc)

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), PortfolioHandler)
    print(f"Serving portfolio at http://127.0.0.1:{PORT}")
    server.serve_forever()
