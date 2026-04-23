# Changelog

## [Unreleased]

### Added

- 新增 `HistoryEntry` Pydantic 模型，用于替代 dict 传递历史步骤上下文
- HTML 报告中显示截图相似度信息
- HTML 报告顶部显示任务结果（done/fail 时）
- `demo_find_and_click` 使用 `detect_element` 获取坐标，修复 find 模式无法点击的问题

### Changed

- 将 `knowledge` 参数统一重命名为 `context`，与 CLI 参数 `--context` 保持一致
  - `run_ai_task()` 参数 `knowledge` → `context`
  - `execute_ai_task()` 参数 `knowledge` → `user_context`
  - `build_user_prompt_with_memory()` 参数 `knowledge` → `user_context`
  - 中文显示名从"背景知识"改为"任务上下文"
  - CLI `--context-file` (`-cf`) 和 `--context` (`-c`) 参数保持不变
  - README.md 中的示例和说明已同步更新
- `_execute_action` 不再返回观察字符串，失败时直接抛出异常
- `Category.PLAN` 重命名为 `Category.VISION`，`Category.DETECT` 合并到 `VISION`
- AndroidController 从 subprocess + adb 命令改为 adbutils 库
- HTML 报告中 swipe 标注箭头改为红色
- `build_history_summary` 参数类型从 `list` 改为 `list[HistoryEntry]`
