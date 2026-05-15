# 图片内容提取功能设计

## 概述

新增 `extract_content()` 函数和 CLI `extract` 模式，支持用户通过自定义查询从图片中提取结构化内容，输出为 JSON 格式。支持两种模式：自由输出（AI 决定结构）和示例约束（用户提供 JSON 输出示例，AI 按示例格式输出）。

## 核心数据模型

```python
class ExtractionResult(BaseModel):
    success: bool                # 是否成功提取
    content: dict | list | None  # 提取到的 JSON 内容
    raw_response: str | None     # AI 原始响应文本（调试用）
    thought: str | None          # AI 推理过程
```

## 核心 API

```python
def extract_content(
    image_source: str | Path,
    query: str,
    example: dict | list | None = None,
) -> ExtractionResult
```

- `image_source`: 图片文件路径
- `query`: 查询提示词，如 "提取所有价格信息"、"识别图中的表格数据"
- `example`: 可选的 JSON 输出示例，提供时 AI 按照示例的格式和字段输出。例如 `{"name": "示例商品", "price": 99.9}`

内部使用 `Category.VISION` 模型，`response_format={"type": "json_object"}` 强制 JSON 输出。

## 系统提示词策略

提示词要求 AI 将响应包裹在统一结构中：

```json
{
  "thought": "推理过程...",
  "content": { ... }
}
```

- **无 example**：提示 AI 根据 query 自由提取，自主决定最合适的 JSON 结构
- **有 example**：提示 AI 严格参照示例的格式和字段输出，将实际提取的内容填入对应字段

## CLI 命令

```bash
# 自由提取
uiautoagent -m extract -i image.png -q "提取所有价格"

# 指定输出示例文件
uiautoagent -m extract -i image.png -q "提取商品信息" --example example.json
```

CLI 参数：
- `-i/--image`: 图片文件路径（必填）
- `-q/--query`: 查询提示词（必填）
- `--example`: JSON 输出示例文件路径（可选），例如 `{"name": "商品名", "price": 0}`

## 文件变更清单

| 文件 | 变更 |
|------|------|
| `src/uiautoagent/detector/content_extractor.py` | **新建** - 核心提取逻辑、数据模型 |
| `src/uiautoagent/cli/main.py` | 新增 `extract` 模式注册和参数解析 |
| `src/uiautoagent/__init__.py` | 导出 `extract_content`, `ExtractionResult` |
| `tests/test_content_extractor.py` | **新建** - 单元测试 |

## 实现细节

### 图片处理

复用 bbox_detector 中相同的 base64 编码方式：读取图片 → base64 → data URI 嵌入 `image_url` 消息。

### JSON 响应解析

使用 `safe_validate_json()` 进行 JSON 解析和 AI 修复（与 bbox_detector 一致），确保格式错误的响应也能被正确处理。

### 错误处理

- 图片文件不存在：抛出 FileNotFoundError
- AI 响应无法解析为 JSON：返回 `ExtractionResult(success=False, content=None, ...)`
- example 文件无法解析为 JSON：抛出 ValueError

## 测试策略

- 使用 mock 替代实际 AI 调用
- 测试用例覆盖：自由提取、示例约束提取、无效图片路径、AI 返回非法 JSON
