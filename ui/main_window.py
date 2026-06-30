"""
主窗口模块
无边框、置顶、半透明、可拖拽的悬浮窗
"""

import json
import os
import sys
import winreg
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSystemTrayIcon, QMenu, QApplication,
    QMessageBox, QInputDialog, QDialog, QLineEdit,
    QPushButton, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QAction, QIcon, QPixmap

from data.fetcher import StockData, fetch_realtime, fetch_kline, fetch_intraday
from ui.stock_widget import StockRow
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
        "refresh_interval": 5,
        "window_x": 0,
        "window_y": 800,
        "opacity": 0.9,
        "auto_start": False,
        "always_on_top": True,
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


class MainWindow(QMainWindow):
    """主悬浮窗"""

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.stocks: list[StockData] = []
        self.stock_rows: list[StockRow] = []
        self._drag_pos = None

        self._init_stocks()
        self._setup_ui()
        self._setup_tray()
        self._setup_timers()

        # 加载分时数据（后台）
        QTimer.singleShot(500, self._load_all_intraday)

    def _init_stocks(self):
        """初始化股票列表"""
        for item in self.config.get("stocks", []):
            self.stocks.append(StockData(item["code"], item.get("name", item["code"])))

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
        self.setWindowTitle("股票监控")
        self._apply_window_flags()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 主容器
        self.central_widget = QWidget()
        self.central_widget.setStyleSheet("""
            QWidget#container {
                background-color: rgba(30, 30, 30, 230);
                border: 1px solid #444;
                border-radius: 6px;
            }
        """)
        self.central_widget.setObjectName("container")

        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)

        # 标题栏
        title_bar = QWidget()
        title_bar.setFixedHeight(24)
        title_bar.setStyleSheet("background-color: rgba(40, 40, 40, 230); border-radius: 6px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 0, 4, 0)

        title_label = QLabel("📊 股票监控")
        title_label.setStyleSheet("color: #AAAAAA; font-size: 11px; font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        # 设置按钮
        btn_settings = QPushButton("⚙")
        btn_settings.setFixedSize(20, 18)
        btn_settings.setStyleSheet("""
            QPushButton {
                color: #AAAAAA; font-size: 13px; font-weight: bold;
                background: transparent; border: none;
            }
            QPushButton:hover { color: #FFFFFF; }
        """)
        btn_settings.setToolTip("设置")
        btn_settings.clicked.connect(self._open_settings)
        title_layout.addWidget(btn_settings)

        # 置顶按钮
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setFixedSize(20, 18)
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

        main_layout.addWidget(title_bar)

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

        for stock in self.stocks:
            row = StockRow(stock)
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
        w = 400

        x = self.config.get("window_x", 0)
        y = self.config.get("window_y", 800)

        # 先调整到屏幕合适位置
        self.setFixedSize(w, total_h)
        self.move(x, y)

    def _setup_tray(self):
        """设置系统托盘"""
        # 创建一个简单的图标
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(220, 50, 50))
        icon = QIcon(pixmap)

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("股票监控")

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

        # 启动时立即刷新一次
        QTimer.singleShot(100, self._refresh_realtime)

    def _refresh_realtime(self):
        """刷新所有股票的实时行情"""
        for stock in self.stocks:
            fetch_realtime(stock)

        # 更新UI
        for row in self.stock_rows:
            row.update_display()

    def _refresh_intraday(self):
        """刷新所有股票的分时数据"""
        for stock in self.stocks:
            fetch_intraday(stock)

        for row in self.stock_rows:
            row.update_display()

    def _load_all_intraday(self):
        """加载所有股票的分时数据（首次）"""
        for stock in self.stocks:
            fetch_intraday(stock)

        for row in self.stock_rows:
            row.update_display()

    def _open_settings(self):
        """打开设置窗口"""
        dialog = SettingsDialog(
            stocks_config=self.config.get("stocks", []),
            refresh_interval=self.config.get("refresh_interval", 5),
            auto_start=self.config.get("auto_start", False),
            always_on_top=self.config.get("always_on_top", True),
            parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_stocks = dialog.get_stocks_config()
            new_interval = dialog.get_refresh_interval()
            new_auto_start = dialog.get_auto_start()
            new_always_on_top = dialog.get_always_on_top()

            # 记录旧值用于比较
            old_always_on_top = self.config.get("always_on_top", True)

            # 更新配置
            self.config["stocks"] = new_stocks
            self.config["refresh_interval"] = new_interval
            self.config["auto_start"] = new_auto_start
            self.config["always_on_top"] = new_always_on_top
            save_config(self.config)

            # 应用开机自启动设置
            set_auto_start(new_auto_start)

            # 应用窗口置顶设置（仅在变化时切换）
            if new_always_on_top != old_always_on_top:
                self._apply_window_flags()
                self.show()

            # 重建股票列表
            self._rebuild_stocks()

            # 更新刷新间隔
            interval_ms = new_interval * 1000
            self.timer_realtime.start(interval_ms)

    def _rebuild_stocks(self):
        """根据配置重建股票列表"""
        # 清除旧的
        for row in self.stock_rows:
            row.setParent(None)
            row.deleteLater()
        self.stock_rows.clear()
        self.stocks.clear()

        # 重新初始化
        for item in self.config.get("stocks", []):
            self.stocks.append(StockData(item["code"], item.get("name", item["code"])))

        # 重建行
        for stock in self.stocks:
            row = StockRow(stock)
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

    def _update_pin_button_style(self):
        """更新置顶按钮样式"""
        is_pinned = self.config.get("always_on_top", True)
        if is_pinned:
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    color: #FFD700; font-size: 11px;
                    background: transparent; border: none;
                }
                QPushButton:hover { color: #FFA500; }
            """)
            self.btn_pin.setToolTip("已置顶 - 点击取消")
        else:
            self.btn_pin.setStyleSheet("""
                QPushButton {
                    color: #666666; font-size: 11px;
                    background: transparent; border: none;
                }
                QPushButton:hover { color: #FFFFFF; }
            """)
            self.btn_pin.setToolTip("未置顶 - 点击置顶")

    def _toggle_pin(self):
        """切换窗口置顶"""
        self.config["always_on_top"] = not self.config.get("always_on_top", True)
        save_config(self.config)
        self._apply_window_flags()
        self._update_pin_button_style()

    def _quit(self):
        """退出程序"""
        # 保存窗口位置
        self.config["window_x"] = self.x()
        self.config["window_y"] = self.y()
        save_config(self.config)
        self.tray.hide()
        QApplication.instance().quit()

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
        """绘制半透明背景"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制圆角矩形背景
        painter.setBrush(QColor(30, 30, 30, 230))
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawRoundedRect(self.rect(), 6, 6)
        painter.end()
