"""设备Agent使用示例 - 演示如何使用通用Agent框架"""

import os
from datetime import datetime
from pathlib import Path
import re

import yaml
from android_controller import AndroidController


def _str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(str, _str_presenter)
from device_agent import DeviceAgent, Action, ActionType, AgentConfig, TaskStep
from bbox_detector import detect_element, draw_bbox


# ========== 任务记忆系统 ==========


class TaskMemory:
    """任务记忆管理系统 - 存储和复用任务执行步骤"""

    def __init__(self, memory_file: str | Path = "task_memory.yaml"):
        self.memory_file = Path(memory_file)
        self._memories: list[dict] = self._load_memories()

    def _load_memories(self) -> list[dict]:
        """从文件加载记忆"""
        if self.memory_file.exists():
            try:
                data = yaml.safe_load(self.memory_file.read_text(encoding="utf-8"))
                return data.get("tasks", []) if data else []
            except Exception as e:
                print(f"⚠️  加载任务记忆失败: {e}")
                return []
        return []

    def _save_memories(self):
        """保存记忆到文件"""
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated_at": datetime.now().isoformat(),
            "total_tasks": len(self._memories),
            "tasks": self._memories,
        }
        # yaml会自动将多行字符串保存为块样式标量（|- 或 |+）
        self.memory_file.write_text(
            yaml.dump(
                data,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def find_similar_tasks(self, task: str, limit: int = 3) -> list[dict]:
        """
        查找相似的历史任务

        策略：
        1. 先用字符串完全匹配查找
        2. 如果找不到，再用AI查找
        3. 如果AI也找不到，返回空

        Args:
            task: 当前任务描述
            limit: 返回数量限制

        Returns:
            相似任务列表，按相似度排序
        """
        if not self._memories:
            return []

        # 步骤1：字符串完全匹配
        exact_matches = [
            m for m in self._memories if m["success"] and m["task"] == task
        ]
        if exact_matches:
            print(f"💡 找到完全相同的任务 ({len(exact_matches)}个)")
            # 按时间排序，返回最新的
            return sorted(exact_matches, key=lambda x: x["timestamp"], reverse=True)[
                :limit
            ]

        # 步骤2：使用AI查找相似任务
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
                api_key=os.getenv("API_KEY"),
            )

            # 构建历史任务列表（只返回成功任务）
            successful_tasks = [
                {"index": i, "task": m["task"], "summary": m.get("summary", "")}
                for i, m in enumerate(self._memories)
                if m["success"]
            ]

            if not successful_tasks:
                return []

            # 构建AI提示
            tasks_list = "\n".join(
                [f"{i}. {t['task']}" for i, t in enumerate(successful_tasks)]
            )

            prompt = f"""你是一个任务相似度分析专家。请从以下历史任务列表中，找出与当前任务最相似的{limit}个任务。

当前任务：{task}

历史任务列表：
{tasks_list}

请以JSON格式返回最相似任务的索引号（按相似度从高到低排序）：
{{
  "similar_indices": [索引号1, 索引号2, ...],
  "reasoning": "简短说明为什么这些任务相似"
}}

只返回索引号，不要返回任务内容。"""

            response = client.chat.completions.create(
                model=os.getenv("MODEL_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": "你是一个任务相似度分析专家。"},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0.0,
            )

            content = response.choices[0].message.content
            if not content:
                return []

            result = yaml.safe_load(content)
            indices = result.get("similar_indices", [])

            if not indices:
                print("💡 AI未找到相似任务")
                return []

            # 根据索引获取对应的记忆（需要转换回原始索引）
            similar_memories = []
            for idx in indices[:limit]:
                if 0 <= idx < len(successful_tasks):
                    original_idx = successful_tasks[idx]["index"]
                    similar_memories.append(self._memories[original_idx])

            if similar_memories:
                print(f"💡 AI找到相似任务: {result.get('reasoning', '')}")

            return similar_memories

        except Exception as e:
            print(f"⚠️  AI相似度分析失败: {e}")
            return []

    def save_task(
        self,
        task: str,
        history: list[TaskStep],
        success: bool,
        summary: str | None = None,
    ):
        """
        保存任务记忆

        Args:
            task: 任务描述
            history: 执行历史
            success: 是否成功
            summary: Markdown格式的任务总结
        """
        memory = {
            "task": task,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "total_steps": len(history),
            "summary": summary or "",
        }

        self._memories.append(memory)
        self._save_memories()

    def format_for_ai(self, similar_tasks: list[dict]) -> str:
        """将相似任务格式化为AI可读的参考信息"""
        if not similar_tasks:
            return "（无相关历史任务）"

        lines = ["## 相似历史任务经验参考"]
        for i, task_mem in enumerate(similar_tasks, 1):
            status = "✅ 成功" if task_mem["success"] else "❌ 失败"
            lines.append(f"\n### {i}. {task_mem['task']} - {status}")

            summary = task_mem.get("summary", "")
            if summary:
                # 直接使用Markdown内容
                lines.append(summary)
            else:
                lines.append("- 无总结信息")

        # 在末尾添加过期提示
        lines.append(
            "\n**⚠️ 注意: 以上经验可能随APP更新失效，请根据当前屏幕实际情况灵活调整**"
        )

        return "\n".join(lines)


def _summarize_task(task: str, history: list[TaskStep], success: bool) -> str:
    """
    使用AI总结任务执行结果，生成Markdown格式的经验总结

    Args:
        task: 任务描述
        history: 执行历史
        success: 是否成功

    Returns:
        Markdown格式的任务总结
    """
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("API_KEY"),
        )

        # 构建操作历史摘要
        steps_summary = []
        for h in history:
            status = "✅" if h.success else "❌"
            action = h.action
            if action.type == ActionType.TAP and action.target:
                steps_summary.append(f"{status} 点击: {action.target}")
            elif action.type == ActionType.INPUT and action.text:
                steps_summary.append(f"{status} 输入: {action.text}")
            elif action.type == ActionType.SWIPE:
                steps_summary.append(f"{status} 滑动: {action.direction}")
            elif action.type == ActionType.BACK:
                steps_summary.append(f"{status} 返回")
            elif action.type == ActionType.WAIT:
                steps_summary.append(f"{status} 等待")

        steps_text = "\n".join(steps_summary)

        prompt = f"""请分析以下任务执行历史，生成经验总结（Markdown格式）。

任务: {task}
结果: {"成功" if success else "失败"}

执行步骤:
{steps_text}

请以Markdown格式返回经验总结，包含成功做法和错误尝试。

成功任务示例：
```markdown
成功完成，共6步

# 正确操作步骤

1. 点击 设置
2. 点击 个人资料
3. 点击 昵称
4. 输入 kitty
5. 滑动 down
6. 点击 保存

# 错误尝试（请避免）

- 点击"修改资料"按钮无效（此按钮无法修改昵称，应该点击"昵称"）
- 向左滑动没找到目标（页面需要向下滑动才能看到昵称选项）
```

失败任务示例：
```markdown
任务失败，共尝试5步

# 执行过的操作

1. 点击 设置
2. 点击 个人资料
3. 点击 账号设置（无效，此按钮不存在）
4. 向下滑动（没找到目标）

# 失败原因

- 找不到"账号设置"入口，可能需要先完成其他步骤
- 向下滑动后仍未发现目标选项
```

要求：
1. 按照示例格式生成Markdown
2. 只返回Markdown内容，不要用代码块包裹
3. 紧凑格式，列表项之间不要空行"""

        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            messages=[
                {
                    "role": "system",
                    "content": "你是一个任务总结专家，擅长分析操作历史并提取关键信息。",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1024,
            temperature=0.0,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("AI返回空响应")
        return _compress_markdown(content)

    except Exception as e:
        print(f"⚠️  AI总结失败，不保存: {e}")


def _clarify_task(task: str) -> str:
    """
    使用AI将用户输入的任务描述重新表述为清晰、无歧义的操作指令。

    Args:
        task: 用户原始任务描述（可能存在语法或语义问题）

    Returns:
        经过AI重新表述的清晰任务描述
    """
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("API_KEY"),
        )

        response = client.chat.completions.create(
            model=os.getenv("MODEL_NAME", "gpt-4o"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个手机自动化任务解析专家。"
                        "用户会给你一段手机操作任务描述，可能存在语法错误、表达不清或语义歧义。"
                        "请将其重新表述为一句清晰、完整、无歧义的操作指令。"
                        "只返回重新表述后的任务描述，不要添加任何解释。"
                    ),
                },
                {"role": "user", "content": task},
            ],
            max_tokens=256,
            temperature=0.0,
        )

        clarified = (response.choices[0].message.content or "").strip()
        if clarified and clarified != task:
            print(f"✏️  任务已澄清: {task!r} → {clarified!r}")
            return clarified
        return task

    except Exception as e:
        print(f"⚠️  任务澄清失败，使用原始描述: {e}")
        return task


