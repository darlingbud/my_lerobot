#!/usr/bin/env python
"""Robot Agent Skill - client 非持久化，每次命令新建 client，server 手动启动/关闭."""

import sys
import os
import time
import socket
import subprocess
import json
import threading
import select

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(SCRIPT_DIR, "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)

sys.path.insert(0, SCRIPT_DIR)

from robot_client import RobotClient


class RobotAgent:
    def __init__(self, host="127.0.0.1", port=8765, port_name="/dev/ttyACM0", robot_id="my_awesome_follower_arm"):
        self.host = host
        self.port = port
        self.port_name = port_name
        self.robot_id = robot_id
        self.tmux_session = "robot_server"
        self.client = None
        self._safe_pos = {
            "shoulder_pan.pos": 1.126972201352359,
            "shoulder_lift.pos": -97.32999582811848,
            "elbow_flex.pos": 100.0,
            "wrist_flex.pos": 71.68443496801706,
            "wrist_roll.pos": 0.024420024420024333,
            "gripper.pos": 0.9946949602122015,
        }
        self._record_file = os.path.join(RECORDINGS_DIR, "last_recorded.json")
        self._recording = False
        self._record_data = None
        self._record_thread = None
        self._replay_freq = 100

    def is_server_online(self):
        """检查 server 是否运行"""
        for _ in range(3):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((self.host, self.port))
                sock.sendall(b"ping\n")
                data = sock.recv(1024)
                sock.close()
                return b"pong" in data
            except Exception:
                time.sleep(0.5)
        return False

    def check_server(self):
        """检查 server 是否启动，未启动则提示用户"""
        if not self.is_server_online():
            raise RuntimeError(
                f"Server not running on {self.host}:{self.port}\n"
                f"Please run: python agent_skill/robot_agent.py --connect"
            )

    def connect(self):
        """连接机械臂: 启动 server"""
        if self.is_server_online():
            if self.is_robot_connected():
                print(f"Server already running on {self.host}:{self.port}")
                return True
            else:
                print("Server running but robot disconnected, restarting...")
                self.disconnect()

        cmd = [
            "tmux", "new-session", "-d", "-s", self.tmux_session,
            f"python {SCRIPT_DIR}/robot_server.py --port {self.port_name} --host {self.host} --port-num {self.port} --id {self.robot_id}"
        ]

        print(f"Starting server in tmux session '{self.tmux_session}'...")
        subprocess.run(cmd, check=True)

        for _ in range(3):
            time.sleep(0.5)
            if self.is_server_online():
                if self.is_robot_connected():
                    print("Server is online and robot connected!")
                    return True
                else:
                    print("Server started but robot not connected, check the arm")
                    break

        self.disconnect()
        raise RuntimeError("Failed to connect robot. Make sure the arm is connected and run lerobot-find-port to find the correct port.")

    def is_robot_connected(self):
        """检查机械臂是否连接"""
        try:
            client = RobotClient(self.host, self.port)
            client.connect()
            resp = client.send("status")
            client.close()
            return resp.get("connected", False)
        except Exception:
            return False

    def disconnect(self):
        """关闭机械臂: 退出 server"""
        if self.is_server_online():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self.host, self.port))
                sock.sendall(b"quit\n")
                sock.close()
                print("Server stopped")
            except Exception:
                pass
        else:
            print("Server not running")

    def _get_client(self):
        """获取 client，复用连接"""
        self.check_server()
        if self.client is None:
            self.client = RobotClient(self.host, self.port)
            self.client.connect()
        return self.client

    def send_command(self, cmd):
        """发送命令 (自动检测连接状态)"""
        resp = self._get_client().send(cmd)
        if resp.get("status") == "error" and "disconnected" in resp.get("message", "").lower():
            print("Arm disconnected! Closing server...")
            self.disconnect()
            raise ConnectionError(resp.get("message"))
        return resp

    def _check_connected(self):
        """检查连接状态"""
        try:
            resp = self._get_client().send("ping")
            if not resp.get("connected", True):
                print("Arm disconnected! Closing server...")
                self.disconnect()
                return False
            return True
        except Exception:
            return False

    def get_observation(self):
        return self.send_command("get")

    def set_positions(self, **kwargs):
        cmd = "set " + " ".join(f"{k}={v}" for k, v in kwargs.items())
        return self.send_command(cmd)

    def home(self):
        return self.send_command("home")

    def zero_pos(self):
        return self.send_command("home")

    def safe_pos(self):
        return self.set_positions(**self._safe_pos)

    def free(self):
        self.safe_pos()
        time.sleep(1)
        return self.send_command("free")

    def lock(self):
        return self.send_command("lock")

    def status(self):
        return self.send_command("status")

    def go_safe_pos(self):
        """移动到 safety pos"""
        return self.set_positions(**self._safe_pos)

    def _record_loop(self, frequency):
        """录制循环 (在线程中运行)"""
        client = None
        while self._recording:
            try:
                if client is None:
                    client = self._get_client()
                client.socket.sendall(b"get\n")
                buffer = ""
                while "\n" not in buffer:
                    data = client.socket.recv(1024)
                    if not data:
                        break
                    buffer += data.decode("utf-8")
                obs = json.loads(buffer.split("\n")[0])
                state = obs.get("observation", {})
                action = {"timestamp": time.time() - getattr(self, "_record_start_time", time.time())}
                for joint in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
                    key = f"{joint}.pos"
                    if key in state:
                        action[key] = state[key]
                self._record_data["actions"].append(action)
            except Exception:
                client = None
                time.sleep(0.1)
                continue
            time.sleep(1.0 / frequency)
        if client:
            client.close()

    def recard(self, frequency=10, filename=None):
        """录制关节动作

        1. 检查状态
        2. 如果locked，提示用户确认
        3. 启动录制线程
        4. 等待Enter
        5. 停止并保存
        """
        obs = self.status()
        is_locked = obs.get("locked", True)
        is_connected = obs.get("connected", False)

        print(f"[Status] connected: {is_connected}, locked: {is_locked}")

        if is_locked:
            print("[Warning] Torque is locked! Recording will still work but positions may not change.")
            resp = input("Continue? [y/N]: ").strip().lower()
            if resp != "y":
                print("Cancelled.")
                return

        if filename is None:
            self._record_file = os.path.join(RECORDINGS_DIR, "last_recorded.json")
            print(f"[Default] {self._record_file}")
        else:
            if not filename.endswith(".json"):
                filename += ".json"
            self._record_file = os.path.join(RECORDINGS_DIR, filename)

        print(f"Saving to: {self._record_file}")
        print(f"Recording at {frequency}Hz... Press Enter to stop.")

        self._recording = True
        self._record_data = {"frequency": frequency, "actions": []}
        self._record_start_time = time.time()

        self._record_thread = threading.Thread(target=self._record_loop, args=(frequency,))
        self._record_thread.start()

        try:
            input()
        except KeyboardInterrupt:
            print("\nStopping...")

        self._recording = False
        if self._record_thread:
            self._record_thread.join(timeout=2)

        if self._record_data:
            with open(self._record_file, "w") as f:
                json.dump(self._record_data, f)
            print(f"Recorded {len(self._record_data['actions'])} actions -> {self._record_file}")
        else:
            print("No data recorded.")

    def replay(self, speed=1.0, filename=None):
        """重放录制的动作 (插值实现变速)

        Args:
            speed: 播放速度 (1.0=原始速度, >1=慢, <1=快)
            filename: 动作文件 (可选，默认 last_recorded.json)
        """
        self.check_server()
        if not self.is_server_online():
            raise RuntimeError(f"Server not running on {self.host}:{self.port}")

        if filename:
            replay_file = filename
        else:
            replay_file = self._record_file

        if not os.path.exists(replay_file):
            raise FileNotFoundError(f"No recorded file found: {replay_file}")

        print(f"Replaying: {replay_file}")

        with open(replay_file, "r") as f:
            data = json.load(f)

        recording_freq = data.get("frequency", 10)
        actions = data.get("actions", [])
        if not actions:
            raise ValueError(f"No actions in {replay_file}")

        joint_keys = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]

        ratio = (self._replay_freq / recording_freq) / speed
        interpolated = self._interpolate_actions(actions, ratio)

        interval = 1.0 / self._replay_freq

        print(f"Replaying {len(interpolated)} actions (original {len(actions)}, record_freq={recording_freq}) at {speed}x speed (replay_freq={self._replay_freq}Hz)...")

        client = self._get_client()
        for action in interpolated:
            positions = {}
            for joint in joint_keys:
                key = f"{joint}.pos"
                if key in action:
                    positions[key] = action[key]
            if positions:
                cmd = "set " + " ".join(f"{k}={v}" for k, v in positions.items())
                client.send(cmd)
            time.sleep(interval)

        print("Replay complete!")
        return True

    def _interpolate_actions(self, actions, ratio):
        """插值生成新动作序列"""
        if len(actions) < 2:
            return actions

        if ratio == 1:
            return actions

        joint_keys = [j + ".pos" for j in ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]]

        if ratio > 1:
            extra_steps = int(ratio)
            result = []

            for i in range(len(actions) - 1):
                curr = actions[i]
                next_ = actions[i + 1]

                result.append(curr)
                for step in range(1, extra_steps):
                    t = step / extra_steps
                    interpolated = {}
                    for key in joint_keys:
                        if key in curr and key in next_:
                            interpolated[key] = curr[key] + (next_[key] - curr[key]) * t
                    result.append(interpolated)

            result.append(actions[-1])
            return result

        step = int(1 / ratio)
        result = []
        for i in range(0, len(actions), step):
            result.append(actions[i])
        return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Robot Agent CLI")
    parser.add_argument("--connect", action="store_true", help="启动 server 并连接机械臂")
    parser.add_argument("--disconnect", action="store_true", help="退出 server")
    parser.add_argument("--get", action="store_true", help="获取观察")
    parser.add_argument("--set", type=str, help="设置位置, e.g., --set 'shoulder_pan.pos=30'")
    parser.add_argument("--home", action="store_true", help="回零位")
    parser.add_argument("--zero-pos", action="store_true", help="回零位 (同 --home)")
    parser.add_argument("--safe-pos", action="store_true", help="移动到安全位置")
    parser.add_argument("--free", action="store_true", help="解锁扭矩")
    parser.add_argument("--lock", action="store_true", help="锁定扭矩")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--go-safe-pos", action="store_true", help="移动到 safety pos")
    parser.add_argument("--recard", nargs="?", const=10, type=int, default=None, help="录制频率 Hz (默认10)")
    parser.add_argument("-f", "--recard-file", type=str, default=None, help="录制文件名")
    parser.add_argument("-t", "--recard-timeout", type=int, default=0, help="录制超时(秒), 0等待Enter")
    parser.add_argument("--replay", action="store_true", help="重放动作")
    parser.add_argument("-r", "--replay-file", type=str, default=None, help="重放文件")
    parser.add_argument("-s", "--replay-speed", type=float, default=1.0, help="重放速度 (默认1.0)")
    args = parser.parse_args()
    
    agent = RobotAgent()
    
    if args.connect:
        agent.connect()
    elif args.disconnect:
        agent.disconnect()
    elif args.status:
        print(agent.status())
    elif args.get:
        print(agent.get_observation())
    elif args.set:
        kwargs = {}
        for part in args.set.split():
            if "=" in part:
                k, v = part.split("=", 1)
                kwargs[k] = float(v)
        print(agent.set_positions(**kwargs))
    elif args.home:
        print(agent.home())
    elif args.zero_pos:
        print(agent.zero_pos())
    elif args.safe_pos:
        print(agent.safe_pos())
    elif args.free:
        print(agent.free())
    elif args.lock:
        print(agent.lock())
    elif args.go_safe_pos:
        print(agent.go_safe_pos())
    elif args.replay:
        speed = args.replay_speed if args.replay_speed > 0 else 1.0
        filename = args.replay_file
        if not filename:
            filename = args.recard_file
        if filename:
            if not filename.endswith(".json"):
                filename += ".json"
            replay_file = os.path.join(RECORDINGS_DIR, filename)
        else:
            replay_file = None
        agent.replay(speed, replay_file)
    elif args.recard is not None or args.recard_file:
        frequency = args.recard if args.recard is not None else 10
        agent.recard(frequency, args.recard_file)
    else:
        print("Robot Agent CLI")
        print("Usage:")
        print("  --connect     # 启动 server 并连接机械臂")
        print("  --disconnect  # 退出 server")
        print("  --status      # 查看状态")
        print("  --get         # 获取观察")
        print("  --set 'k=v'   # 设置位置")
        print("  --home        # 回零位")
        print("  --zero-pos    # 回零位 (同 --home)")
        print("  --safe-pos    # 移动到安全位置")
        print("  --free        # 解锁扭矩")
        print("  --lock        # 锁定扭矩")
        print("  --recard [Hz]  # 录制动作")
        print("  --replay [x]  # 重放动作")


if __name__ == "__main__":
    main()
