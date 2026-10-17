import json
from datetime import datetime
from urllib.parse import urlparse

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QSpinBox,
)

from app.constants import ActionType
from app.services.scheduler_service import SCHEDULE_LABELS

ACTION_LABELS = {
    ActionType.OPEN: "Mở profile",
    ActionType.CLOSE: "Đóng profile",
    ActionType.RESTART: "Khởi động lại",
    ActionType.OPEN_URL: "Mở URL",
    ActionType.STOP_AFTER: "Mở rồi tự đóng sau N phút",
    ActionType.PUBLISH_YOUTUBE: "Public YouTube",
}


class TaskDialog(QDialog):
    def __init__(self, profiles, groups, parent=None, task=None):
        super().__init__(parent)
        self.setWindowTitle("Tạo tác vụ" if task is None else "Sửa tác vụ")
        self.resize(520, 0)
        self.form = form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Để trống sẽ dùng tên hành động")
        self.single = QRadioButton("Một profile")
        self.group = QRadioButton("Cả nhóm (chạy lần lượt từng profile)")
        self.single.setChecked(True)
        self.group.setEnabled(bool(groups))
        self.profile = QComboBox()
        self.profile_ids = [p.id for p in profiles]
        self.profile.addItems([p.name for p in profiles])
        self.group_name = QComboBox()
        self.group_name.addItems(groups)
        self.action = QComboBox()
        for action, label in ACTION_LABELS.items():
            self.action.addItem(label, action)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://...")
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 1440)
        self.minutes.setValue(30)
        self.max_videos = QSpinBox()
        self.max_videos.setRange(-1, 10000)
        self.max_videos.setValue(-1)
        self.max_videos.setSpecialValueText("Theo profile")
        self.max_videos.setToolTip("0 = tất cả video")
        self.visibility = QComboBox()
        self.visibility.addItems(["Theo profile", "public", "unlisted", "private"])
        self.schedule = QComboBox()
        for key, label in SCHEDULE_LABELS.items():
            self.schedule.addItem(label, key)
        self.interval = QSpinBox()
        self.interval.setRange(1, 10080)
        self.interval.setValue(60)
        self.when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.when.setCalendarPopup(True)
        self.retries = QSpinBox()
        self.retries.setRange(0, 5)
        self.retries.setSuffix(" lần")
        self.delay = QSpinBox()
        self.delay.setRange(0, 3600)
        self.delay.setSuffix(" giây")
        self.enabled = QCheckBox("Bật lịch cho tác vụ này")
        self.enabled.setChecked(True)

        form.addRow("Tên", self.name)
        form.addRow("Chạy cho", self.single)
        form.addRow("", self.profile)
        form.addRow("", self.group)
        form.addRow("", self.group_name)
        form.addRow("Hành động", self.action)
        form.addRow("URL", self.url)
        form.addRow("Đóng sau", self.minutes)
        form.addRow("Số video", self.max_videos)
        form.addRow("Chế độ hiển thị", self.visibility)
        form.addRow("Lịch", self.schedule)
        form.addRow("Mỗi (phút)", self.interval)
        form.addRow("Thời điểm", self.when)
        form.addRow("Thử lại khi lỗi", self.retries)
        form.addRow("Nghỉ giữa các profile", self.delay)
        form.addRow("", self.enabled)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if task:
            self._load(task)
        for signal in (
            self.single.toggled,
            self.action.currentIndexChanged,
            self.schedule.currentIndexChanged,
        ):
            signal.connect(self._update_rows)
        self._update_rows()

    def _load(self, task):
        payload = json.loads(task.payload or "{}")
        self.name.setText(task.name)
        if task.target_group:
            self.group.setChecked(True)
            self.group_name.setCurrentText(task.target_group)
        elif task.profile_id in self.profile_ids:
            self.profile.setCurrentIndex(self.profile_ids.index(task.profile_id))
        self.action.setCurrentIndex(max(0, self.action.findData(task.action_type)))
        self.url.setText(payload.get("url", ""))
        self.minutes.setValue(int(payload.get("minutes", 30)))
        self.max_videos.setValue(int(payload.get("maxVideos", -1)))
        self.visibility.setCurrentText(payload.get("visibility", "Theo profile"))
        self.delay.setValue(int(payload.get("delaySeconds", 0)))
        self.schedule.setCurrentIndex(max(0, self.schedule.findData(task.schedule_type)))
        self.interval.setValue(task.interval_minutes or 60)
        if task.scheduled_at:
            self.when.setDateTime(QDateTime(task.scheduled_at))
        self.retries.setValue(task.max_retries or 0)
        self.enabled.setChecked(task.enabled)

    def _update_rows(self):
        action = self.action.currentData()
        schedule = self.schedule.currentData()
        youtube = action == ActionType.PUBLISH_YOUTUBE
        self.form.setRowVisible(self.profile, self.single.isChecked())
        self.form.setRowVisible(self.group_name, self.group.isChecked())
        self.form.setRowVisible(self.delay, self.group.isChecked())
        self.form.setRowVisible(self.url, action == ActionType.OPEN_URL)
        self.form.setRowVisible(self.minutes, action == ActionType.STOP_AFTER)
        for widget in (self.max_videos, self.visibility):
            self.form.setRowVisible(widget, youtube)
        self.form.setRowVisible(self.interval, schedule == "interval")
        self.form.setRowVisible(self.when, schedule in {"once", "daily"})
        self.form.setRowVisible(self.enabled, schedule != "immediate")
        self.when.setDisplayFormat("HH:mm" if schedule == "daily" else "dd/MM/yyyy HH:mm")

    def values(self):
        action = self.action.currentData()
        schedule = self.schedule.currentData()
        payload = {}
        if action == ActionType.OPEN_URL:
            payload["url"] = self.url.text().strip()
        elif action == ActionType.STOP_AFTER:
            payload["minutes"] = self.minutes.value()
        elif action == ActionType.PUBLISH_YOUTUBE:
            if self.max_videos.value() >= 0:
                payload["maxVideos"] = self.max_videos.value()
            if self.visibility.currentIndex() > 0:
                payload["visibility"] = self.visibility.currentText()
        if self.group.isChecked() and self.delay.value():
            payload["delaySeconds"] = self.delay.value()
        when = self.when.dateTime().toPython().replace(second=0, microsecond=0)
        return {
            "name": self.name.text().strip() or self.action.currentText(),
            "profile_id": self.profile_ids[self.profile.currentIndex()]
            if self.profile_ids
            else None,
            "target_group": self.group_name.currentText() if self.group.isChecked() else "",
            "action_type": action,
            "payload": json.dumps(payload, ensure_ascii=False),
            "schedule_type": schedule,
            "scheduled_at": when if schedule in {"once", "daily"} else None,
            "interval_minutes": self.interval.value() if schedule == "interval" else None,
            "max_retries": self.retries.value(),
            "enabled": self.enabled.isChecked() or schedule == "immediate",
        }

    def accept(self):
        values = self.values()
        url = json.loads(values["payload"]).get("url", "")
        if values["action_type"] == ActionType.OPEN_URL and urlparse(url).scheme not in {
            "http",
            "https",
        }:
            QMessageBox.warning(self, "Thiếu URL", "Hãy nhập URL bắt đầu bằng http(s)://")
            return
        if values["schedule_type"] == "once" and values["scheduled_at"] <= datetime.now():
            QMessageBox.warning(self, "Sai thời điểm", "Thời điểm chạy một lần phải ở tương lai.")
            return
        super().accept()
