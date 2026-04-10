"""基于AI视觉模型获取元素bbox位置的检测器"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Type, TypeVar

import json

from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, ValidationError

_T = TypeVar("_T", bound=BaseModel)

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "").rstrip("/")
API_KEY = os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def __str__(self) -> str:
        return f"BBox(x1={self.x1}, y1={self.y1}, x2={self.x2}, y2={self.y2}, {self.width}x{self.height})"


class ElementLocation(BaseModel):
    thought: str | None = None
    found: bool
    bbox: list[int] | None
    description: str | None = None


class DetectionResult(BaseModel):
    found: bool
    bbox: BBox | None
    description: str | None = None
    thought: str | None = None


# --- 输出示例 ---
_example_found = ElementLocation(
    found=True,
    bbox=[100, 200, 300, 250],
    description="登录按钮",
    thought="在图片左上角发现了蓝色的登录按钮",
)
_example_not_found = ElementLocation(
    found=False, bbox=None, description=None, thought="图片中没有找到符合描述的元素"
)

_EXAMPLES = f"""
输出示例：
找到元素时：
{_example_found.model_dump_json(ensure_ascii=False)}

未找到元素时：
{_example_not_found.model_dump_json(ensure_ascii=False)}
"""

# 将示例加入系统提示
SYSTEM_PROMPT = f"""你是一个UI元素定位专家。用户会给你一张截图和需要查找的元素描述，你需要在图片中定位该元素并返回其边界框坐标。

假设图片尺寸统一为1000x1000，所有坐标均基于此尺寸给出。
请以JSON格式返回结果，包含你的思考过程(thought)。
如果找不到对应元素，found设为false，bbox设为null，并在thought中说明原因。

{_EXAMPLES}
"""

print("SYSTEM_PROMPT:", SYSTEM_PROMPT)


def safe_validate_json(
    raw: str | None,
    model_class: Type[_T],
    *,
    client: OpenAI,
    model_name: str,
    max_retries: int = 1,
) -> _T:
    """
    安全地解析并验证 JSON 模型，支持 AI 重新格式化。

    Args:
        raw: 原始 JSON 字符串
        model_class: Pydantic 模型类
        client: OpenAI 客户端（用于 AI 重新格式化）
        model_name: 使用的模型名称
        max_retries: AI 重新格式化的最大重试次数

    Returns:
        验证后的模型实例

    Raises:
        ValueError: raw 为空或 AI 格式化失败
    """
    if not raw or not raw.strip():
        raise ValueError("原始 JSON 字符串为空")

    # 尝试直接解析
    try:
        return model_class.model_validate_json(raw)
    except ValidationError:
        pass  # 继续尝试 AI 修复
    except json.JSONDecodeError:
        pass  # 继续尝试 AI 修复

    # AI 重新格式化
    schema = model_class.model_json_schema()
    properties = schema.get("properties", {})
    json_example = json.dumps(
        {
            k: (v.get("default") if "default" in v else None)
            for k, v in properties.items()
        },
        ensure_ascii=False,
        indent=2,
    )

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": f"""你是一个 JSON 修复专家。用户会给你一个格式错误的 JSON 字符串，你需要将其修复为符合指定 schema 的有效 JSON。

目标 schema:
{json.dumps(schema, ensure_ascii=False, indent=2)}

示例格式:
{json_example}

要求:
1. 只返回修复后的 JSON 字符串，不要有任何额外说明
2. 确保所有必需字段都存在
3. 保持原有数据语义，只修复格式问题""",
                    },
                    {"role": "user", "content": f"请修复以下 JSON:\n\n{raw}"},
                ],
                response_format={"type": "json_object"},
                max_tokens=2048,
                temperature=0.0,
            )
            fixed = response.choices[0].message.content
            if fixed:
                return model_class.model_validate_json(fixed)
        except (ValidationError, json.JSONDecodeError):
            if attempt < max_retries:
                continue
            raise

    raise ValueError(f"AI 格式化失败，无法解析为 {model_class.__name__}")


def _encode_image(image_source: str | Path) -> tuple[str, str]:
    """将图片编码为base64，返回 (base64_str, media_type)"""
    path = Path(image_source)
    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_types.get(suffix, "image/png")
    return base64.b64encode(path.read_bytes()).decode(), media_type


def detect_element(
    image_source: str | Path,
    query: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> DetectionResult:
    """
    在图片中检测指定元素并返回其bbox。

    Args:
        image_source: 图片路径
        query: 要查找的元素描述，如"登录按钮"、"搜索框"
        base_url: 覆盖环境变量中的BASE_URL
        api_key: 覆盖环境变量中的API_KEY
        model: 覆盖环境变量中的MODEL_NAME
    """
    key = api_key or API_KEY
    if not key:
        raise ValueError("API_KEY未设置，请在.env中配置或通过参数传入")

    client = OpenAI(
        base_url=base_url or BASE_URL,
        api_key=key,
        timeout=REQUEST_TIMEOUT,
    )
    model_name = model or MODEL_NAME

    b64, media_type = _encode_image(image_source)
    img = Image.open(image_source)
    w, h = img.size

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"请定位: {query}"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    },
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "element_location",
                "schema": ElementLocation.model_json_schema(),
            },
        },
        max_tokens=1024,
        temperature=0.0,
    )

    raw = response.choices[0].message.content
    print("Raw:", raw)
    loc = safe_validate_json(
        raw,
        ElementLocation,
        client=client,
        model_name=model_name,
    )

    bbox = None
    if loc.found and loc.bbox:
        x1, y1, x2, y2 = loc.bbox
        bbox = BBox(
            x1=max(0, int(x1 * w / 1000)),
            y1=max(0, int(y1 * h / 1000)),
            x2=min(w, int(x2 * w / 1000)),
            y2=min(h, int(y2 * h / 1000)),
        )

    return DetectionResult(
        found=loc.found, bbox=bbox, description=loc.description, thought=loc.thought
    )


def draw_bbox(
    image_source: str | Path, result: DetectionResult, output: str | Path | None = None
) -> Image.Image:
    """在图片上绘制检测到的bbox"""
    from PIL import ImageDraw

    img = Image.open(image_source).convert("RGB")
    if result.bbox:
        draw = ImageDraw.Draw(img)
        b = result.bbox
        draw.rectangle([b.x1, b.y1, b.x2, b.y2], outline="red", width=3)
        if result.description:
            draw.text((b.x1, b.y1 - 16), result.description, fill="red")

    if output:
        img.save(output)
    return img
