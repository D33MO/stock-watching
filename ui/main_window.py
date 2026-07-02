"""
主窗口模块
无边框、置顶、半透明、可拖拽的悬浮窗
"""

import json
import os
import sys
import winreg
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSystemTrayIcon, QMenu, QApplication,
    QMessageBox, QInputDialog, QDialog, QLineEdit,
    QPushButton, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QByteArray, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QAction, QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from data.fetcher import (
    StockData, fetch_realtime, fetch_kline, fetch_intraday, fetch_supplementary,
    fetch_futures_realtime, fetch_futures_intraday,
)
from ui.stock_widget import StockRow, ALL_FIELD_SPECS, ALL_FIELD_WIDTH
from ui.settings_dialog import SettingsDialog


def get_config_path():
    """获取配置文件路径"""
    if getattr(sys, 'frozen', False):
        # 打包后，配置文件在exe同目录
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "config.json")


def load_config():
    """加载配置文件"""
    path = get_config_path()
    default = {
        "stocks": [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "300750", "name": "宁德时代"},
            {"code": "002594", "name": "比亚迪"},
        ],
        "display_fields": ["price", "change_pct", "intraday"],
        "refresh_interval": 5,
        "window_x": 0,
        "window_y": 800,
        "opacity": 0.9,
        "auto_start": False,
        "always_on_top": True,
        "transparent_bg": False,
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 合并默认值
            for k, v in default.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception:
        return default


def save_config(cfg):
    """保存配置文件"""
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存配置失败: {e}")


# ===== 开机自启动（Windows 注册表） =====
APP_NAME = "股票监控"
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_path():
    """获取当前可执行文件路径"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)


def set_auto_start(enable: bool):
    """设置开机自启动"""
    try:
        exe_path = _get_exe_path()
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE)
        if enable:
            # 使用 --autostart 标记区分是否为自启动
            if getattr(sys, 'frozen', False):
                cmd = f'"{exe_path}" --autostart'
            else:
                cmd = f'"{sys.executable}" "{exe_path}" --autostart'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"设置开机自启动失败: {e}")


def is_auto_start_enabled() -> bool:
    """检查是否已设置开机自启动"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


class RefreshWorker(QObject):
    """后台刷新数据的工作线程，内部并行请求所有品种"""
    finished = pyqtSignal(str)  # task_id

    def __init__(self, stocks: list, task_id: str,
                 do_realtime=False, do_intraday=False, do_supplementary=False):
        super().__init__()
        self.stocks = stocks
        self.task_id = task_id
        self.do_realtime = do_realtime
        self.do_intraday = do_intraday
        self.do_supplementary = do_supplementary

    def run(self):
        """在后台线程中执行，并行请求所有品种数据"""
        with ThreadPoolExecutor(max_workers=min(8, len(self.stocks) or 1)) as executor:
            futures = []
            for stock in self.stocks:
                if self.do_realtime:
                    if stock.instrument_type == "futures":
                        futures.append(executor.submit(fetch_futures_realtime, stock))
                    else:
                        futures.append(executor.submit(fetch_realtime, stock))
                if self.do_intraday:
                    if stock.instrument_type == "futures":
                        futures.append(executor.submit(fetch_futures_intraday, stock))
                    else:
                        futures.append(executor.submit(fetch_intraday, stock))
            if self.do_supplementary:
                futures.append(executor.submit(fetch_supplementary, self.stocks))
            # 等待所有请求完成
            for f in futures:
                f.result()
        self.finished.emit(self.task_id)


