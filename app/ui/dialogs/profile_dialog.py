import json
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.browser_detection import detect_browsers
from app.utils.validation import ProfileInput


class ProfileDialog(QDialog):
    def __init__(self, parent=None, profile=None, groups=()):
        super().__init__(parent)
        self.setWindowTitle("Thêm profile" if profile is None else "Sửa profile")
        self.color = profile.color if profile else "#4285F4"
        self.name_edit, self.binary_edit = QLineEdit(), QLineEdit()
        self.directory_edit = QLineEdit()
        self.notes_edit, self.tags_edit, self.urls_edit, self.args_edit = (
            QTextEdit(),
            QLineEdit(),
            QTextEdit(),
            QLineEdit(),
        )
        self.purpose_edit = QLineEdit()
        # Editable list of existing groups: a typo would silently split a group task.
        self.group_edit = QComboBox()
        self.group_edit.setEditable(True)
        self.group_edit.addItems(["", *groups])
        self.remote_debugging = QCheckBox("Bật cổng điều khiển CDP (Playwright/Selenium)")
        self.channel_url = QLineEdit()
        self.channel_url.setPlaceholderText("https://studio.youtube.com/channel/UC.../videos")
        self.thumbnail_folder = QLineEdit()
        self.thumbnail_folder.setPlaceholderText("~/Videos/KenhA/thumbs  (12_ten.jpg = nháp 12)")
        self.automation_config = QTextEdit()
        self.automation_config.setPlaceholderText(
            '{"visibility": "public", "maxVideos": 5, "delayMin": 3, "delayMax": 8}'
        )
        self.automation_config.setMaximumHeight(90)
        self.pinned = QCheckBox("Ghim profile lên đầu danh sách")
        self.proxy = QCheckBox("Bật proxy")
        self.proxy_host, self.proxy_port = QLineEdit(), QSpinBox()
        self.proxy_port.setRange(1, 65535)
        self.proxy_scheme = QComboBox()
        self.proxy_scheme.addItems(["http", "https", "socks4", "socks5"])
        if profile is None:
            browsers = detect_browsers()
            self.binary_edit.setText(browsers[0]["path"] if browsers else "")
            self.directory_edit.setText("Default")
        self.directory_edit.setReadOnly(True)
        self.name_edit.setPlaceholderText("Ví dụ: Kênh YouTube A")
        self.tags_edit.setPlaceholderText("youtube, kênh-a (phân cách bằng dấu phẩy)")
        self.urls_edit.setPlaceholderText("Mỗi dòng một URL https://...")
        self.urls_edit.setMaximumHeight(80)
        self.notes_edit.setMaximumHeight(80)
        if profile:
            self.name_edit.setText(profile.name)
            self.binary_edit.setText(profile.browser_binary)
            self.directory_edit.setText(profile.profile_directory)
            self.notes_edit.setPlainText(profile.notes)
            self.tags_edit.setText(profile.tags)
            self.purpose_edit.setText(profile.purpose)
            self.group_edit.setCurrentText(profile.group_name)
            self.remote_debugging.setChecked(profile.remote_debugging)
            self.channel_url.setText(profile.channel_url)
            try:
                extra = json.loads(profile.automation_config or "{}")
            except ValueError:
                extra = {}
            self.thumbnail_folder.setText(extra.pop("thumbnailFolder", ""))
            self.automation_config.setPlainText(
                json.dumps(extra, ensure_ascii=False, indent=2) if extra else ""
            )
            self.pinned.setChecked(profile.pinned)
            self.urls_edit.setPlainText(profile.startup_urls)
            self.args_edit.setText(profile.extra_arguments)
            self.proxy.setChecked(profile.proxy_enabled)
            self.proxy_host.setText(profile.proxy_host)
            self.proxy_scheme.setCurrentText(profile.proxy_scheme)
            if profile.proxy_port:
                self.proxy_port.setValue(profile.proxy_port)
        browse = QPushButton("Chọn file")
        browse.clicked.connect(self.browse_binary)
        self.color_button = color = QPushButton("Chọn màu")
        color.clicked.connect(self.pick_color)
        self._show_color()
        tabs = QTabWidget()
        basic, automation, advanced = QFormLayout(), QFormLayout(), QFormLayout()
        for title, form in (("Cơ bản", basic), ("Tự động hóa", automation), ("Nâng cao", advanced)):
            page = QWidget()
            page.setLayout(form)
            tabs.addTab(page, title)
        basic.addRow("Tên profile *", self.name_edit)
        basic.addRow("Nhóm", self.group_edit)
        basic.addRow("Mục đích", self.purpose_edit)
        basic.addRow("Tags", self.tags_edit)
        basic.addRow("Màu", color)
        basic.addRow("Hiển thị", self.pinned)
        basic.addRow("Ghi chú", self.notes_edit)

        automation.addRow("Link Studio của kênh", self.channel_url)
        folder_browse = QPushButton("Chọn thư mục")
        folder_browse.clicked.connect(self.browse_thumbnail_folder)
        folder_row = QVBoxLayout()
        folder_row.addWidget(self.thumbnail_folder)
        folder_row.addWidget(folder_browse)
        automation.addRow("Thư mục thumbnail", folder_row)
        automation.addRow("Cấu hình khác (JSON)", self.automation_config)
        automation.addRow("Điều khiển từ script", self.remote_debugging)
        hint = QLabel(
            "Link Studio: tác vụ Public YouTube mở đúng kênh này.\n"
            "Thumbnail: tên file bắt đầu bằng số thứ tự của nháp (12_ten.jpg, 12 ten.png).\n"
            "JSON: visibility, maxVideos, delayMin, delayMax (ms), monetizationChannel,\n"
            "skipMissing, scheduleMode... Thiết lập trong tác vụ sẽ ghi đè.\n"
            "Public YouTube tự bật CDP. Chỉ dùng được với Profile riêng."
        )
        hint.setObjectName("muted")
        automation.addRow(hint)

        binary_row = QVBoxLayout()
        binary_row.addWidget(self.binary_edit)
        binary_row.addWidget(browse)
        advanced.addRow("Browser binary *", binary_row)
        advanced.addRow("Profile directory", self.directory_edit)
        advanced.addRow("Startup URLs", self.urls_edit)
        advanced.addRow("Tham số thêm", self.args_edit)
        advanced.addRow("Proxy", self.proxy)
        advanced.addRow("Proxy scheme", self.proxy_scheme)
        advanced.addRow("Proxy host", self.proxy_host)
        advanced.addRow("Proxy port", self.proxy_port)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.resize(560, 480)
        layout.addWidget(buttons)

    def browse_binary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn trình duyệt", "/usr/bin")
        if path:
            self.binary_edit.setText(path)

    def browse_thumbnail_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục thumbnail")
        if folder:
            self.thumbnail_folder.setText(folder)

    def _automation_json(self) -> str:
        text = self.automation_config.toPlainText().strip()
        folder = self.thumbnail_folder.text().strip()
        if not folder:
            return text
        data = json.loads(text) if text else {}
        if not isinstance(data, dict):
            raise ValueError("Cấu hình khác phải là JSON object")
        return json.dumps({**data, "thumbnailFolder": folder}, ensure_ascii=False)

    def pick_color(self):
        color = QColorDialog.getColor(QColor(self.color), self)
        if color.isValid():
            self.color = color.name()
            self._show_color()

    def _show_color(self):
        self.color_button.setText(self.color)
        self.color_button.setStyleSheet(f"background: {self.color}; color: white;")

    def values(self) -> ProfileInput:
        return ProfileInput(
            name=self.name_edit.text(),
            browser_binary=str(Path(self.binary_edit.text())),
            color=self.color,
            notes=self.notes_edit.toPlainText(),
            tags=self.tags_edit.text(),
            purpose=self.purpose_edit.text(),
            group_name=self.group_edit.currentText().strip(),
            pinned=self.pinned.isChecked(),
            proxy_enabled=self.proxy.isChecked(),
            proxy_scheme=self.proxy_scheme.currentText(),
            proxy_host=self.proxy_host.text().strip(),
            proxy_port=self.proxy_port.value() if self.proxy.isChecked() else None,
            startup_urls=self.urls_edit.toPlainText().splitlines(),
            extra_arguments=self.args_edit.text(),
            remote_debugging=self.remote_debugging.isChecked(),
            channel_url=self.channel_url.text(),
            automation_config=self._automation_json(),
        )

    def accept(self):
        try:
            self.values()
        except Exception as exc:
            QMessageBox.warning(self, "Dữ liệu không hợp lệ", str(exc))
            return
        super().accept()
