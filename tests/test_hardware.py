from __future__ import annotations

import getpass
import socket
from pathlib import Path

from maifetch.hardware import (
    collect_hardware,
    detect_virt,
    parse_cpuinfo,
    parse_meminfo,
    parse_os_release,
    parse_uptime,
    windows_os_name,
)
from maifetch.snapshot import Hardware

OS_RELEASE = 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nNAME="Debian GNU/Linux"\nVERSION_ID="12"\n'
CPUINFO_X86 = "processor\t: 0\nvendor_id\t: AuthenticAMD\nmodel name\t: AMD Ryzen 9 7950X 16-Core Processor\n"
CPUINFO_ARM = "processor\t: 0\nBogoMIPS\t: 108.00\n\nHardware\t: BCM2835\nModel\t\t: Raspberry Pi 4 Model B Rev 1.4\n"
MEMINFO = "MemTotal:       65641092 kB\nMemFree:         1234567 kB\nMemAvailable:   53897384 kB\n"


def test_parse_os_release() -> None:
    assert parse_os_release(OS_RELEASE) == "Debian GNU/Linux 12 (bookworm)"
    assert parse_os_release('NAME="Alpine Linux"\nVERSION="3.20"\n') == "Alpine Linux 3.20"
    assert parse_os_release("") is None


def test_parse_cpuinfo() -> None:
    assert parse_cpuinfo(CPUINFO_X86) == "AMD Ryzen 9 7950X 16-Core Processor"
    assert parse_cpuinfo(CPUINFO_ARM) == "BCM2835"
    assert parse_cpuinfo("") is None


def test_parse_meminfo() -> None:
    used, total = parse_meminfo(MEMINFO)
    assert total == 65641092 * 1024
    assert used == (65641092 - 53897384) * 1024
    assert parse_meminfo("MemTotal: 1024 kB\n") == (None, 1024 * 1024)
    assert parse_meminfo("") == (None, None)


def test_parse_uptime() -> None:
    assert parse_uptime("1047552.91 3901234.55\n") == 1047552.91
    assert parse_uptime("") is None
    assert parse_uptime("garbage") is None


def test_detect_virt() -> None:
    blank = {"cgroup": "", "proc_version": "", "dmi_vendor": "", "dmi_product": ""}
    assert detect_virt(container_marker=True, **blank) == "Docker/容器"
    assert detect_virt(container_marker=False, **{**blank, "cgroup": "0::/kubepods/besteffort/pod1"}) == "Docker/容器"
    assert (
        detect_virt(container_marker=False, **{**blank, "proc_version": "Linux 5.15.0-microsoft-standard-WSL2"})
        == "WSL"
    )
    assert detect_virt(container_marker=False, **{**blank, "dmi_vendor": "QEMU", "dmi_product": "Standard PC"}) == "QEMU"
    assert (
        detect_virt(
            container_marker=False, **{**blank, "dmi_vendor": "Microsoft Corporation", "dmi_product": "Virtual Machine"}
        )
        == "Hyper-V"
    )
    assert (
        detect_virt(container_marker=False, **{**blank, "dmi_vendor": "Microsoft Corporation", "dmi_product": "Surface"})
        is None
    )
    assert detect_virt(container_marker=False, **blank) is None


def test_windows_os_name() -> None:
    assert windows_os_name("10", "10.0.22631") == "Windows 11 (build 22631)"
    assert windows_os_name("10", "10.0.19045") == "Windows 10 (build 19045)"
    assert windows_os_name("2022Server", "") == "Windows 2022Server"


def test_collect_hardware_on_this_machine(tmp_path: Path) -> None:
    hw = collect_hardware(tmp_path)
    assert isinstance(hw, Hardware)
    assert hw.python is not None
    assert hw.disk_total is not None and hw.disk_total > 0


def test_collect_hardware_never_includes_identifying_data(tmp_path: Path) -> None:
    text = repr(collect_hardware(tmp_path))
    hostname = socket.gethostname()
    if len(hostname) >= 3:
        assert hostname not in text
    user = getpass.getuser()
    if len(user) >= 3:
        assert user not in text
    assert str(tmp_path) not in text
