# Robot Agent Skill

> 需要 conda 环境 `lerobot`
>
> ```bash
> conda activate lerobot
> ```

Robot Agent 是一个机械臂控制代理，基于 client-server 架构。

## 架构

```
CLI (robot_agent.py)
    ↓ 命令
RobotAgent (robot_agent.py)
    ↓ send()
RobotClient (robot_client.py)
    ↓ socket
RobotServer (robot_server.py) ←→ 机械臂
```

- **RobotAgent**: 命令封装类
- **RobotClient**: Socket 客户端，发送命令给 server
- **RobotServer**: Socket 服务端，持久运行，管理机械臂连接

## 快速开始

```bash
# 0. 硬件测试 (测试机械臂和相机端口)
python agent_skill/robot_agent.py --test
python agent_skill/robot_agent.py --test-arm        # 测试机械臂端口
python agent_skill/robot_agent.py --test-camera opencv   # 测试 opencv 相机

# 1. 连接机械臂 (启动 server)
python agent_skill/robot_agent.py --connect

# 2. 解锁扭矩 (可手动移动机械臂)
python agent_skill/robot_agent.py --free

# 3. 录制动作
python agent_skill/robot_agent.py --record 10

# 4. 重放动作
python agent_skill/robot_agent.py --replay
```

## 常用命令

| 命令                    | 说明                         |
| ----------------------- | ---------------------------- |
| `--connect`             | 连接机械臂 (启动 server)     |
| `--disconnect`          | 断开连接 (停止 server)       |
| `--status`              | 查看状态                     |
| `--get`                 | 获取关节位置                 |
| `--set "key=value ..."` | 设置关节位置                 |
| `--free`                | 解锁扭矩                     |
| `--lock`                | 锁定扭矩                     |
| `--home`                | 回零位                       |
| `--safe-pos`            | 移动到安全位置               |
| `--record [Hz]`         | 录制动作 (默认10Hz)          |
| `--replay [x]`          | 重放动作 (默认1.0倍速)       |
| `--test`                | 测试所有硬件 (机械臂 + 相机) |
| `--test-arm`            | 测试机械臂端口               |
| `--test-camera`         | 测试相机 (opencv/realsense)  |

## 录制 (record)

```bash
# 默认录制，Enter停止
python agent_skill/robot_agent.py --record 10

# 指定文件名 (自动加.json)
python agent_skill/robot_agent.py --record 10 --record-file demo

# 超时自动停止 (秒)
python agent_skill/robot_agent.py --record 10 --record-timeout 5
```

- locked 状态下会提示确认
- 录制文件保存在 `agent_skill/recordings/`
- 默认文件: `last_recorded.json`

## 重放 (replay)

```bash
# 默认1.0倍速
python agent_skill/robot_agent.py --replay

# 2.0倍速 (快)
python agent_skill/robot_agent.py --replay 2.0

# 0.5倍速 (慢)
python agent_skill/robot_agent.py --replay 0.5
```

## 设置位置

```bash
# 单个关节
python agent_skill/robot_agent.py --set "shoulder_pan.pos=30"

# 多个关节
python agent_skill/robot_agent.py --set "shoulder_pan.pos=30 elbow_flex.pos=45"
```

## 状态说明

- `connected`: 机械臂物理连接状态
- `locked`: 扭矩锁定 (True=锁定, False=可手动移动)

## 文件结构

```
agent_skill/
├── robot_agent.py    # CLI + Agent类
├── robot_client.py  # Client类
├── robot_server.py  # Server类
├── recordings/     # 录制文件目录
│   └── last_recorded.json
├── README.md        # 使用说明
└── LOGIC.md        # 逻辑详解
```

## 注意事项

- 必须先运行 `lerobot-find-port` 确认串口存在，否则 server 启动失败
- 确保 tmux 已安装
- 端口 8765 只能被 server 占用
- 如果端口被占用但不是 server，提示用户 kill
- 机械臂断开时，server 自动检测并关闭
- server 本质是机械臂代理，必须在机械臂物理连接成功后才存在