class MainWindow(QMainWindow):
    """主悬浮窗"""

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.stocks: list[StockData] = []
        self.stock_rows: list[StockRow] = []
        self._drag_pos = None
        self._workers: dict[str, tuple] = {}  # task_id -> (thread, worker)

        self._init_stocks()
        self._setup_ui()
        self._setup_tray()
        self._setup_timers()

        # 设置窗口图标
        logo_path = self._get_logo_path()
        if logo_path:
            self.setWindowIcon(QIcon(logo_path))

        # 加载分时数据（后台）
        QTimer.singleShot(500, self._load_all_intraday)

    @staticmethod
    def _get_logo_path():
        """获取 logo.png 的路径"""
        if getattr(sys, 'frozen', False):
            # 打包后，优先从 exe 内部打包的资源中查找（sys._MEIPASS）
            meipass_path = os.path.join(sys._MEIPASS, "logo.png")
            if os.path.exists(meipass_path):
                return meipass_path
            # 兼容：如果 logo.png 在 exe 同目录（手动复制的情况）
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_dir, "logo.png")
        return path if os.path.exists(path) else None

    @staticmethod
    def _get_assets_dir():
        """获取 assets 目录路径"""
        if getattr(sys, 'frozen', False):
            # 打包后，优先从 exe 内部的资源中查找（sys._MEIPASS）
            meipass_path = os.path.join(sys._MEIPASS, "assets")
            if os.path.exists(meipass_path):
                return meipass_path
            # 兼容：如果 assets 在 exe 同目录（手动复制的情况）
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "assets")

    def _init_stocks(self):
        """初始化品种列表（股票/期货）"""
        from data.fetcher import fetch_futures_name
        for item in self.config.get("stocks", []):
            inst_type = item.get("type", "stock")
            name = item.get("name", item["code"])
            if inst_type == "futures" and not name:
                name = fetch_futures_name(item["code"])
            sd = StockData(item["code"], name, inst_type)
            self.stocks.append(sd)

    def _apply_window_flags(self):
        """根据配置应用窗口标志（置顶等）"""
        visible = self.isVisible()
        if visible:
            self.hide()  # 切换 WindowFlags 前必须先 hide()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool  # 不在任务栏显示
        )
        if self.config.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if visible:
            self.show()

    def _setup_ui(self):
        """设置UI"""
        self.setWindowTitle("行情监控")
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 主容器
        self.central_widget = QWidget()
        self._apply_container_style()
        self.central_widget.setObjectName("container")

        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)

        # 标题栏
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(24)
        self._apply_title_bar_style()
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(8, 0, 4, 0)

        # 标题图标
        logo_path = self._get_logo_path()
        logo_label = QLabel()
        if logo_path:
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(pixmap)
        logo_label.setFixedSize(16, 16)

        title_label = QLabel("行情监控")
        title_label.setStyleSheet("color: #AAAAAA; font-size: 11px; font-weight: bold;")
        title_layout.addWidget(logo_label)
        title_layout.addSpacing(4)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 设置按钮
        self.btn_settings = QPushButton()
        self.btn_settings.setFixedSize(20, 18)
        self.btn_settings.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
            }
        """)
        self.btn_settings.setIcon(self._load_svg_icon("setting.svg", "#AAAAAA"))
        self.btn_settings.setIconSize(self.btn_settings.size())
        self.btn_settings.installEventFilter(self)
        self.btn_settings.setToolTip("设置")
        self.btn_settings.clicked.connect(self._open_settings)
        title_layout.addWidget(self.btn_settings)

        # 置顶按钮
        self.btn_pin = QPushButton()
        self.btn_pin.setFixedSize(20, 18)
        self.btn_pin.setToolTip("已置顶 - 点击取消")
        self.btn_pin.installEventFilter(self)
        self._update_pin_button_style()
        self.btn_pin.clicked.connect(self._toggle_pin)
        title_layout.addWidget(self.btn_pin)

        # 关闭按钮（最小化到托盘）
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(20, 18)
        btn_close.setStyleSheet("""
            QPushButton {
                color: #AAAAAA; font-size: 13px; font-weight: bold;
                background: transparent; border: none;
            }
            QPushButton:hover { color: #FF4444; }
        """)
        btn_close.setToolTip("最小化到托盘")
        btn_close.clicked.connect(self.close)
        title_layout.addWidget(btn_close)

        main_layout.addWidget(self.title_bar)

        # 分隔线
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #444;")
        main_layout.addWidget(sep)

        # 股票行
        self.stock_container = QWidget()
        self.stock_layout = QVBoxLayout(self.stock_container)
        self.stock_layout.setContentsMargins(0, 2, 0, 2)
        self.stock_layout.setSpacing(0)
        main_layout.addWidget(self.stock_container)

        self.setCentralWidget(self.central_widget)

        # 创建股票行
        self._create_stock_rows()

        # 设置位置和大小
        self._update_geometry()

    def _create_stock_rows(self):
        """创建股票行"""
        # 清除旧的
        for row in self.stock_rows:
            row.setParent(None)
            row.deleteLater()
        self.stock_rows.clear()

        display_fields = self.config.get("display_fields", ["price", "change_pct", "intraday"])
        for stock in self.stocks:
            row = StockRow(stock, display_fields=display_fields)
            row.clicked.connect(self._on_stock_clicked)
            self.stock_rows.append(row)
            self.stock_layout.addWidget(row)

            # 分隔线
            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: #333;")
            self.stock_layout.addWidget(sep)

        self._update_geometry()

    def _update_geometry(self):
        """更新窗口几何信息"""
        n = len(self.stocks)
        title_h = 25
        row_h = 56
        total_h = title_h + n * (row_h + 1) + 4

        # 根据显示字段计算宽度
        display_fields = self.config.get("display_fields", ["price", "change_pct", "intraday"])
        w = 78  # 名称标签(70) + 左边距(8)
        for f in display_fields:
            if f == "intraday":
                w += 96  # 分时图宽度(90) + 间距(6)
            elif f in ALL_FIELD_SPECS:
                w += ALL_FIELD_WIDTH + 6  # 字段宽度 + 间距
        w += 8  # 右边距

        x = self.config.get("window_x", 0)
        y = self.config.get("window_y", 800)

        self.setFixedSize(w, total_h)
        self.move(x, y)

    def _setup_tray(self):
        """设置系统托盘"""
        # 使用 logo.png 作为图标
        logo_path = self._get_logo_path()
        if logo_path:
            icon = QIcon(logo_path)
        else:
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(220, 50, 50))
            icon = QIcon(pixmap)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("行情监控")

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #2B2B2B; color: #E0E0E0;
                border: 1px solid #555;
            }
            QMenu::item:selected { background-color: #444; }
        """)

        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        settings_action_tray = QAction("设置", self)
        settings_action_tray.triggered.connect(self._open_settings)
        menu.addAction(settings_action_tray)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _setup_timers(self):
        """设置定时器"""
        # 实时行情刷新
        self.timer_realtime = QTimer(self)
        self.timer_realtime.timeout.connect(self._refresh_realtime)
        interval = self.config.get("refresh_interval", 5) * 1000
        self.timer_realtime.start(interval)

        # 分时数据刷新（每60秒）
        self.timer_intraday = QTimer(self)
        self.timer_intraday.timeout.connect(self._refresh_intraday)
        self.timer_intraday.start(60000)

        # 补充数据定时器（量比、换手率等，每3分钟）
        self.timer_supplementary = QTimer(self)
        self.timer_supplementary.timeout.connect(self._refresh_supplementary)
        self.timer_supplementary.start(180000)  # 3分钟

        # 启动时立即刷新一次
        QTimer.singleShot(100, self._refresh_realtime)
        QTimer.singleShot(500, self._refresh_supplementary)

    def _start_refresh(self, task_id: str, do_realtime=False, do_intraday=False, do_supplementary=False):
        """在后台线程中刷新数据，完成后自动更新 UI"""
        if not self.stocks:
            return

        # 如果同类型 worker 还在运行，跳过本次刷新
        if task_id in self._workers:
            return

        thread = QThread(self)
        worker = RefreshWorker(
            stocks=self.stocks,
            task_id=task_id,
            do_realtime=do_realtime,
            do_intraday=do_intraday,
            do_supplementary=do_supplementary,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda tid: self._on_refresh_finished(tid))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.wait)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._workers.pop(task_id, None))

        self._workers[task_id] = (thread, worker)
        thread.start()

    def _on_refresh_finished(self, task_id: str):
        """后台刷新完成，在主线程更新 UI"""
        if task_id in ("realtime", "load_all"):
            # 实时数据或首次加载完成 → 更新所有行
            for row in self.stock_rows:
                row.update_display()
        elif task_id == "intraday":
            # 分时数据更新完成
            for row in self.stock_rows:
                row.update_display()
        elif task_id == "supplementary":
            # 补充数据更新完成
            for row in self.stock_rows:
                row.update_display()

    def _refresh_realtime(self):
        """刷新所有品种的实时行情（后台并行）"""
        self._start_refresh(task_id="realtime", do_realtime=True)

    def _refresh_intraday(self):
        """刷新所有品种的分时数据（后台并行）"""
        self._start_refresh(task_id="intraday", do_intraday=True)

    def _refresh_supplementary(self):
        """刷新补充数据（量比、换手率等，后台并行）"""
        if not self.stocks:
            return
        self._start_refresh(task_id="supplementary", do_supplementary=True)

    def _load_all_intraday(self):
        """加载所有品种的分时数据（首次，后台并行）"""
        self._start_refresh(task_id="load_all", do_realtime=True, do_intraday=True)
        # 首次加载补充数据（延迟启动，等实时数据先回来）
        QTimer.singleShot(3000, lambda: self._start_refresh(
            task_id="supp_first", do_supplementary=True))

    def _open_settings(self):
        """打开设置窗口"""
        dialog = SettingsDialog(
            stocks_config=self.config.get("stocks", []),
            refresh_interval=self.config.get("refresh_interval", 5),
            auto_start=self.config.get("auto_start", False),
            always_on_top=self.config.get("always_on_top", True),
            transparent_bg=self.config.get("transparent_bg", False),
            display_fields=self.config.get("display_fields", ["price", "change_pct", "intraday"]),
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_stocks = dialog.get_stocks_config()
            new_interval = dialog.get_refresh_interval()
            new_auto_start = dialog.get_auto_start()
            new_always_on_top = dialog.get_always_on_top()
            new_transparent_bg = dialog.get_transparent_bg()
            new_display_fields = dialog.get_display_fields()

            # 记录旧值用于比较
            old_always_on_top = self.config.get("always_on_top", True)
            old_display_fields = self.config.get("display_fields", [])

            # 更新配置
            self.config["stocks"] = new_stocks
            self.config["display_fields"] = new_display_fields
            self.config["refresh_interval"] = new_interval
            self.config["auto_start"] = new_auto_start
            self.config["always_on_top"] = new_always_on_top
            self.config["transparent_bg"] = new_transparent_bg
            save_config(self.config)

            # 应用开机自启动设置
            set_auto_start(new_auto_start)

            # 应用窗口置顶设置（仅在变化时切换）
            if new_always_on_top != old_always_on_top:
                self._apply_window_flags()
                self.show()

            # 应用透明背景设置
            self._apply_container_style()
            self._apply_title_bar_style()
            self.update()  # 触发重绘 paintEvent

            # 重建股票列表
            self._rebuild_stocks()

            # 更新刷新间隔
            interval_ms = new_interval * 1000
            self.timer_realtime.start(interval_ms)

    def _rebuild_stocks(self):
        """根据配置重建品种列表"""
        from data.fetcher import fetch_futures_name
        # 清除旧的
        for row in self.stock_rows:
            row.setParent(None)
            row.deleteLater()
        self.stock_rows.clear()
        self.stocks.clear()

        # 重新初始化
        for item in self.config.get("stocks", []):
            inst_type = item.get("type", "stock")
            name = item.get("name", item["code"])
            if inst_type == "futures" and not name:
                name = fetch_futures_name(item["code"])
            self.stocks.append(StockData(item["code"], name, inst_type))

        # 重建行
        display_fields = self.config.get("display_fields", ["price", "change_pct", "intraday"])
        for stock in self.stocks:
            row = StockRow(stock, display_fields=display_fields)
            row.clicked.connect(self._on_stock_clicked)
            self.stock_rows.append(row)
            self.stock_layout.addWidget(row)

            sep = QWidget()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: #333;")
            self.stock_layout.addWidget(sep)

        self._update_geometry()

        # 加载数据
        QTimer.singleShot(200, self._load_all_intraday)

    def _load_single_stock(self, stock):
        """加载单只股票数据"""
        fetch_realtime(stock)
        fetch_intraday(stock)
        for row in self.stock_rows:
            if row.stock_data is stock:
                row.update_display()
                break

    def _on_stock_clicked(self, code):
        """点击股票行"""
        # 可以扩展：点击后显示详细信息等
        pass

    def _apply_container_style(self):
        """根据 transparent_bg 设置容器背景样式"""
        is_transparent = self.config.get("transparent_bg", False)
        if is_transparent:
            self.central_widget.setStyleSheet("""
                QWidget#container {
                    background-color: transparent;
                    border: 1px solid #444;
                    border-radius: 6px;
                }
            """)
        else:
            self.central_widget.setStyleSheet("""
                QWidget#container {
                    background-color: rgba(30, 30, 30, 230);
                    border: 1px solid #444;
                    border-radius: 6px;
                }
            """)

    def _apply_title_bar_style(self):
        """根据 transparent_bg 设置标题栏背景样式"""
        if self.config.get("transparent_bg", False):
            self.title_bar.setStyleSheet("background-color: transparent; border-radius: 6px;")
        else:
            self.title_bar.setStyleSheet("background-color: rgba(40, 40, 40, 230); border-radius: 6px;")

    def _load_pin_icon(self, filled: bool, color: str) -> QIcon:
        """加载 SVG pin 图标并渲染为 QIcon"""
        svg_name = "pin-fill.svg" if filled else "pin.svg"
        svg_path = os.path.join(self._get_assets_dir(), "svg", svg_name)
        if not os.path.exists(svg_path):
            # 回退：用 emoji 文本
            pixmap = QPixmap(18, 18)
            pixmap.fill(Qt.GlobalColor.transparent)
            return QIcon(pixmap)

        with open(svg_path, "r", encoding="utf-8") as f:
            svg_data = f.read()

        # 在 <path> 中注入 fill/stroke 颜色
        if filled:
            svg_data = svg_data.replace("<path", f'<path fill="{color}" stroke="none"')
        else:
            svg_data = svg_data.replace("<path", f'<path fill="none" stroke="{color}" stroke-width="80"')

        renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _load_svg_icon(self, svg_name: str, fill_color: str) -> QIcon:
        """加载任意 SVG 图标，注入填充色并渲染为 QIcon"""
        svg_path = os.path.join(self._get_assets_dir(), "svg", svg_name)
        if not os.path.exists(svg_path):
            return QIcon()

        with open(svg_path, "r", encoding="utf-8") as f:
            svg_data = f.read()

        # 替换所有硬编码的 fill 属性
        import re
        svg_data = re.sub(r'fill="[^"]*"', f'fill="{fill_color}"', svg_data)
        svg_data = re.sub(r'stroke="[^"]*"', 'stroke="none"', svg_data)

        renderer = QSvgRenderer(QByteArray(svg_data.encode("utf-8")))
        pixmap = QPixmap(18, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _update_pin_button_style(self):
        """更新置顶按钮图标和样式"""
        is_pinned = self.config.get("always_on_top", True)
        self.btn_pin.setStyleSheet("""
            QPushButton {
                background: transparent; border: none;
            }
        """)
        if is_pinned:
            icon = self._load_pin_icon(filled=True, color="#E0E0E0")
            self.btn_pin.setIcon(icon)
            self.btn_pin.setIconSize(self.btn_pin.size())
            self.btn_pin.setToolTip("已置顶 - 点击取消")
        else:
            icon = self._load_pin_icon(filled=False, color="#666666")
            self.btn_pin.setIcon(icon)
            self.btn_pin.setIconSize(self.btn_pin.size())
            self.btn_pin.setToolTip("未置顶 - 点击置顶")

    def _toggle_pin(self):
        """切换窗口置顶"""
        self.config["always_on_top"] = not self.config.get("always_on_top", True)
        save_config(self.config)
        self._apply_window_flags()
        self._update_pin_button_style()

    def eventFilter(self, obj, event):
        """事件过滤器，处理按钮 hover 效果"""
        # 用 getattr 避免按钮尚未创建时的访问错误
        btn_pin = getattr(self, 'btn_pin', None)
        btn_settings = getattr(self, 'btn_settings', None)

        if obj is btn_pin:
            is_pinned = self.config.get("always_on_top", True)
            if event.type() == event.Type.Enter:
                if is_pinned:
                    icon = self._load_pin_icon(filled=True, color="#FFFFFF")
                else:
                    icon = self._load_pin_icon(filled=False, color="#AAAAAA")
                self.btn_pin.setIcon(icon)
                self.btn_pin.setIconSize(self.btn_pin.size())
            elif event.type() == event.Type.Leave:
                if is_pinned:
                    icon = self._load_pin_icon(filled=True, color="#E0E0E0")
                else:
                    icon = self._load_pin_icon(filled=False, color="#666666")
                self.btn_pin.setIcon(icon)
                self.btn_pin.setIconSize(self.btn_pin.size())
        elif obj is btn_settings:
            if event.type() == event.Type.Enter:
                self.btn_settings.setIcon(self._load_svg_icon("setting.svg", "#FFFFFF"))
                self.btn_settings.setIconSize(self.btn_settings.size())
            elif event.type() == event.Type.Leave:
                self.btn_settings.setIcon(self._load_svg_icon("setting.svg", "#AAAAAA"))
                self.btn_settings.setIconSize(self.btn_settings.size())
        return super().eventFilter(obj, event)

    def _quit(self):
        """退出程序"""
        # 保存窗口位置
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()
        save_config(self.config)

        # 停止所有定时器
        self.timer_realtime.stop()
        self.timer_intraday.stop()
        self.timer_supplementary.stop()

        # 隐藏托盘图标
        self.tray.hide()

        # 彻底退出（强制终止进程，释放文件锁）
        QApplication.instance().quit()
        os._exit(0)

    def mousePressEvent(self, event):
        """支持拖拽"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """拖拽移动"""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        """释放拖拽，保存位置"""
        if self._drag_pos is not None:
            self._drag_pos = None
            self.config["window_x"] = self.x()
            self.config["window_y"] = self.y()
            save_config(self.config)
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        """关闭时最小化到托盘"""
        event.ignore()
        self.hide()

    def contextMenuEvent(self, event):
        """右键菜单"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2B2B2B; color: #E0E0E0;
                border: 1px solid #555;
            }
            QMenu::item:selected { background-color: #444; }
        """)

        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        for stock in self.stocks:
            remove_action = QAction(f"删除 {stock.name}({stock.code})", self)
            remove_action.triggered.connect(lambda checked, s=stock: self._remove_stock(s))
            menu.addAction(remove_action)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())

    def _remove_stock(self, stock):
        """删除股票"""
        # 从列表中移除
        self.stocks = [s for s in self.stocks if s is not stock]
        self.config["stocks"] = [s for s in self.config["stocks"] if s["code"] != stock.code]
        save_config(self.config)

        # 重建UI
        self._create_stock_rows()

    def paintEvent(self, event):
        """绘制窗口背景（半透明或透明模式）"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.config.get("transparent_bg", False):
            # 透明模式：仅绘制细边框，不填充背景
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawRoundedRect(self.rect(), 6, 6)
        else:
            # 默认半透明模式：绘制圆角矩形背景
            painter.setBrush(QColor(30, 30, 30, 230))
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawRoundedRect(self.rect(), 6, 6)
        painter.end()
