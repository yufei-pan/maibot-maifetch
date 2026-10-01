# maifetch（麦麦状态）

让麦麦了解自己的 MaiBot 插件：版本、平台、插件与工具、模型用量、在线时长，开了「炫耀模式」还能晒机器配置。

- **规划器工具 `maifetch`**：用户问「你是什么模型 / 什么版本 / 装了什么插件 / 跑了多久 / 用了多少 token」时，麦麦查真实数据回答，不再凭印象。
- **规划器注入**：每次规划前，在系统提示词末尾追加一段简短的自身信息（只含慢变事实，不影响提示词缓存），让麦麦知道自己能做什么。
- **`/maifetch` 命令**：发一张状态卡片图。

> 关于「你是什么模型」：插件拿不到每个任务（回复器 / 规划器）具体用的哪个模型，所以麦麦会如实回答「近 N 天主要由 X、Y 驱动」。

## 安装

1. 将本仓库放到 `MaiBot/plugins/maibot-maifetch/`（或从工作区同级目录符号链接：`ln -s ../../maibot-maifetch MaiBot/plugins/maibot-maifetch`）。
2. 重启 Host，或在 WebUI 加载插件。首次加载会从 `config.default.toml` 生成运行期 `config.toml`。
3. 需要 MaiBot ≥ 1.3.1（插件 SDK ≥ 2.8.2）。出图依赖 Host 的浏览器渲染（Playwright）；不可用时自动改发文字版。

## 命令

| 命令 | 作用 |
|---|---|
| `/maifetch` | 发送状态卡片（使用配置的模板） |
| `/maifetch 文字` | 发送文字版 |
| `/maifetch dashboard` / `terminal` / `sheet` | 用指定内置模板出图 |
| `/maifetch 帮助` | 用法 |

同一聊天发卡片有冷却（默认 30 秒）。可在 `[command].aliases` 加别名（按原样匹配，例如 `"/状态"`，改完需重载插件）。

## 规划器工具

工具名 `maifetch`，参数：

- `section`：`all`（默认）/ `identity` / `runtime` / `plugins` / `models` / `usage` / `hardware`，也接受中文（全部、身份、版本、插件、模型、用量、硬件）。
- `send_card`：为 true 时同时把状态卡片发到当前聊天（与命令共用冷却）。

工具结果末尾会提醒规划器把相关事实写进 `reply` 工具的 `reply_reference`——回复器看不到工具结果。

## 配置

见 `config.default.toml`。数值超出范围会被自动钳制。

| 字段 | 默认 | 说明 |
|---|---|---|
| `plugin.enabled` | `true` | 总开关 |
| `visibility.show_account` | `false` | 显示机器人账号 |
| `visibility.show_plugin_list` | `true` | 显示插件列表（关闭后仍显示数量） |
| `visibility.show_cost` | `false` | 显示花费 |
| `usage.window_days` | `7` | 用量统计窗口（1–90 天） |
| `usage.top_models` | `5` | 列出前几个模型（1–10） |
| `injection.enabled` | `true` | 规划器注入开关 |
| `injection.refresh_minutes` | `10` | 摘要刷新间隔（1–1440 分钟） |
| `command.aliases` | `[]` | 命令别名 |
| `command.cooldown_seconds` | `30` | 发卡片冷却（0 = 不限） |
| `card.template` | `assets/dashboard.html` | 卡片模板（相对插件目录或绝对路径） |
| `card.scale` | `1.0` | 渲染像素比（0.5–3.0） |
| `card.format` | `webp` | `webp`（无损）或 `png` |
| `card.render_timeout_ms` | `20000` | 渲染超时 |
| `hardware.enabled` | `false` | 硬件信息总开关（炫耀模式） |
| `hardware.show_*` | `true` | 各硬件字段：os / kernel / arch / cpu / memory / disk / python / uptime / virt |

可见性开关同时作用于工具、注入与卡片：被隐藏的字段不会出现在任何地方。

## 隐私

- 硬件信息默认关闭；开启后只读系统名称、内核、架构、CPU 型号与核心数、内存、MaiBot 所在磁盘用量、Python 版本、开机时长、容器 / 虚拟机类型。
- **无论如何都不会采集**主机名、IP / MAC、用户名、文件路径、挂载列表、序列号、进程。
- 消息统计只取总数；统计接口返回的其他群聊名称会被立即丢弃，不会出现在任何输出里。
- 「平台」只显示平台名：`bot.platforms` 里 `平台:账号` 格式的备用账号 ID 会被丢弃；未配置时不显示该项。
- Host 统计接口最多返回 50 个模型 / 聊天，触顶时合计显示为下限（如 `3,906+`）。

## 自定义模板

把 `card.template` 指向自己的 HTML 文件即可。约定：

- 根元素必须是 `id="card"`（截图只截它），宽度由模板自己定。
- 占位符写作 `{名称}`，只替换一遍；未知的花括号（CSS、JS）原样保留。**不要在 HTML 注释里写占位符**。
- 内置字体自动可用：`Noto Sans SC`（400 / 700）、`JetBrains Mono`；渲染不联网。

### 模板占位符

标量（已 HTML 转义；可隐藏字段缺失时为空，其余缺失显示「未知」）：

`nickname` `nickname_initial` `alias_names` `platforms` `account` `local_time` `timezone` `host_version` `sdk_version`
`plugin_version` `uptime` `uptime_short` `online_since` `plugin_count` `tool_count` `model_tasks` `window_days`
`total_requests` `total_tokens` `total_cost` `total_messages` `top_model` `top_model_more` `hw_os` `hw_kernel`
`hw_arch` `hw_cpu` `hw_memory` `hw_disk` `hw_python` `hw_uptime` `hw_virt` `generated_at`

片段（插件生成的 HTML，隐藏或为空时为空串）：

| 占位符 | 结构 |
|---|---|
| `tiles_html` | 4 × `.mf-tile > b + span`（花费隐藏时第 4 格为请求数） |
| `model_rows_html` | `.mf-model-row > .mf-model-name / .mf-model-bar > i / .mf-model-req / .mf-model-tok / .mf-model-cost`；无数据时 `.mf-empty` |
| `plugin_list_html` | 最多 8 个 `.mf-chip`，其余合并为 `.mf-chip.mf-more`「+N」 |
| `hardware_block_html` | `.mf-hw > .mf-hw-title + .mf-hw-grid > .mf-hw-row > .mf-k + .mf-v` |
| `hardware_lines_html` | 终端风格：`.dim` 分隔线 + `<div><span class="k">Key</span>: value</div>` |
| `identity_rows_html` / `runtime_rows_html` / `model_table_rows_html` | `<tr><td>标签</td><td>值</td></tr>` 行 |
| `hardware_table_html` | `<div class="sec">硬件</div><table>…</table>` |
| `maimai_logo_svg` | 20×14 呆萌像素麦麦（内联 SVG） |
| `data_json` | 脱敏后的完整快照 JSON，可放进 `<script type="application/json">` |

### 本地预览

```bash
cd maibot-maifetch
PYTHONPATH=.:../maibot-plugin-sdk python3 tools/preview_cards.py preview --template /path/to/my.html
```

需要本机安装 Playwright 与 Chromium（`--chrome` 可指定浏览器路径）。

## 测试

```bash
cd maibot-maifetch
python3 -m pytest -q
PYTHONPATH=../maibot-plugin-sdk python3 tests/smoke_test.py
```

## 许可

MIT。内置字体 Noto Sans SC 与 JetBrains Mono 采用 SIL Open Font License 1.1（见 `assets/fonts/`）。
