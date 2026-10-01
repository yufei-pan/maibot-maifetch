from __future__ import annotations

from maifetch.cooldown import Cooldown


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_cooldown_per_key() -> None:
    clock = Clock()
    cooldown = Cooldown(30, clock=clock)
    assert cooldown.hit("a") == 0
    clock.now += 10
    assert cooldown.hit("a") == 20
    assert cooldown.hit("b") == 0
    clock.now += 20.5
    assert cooldown.hit("a") == 0


def test_cooldown_rounds_up_and_disables() -> None:
    clock = Clock()
    cooldown = Cooldown(30, clock=clock)
    cooldown.hit("a")
    clock.now += 29.9
    assert cooldown.hit("a") == 1
    cooldown.set_seconds(0)
    assert cooldown.hit("a") == 0
    assert cooldown.hit("a") == 0
