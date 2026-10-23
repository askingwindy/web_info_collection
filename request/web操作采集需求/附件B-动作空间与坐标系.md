# 动作空间与系统提示
本数据集所有终端共用**同一套动作空间**：`action.action_type` 与 `tool_call.tool_name` 取值相同，`tool_call.arguments` 的参数名与格式一致。下表的 Web 列标 ✓ 的就是网页数据可用的动作子集；浏览器自动化产出的原始动作要在交付前映射到这套动作空间，映射方式写进《合成方式说明》（需求书 §3.4）。
## 1. 统一动作空间
| action_type | arguments | 移动端 | 桌面端 | Web | 说明 |
|---|---|:-:|:-:|:-:|---|
| `click` | `x`, `y` | ✓ | ✓ | ✓ | 在 (x, y) 处单击（移动端为轻触） |
| `double_click` | `x`, `y` |  | ✓ | ✓ | 在 (x, y) 处双击 |
| `right_click` | `x`, `y` |  | ✓ | ✓ | 在 (x, y) 处右键单击 |
| `long_press` | `x`, `y` | ✓ |  |  | 在 (x, y) 处长按 |
| `type` | `text` | ✓ | ✓ | ✓ | 向当前获得焦点的输入框输入文本 |
| `hotkey` | `keys` | ✓ | ✓ | ✓ | 按下按键或组合键，keys 为按键名数组，如 ["ctrl", "s"]、["enter"] |
| `scroll` | `x`, `y`, `direction` | ✓ | ✓ | ✓ | 在 (x, y) 处滚动页面，direction 为 up/down/left/right（内容移动方向的反向，即查看更下方内容用 down） |
| `swipe` | `x`, `y`, `end_x`, `end_y` | ✓ |  |  | 从 (x, y) 滑动到 (end_x, end_y) |
| `drag` | `x`, `y`, `end_x`, `end_y` |  | ✓ | ✓ | 按住左键从 (x, y) 拖到 (end_x, end_y) |
| `back` | — | ✓ |  | ✓ | 返回上一页（安卓返回键 / 浏览器后退） |
| `home` | — | ✓ |  |  | 回到系统主屏 |
| `open_app` | `app_name` | ✓ | ✓ |  | 直接启动应用 |
| `open_url` | `url` |  |  | ✓ | 在浏览器中打开网址 |
| `select` | `x`, `y`, `option` |  | ✓ | ✓ | 在 (x, y) 处的下拉框中选择 option |
| `wait` | — | ✓ | ✓ | ✓ | 不操作，等待界面加载或变化 |
| `complete` | `status` | ✓ | ✓ | ✓ | 结束任务，status 为 success（已完成）或 infeasible（无法完成） |

## 2. 坐标系
- 原点在截图左上角，x 向右、y 向下，单位为**截图像素**，全部为整数。
- `action.coordinate`、`action.target_bbox`、`tool_call.arguments` 中的 x / y / end_x / end_y、界面树中的 `bbox`，都在同一张截图的像素坐标系里。
- 截图分辨率见 `device_info.screen_resolution`，同一条样本内所有截图分辨率相同。
- 触点坐标指向目标控件内部（通常为中心附近），可用 `target_bbox` 核对。

## 3. 网页数据的系统提示（模板）

已交付网页数据所用的参考提示，动作与坐标写法与数据一致。自动化合成的数据在此基础上补一份《合成方式说明》（需求书 §3）。

```text
你在操作一台电脑上的浏览器，为用户完成任务。
每一轮你会看到一张当前界面的截图，以及此前已经执行过的动作列表。请输出下一步的一个动作，格式为一个 JSON 对象。

坐标系：原点在截图左上角，x 向右、y 向下，单位为截图像素。点击类动作指向目标控件的中心。

可用动作（与数据中 tool_call 的 tool_name / arguments 完全一致）：
{"tool_name": "click", "arguments": {"x": …, "y": …}}  在 (x, y) 处单击（移动端为轻触）
{"tool_name": "double_click", "arguments": {"x": …, "y": …}}  在 (x, y) 处双击
{"tool_name": "right_click", "arguments": {"x": …, "y": …}}  在 (x, y) 处右键单击
{"tool_name": "type", "arguments": {"text": …}}  向当前获得焦点的输入框输入文本
{"tool_name": "hotkey", "arguments": {"keys": …}}  按下按键或组合键，keys 为按键名数组，如 ["ctrl", "s"]、["enter"]
{"tool_name": "scroll", "arguments": {"x": …, "y": …, "direction": …}}  在 (x, y) 处滚动页面，direction 为 up/down/left/right（内容移动方向的反向，即查看更下方内容用 down）
{"tool_name": "drag", "arguments": {"x": …, "y": …, "end_x": …, "end_y": …}}  按住左键从 (x, y) 拖到 (end_x, end_y)
{"tool_name": "back", "arguments": {}}  返回上一页（安卓返回键 / 浏览器后退）
{"tool_name": "open_url", "arguments": {"url": …}}  在浏览器中打开网址
{"tool_name": "select", "arguments": {"x": …, "y": …, "option": …}}  在 (x, y) 处的下拉框中选择 option
{"tool_name": "wait", "arguments": {}}  不操作，等待界面加载或变化
{"tool_name": "complete", "arguments": {"status": …}}  结束任务，status 为 success（已完成）或 infeasible（无法完成）

同时给出 thought 字段，用一两句话说明为什么选择这个动作。
任务完成、且截图上能看到完成结果时，输出 {"tool_name": "complete", "arguments": {"status": "success"}}。
```
