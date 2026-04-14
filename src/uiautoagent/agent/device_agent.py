"""通用设备AI Agent - 支持自主决策和执行任务"""

from __future__ import annotations

import json
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from uiautoagent.controller.base import DeviceController, SwipeDirection


class ActionType(str, Enum):
    """动作类型"""

    TAP = "tap"  # 点击元素
    INPUT = "input"  # 输入文本
    SWIPE = "swipe"  # 滑动
    BACK = "back"  # 返回
    WAIT = "wait"  # 等待
    DONE = "done"  # 任务完成
    FAIL = "fail"  # 任务失败


class Action(BaseModel):
    """执行的动作"""

    type: ActionType
    thought: str  # 为什么要执行这个动作
    target: str | None = None  # 目标元素描述（tap用）
    position: tuple[int, int] | None = None  # 具体坐标
    text: str | None = None  # 输入的文本
    direction: SwipeDirection | None = None  # 滑动方向
    swipe_start: str | None = None  # 滑动起始位置描述
    swipe_end: str | None = None  # 滑动结束位置描述
    wait_ms: int = 1000  # 等待时间
    return_result: bool = False  # 是否返回当前屏幕的观察结果
    result: str | None = None  # 任务返回的结果/答案

    class Config:
        use_enum_values = True

    def __str__(self) -> str:
        if self.type == ActionType.TAP:
            pos = f"@{self.position}" if self.position else ""
            return f"点击: {self.target}{pos}"
        elif self.type == ActionType.INPUT:
            return f"输入: {self.text}"
        elif self.type == ActionType.SWIPE:
            if self.swipe_start and self.swipe_end:
                return f"滑动: {self.swipe_start} → {self.swipe_end}"
            return f"滑动: {self.direction}"
        elif self.type == ActionType.BACK:
            return "返回"
        elif self.type == ActionType.WAIT:
            return f"等待 {self.wait_ms}ms"
        elif self.type == ActionType.DONE:
            return f"✅ 完成: {self.thought}" if self.thought else "✅ 完成"
        elif self.type == ActionType.FAIL:
            return f"❌ 失败: {self.thought}" if self.thought else "❌ 失败"
        return self.type


class TaskStep(BaseModel):
    """任务执行步骤记录"""

    step_number: int
    screenshot_path: str
    action: Action
    observation: str  # 执行后的观察结果
    success: bool
    timestamp: float

    class Config:
        use_enum_values = True


class AgentConfig(BaseModel):
    """Agent配置"""

    max_steps: int = 20  # 最大执行步数
    tasks_dir: str = "tasks"  # 任务目录父目录
    save_screenshots: bool = True
    verbose: bool = True


