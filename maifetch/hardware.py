"""stdlib-only 硬件信息采集（默认关闭的「炫耀模式」）。

绝不读取：主机名、网络接口、用户、挂载列表、序列号、进程。所有探测都可失败，失败即为 None。
本模块是阻塞的，调用方需放进 asyncio.to_thread。
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from maifetch.snapshot import Hardware

_CONTAINER_CGROUP_MARKERS = ("docker", "containerd", "kubepods", "libpod")
_VM_MARKERS = (("qemu", "QEMU"), ("kvm", "KVM"), ("vmware", "VMware"), ("virtualbox", "VirtualBox"), ("xen", "Xen"))


def parse_os_release(text: str) -> str | None:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    if fields.get("PRETTY_NAME"):
        return fields["PRETTY_NAME"]
    joined = " ".join(part for part in (fields.get("NAME"), fields.get("VERSION")) if part)
    return joined or None


def parse_cpuinfo(text: str) -> str | None:
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        name = key.strip()
        if sep and name in ("model name", "Hardware", "Model") and name not in found and value.strip():
            found[name] = value.strip()
    for name in ("model name", "Hardware", "Model"):
        if name in found:
            return found[name]
    return None


def parse_meminfo(text: str) -> tuple[int | None, int | None]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"^(\w+):\s+(\d+)\s*kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if total is None:
        return None, None
    if available is None:
        return None, total
    return total - available, total


def parse_uptime(text: str) -> float | None:
    try:
        return float(text.split()[0])
    except (IndexError, ValueError):
        return None


def detect_virt(
    *, container_marker: bool, cgroup: str, proc_version: str, dmi_vendor: str, dmi_product: str
) -> str | None:
    if container_marker or any(marker in cgroup.lower() for marker in _CONTAINER_CGROUP_MARKERS):
        return "Docker/容器"
    if "microsoft" in proc_version.lower():
        return "WSL"
    vendor, product = dmi_vendor.lower(), dmi_product.lower()
    if "microsoft" in vendor and "virtual machine" in product:
        return "Hyper-V"
    for marker, label in _VM_MARKERS:
        if marker in vendor or marker in product:
            return label
    return None


def windows_os_name(release: str, version: str) -> str:
    try:
        build = int(version.split(".")[2])
    except (IndexError, ValueError):
        build = 0
    name = "Windows 11" if release == "10" and build >= 22000 else f"Windows {release}"
    return f"{name} (build {build})" if build else name


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _sysctl(key: str) -> str | None:
    try:
        result = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, timeout=2, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _windows_cpu_name() -> str | None:
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip() or None
    except Exception:  # noqa: BLE001 - 非 Windows 或无权限
        return None


@dataclass(frozen=True)
class _Static:
    os: str | None
    kernel: str | None
    arch: str | None
    cpu: str | None
    cores: int | None
    python: str | None
    virt: str | None


@lru_cache(maxsize=1)
def _static_info() -> _Static:
    system = platform.system()
    kernel = platform.release() or None
    virt: str | None = None
    if system == "Linux":
        os_name = parse_os_release(_read("/etc/os-release")) or "Linux"
        cpu = parse_cpuinfo(_read("/proc/cpuinfo"))
        virt = detect_virt(
            container_marker=Path("/.dockerenv").exists() or Path("/run/.containerenv").exists(),
            cgroup=_read("/proc/1/cgroup"),
            proc_version=_read("/proc/version"),
            dmi_vendor=_read("/sys/class/dmi/id/sys_vendor"),
            dmi_product=_read("/sys/class/dmi/id/product_name"),
        )
    elif system == "Darwin":
        version = platform.mac_ver()[0]
        os_name = f"macOS {version}" if version else "macOS"
        cpu = _sysctl("machdep.cpu.brand_string")
    elif system == "Windows":
        os_name = windows_os_name(platform.release(), platform.version())
        kernel = platform.version() or None
        cpu = _windows_cpu_name()
    else:
        os_name = system or None
        cpu = platform.processor() or None
    return _Static(
        os=os_name,
        kernel=kernel,
        arch=platform.machine() or None,
        cpu=cpu,
        cores=os.cpu_count(),
        python=platform.python_version(),
        virt=virt,
    )


def _windows_memory() -> tuple[int | None, int | None]:
    try:

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return None, None
        return int(status.ullTotalPhys - status.ullAvailPhys), int(status.ullTotalPhys)
    except Exception:  # noqa: BLE001
        return None, None


def _memory() -> tuple[int | None, int | None]:
    system = platform.system()
    if system == "Linux":
        return parse_meminfo(_read("/proc/meminfo"))
    if system == "Darwin":
        total = _sysctl("hw.memsize")
        return None, int(total) if total and total.isdigit() else None
    if system == "Windows":
        return _windows_memory()
    return None, None


def _uptime() -> float | None:
    system = platform.system()
    if system == "Linux":
        return parse_uptime(_read("/proc/uptime"))
    if system == "Darwin":
        match = re.search(r"sec\s*=\s*(\d+)", _sysctl("kern.boottime") or "")
        return max(0.0, time.time() - int(match.group(1))) if match else None
    if system == "Windows":
        try:
            ticks = ctypes.windll.kernel32.GetTickCount64  # type: ignore[attr-defined]
            ticks.restype = ctypes.c_ulonglong
            return ticks() / 1000.0
        except Exception:  # noqa: BLE001
            return None
    return None


def _disk(path: Path) -> tuple[int | None, int | None]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None, None
    return usage.used, usage.total


def collect_hardware(disk_path: Path) -> Hardware:
    """采集全部硬件字段（可见性由 redact 统一处理）。disk_path 只用于定位所在磁盘，不会出现在结果里。"""

    static = _static_info()
    mem_used, mem_total = _memory()
    disk_used, disk_total = _disk(disk_path)
    return Hardware(
        os=static.os,
        kernel=static.kernel,
        arch=static.arch,
        cpu=static.cpu,
        cpu_cores=static.cores,
        mem_used=mem_used,
        mem_total=mem_total,
        disk_used=disk_used,
        disk_total=disk_total,
        python=static.python,
        uptime_s=_uptime(),
        virt=static.virt,
    )
