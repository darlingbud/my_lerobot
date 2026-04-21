#!/usr/bin/env python
"""机器人服务器 - 持续连接，等待客户端指令."""

import socket
import json
import threading
import time
from lerobot.robots.so_follower import SO100Follower, SO100FollowerConfig


class RobotServer:
    def __init__(self, host="127.0.0.1", port=8765, port_name="/dev/ttyACM0", robot_id="my_awesome_follower_arm"):
        self.host = host
        self.port = port
        self.port_name = port_name
        self.robot_id = robot_id
        self.robot = None
        self.server_socket = None
        self.running = False
        self.client_socket = None
        self.torque_locked = True
        self.connected = False
        self.connect_failed = False
        self.connect_error = None

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        print(f"Server listening on {self.host}:{self.port}")

        self.running = True

        print("Connecting to robot...")
        import threading
        robot_thread = threading.Thread(target=self.connect_robot, daemon=True)
        robot_thread.start()
        robot_thread.join()

        if self.connect_failed:
            print(f"Robot connection failed: {self.connect_error}")
            self.running = False
            self.server_socket.close()
            return

        self.accept_loop()

    def connect_robot(self):
        print(f"Connecting to robot at {self.port_name}...")
        try:
            self.config = SO100FollowerConfig(
                port=self.port_name,
            )
            self.config.id = self.robot_id
            self.robot = SO100Follower(self.config)
            self.robot.connect(calibrate=False)
            self.connected = True
            print("Robot connected!")
        except Exception as e:
            self.connect_failed = True
            self.connect_error = str(e)
            print(f"Failed to connect robot: {e}")
            raise

        import threading
        monitor_thread = threading.Thread(target=self.monitor_connection, daemon=True)
        monitor_thread.start()

    def monitor_connection(self):
        while self.running:
            time.sleep(3)
            if not self.connected:
                continue
            try:
                print("Monitor: checking connection...")
                self.robot.get_observation()
                print("Monitor: robot OK")
            except Exception as e:
                print(f"Arm disconnected! {e}")
                self.connected = False
                break

    def _get_torque_status(self):
        """Query actual torque status from robot hardware."""
        if not self.robot or not self.connected:
            return self.torque_locked
        try:
            motors = list(self.robot.bus.motors.keys())
            if not motors:
                return self.torque_locked
            first_motor = motors[0]
            torque_enable = self.robot.bus.read("Torque_Enable", first_motor)
            actual_locked = bool(torque_enable)
            self.torque_locked = actual_locked
            return actual_locked
        except Exception as e:
            print(f"Warning: Failed to read torque status: {e}")
            return self.torque_locked

    def accept_loop(self):
        while self.running:
            try:
                print("Waiting for client...")
                self.client_socket, addr = self.server_socket.accept()
                print(f"Client connected: {addr}")

                client_thread = threading.Thread(target=self.handle_client, daemon=True)
                client_thread.start()

            except Exception as e:
                if self.running:
                    print(f"Accept error: {e}")

    def handle_client(self):
        client_sock = self.client_socket
        buffer = ""
        while self.running and client_sock:
            try:
                data = client_sock.recv(1024)
                if not data:
                    break

                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self.process_command(line.strip(), client_sock)

            except (AttributeError, OSError) as e:
                print(f"Client error: {e}")
                break
            except Exception as e:
                print(f"Client error: {e}")
                break

        print("Client disconnected")

    def process_command(self, cmd, client_sock=None):
        if client_sock is None:
            client_sock = self.client_socket
        print(f"Executing: {cmd}")

        def send_resp(data):
            try:
                if client_sock:
                    client_sock.sendall((json.dumps(data) + "\n").encode("utf-8"))
            except Exception as e:
                print(f"Failed to send response: {e}")

        try:
            parts = cmd.split()
            command = parts[0].lower()

            if command == "ping":
                send_resp({"status": "ok", "pong": True})
                return

            if not self.connected:
                send_resp({"status": "error", "message": "Arm disconnected"})
                return

            if command == "get":
                obs = self.robot.get_observation()
                send_resp({"status": "ok", "observation": obs})

            elif command == "status":
                actual_locked = self._get_torque_status()
                send_resp({"status": "ok", "connected": self.connected, "locked": actual_locked})

            elif command == "set":
                if len(parts) < 2:
                    send_resp({"status": "error", "message": "Usage: set motor.pos=value ..."})
                    return

                action = {}
                for part in parts[1:]:
                    if "=" in part:
                        key, val = part.split("=", 1)
                        action[key] = float(val)

                self.robot.send_action(action)
                send_resp({"status": "ok", "action": action})

            elif command == "home":
                action = {f"{m}.pos": 0.0 for m in self.robot.bus.motors}
                self.robot.send_action(action)
                send_resp({"status": "ok", "action": action})

            elif command == "free":
                print("Disabling torque...")
                self.robot.bus.disable_torque()
                self.torque_locked = False
                send_resp({"status": "ok", "message": "Torque disabled", "locked": False})

            elif command == "lock":
                self.robot.bus.enable_torque()
                self.torque_locked = True
                send_resp({"status": "ok", "message": "Torque enabled", "locked": True})

            elif command == "quit":
                self.running = False
                send_resp({"status": "ok", "message": "Server shutting down"})

            else:
                send_resp({"status": "error", "message": f"Unknown command: {command}"})

        except Exception as e:
            send_resp({"status": "error", "message": str(e)})

    def send_response(self, data):
        try:
            if self.client_socket:
                self.client_socket.sendall((json.dumps(data) + "\n").encode("utf-8"))
                print(f"Response sent: {data}")
        except Exception as e:
            print(f"Failed to send response: {e}")

    def stop(self):
        self.running = False
        if self.robot:
            self.robot.disconnect()
        if self.server_socket:
            self.server_socket.close()
        print("Server stopped")


def main():
    import sys

    host = "127.0.0.1"
    port = 8765
    port_name = "/dev/ttyACM0"
    robot_id = "my_awesome_follower_arm"

    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port_name = sys.argv[i + 1]
        elif arg == "--host" and i + 1 < len(sys.argv):
            host = sys.argv[i + 1]
        elif arg == "--port-num" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
        elif arg == "--id" and i + 1 < len(sys.argv):
            robot_id = sys.argv[i + 1]

    server = RobotServer(host, port, port_name, robot_id)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()