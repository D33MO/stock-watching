"""
设置窗口 - 股票管理 & 刷新间隔设置 & 自定义显示字段
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QComboBox, QGroupBox, QListWidgetItem,
    QMessageBox, QAbstractItemView, QCheckBox, QWidget, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QObject, QTimer
from PyQt6.QtGui import QFont

from data.fetcher import fetch_stock_name, fetch_futures_name
from ui.stock_widget import REALTIME_FIELDS, SUPPLEMENTARY_FIELDS, FUTURES_FIELDS
from version import __version__, GITHUB_API_URL, GITHUB_RELEASES_URL


class FetchNameWorker(QObject):
    """后台获取股票名称的工作线程"""
    finished = pyqtSignal(str, str)  # code, name

    def __init__(self, code: str):
        super().__init__()
        self.code = code

    def run(self):
        name = fetch_stock_name(self.code)
        self.finished.emit(self.code, name)


class FetchFuturesNameWorker(QObject):
    """后台获取期货合约名称的工作线程"""
    finished = pyqtSignal(str, str)  # code, name

    def __init__(self, code: str):
        super().__init__()
        self.code = code

    def run(self):
        name = fetch_futures_name(self.code)
        self.finished.emit(self.code, name)


class CheckUpdateWorker(QObject):
    """后台检查更新的工作线程"""
    finished = pyqtSignal(bool, str)  # has_update, latest_version

    def run(self):
        try:
            import requests
            resp = requests.get(GITHUB_API_URL, timeout=5)
            if resp.status_code != 200:
                self.finished.emit(False, "")
                return
            data = resp.json()
            tag = data.get("tag_name", "")
            latest_ver = tag.lstrip("v")  # 去掉开头的 v
            has_update = self._compare_versions(latest_ver, __version__) > 0
            self.finished.emit(has_update, latest_ver)
        except Exception:
            self.finished.emit(False, "")

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        """版本比较，v1 > v2 返回 1，相等返回 0，小于返回 -1"""
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            for a, b in zip(parts1, parts2):
                if a > b:
                    return 1
                if a < b:
                    return -1
            return 0
        except (ValueError, AttributeError):
            return 0  # 解析失败视为相同版本


class SettingsDialog(QDialog):
    """设置窗口"""

    # 信号：设置保存后发射
    settings_changed = pyqtSignal()

    def __init__(self, stocks_config: list, refresh_interval: int,
                 auto_start: bool = False, always_on_top: bool = True,
                 display_fields: list[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(420, 620)
        self.stocks_config = list(stocks_config)
        self.refresh_interval = refresh_interval
        self.auto_start = auto_start
        self.always_on_top = always_on_top
        self.display_fields = display_fields or ["price", "change_pct", "intraday"]
        self._setup_ui()
        QTimer.singleShot(0, self._check_update)

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #2B2B2B; color: #E0E0E0; }
            QGroupBox {
                color: #CCCCCC; font-size: 13px; font-weight: bold;
                border: 1px solid #555; border-radius: 6px;
                margin-top: 10px; padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px; padding: 0 5px;
            }
            QLabel { color: #E0E0E0; font-size: 12px; }
            QLineEdit {
                background-color: #3C3C3C; color: #FFFFFF;
                border: 1px solid #555; border-radius: 4px;
                padding: 5px; font-size: 12px;
            }
            QPushButton {
                background-color: #4A4A4A; color: #FFFFFF;
                border: 1px solid #666; border-radius: 4px;
                padding: 5px 12px; font-size: 12px;
            }
            QPushButton:hover { background-color: #5A5A5A; }
            QPushButton#btn_delete {
                background-color: #663333;
            }
            QPushButton#btn_delete:hover {
                background-color: #884444;
            }
            QPushButton#btn_save {
                background-color: #336633;
                font-weight: bold;
            }
            QPushButton#btn_save:hover {
                background-color: #448844;
            }
            QListWidget {
                background-color: #333333; color: #E0E0E0;
                border: 1px solid #555; border-radius: 4px;
                font-size: 12px;
            }
            QListWidget::item:selected { background-color: #444; }
            QComboBox {
                background-color: #3C3C3C; color: #FFFFFF;
                border: 1px solid #555; border-radius: 4px;
                padding: 5px; font-size: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #333; color: #E0E0E0;
                selection-background-color: #444;
            }
            QCheckBox {
                color: #E0E0E0; font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #666;
                border-radius: 3px;
                background-color: #3C3C3C;
            }
            QCheckBox::indicator:checked {
                background-color: #336633;
                border-color: #448844;
            }
            QCheckBox::indicator:hover {
                border-color: #888;
            }
        """)

        main_layout = QVBoxLayout(self)

        # 创建滚动区域，内容过多时可滚动
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: transparent;")
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)

        # ===== 股票管理 =====
        group_stocks = QGroupBox("股票管理")
        stocks_layout = QVBoxLayout()

        # 输入行
        input_layout = QHBoxLayout()
        self.combo_type = QComboBox()
        self.combo_type.addItems(["股票", "期货"])
        self.combo_type.setFixedWidth(70)
        self.combo_type.currentTextChanged.connect(self._on_type_changed)
        input_layout.addWidget(self.combo_type)

        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("输入股票代码，如 600519")
        self.input_code.returnPressed.connect(self._add_stock)
        input_layout.addWidget(self.input_code)

        btn_add = QPushButton("+ 添加")
        btn_add.clicked.connect(self._add_stock)
        input_layout.addWidget(btn_add)
        self.btn_add = btn_add

        stocks_layout.addLayout(input_layout)

        # 股票列表
        self.stock_list = QListWidget()
        self.stock_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.stock_list.setMinimumHeight(160)
        self._refresh_stock_list()
        stocks_layout.addWidget(self.stock_list, 1)

        # 删除按钮
        btn_layout = QHBoxLayout()
        btn_delete = QPushButton("删除选中")
        btn_delete.setObjectName("btn_delete")
        btn_delete.clicked.connect(self._delete_stock)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        stocks_layout.addLayout(btn_layout)

        group_stocks.setLayout(stocks_layout)
        layout.addWidget(group_stocks)

        # ===== 实时行情 =====
        group_realtime = QGroupBox("实时行情")
        rt_layout = QVBoxLayout()

        # 字段勾选（网格）
        rt_grid = QGridLayout()
        rt_grid.setVerticalSpacing(6)
        self._realtime_cbs = {}
        col = 0
        row = 0
        for key, spec in REALTIME_FIELDS.items():
            cb = QCheckBox(spec["label"])
            cb.setChecked(key in self.display_fields)
            self._realtime_cbs[key] = cb
            rt_grid.addWidget(cb, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
        # 分时图
        self._cb_intraday = QCheckBox("分时图")
        self._cb_intraday.setChecked("intraday" in self.display_fields)
        rt_grid.addWidget(self._cb_intraday, row + 1, 0)
        rt_layout.addLayout(rt_grid)

        # 刷新间隔（放在实时行情组内）
        rt_sep = QWidget()
        rt_sep.setFixedHeight(1)
        rt_sep.setStyleSheet("background-color: #444;")
        rt_layout.addWidget(rt_sep)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("刷新间隔:"))
        self.combo_interval = QComboBox()
        self.combo_interval.addItems(["3秒", "5秒", "10秒", "30秒", "60秒"])
        self.interval_values = [3, 5, 10, 30, 60]
        if self.refresh_interval in self.interval_values:
            self.combo_interval.setCurrentIndex(self.interval_values.index(self.refresh_interval))
        else:
            self.combo_interval.setCurrentIndex(1)
        interval_row.addWidget(self.combo_interval)
        interval_row.addStretch()
        rt_layout.addLayout(interval_row)

        group_realtime.setLayout(rt_layout)
        layout.addWidget(group_realtime)

        # 补充数据字段
        group_supp = QGroupBox("其他数据")
        supp_layout = QVBoxLayout()
        supp_grid = QHBoxLayout()
        self._supp_cbs = {}
        for key, spec in SUPPLEMENTARY_FIELDS.items():
            cb = QCheckBox(spec["label"])
            cb.setChecked(key in self.display_fields)
            self._supp_cbs[key] = cb
            supp_grid.addWidget(cb)
        supp_grid.addStretch()
        supp_layout.addLayout(supp_grid)
        # 说明文字
        note = QLabel("量比和换手率数据约3分钟更新一次")
        note.setStyleSheet("color: #888888; font-size: 10px;")
        supp_layout.addWidget(note)

        # 期货字段
        supp_sep = QWidget()
        supp_sep.setFixedHeight(1)
        supp_sep.setStyleSheet("background-color: #444;")
        supp_layout.addWidget(supp_sep)

        futures_row = QHBoxLayout()
        self._futures_cbs = {}
        for key, spec in FUTURES_FIELDS.items():
            cb = QCheckBox(spec["label"])
            cb.setChecked(key in self.display_fields)
            self._futures_cbs[key] = cb
            futures_row.addWidget(cb)
        futures_row.addStretch()
        supp_layout.addLayout(futures_row)

        group_supp.setLayout(supp_layout)
        layout.addWidget(group_supp)

        # ===== 窗口行为 =====
        group_behavior = QGroupBox("窗口行为")
        behavior_layout = QVBoxLayout()

        self.cb_auto_start = QCheckBox("开机自启动")
        self.cb_auto_start.setChecked(self.auto_start)
        self.cb_auto_start.setToolTip("开机后自动启动本程序")
        behavior_layout.addWidget(self.cb_auto_start)

        self.cb_always_on_top = QCheckBox("窗口置顶")
        self.cb_always_on_top.setChecked(self.always_on_top)
        self.cb_always_on_top.setToolTip("窗口始终显示在其他窗口之上")
        behavior_layout.addWidget(self.cb_always_on_top)

        group_behavior.setLayout(behavior_layout)
        layout.addWidget(group_behavior)

        # 将设置内容放入滚动区域
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # ===== 版本信息 =====
        update_layout = QHBoxLayout()
        self.label_version = QLabel(f"当前版本 v{__version__}")
        self.label_version.setStyleSheet("color: #666666; font-size: 11px;")
        self.label_update = QLabel("")
        self.label_update.setStyleSheet("color: #FFAA00; font-size: 11px;")
        self.btn_download = QPushButton("去下载")
        self.btn_download.setStyleSheet("""
            QPushButton {
                color: #FFFFFF; font-size: 11px;
                background-color: #2266CC; border: none;
                border-radius: 4px; padding: 4px 12px;
            }
            QPushButton:hover { background-color: #3388EE; }
        """)
        self.btn_download.clicked.connect(self._open_download)
        self.btn_download.setVisible(False)
        update_layout.addWidget(self.label_version)
        update_layout.addWidget(self.label_update)
        update_layout.addWidget(self.btn_download)
        update_layout.addStretch()
        main_layout.addLayout(update_layout)

        # ===== 底部按钮 =====
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)

        btn_save = QPushButton("保存")
        btn_save.setObjectName("btn_save")
        btn_save.clicked.connect(self._save)
        bottom_layout.addWidget(btn_save)

        main_layout.addLayout(bottom_layout)

    def _refresh_stock_list(self):
        """刷新品种列表显示"""
        self.stock_list.clear()
        for item in self.stocks_config:
            typ = item.get("type", "stock")
            name = item.get("name", "")
            if typ == "futures":
                display = f"{item['code']}  {name}  [期货]"
            else:
                display = f"{item['code']}  {name}"
            self.stock_list.addItem(display)

    def _on_type_changed(self, text: str):
        """切换添加类型时更新提示"""
        if text == "期货":
            self.input_code.setPlaceholderText("输入期货代码，如 CU2409")
        else:
            self.input_code.setPlaceholderText("输入股票代码，如 600519")

    def _add_stock(self):
        """添加品种（异步获取名称）"""
        code = self.input_code.text().strip().upper()
        if not code:
            return

        inst_type = "futures" if self.combo_type.currentText() == "期货" else "stock"

        for s in self.stocks_config:
            if s["code"] == code:
                QMessageBox.warning(self, "提示", f"{code} 已存在")
                return

        self.input_code.clear()
        self.input_code.setPlaceholderText("正在获取名称...")
        self.btn_add.setEnabled(False)
        self.combo_type.setEnabled(False)

        if inst_type == "futures":
            self._fetch_thread = QThread()
            self._fetch_worker = FetchFuturesNameWorker(code)
            self._fetch_worker.moveToThread(self._fetch_thread)
            self._fetch_thread.started.connect(self._fetch_worker.run)
            self._fetch_worker.finished.connect(self._on_futures_name_fetched)
            self._fetch_worker.finished.connect(self._fetch_thread.quit)
            self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
            self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
            self._fetch_thread.start()
        else:
            self._fetch_thread = QThread()
            self._fetch_worker = FetchNameWorker(code)
            self._fetch_worker.moveToThread(self._fetch_thread)
            self._fetch_thread.started.connect(self._fetch_worker.run)
            self._fetch_worker.finished.connect(self._on_name_fetched)
            self._fetch_worker.finished.connect(self._fetch_thread.quit)
            self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
            self._fetch_thread.finished.connect(self._fetch_thread.deleteLater)
            self._fetch_thread.start()

    def _on_name_fetched(self, code: str, name: str):
        self.btn_add.setEnabled(True)
        self.combo_type.setEnabled(True)
        self.input_code.setPlaceholderText("输入股票代码，如 600519")

        if not name:
            name = code

        new_item = {"code": code, "name": name, "type": "stock"}
        self.stocks_config.append(new_item)
        self._refresh_stock_list()

    def _on_futures_name_fetched(self, code: str, name: str):
        self.btn_add.setEnabled(True)
        self.combo_type.setEnabled(True)
        self.input_code.setPlaceholderText("输入期货代码，如 CU2409（沪铜2409）")

        if not name:
            name = code

        new_item = {"code": code, "name": name, "type": "futures"}
        self.stocks_config.append(new_item)
        self._refresh_stock_list()

    def _check_update(self):
        """后台检查更新"""
        self._update_thread = QThread()
        self._update_worker = CheckUpdateWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.finished.connect(self._on_update_check)
        self._update_worker.finished.connect(self._update_thread.quit)
        self._update_worker.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.start()

    def _on_update_check(self, has_update: bool, latest_ver: str):
        """更新检查结果"""
        if has_update:
            self.label_update.setText(f"🔔 发现新版本 v{latest_ver}  ")
            self.btn_download.setVisible(True)

    def _open_download(self):
        """打开下载页面"""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(GITHUB_RELEASES_URL))

    def _delete_stock(self):
        row = self.stock_list.currentRow()
        if row < 0:
            return
        self.stocks_config.pop(row)
        self._refresh_stock_list()

    def _save(self):
        """保存设置"""
        idx = self.combo_interval.currentIndex()
        self.refresh_interval = self.interval_values[idx]
        self.auto_start = self.cb_auto_start.isChecked()
        self.always_on_top = self.cb_always_on_top.isChecked()
        self.display_fields = self.get_display_fields()
        self.settings_changed.emit()
        self.accept()

    def get_stocks_config(self):
        return self.stocks_config

    def get_refresh_interval(self):
        return self.refresh_interval

    def get_auto_start(self):
        return self.auto_start

    def get_always_on_top(self):
        return self.always_on_top

    def get_display_fields(self) -> list[str]:
        """获取用户勾选的显示字段列表（保持配置中的顺序）"""
        fields = []
        # 实时字段按定义顺序
        for key in REALTIME_FIELDS:
            if self._realtime_cbs[key].isChecked():
                fields.append(key)
        # 分时图
        if self._cb_intraday.isChecked():
            fields.append("intraday")
        # 补充字段按定义顺序
        for key in SUPPLEMENTARY_FIELDS:
            if self._supp_cbs[key].isChecked():
                fields.append(key)
        # 期货字段
        for key in FUTURES_FIELDS:
            if self._futures_cbs[key].isChecked():
                fields.append(key)
        return fields