def _compress_markdown(md: str) -> str:
    # 移除代码块标记
    if md.startswith("```"):
        md = re.sub(r"^```[\w]*\n", "", md)  # 移除开头的```和可选的语言标记
        md = re.sub(r"\n```\s*$", "", md)  # 移除结尾的```

    # 多个空行 -> 一个
    md = re.sub(r"\n{3,}", "\n\n", md)

    # 列表之间的空行去掉
    md = re.sub(r"^(\s*[-*+] .+)\n+(?=\s*[-*+] )", r"\1\n", md, flags=re.MULTILINE)

    # 数字列表
    md = re.sub(r"^(\s*\d+\. .+)\n+(?=\s*\d+\. )", r"\1\n", md, flags=re.MULTILINE)

    return md.strip()


# 全局任务记忆实例
_task_memory = TaskMemory()


def get_task_memory() -> TaskMemory:
    """获取全局任务记忆实例"""
    return _task_memory


def demo_manual_control():
    """演示手动控制Agent执行任务（适用于已知步骤的任务）"""
    print("=" * 50)
    print("📱 设备Agent - 手动控制模式")
    print("=" * 50)

    # 检查设备
    devices = AndroidController.list_devices()
    if not devices:
        print("❌ 未检测到Android设备，请确保ADB已连接")
        return

    print(f"✅ 检测到设备: {devices[0]}")

    # 创建Agent
    controller = AndroidController(devices[0])
    agent = DeviceAgent(
        controller,
        config=AgentConfig(
            max_steps=20,
            save_screenshots=True,
        ),
    )

    info = controller.get_device_info()
    print(f"📋 设备信息: {info['model']} ({info['width']}x{info['height']})\n")

    # 示例：打开应用并执行操作（手动步骤）
    steps = [
        Action(
            type=ActionType.TAP,
            thought="打开应用",
            target="微信图标",
        ),
        Action(
            type=ActionType.WAIT,
            thought="等待应用启动",
            wait_ms=2000,
        ),
        Action(
            type=ActionType.TAP,
            thought="点击搜索框",
            target="搜索框",
        ),
        Action(
            type=ActionType.INPUT,
            thought="输入搜索关键词",
            text="test",
        ),
        Action(
            type=ActionType.DONE,
            thought="任务完成",
        ),
    ]

    # 执行步骤
    for action in steps:
        agent.step(action)

    # 保存历史
    agent.save_history()
    agent.print_summary()


