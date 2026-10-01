# maibot-maifetch — Design Spec

**Date:** 2026-10-01
**Status:** Approved (brainstorming) — pending written-spec review
**Plugin directory:** `maibot-maifetch/` (own git repo, sibling of the other first-party plugins)
**Plugin id:** `com.0-hz.maifetch`
**Display name:** maifetch（麦麦状态）
**Targets:** MaiBot Host **1.3.1** (`host_application` 1.3.1 – 1.99.99), SDK **2.8.2** (`sdk` 2.8.2 – 2.99.99)
**Architecture:** collect → redact → format, with three consumers (planner tool, planner-prompt injection, image card)

## Summary

A neofetch-style self-awareness plugin for MaiBot. It gives the planner (and therefore 麦麦) accurate facts about
itself — who it is, what it runs on, which plugins/tools/models it has, and how much it has been used — through
three surfaces:

1. **`@Tool maifetch`** — full detail on demand; optional `send_card` renders and sends the status card.
2. **Planner injection** — a short, cache-stable summary appended to the planner system prompt on every request.
3. **`/maifetch` command** — renders a status card image (3 bundled HTML templates + user templates) and sends it.

Host-machine hardware info is shown by default; operators who don't want machine details visible in chat turn it
off as a whole or per field (the WebUI description warns about this).

## Problem

麦麦 has no reliable way to know its own version, plugins, models, uptime or usage. When users ask
「你是什么模型 / 什么版本 / 装了哪些插件 / 跑了多久 / 用了多少 token」 it guesses, and when deciding whether it *can* do
something it has no grounding in what is actually installed/configured. Operators who like neofetch also want a
shareable status image.

## Goals

- Answer self-questions truthfully (version, platforms, plugins, models, uptime, usage).
- Self-grounding: planner always sees a short stable self-summary; detail is one tool call away.
- Usage/cost awareness on request (tokens, requests, messages; cost when enabled).
- `/maifetch` card image with 3 bundled templates (default: dashboard) and operator-supplied custom templates.
- Per-field visibility toggles applied uniformly to tool, injection, and card.
- Narrow, stdlib-only hardware info (default on, can be turned off as a whole or per field).
- Plugin-only: no Host/SDK source changes; only published SDK capabilities + documented Host env/hook contracts.

## Non-goals (v1)

