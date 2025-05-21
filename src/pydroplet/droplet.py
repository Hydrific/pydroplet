import json
import socket
import threading


def null():
    pass


class Droplet:
    def __init__(self, port, ip_addr, callback, timeout=10):
        self.port = 3333
        self.ip_addr = "localhost"
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(timeout)
        self.callback = callback
        self.flow = 0
        self.stop_serve = threading.Event()
        self.start()

    def try_connect(self):
        # TODO
        return True

    def start(self):
        try:
            self.socket.bind(("", self.port))
        except OSError as e:
            print(f"Bind failed: {e}")
        self.socket.listen()
        threading.Thread(target=self.run_server, daemon=True).start()

    def stop(self):
        self.stop_serve.set()

    def set_flow(self, flow):
        if flow is not None:
            self.flow = flow
            self.callback(flow)

    # TODO: How to accomodate multiple droplets???
    def run_server(self):
        self.stop_serve.clear()
        while True:
            try:
                if self.stop_serve.is_set():
                    return
                conn, address = self.socket.accept()
                while True:
                    if self.stop_serve.is_set():
                        return
                    data = conn.recv(1024)
                    if data:
                        try:
                            msg = json.loads(data)
                            self.set_flow(msg.get("flow"))
                        except json.JSONDecodeError:
                            print(f"Failed to decode message: {data}")
            except TimeoutError:
                pass
