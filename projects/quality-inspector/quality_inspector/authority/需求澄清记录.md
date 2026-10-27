# Web 操作轨迹采集需求澄清记录

确认日期：2026-10-21。依据：项目用户对核心问题及站点范围的答复。

本记录用于本项目的采集方案和验收。与原需求书及附件不一致的部分，以本记录为准；其余要求继续按原需求书及附件执行。

## 站点来源与计数

站点由本项目自行寻找，无预设审核清单。站点筛选继续遵循原需求书的中文界面、类目覆盖等要求，交付时提供站点清单及类目。

同一域名下的不同 URI 可以作为独立站点统计。各站点产出的轨迹仍须满足任务具有实质差异及去重要求。

数量以原需求书为准：交付 20 万条完整操作轨迹，约 10,000 个中文站点、每站约 20 条；站点数及每站条数允许按原需求书灵活分配。

## 有效操作步

每条轨迹要求的至少 5 个有效操作步，只统计有显式页面操作的步骤，例如点击、输入、滚动、选择等。等待 `wait` 和结束确认 `complete` 不计入这 5 步。

有效操作步数与 `steps` 数组长度分别统计。原需求书关于短流程的标记、原因和不超过 2% 的要求继续适用。

## 任务完成判定

按任务规划与实际执行结果判断，核心条件是轨迹连续、不能跳过步骤，并且最终状态页面符合任务描述。

`controlled_exception` 是否适用，按具体任务规划和实际结果判断。该标签不能替代轨迹连续性与最终页面符合任务描述的检查。完成依据应能从交付的截图和动作记录中核验。

## 重复轨迹处理

交付前剔除检出的重复及近重复轨迹，内部目标为交付集重复率为 0。按原需求书的四路判定要求开展去重，并保证甲方算法计算出的交付集重复率低于 0.1%。

## 账号与页面信息

使用测试账号，或在来源与合规说明中对相关账号和页面信息作出声明，按此口径无需额外对截图和界面树做特殊脱敏处理。

## 验收范围

不要求采集完成后重新访问网站、重跑任务以复现轨迹。原需求书第 7 节中随机抽 20 条重跑的要求不再适用。

验收核对已采集的轨迹与截图是否逻辑一致：步骤连续，动作及其结果描述与相邻截图对应，最终状态页面符合任务描述。

## 快捷键的 Windows 交付表达

补充确认日期：2026-10-26。依据：项目用户先要求全选统一为 ctrl+a，随后明确所有键位均采用 Windows 表达，例如粘贴 ctrl+v；本条扩展并替代此前仅规范全选的范围。

交付数据中每个 hotkey 的 tool_call.arguments.keys、action.input_text 和 action.target_text 均采用 Windows 规范名称。参数及连接文本使用规范小写键名，例如 ["ctrl", "v"] 与 ctrl+v；显示名称使用 Ctrl+V。修饰键顺序固定为 ctrl、alt、shift、win，再接一个主键。允许单独一个修饰键，不允许重复修饰键、多主键或主键之后追加修饰键。

常见表达包括 Ctrl+A/C/V/X（全选/复制/粘贴/剪切）、Ctrl+Z、Ctrl+Shift+Z、Ctrl+S/F 等。Return、Esc、Control/Ctl、Spacebar、PgUp/PgDn、Del/Ins、Left/Right/Up/Down 等别名分别规范为 enter、escape、ctrl、space、pageup/pagedown、delete/insert、arrowleft/arrowright/arrowup/arrowdown；显示为 Enter、Esc、Ctrl、Space、PageUp/PageDown、Delete/Insert、Left/Right/Up/Down。其他统一名称包括 Tab、Backspace、Home、End、CapsLock、NumLock、ScrollLock、Pause、PrintScreen、ContextMenu 和 F1至F24。带修饰键的字母参数小写，单独的大写字符键保留实际大小写，不把真实字符输入改写为另一字符。

跨平台映射依据 device_info.os_name：macOS（含 Darwin）实际 Command/Meta/Cmd/⌘ 与主键 A/C/V/X/Z/S/F/P/O/N/W/T/L/R/D/G/B/I/U/K 的常见组合（可附带 Shift），以及不带 Shift 的 Command+1至9，按已声明的同功能 Web 操作交付为对应 Ctrl 组合。原始执行按键和操作顺序必须保留。Windows 原生 Meta 表示 Win 键，不得误映射为 Ctrl；未知平台含 Meta/Command 时不可推定。

Mac 的 Command+方向键、Option 组合等不能仅替换修饰键以声称同功能；未定义的跨平台组合和未知键名须明确报 WINDOWS_SHORTCUT_MAPPING_REQUIRED，补充功能映射后才能交付，不能继续输出 Meta/Option 或编造 Ctrl 表达。已使用 Windows 名称的其他单键/组合保持功能和主键不变。

《合成方式说明》和包外来源追溯须说明 Windows 归一化规则，绑定变更前后的标注哈希及逐步映射，不得把交付参数冒称为未变更的原始执行参数。历史文件不原地覆盖；变更标注生成新版本并重新检查。旧人工审核记录保持原样，不改写其标注哈希、不自动签署为新版通过。
