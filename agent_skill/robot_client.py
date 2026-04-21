#!/usr/bin/env python
"""机器人客户端 - 发送指令给服务器."""

import socket
import json
import sys


class RobotClient:
    def __init__(self, host="127.0.0.1", port=8765):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.host, self.port))
        print(f"Connected to {self.host}:{self.port}")

    def send(self, cmd):
        if not self.socket:
            self.connect()

        self.socket.sendall((cmd + "\n").encode("utf-8"))

        buffer = ""
        while "\n" not in buffer:
            data = self.socket.recv(1024)
            if not data:
                raise ConnectionError("Server disconnected")
            buffer += data.decode("utf-8")

        line, _ = buffer.split("\n", 1)
        return json.loads(line)

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def get(self):
        return self.send("get")

    def set(self, **kwargs):
        cmd = "set " + " ".join(f"{k}={v}" for k, v in kwargs.items())
        return self.send(cmd)

    def home(self):
        return self.send("home")

    def free(self):
        return self.send("free")

    def lock(self):
        return self.send("lock")

    def quit(self):
        return self.send("quit")


def main():
    import os
    import readline

    host = "127.0.0.1"
    port = 8765

    for i, arg in enumerate(sys.argv):
        if arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
        elif arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        elif arg == "--command" and i + 1 < len(sys.argv):
            client = RobotClient(host, port)
            client.connect()
            resp = client.send(sys.argv[i + 1])
            print(resp)
            client.close()
            return

    client = RobotClient(host, port)
    client.connect()

    print("Connected! Commands: get, set, home, free, lock, quit")
    print("Usage: set shoulder_pan.pos=30 elbow_flex.pos=45")

    while True:
        try:
            cmd = input("\n> ").strip()
            if not cmd:
                continue

            resp = client.send(cmd)
            print(resp)

            if cmd.startswith("quit"):
                break

        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            break

    client.close()


if __name__ == "__main__":
    main()