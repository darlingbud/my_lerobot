import time

from lerobot.robots.so_follower import SO100Follower, SO100FollowerConfig


def main():
    # 1. 初始化 Follower 机械臂
    # 注意：这里只初始化 follower，不需要 leader

    robot_config = SO100FollowerConfig(
        port="/dev/ttyACM0",
        id="my_awesome_follower_arm",
    )
    robot = SO100Follower(robot_config)

    # 2. 连接机械臂
    print("Connecting to robot...")

    robot.connect()
    print("Connected!")
    print("Available motors:", list(robot.bus.motors.keys()))
    try:
        # 3. 获取当前关节位置（可选，用于确认初始状态）
        present_positions = robot.get_observation()
        print(f"Current positions: {present_positions}")

        # 4. 定义目标关节角度 (弧度 rad)
        # SO-101 通常有 6 个或更多自由度，具体取决于你的配置
        # 警告：请确保这些角度在机械臂的安全范围内！
        # 这里假设是 6 轴机械臂，全部设为 0 (中间位置) 作为示例
        target_positions = {
            "shoulder_pan.pos": 0,
            "shoulder_lift.pos": 0,
            "elbow_flex.pos": 0,
            "wrist_flex.pos": 0,
            "wrist_roll.pos": 0,
            "gripper.pos": 0,
        }

        # 如果你想移动到某个特定姿态，需要填入对应的弧度值
        # 例如: target_positions = np.array([0.1, -0.2, 0.5, 0.0, 0.0, 0.0])

        # 5. 发送动作指令
        # send_action 通常会立即执行，或者根据内部插补器平滑移动
        print(f"Moving to positions: {target_positions}")
        robot.send_action(target_positions)

        # # 等待机械臂运动完成 (简单粗暴的方式，实际项目中可能需要查询状态)
        time.sleep(2)

        # # 6. 移动到另一个位置
        #  # 修改目标位置值
        actions = {
            "shoulder_pan.pos": 30,  # 肩部水平旋转到30度
            "shoulder_lift.pos": -20,  # 肩部向上抬-20度
            "elbow_flex.pos": 45,  # 肘部弯曲45度
            "wrist_flex.pos": 10,  # 腕部俯仰10度
            "wrist_roll.pos": 0,  # 腕部旋转0度
            "gripper.pos": 1.0,  # 夹爪完全闭合（1.0）
        }

        # 发送新动作
        robot.send_action(actions)

        # robot.bus.disable_torque()
        time.sleep(20)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # 7. 断开连接
        print("Disconnecting...")
        robot.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