def demo_ai_assisted_task(task: str = "修改昵称为kitty"):
    """
    演示AI辅助任务执行 - AI自主决策并完成任务

    Args:
        task: 要执行的任务描述
    """
    print("=" * 50)
    print("📱 设备Agent - AI自主决策模式")
    print("=" * 50)

    # 配置AI API
    if not os.getenv("API_KEY"):
        print("⚠️  未配置API_KEY，跳过AI示例")
        return

    # 检查设备
    devices = AndroidController.list_devices()
    if not devices:
        print("❌ 未检测到Android设备")
        return

    # 创建Agent
    controller = AndroidController(devices[0])
    agent = DeviceAgent(
        controller,
        config=AgentConfig(max_steps=30, save_screenshots=True, verbose=True),
    )

    info = controller.get_device_info()
    print(f"📋 设备信息: {info['model']} ({info['width']}x{info['height']})")

    print(f"\n🎯 任务: {task}")

    # 用AI澄清任务描述
    task = _clarify_task(task)

    print("🤖 AI将自主分析屏幕并决策每一步操作...\n")

    # 执行AI自主任务
    execute_ai_task(agent, task)


# ========== AI决策辅助函数 ==========


def _get_system_prompt() -> str:
    """获取系统提示词"""
    return """你是一个手机操作专家。用户会给你一个任务和当前手机屏幕截图，你需要分析屏幕并决定下一步操作。

## 利用历史经验
用户会提供相似历史任务的执行步骤，请参考这些成功经验：
- 优先尝试历史任务中成功的操作模式
- 如果历史任务显示某个元素描述有效，使用相同的描述
- 注意历史任务中的关键步骤顺序

可用操作类型：
1. tap - 点击屏幕上的元素（需要指定target描述元素，如"搜索按钮"）
2. input - 输入文本（需要指定text内容）
3. swipe - 滑动屏幕（需要指定direction: up/down/left/right）
4. back - 返回上一页
5. wait - 等待（需要指定wait_ms毫秒数）
6. done - 任务完成（当任务已完成时）
7. fail - 任务失败（当无法继续时）

请以JSON格式返回你的决策：
{
  "type": "操作类型",
  "thought": "为什么执行这个操作",
  "target": "目标元素描述（仅tap时需要，其他操作省略此字段）",
  "text": "输入文本（仅input时需要，其他操作省略此字段）",
  "direction": "滑动方向（仅swipe时需要，值为up/down/left/right之一，其他操作省略此字段）",
  "wait_ms": 等待毫秒数（仅wait时需要，默认1000，其他操作省略此字段）",
  "return_result": true（仅done时需要，表示任务需要返回观察结果）
  "result": "任务返回的结果或答案（仅done时需要）"
}

重要：
- 只包含你使用的操作类型所需的字段，不要包含空字符串或null值
- 例如：tap操作只需要type、thought、target三个字段
- 当任务需要返回观察结果时，done操作必须包含return_result和result字段

注意：
- 优先参考历史任务的成功步骤
- 分析屏幕时要仔细，确保能找到目标元素
- 如果找不到元素，可以尝试滑动或返回
- 任务完成后使用done
- 无法继续时使用fail
- input类型操作前需要先tap对应的输入框
- 如果任务要求返回信息（如"查看好友发了什么消息"），done时必须设置return_result:true并在result中描述结果"""


