import json
import re
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import ProfileStatus, TaskStatus
from app.services.scheduler_service import SCHEDULE_LABELS
from app.ui.dialogs.profile_dialog import ProfileDialog
from app.ui.dialogs.task_dialog import ACTION_LABELS, TaskDialog


class AIAgentDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cấu hình AI Agent")
        self.resize(680, 560)
        form = QFormLayout(self)

        self.provider = QComboBox()
        self.provider.addItems(["openai", "gemini", "anthropic", "ollama"])
        self.provider.setCurrentText(settings.get("provider", "openai"))
        self.text_model = QLineEdit(settings.get("text_model", "gpt-4.1"))
        self.transcription_model = QLineEdit(settings.get("transcription_model", "whisper-1"))
        self.image_model = QLineEdit(settings.get("image_model", "gpt-image-1"))
        self.api_key_env = QLineEdit(settings.get("api_key_env", "OPENAI_API_KEY"))
        self.api_key_env.setPlaceholderText("Ví dụ: OPENAI_API_KEY")
        self.transcript_folder = QLineEdit(settings.get("transcript_folder", ""))
        self.thumbnail_folder = QLineEdit(settings.get("thumbnail_folder", ""))
        self.channel_context = QTextEdit(settings.get("channel_context", ""))
        self.channel_context.setPlaceholderText(
            "Chủ đề, đối tượng, giọng văn và quy tắc của kênh..."
        )
        self.channel_context.setMaximumHeight(90)
        self.require_approval = QCheckBox("Bắt buộc duyệt trước khi áp dụng/public")
        self.require_approval.setChecked(settings.get("require_approval", True))
        self.generate_title = QCheckBox("AI tạo/cải thiện title")
        self.generate_title.setChecked(settings.get("generate_title", True))
        self.generate_description = QCheckBox("AI tạo description")
        self.generate_description.setChecked(settings.get("generate_description", True))
        self.generate_thumbnail = QCheckBox("AI tạo/chỉnh thumbnail")
        self.generate_thumbnail.setChecked(settings.get("generate_thumbnail", False))

        form.addRow("AI provider", self.provider)
        form.addRow("Text model", self.text_model)
        form.addRow("Transcription model", self.transcription_model)
        form.addRow("Image model", self.image_model)
        form.addRow("Tên biến API key", self.api_key_env)
        form.addRow("Thư mục transcript", self._path_row(self.transcript_folder))
        form.addRow("Thư mục thumbnail AI", self._path_row(self.thumbnail_folder))
        form.addRow("Bối cảnh kênh", self.channel_context)
        form.addRow("Tính năng", self._options_widget())
        form.addRow("An toàn", self.require_approval)

        note = QLabel(
            "API key chỉ được đọc từ biến môi trường, không lưu vào SQLite/settings.json."
        )
        note.setObjectName("muted")
        form.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _path_row(self, field):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field)
        button = QPushButton("Chọn")
        button.clicked.connect(lambda: self._choose_folder(field))
        layout.addWidget(button)
        return row

    def _choose_folder(self, field):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if folder:
            field.setText(folder)

    def _options_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        for checkbox in (self.generate_title, self.generate_description, self.generate_thumbnail):
            layout.addWidget(checkbox)
        return widget

    def values(self):
        return {
            "provider": self.provider.currentText(),
            "text_model": self.text_model.text().strip(),
            "transcription_model": self.transcription_model.text().strip(),
            "image_model": self.image_model.text().strip(),
            "api_key_env": self.api_key_env.text().strip(),
            "transcript_folder": self.transcript_folder.text().strip(),
            "thumbnail_folder": self.thumbnail_folder.text().strip(),
            "channel_context": self.channel_context.toPlainText().strip(),
            "require_approval": self.require_approval.isChecked(),
            "generate_title": self.generate_title.isChecked(),
            "generate_description": self.generate_description.isChecked(),
            "generate_thumbnail": self.generate_thumbnail.isChecked(),
        }


