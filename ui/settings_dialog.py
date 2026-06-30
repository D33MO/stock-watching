"""
设置窗口 - 股票管理 & 刷新间隔设置
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QComboBox, QGroupBox, QListWidgetItem,
    QMessageBox, QAbstractItemView, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from data.fetcher import fetch_stock_name


class SettingsDialog(QDialog):
    """设置窗口"""

    # 信号：设置保存后发射
    settings_changed = pyqtSignal()

    def __init__(self, stocks_config: list, refresh_interval: int,
                 auto_start: bool = False, always_on_top: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setFixedSize(400, 560)
        self.stocks_config = list(stocks_config)  # [{"code": "600519", "name": "贵州茅台"}, ...]
        self.refresh_interval = refresh_interval
        self.auto_start = auto_start
        self.always_on_top = always_on_top
        self._setup_ui()

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

        layout = QVBoxLayout(self)

        # ===== 股票管理 =====
        group_stocks = QGroupBox("股票管理")
        stocks_layout = QVBoxLayout()

        # 输入行
        input_layout = QHBoxLayout()
        self.input_code = QLineEdit()
        self.input_code.setPlaceholderText("输入股票代码，如 600519")
        self.input_code.returnPressed.connect(self._add_stock)
        input_layout.addWidget(self.input_code)

        btn_add = QPushButton("+ 添加")
        btn_add.clicked.connect(self._add_stock)
        input_layout.addWidget(btn_add)

        stocks_layout.addLayout(input_layout)

        # 股票列表
        self.stock_list = QListWidget()
        self.stock_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._refresh_stock_list()
        stocks_layout.addWidget(self.stock_list)

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

        # ===== 刷新设置 =====
        group_refresh = QGroupBox("数据刷新")
        refresh_layout = QHBoxLayout()

        refresh_layout.addWidget(QLabel("刷新间隔:"))

        self.combo_interval = QComboBox()
        self.combo_interval.addItems(["3秒", "5秒", "10秒", "30秒", "60秒"])
        self.interval_values = [3, 5, 10, 30, 60]
        # 设置当前选中
        if self.refresh_interval in self.interval_values:
            self.combo_interval.setCurrentIndex(self.interval_values.index(self.refresh_interval))
        else:
            self.combo_interval.setCurrentIndex(1)  # 默认5秒
        refresh_layout.addWidget(self.combo_interval)

        refresh_layout.addStretch()
        group_refresh.setLayout(refresh_layout)
        layout.addWidget(group_refresh)

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

        layout.addLayout(bottom_layout)

    def _refresh_stock_list(self):
        """刷新股票列表显示"""
        self.stock_list.clear()
        for item in self.stocks_config:
            self.stock_list.addItem(f"{item['code']}  {item.get('name', '')}")

    def _add_stock(self):
        """添加股票"""
        code = self.input_code.text().strip()
        if not code:
            return

        # 检查是否已存在
        for s in self.stocks_config:
            if s["code"] == code:
                QMessageBox.warning(self, "提示", f"股票 {code} 已存在")
                return

        self.input_code.clear()

        # 同步获取股票名称（会短暂阻塞）
        self.input_code.setPlaceholderText("正在获取股票名称...")
        name = fetch_stock_name(code)
        self.input_code.setPlaceholderText("输入股票代码，如 600519")

        if not name:
            name = code

        new_item = {"code": code, "name": name}
        self.stocks_config.append(new_item)
        self._refresh_stock_list()

    def _delete_stock(self):
        """删除选中股票"""
        row = self.stock_list.currentRow()
        if row < 0:
            return
        self.stocks_config.pop(row)
        self._refresh_stock_list()

    def _save(self):
        """保存设置"""
        # 获取刷新间隔
        idx = self.combo_interval.currentIndex()
        self.refresh_interval = self.interval_values[idx]
        # 获取窗口行为设置
        self.auto_start = self.cb_auto_start.isChecked()
        self.always_on_top = self.cb_always_on_top.isChecked()
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
