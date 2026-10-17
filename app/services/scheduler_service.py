import logging
from datetime import datetime

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

SCHEDULE_LABELS = {
    "immediate": "Chạy thủ công",
    "interval": "Lặp mỗi N phút",
    "daily": "Hằng ngày lúc",
    "once": "Một lần lúc",
}


class SchedulerService:
    def __init__(self, task_service):
        self.task_service = task_service
        # Grace time: a job missed while the machine was busy/asleep still runs once.
        self.scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "misfire_grace_time": 600, "max_instances": 1}
        )

    def start(self) -> None:
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule(self, task) -> None:
        self.unschedule(task.id)
        if not task.enabled or task.schedule_type == "immediate":
            return
        if task.schedule_type == "once" and task.scheduled_at:
            if task.scheduled_at < datetime.now():
                return
            trigger = DateTrigger(run_date=task.scheduled_at)
        elif task.schedule_type == "interval" and task.interval_minutes:
            trigger = IntervalTrigger(minutes=task.interval_minutes)
        elif task.schedule_type == "daily" and task.scheduled_at:
            trigger = CronTrigger(hour=task.scheduled_at.hour, minute=task.scheduled_at.minute)
        else:
            raise ValueError("Lịch tác vụ không hợp lệ")
        self.scheduler.add_job(
            self._run, trigger=trigger, args=[task.id], id=task.id, replace_existing=True
        )

    def unschedule(self, task_id: str) -> None:
        try:
            self.scheduler.remove_job(task_id)
        except JobLookupError:
            pass

    def run_now(self, task_id: str) -> None:
        """Run in the scheduler's thread pool so the UI never blocks."""
        self.scheduler.add_job(self._run, args=[task_id], id=f"now-{task_id}")

    def is_running_now(self, task_id: str) -> bool:
        return self.scheduler.get_job(f"now-{task_id}") is not None

    def next_run(self, task_id: str) -> datetime | None:
        job = self.scheduler.get_job(task_id)
        return job.next_run_time if job else None

    def _run(self, task_id: str) -> None:
        try:
            self.task_service.run(task_id)
        except Exception:
            logger.exception("Tác vụ %s thất bại", task_id)

    def restore(self) -> None:
        for task in self.task_service.list():
            try:
                self.schedule(task)
            except ValueError:
                logger.warning("Bỏ qua tác vụ %s: lịch không hợp lệ", task.name)
