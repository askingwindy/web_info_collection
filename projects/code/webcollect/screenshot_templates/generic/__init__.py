"""策略 2 · generic 模板包。

独立拥有提示词、线协议 schema、输出规范化/解析、决策循环与观察/动作适配
的完整业务拷贝；只依赖共享底座（浏览器原始事实、模型网关、合同/证据/导航
与正式保存链）。本包不 import 其它模板包或 webcollect.screenshot_plan /
webcollect.screenshot_session 单体实现。
"""
from . import plan as _plan_module
from . import session as _session_module
from .plan import (SYSTEM_PROMPT, RAW_ONLY_ENDINGS, READY_ENDING, submit_plan_schema,
    _allowed_all, _verify_input, explicit_submission_required, tail_effect_observed,
    validate_ending_marker, _replay_session)
from .plan import screenshot_chooser
from .session import ScreenshotPlanSession as Session

TEMPLATE_NAME = 'generic'
PLAN_MODULE = 'webcollect.screenshot_templates.generic.plan'
SESSION_MODULE = 'webcollect.screenshot_templates.generic.session'

__all__ = ['TEMPLATE_NAME', 'PLAN_MODULE', 'SESSION_MODULE', 'Session',
           'screenshot_chooser', 'SYSTEM_PROMPT', 'RAW_ONLY_ENDINGS', 'READY_ENDING',
           'submit_plan_schema', '_allowed_all', '_verify_input',
           'explicit_submission_required', 'tail_effect_observed',
           'validate_ending_marker', '_replay_session']
