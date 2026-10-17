"""One entry point for every external command (CLI, control socket, MCP/Hermes).

Results are plain JSON-safe dicts. When a scheduler is given (inside the running app),
long jobs run in the background; without it (standalone CLI) they run synchronously.
"""

import json
import urllib.request
from datetime import datetime, time

from app.constants import ActionType, ProfileStatus, TaskStatus

DEFAULT_AGENT_POLICY = {
    "allowed_visibility": ["public", "unlisted", "private"],
    "max_videos": 20,
}


class Controller:
    def __init__(self, profiles, process, tasks, scheduler=None, settings_path=None):
        self.profiles, self.process, self.tasks = profiles, process, tasks
        self.scheduler = scheduler
        self.settings_path = settings_path

    def handle(self, command: str, args: dict | None = None, agent: bool = False):
        method = getattr(self, f"cmd_{command.replace('-', '_')}", None)
        if not method:
            raise ValueError(f"Lệnh không hỗ trợ: {command}")
        return method(agent=agent, **(args or {}))

    # --- helpers -----------------------------------------------------------------------

    def agent_policy(self) -> dict:
        try:
            settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (AttributeError, OSError, ValueError):
            settings = {}
        return {**DEFAULT_AGENT_POLICY, **settings.get("agent", {})}

    def _pick(self, names=None, group=None, all=False):
        profiles = self.profiles.list()
        if all:
            chosen = profiles
        elif group:
            chosen = [p for p in profiles if p.group_name == group]
        else:
            wanted = set(names or [])
            chosen = [p for p in profiles if p.name in wanted or p.id in wanted]
            missing = wanted - {p.name for p in chosen} - {p.id for p in chosen}
            if missing:
                raise ValueError(f"Không tìm thấy profile: {', '.join(sorted(missing))}")
        if not chosen:
            raise ValueError("Không có profile nào khớp")
        return chosen

    def _task(self, task):
        match = [t for t in self.tasks.list() if task in {t.id, t.name}]
        if len(match) != 1:
            raise ValueError("Không tìm thấy tác vụ" if not match else "Tên bị trùng, dùng ID")
        return match[0]

    @staticmethod
    def _profile_dict(p):
        return {
            "id": p.id, "name": p.name, "group": p.group_name, "purpose": p.purpose,
            "tags": p.tags, "status": str(p.status), "imported": p.imported,
            "debug_port": p.debug_port, "channel_url": p.channel_url,
        }

    @staticmethod
    def _iso(value):
        return value.isoformat(timespec="seconds") if value else None

    def _bulk(self, action, profiles, workers):
        results = action([p.id for p in profiles], workers)
        names = {p.id: p.name for p in profiles}
        return {
            "ok": [names[pid] for pid, r in results.items() if not isinstance(r, Exception)],
            "errors": {
                names[pid]: str(r) for pid, r in results.items() if isinstance(r, Exception)
            },
        }

    # --- commands ----------------------------------------------------------------------

    def cmd_list_profiles(self, agent=False, group=None):
        self.process.discover()
        return [
            self._profile_dict(p) for p in self.profiles.list()
            if not group or p.group_name == group
        ]

    def cmd_open(self, agent=False, names=None, group=None, all=False, workers=2):
        return self._bulk(self.process.bulk_open, self._pick(names, group, all), workers)

    def cmd_close(self, agent=False, names=None, group=None, all=False, workers=2):
        return self._bulk(self.process.bulk_close, self._pick(names, group, all), workers)

    def cmd_cdp(self, agent=False, profile=None):
        self.process.discover()
        chosen = self._pick([profile])[0]
        if not chosen.debug_port or chosen.status != ProfileStatus.RUNNING:
            raise ValueError("Profile chưa mở hoặc chưa bật CDP")
        url = f"http://127.0.0.1:{chosen.debug_port}"
        with urllib.request.urlopen(f"{url}/json/version", timeout=3) as response:
            return {"http": url, **json.loads(response.read())}

    def cmd_check(self, agent=False, profile=None):
        return self.tasks.publisher.preview(self._pick([profile])[0].id)

    def cmd_list_tasks(self, agent=False):
        names = {p.id: p.name for p in self.profiles.list()}
        return [
            {
                "id": t.id, "name": t.name, "action": t.action_type,
                "target": f"group:{t.target_group}" if t.target_group
                else names.get(t.profile_id, t.profile_id),
                "schedule": t.schedule_type, "enabled": t.enabled, "status": t.status,
                "last_run_at": self._iso(t.last_run_at), "last_error": t.last_error,
                "next_run_at": self._iso(self.scheduler.next_run(t.id)) if self.scheduler
                else None,
            }
            for t in self.tasks.list()
        ]

    def cmd_publish(
        self, agent=False, profile=None, group=None, max_videos=None, visibility=None,
        wait=False,
    ):
        targets = self._pick([profile] if profile else None, group)
        payload = {}
        if agent:
            policy = self.agent_policy()
            limit = int(policy["max_videos"])
            max_videos = min(max_videos or limit, limit)
            for target in targets:
                effective = visibility or json.loads(target.automation_config or "{}").get(
                    "visibility", "public"
                )
                if effective not in policy["allowed_visibility"]:
                    raise PermissionError(
                        f"Agent không được public ở chế độ '{effective}' ({target.name}). "
                        f"Cho phép: {', '.join(policy['allowed_visibility'])}"
                    )
        if max_videos is not None:
            payload["maxVideos"] = int(max_videos)
        if visibility:
            payload["visibility"] = visibility
        label = f"nhóm {group}" if group else targets[0].name
        task = self.tasks.create(
            name=f"{'Hermes' if agent else 'CLI'}: Public {label} {datetime.now():%d/%m %H:%M}",
            profile_id=targets[0].id,
            target_group=group or "",
            action_type=ActionType.PUBLISH_YOUTUBE,
            payload=json.dumps(payload),
            schedule_type="immediate",
        )
        return self.cmd_run_task(task=task.id, wait=wait)

    def cmd_run_task(self, agent=False, task=None, wait=False):
        chosen = self._task(task)
        if self.scheduler and not wait:
            self.scheduler.run_now(chosen.id)
            return {"task_id": chosen.id, "name": chosen.name, "started": True,
                    "hint": "Dùng status để theo dõi tiến độ"}
        try:
            self.tasks.run(chosen.id)
        except Exception:
            pass  # Recorded in task status and history.
        return self.cmd_status(task=chosen.id)

    def cmd_status(self, agent=False, task=None):
        chosen = self._task(task)
        targets = self.tasks.targets(chosen)
        progress = {
            p.name: self.tasks.publisher.progress[p.id]
            for p in targets
            if p.id in self.tasks.publisher.progress
        }
        queued = bool(self.scheduler and self.scheduler.is_running_now(chosen.id))
        started = chosen.last_run_at or datetime.combine(chosen.created_at.date(), time.min)
        runs = [r for r in self.tasks.history(chosen.id, 100) if r.started_at >= started] or (
            self.tasks.history(chosen.id, len(targets) or 1)
        )
        return {
            "task_id": chosen.id,
            "name": chosen.name,
            "status": "QUEUED" if queued else chosen.status,
            "finished": not queued and chosen.status in {TaskStatus.SUCCESS, TaskStatus.FAILED},
            "last_error": chosen.last_error,
            "progress": progress,
            "runs": [self._run_dict(r) for r in runs],
        }

    def _run_dict(self, run):
        return {
            "profile": run.profile_name, "status": run.status, "attempts": run.attempts,
            "started_at": self._iso(run.started_at), "finished_at": self._iso(run.finished_at),
            "result": run.detail, "error": run.error,
        }

    def cmd_history(self, agent=False, task=None, limit=20):
        return [self._run_dict(r) for r in self.tasks.history(self._task(task).id, limit)]

    def cmd_stop(self, agent=False, task=None):
        chosen = self._task(task)
        if self.scheduler:
            self.scheduler.unschedule(f"now-{chosen.id}")  # Not started yet: just drop it.
        self.tasks.stop(chosen.id)
        return {"task_id": chosen.id, "stop_requested": True,
                "note": "Dừng sau khi xong video đang xử lý"}
