"""maifetch（麦麦状态）插件入口。

让麦麦了解自己：规划器工具 maifetch、规划器系统提示词里的自身信息摘要，以及 /maifetch 状态卡片图。
实现逻辑在同目录的 maifetch/ 包内。Runner 只把插件的上级目录放进 sys.path，
因此这里先把插件目录加入 sys.path 再导入（包名全局唯一，避免与其他插件冲突）。
"""

from __future__ import annotations

import asyncio
import json
import sys
from base64 import b64decode, b64encode
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from maibot_sdk import CONFIG_RELOAD_SCOPE_SELF, Command, HookHandler, MaiBotPlugin, Tool
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder, ToolParameterInfo, ToolParamType

_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from maifetch.card import build_card_html
from maifetch.collect import collect_snapshot
from maifetch.config import (
    MaiFetchConfig,
    Settings,
    build_settings,
    ensure_shipped_config_present,
    normalize_config_dict,
)
from maifetch.cooldown import Cooldown
from maifetch.inject import apply_injection
from maifetch.redact import apply_visibility
from maifetch.registration import (
    COMMAND_COMPONENT_NAME,
    HELP_TEXT,
    SECTION_PARAM_DESCRIPTION,
    SEND_CARD_PARAM_DESCRIPTION,
    TOOL_NAME,
    build_command_pattern,
    parse_command_arg,
    patch_components,
    tool_description,
)
from maifetch.render import font_face_css, load_template, png_to_webp
from maifetch.snapshot import Snapshot
from maifetch.text import SECTIONS, format_injection, format_tool_text, format_user_text, parse_bool

PLUGIN_VERSION: str = json.loads((_PLUGIN_DIR / "_manifest.json").read_text(encoding="utf-8"))["version"]
FONT_DIR = _PLUGIN_DIR / "assets" / "fonts"
HOOK_TIMEOUT_MS = 5000
RETRY_SECONDS = 30
WARMUP_SECONDS = 60
# 注入摘要依赖的数据源；其中任何一个失败，摘要就不算完整
INJECTION_SOURCES = frozenset({"identity", "models", "plugins"})
RENDER_VIEWPORT = {"width": 800, "height": 600}

CARD_SENT = "sent"
CARD_MAYBE_FAILED = "maybe_failed"
CARD_RENDER_FAILED = "render_failed"
_TOOL_CARD_STATUS = {
    CARD_SENT: "已发送状态卡片。",
    CARD_MAYBE_FAILED: "状态卡片可能未送达。",
    CARD_RENDER_FAILED: "卡片渲染不可用，仅返回文字。",
}


