"""可见性脱敏：所有输出面都只读本函数返回的快照，隐藏字段因此不可能从任何渠道泄露。"""

from __future__ import annotations

from dataclasses import replace

from maifetch.config import HardwareToggles, Visibility
from maifetch.snapshot import Snapshot


def apply_visibility(
    snapshot: Snapshot,
    visibility: Visibility,
    hardware: HardwareToggles,
    *,
    show_by_requests: bool = True,
    show_by_cost: bool = True,
) -> Snapshot:
    identity = snapshot.identity if visibility.show_account else replace(snapshot.identity, account=None)
    runtime = snapshot.runtime if visibility.show_plugin_list else replace(snapshot.runtime, plugins=None)
    usage = snapshot.usage
    if not visibility.show_cost:
        usage = replace(usage, total_cost=None, models=tuple(replace(m, cost=None) for m in usage.models))
    show_cost_ranking = show_by_cost and visibility.show_cost
    usage = replace(
        usage,
        show_request_ranking=show_by_requests,
        show_cost_ranking=show_cost_ranking,
        models_by_cost=usage.models_by_cost if show_cost_ranking else (),
        costed_model_count=usage.costed_model_count if show_cost_ranking else None,
    )

    hw = snapshot.hardware
    if hw is not None and not hardware.enabled:
        hw = None
    elif hw is not None:
        hw = replace(
            hw,
            os=hw.os if hardware.os else None,
            kernel=hw.kernel if hardware.kernel else None,
            arch=hw.arch if hardware.arch else None,
            cpu=hw.cpu if hardware.cpu else None,
            cpu_cores=hw.cpu_cores if hardware.cpu else None,
            mem_used=hw.mem_used if hardware.memory else None,
            mem_total=hw.mem_total if hardware.memory else None,
            disk_used=hw.disk_used if hardware.disk else None,
            disk_total=hw.disk_total if hardware.disk else None,
            python=hw.python if hardware.python else None,
            uptime_s=hw.uptime_s if hardware.uptime else None,
            virt=hw.virt if hardware.virt else None,
        )
    return replace(snapshot, identity=identity, runtime=runtime, usage=usage, hardware=hw)
