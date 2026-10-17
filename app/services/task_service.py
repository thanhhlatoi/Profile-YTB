from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from threading import RLock

from app.constants import ActionType, TaskStatus
from app.models.database import Profile, Task, TaskRun
from app.services.studio_publisher import StudioPublisher


class TaskService:
    def __init__(self, session_factory, process_service, publisher=None, retry_delay=30):
        self.session_factory, self.process_service = session_factory, process_service
        self.publisher = publisher or StudioPublisher(process_service)
        self.retry_delay = retry_delay
        self._profile_locks: dict[str, RLock] = {}
        self._locks_guard = threading.Lock()

    def create(self, **kwargs) -> Task:
        with self.session_factory() as session:
            kwargs["profile_id"] = self._anchor_profile(session, kwargs)
            task = Task(**kwargs)
            session.add(task)
            session.commit()
            return task

    def update(self, task_id: str, **kwargs) -> Task:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError("Không tìm thấy tác vụ")
            kwargs["profile_id"] = self._anchor_profile(session, kwargs)
            for key, value in kwargs.items():
                setattr(task, key, value)
            if task.enabled and task.status == TaskStatus.DISABLED:
                task.status = TaskStatus.PENDING
            session.commit()
            return task

    @staticmethod
    def _anchor_profile(session, kwargs) -> str:
        group = kwargs.get("target_group") or ""
        if group:
            first = (
                session.query(Profile)
                .filter_by(group_name=group, deleted=False)
                .order_by(Profile.name)
                .first()
            )
            if not first:
                raise ValueError(f"Nhóm '{group}' chưa có profile nào")
            return first.id
        profile = session.get(Profile, kwargs.get("profile_id"))
        if not profile or profile.deleted:
            raise ValueError("Không tìm thấy profile")
        return profile.id

    def list(self) -> list[Task]:
        with self.session_factory() as session:
            return session.query(Task).order_by(Task.created_at.desc()).all()

    def get(self, task_id: str) -> Task:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError("Không tìm thấy tác vụ")
            return task

    def history(self, task_id: str, limit: int = 50) -> list[TaskRun]:
        with self.session_factory() as session:
            return (
                session.query(TaskRun)
                .filter_by(task_id=task_id)
                .order_by(TaskRun.id.desc())
                .limit(limit)
                .all()
            )

    def delete(self, task_id: str) -> None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError("Không tìm thấy tác vụ")
            session.query(TaskRun).filter_by(task_id=task_id).delete()
            session.delete(task)
            session.commit()

    def set_enabled(self, task_id: str, enabled: bool) -> None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError("Không tìm thấy tác vụ")
            task.enabled = enabled
            task.status = TaskStatus.PENDING if enabled else TaskStatus.DISABLED
            session.commit()

    def targets(self, task: Task) -> list[Profile]:
        with self.session_factory() as session:
            if task.target_group:
                return (
                    session.query(Profile)
                    .filter_by(group_name=task.target_group, deleted=False)
                    .order_by(Profile.name)
                    .all()
                )
            profile = session.get(Profile, task.profile_id)
            return [profile] if profile and not profile.deleted else []

    def stop(self, task_id: str) -> None:
        """Ask running YouTube publishes of this task to stop after the current video."""
        for profile in self.targets(self.get(task_id)):
            self.publisher.request_stop(profile.id)

    def run(self, task_id: str) -> None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError("Không tìm thấy tác vụ")
            task.status, task.last_error = TaskStatus.RUNNING, ""
            session.commit()
        payload = json.loads(task.payload or "{}")
        delay = max(0, int(payload.get("delaySeconds", 0)))
        errors = []
        try:
            profiles = self.targets(task)
            if not profiles:
                raise ValueError("Tác vụ không có profile nào để chạy")
            for index, profile in enumerate(profiles):
                if index and delay:
                    time.sleep(delay)
                error = self._run_for_profile(task, profile, payload)
                if error:
                    errors.append(f"{profile.name}: {error}")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            with self.session_factory() as session:
                current = session.get(Task, task_id)
                if current:
                    current.status = TaskStatus.FAILED if errors else TaskStatus.SUCCESS
                    current.last_run_at = datetime.now()
                    current.last_error = "\n".join(errors)[:2000]
                    session.commit()
        if errors:
            raise RuntimeError("\n".join(errors))

    def _run_for_profile(self, task: Task, profile: Profile, payload: dict) -> str:
        """Run one profile with retries, record it in history, return the error ('' if ok)."""
        with self.session_factory() as session:
            run = TaskRun(task_id=task.id, profile_id=profile.id, profile_name=profile.name)
            session.add(run)
            session.commit()
            run_id = run.id
        with self._locks_guard:
            lock = self._profile_locks.setdefault(profile.id, RLock())
        error, detail, attempts = "", "", 0
        if not lock.acquire(blocking=False):
            error = "Profile đang được sử dụng bởi tác vụ khác"
        else:
            try:
                for attempts in range(1, max(0, task.max_retries) + 2):
                    try:
                        detail = self._execute(task.action_type, profile.id, payload) or ""
                        error = ""
                        break
                    except Exception as exc:
                        error = str(exc)[:500]
                        if attempts <= task.max_retries:
                            time.sleep(self.retry_delay)
            finally:
                lock.release()
        with self.session_factory() as session:
            run = session.get(TaskRun, run_id)
            run.finished_at = datetime.now()
            run.status = TaskStatus.FAILED if error else TaskStatus.SUCCESS
            run.attempts, run.error, run.detail = max(1, attempts), error, detail
            session.commit()
        return error

    def _execute(self, action_type: str, profile_id: str, payload: dict) -> str | None:
        process = self.process_service
        if action_type == ActionType.OPEN:
            process.open(profile_id)
        elif action_type == ActionType.CLOSE:
            process.close(profile_id)
        elif action_type == ActionType.RESTART:
            process.restart(profile_id)
        elif action_type == ActionType.OPEN_URL:
            process.open_url(profile_id, payload["url"])
        elif action_type == ActionType.OPEN_URLS:
            process.open(profile_id, payload["urls"])
        elif action_type == ActionType.STOP_AFTER:
            process.open(profile_id)
            threading.Timer(
                float(payload["minutes"]) * 60, process.close, args=[profile_id]
            ).start()
        elif action_type == ActionType.PUBLISH_YOUTUBE:
            config = {k: v for k, v in payload.items() if k != "delaySeconds"}
            return self.publisher.publish(profile_id, config)
        else:
            raise ValueError("Loại tác vụ không được hỗ trợ")