class MaiFetchPlugin(MaiBotPlugin):
    """maifetch 插件主体：只做组件与生命周期胶水，逻辑都在 maifetch 包里。"""

    config_model = MaiFetchConfig

    def __init__(self) -> None:
        super().__init__()
        self._settings: Settings | None = None
        self._injection_text = ""
        self._refresh_task: asyncio.Task[None] | None = None
        self._cooldown = Cooldown(0)
        self._webp_warned = False
        self._has_complete_cache = False
        self._warmup_pending = False

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #
    def normalize_plugin_config(self, config_data: Mapping[str, Any] | None) -> tuple[dict[str, Any], bool]:
        raw = dict(config_data or {})
        normalized, notes = normalize_config_dict(raw)
        sdk_normalized, sdk_changed = super().normalize_plugin_config(normalized)
        if notes:
            self._get_logger().info("maifetch 配置已规范化：%s", "；".join(notes))
        return sdk_normalized, sdk_changed or bool(notes) or sdk_normalized != raw

    def _refresh_settings(self) -> Settings:
        settings = build_settings(self.config)  # type: ignore[arg-type]
        self._settings = settings
        self._cooldown.set_seconds(settings.cooldown_seconds)
        return settings

    def _require_settings(self) -> Settings:
        return self._settings if self._settings is not None else self._refresh_settings()

    def get_components(self) -> list[dict[str, Any]]:
        """注册前用当前配置修补工具描述（统计窗口）与命令正则（别名）。"""

        if self._plugin_config_instance is not None:
            self._refresh_settings()
        components = super().get_components()
        settings = self._settings or build_settings(MaiFetchConfig())
        patch_components(components, window_days=settings.window_days, aliases=settings.aliases)
        return components

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    async def on_load(self) -> None:
        settings = self._refresh_settings()
        # Runner 逐个激活插件：首次刷新时排在后面的插件还没注册，加载后补刷一次以拿到完整插件数
        self._warmup_pending = True
        self._restart_refresher()
        self.ctx.logger.info(
            "maifetch 已加载：注入=%s，模板=%s，硬件=%s，统计窗口=%s 天",
            settings.injection_enabled,
            settings.template,
            settings.hardware.enabled,
            settings.window_days,
        )

    async def on_unload(self) -> None:
        await self._stop_refresher()
        self.ctx.logger.info("maifetch 已卸载")

    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        del config_data
        if scope != CONFIG_RELOAD_SCOPE_SELF:
            return
        self._refresh_settings()
        self._restart_refresher()
        self.ctx.logger.info("maifetch 配置已更新：version=%s（命令别名与工具描述在重载插件后生效）", version)

    # ------------------------------------------------------------------ #
    # 后台刷新（规划器注入用的缓存）
    # ------------------------------------------------------------------ #
    def _restart_refresher(self) -> None:
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_task.cancel()
        self._refresh_task = None
        settings = self._require_settings()
        if settings.enabled and settings.injection_enabled:
            self._refresh_task = asyncio.create_task(self._refresh_loop(), name="maifetch.refresh")
        else:
            self._injection_text = ""
            self._has_complete_cache = False

    async def _stop_refresher(self) -> None:
        task, self._refresh_task = self._refresh_task, None
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def _next_delay(self, ok: bool) -> float:
        """下一次刷新前的等待秒数：摘要不完整时 30 s 重试；加载后首次成功再补刷一次；之后按配置间隔。"""

        interval = self._require_settings().refresh_minutes * 60
        if not ok:
            return min(RETRY_SECONDS, interval)
        if self._warmup_pending:
            self._warmup_pending = False
            return min(WARMUP_SECONDS, interval)
        return interval

    async def _refresh_loop(self) -> None:
        while True:
            ok = await self._refresh_once()
            await asyncio.sleep(self._next_delay(ok))

    async def _refresh_once(self) -> bool:
        """刷新注入摘要。返回 False 表示还没有完整摘要（如 Host 尚未就绪），调用方会 30 s 后重试。"""

        try:
            snapshot = await self._collect()
        except Exception as exc:  # noqa: BLE001 - 刷新失败沿用旧缓存
            self.ctx.logger.warning("maifetch 刷新自身信息失败，沿用上次缓存：%s", exc)
            return self._has_complete_cache
        if not set(snapshot.failed_sources) & INJECTION_SOURCES:
            self._injection_text = format_injection(snapshot)
            self._has_complete_cache = True
            return True
        if self._has_complete_cache:
            self.ctx.logger.debug(
                "maifetch 部分数据源不可用（%s），保留上次完整摘要", "、".join(snapshot.failed_sources)
            )
            return True
        # 还没有完整摘要：先用残缺的（总比没有好），并继续快速重试
        self._injection_text = format_injection(snapshot)
        return False

    async def _collect(self) -> Snapshot:
        settings = self._require_settings()
        raw = await collect_snapshot(self.ctx, settings, plugin_version=PLUGIN_VERSION, plugin_dir=_PLUGIN_DIR)
        return apply_visibility(raw, settings.visibility, settings.hardware)

    # ------------------------------------------------------------------ #
    # 规划器注入
    # ------------------------------------------------------------------ #
    @HookHandler(
        "maisaka.planner.before_request",
        name="maifetch_planner_inject",
        description="把麦麦的自身信息摘要追加到规划器系统提示词",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        timeout_ms=HOOK_TIMEOUT_MS,
        error_policy=ErrorPolicy.SKIP,
    )
    async def on_planner_before_request(self, **kwargs: Any) -> dict[str, Any]:
        try:
            settings = self._settings
            text = self._injection_text
            if settings is None or not settings.enabled or not settings.injection_enabled or not text:
                return {"action": "continue"}
            if apply_injection(kwargs, text):
                return {"action": "continue", "modified_kwargs": kwargs}
        except Exception as exc:  # noqa: BLE001 - 注入失败绝不阻塞规划器
            self.ctx.logger.warning("maifetch 注入规划器提示词失败：%s", exc)
        return {"action": "continue"}

    # ------------------------------------------------------------------ #
    # 规划器工具
    # ------------------------------------------------------------------ #
    @Tool(
        TOOL_NAME,
        description=tool_description(7),
        parameters=[
            ToolParameterInfo(
                name="section",
                param_type=ToolParamType.STRING,
                description=SECTION_PARAM_DESCRIPTION,
                required=False,
                enum_values=list(SECTIONS),
            ),
            ToolParameterInfo(
                name="send_card",
                param_type=ToolParamType.BOOLEAN,
                description=SEND_CARD_PARAM_DESCRIPTION,
                required=False,
            ),
        ],
    )
    async def tool_maifetch(
        self, section: Any = "all", send_card: Any = False, stream_id: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        del kwargs
        settings = self._require_settings()
        if not settings.enabled:
            return {"success": False, "content": "maifetch 已在配置中停用。"}
        snapshot = await self._collect()
        text = format_tool_text(snapshot, section)
        if parse_bool(send_card):
            status = await self._tool_send_card(snapshot, str(stream_id or ""))
            text = f"{status}\n{text}"
        return {"success": True, "content": text}

    async def _tool_send_card(self, snapshot: Snapshot, stream_id: str) -> str:
        if not stream_id:
            return "当前没有可发送的聊天，未发送卡片。"
        remaining = self._cooldown.hit(stream_id)
        if remaining:
            return f"冷却中，{remaining} 秒后可再发卡片。"
        return _TOOL_CARD_STATUS[await self._render_and_send(snapshot, stream_id)]

    # ------------------------------------------------------------------ #
    # /maifetch 命令
    # ------------------------------------------------------------------ #
    @Command(
        COMMAND_COMPONENT_NAME,
        description="查看麦麦状态卡片：/maifetch [文字|dashboard|terminal|sheet]",
        pattern=build_command_pattern(()),
    )
    async def cmd_maifetch(self, **kwargs: Any) -> tuple[bool, str, int]:
        stream_id = str(kwargs.get("stream_id") or "")
        if not stream_id:
            return False, "缺少 stream_id", 2
        settings = self._require_settings()
        if not settings.enabled:
            return False, "maifetch 已停用", 2
        matched = kwargs.get("matched_groups")
        action, bundled = parse_command_arg(matched.get("arg") if isinstance(matched, Mapping) else None)
        if action == "help":
            await self.ctx.send.text(HELP_TEXT, stream_id)
            return True, "已发送用法", 2
        if action == "text":
            await self.ctx.send.text(format_user_text(await self._collect()), stream_id)
            return True, "已发送文字版状态", 2
        remaining = self._cooldown.hit(stream_id)
        if remaining:
            await self.ctx.send.text(f"请 {remaining} 秒后再试。", stream_id)
            return False, "冷却中", 2
        snapshot = await self._collect()
        status = await self._render_and_send(snapshot, stream_id, bundled)
        if status == CARD_RENDER_FAILED:
            await self.ctx.send.text("（图片渲染不可用，以下为文字版）\n" + format_user_text(snapshot), stream_id)
            return True, "图片渲染不可用，已发送文字版", 2
        if status == CARD_MAYBE_FAILED:
            return False, "状态卡片可能未送达", 2
        return True, "已发送状态卡片", 2

    # ------------------------------------------------------------------ #
    # 卡片渲染与发送
    # ------------------------------------------------------------------ #
    async def _render_and_send(self, snapshot: Snapshot, stream_id: str, bundled_name: str | None = None) -> str:
        settings = self._require_settings()
        try:
            template = load_template(_PLUGIN_DIR, settings.template, bundled_name, self.ctx.logger)
            html = build_card_html(snapshot, template, font_face_css(FONT_DIR))
            result = await self.ctx.render.html2png(
                html,
                selector="#card",
                viewport=dict(RENDER_VIEWPORT),
                device_scale_factor=settings.scale,
                omit_background=True,
                render_timeout_ms=settings.render_timeout_ms,
                allow_network=False,
            )
        except Exception as exc:  # noqa: BLE001 - 无 Playwright / 渲染崩溃时回退文字
            self.ctx.logger.warning("maifetch 卡片渲染失败：%s", exc)
            return CARD_RENDER_FAILED
        image_b64 = result.get("image_base64") if isinstance(result, Mapping) else None
        if not image_b64:
            reason = result.get("error") if isinstance(result, Mapping) else result
            self.ctx.logger.warning("maifetch 卡片渲染未返回图片：%s", reason)
            return CARD_RENDER_FAILED
        if settings.image_format == "webp":
            try:
                webp = await asyncio.to_thread(png_to_webp, b64decode(image_b64))
            except ValueError:  # base64 解码失败（binascii.Error 是 ValueError 子类）：按原样发送
                webp = None
            if webp is not None:
                image_b64 = b64encode(webp).decode("ascii")
            elif not self._webp_warned:
                self._webp_warned = True
                self.ctx.logger.warning("maifetch 无法转为 WebP（Pillow 不可用或编码失败），改发 PNG")
        try:
            sent = await self.ctx.send.image(image_b64, stream_id)
        except Exception as exc:  # noqa: BLE001 - RPC 超时 / Host 异常：可能已送达，也可能没有
            self.ctx.logger.warning("maifetch 状态卡片发送异常（可能未送达）：%s", exc)
            return CARD_MAYBE_FAILED
        if sent:
            return CARD_SENT
        self.ctx.logger.warning("maifetch 状态卡片发送返回失败（经 NapCat 发送大图时可能是误报）：stream=%s", stream_id)
        return CARD_MAYBE_FAILED


def create_plugin() -> MaiFetchPlugin:
    """创建插件实例；首次运行时先落盘带注释的配置模板。"""

    ensure_shipped_config_present(_PLUGIN_DIR)
    return MaiFetchPlugin()