- Per-chat usage breakdowns (would leak other groups' names into whichever chat runs `/maifetch`).
- Per-task model mapping (e.g. "replyer uses model X") — not reachable from plugins (see Verified Host facts).
- Hostname, IPs/MACs, usernames, paths, mount lists, serial numbers, process lists — never collected, not configurable.
- Admin/role-gated views (visibility is per-field config, same view for everyone).
- GPU info, `psutil`, Jinja2, or any new runtime dependency beyond Pillow (already a Host dependency).
- Replyer-side injection.

## Decisions (from brainstorming)

| Topic | Choice |
|---|---|
| Info scope | MaiBot runtime + models & usage + bot identity/env + hardware (default on, can be turned off) |
| Tool purpose | Answer self-questions, self-grounding, usage/cost awareness |
| Visibility | Per-field toggles in config; same view for everyone; applies to tool, injection, card |
| Planner delivery | Tool (pull) **and** short always-on injection (push) |
| Tool can show image | Yes — `send_card: bool` param (default false); plugin sends via `ctx.send.image` |
| Hardware | Default on (`hardware.enabled = true`, changed after live review), per-field sub-toggles, stdlib only, never in injection; descriptions warn that everyone in the chat can see it |
| Default card template | Dashboard (compact: identity row + 4 tiles + model table + plugin chips) |
| Bundled templates | dashboard (default), terminal (neofetch-style, dorky pixel 麦麦), sheet (plain info sheet) |
| Template engine | `{placeholder}` substitution like impression-card + pre-rendered fragments + `{data_json}` |
| Code layout | `plugin.py` glue + uniquely named `maifetch/` subpackage (swarm-style `sys.path` insert) |
| Host target | 1.3.1 (SDK ≥ 2.8.2) |

## Verified Host facts (MaiBot 1.3.1 source)

These drove the design; re-verify if the Host target moves.

| Fact | Where | Consequence |
|---|---|---|
| Runner loads `plugin.py` as a package (`submodule_search_locations=[plugin_dir]`); only the plugin's **parent** dir is on `sys.path` | `src/plugin_runtime/runner/plugin_loader.py` `_load_single_plugin` | Absolute sibling imports fail (cf. world-clock inlining). Use swarm pattern: `plugin.py` inserts its own dir into `sys.path`, logic lives in uniquely named `maifetch/` package. |
| Runner env carries `MAIBOT_HOST_VERSION` | `src/plugin_runtime/host/supervisor.py` `_build_runner_environment` | Host version without a capability. |
| `config.get` reads **bot_config** (`global_config`) only; model task config lives in `model_config` | `capabilities/core.py` `_cap_config_get`; `src/config/config.py` | No per-task model mapping. |
| `llm.get_available_models` returns **task names** only | `capabilities/core.py` `_cap_llm_get_available_models` | Report configured tasks (e.g. vlm, voice) as capability grounding. |
| Stats `module_name` = `request_type.split(".")[0]` (`"maisaka"` for planner *and* replyer) | `src/chat/utils/statistic.py` | "Main model" = top by requests over window, phrased honestly ("近 N 天主要由 … 驱动"). |
| `statistics.local.*` caps `limit`/`top_chats` at 50 and `days` at 365; `message_trend` total sums only the returned chats | `capabilities/data.py` `_normalize_statistics_limit`, `_cap_statistics_local_message_trend` | Request 50; flag lower-bound totals with `+`. |
| `statistics.local.models(days, limit)` → `model_name, request_count, total_tokens, total_cost, avg_response_time` | `capabilities/data.py` | Model table + totals. |
| `OnlineTime` rows: newest by `end_timestamp` has `start_timestamp` = current continuous online session (restarts within 1 min merged) | `src/chat/utils/statistic.py`, `database_model.OnlineTime` | Cross-platform uptime via `ctx.db.get("OnlineTime", order_by="-end_timestamp", limit=1, single_result=True)`. |
| `bot.platforms` entries are `platform:账号` strings; `bot.platform` / `bot.platforms` are adapter *fallbacks* (default empty) | `src/config/official_configs.py` `BotConfig`, `src/services/bot_account_service.py` | Only the platform name is used; account IDs never output; empty platforms are omitted (not 「未知」). |
| `component.get_all_plugins` → `{pid: {name, version, components:[{name, type, enabled, ...}]}}` | `capabilities/components.py` | Plugin list + tool count (`type` ∈ tool/action, case-insensitive, `enabled`). |
| Replyer **drops** `ToolResultMessage` from its context | `src/chat/replyer/maisaka_generator_base.py` `_is_replyer_filtered_history_message` | Tool output must tell the planner to copy relevant facts into `reply`'s `reply_reference`. |
| `maisaka.planner.before_request` payload: `items` (schema v1), `item_schema_version`, `tool_definitions`, `session_id`; first item is the system prompt; 1.3 measures prompt-cache hit/miss per section | `src/maisaka/chat_loop_service.py` | Inject into the system item; injected text must be **stable** (no live counters). |
| Command result 3rd element truthy ⇒ message intercepted (planner doesn't also respond) | `src/plugin_runtime/component_query.py` | Return `(ok, msg, 2)`. |
| Host tool invoke RPC ~60 s timeout | (memory: plugin-long-tool-async-rpc-timeout) | Tool path budget ≪ 60 s; synchronous is fine here. |
| NapCat send can false-fail on big images (15 s ack timeout) | (memory: plugin-send-capability-return-contract) | 1× render + lossless WebP; phrase send failure as 「可能未送达」. |

---

## Architecture

### Layout

```
maibot-maifetch/
├─ plugin.py             glue only: MaiFetchPlugin (components, lifecycle, config normalize/migrate, refresher task)
├─ maifetch/             uniquely named package (shared Runner process — no generic module names)
│  ├─ __init__.py
│  ├─ config.py          config models, normalize/clamp, Settings snapshot, shipped-config copy
│  ├─ snapshot.py        frozen dataclasses (Identity / Runtime / ModelUsage / Usage / Hardware / Snapshot)
│  ├─ fmt.py             number/size/duration/time formatting shared by text + card
│  ├─ collect.py         collect_snapshot(ctx, settings) → Snapshot   (the ONLY module besides plugin.py that touches ctx)
│  ├─ hardware.py        collect_hardware(disk_path) → Hardware        (pure stdlib, no ctx)
│  ├─ redact.py          apply_visibility(snapshot, visibility, hw) → Snapshot   (single point where toggles apply)
│  ├─ text.py            format_tool_text / format_user_text / format_injection; tool-input parsing
│  ├─ logo.py            20×14 pixel 麦麦 grid + maimai_svg()
│  ├─ card.py            build_card_html(snapshot, template_str, font_css) → html; scalars; fragments; data_json
│  ├─ render.py          template resolve/load, embedded font CSS, PNG→lossless WebP
│  ├─ inject.py          apply_injection(kwargs, text) for items schema v1 / legacy messages
│  ├─ cooldown.py        per-stream Cooldown
│  ├─ registration.py    tool description, command pattern/arg parsing, get_components patching
│  └─ sample.py          sample Snapshot for tests and template preview
├─ tools/preview_cards.py  local template preview (Playwright), dev-only
├─ assets/
│  ├─ dashboard.html     default
│  ├─ terminal.html
│  ├─ sheet.html
│  └─ fonts/             NotoSansSC-400.woff2, NotoSansSC-700.woff2 (from impression-card), JetBrainsMono-Regular.woff2, OFL.txt
├─ tests/                unit tests per module + smoke_test.py
├─ _manifest.json · config.default.toml · README.md · CHANGELOG.md · LICENSE (MIT) · .gitignore
└─ docs/superpowers/specs/2026-10-01-maifetch-design.md
```

`plugin.py` head (swarm pattern):

```python
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))
from maifetch.collect import collect_snapshot  # noqa: E402
...
```

### Data flow

```
refresher task (on load, every refresh_minutes, on config update)
    collect_snapshot → apply_visibility → cache {snapshot, injection_text}
                                                │  (cached; no RPC on the hook path)
planner request ─► @HookHandler maisaka.planner.before_request ─► append injection_text to first SystemMessageItem
planner tool    ─► @Tool maifetch ─► fresh collect → redact → format_tool_text  (+ send_card → card pipeline)
"/maifetch"     ─► @Command maifetch ─► fresh collect → redact → card pipeline (fallback: format_user_text)

card pipeline: load template → build_card_html → ctx.render.html2png(#card, scale) → Pillow lossless WebP → ctx.send.image
```

Rule: every consumer reads a **redacted** `Snapshot`. Nothing formats raw collected data.

---

## Components

### 1. Refresher (background task)

- Started in `on_load` (first refresh runs immediately), loops every `injection.refresh_minutes` (default 10).
  If a refresh raises or reports failed sources while no good cache exists yet (e.g. Host capabilities not ready at
  load), the next attempt runs after 30 s instead of the full interval — repeatedly, until a refresh succeeds for
  every source the injection uses (identity, models, plugins). After the first complete refresh following load, one
  warm-up refresh runs 60 s later: the Runner activates plugins one by one, so plugins after maifetch are not yet
  registered at its first refresh and the plugin/tool counts would be low.
- Also triggered by `on_config_update(scope=self)`.
- On success: replace cache `{snapshot, injection_text}`. On failure: keep previous cache, log warning.
- Cancelled and awaited in `on_unload`.
- Runs even if `injection.enabled = false`? **No** — when injection is disabled the task is not started (tool and
  command always collect fresh).

### 2. Hook — `maisaka.planner.before_request`

- `@HookHandler(..., mode=BLOCKING, order=NORMAL, timeout_ms=5000, error_policy=SKIP)`. The timeout covers the
  IPC round trip of the whole planner context; three consecutive hook timeouts open the Host's plugin-wide circuit
  breaker for 60–300 s (disabling the tool and command too), so it must not be tight.
- If `plugin.enabled` and `injection.enabled` and cache ready: find the **first** item with
  `item_type == "SystemMessageItem"` in `items` (when `item_schema_version == 1`) and append a part
  `{"type": "text", "text": "\n\n" + injection_text}`. If `items` absent, legacy `messages` path: first
  `role == "system"` message; append to `str` content or as a text part to list content.
- No system item found → skip silently (debug log). Never invents a new item.
- No RPC, no I/O. Whole body wrapped in try/except → `{"action": "continue"}` on any error.
- Returns `{"action": "continue", "modified_kwargs": kwargs}` only when it changed something.

### 3. Tool — `maifetch`

- Name `maifetch` (single tool; no tool_search category issue).
- `brief_description` / `description` (zh-CN), config-aware via `get_components()` override (window days):
  「【maifetch·自身信息】查询麦麦自身的运行信息：版本、接入平台、已加载插件与工具、已配置模型任务、近 N 天模型用量、
  本次在线时长（运维开启时含硬件信息）。用户问到你是什么模型/什么版本/装了什么插件/能不能做某事/跑了多久/用了多少
  token 时调用，不要凭印象回答。send_card=true 时直接把状态卡片图发到当前聊天。」
- Params:
  - `section` (string, optional, `enum_values` = `all, identity, runtime, models, usage, plugins, hardware`,
    default `all`). Defensive aliases accepted (case-insensitive): 全部/所有→all, 身份/我是谁→identity,
    运行/版本/在线→runtime, 模型→models, 用量/用量统计/token→usage, 插件/工具→plugins, 硬件/机器/配置→hardware.
    Unknown value → `all` plus a one-line note in the output. `hardware` while hardware disabled → note
    「运维未开启硬件信息」.
  - `send_card` (boolean, optional, default false). Also accepts `"true"/"1"/"是"` strings.
- Always collects **fresh** (usage changes).
- Returns `{"success": True, "content": text}`; text ends with
  「（回复用户时，请把与问题相关的事实写进 reply 工具的 reply_reference，回复器看不到本工具结果。）」
- `send_card=true`: runs the card pipeline to the tool's `stream_id`; shares the command's per-stream cooldown.
  Content gains a status line: 「已发送状态卡片」/「状态卡片可能未送达」/「卡片渲染不可用，仅返回文字」/
  「冷却中，N 秒后可再发卡片」.
- Budget: collection ≤ ~3 s (concurrent, per-source timeout) + render ≤ `render_timeout_ms` (20 s) + encode/send —
  well under the ~60 s tool RPC limit.

### 4. Command — `/maifetch` (component name `maifetch_card`; the tool owns the name `maifetch`)

- Pattern built in `get_components()` from config:
  `^(?:/maifetch|<alias1>|<alias2>…)(?:\s+(?P<arg>\S+))?\s*$` (aliases `re.escape`d and used **literally** — the
  operator includes a leading `/` if they want one). Alias changes take effect on plugin reload (registration-time),
  documented in the WebUI description.
- Args:
  - none → card with configured template
  - `文字` / `text` → text version (`format_user_text`)
  - `dashboard` / `terminal` / `sheet` → that **bundled** template (never an arbitrary path from chat)
  - `帮助` / `help` → short usage text
  - anything else → usage text
- Per-stream cooldown `command.cooldown_seconds` (default 30; 0 disables), in-memory `{stream_id: last_ts}`,
  shared with the tool's `send_card`. Cooldown hit → 「请 N 秒后再试」.
- Render failure / Playwright unavailable → sends `format_user_text` with a leading 「（图片渲染不可用，以下为文字版）」.
- Always returns `(ok, summary, 2)` so the message is intercepted.

### 5. Card pipeline

1. Resolve template: config `card.template` (relative → plugin dir; absolute allowed — operator-controlled) or a
   bundled name from the command arg. Read failure → bundled `assets/dashboard.html` + warning.
2. `build_card_html(snapshot, template_str, plugin_version)` → prepend embedded `@font-face` CSS
   (`Noto Sans SC` 400/700, `JetBrains Mono` 400 as `data:` woff2, cached per process) → substitute placeholders.
3. `ctx.render.html2png(html, selector="#card", device_scale_factor=card.scale, render_timeout_ms=card.render_timeout_ms, allow_network=False)`.
4. `card.format == "webp"` → Pillow lossless WebP (`lossless=True, method=6`); `png` → as-is. Pillow import failure →
   PNG + one warning.
5. `ctx.send.image(b64, stream_id)`; `False` → log + 「可能未送达」 (NapCat false-negative), never retried.

---

## Snapshot model (`maifetch/snapshot.py`)

All fields optional (`None` = unknown/hidden). Frozen dataclasses; `Snapshot.failed_sources: tuple[str, ...]`.

```python
@dataclass(frozen=True)
class Identity:
    nickname: str | None
    alias_names: tuple[str, ...]
    platforms: tuple[str, ...]          # platform NAMES only: bot.platform + the part before ':' of each
                                        # bot.platforms entry (format platform:账号); account IDs discarded
    account: str | None                 # bot.qq_account — hidden by default
    local_time: datetime | None         # tz-aware, process clock
    timezone: str | None                # IANA name when resolvable, else abbreviation

@dataclass(frozen=True)
class PluginInfo:
    plugin_id: str
    version: str

@dataclass(frozen=True)
class Runtime:
    host_version: str | None            # env MAIBOT_HOST_VERSION
    sdk_version: str | None             # maibot_sdk.__version__
    plugin_version: str                 # this plugin's manifest version
    online_since: datetime | None       # newest OnlineTime.start_timestamp
    plugins: tuple[PluginInfo, ...] | None   # None when list hidden; count kept separately
    plugin_count: int | None
    tool_count: int | None              # enabled components with type tool/action
    model_tasks: tuple[str, ...] | None # llm.get_available_models()

@dataclass(frozen=True)
class ModelUsage:
    model_name: str
    requests: int
    tokens: int
    avg_latency_s: float | None
    cost: float | None                  # hidden by default

@dataclass(frozen=True)
class Usage:
    window_days: int
    models: tuple[ModelUsage, ...]      # top-K by requests
    model_count: int | None             # models with usage rows in the window (totals cover all of them)
    total_requests: int | None          # summed over all rows fetched (Host cap 50), not only top-K
    total_tokens: int | None
    total_cost: float | None            # hidden by default
    totals_capped: bool                 # True when models() returned 50 rows → totals are a lower bound
    total_messages: int | None          # message_trend(days, top_chats=50).series["total"]
    messages_capped: bool               # True when 50 chat series came back → lower bound

@dataclass(frozen=True)
class Hardware:                          # present only when hardware.enabled
    os: str | None; kernel: str | None; arch: str | None
    cpu: str | None; cpu_cores: int | None
    mem_used: int | None; mem_total: int | None      # bytes
    disk_used: int | None; disk_total: int | None    # bytes, volume containing the plugin dir
    python: str | None; uptime_s: float | None; virt: str | None

@dataclass(frozen=True)
class Snapshot:
    collected_at: datetime
    identity: Identity
    runtime: Runtime
    usage: Usage
    hardware: Hardware | None
    failed_sources: tuple[str, ...]
```

### Data sources (`collect.py`)

All RPCs run concurrently via `asyncio.gather`, each wrapped in `asyncio.wait_for(…, 3.0)`; an exception/timeout
records the source name in `failed_sources` and leaves its fields `None`. Every source goes through
`ctx.call_capability(name, **args)` directly: on Host failure it returns the raw `{"success": False, "error": …}` dict,
which the collector treats as a failure (some SDK convenience proxies, e.g. `statistics.local.models`, turn that into
`[]`, which would wrongly render as "0 次").

| Source key | Call |
|---|---|
| `identity` | `ctx.config.get("bot.nickname")`, `"bot.alias_names"`, `"bot.platform"`, `"bot.platforms"`, `"bot.qq_account"` (only fetched when `show_account`) |
| `online` | `ctx.db.get("OnlineTime", order_by="-end_timestamp", limit=1, single_result=True)` |
| `plugins` | `ctx.component.get_all_plugins()` |
| `model_tasks` | `ctx.llm.get_available_models()` |
| `models` | `ctx.statistics.local.models(days=window_days, limit=50)` |
| `messages` | `ctx.statistics.local.message_trend(days=window_days, bucket="day", top_chats=50)` → `series["total"]` only. The Host sums **only the returned top-N chats** (no 「其他」 bucket) and caps N at 50, so 50 returned series ⇒ `messages_capped`. Chat labels in the response are discarded immediately — never logged, stored, or displayed |
| local | `os.environ["MAIBOT_HOST_VERSION"]`, `maibot_sdk.__version__`, manifest version, `datetime.now().astimezone()` |
| `hardware` | `asyncio.to_thread(collect_hardware, toggles)` only when `hardware.enabled` |

Manifest `capabilities`: `config.get`, `database.get`, `component.get_all_plugins`, `llm.get_available_models`,
`statistics.local.models`, `statistics.local.message_trend`, `render.html2png`, `send.text`, `send.image`.

### Hardware (`hardware.py`, stdlib only)

Static fields (os, kernel, arch, cpu, cores, python, virt) computed once and cached per process; dynamic
(memory, disk, uptime) per call. Each probe is individually try/except → `None`.

| Field | Linux | macOS | Windows |
|---|---|---|---|
| os | `/etc/os-release` `PRETTY_NAME` | `platform.mac_ver()` → `macOS 14.5` | `platform.release()`/`version()`; build ≥ 22000 → Windows 11 |
| kernel | `platform.release()` | `platform.release()` | build number |
| arch | `platform.machine()` | same | same |
| cpu | `/proc/cpuinfo` `model name` (ARM: `Hardware`/`Model`) | `sysctl -n machdep.cpu.brand_string` (subprocess, 2 s timeout) | `winreg` `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` `ProcessorNameString` |
| cores | `os.cpu_count()` (logical) | same | same |
| memory | `/proc/meminfo` MemTotal − MemAvailable | `sysctl -n hw.memsize` (total only) | `ctypes` `GlobalMemoryStatusEx` |
| disk | `shutil.disk_usage(plugin_dir)` | same | same |
| python | `platform.python_version()` (Runner uses Host's `sys.executable`) | same | same |
| uptime | `/proc/uptime` | `sysctl -n kern.boottime` | `ctypes` `GetTickCount64` |
| virt | `/.dockerenv` or `/proc/1/cgroup` ∋ docker/containerd/kubepods → `Docker/容器`; `/proc/version` ∋ microsoft → `WSL`; `/sys/class/dmi/id/{sys_vendor,product_name}` ∋ KVM/QEMU/VMware/VirtualBox/Hyper-V → that name | — | — |

Parsers are pure functions taking file text (testable on any OS with fixtures). Never read: hostname, network
interfaces, users, mounts list, serials, processes.

### Visibility (`redact.py`)

`apply_visibility(snapshot, visibility, hardware_cfg) → Snapshot` returns a copy with hidden fields set to `None`:

- `show_account = false` → `identity.account = None`
- `show_plugin_list = false` → `runtime.plugins = None` (count stays)
- `show_cost = false` → every `ModelUsage.cost = None`, `usage.total_cost = None`
- `hardware.enabled = false` → `hardware = None`; else each `show_*` false → that field `None`

All formatters, fragments, scalars and `{data_json}` read only the redacted snapshot, so a hidden field cannot leak
through any surface.

---

## Text formats (`text.py`)

### Injection (stable facts only — no counters, no times)

```
【maifetch·自身信息】你是「{nickname}」，运行在 MaiBot {host_version}（插件 SDK {sdk_version}），接入平台：{platforms}。
近 {N} 天主要使用的模型：{top-3 model names by requests}；已加载 {plugin_count} 个插件、{tool_count} 个工具。
需要版本、插件、模型、用量、在线时长等详情时调用 maifetch 工具，不要凭印象回答。
```

Unknown pieces are dropped from the sentence (not printed as 未知). Text only changes when one of these facts changes,
keeping the planner system-prompt prefix cache-stable across refreshes.

### Tool text (planner audience)

Sectioned plain text, e.g.:

```
【身份】昵称：麦麦（别名：小麦）；平台：qq、email；本地时间：2026-10-01 14:24（Asia/Shanghai）
【运行】MaiBot 1.3.1 · 插件 SDK 2.8.2 · maifetch 0.1.0；本次在线 3 天 4 小时（自 09-28 10:02）
【插件】12 个已加载、31 个工具：maibook@0.1.3、fetch-url@0.4.1、…
【模型任务】replyer、planner、utils、vlm、voice
【模型用量·近 7 天】调用次数最多的前 5 个（共 12 个模型，其余未列出）：deepseek-v3.2 1,284 次/1.86M tok/2.1s；…
                                        ← all listed: 「全部 3 个模型：」; capped: 「共 50+ 个模型」
【合计·近 7 天（全部模型）】1,774 次请求、2.41M tokens、3,906 条消息
【硬件】（仅开启时）Debian GNU/Linux 12 x86_64 · 内核 6.8.12-pve · Docker · AMD Ryzen 9 7950X ×32 · 内存 11.2/62.6 GiB · 磁盘 214/937 GiB · Python 3.12.7
（数据源未响应：…）            ← only when failed_sources non-empty
（回复用户时，请把与问题相关的事实写进 reply 工具的 reply_reference，回复器看不到本工具结果。）
```

`section` filters which blocks print. Unknown values render 「未知」. Capped totals render with a trailing `+`
(e.g. `3,906+ 条消息`) in every surface (tool/user text, tiles, scalars).

### User text (command fallback / `/maifetch 文字`)

Same blocks as tool text minus the final reply_reference hint and the failed-sources line.

---

## Templates (`card.py` + `assets/`)

### Contract

Substitution is impression-card style: literal `{key}` replacement (never `str.format`). The root element must be
`id="card"` (screenshot selector). Each bundled template starts with a comment header listing every placeholder and
fragment class; the README carries the full table.

- **Scalars** (HTML-escaped; hideable fields → `""` when absent, others → `未知`):
  `{nickname}` `{nickname_initial}` `{alias_names}` `{platforms}` `{account}` `{local_time}` `{timezone}`
  `{host_version}` `{sdk_version}` `{plugin_version}` `{uptime}` `{uptime_short}` `{online_since}`
  `{plugin_count}` `{tool_count}` `{model_tasks}` `{window_days}`
  `{total_requests}` `{total_tokens}` `{total_cost}` `{total_messages}` `{top_model}` `{top_model_more}` (counts all models, not just listed) `{model_scope}` (「前 5 / 共 12」 / 「共 3 个」 / "")
  `{hw_os}` `{hw_kernel}` `{hw_arch}` `{hw_cpu}` `{hw_memory}` `{hw_disk}` `{hw_python}` `{hw_uptime}` `{hw_virt}`
  `{generated_at}`
- **Fragments** (pre-rendered HTML, `""` when the section is hidden/empty):
  - `{tiles_html}` — 4 × `.mf-tile` (`<b>` value + `<span>` label): 本次在线, 插件·工具, tokens·N 天, and
    花费·N 天 when `show_cost` else 请求·N 天 (tile row never has a hole).
  - `{model_rows_html}` — `.mf-model-row` × top-K: `.mf-model-name`, `.mf-model-bar > i[style=width:%]`
    (relative to top requests), `.mf-model-req`, `.mf-model-tok`, `.mf-model-cost` (omitted when hidden).
  - `{plugin_list_html}` — `.mf-chip` × up to 8 plugin ids, then `.mf-chip.mf-more` 「+N」; `""` when list hidden.
  - `{hardware_block_html}` — `.mf-hw` with `.mf-hw-row` (`.mf-k` / `.mf-v`) per visible field; `""` when off.
  - `{hardware_lines_html}` — terminal-style `<div><span class="k">Key</span>: value</div>` lines preceded by a
    `.dim` separator; `""` when off.
  - Sheet tables: `{identity_rows_html}`, `{runtime_rows_html}`, `{model_table_rows_html}` (`<tr><td>…</td><td>…</td></tr>`
    rows; hidden fields produce no row) and `{hardware_table_html}` (`<div class="sec">硬件</div><table>…</table>` or `""`).
  - `{maimai_logo_svg}` — the pixel 麦麦 (below) as inline SVG, generated from one grid constant in `maifetch/logo.py`.
- **`{data_json}`** — redacted snapshot as JSON (`ensure_ascii=False`, `</` escaped as `<\/`), for templates that
  build themselves with inline JS inside `<script type="application/json" id="maifetch-data">{data_json}</script>`.

### Bundled templates

All flat, understated; widths are CSS px at `scale = 1.0`.

- **`assets/dashboard.html` (default)** — width 720, bg `#f6f7f9`, text `#23252a`, muted `#7b808b`, panels white
  with `#e4e6ea` border, bars `#7d8799`. Header: rounded avatar block 「麦」 + nickname + `MaiBot {host_version} ·
  SDK {sdk_version} · {platforms}`. Then `{tiles_html}` (4-col grid), 「模型用量 · 近 N 天」 box with
  `{model_rows_html}`, 「已加载插件」 box with `{plugin_list_html}` (box omitted when empty), `{hardware_block_html}`
  (2-col box), footer `{timezone} · {local_time}` left / `maifetch {plugin_version}` right.
- **`assets/terminal.html`** — width 760, bg `#1e1f24`, text `#c9ccd3`, mono `JetBrains Mono` with `Noto Sans SC`
  fallback for CJK. Window dots bar; left: inline-SVG pixel 麦麦 (below), right: `麦麦@MaiBot` title
  (`@` in `#86e541`), separator, keys in `#ef8d24` (Host, SDK, Online, Plugins, Platforms, Model, Usage), then
  `{hardware_lines_html}` (OS, Kernel, Virt, CPU, Memory, Disk, Python), then 6 swatches
  `#2f130a #ef8d24 #f6b866 #fcfdfc #86e541 #4f9a1f`.
- **`assets/sheet.html`** — width 680, bg `#fbfbfa`, border `#e3e3e0`, sectioned key/value tables: 身份 / 运行
  (incl. 模型任务) / 模型与用量·近 N 天 (per-model 次数 · tok · 平均延迟, plus 合计 row with messages) / 硬件 (when on);
  footer `maifetch {plugin_version}`.

### Pixel 麦麦 (terminal logo)

Hand-drawn 20×14 "dorky" Sacabambaspis 麦麦 (reference: `MaiBot/depends-data/maimai-v2.png`, top figure):
cross-eyed googly eyes (pupils face each other), tiny beak on the orange/white line, lopsided three-lobe clover tail,
two-leaf sprout, no outline. Rendered as inline `<svg viewBox="0 0 20 14" shape-rendering="crispEdges">` with
run-length `<rect>`s, displayed at 6 px/cell (120 × 84). Generated by `maifetch/logo.py` and exposed as the
`{maimai_logo_svg}` placeholder; `terminal.html` uses it, custom templates may use or replace it.

```
...........gg.gg....
............ggg.....
.............g......
.gg.......ooooooo...
.ggg...oooooooooooo.
..gggooooooEEEooEEEo
...goooooooEEpoopEEo
gg.ooooooooEEEooEEEo
gggoooooooooooppooow
gg.ooooooooooopwwww.
....ooooowwwwwwwww..
...ggwwwwwwwwwww....
.ggg...wwwwww.......
.gg.................
```

Palette: `o` body `#ef8d24` · `w`/`E` belly & eye white `#fcfdfc` · `p` pupils/beak `#2f130a` · `g` sprout/tail
`#86e541` · `.` transparent. (Mockups: workspace `.superpowers/brainstorm/1902611-1790839283/content/`.)

### Fonts

`@font-face` CSS built once per process from `assets/fonts/*.woff2` as `data:` URIs (impression-card's
`_embedded_font_face_css` approach) and prepended to every template, so custom templates get the fonts for free and
rendering never needs the network. Ship `assets/fonts/OFL.txt` (Noto Sans SC and JetBrains Mono are SIL OFL 1.1).

---

## Configuration

`config_version = "1.0.0"`. Ships `config.default.toml`, copied to `config.toml` by `create_plugin()` when missing
(world-clock's `_ensure_shipped_config_present`; no bare-config restore needed for a plugin that ships the template
from its first release). `normalize_plugin_config` runs maifetch normalization (defaults merge, numeric
coercion/clamping, format/template/alias cleanup, version stamp) before the SDK's. No optional (`| None`) fields, so
no WebUI blank-optional coercion is needed; blank/invalid numbers fall back to defaults. Each section is a
`PluginConfigBase` with `__ui_label__` / `__ui_icon__` / `__ui_order__` and zh-CN `description`s.

```toml
[plugin]
enabled = true
config_version = "1.0.0"

[visibility]          # 「可见性」— 同时作用于工具、提示注入与状态卡片
show_account = false       # 机器人账号（bot.qq_account）
show_plugin_list = true    # 已加载插件列表（关闭后仍显示数量）
show_cost = true           # 花费（按模型与合计）；默认显示（上线评审后调整）

[usage]               # 「用量统计」
window_days = 7            # 1–90
top_models = 5             # 1–10

[injection]           # 「规划器注入」
enabled = true
refresh_minutes = 10       # 1–1440

[command]             # 「命令」
aliases = []               # 额外触发词，如 ["/状态"]；修改后需重载插件生效
cooldown_seconds = 30      # 同一聊天内发卡片的冷却；0 = 不限制

[card]                # 「状态卡片」
template = "assets/dashboard.html"   # 相对插件目录或绝对路径；内置 dashboard / terminal / sheet
scale = 1.0                # 0.5–3.0；越大越清晰、图片越大（NapCat 大图可能误报发送失败）
format = "webp"            # webp（无损，体积小）| png
render_timeout_ms = 20000  # 1000–45000

[hardware]            # 「硬件信息」— 默认显示；说明中提示群聊中所有人可见，不希望暴露时关闭
enabled = true
show_os = true
show_kernel = true
show_arch = true
show_cpu = true
show_memory = true
show_disk = true
show_python = true
show_uptime = true
show_virt = true
```

Out-of-range numbers are clamped during normalization (with a note), not rejected. `on_config_update` refreshes
settings, restarts/stops the refresher as needed, and triggers an immediate refresh.

## Manifest

```json
{
  "manifest_version": 2,
  "id": "com.0-hz.maifetch",
  "version": "0.1.0",
  "name": "maifetch（麦麦状态）",
  "description": "让麦麦了解自己：版本、平台、插件与工具、模型用量、在线时长（可选硬件信息）。提供规划器工具、规划器自身信息注入与 /maifetch 状态卡片图。",
  "author": {"name": "kes", "url": "https://github.com/yufei-pan"},
  "license": "MIT",
  "urls": {
    "repository": "https://github.com/yufei-pan/maibot-maifetch",
    "homepage": "https://github.com/yufei-pan/maibot-maifetch",
    "documentation": "https://github.com/yufei-pan/maibot-maifetch/blob/main/README.md",
    "issues": "https://github.com/yufei-pan/maibot-maifetch/issues"
  },
  "host_application": {"min_version": "1.3.1", "max_version": "1.99.99"},
  "sdk": {"min_version": "2.8.2", "max_version": "2.99.99"},
  "dependencies": [{"type": "python_package", "name": "pillow", "version_spec": ">=10.0.0"}],
  "capabilities": ["config.get", "database.get", "component.get_all_plugins", "llm.get_available_models",
                   "statistics.local.models", "statistics.local.message_trend", "render.html2png",
                   "send.text", "send.image"],
  "i18n": {"default_locale": "zh-CN"}
}
```

---

## Error handling

| Failure | Behavior |
|---|---|
| One RPC source fails/times out (3 s) | Fields `None` → 「未知」; source listed in `failed_sources`; tool text notes it; card unaffected otherwise |
| All sources fail | Tool still returns local facts (versions, time); command still renders |
| Refresher fails | Keep last cache; warning log; hook keeps injecting last good text |
| Cache not ready (first seconds) | Hook does nothing |
| Hook internal error | Caught → continue unmodified (plus `error_policy=SKIP`) |
| Template unreadable | Bundled dashboard + warning |
| Render error/timeout (no Playwright etc.) | Command: text fallback with note; tool: 「卡片渲染不可用，仅返回文字」 |
| Pillow missing | PNG + one warning |
| `send.image` returns False | Log; message 「可能未送达」 (NapCat ack false-negative); no retry |
| Cooldown | 「请 N 秒后再试」, still intercepted |
| Hardware probe fails | That field `None`; other fields unaffected |

## Testing

Run: `PYTHONPATH=.:../maibot-plugin-sdk pytest -v` and `PYTHONPATH=../maibot-plugin-sdk python tests/smoke_test.py`.

- `test_hardware.py` — parsers vs fixture text (`os-release`, `cpuinfo` x86 + ARM, `meminfo`, `uptime`, cgroup
  docker/kubepods, `/proc/version` WSL, DMI vendors); assert forbidden data (hostname etc.) never appears in output.
- `test_redact.py` — for each toggle, the hidden value is absent from tool text, user text, injection, every scalar,
  every fragment, and `data_json`.
- `test_text.py` — section filtering + aliases; unknown section note; reply_reference hint present; injection text
  is identical across snapshots differing only in counters/times (cache stability).
- `test_card.py` — placeholder substitution; HTML escaping of hostile values (`<script>`, `{nickname}` inside
  values not re-expanded); cost tile swap; `+N` chip overflow; `data_json` `</` escaping; each bundled template has
  `id="card"` and no unknown placeholders left after rendering.
- `test_config.py` — defaults, blank-WebUI coercion, clamping, version stamp, bare-config restore.
- `test_collect.py` — fake ctx: concurrent collection, per-source timeout → `failed_sources`, response-shape
  parsing for each capability, 50-row/50-chat responses set `totals_capped`/`messages_capped` (rendered with `+`),
  chat labels from `message_trend` never reach the snapshot.
- `smoke_test.py` — fake ctx end to end: tool (`all` / one section / `send_card`), command (card, `文字`, bundled
  name, cooldown, render failure fallback), hook (items schema v1 append, legacy messages, no system item, cache
  empty).
- Manual on a live Host 1.3.1 + NapCat: `/maifetch` (each template), tool via chat 「你是什么模型？」, hardware on/off,
  WebUI config edits; verify planner prompt shows the injection (Maisaka monitor).

## Packaging

`README.md` (zh-CN: install/symlink, commands, tool, config table, template placeholder/class reference, privacy
notes on hardware), `CHANGELOG.md` (0.1.0), `LICENSE` (MIT), `.gitignore` (same as world-clock: `__pycache__/`,
`.venv/`, `.pytest_cache/`, `config.local.toml`, `config.toml`).

## Risks / future

- Host may later expose per-task model config or Host uptime directly → switch sources, keep snapshot shape.
- If `statistics.local.*` response shapes change, `collect.py` parsing is the single place to adapt (tested with
  shape fixtures).
- Font data URIs make each render's HTML ~3 MB over RPC (same as impression-card today); acceptable, revisit if
  render latency is an issue.
