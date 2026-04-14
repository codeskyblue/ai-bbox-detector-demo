# UIAutoAgent

AI 驱动的 UI 自动化框架，支持视觉定位和自主任务执行。

## 特性

- 🎯 AI 视觉定位元素，无需 DOM
- 🤖 自主决策执行任务
- 🧠 任务记忆学习
- 📱 Android / iOS 设备支持
- 🔧 灵活的模型配置（支持不同场景使用不同模型）

## 安装

```bash
uv sync
cp .env.example .env
# 编辑 .env 配置 API_KEY 和模型
```

## 配置

在 `.env` 文件中配置 OpenAI 兼容的 API：

```bash
# 基础配置
BASE_URL=https://api.openai.com/v1
API_KEY=sk-xxx
MODEL_NAME=doubao-seed-2.0-pro

# 可选：为不同场景配置不同的模型
MODEL_DECISION=gpt-4o      # AI决策模型（需要视觉能力）
MODEL_DETECT=doubao-seed-2.0-pro             # 元素检测模型（需要视觉能力）
MODEL_TEXT=gpt-4o-mini          # 文本处理模型（总结、澄清等）

# 请求超时时间（秒）
REQUEST_TIMEOUT=60
```

### 场景说明

| 场景 | 说明 | 模型要求 |
|------|------|----------|
| `DECISION` | AI 决策下一步操作 | 需要视觉能力 |
| `DETECT` | UI 元素检测定位 | 需要视觉能力 |
| `TEXT` | 文本处理（总结、澄清、搜索） | 纯文本，无视觉要求 |

## 快速开始

```bash
# AI 自主执行任务
uv run uiautoagent -m ai -t "修改昵称为 kitty"

# 指定iOS设备
uv run uiautoagent -m ai -t "修改昵称为 kitty" -p ios

# 其他模式
uv run uiautoagent -m find    # 查找并点击
uv run uiautoagent -m manual  # 手动控制
```

## Python API

### AI 自主执行任务

```python
from uiautoagent import run_ai_task

# 最简单的用法 - AI 自主完成任务
result = run_ai_task("修改昵称为 kitty")
if result.success:
    print(f"任务完成: {result.result}")
else:
    print(f"任务失败: {result.result}")

# 如果任务需要返回观察结果（如"查看有多少个好友"）
result = run_ai_task("查看有多少个好友")
if result.success:
    print(f"好友数量: {result.result}")  # 例如: "有5个好友"
```

### 元素检测

```python
from uiautoagent import detect_element, draw_bbox

# 检测元素
result = detect_element("screenshot.png", "登录按钮")
if result.found:
    print(f"位置: {result.bbox}")  # BBox(x, y, width, height)
    draw_bbox("screenshot.png", result.bbox, "result.png")
```

### 设备控制

```python
from uiautoagent import AndroidController, IOSController, SwipeDirection

# 控制Android设备
controller = AndroidController()
controller.tap(500, 1000)  # 点击坐标
controller.swipe_direction(SwipeDirection.UP)  # 向上滑动
controller.input_text("hello")  # 输入文本
controller.back()  # 返回

# 控制iOS设备
controller = IOSController()  # 自动检测USB设备
# 或指定URL连接: IOSController(url="http://localhost:8100")
# 或指定UDID: IOSController(udid="00008101-...")
controller.tap(500, 1000)
controller.swipe_direction(SwipeDirection.UP)
controller.input_text("hello")
controller.home()  # Home键
```

### Agent 手动控制

```python
from uiautoagent import DeviceAgent, Action, ActionType, AgentConfig

agent = DeviceAgent(
    AndroidController(),
    config=AgentConfig(max_steps=20, save_screenshots=True)
)

# 执行动作
agent.step(Action(type=ActionType.TAP, thought="点击登录", target="登录按钮"))
agent.step(Action(ActionType.WAIT, wait_ms=2000))
agent.step(Action(type=ActionType.INPUT, text="username"))
```

### 任务记忆

```python
from uiautoagent import get_task_memory

memory = get_task_memory()
similar = memory.find_similar_tasks("修改昵称")
for task in similar:
    print(f"{task['task']} - {'成功' if task['success'] else '失败'}")
```

### 直接调用 AI

```python
from uiautoagent import Category, chat_completion

# 使用 Category 枚举指定场景（推荐）
response = chat_completion(
    category=Category.TEXT,  # 文本处理场景
    messages=[{"role": "user", "content": "总结这段文本"}],
    max_tokens=500,
)
content = response.choices[0].message.content

# 不同场景会自动使用对应的模型
decision_response = chat_completion(
    category=Category.DECISION,  # 决策场景
    messages=[{"role": "user", "content": "分析这张图片"}],
    # 注意：决策场景需要提供图片
)
```

### Token 统计

```python
from uiautoagent import TokenTracker

# Token 统计会自动记录
tracker = TokenTracker()

# 获取所有场景的统计
stats = TokenTracker.get_stats()
for category, stat in stats.items():
    print(f"{category}: {stat.total} tokens")

# 获取总统计
total = TokenTracker.get_total()
print(f"总计: {total.total} tokens")

# 计算费用
input_cost, output_cost, total_cost = TokenTracker.calculate_cost(
    total.prompt, total.completion
)
print(f"费用: ¥{total_cost:.4f}")
```

AI 视觉定位可以精准识别屏幕上的 UI 元素：

**原始截图**
![sample.png](assets/sample.png)

**检测结果** - 查询"登录按钮"
![result.png](assets/result.png)

检测到元素位置：`BBox(x=540, y=1320, width=240, height=120)`

## 要求

- Python 3.10+
- OpenAI 兼容的 API
  - 视觉场景（`DECISION`、`DETECT`）需要支持 Vision 的模型
  - 文本场景（`TEXT`）使用普通聊天模型即可
- Android 需要 ADB
- iOS 需要 WebDriverAgent 和 [wdapy](https://github.com/openatx/wdapy)，设备列表需要 `idevice_id`（libimobiledevice）或 `tidevice`

## License

[LICENSE](LICENSE)
