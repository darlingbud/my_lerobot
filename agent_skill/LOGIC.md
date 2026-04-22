# Robot Agent 逻辑梳理

## 架构概览

```
CLI (robot_agent.py main)
    ↓
RobotAgent (robot_agent.py 类)
    ↓ send_command()
RobotClient (robot_client.py)  ← Socket 客户端
    ↓
RobotServer (robot_server.py) ←→ 机械臂 (Feetech舵机)
```

- **RobotAgent**: 命令封装类，CLI 调用的接口
- **RobotClient**: Socket 客户端，发送命令给 server
- **RobotServer**: Socket 服务端，持久运行，管理机械臂

## 1. Server

### 职责

- 持久运行，管理机械臂连接
- 响应客户端命令
- 检测机械臂连接状态

### 特性

- **持久化**: server 启动后持续运行，直到显式关闭
- **启动前提**: 必须有物理机械臂连接，如果连接失败则退出
- **自动检测**: 每3秒检测机械臂连接，断开时自动关闭
- **两个状态**: `connected`(物理连接) 和 `locked`(扭矩锁定)

### 关键实现

- monitor_connection 使用 `robot.get_observation()` 而不是 `bus.read()`，因为 get_observation 是封装好的方法
- handle_client 使用本地 socket 引用，避免多线程时 socket 被覆盖

### 启动命令

```bash
python agent_skill/robot_agent.py --connect
```

内部启动 tmux 后台 server，然后检测机械臂连接。

---

## 2. Client

### 职责

- 发送命令给 server
- 每次 CLI 调用创建新 client

### 特性

- **连接检测**: 连接前检查 server 是否在线，使用 socket ping 检测
- **非持久**: 每次命令后关闭，不能启动/关闭 server
- **连接检查自动化**: 每次请求时检查 `connected` 状态，如果断开则自动关闭 server

### 与 Agent 生命周期同

- 每次 CLI 调用创建 1 个 RobotAgent 实例
- 每个 RobotAgent 实例创建 1 个 RobotClient 实例
- 同一 RobotAgent 实例内的所有方法调用共享同一个 client
- 如 `agent.free(); agent.record(); agent.replay()` 共用 1 个 client

---

## 3. record (录制)

### 使用

```bash
# 默认录制
python agent_skill/robot_agent.py --record 10

# 指定文件名
python agent_skill/robot_agent.py --record 10 --record-file my_record

# 指定文件名 (自动加.json)
python agent_skill/robot_agent.py --record 10 --record-file my_record.json

# 超时自动停止 (秒)
python agent_skill/robot_agent.py --record 10 --record-timeout 5
```

### 流程

```
CLI
  ↓
agent.record(frequency, filename)
  ├─ 1. 检查状态
  │     ├─ connected: True/False
  │     └─ locked: True/False
  │
  ├─ 2. locked时提示用户
  │     "Torque is locked! Continue? [y/N]: "
  │     ├─ "y" → 继续
  │     └─ 其他 → 取消
  │
  ├─ 3. 启动录制线程 _record_loop
  │     └─ 线程中循环发送 "get" 命令获取关节位置
  │
  ├─ 4. 主线程等待 Enter
  │     "Press Enter to stop recording..."
  │
  └─ 5. 停止并保存
        ├─ 设置 _recording = False
        ├─ join 线程
        └─ 保存到 JSON
```

### 关键实现

- **主线程等待 Enter**: record 方法内部等待 input()，不是 CLI 层处理
- **录制线程**: 用 socket 直接发送 "get"，不经过 RobotAgent 类的封装
- **locked 提示**: 如果 locked，提示用户确认是否继续录制（位置不会变化但仍可录制）

### 录制线程 `_record_loop`

```python
def _record_loop(frequency):
    while self._recording:
        # 1. 发送 "get" 命令获取观察
        client.send("get")

        # 2. 解析响应
        obs = response["observation"]

        # 3. 构建动作
        action = {
            "timestamp": time - start_time,
            "shoulder_pan.pos": ...,
            "shoulder_lift.pos": ...,
            "elbow_flex.pos": ...,
            "wrist_flex.pos": ...,
            "wrist_roll.pos": ...,
            "gripper.pos": ...,
        }

        # 4. 保存
        self._record_data["actions"].append(action)

        # 5. 等待
        time.sleep(1.0 / frequency)
```

