"""Delivers reminders to the notify services."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    ACTION_DISMISS,
    ACTION_DONE,
    ACTION_PREFIX,
    ACTION_SNOOZE,
    NOTIFICATION_TITLE,
)
from .policy import ChannelPlan

_LOGGER = logging.getLogger(__name__)

GROUP = "task_reminder"


def tag_for(task_id: str) -> str:
    """Notification tag so a task's notification can be replaced and cleared."""
    return f"{GROUP}_{task_id}"


class Notifier:
    """Sends reminders; one failing channel never blocks the others."""

    def __init__(
        self,
        hass: HomeAssistant,
        phone: list[str],
        alexa: list[str],
        extra: list[str],
        tap_url: str | None = None,
    ) -> None:
        self.hass = hass
        self.phone = phone
        self.alexa = alexa
        self.extra = extra
        self.tap_url = tap_url or None
        # Called for every push that counts against the Companion app's daily limit.
        self.on_push: Callable[[], None] | None = None

    @property
    def configured(self) -> bool:
        """True when at least one notify service is configured."""
        return bool(self.phone or self.alexa or self.extra)

    async def _call(self, service: str, payload: dict[str, Any]) -> bool:
        try:
            await self.hass.services.async_call("notify", service, payload, blocking=True)
        except Exception:
            _LOGGER.warning("Notify service notify.%s failed", service, exc_info=True)
            return False
        if self.on_push and service in (*self.phone, *self.extra) and self._counts(payload):
            self.on_push()
        return True

    @staticmethod
    def _counts(payload: dict[str, Any]) -> bool:
        """Commands (clear_notification) and critical alerts do not count towards the limit."""
        if payload.get("message") == "clear_notification":
            return False
        sound = (payload.get("data") or {}).get("push", {}).get("sound")
        return not (isinstance(sound, dict) and sound.get("critical"))

    async def _send_all(self, calls: list[tuple[str, dict[str, Any]]]) -> int:
        results = await asyncio.gather(*(self._call(s, p) for s, p in calls))
        return sum(results)

    def _tap(self) -> dict[str, str]:
        """Where tapping the notification goes: iOS reads `url`, Android `clickAction`."""
        return {"url": self.tap_url, "clickAction": self.tap_url} if self.tap_url else {}

    @staticmethod
    def _actions(task_id: str, can_snooze: bool, dismissable: bool) -> list[dict]:
        actions = [{"action": f"{ACTION_PREFIX}{ACTION_DONE}_{task_id}", "title": "Done"}]
        if can_snooze:
            actions.append(
                {"action": f"{ACTION_PREFIX}{ACTION_SNOOZE}_{task_id}", "title": "Snooze"}
            )
        if dismissable:
            actions.append(
                {
                    "action": f"{ACTION_PREFIX}{ACTION_DISMISS}_{task_id}",
                    "title": "Dismiss",
                    "destructive": True,
                }
            )
        return actions

    async def async_remind(
        self,
        *,
        task_id: str,
        message: str,
        plan: ChannelPlan,
        time_critical: bool,
        can_snooze: bool,
        dismissable: bool,
        sound: str | None = None,
        alexa_targets: list[str] | None = None,
        tag: str | None = None,
    ) -> int:
        """Send a reminder along the plan. Returns how many services accepted it."""
        data: dict[str, Any] = {
            "tag": tag or tag_for(task_id),
            "group": GROUP,
            "actions": self._actions(task_id, can_snooze, dismissable),
            **self._tap(),
        }
        push: dict[str, Any] = {}
        if plan.critical:
            push["sound"] = {"name": sound or "default", "critical": 1, "volume": 1.0}
        else:
            if time_critical:
                push["interruption-level"] = "time-sensitive"
            if sound:
                push["sound"] = sound
        if push:
            data["push"] = push

        calls: list[tuple[str, dict[str, Any]]] = []
        if plan.phone:
            calls += [
                (s, {"title": NOTIFICATION_TITLE, "message": message, "data": data})
                for s in self.phone
            ]
        if plan.extra:
            calls += [
                (s, {"title": NOTIFICATION_TITLE, "message": message, "data": data})
                for s in self.extra
            ]
        if plan.alexa:
            targets = self.alexa if alexa_targets is None else alexa_targets
            calls += [(s, {"message": message, "data": {"type": "announce"}}) for s in targets]
        return await self._send_all(calls)

    async def async_quiet(self, *, task_id: str, message: str) -> int:
        """One quiet, passive notification (used while away)."""
        data = {
            "tag": tag_for(task_id),
            "group": GROUP,
            "actions": self._actions(task_id, False, False),
            "push": {"interruption-level": "passive"},
            **self._tap(),
        }
        return await self._send_all(
            [
                (s, {"title": NOTIFICATION_TITLE, "message": message, "data": data})
                for s in self.phone
            ]
        )

    async def async_summary(self, lines: list[str]) -> int:
        """One notification summarising what piled up during a silent period."""
        payload = {
            "title": NOTIFICATION_TITLE,
            "message": "\n".join(lines),
            "data": {"group": GROUP, "tag": f"{GROUP}_summary"},
        }
        return await self._send_all([(s, dict(payload)) for s in self.phone])

    async def async_clear(self, task_id: str) -> None:
        """Remove a task's notification from the phones."""
        await self.async_clear_tags([tag_for(task_id)])

    async def async_clear_tags(self, tags: list[str]) -> None:
        """Remove notifications by tag (a ringing task may have used several)."""
        calls = []
        for tag in tags:
            payload = {"message": "clear_notification", "data": {"tag": tag}}
            calls += [(s, dict(payload)) for s in [*self.phone, *self.extra]]
        await self._send_all(calls)