def _build_history_summary(history: list) -> str:
    """构建历史摘要字符串"""
    if not history:
        return "（这是第一步，无历史记录）"

    lines = []
    for h in history:
        status = "✅" if h["success"] else "❌"
        action = h["action"]

        # 构建动作详情
        parts = [f"类型: {action['type']}"]
        if action.get("thought"):
            parts.append(f"思考: {action['thought']}")
        if action.get("target"):
            parts.append(f"目标: {action['target']}")
        if action.get("text"):
            parts.append(f"输入: {action['text']}")
        if action.get("direction"):
            parts.append(f"方向: {action['direction']}")
        if action.get("wait_ms"):
            parts.append(f"等待: {action['wait_ms']}ms")

        details = ", ".join(parts)
        obs = f" → {h['observation']}" if h.get("observation") else ""
        lines.append(f"[步骤{h['step']}] {status} {details}{obs}")

    return "\n".join(lines)


def _build_user_prompt_with_memory(
    task: str, context: dict, memory_reference: str
) -> str:
    """构建用户消息（包含历史任务参考）"""
    history_summary = _build_history_summary(context["history"])
    device_info = context["device_info"]

    return f"""任务：{task}

设备信息：{device_info["model"]} ({device_info["width"]}x{device_info["height"]})

{memory_reference}

## 当前任务执行历史
{history_summary}

## 当前屏幕
请参考上方相似历史任务的经验，分析当前屏幕并决定下一步操作："""


def _encode_screenshot(screenshot_path: str | Path) -> str:
    """编码截图为base64"""
    import base64

    with open(screenshot_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _call_ai_decision(
    client, model: str, system_prompt: str, user_prompt: str, screenshot_b64: str
) -> dict:
    """调用AI决策API"""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=1024,
        temperature=0.0,
    )

    decision_text = response.choices[0].message.content
    if not decision_text:
        raise ValueError("AI返回空响应")

    print(f"🧠 AI思考: {decision_text[:200]}...")

    import json

    return json.loads(decision_text)


def _parse_action_from_decision(decision: dict) -> Action:
    """从AI决策解析出Action对象"""
    action_type = ActionType(decision.get("type", "fail"))

    # 构建Action参数，过滤掉空字符串
    kwargs = {
        "type": action_type,
        "thought": decision.get("thought") or "",
    }

    # 只在非空时添加可选字段
    if decision.get("target"):
        kwargs["target"] = decision["target"]
    if decision.get("text"):
        kwargs["text"] = decision["text"]
    if decision.get("direction") and decision["direction"] in (
        "up",
        "down",
        "left",
        "right",
    ):
        kwargs["direction"] = decision["direction"]
    if decision.get("wait_ms"):
        kwargs["wait_ms"] = decision["wait_ms"]
    if decision.get("return_result"):
        kwargs["return_result"] = True
    if decision.get("result"):
        kwargs["result"] = decision["result"]

    return Action(**kwargs)


