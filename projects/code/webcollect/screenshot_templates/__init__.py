"""策略 2 模板包集合：operation / long_reading / generic。

路由（模板选择、冻结与按任务派发）唯一入口是
webcollect.screenshot_planners；本包不承载共享业务代码，
各模板包相互独立、不互相 import。
"""
