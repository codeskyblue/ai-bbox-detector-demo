"""AI 客户端管理 - 统一 OpenAI 客户端初始化"""

from __future__ import annotations

import os
from collections import defaultdict
from enum import Enum
from functools import lru_cache
from threading import Lock
from typing import Any

import httpx
from openai import OpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, Field


class Category(str, Enum):
    """AI 调用场景分类

    用于区分不同用途的 AI 调用，便于统计 token 使用量和配置不同模型。
    """

    DECISION = "decision"
    DETECT = "detect"
    TEXT = "text"
    DEFAULT = "default"


# Token价格配置（人民币/百万tokens）
TOKEN_PRICE_INPUT = 4.8
TOKEN_PRICE_OUTPUT = 24.0

# 不同场景的模型配置
_MODEL_CONFIG: dict[Category, str] = {
    Category.DECISION: os.getenv("MODEL_DECISION", ""),
    Category.DETECT: os.getenv("MODEL_DETECT", ""),
    Category.TEXT: os.getenv("MODEL_TEXT", ""),
}
_DEFAULT_MODEL = os.getenv("MODEL_NAME", "gpt-4o")


class TokenStats(BaseModel):
    """Token使用量统计"""

    prompt: int = Field(default=0, ge=0, description="输入token数量")
    completion: int = Field(default=0, ge=0, description="输出token数量")
    total: int = Field(default=0, ge=0, description="总token数量")

    def add(self, prompt: int, completion: int) -> None:
        """增加token数量"""
        self.prompt += prompt
        self.completion += completion
        self.total += prompt + completion


# 全局token统计（线程安全）
_token_stats: dict[str, TokenStats] = defaultdict(TokenStats)
_stats_lock = Lock()

# 最近一次记录的token信息
_last_record: TokenStats | None = None
_record_lock = Lock()


class TokenTracker:
    """Token使用量追踪器"""

    def __init__(self, category: Category | str = Category.DEFAULT):
        """
        初始化追踪器

        Args:
            category: 用途分类，如 Category.DECISION, Category.SUMMARIZE
        """
        self.category = category if isinstance(category, str) else category.value

    def record(self, response) -> TokenStats:
        """
        记录API响应的token使用量

        Args:
            response: OpenAI API响应对象

        Returns:
            token使用量TokenStats对象
        """
        usage = getattr(response, "usage", None)
        if usage:
            stats = TokenStats(
                prompt=usage.prompt_tokens,
                completion=usage.completion_tokens,
                total=usage.total_tokens,
            )

            with _stats_lock:
                _token_stats[self.category].add(stats.prompt, stats.completion)

            # 保存最近一次记录
            global _last_record
            with _record_lock:
                _last_record = stats

            return stats

        return TokenStats()

    @staticmethod
    def get_stats() -> dict[str, TokenStats]:
        """
        获取所有token统计

        Returns:
            按分类统计的token使用量
        """
        with _stats_lock:
            # 返回副本，避免外部修改
            return {k: TokenStats(**v.model_dump()) for k, v in _token_stats.items()}

    @staticmethod
    def get_total() -> TokenStats:
        """
        获取总token使用量

        Returns:
            总token使用量TokenStats对象
        """
        with _stats_lock:
            total = TokenStats()
            for stats in _token_stats.values():
                total.add(stats.prompt, stats.completion)
            return total

    @staticmethod
    def get_last_record() -> TokenStats | None:
        """
        获取最近一次记录的token信息

        Returns:
            最近一次的token使用量TokenStats对象，如果没有则返回None
        """
        with _record_lock:
            return _last_record

    @staticmethod
    def calculate_cost(
        prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float, float]:
        """
        计算token费用

        Args:
            prompt_tokens: 输入token数量
            completion_tokens: 输出token数量

        Returns:
            (输入费用, 输出费用, 总费用) 单位：人民币
        """
        input_cost = prompt_tokens * TOKEN_PRICE_INPUT / 1_000_000
        output_cost = completion_tokens * TOKEN_PRICE_OUTPUT / 1_000_000
        total_cost = input_cost + output_cost
        return input_cost, output_cost, total_cost

    @staticmethod
    def reset():
        """重置所有统计"""
        with _stats_lock:
            _token_stats.clear()
        global _last_record
        with _record_lock:
            _last_record = None


