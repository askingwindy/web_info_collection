"""策略 3 stepwise：独立逐步采集（每轮一次调用、一个动作）。

本包独立维护策略 3 的提示词、模型协议、决策循环、目标调整、动作绑定、
效果判断、原始记录、回写、单独判定、annotation 生成与保存资格；只复用
浏览器捕获/执行、模型网关、账本、RuntimeStore、候选回写与导出外壳等宿主
基础设施。包内代码不 import 其它策略的业务实现（screenshot_plan/
screenshot_session/screenshot_templates/banded_plan/react_session、
collection_contract/collection_evidence/closing_policy/goal_evidence/
postprocess/candidate_navigation），见《策略3独立逐步采集代码实现SDD》§2。
"""
from ..collection_strategy import STRATEGY_STEPWISE as STRATEGY_ID


def run_collection(*args, **kwargs):
    """采集外壳入口（collect_runtime 按冻结策略分流调用）。"""
    from .collection import run_collection as _run
    return _run(*args, **kwargs)


__all__ = ['STRATEGY_ID', 'run_collection']