class MainWindow(QMainWindow):
    PROFILE_COLUMNS = ("", "Tên profile", "Trạng thái", "Nhóm", "Mục đích", "Tags", "Nguồn",
                       "Thư mục", "CDP")
    TASK_COLUMNS = ("Tên tác vụ", "Chạy cho", "Hành động", "Lịch", "Lần chạy kế", "Lần chạy cuối",
                    "Trạng thái")
    STATUS_COLORS = {
        ProfileStatus.RUNNING: "#16a34a",
        ProfileStatus.STARTING: "#d97706",
        ProfileStatus.STOPPING: "#d97706",
        ProfileStatus.ERROR: "#dc2626",
    }

    def __init__(self, paths, profile_service, process_service, task_service, scheduler_service):
        super().__init__()
        self.paths = paths
        self.profile_service = profile_service
        self.process_service = process_service
        self.task_service = task_service
        self.scheduler_service = scheduler_service
        self.bulk_workers = 2
        self.setWindowTitle("Chrome Profile Manager")
        self.resize(1180, 760)
        self.stack = QStackedWidget()
        self.profile_list = QTableWidget(0, len(self.PROFILE_COLUMNS))
        self.profile_list.setHorizontalHeaderLabels(self.PROFILE_COLUMNS)
        self.profile_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.profile_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.profile_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.profile_list.setShowGrid(False)
        self.profile_list.setWordWrap(False)
        self.profile_list.setAlternatingRowColors(True)
        self.profile_list.verticalHeader().setVisible(False)
        self.profile_list.verticalHeader().setDefaultSectionSize(40)
        header = self.profile_list.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(len(self.PROFILE_COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.profile_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.profile_list.customContextMenuRequested.connect(self.show_profile_context_menu)
        self.profile_list.cellDoubleClicked.connect(lambda _row, _col: self.open_selected())
        self.profile_list.itemSelectionChanged.connect(self.update_profile_actions)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍  Tìm tên, nhóm, mục đích, tag, ghi chú...  (Ctrl+F)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_profiles)
        self.status_filter = QComboBox()
        self.status_filter.addItems(
            [
                "Tất cả", "Đã ghim", "Quan trọng", "Đang chạy", "Đã dừng",
                "Chrome gốc", "Profile riêng",
            ]
        )
        self.status_filter.currentTextChanged.connect(self.refresh_profiles)
        self.group_filter = QComboBox()
        self.group_filter.addItem("Tất cả nhóm")
        self.group_filter.currentTextChanged.connect(self.refresh_profiles)
        self.profile_label = QLabel()
        self.dashboard_label = QLabel()
        self.task_label = QLabel()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.settings_view = QTextEdit()
        self.settings_view.setReadOnly(True)
        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self.ai_prompt.setPlainText(self._read_settings().get("ai", {}).get("prompt", ""))
        self.timer = QTimer(self)
        # Poll only process status; full refresh would reset selections and text being edited.
        self.timer.timeout.connect(self.refresh_profiles)
        self.timer.start(3000)
        self.refresh()

    def _build_ui(self):
        nav = QListWidget()
        nav.addItems(
            [
                "Tổng quan", "Chrome Profiles", "Tác vụ", "AI Agent", "Nhật ký", "Cài đặt",
            ]
        )
        nav.setObjectName("sidebar")
        nav.setFixedWidth(210)
        nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        nav.currentRowChanged.connect(lambda _row: self.refresh())
        self.dashboard, self.profile_page, self.task_page, self.ai_page = (
            QWidget() for _ in range(4)
        )
        pages = (self.dashboard, self.profile_page, self.task_page, self.ai_page)
        for page in pages:
            self.stack.addWidget(page)
        self.stack.addWidget(self.log_view)
        self.stack.addWidget(self.settings_view)
        self._build_dashboard()
        self._build_profiles()
        self._build_tasks()
        self._build_ai_agent()
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        nav.setCurrentRow(1)
        self.setStyleSheet(
            """
            * { font-family: 'Noto Sans', 'Segoe UI', sans-serif; }
            QMainWindow, QWidget { background: #f5f7fb; color: #172033; }
            #sidebar { background: #111827; color: #cbd5e1; border: 0; padding: 14px 8px; }
            #sidebar::item { padding: 13px 14px; margin: 3px 0; border-radius: 8px; }
            #sidebar::item:selected { background: #2563eb; color: white; }
            #sidebar::item:hover:!selected { background: #1f2937; }
            QLineEdit, QComboBox, QSpinBox, QTextEdit, QListWidget {
                background: white; border: 1px solid #d7deea; border-radius: 8px;
                padding: 8px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus, QListWidget:focus {
                border: 1px solid #2563eb;
            }
            QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 8px;
                padding: 9px 14px; min-height: 18px; }
            QPushButton:hover { background: #eff6ff; border-color: #93c5fd; }
            QPushButton:pressed { background: #dbeafe; }
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; }
            QPushButton#primaryButton:hover { background: #1d4ed8; }
            QPushButton#dangerButton { color: #b91c1c; }
            QListWidget#profileList, QListWidget#taskList, QListWidget#trashList {
                padding: 6px; outline: 0;
            }
            QListWidget#profileList::item, QListWidget#taskList::item, QListWidget#trashList::item {
                padding: 12px; margin: 3px 0; border-radius: 8px;
            }
            QListWidget#profileList::item:selected, QListWidget#taskList::item:selected,
            QListWidget#trashList::item:selected { background: #dbeafe; color: #172033; }
            QTableWidget {
                background: white; alternate-background-color: #f8fafc;
                border: 1px solid #d7deea; border-radius: 8px; outline: 0;
                selection-background-color: #dbeafe; selection-color: #172033;
            }
            QTableWidget::item { padding: 0 8px; border: 0; }
            QHeaderView::section {
                background: #f1f5f9; color: #475569; border: 0;
                border-bottom: 1px solid #e2e8f0; padding: 8px; font-weight: 600;
            }
            QComboBox::drop-down { border: 0; width: 24px; }
            QPushButton:disabled { color: #94a3b8; background: #f1f5f9; border-color: #e2e8f0; }
            QPushButton#primaryButton:disabled { background: #93c5fd; color: white; }
            QPushButton::menu-indicator { subcontrol-position: right center; right: 8px; }
            QStatusBar { background: white; color: #475569; border-top: 1px solid #e2e8f0; }
            QLabel#emptyState { color: #64748b; font-size: 15px; padding: 40px; }
            QLabel#muted { color: #64748b; }
            QLabel#pageTitle { color: #0f172a; font-size: 22px; font-weight: 700; }
             QLabel#statCard { background: white; border: 1px solid #e2e8f0; border-radius: 10px;
                 padding: 16px; font-size: 15px; }
             QWidget#totpCard { background: white; border: 1px solid #e2e8f0; border-radius: 10px; }
             QLabel#totpCode { color: #2563eb; font-size: 38px; font-weight: 700; padding: 18px; }
             """
        )

    def _page_title(self, text):
        label = QLabel(text)
        label.setObjectName("pageTitle")
        return label

    def _muted(self, text):
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    def _button(self, text, callback, object_name=None):
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        button.clicked.connect(callback)
        return button

    def _stat_card(self):
        card = QLabel()
        card.setObjectName("statCard")
        card.setMinimumHeight(70)
        return card

    def _build_dashboard(self):
        layout = QVBoxLayout(self.dashboard)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(self._page_title("Tổng quan"))
        layout.addWidget(self._muted("Quản lý nhanh các Chrome profile và tác vụ đang chạy."))
        self.dashboard_stats = QGridLayout()
        self.dashboard_stats.setSpacing(12)
        self.stat_cards = [self._stat_card() for _ in range(4)]
        for index, card in enumerate(self.stat_cards):
            self.dashboard_stats.addWidget(card, 0, index)
        layout.addLayout(self.dashboard_stats)
        quick = QWidget()
        quick_layout = QHBoxLayout(quick)
        quick_layout.setContentsMargins(0, 8, 0, 0)
        quick_layout.addWidget(self._button("Mở tất cả profile", self.open_all, "primaryButton"))
        quick_layout.addWidget(self._button("Đóng tất cả profile", self.stop_all))
        quick_layout.addWidget(self._button("+ Thêm profile", self.add_profile))
        quick_layout.addWidget(self._button("Quét Chrome", self.import_chrome_profiles))
        quick_layout.addStretch()
        layout.addWidget(quick)
        layout.addWidget(self._muted("Tóm tắt hệ thống"))
        layout.addWidget(self.dashboard_label)
        layout.addStretch()

    def _build_profiles(self):
        layout = QVBoxLayout(self.profile_page)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(self._page_title("Chrome Profiles"))
        header.addStretch()
        header.addWidget(self._button("+ Thêm profile", self.add_profile, "primaryButton"))
        tools = QPushButton("Công cụ")
        tools_menu = QMenu(tools)
        tools_menu.addAction("Quét profile Chrome trên máy", self.import_chrome_profiles)
        tools_menu.addAction("Nhập cấu hình từ JSON...", self.import_profiles)
        tools_menu.addAction("Xuất cấu hình ra JSON...", self.export_profiles)
        tools_menu.addSeparator()
        tools_menu.addAction("Đóng tất cả profile", self.stop_all)
        tools.setMenu(tools_menu)
        header.addWidget(tools)
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.group_filter)
        layout.addLayout(filters)

        actions = QHBoxLayout()
        self.selection_buttons = [
            self._button("▶  Mở", self.open_selected, "primaryButton"),
            self._button("■  Đóng", self.close_selected),
            self._button("★  Quan trọng", self.toggle_selected_important),
            self._button("🗑  Xóa", self.delete_selected, "dangerButton"),
        ]
        self.edit_button = self._button("✎  Sửa", lambda: self.edit_profile(self.selected_id()))
        self.selection_buttons.insert(2, self.edit_button)
        for button in self.selection_buttons:
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.profile_label)
        self.profile_label.setObjectName("muted")
        layout.addLayout(actions)

        self.empty_label = QLabel(
            "Chưa có profile nào.\nBấm “+ Thêm profile” hoặc Công cụ › Quét profile Chrome."
        )
        self.empty_label.setObjectName("emptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.profile_list, 1)
        layout.addWidget(
            self._muted(
                "Nhấp đúp hoặc Enter: mở  •  F2: sửa  •  Delete: xóa  •  "
                "Ctrl+N: thêm  •  F5: làm mới  •  Chuột phải: thêm thao tác"
            )
        )
        self.update_profile_actions()

    def _build_shortcuts(self):
        for keys, callback in (
            ("Ctrl+N", self.add_profile),
            ("Ctrl+F", lambda: (self.search.setFocus(), self.search.selectAll())),
            ("F5", self.refresh),
        ):
            QShortcut(QKeySequence(keys), self, callback)
        # Row actions only fire while the table has focus, so typing in search is unaffected.
        for keys, callback in (
            ("Return", self.open_selected),
            ("Enter", self.open_selected),
            ("F2", lambda: self.edit_profile(self.selected_id())),
            ("Delete", self.delete_selected),
        ):
            shortcut = QShortcut(QKeySequence(keys), self.profile_list, callback)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

    def update_profile_actions(self):
        count = len(self.selected_ids())
        for button in self.selection_buttons:
            button.setEnabled(count > 0)
        self.edit_button.setEnabled(count == 1)
        self._update_profile_label()

    def _update_profile_label(self):
        visible, total, running = getattr(self, "_profile_counts", (0, 0, 0))
        selected = len(self.selected_ids())
        self.profile_label.setText(
            f"{visible}/{total} hiển thị  •  {running} đang chạy"
            + (f"  •  {selected} đã chọn" if selected else "")
        )

    def _build_tasks(self):
        layout = QVBoxLayout(self.task_page)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(self._page_title("Tác vụ"))
        header.addStretch()
        header.addWidget(self._button("+ Tạo tác vụ", self.create_task, "primaryButton"))
        layout.addLayout(header)
        actions = QHBoxLayout()
        self.task_buttons = [
            self._button("▶  Chạy ngay", self.run_selected_task, "primaryButton"),
            self._button("✎  Sửa", self.edit_selected_task),
            self._button("⏯  Bật / Tắt lịch", self.toggle_selected_task),
            self._button("■  Dừng", self.stop_selected_task),
            self._button("🗑  Xóa", self.delete_selected_task, "dangerButton"),
        ]
        for button in self.task_buttons:
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self.task_list = QTableWidget(0, len(self.TASK_COLUMNS))
        self.task_list.setHorizontalHeaderLabels(self.TASK_COLUMNS)
        self.task_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.task_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.task_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.task_list.setShowGrid(False)
        self.task_list.setAlternatingRowColors(True)
        self.task_list.verticalHeader().setVisible(False)
        self.task_list.verticalHeader().setDefaultSectionSize(38)
        task_header = self.task_list.horizontalHeader()
        task_header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for column in range(len(self.TASK_COLUMNS)):
            task_header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        task_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.task_list.itemSelectionChanged.connect(self.render_task_history)
        self.task_list.cellDoubleClicked.connect(lambda _r, _c: self.edit_selected_task())
        layout.addWidget(self.task_list, 3)
        layout.addWidget(self._muted("Lịch sử chạy của tác vụ đang chọn"))
        self.task_history = QTextEdit()
        self.task_history.setReadOnly(True)
        layout.addWidget(self.task_history, 2)
        layout.addWidget(self.task_label)
        self.task_label.setObjectName("muted")

    def _build_ai_agent(self):
        layout = QVBoxLayout(self.ai_page)
        layout.setContentsMargins(28, 24, 28, 24)
        header = QHBoxLayout()
        header.addWidget(self._page_title("AI Agent"))
        header.addStretch()
        header.addWidget(self._button("Cấu hình AI", self.configure_ai, "primaryButton"))
        layout.addLayout(header)
        layout.addWidget(
            self._muted(
                "Tạo title, description và thumbnail theo từng kênh. "
                "Kết quả được duyệt trước khi áp dụng vào YouTube."
            )
        )
        self.ai_summary = QLabel()
        self.ai_summary.setWordWrap(True)
        self.ai_summary.setObjectName("statCard")
        layout.addWidget(self.ai_summary)
        self.ai_prompt = QTextEdit()
        self.ai_prompt.setPlaceholderText(
            "Prompt bổ sung cho kênh, ví dụ: viết tiếng Việt, ngắn gọn, không giật tít..."
        )
        self.ai_prompt.setMaximumHeight(130)
        layout.addWidget(QLabel("Prompt bổ sung"))
        layout.addWidget(self.ai_prompt)
        actions = QHBoxLayout()
        actions.addWidget(self._button("Lưu prompt", self.save_ai_prompt, "primaryButton"))
        actions.addWidget(self._button("Kiểm tra API key", self.check_ai_key))
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(
            self._muted(
                "API key được đọc từ biến môi trường. Ví dụ: export OPENAI_API_KEY='...'."
            )
        )
        layout.addStretch()

    def refresh(self):
        self.refresh_profiles()
        try:
            self.render_tasks(self.task_service.list(), self.profile_service.list())
            self.render_logs()
            self.render_settings()
        except Exception as exc:
            self.log(f"Refresh lỗi: {exc}")

    def refresh_profiles(self):
        try:
            self.process_service.discover()
            profiles = self.profile_service.list()
            query = self.search.text().lower()
            filter_value = self.status_filter.currentText()
            filters = {
                "Đã ghim": lambda p: p.pinned,
                "Quan trọng": lambda p: p.important,
                "Đang chạy": lambda p: p.status == ProfileStatus.RUNNING,
                "Đã dừng": lambda p: p.status != ProfileStatus.RUNNING,
                "Chrome gốc": lambda p: p.imported,
                "Profile riêng": lambda p: not p.imported,
            }
            keep = filters.get(filter_value, lambda p: True)
            groups = sorted({p.group_name for p in profiles if p.group_name}, key=str.casefold)
            current_group = self.group_filter.currentText()
            known = [self.group_filter.itemText(i) for i in range(1, self.group_filter.count())]
            if groups != known:
                self.group_filter.blockSignals(True)
                self.group_filter.clear()
                self.group_filter.addItems(["Tất cả nhóm", *groups])
                self.group_filter.setCurrentText(current_group)
                self.group_filter.blockSignals(False)
            group = self.group_filter.currentIndex()
            visible = [
                profile
                for profile in profiles
                if keep(profile)
                and (group <= 0 or profile.group_name == self.group_filter.currentText())
                and query
                in (
                    f"{profile.name} {profile.profile_directory} {profile.tags} "
                    f"{profile.notes} {profile.group_name} {profile.purpose}"
                ).lower()
            ]
            visible.sort(key=self.profile_sort_key)
            self.render_profiles(visible)
            running = sum(profile.status == ProfileStatus.RUNNING for profile in profiles)
            tasks = self.task_service.list()
            self._profile_counts = (len(visible), len(profiles), running)
            self._update_profile_label()
            self.empty_label.setVisible(not profiles)
            self.profile_list.setVisible(bool(profiles))
            self.dashboard_label.setText(
                f"Tác vụ bật: {sum(task.enabled for task in tasks)}\n"
                f"Lỗi tác vụ: {sum(task.status == 'FAILED' for task in tasks)}"
            )
            self._update_dashboard_stats(len(profiles), running, len(tasks))
            if self.stack.currentWidget() is self.task_page:
                self.render_tasks(tasks, profiles)
        except Exception as exc:
            self.log(f"Refresh lỗi: {exc}")

    @staticmethod
    def profile_sort_key(profile):
        """Match Chrome's profile order instead of sorting imported profiles by display name."""
        pinned = 0 if profile.pinned else 1
        if profile.imported:
            directory = profile.profile_directory or ""
            if directory == "Default":
                chrome_order = (0, 0)
            else:
                match = re.fullmatch(r"Profile (\d+)", directory)
                chrome_order = (1, int(match.group(1))) if match else (2, directory.casefold())
            return (pinned, 0, profile.user_data_dir or "", chrome_order, profile.name.casefold())
        return (pinned, 1, "", (0, 0), profile.name.casefold())

    def render_profiles(self, profiles):
        """Rebuild visible rows without moving the user's scroll position or selection."""
        table = self.profile_list
        # The 3 s poll usually finds nothing new; skip the rebuild so selection/scroll stay put.
        signature = tuple(
            (p.id, p.name, p.color, p.pinned, p.important, p.notes, p.status, p.group_name,
             p.purpose, p.tags, p.imported, p.profile_directory, p.remote_debugging, p.debug_port)
            for p in profiles
        )
        if signature == getattr(self, "_rendered_signature", None):
            return
        self._rendered_signature = signature
        scrollbar = table.verticalScrollBar()
        scroll_value = scrollbar.value()
        selected_ids = set(self.selected_ids())
        current_id = self._row_id(table.currentRow())

        header = table.horizontalHeader()
        # ResizeToContents re-measures every row on each setItem (quadratic); measure once instead.
        modes = [header.sectionResizeMode(c) for c in range(table.columnCount())]
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            table.clearSelection()
            table.setRowCount(len(profiles))
            selection = table.selectionModel()
            for row, profile in enumerate(profiles):
                dot = QPixmap(14, 14)
                dot.fill(QColor(profile.color or "#4285F4"))
                color_item = QTableWidgetItem()
                color_item.setIcon(QIcon(dot))
                prefix = ("📌 " if profile.pinned else "") + ("★ " if profile.important else "")
                name_item = QTableWidgetItem(prefix + profile.name)
                name_item.setData(Qt.ItemDataRole.UserRole, profile.id)
                name_item.setToolTip(profile.notes or profile.name)
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
                status_item = QTableWidgetItem("●  " + self.status_text(profile.status))
                status_item.setForeground(
                    QBrush(QColor(self.STATUS_COLORS.get(profile.status, "#94a3b8")))
                )
                cells = (
                    color_item,
                    name_item,
                    status_item,
                    QTableWidgetItem(profile.group_name),
                    QTableWidgetItem(profile.purpose),
                    QTableWidgetItem(profile.tags),
                    QTableWidgetItem("Chrome gốc" if profile.imported else "Profile riêng"),
                    QTableWidgetItem(profile.profile_directory),
                    QTableWidgetItem(str(profile.debug_port) if profile.remote_debugging and
                                     profile.debug_port else ""),
                )
                for column, item in enumerate(cells):
                    table.setItem(row, column, item)
                if profile.id in selected_ids:
                    selection.select(
                        table.model().index(row, 0),
                        selection.SelectionFlag.Select | selection.SelectionFlag.Rows,
                    )
                if profile.id == current_id:
                    selection.setCurrentIndex(
                        table.model().index(row, 1), selection.SelectionFlag.NoUpdate
                    )
        finally:
            for column, mode in enumerate(modes):
                header.setSectionResizeMode(column, mode)
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
        self.update_profile_actions()
        # Restore after Qt recalculates the table geometry.
        QTimer.singleShot(0, lambda: scrollbar.setValue(scroll_value))

    def _row_id(self, row):
        item = self.profile_list.item(row, 1) if row >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def status_text(self, status):
        return {
            ProfileStatus.RUNNING: "Đang chạy",
            ProfileStatus.STARTING: "Đang mở",
            ProfileStatus.STOPPING: "Đang đóng",
            ProfileStatus.ERROR: "Lỗi",
            ProfileStatus.STOPPED: "Đã dừng",
        }.get(status, str(status))

    def _update_dashboard_stats(self, total, running, task_count):
        cards = (
            ("Tổng profile", total),
            ("Đang chạy", running),
            ("Đã dừng", total - running),
            ("Tác vụ", task_count),
        )
        for card, (title, value) in zip(self.stat_cards, cards):
            card.setText(f"<b>{title}</b><br><span style='font-size:24px'>{value}</span>")

    def stop_all(self):
        try:
            self.process_service.stop_all()
            self.log("Đã đóng tất cả profile")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Không thể đóng profile", str(exc))

    def selected_ids(self):
        rows = sorted(index.row() for index in self.profile_list.selectionModel().selectedRows())
        return [self._row_id(row) for row in rows]

    def selected_id(self):
        ids = self.selected_ids()
        return ids[0] if ids else None

    def _run_action(self, callback, profile_id):
        try:
            callback(profile_id)
            self.log(f"Đã thực hiện {callback.__name__} cho profile {profile_id}")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Thao tác thất bại", str(exc))

    def _run_bulk(self, action, ids, title):
        if not ids:
            QMessageBox.information(self, title, "Hãy chọn ít nhất một profile.")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            results = action(ids, self.bulk_workers)
        finally:
            QApplication.restoreOverrideCursor()
        names = {profile.id: profile.name for profile in self.profile_service.list()}
        errors = [
            f"{names.get(pid, pid)}: {result}"
            for pid, result in results.items()
            if isinstance(result, Exception)
        ]
        self.log(f"{title}: {len(ids) - len(errors)}/{len(ids)} thành công")
        self.refresh_profiles()
        if errors:
            QMessageBox.warning(self, title, "Một số profile lỗi:\n" + "\n".join(errors))

    def open_selected(self):
        self._run_bulk(self.process_service.bulk_open, self.selected_ids(), "Mở profile")

    def close_selected(self):
        self._run_bulk(self.process_service.bulk_close, self.selected_ids(), "Đóng profile")

    def toggle_selected_important(self):
        ids = self.selected_ids()
        if not ids:
            QMessageBox.information(self, "Profile quan trọng", "Hãy chọn profile trước.")
            return
        profiles = {profile.id: profile for profile in self.profile_service.list()}
        should_mark = not all(profiles[profile_id].important for profile_id in ids)
        for profile_id in ids:
            self.profile_service.set_important(profile_id, should_mark)
        self.log(
            f"Đánh dấu {len(ids)} profile {'quan trọng' if should_mark else 'không quan trọng'}"
        )
        self.refresh()

    def open_all(self):
        ids = [profile.id for profile in self.profile_service.list()]
        self._run_bulk(self.process_service.bulk_open, ids, "Mở tất cả profile")

    def add_profile(self):
        dialog = ProfileDialog(self, groups=self._groups())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                profile = self.profile_service.create(dialog.values())
                self.log(f"Tạo profile {profile.name}")
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Không thể tạo", str(exc))

    def edit_profile(self, profile_id):
        profile = next((p for p in self.profile_service.list() if p.id == profile_id), None)
        if not profile:
            return
        dialog = ProfileDialog(self, profile, self._groups())
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.profile_service.update(profile.id, dialog.values())
                self.log(f"Cập nhật profile {profile.name}")
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Không thể cập nhật", str(exc))

    def import_chrome_profiles(self):
        try:
            count = self.profile_service.import_chrome_profiles()
            self.log(f"Quét Chrome: đã thêm {count} profile")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Không thể quét Chrome", str(exc))

    def show_profile_context_menu(self, position):
        profile_id = self.selected_id()
        if not profile_id:
            return
        menu = QMenu(self)
        menu.addAction("▶  Mở", self.open_selected)
        menu.addAction("■  Đóng", self.close_selected)
        single = (
            ("⟳  Khởi động lại", self.process_service.restart),
            ("✎  Sửa profile", self.edit_profile),
            ("⧉  Nhân bản cấu hình", self.clone_profile),
            ("📁  Mở thư mục dữ liệu", self.open_data_folder),
        )
        for title, callback in single:
            action = QAction(title, self)
            action.triggered.connect(
                lambda checked=False, cb=callback: self._run_action(cb, profile_id)
            )
            action.setEnabled(len(self.selected_ids()) == 1)
            menu.addAction(action)
        selected = next((p for p in self.profile_service.list() if p.id == profile_id), None)
        if selected and selected.imported and len(self.selected_ids()) == 1:
            menu.addAction(
                "⇪  Chuyển thành Profile riêng (giữ đăng nhập)",
                lambda: self.convert_profile(selected),
            )
        menu.addSeparator()
        menu.addAction("★  Đánh dấu / bỏ quan trọng", self.toggle_selected_important)
        menu.addAction("🗑  Xóa vĩnh viễn", self.delete_selected)
        menu.exec(self.profile_list.viewport().mapToGlobal(position))

    def delete_selected(self):
        ids = set(self.selected_ids())
        profiles = [p for p in self.profile_service.list() if p.id in ids]
        if not profiles:
            return
        names = "\n".join(f"  • {p.name}" for p in profiles[:10])
        more = f"\n  … và {len(profiles) - 10} profile khác" if len(profiles) > 10 else ""
        warning = (
            "\n\nCó profile Chrome gốc: hãy ĐÓNG HẾT Google Chrome trước. Profile sẽ bị gỡ "
            "khỏi Chrome luôn."
            if any(p.imported for p in profiles)
            else ""
        )
        if (
            QMessageBox.warning(
                self,
                "Xóa vĩnh viễn",
                f"Xóa vĩnh viễn {len(profiles)} profile?\n{names}{more}\n\n"
                "Toàn bộ dữ liệu (đăng nhập, cookie, lịch sử, extension), tác vụ và lịch sử "
                f"chạy của các profile này sẽ bị xóa khỏi máy. KHÔNG THỂ khôi phục.{warning}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        errors = []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for profile in profiles:
                try:
                    for task_id in self.profile_service.delete(profile.id):
                        self.scheduler_service.unschedule(task_id)
                except Exception as exc:
                    errors.append(f"{profile.name}: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
        self.log(f"Đã xóa vĩnh viễn {len(profiles) - len(errors)} profile")
        self.refresh()
        if errors:
            QMessageBox.warning(self, "Không thể xóa", "\n".join(errors))

    def convert_profile(self, profile):
        name, ok = QInputDialog.getText(
            self,
            "Chuyển thành Profile riêng",
            "Chép dữ liệu (đăng nhập, cookie, extension) sang một Profile riêng mới.\n"
            "Profile Chrome gốc giữ nguyên. Hãy ĐÓNG Google Chrome trước.\n\n"
            "Tên profile mới:",
            text=f"{profile.name} (riêng)",
        )
        if not ok or not name.strip():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            created = self.profile_service.convert_to_own(profile.id, name)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Không thể chuyển", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self.log(f"Đã chuyển {profile.name} thành Profile riêng {created.name}")
        self.refresh()
        QMessageBox.information(
            self,
            "Đã tạo Profile riêng",
            f"Đã tạo '{created.name}'.\n\nMở profile này và vào YouTube Studio để kiểm tra còn "
            "đăng nhập. Nếu Google yêu cầu đăng nhập lại thì đăng nhập một lần là xong.\n"
            "Tác vụ Public YouTube hãy chọn profile mới này.",
        )

    def clone_profile(self, profile_id):
        profile = next((p for p in self.profile_service.list() if p.id == profile_id), None)
        if not profile:
            return
        name, ok = QInputDialog.getText(
            self, "Nhân bản cấu hình", "Tên profile mới:", text=f"{profile.name} (copy)"
        )
        if ok and name.strip():
            self.profile_service.clone(profile_id, name.strip())
            self.log(f"Nhân bản {profile.name} -> {name.strip()}")

    def open_data_folder(self, profile_id):
        profile = next((p for p in self.profile_service.list() if p.id == profile_id), None)
        if not profile:
            return
        folder = (
            f"{profile.user_data_dir}/{profile.profile_directory}"
            if profile.imported
            else str(self.paths.profiles / profile.id)
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def export_profiles(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất cấu hình profile", "profiles.json", "JSON (*.json)"
        )
        if not path:
            return
        ids = self.selected_ids() or None
        try:
            count = self.profile_service.export_json(path, ids)
            self.log(f"Đã xuất {count} profile ra {path}")
        except Exception as exc:
            QMessageBox.warning(self, "Không thể xuất", str(exc))

    def import_profiles(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Nhập cấu hình profile", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            count = self.profile_service.import_json(path)
            self.log(f"Đã nhập {count} profile từ {path}")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Không thể nhập", str(exc))

    def toggle_important(self, profile_id):
        profile = next((p for p in self.profile_service.list() if p.id == profile_id), None)
        if not profile:
            return
        self.profile_service.set_important(profile_id, not profile.important)
        state = "quan trọng" if not profile.important else "bỏ đánh dấu quan trọng"
        self.log(f"Đã {state}: {profile.name}")
        self.refresh()

    def selected_task_id(self):
        rows = self.task_list.selectionModel().selectedRows()
        item = self.task_list.item(rows[0].row(), 0) if rows else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def render_tasks(self, tasks, profiles):
        names = {profile.id: profile.name for profile in profiles}
        selected = self.selected_task_id()
        table = self.task_list
        table.blockSignals(True)
        table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            schedule = SCHEDULE_LABELS.get(task.schedule_type, task.schedule_type)
            if task.schedule_type == "interval":
                schedule = f"Mỗi {task.interval_minutes} phút"
            elif task.schedule_type == "daily" and task.scheduled_at:
                schedule = f"Hằng ngày {task.scheduled_at:%H:%M}"
            elif task.schedule_type == "once" and task.scheduled_at:
                schedule = f"Lúc {task.scheduled_at:%d/%m %H:%M}"
            if task.schedule_type != "immediate" and not task.enabled:
                schedule += " (đã tắt)"
            next_run = self.scheduler_service.next_run(task.id)
            status = "Đang chờ chạy" if self.scheduler_service.is_running_now(task.id) else {
                TaskStatus.SUCCESS: "✔ Thành công",
                TaskStatus.FAILED: "✖ Lỗi",
                TaskStatus.RUNNING: "⟳ Đang chạy",
                TaskStatus.DISABLED: "Đã tắt",
            }.get(task.status, "Chưa chạy")
            cells = (
                task.name,
                f"Nhóm: {task.target_group}" if task.target_group
                else names.get(task.profile_id, "(profile đã xóa)"),
                ACTION_LABELS.get(task.action_type, task.action_type),
                schedule,
                f"{next_run:%d/%m %H:%M}" if next_run else "-",
                f"{task.last_run_at:%d/%m %H:%M}" if task.last_run_at else "-",
                status,
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, task.id)
                if column == 6:
                    item.setToolTip(task.last_error or "")
                    color = {"✔": "#16a34a", "✖": "#dc2626", "⟳": "#d97706"}.get(text[:1])
                    if color:
                        item.setForeground(QBrush(QColor(color)))
                table.setItem(row, column, item)
            if task.id == selected:
                table.selectRow(row)
        table.blockSignals(False)
        failed = sum(task.status == TaskStatus.FAILED for task in tasks)
        self.task_label.setText(
            f"{len(tasks)} tác vụ • {failed} lỗi lần chạy cuối • "
            "Tác vụ chỉ chạy theo lịch khi ứng dụng đang mở (kể cả khi ẩn dưới khay)"
        )
        for button in self.task_buttons:
            button.setEnabled(self.selected_task_id() is not None)
        self.render_task_history()

    def render_task_history(self):
        task_id = self.selected_task_id()
        for button in self.task_buttons:
            button.setEnabled(task_id is not None)
        if not task_id:
            self.task_history.setPlainText("Chọn một tác vụ để xem lịch sử chạy.")
            return
        lines = []
        for run in self.task_service.history(task_id):
            mark = {"SUCCESS": "✔", "FAILED": "✖"}.get(run.status, "⟳")
            tries = f" ({run.attempts} lần thử)" if run.attempts > 1 else ""
            error = f" — {run.error or run.detail}" if run.error or run.detail else ""
            when = f"{run.started_at:%d/%m %H:%M:%S}"
            lines.append(f"{when}  {mark} {run.profile_name}{tries}{error}")
        text = "\n".join(lines) or "Chưa chạy lần nào."
        if self.task_history.toPlainText() != text:
            self.task_history.setPlainText(text)

    def _task_dialog(self, task=None):
        profiles = self.profile_service.list()
        if not profiles:
            QMessageBox.information(self, "Tác vụ", "Chưa có profile.")
            return None
        dialog = TaskDialog(profiles, self._groups(), self, task)
        return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None

    def create_task(self):
        values = self._task_dialog()
        if values:
            try:
                task = self.task_service.create(**values)
                self.scheduler_service.schedule(task)
                self.log(f"Tạo tác vụ {task.name}")
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Không thể tạo tác vụ", str(exc))

    def edit_selected_task(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        values = self._task_dialog(self.task_service.get(task_id))
        if values:
            try:
                task = self.task_service.update(task_id, **values)
                self.scheduler_service.schedule(task)
                self.log(f"Cập nhật tác vụ {task.name}")
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Không thể cập nhật tác vụ", str(exc))

    def run_selected_task(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        try:
            self.scheduler_service.run_now(task_id)
            self.log("Đã đưa tác vụ vào hàng chạy nền")
        except Exception as exc:
            QMessageBox.warning(self, "Không thể chạy", f"Tác vụ đang chạy hoặc lỗi: {exc}")
        self.refresh()

    def stop_selected_task(self):
        task_id = self.selected_task_id()
        if task_id:
            self.task_service.stop(task_id)
            self.log("Đã gửi lệnh dừng: xử lý xong video hiện tại sẽ dừng")

    def toggle_selected_task(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        task = self.task_service.get(task_id)
        self.task_service.set_enabled(task_id, not task.enabled)
        try:
            self.scheduler_service.schedule(self.task_service.get(task_id))
        except ValueError as exc:
            QMessageBox.warning(self, "Lịch không hợp lệ", str(exc))
        self.log(f"{'Tắt' if task.enabled else 'Bật'} lịch tác vụ {task.name}")
        self.refresh()

    def delete_selected_task(self):
        task_id = self.selected_task_id()
        if not task_id:
            return
        task = self.task_service.get(task_id)
        if (
            QMessageBox.question(self, "Xóa tác vụ", f"Xóa tác vụ '{task.name}' và lịch sử chạy?")
            == QMessageBox.StandardButton.Yes
        ):
            self.scheduler_service.unschedule(task_id)
            self.task_service.delete(task_id)
            self.log(f"Xóa tác vụ {task.name}")
            self.refresh()

    def _groups(self):
        groups = {p.group_name for p in self.profile_service.list() if p.group_name}
        return sorted(groups, key=str.casefold)

    def log(self, message):
        self.statusBar().showMessage(message, 6000)
        self.paths.logs.mkdir(parents=True, exist_ok=True)
        with (self.paths.logs / "app.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat(timespec='seconds')} | {message}\n")

    def render_logs(self):
        path = self.paths.logs / "app.log"
        self.log_view.setPlainText(
            path.read_text(encoding="utf-8") if path.exists() else "Chưa có nhật ký"
        )

    def render_settings(self):
        settings_path = self.paths.config / "settings.json"
        if not settings_path.exists():
            settings_path.write_text(
                json.dumps({"data_root": str(self.paths.root), "ai": {}}, indent=2),
                encoding="utf-8",
            )
        self.settings_view.setPlainText(settings_path.read_text(encoding="utf-8"))
        self.render_ai_summary()

    def _read_settings(self):
        settings_path = self.paths.config / "settings.json"
        if not settings_path.exists():
            return {"data_root": str(self.paths.root), "ai": {}}
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"data_root": str(self.paths.root), "ai": {}}

    def _write_settings(self, settings):
        settings_path = self.paths.config / "settings.json"
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def render_ai_summary(self):
        settings = self._read_settings().get("ai", {})
        provider = settings.get("provider", "Chưa cấu hình")
        text_model = settings.get("text_model", "-")
        key_env = settings.get("api_key_env", "OPENAI_API_KEY")
        enabled = [
            label
            for enabled, label in (
                (settings.get("generate_title", True), "title"),
                (settings.get("generate_description", True), "description"),
                (settings.get("generate_thumbnail", False), "thumbnail"),
            )
            if enabled
        ]
        features = ", ".join(enabled) or "chưa chọn tính năng"
        self.ai_summary.setText(
            f"Provider: {provider}\nModel nội dung: {text_model}\n"
            f"Tính năng: {features}\nBiến API key: {key_env}\n"
            f"Duyệt trước khi áp dụng: "
            f"{'Có' if settings.get('require_approval', True) else 'Không'}"
        )

    def configure_ai(self):
        settings = self._read_settings().get("ai", {})
        dialog = AIAgentDialog(settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            app_settings = self._read_settings()
            app_settings["ai"] = {**settings, **dialog.values()}
            self._write_settings(app_settings)
            self.render_ai_summary()
            self.log("Cập nhật cấu hình AI Agent")

    def save_ai_prompt(self):
        settings = self._read_settings()
        settings.setdefault("ai", {})["prompt"] = self.ai_prompt.toPlainText().strip()
        self._write_settings(settings)
        self.render_ai_summary()
        self.log("Lưu prompt AI Agent")

    def check_ai_key(self):
        import os

        settings = self._read_settings().get("ai", {})
        variable = settings.get("api_key_env", "OPENAI_API_KEY")
        if os.environ.get(variable):
            QMessageBox.information(self, "API key", f"Đã tìm thấy biến môi trường {variable}.")
        else:
            QMessageBox.warning(self, "API key", f"Chưa tìm thấy biến môi trường {variable}.")

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip("Chrome Profile Manager")
        menu = QMenu(self)
        menu.addAction("Mở ứng dụng", self.showNormal)
        menu.addAction("Dừng tất cả profile", self.process_service.stop_all)
        menu.addAction("Thoát hoàn toàn", QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def closeEvent(self, event):
        # Đóng cửa sổ = thoát hẳn (không chạy ngầm trong khay).
        event.accept()
        QApplication.quit()
