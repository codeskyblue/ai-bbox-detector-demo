"""测试 PlanAdapter 的 validate_python 方法"""

import pytest
from pydantic import ValidationError

from uiautoagent.agent.plan import (
    _plan_adapter,
    parse_plan_response,
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
)


class TestPlanAdapterValidatePython:
    """测试 _plan_adapter.validate_python 方法"""

    def test_validate_tap_action(self):
        """测试解析 tap 操作"""
        data = {
            "type": "tap",
            "thought": "点击搜索按钮",
            "log": "点击搜索",
            "target": "搜索按钮",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, TapPlanAction)
        assert result.type == "tap"
        assert result.target == "搜索按钮"

    def test_validate_long_press_action(self):
        """测试解析 long_press 操作"""
        data = {
            "type": "long_press",
            "thought": "长按消息",
            "log": "长按",
            "target": "消息内容",
            "long_press_ms": 1000,
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, LongPressPlanAction)
        assert result.type == "long_press"
        assert result.target == "消息内容"
        assert result.long_press_ms == 1000

    def test_validate_long_press_with_default_ms(self):
        """测试 long_press 使用默认时长"""
        data = {
            "type": "long_press",
            "target": "消息",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, LongPressPlanAction)
        assert result.long_press_ms == 800  # 默认值

    def test_validate_input_action(self):
        """测试解析 input 操作"""
        data = {
            "type": "input",
            "thought": "输入搜索内容",
            "log": "输入",
            "text": "python",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, InputPlanAction)
        assert result.type == "input"
        assert result.text == "python"

    def test_validate_swipe_with_direction(self):
        """测试解析 swipe 操作（方向）"""
        data = {
            "type": "swipe",
            "thought": "向上滑动",
            "log": "上滑",
            "direction": "up",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, SwipePlanAction)
        assert result.type == "swipe"
        assert result.direction == "up"
        assert result.swipe_start is None
        assert result.swipe_end is None

    def test_validate_swipe_with_positions(self):
        """测试解析 swipe 操作（位置）"""
        data = {
            "type": "swipe",
            "thought": "滑动",
            "log": "滑动",
            "swipe_start": "个人资料",
            "swipe_end": "设置",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, SwipePlanAction)
        assert result.swipe_start == "个人资料"
        assert result.swipe_end == "设置"
        assert result.direction is None

    def test_validate_back_action(self):
        """测试解析 back 操作"""
        data = {
            "type": "back",
            "thought": "返回",
            "log": "返回",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, BackPlanAction)
        assert result.type == "back"

    def test_validate_wait_action(self):
        """测试解析 wait 操作"""
        data = {
            "type": "wait",
            "thought": "等待",
            "log": "等待",
            "wait_ms": 2000,
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, WaitPlanAction)
        assert result.wait_ms == 2000

    def test_validate_wait_with_default_ms(self):
        """测试 wait 使用默认时长"""
        data = {
            "type": "wait",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, WaitPlanAction)
        assert result.wait_ms == 1000  # 默认值

    def test_validate_app_launch_action(self):
        """测试解析 app_launch 操作"""
        data = {
            "type": "app_launch",
            "thought": "启动微信",
            "log": "启动",
            "app_id": "com.tencent.mm",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, AppLaunchPlanAction)
        assert result.app_id == "com.tencent.mm"

    def test_validate_app_stop_action(self):
        """测试解析 app_stop 操作"""
        data = {
            "type": "app_stop",
            "app_id": "com.tencent.mm",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, AppStopPlanAction)

    def test_validate_app_reboot_action(self):
        """测试解析 app_reboot 操作"""
        data = {
            "type": "app_reboot",
            "thought": "重启微信",
            "log": "重启",
            "app_id": "com.tencent.mm",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, AppRebootPlanAction)
        assert result.app_id == "com.tencent.mm"

    def test_validate_done_action(self):
        """测试解析 done 操作"""
        data = {
            "type": "done",
            "thought": "完成",
            "log": "完成",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, DonePlanAction)
        assert result.return_result is False

    def test_validate_done_with_result(self):
        """测试解析 done 操作（带结果）"""
        data = {
            "type": "done",
            "thought": "完成",
            "log": "完成",
            "return_result": True,
            "result": "任务完成，共找到15个好友",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, DonePlanAction)
        assert result.return_result is True
        assert result.result == "任务完成，共找到15个好友"

    def test_validate_fail_action(self):
        """测试解析 fail 操作"""
        data = {
            "type": "fail",
            "thought": "失败",
            "log": "失败",
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, FailPlanAction)

    def test_validate_missing_required_field(self):
        """测试缺少必需字段时抛出 ValidationError"""
        # tap 操作缺少必需的 target 字段
        data = {
            "type": "tap",
            "thought": "点击",
        }
        with pytest.raises(ValidationError):
            _plan_adapter.validate_python(data)

    def test_validate_invalid_direction(self):
        """测试无效的 direction 值"""
        data = {
            "type": "swipe",
            "direction": "diagonal",  # 无效值
        }
        with pytest.raises(ValidationError):
            _plan_adapter.validate_python(data)

    def test_validate_invalid_type(self):
        """测试无效的 type 值"""
        data = {
            "type": "invalid_type",
        }
        with pytest.raises(ValidationError):
            _plan_adapter.validate_python(data)

    def test_validate_extra_fields_ignored(self):
        """测试额外字段被忽略（strict=False）"""
        data = {
            "type": "tap",
            "target": "按钮",
            "extra_field": "应该被忽略",  # 额外字段
        }
        result = _plan_adapter.validate_python(data)
        assert isinstance(result, TapPlanAction)
        # 额外字段应该被忽略，不会出现在结果中
        assert not hasattr(result, "extra_field")

    def test_validate_min_wait_ms(self):
        """测试 wait_ms 最小值约束"""
        data = {
            "type": "wait",
            "wait_ms": -100,  # 负数，应该失败
        }
        with pytest.raises(ValidationError):
            _plan_adapter.validate_python(data)

    def test_validate_min_long_press_ms(self):
        """测试 long_press_ms 最小值约束"""
        data = {
            "type": "long_press",
            "target": "消息",
            "long_press_ms": -50,  # 负数，应该失败
        }
        with pytest.raises(ValidationError):
            _plan_adapter.validate_python(data)


class TestParsePlanResponse:
    """测试 parse_plan_response 函数"""

    def test_parse_single_json(self):
        """测试解析单个 JSON"""
        raw = '{"type": "tap", "thought": "test", "log": "test", "target": "按钮"}'
        result = parse_plan_response(raw)
        assert isinstance(result, TapPlanAction)
        assert result.target == "按钮"
