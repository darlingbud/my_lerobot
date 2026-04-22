#!/usr/bin/env python

# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""实机测试: SO Follower 力矩开启/关闭功能.

警告: 这个测试会真正控制电机运动，请在安全环境下运行!
运行: pytest tests/robots/test_so_follower_torque.py -v -s
"""

import time

import pytest

from lerobot.robots.so_follower import (
    SO100Follower,
    SO100FollowerConfig,
)


@pytest.fixture
def follower():
    """创建真实的 SO100Follower 实例，连接机器人."""
    port = "/dev/ttyACM0"
    cfg = SO100FollowerConfig(
        port=port,
        id="my_awesome_follower_arm",
        disable_torque_on_disconnect=True,
    )
    robot = SO100Follower(cfg)

    print(f"\n[Fixture] 连接到 {port}...")
    robot.connect(calibrate=False)

    yield robot

    print("\n[Fixture] 断开连接...")
    robot.disconnect()


def test_connect_and_enable_torque(follower):
    """测试1: 连接后力矩自动开启."""
    assert follower.is_connected
    print("\n[Test] 机器人已连接")

    obs = follower.get_observation()
    print(f"[Test] 读取到关节位置: {obs}")


def test_disable_torque(follower):
    """测试2: 禁用力矩后可以手动移动关节."""
    assert follower.is_connected

    print("\n[Test] 禁用力矩...")
    follower.bus.disable_torque()

    print("[Test] 警告: 现在可以手动移动机械臂!")
    time.sleep(2)


def test_enable_torque_after_disable(follower):
    """测试3: 禁用后再启用，电机恢复控制."""
    print("\n[Test] 禁用力矩...")
    follower.bus.disable_torque()

    time.sleep(1)

    print("[Test] 重新启用力矩...")
    follower.bus.enable_torque()

    print("[Test] 发送一个动作测试...")
    action = {f"{motor}.pos": 0.0 for motor in follower.bus.motors}
    follower.send_action(action)

    print("[Test] 动作已发送到电机")


def test_disconnect_disables_torque(follower):
    """测试4: 断开连接时禁用力矩."""
    pass


def test_send_action_and_read_observation(follower):
    """测试5: 发送动作并读取观察."""
    initial_obs = follower.get_observation()
    print(f"\n[Test] 初始位置: {initial_obs}")

    print("[Test] 发送动作...")
    action = {}
    for motor in follower.bus.motors:
        action[f"{motor}.pos"] = 0.0

    sent_action = follower.send_action(action)
    time.sleep(0.5)

    final_obs = follower.get_observation()
    print(f"[Test] 动作发送后: {sent_action}")
    print(f"[Test] 当前位置: {final_obs}")
