"""测试用假 ctx：模拟 Host 能力调用、渲染与发送（不依赖 Host）。"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from types import SimpleNamespace
from typing import Any

from maifetch.config import MaiFetchConfig, Settings, build_settings

CONFIG_VALUES: dict[str, Any] = {
    "bot.nickname": "麦麦",
    "bot.alias_names": ["小麦"],
    "bot.platform": "qq",
    "bot.platforms": ["qq", "email"],
    "bot.qq_account": "123456789",
}


def sample_plugins() -> dict[str, Any]:
    return {
        "com.0-hz.maibook": {
            "name": "com.0-hz.maibook",
            "version": "0.1.3",
            "components": [
                {"name": "bookshelf_list", "type": "TOOL", "enabled": True},
                {"name": "maibook_cmd", "type": "COMMAND", "enabled": True},
            ],
        },
        "com.0-hz.maifetch": {
            "name": "com.0-hz.maifetch",
            "version": "0.1.0",
            "components": [
                {"name": "maifetch", "type": "TOOL", "enabled": True},
                {"name": "disabled_tool", "type": "TOOL", "enabled": False},
            ],
        },
    }


def default_responses() -> dict[str, Any]:
    return {
        "config.get": lambda key, default=None: CONFIG_VALUES.get(key, default),
        "database.get": lambda **_: {
            "id": 1,
            "start_timestamp": "2026-09-28T10:02:00",
            "end_timestamp": "2026-10-01T14:20:00",
        },
        "component.get_all_plugins": lambda **_: sample_plugins(),
        "llm.get_available_models": lambda **_: ["replyer", "planner", "utils", "vlm", "voice"],
        "statistics.local.models": lambda **_: [
            {
                "model_name": "qwen3-235b",
                "request_count": 402,
                "total_tokens": 410_000,
                "total_cost": 0.96,
                "avg_response_time": 3.4,
            },
            {
                "model_name": "deepseek-v3.2",
                "request_count": 1284,
                "total_tokens": 1_860_000,
                "total_cost": 3.42,
                "avg_response_time": 2.1,
            },
            {
                "model_name": "glm-4.6v",
                "request_count": 88,
                "total_tokens": 140_000,
                "total_cost": 0.49,
                "avg_response_time": 4.0,
            },
        ],
        "statistics.local.message_trend": lambda **_: {
            "timestamps": ["2026-09-25"],
            "values_by_key": {"c1": [3000.0], "c2": [906.0]},
            "labels_by_key": {"c1": "秘密群A", "c2": "秘密群B"},
            "total": 3906.0,
            "source_count": 2,
        },
    }


def tiny_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGBA", (4, 3), (239, 141, 36, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def make_settings(overrides: dict[str, Any] | None = None) -> Settings:
    return build_settings(MaiFetchConfig.model_validate(overrides or {}))


class FakeCtx:
    """最小 ctx：call_capability 按能力名查表；render / send 记录调用。"""

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        *,
        render_result: Any = None,
        send_ok: bool | Exception = True,
        delay: dict[str, float] | None = None,
    ) -> None:
        self.responses = default_responses()
        self.responses.update(responses or {})
        self.delay = delay or {}
        self.logger = logging.getLogger("maifetch.tests")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.rendered_html: list[str] = []
        self.render_kwargs: list[dict[str, Any]] = []
        self.sent_images: list[tuple[str, str]] = []
        self.sent_texts: list[tuple[str, str]] = []
        self._render_result = (
            render_result
            if render_result is not None
            else {"image_base64": base64.b64encode(tiny_png()).decode("ascii"), "mime_type": "image/png"}
        )
        self._send_ok = send_ok
        self.render = SimpleNamespace(html2png=self._html2png)
        self.send = SimpleNamespace(image=self._send_image, text=self._send_text)

    async def call_capability(self, capability: str, timeout_ms: int | None = None, **kwargs: Any) -> Any:
        del timeout_ms
        self.calls.append((capability, kwargs))
        if capability in self.delay:
            await asyncio.sleep(self.delay[capability])
        handler = self.responses.get(capability)
        if handler is None:
            return {"success": False, "error": f"未模拟的能力 {capability}"}
        value = handler(**kwargs) if callable(handler) else handler
        if isinstance(value, Exception):
            raise value
        return value

    async def _html2png(self, html: str, **kwargs: Any) -> Any:
        self.rendered_html.append(html)
        self.render_kwargs.append(kwargs)
        if isinstance(self._render_result, Exception):
            raise self._render_result
        return self._render_result

    async def _send_image(self, image_base64: str, stream_id: str, **kwargs: Any) -> bool:
        del kwargs
        self.sent_images.append((image_base64, stream_id))
        if isinstance(self._send_ok, Exception):
            raise self._send_ok
        return self._send_ok

    async def _send_text(self, text: str, stream_id: str, **kwargs: Any) -> bool:
        del kwargs
        self.sent_texts.append((text, stream_id))
        return True
