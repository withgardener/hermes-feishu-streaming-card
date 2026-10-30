"""Read-only task state and typography roles, independent of card JSON dialects.

The renderer supplies a session view and can inject its observation clock.
These functions never change execution state, selection state, or permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any


TASK_TEXT_SIZE_DEFAULTS = {
    "body": "normal", "reasoning": "small", "tool": "small",
    "notice": "normal", "footer": "notation",
}


TASK_OBSERVATION_SECONDS = 60


def task_observation_delay(session: Any, *, now: float | None = None) -> float:
    """Time until an honest silence observation; invalid clocks never busy-loop."""
    clock = time.time() if now is None else now
    updated = session.updated_at
    if (isinstance(updated, (int, float)) and not isinstance(updated, bool)
            and math.isfinite(updated) and updated > 0 and math.isfinite(clock)):
        return max(0.0, TASK_OBSERVATION_SECONDS - max(0.0, clock - updated))
    return float(TASK_OBSERVATION_SECONDS)


@dataclass(frozen=True)
class TaskPresentation:
    label: str
    color: str
    observation: str = ""


def task_presentation(session: Any, *, now: float | None = None) -> TaskPresentation:
    """Describe observed state without inferring success or liveness from silence."""
    if getattr(session, "presentation_state", "") == "reconnecting":
        return TaskPresentation("等待状态同步", "grey", "连接已重建；执行状态尚未同步，原授权不会恢复。")
    interaction = session.active_interaction
    if interaction is not None:
        if interaction.status == "paused":
            return TaskPresentation("审批已暂停", "orange", "请重新查看操作范围；旧授权不会自动恢复。")
        if interaction.status == "pending":
            return TaskPresentation(
                "等待审批" if interaction.kind == "approval" else "等待你的选择",
                "orange",
                "请核对完整操作范围后选择。" if interaction.kind == "approval" else "提交后会在这里显示回执。",
            )
    if session.status == "failed":
        return TaskPresentation("已停止", "red")
    if session.status == "completed":
        return TaskPresentation("已完成", "green")
    if session.delivery_kind == "notice":
        return TaskPresentation("状态更新", "blue")
    clock = time.time() if now is None else now
    updated = session.updated_at
    observation = ""
    if (isinstance(updated, (int, float)) and not isinstance(updated, bool)
            and math.isfinite(updated) and updated > 0 and math.isfinite(clock)):
        age = max(0, int(clock - updated))
        if age >= TASK_OBSERVATION_SECONDS:
            observation = f"最近 {age // 60} 分钟未收到新事件；任务是否仍在执行尚待确认。"
    label = "等待新进展" if observation else "执行中" if session.tools or session.answer_text else "思考中"
    return TaskPresentation(label, "grey" if observation else "blue", observation)