@lru_cache(maxsize=1)
def _get_ai_client() -> OpenAI:
    """
    获取 AI 客户端实例（单例模式，内部使用）

    注意：此客户端会忽略系统代理设置（trust_env=False）

    Returns:
        OpenAI 客户端实例
    """
    # 设置超时时间（秒）
    timeout = float(os.getenv("REQUEST_TIMEOUT", "60"))

    # 创建不使用系统代理的 HTTP 客户端
    http_client = httpx.Client(trust_env=False, timeout=timeout)

    return OpenAI(
        base_url=os.getenv("BASE_URL", "https://api.openai.com/v1"),
        api_key=os.getenv("API_KEY"),
        http_client=http_client,
        timeout=timeout,
    )


def get_ai_model(category: Category | str | None = None) -> str:
    """
    获取 AI 模型名称

    Args:
        category: 可选的场景分类，用于获取特定场景的模型。
                  如果为 None，返回默认模型。
                  支持 Category 枚举值或对应的字符串值

    Returns:
        模型名称，如 "gpt-4o"

    Example:
        >>> from uiautoagent.ai import get_ai_model, Category
        >>> get_ai_model()  # 获取默认模型
        'gpt-4o'
        >>> get_ai_model(Category.DECISION)  # 获取决策场景的模型
        'gpt-4o-mini'
        >>> get_ai_model("decision")  # 也支持字符串
        'gpt-4o-mini'
    """
    if category:
        # 如果是 Category 枚举，转换为字符串值
        category_value = category.value if isinstance(category, Category) else category
        # 查找对应的 Category 枚举
        for cat in Category:
            if cat.value == category_value and cat in _MODEL_CONFIG:
                model = _MODEL_CONFIG[cat]
                if model:
                    return model
    return _DEFAULT_MODEL


def get_ai_config() -> dict:
    """
    获取 AI 配置信息

    Returns:
        包含 base_url, model, timeout 等配置的字典
    """
    return {
        "base_url": os.getenv("BASE_URL", "https://api.openai.com/v1"),
        "model": _DEFAULT_MODEL,
        "timeout": int(os.getenv("REQUEST_TIMEOUT", "30")),
    }


def chat_completion(
    category: Category | str,
    model: str | None = None,
    **kwargs: Any,
) -> ChatCompletion:
    """
    调用 OpenAI Chat Completions API 并自动统计 token 使用量

    这是一个统一的 AI 调用入口，封装了 chat.completions.create 和 token 统计。
    所有需要调用 AI 的地方都应该使用这个函数。

    Args:
        category: 用途分类，用于 token 统计和模型选择。
                  支持 Category 枚举值或对应的字符串值
                  如果配置了对应的环境变量（如 MODEL_DECISION），将使用该模型，
                  否则使用默认模型（MODEL_NAME）。
        model: 可选，显式指定模型。如果提供，将覆盖 category 的模型选择。
        **kwargs: 传递给 chat.completions.create 的所有参数，包括：
            - messages: 消息列表
            - max_tokens: 最大生成 token 数
            - temperature: 温度参数
            - response_format: 响应格式
            - 等等...

    Returns:
        ChatCompletion: API 响应对象

    Example:
        >>> from uiautoagent.ai import chat_completion, Category
        >>> # 使用 Category 枚举（推荐）
        >>> response = chat_completion(
        ...     category=Category.DECISION,
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     max_tokens=100,
        ... )
        >>> # 也支持字符串（向后兼容）
        >>> response = chat_completion(
        ...     category="decision",
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     max_tokens=100,
        ... )
        >>> # 显式指定模型
        >>> response = chat_completion(
        ...     category=Category.DECISION,
        ...     model="gpt-4o",
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     max_tokens=100,
        ... )
        >>> content = response.choices[0].message.content
    """
    client = _get_ai_client()
    tracker = TokenTracker(category)

    # 如果没有显式指定模型，使用 category 对应的模型
    if model is None:
        model = get_ai_model(category)

    response = client.chat.completions.create(model=model, **kwargs)
    tracker.record(response)

    return response
