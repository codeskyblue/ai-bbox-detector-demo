"""AI 规划响应模型 - 使用联合类型为每个 action type 定义特定参数"""

from typing import Literal, Union
from pydantic import BaseModel, Field, TypeAdapter
import json
import logging

logger = logging.getLogger(__name__)


class BasePlanAction(BaseModel):
    """基础规划动作 - 所有类型共有的字段"""

    thought: str = ""
    log: str = ""


class TapPlanAction(BasePlanAction):
    """点击操作"""

    type: Literal["tap"] = "tap"
    target: str = Field(..., description="目标元素描述，如'搜索按钮'")


class LongPressPlanAction(BasePlanAction):
    """长按操作"""

    type: Literal["long_press"] = "long_press"
    target: str = Field(..., description="目标元素描述")
    long_press_ms: int | None = Field(
        default=800, ge=0, description="长按毫秒数，默认800"
    )


class InputPlanAction(BasePlanAction):
    """输入文本操作"""

    type: Literal["input"] = "input"
    text: str = Field(..., description="要输入的文本内容")


class SwipePlanAction(BasePlanAction):
    """滑动操作"""

    type: Literal["swipe"] = "swipe"

    # 方式1: 按方向滑动
    direction: Literal["up", "down", "left", "right"] | None = Field(
        default=None, description="滑动方向（up/down/left/right）"
    )

    # 方式2: 按位置描述滑动
    swipe_start: str | None = Field(
        default=None, description="滑动起始位置描述，如'头像图标'"
    )
    swipe_end: str | None = Field(
        default=None, description="滑动结束位置描述，如'设置按钮'"
    )


class BackPlanAction(BasePlanAction):
    """返回操作"""

    type: Literal["back"] = "back"


class WaitPlanAction(BasePlanAction):
    """等待操作"""

    type: Literal["wait"] = "wait"
    wait_ms: int = Field(default=1000, ge=0, description="等待毫秒数，默认1000")


class AppLaunchPlanAction(BasePlanAction):
    """启动应用操作"""

    type: Literal["app_launch"] = "app_launch"
    app_id: str = Field(
        ...,
        description="应用包名（Android）或 Bundle ID（iOS），如 com.tencent.mm",
    )


class AppStopPlanAction(BasePlanAction):
    """停止应用操作"""

    type: Literal["app_stop"] = "app_stop"
    app_id: str = Field(
        ...,
        description="应用包名（Android）或 Bundle ID（iOS）",
    )


class AppRebootPlanAction(BasePlanAction):
    """重启应用操作"""

    type: Literal["app_reboot"] = "app_reboot"
    app_id: str = Field(
        ...,
        description="应用包名（Android）或 Bundle ID（iOS）",
    )


class DonePlanAction(BasePlanAction):
    """任务完成操作"""

    type: Literal["done"] = "done"
    return_result: bool = Field(default=False, description="是否返回观察结果")
    result: str | None = Field(default=None, description="任务返回的结果或答案")


class FailPlanAction(BasePlanAction):
    """任务失败操作"""

    type: Literal["fail"] = "fail"


# 联合类型，包含所有可能的操作类型
PlanAction = Union[
    TapPlanAction,
    LongPressPlanAction,
    InputPlanAction,
    SwipePlanAction,
    BackPlanAction,
    WaitPlanAction,
    AppLaunchPlanAction,
    AppStopPlanAction,
    AppRebootPlanAction,
    DonePlanAction,
    FailPlanAction,
]


# 保持向后兼容的 PlanResponse 别名
PlanResponse = PlanAction


def get_action_examples_prompt() -> str:
    """获取操作类型说明和示例的 Markdown 文本"""

    return """## 操作类型说明

**所有操作都包含这三个必需字段：**
- `type`: 操作类型（如 "tap", "swipe" 等）
- `thought`: 为什么执行这个操作
- `log`: 简洁说明要做的事情

每种操作还有自己特有的字段，下面按类型列出：

---

### 1. tap - 点击元素

```json
{
  "target": "搜索按钮"
}
```

---

### 2. long_press - 长按元素

```json
{
  "target": "消息内容",
  "long_press_ms": 1000
}
```
*`long_press_ms` 可选，默认800*

---

### 3. input - 输入文本

```json
{
  "text": "python"
}
```

---

### 4. swipe - 滑动屏幕

**方式1：按方向滑动**
```json
{
  "direction": "up"
}
```

**方式2：按位置描述滑动**
```json
{
  "swipe_start": "个人资料图标",
  "swipe_end": "设置按钮"
}
```
*direction 和 swipe_start/swipe_end 二选一*

---

### 5. back - 返回上一页

无额外字段

---

### 6. wait - 等待

```json
{
  "wait_ms": 2000
}
```
*`wait_ms` 可选，默认1000*

---

### 7. app_launch - 启动应用

```json
{
  "app_id": "com.tencent.mm"
}
```

---

### 8. app_stop - 停止应用

```json
{
  "app_id": "com.tencent.mm"
}
```

---

### 9. app_reboot - 重启应用

```json
{
  "app_id": "com.tencent.mm"
}
```

---

### 10. done - 任务完成

**普通完成：** 无额外字段

**返回结果：**
```json
{
  "return_result": true,
  "result": "共有15个好友在线"
}
```

---

### 11. fail - 任务失败

无额外字段

---

## 使用说明

1. **只包含必需字段**：每个操作只需要包含它特有的字段
2. **省略默认值**：如 `long_press_ms` 默认800，`wait_ms` 默认1000，无需指定
3. **input 前置**：输入前需要先用 tap 点击输入框
"""


# TypeAdapter 用于解析 Union 类型
_plan_adapter = TypeAdapter(PlanAction)


def parse_plan_response(raw: str) -> PlanAction:
    """
    解析 AI 返回的 JSON 为 PlanAction（Union 类型）

    Args:
        raw: JSON 字符串（可能被 markdown 代码块包裹，或有多个 JSON）

    Returns:
        解析后的 PlanAction 实例

    Raises:
        ValueError: 解析失败时
    """
    import re

    cleaned = raw.strip()

    # 移除 markdown 代码块标记
    if cleaned.startswith("```"):
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()

    try:
        print("RAW:", cleaned)
        data = json.loads(cleaned)
        print("DD:", data)
        return _plan_adapter.validate_python(data)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse plan response: {e}")
        logger.warning(f"Extracted JSON: {cleaned[:200]}")
        raise ValueError(f"无法解析 AI 返回的 JSON: {e}") from e


def get_plan_attr(plan: PlanAction, attr: str, default=None):
    """
    安全地获取 PlanAction 的属性值

    由于 PlanAction 是 Union 类型，不同类型有不同的属性，
    这个函数可以安全地获取属性，不存在时返回默认值

    Args:
        plan: PlanAction 实例
        attr: 属性名
        default: 默认值

    Returns:
        属性值或默认值
    """
    return getattr(plan, attr, default)