def _handle_task_status(
    action: Action, agent: DeviceAgent, task: str, task_memory: TaskMemory
) -> bool:
    """
    处理任务状态并保存记忆

    Returns:
        True表示任务应该结束，False表示继续执行
    """
    if action.type == ActionType.DONE:
        print("\n🎉 任务完成！")

        # 如果需要返回结果
        if action.return_result and action.result:
            print(f"\n📋 任务结果:")
            print(f"   {action.result}")
            print(f"\n📸 当前截图: {agent.get_current_screenshot()}")

        agent.save_history()
        agent.print_summary()

        # 保存成功任务记忆
        summary = _summarize_task(task, agent.history, success=True)
        task_memory.save_task(task, agent.history, success=True, summary=summary)
        print(f"💾 已保存任务记忆")

        return True

    if action.type == ActionType.FAIL:
        print(f"\n❌ AI认为任务无法完成: {action.thought}")
        agent.save_history()
        agent.print_summary()

        # 保存失败任务记忆
        summary = _summarize_task(task, agent.history, success=False)
        task_memory.save_task(task, agent.history, success=False, summary=summary)

        return True

    return False


def _handle_ai_error(agent: DeviceAgent, error: Exception):
    """处理AI决策错误"""
    print(f"❌ AI决策出错: {error}")
    agent.step(
        Action(
            type=ActionType.BACK,
            thought="AI决策出错，尝试返回",
        )
    )


# ========== 主函数 ==========


def execute_ai_task(agent: DeviceAgent, task: str):
    """
    使用AI自主执行任务，支持任务记忆复用

    Args:
        agent: 设备Agent
        task: 任务描述
    """
    from openai import OpenAI

    # 初始化AI客户端
    client = OpenAI(
        base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("API_KEY"),
    )
    model = os.getenv("MODEL_NAME", "gpt-4o")
    max_steps = agent.config.max_steps

    # 获取任务记忆
    task_memory = get_task_memory()
    similar_tasks = task_memory.find_similar_tasks(task)

    if similar_tasks:
        print(f"💡 找到 {len(similar_tasks)} 个相似历史任务，将作为参考:")
        for i, task_mem in enumerate(similar_tasks, 1):
            status = "✅" if task_mem["success"] else "❌"
            print(f"   {i}. {status} {task_mem['task']}")
    else:
        print("💡 未找到相似历史任务")

    # 缓存系统提示词
    system_prompt = _get_system_prompt()

    for step in range(max_steps):
        print(f"\n{'=' * 50}")
        print(f"🤖 AI决策 - 步骤 {step + 1}/{max_steps}")
        print(f"{'=' * 50}")

        # 准备数据
        screenshot_path = agent.get_current_screenshot()
        context = agent.get_context_for_ai()
        screenshot_b64 = _encode_screenshot(screenshot_path)

        # 构建用户消息（包含历史任务参考）
        memory_reference = task_memory.format_for_ai(similar_tasks)
        user_prompt = _build_user_prompt_with_memory(task, context, memory_reference)

        # 调用AI决策
        try:
            decision = _call_ai_decision(
                client, model, system_prompt, user_prompt, screenshot_b64
            )
            action = _parse_action_from_decision(decision)

            # 执行动作
            agent.step(action)

            # 检查任务状态
            if _handle_task_status(action, agent, task, task_memory):
                return

        except Exception as e:
            _handle_ai_error(agent, e)

    # 达到最大步数
    print(f"\n⚠️  达到最大步数限制 ({max_steps})，任务可能未完成")
    agent.save_history()
    agent.print_summary()

    # 保存未完成任务记忆
    task_memory.save_task(task, agent.history, success=False)


def demo_find_and_click():
    """演示简单的查找并点击"""
    print("=" * 50)
    print("📱 设备Agent - 查找并点击")
    print("=" * 50)

    devices = AndroidController.list_devices()
    if not devices:
        print("❌ 未检测到Android设备")
        return

    controller = AndroidController(devices[0])
    agent = DeviceAgent(controller)

    # 查找并点击元素
    agent.step(
        Action(
            type=ActionType.TAP,
            thought="查找并点击返回按钮",
            target="返回按钮",
        )
    )

    agent.save_history()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="设备Agent示例 - AI自主执行手机任务",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["manual", "ai", "find"],
        default="find",
        help="运行模式",
    )
    parser.add_argument(
        "-t",
        "--task",
        default="修改昵称为kitty",
        help="要执行的任务描述（ai模式使用）",
    )
    parser.add_argument(
        "-s",
        "--serial",
        default=None,
        help="指定设备序列号（默认使用第一个可用设备）",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="最大执行步数",
    )
    args = parser.parse_args()

    if args.mode == "manual":
        demo_manual_control()
    elif args.mode == "ai":
        demo_ai_assisted_task(args.task)
    else:
        demo_find_and_click()