### 保存文件

- 目录: `agent_skill/recordings/`
- 默认: `last_recorded.json`
- 结构:

```json
{
  "frequency": 10,
  "actions": [
    {
      "timestamp": 0.0,
      "shoulder_pan.pos": 1.23,
      "shoulder_lift.pos": -45.6,
      ...
    },
    ...
  ]
}
```

---

## 4. Replay (重放)

### 使用

```bash
# 默认1.0倍速
python agent_skill/robot_agent.py --replay

# 2.0倍速
python agent_skill/robot_agent.py --replay 2.0

# 0.5倍速 (慢动作)
python agent_skill/robot_agent.py --replay 0.5
```

### 流程

```
agent.replay(speed)
  │
  ├─ 1. 读取 last_recorded.json
  │
  ├─ 2. 插值 (可选)
  │     ├─ speed > 1: 插帧 (变慢)
  │     └─ speed < 1: 跳帧 (变快)
  │
  ├─ 3. 循环发送 "set" 命令
  │     "set shoulder_pan.pos=1.23 shoulder_lift.pos=-45.6 ..."
  │
  └─ 4. 等待间隔
        interval = 1.0 / replay_freq
```

### 插值

```python
def _interpolate_actions(actions, ratio):
    # ratio = (replay_freq / record_freq) / speed
    #
    # ratio > 1: 插帧 (慢速)
    # ratio < 1: 跳帧 (快速)
    # ratio = 1: 原始速度
```

---

## 5. Server 命令响应

| 命令                | 说明                   |
| ------------------- | ---------------------- |
| `ping`              | 返回 pong              |
| `status`            | 返回 connected, locked |
| `get`               | 返回关节位置观察       |
| `set key=value ...` | 设置关节目标位置       |
| `home`              | 所有关节回零位         |
| `free`              | 禁用扭矩               |
| `lock`              | 启用扭矩               |
| `quit`              | 退出 server            |

---

## 6. 命令响应流程 (同步阻塞模式)

### 设计原则

- **同步阻塞**: client 发送命令后等待 server 返回结果
- **server 等待**: server 执行动作完成后才返回结果
- **返回状态**: 成功返回 ok，失败返回 error + message

### 流程

```
Client                              Server
  |                                   |
  |-- send "set key=value" --------->   |
  |                                   |-- 执行动作
  |                                   |   ├─ 发送目标位置到电机
  |                                   |   ├─ 等待电机到达目标位置 (可选)
  |                                   |   └─ 返回结果
  |<-- response {status, ...} --------   |
  |   (阻塞等待)                       |
  |                                   |
  print(response)                     |
  client 退出                         |
```

### 返回值格式

**成功**:

```json
{"status": "ok", "action": {"shoulder_pan.pos": 1.23, ...}}
```

**失败**:

```json
{ "status": "error", "message": "Failed to write 'Torque_Enable' on id_=1" }
```

### 设计决策: 不阻塞等待

与 lerobot 保持一致，server 收到命令后立即返回，不等待机器人移动完成。

**理由**：

- lerobot 本身设计为非阻塞（用于高频控制场景）
- client 收到返回后即可执行其他操作
- client 可以自行决定是否等待

**可选实现**（已注释）：

- `_wait_for_goal`: 通过 Moving 标志位或 Present_Position 判断是否到达目标
- 如果需要阻塞等待，可以取消注释并调用此方法

---

## 6. 文件结构

```
# 之前分散在根目录
/home/donquixote/lerobot/
├── robot_server.py
├── robot_client.py
├── last_recorded.json
└── ...

# 现在整理到 agent_skill/ 目录
agent_skill/
├── robot_agent.py    # CLI + Agent类
├── robot_client.py  # Client类
├── robot_server.py  # Server类
├── recordings/     # 录制文件目录
│   └── last_recorded.json
├── README.md        # 使用说明
└── LOGIC.md        # 逻辑详解
```
