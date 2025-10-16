#!/usr/bin/env python3
# server.py
import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

START_TS = time.time()
START_ISO = datetime.now(timezone.utc).isoformat()

def make_handler(instance_name: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "MiniWeb/1.0"
        sys_version = ""

        def log(self, level: str, msg: str):
            logging.log(getattr(logging, level), f"[{instance_name}] {msg}")

        def do_GET(self):
            info = {
                "instance": instance_name,
                "pid": os.getpid(),
                "port": self.server.server_address[1],
                "host": socket.gethostname(),
                "started_at": START_ISO,
                "uptime_sec": round(time.time() - START_TS, 3),
                "path": self.path,
                "client": self.client_address[0],
            }

            if self.path in ("/", "/whoami"):
                payload = {
                    "message": f"Hello from instance '{instance_name}'",
                    **info,
                }
                body = json.dumps(payload, ensure_ascii=False, indent=2).encode()
                self._send(200, "application/json; charset=utf-8", body)
                self.log("INFO", f"GET {self.path} -> 200 ({len(body)} bytes)")
            elif self.path in ("/health", "/healthcheck"):
                self._send(200, "text/plain; charset=utf-8", b"OK")
                self.log("INFO", f"GET {self.path} -> 200")
            else:
                self._send(404, "text/plain; charset=utf-8", b"Not found")
                self.log("WARNING", f"GET {self.path} -> 404")

        def _send(self, code: int, ctype: str, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # Убираем базовый шум логгера http.server
        def log_message(self, format, *args):
            return

    return Handler

def setup_logging(instance_name: str):
    handler = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter(
        fmt=f"%(asctime)sZ [%(levelname)s] [{instance_name}] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

def main():
    parser = argparse.ArgumentParser(description="Minimal multi-instance web app")
    parser.add_argument("--name", required=False, default=os.getenv("INSTANCE_NAME", "server"),
                        help="уникальное имя копии (строчные буквы, 1..32)")
    parser.add_argument("--port", type=int, required=False, default=int(os.getenv("PORT", "8000")),
                        help="порт для HTTP сервера")
    args = parser.parse_args()

    # Простая проверка имени
    if not (1 <= len(args.name) <= 32) or not args.name.isalpha() or not args.name.islower():
        print("ERROR: --name должен состоять из строчных букв [a-z], длина 1..32", file=sys.stderr)
        sys.exit(2)

    setup_logging(args.name)
    handler_cls = make_handler(args.name)
    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), handler_cls)

    def _graceful_shutdown(signum, frame):
        logging.info(f"[{args.name}] received signal {signum}, shutting down...")
        # shutdown must run from another thread to avoid deadlock with serve_forever
        threading.Thread(
            target=httpd.shutdown,
            name=f"{args.name}-shutdown",
            daemon=True,
        ).start()

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    logging.info(f"[{args.name}] starting HTTP on port {args.port}, pid={os.getpid()}")
    logging.info(f"[{args.name}] try: curl http://localhost:{args.port}/whoami")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        logging.info(f"[{args.name}] server stopped")

if __name__ == "__main__":
    main()

