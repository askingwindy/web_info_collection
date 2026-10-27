# 字段说明（v4）

本数据所有样本使用同一套字段与格式，不因终端或数据类型而不同。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `sample_id` | string | 是 | 样本编号，包内唯一 |
| `task_instruction` | string | 是 | 任务指令，简体中文；界面上出现的专有名词保留原文 |
| `task_type` | array[string] | 是 | 任务类型标签，可多值 |
| `terminal_type` | string | 是 | 终端系统：Android / iOS / Windows / macOS / Linux / Web |
| `device_info` | object | 是 | device_model 设备型号、os_name 系统名、os_version 系统版本、screen_resolution 截图分辨率 [宽, 高]；取不到的项为空字符串 |
| `app_info` | object | 是 | app_name 应用名、app_version 应用版本、environment 运行环境、ui_language 被操作软件的界面语言（zh / en） |
| `risk_level` | string | 是 | 风险等级：normal / sensitive / high_risk |
| `trajectory_source` | object | 是 | source_type 轨迹类型（human 人工操作 / agent 智能体执行 / human_agent_hybrid 人机协同）、data_type 数据类型编号、action_space 动作空间版本。data_type 对应《动作空间与系统提示》中的同名章节 |
| `steps` | array[object] | 是 | 操作步骤，按执行顺序排列 |
| `final_state_image` | string | 否 | 最终状态截图的相对路径；末步为 complete 时指向末步截图，另有独立终态图时指向该图，否则为空 |
| `final_result` | string | 是 | 任务结束时界面的最终状态描述，简体中文 |
| `completion_status` | string | 是 | success 已完成 / controlled_exception 可控异常 / failed 未完成 |
| `completion_judgement` | string | 是 | 完成判定依据：最终界面上能核验任务完成的具体内容，简体中文 |

## 步骤字段（steps[]）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `step_id` | int | 是 | 步序号，从 1 连续编号 |
| `image_path` | string | 是 | 本步操作【前】的界面截图，相对本样本目录；也是上一步操作后的界面 |
| `ui_tree_path` | string | 是 | 本步操作前的界面树文件（ui_tree/step_NNN.json），与截图同一时刻采集；来源不含界面树时为空字符串 |
| `page_name` | string | 是 | 本步所在页面的名称，简体中文 |
| `user_goal` | string | 是 | 本步要达成的子目标，简体中文 |
| `action` | object | 是 | 本步动作，字段见下表 |
| `tool_call` | object | 是 | 工具调用记录：tool_name 等于 action_type；call_id 调用编号；arguments 为统一动作空间的参数（见《动作空间与系统提示》），坐标为截图像素整数；timestamp 执行时刻（ISO 8601，来源无时间戳时为空）；context 运行环境 |
| `tool_result` | object | 是 | 工具返回：status 执行状态（success / error）、return_value.screen_changed 操作后界面是否变化（末步无下一张截图时省略）、error 错误信息 |
| `next_step_rationale` | string | 是 | 决策摘要：基于当前界面为什么执行本步动作，简体中文，只引用截图或界面树中可见的内容 |
| `step_result` | string | 是 | 本步执行后的实际观察：界面发生了什么变化，简体中文（v3 的 tool_result.observation 已并入本字段） |
| `exception_evidence` | array | 是 | 本步出现的异常弹窗、报错等证据描述；无则为空数组 |

## 动作字段（steps[].action）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `action_type` | string | 是 | 动作类型，取值见《动作空间与系统提示》 |
| `target_element_id` | string | 是 | 目标控件在本步界面树中的 element_id；无界面树或非控件动作时为空字符串 |
| `target_text` | string | 是 | 目标控件的名称，按界面上的原文书写；输入动作为承接输入的输入框名称，按键动作为按键名（如「回车键」）；滚动、等待、启动应用、返回、结束等不作用于控件的动作为空字符串 |
| `target_control_type` | string | 否 | 目标控件类型，如 button / input / menu_item / list_item / tab / checkbox / icon |
| `target_bbox` | array[int] | 否 | 目标控件框 [x_min, y_min, x_max, y_max]，截图像素，原点在左上角 |
| `coordinate` | array[int] | 是 | 触点 [x, y]，截图像素；无触点的动作为空数组 |
| `end_coordinate` | array[int] | 否 | 拖动、滑动的终点 [x, y] |
| `input_text` | string | 是 | 输入的文本（type）或按键（hotkey，以 + 连接）；其他动作为空字符串 |
| `precondition` | string | 是 | 操作前的界面状态，简体中文，只描述截图或界面树中可见的内容 |
| `expected_result` | string | 是 | 执行本步后预期出现的结果，简体中文 |

## 界面树文件（ui_tree/step_NNN.json）

```json
{"image_path": "images/step_001.png", "screen_resolution": [宽, 高], "elements": [ ... ]}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `element_id` | string | 元素编号，本文件内唯一；action.target_element_id 引用它 |
| `parent_id` | string | 父元素编号，根元素为 root |
| `element_type` | string | 统一的元素类型，如 button / input / text / icon / menu / menu_item / list_item / checkbox / tab / window / group |
| `native_role` | string | 系统原生角色名（安卓 class、Windows UIA ControlType、macOS AXRole、Linux AT-SPI role） |
| `text` | string | 元素上的可见文字或无障碍名称，按界面原文 |
| `bbox` | array[int] | [x_min, y_min, x_max, y_max]，与同名截图同一像素坐标系 |
| `clickable` | bool | 是否可点击 |
| `inputable` | bool | 是否可输入 |
| `scrollable` | bool | 是否可滚动 |
| `visible` | bool | 是否可见 |
| `enabled` | bool | 是否启用 |
| `state` | string | 当前状态：default / selected / checked / unchecked / expanded / collapsed / disabled / focused |

## 通用约定

- **坐标系**：原点在截图左上角，x 向右、y 向下，单位为截图像素，全部为整数。`coordinate`、`target_bbox`、`tool_call.arguments` 里的坐标、界面树 `bbox` 用的是同一套坐标。
- **截图时序**：`step_N.png` 是第 N 步操作**前**的界面，也是第 N−1 步操作后的界面。第 N 步的效果看 `step_N.png` → `step_N+1.png`。
- **语言**：所有叙述性字段（指令、页面名、子目标、操作前状态、预期结果、决策摘要、步骤结果、最终结果、判定依据）为简体中文，不截断。界面上原样出现的控件名、菜单名、应用名、文件名保留原文，通常用「」括起。
- **信息来源**：叙述性字段只依据本样本交付的内容——截图、动作记录、界面树（若有）——不引用任何未交付的信息。
- **空值**：取不到的字符串字段为 ""，数组字段为 []，不编造。