class DeviceAgent:
    """通用设备自动化AI代理（支持Android/iOS等）"""

    def __init__(
        self,
        controller: DeviceController,
        config: AgentConfig | None = None,
    ):
        """
        初始化Agent

        Args:
            controller: 设备控制器（Android/iOS等）
            config: Agent配置
        """
        self.controller = controller
        self.config = config or AgentConfig()
        self.history: list[TaskStep] = []
        self.step_count = 0

        # 创建带时间戳的唯一任务目录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.task_dir = Path(self.config.tasks_dir) / f"task_{timestamp}"
        self.task_dir.mkdir(parents=True, exist_ok=True)

        # 截图子目录
        self.screenshot_dir = self.task_dir / "screenshots"
        self.screenshot_dir.mkdir(exist_ok=True)

    def _take_screenshot(self) -> Path:
        """截取屏幕并保存"""
        if self.config.save_screenshots:
            path = self.screenshot_dir / f"step_{self.step_count:03d}.png"
        else:
            path = Path("temp_screenshot.png")
        return self.controller.screenshot(path)

    def _log(self, message: str):
        """打印日志"""
        if self.config.verbose:
            print(message)

    def _detect_and_tap(self, screenshot_path: Path, target: str) -> tuple[bool, str]:
        """检测并点击元素"""
        from uiautoagent.detector import detect_element

        result = detect_element(screenshot_path, target)
        if result.found and result.bbox:
            self.controller.tap_bbox(result.bbox)
            return True, f"已点击: {result.description or target}"
        return False, f"未找到元素: {target}"

    def _detect_and_swipe(
        self, screenshot_path: Path, start: str, end: str
    ) -> tuple[bool, str]:
        """检测起始和结束位置并执行滑动（一次API调用同时检测两个元素）"""
        from uiautoagent.detector import detect_elements

        # 一次API调用同时检测起始和结束位置
        results = detect_elements(screenshot_path, [start, end])

        start_result = results.get(start)
        end_result = results.get(end)

        if not start_result or not start_result.found or not start_result.bbox:
            return False, f"未找到起始位置: {start}"

        if not end_result or not end_result.found or not end_result.bbox:
            return False, f"未找到结束位置: {end}"

        # 获取中心点坐标
        x1, y1 = start_result.bbox.center
        x2, y2 = end_result.bbox.center

        self.controller.swipe(x1, y1, x2, y2)
        return (
            True,
            f"已从 {start_result.description or start} 滑动到 {end_result.description or end}",
        )

    def _execute_action(self, action: Action, screenshot_path: Path) -> str:
        """执行动作并返回观察结果"""
        try:
            if action.type == ActionType.TAP:
                if action.position:
                    x, y = action.position
                    self.controller.tap(x, y)
                    return f"已点击坐标 ({x}, {y})"
                elif action.target:
                    success, msg = self._detect_and_tap(screenshot_path, action.target)
                    return msg

            elif action.type == ActionType.INPUT:
                if action.text:
                    self.controller.input_text(action.text)
                    return f"已输入: {action.text}"
                return "未提供输入文本"

            elif action.type == ActionType.SWIPE:
                if action.swipe_start and action.swipe_end:
                    success, msg = self._detect_and_swipe(
                        screenshot_path, action.swipe_start, action.swipe_end
                    )
                    return msg
                elif action.direction:
                    self.controller.swipe_direction(action.direction)
                    return f"已向{action.direction}滑动"
                return "未提供滑动参数（方向或起止位置描述）"

            elif action.type == ActionType.BACK:
                self.controller.back()
                return "已点击返回键"

            elif action.type == ActionType.WAIT:
                time.sleep(action.wait_ms / 1000)
                return f"已等待 {action.wait_ms}ms"

            elif action.type in (ActionType.DONE, ActionType.FAIL):
                return action.thought or ""

            return f"未知动作类型: {action.type}"

        except Exception as e:
            return f"执行出错: {e}"

    def step(self, action: Action) -> TaskStep:
        """
        执行一步操作

        Args:
            action: 要执行的动作

        Returns:
            执行的步骤记录
        """
        step_start = time.time()
        self.step_count += 1

        # 截图（记录操作前的屏幕状态）
        screenshot_path = self._take_screenshot()

        # 执行动作
        observation = self._execute_action(action, screenshot_path)

        # 判断是否成功
        success = (
            not observation.startswith("未找到")
            and not observation.startswith("执行出错")
            and action.type != ActionType.FAIL
        )

        # 计算执行耗时
        elapsed = time.time() - step_start

        # 记录步骤
        step = TaskStep(
            step_number=self.step_count,
            screenshot_path=str(screenshot_path),
            action=action,
            observation=observation,
            success=success,
            timestamp=time.time(),
        )
        self.history.append(step)

        # 日志输出
        status = "✅" if success else "❌"
        self._log(f"\n[步骤 {self.step_count}] {status} 动作: {action}")
        if action.thought:
            self._log(f"思考: {action.thought}")
        self._log(f"观察: {observation}")
        self._log(f"耗时: {elapsed:.2f}s")

        return step

    def get_current_screenshot(self) -> Path:
        """获取当前屏幕截图（用于AI决策）"""
        return self._take_screenshot()

    def save_history(self, path: str | Path | None = None):
        """保存任务历史到JSON文件"""
        if path is None:
            path = self.task_dir / "history.json"

        # 从全局TokenTracker获取统计
        from uiautoagent.ai import TokenTracker

        total_tokens = TokenTracker.get_total()
        stats_by_category = TokenTracker.get_stats()

        data = {
            "total_steps": len(self.history),
            "total_tokens": {
                "prompt_tokens": total_tokens.prompt,
                "completion_tokens": total_tokens.completion,
                "total_tokens": total_tokens.total,
            },
            "tokens_by_category": {
                k: {
                    "prompt_tokens": v.prompt,
                    "completion_tokens": v.completion,
                    "total_tokens": v.total,
                }
                for k, v in stats_by_category.items()
            },
            "steps": [step.model_dump() for step in self.history],
        }
        Path(path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._log(f"\n📝 任务历史已保存至: {path}")

        # 同时保存可读的文本摘要
        self._save_text_summary()

    def _save_text_summary(self):
        """保存可读的文本摘要"""
        summary_path = self.task_dir / "summary.txt"

        # 从全局TokenTracker获取统计
        from uiautoagent.ai import TokenTracker

        total_tokens = TokenTracker.get_total()
        stats_by_category = TokenTracker.get_stats()

        # 计算费用
        input_cost, output_cost, total_cost = TokenTracker.calculate_cost(
            total_tokens.prompt, total_tokens.completion
        )

        lines = [
            "=" * 60,
            f"任务执行摘要 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            f"总步骤数: {len(self.history)}",
            "截图目录: screenshots/",
            "",
            "Token使用统计:",
            f"  输入Token: {total_tokens.prompt:,}",
            f"  输出Token: {total_tokens.completion:,}",
            f"  总计Token: {total_tokens.total:,}",
            f"  总费用: ¥{total_cost:.4f} (输入:¥{input_cost:.4f}, 输出:¥{output_cost:.4f})",
        ]

        # 按分类显示token统计
        if stats_by_category:
            # 分类名称映射
            category_names = {
                "decision": "AI决策思考",
                "clarify": "任务澄清",
                "summarize": "任务总结",
            }

            lines.append("")
            lines.append("按用途分类:")
            for category, stats in stats_by_category.items():
                _, _, cat_total_cost = TokenTracker.calculate_cost(
                    stats.prompt, stats.completion
                )
                name = category_names.get(category, category)
                lines.append(
                    f"  [{name}] {stats.total:,} tokens (¥{cat_total_cost:.4f}) - 输入:{stats.prompt:,}, 输出:{stats.completion:,}"
                )

        lines.extend(
            [
                "",
                "步骤详情:",
                "-" * 60,
            ]
        )

        for step in self.history:
            status = "✅ 成功" if step.success else "❌ 失败"
            lines.append(f"\n[步骤 {step.step_number}] {status}")
            lines.append(f"  动作: {step.action}")
            if step.action.thought:
                lines.append(f"  思考: {step.action.thought}")
            lines.append(f"  观察: {step.observation}")
            lines.append(f"  截图: screenshots/step_{step.step_number:03d}.png")

        lines.append("\n" + "=" * 60)

        summary_path.write_text("\n".join(lines), encoding="utf-8")
        self._log(f"📄 文本摘要已保存至: {summary_path}")

    def print_summary(self):
        """打印任务执行摘要"""
        # 从全局TokenTracker获取统计
        from uiautoagent.ai import TokenTracker

        total_tokens = TokenTracker.get_total()
        stats_by_category = TokenTracker.get_stats()

        # 计算费用
        _, _, total_cost = TokenTracker.calculate_cost(
            total_tokens.prompt, total_tokens.completion
        )

        print("\n" + "=" * 50)
        print("📋 任务执行摘要")
        print("=" * 50)
        for step in self.history:
            status = "✅" if step.success else "❌"
            print(f"[{step.step_number}] {status} {step.action}")
        print("=" * 50)

        # 打印 token 使用统计
        if total_tokens.total > 0:
            print(
                f"📊 Token: {total_tokens.total:,} (输入:{total_tokens.prompt:,}, 输出:{total_tokens.completion:,}) | 💰 费用: ¥{total_cost:.4f}"
            )

            # 按分类详细统计
            if stats_by_category:
                # 分类名称映射
                category_names = {
                    "decision": "AI决策思考",
                    "clarify": "任务澄清",
                    "summarize": "任务总结",
                }

                print("\n按用途分类:")
                for category, stats in stats_by_category.items():
                    _, _, cat_cost = TokenTracker.calculate_cost(
                        stats.prompt, stats.completion
                    )
                    name = category_names.get(category, category)
                    print(
                        f"  [{name}] {stats.total:,} tokens (输入:{stats.prompt:,}, 输出:{stats.completion:,}) | ¥{cat_cost:.4f}"
                    )
        print("=" * 50)

    def get_context_for_ai(self) -> dict[str, Any]:
        """
        获取当前上下文信息，供AI决策使用

        Returns:
            包含所有历史步骤和当前截图的上下文字典
        """
        return {
            "step_count": self.step_count,
            "history": [
                {
                    "step": s.step_number,
                    "action": s.action.model_dump(),
                    "observation": s.observation,
                    "success": s.success,
                }
                for s in self.history  # 所有步骤
            ],
            "current_screenshot": str(self.get_current_screenshot()),
            "device_info": self.controller.get_device_info(),
        }
