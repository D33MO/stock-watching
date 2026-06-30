"""
股票监控 - 主程序入口
A股实时行情 + 迷你K线图悬浮窗
"""

import sys
import os

# 确保项目根目录在路径中
if getattr(sys, 'frozen', False):
    # 打包后
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_dir)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow


def main():
    # 高DPI支持
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

    app = QApplication(sys.argv)

    # 设置默认字体
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    # 设置应用程序图标（优先使用 ico 格式，打包后 Windows 显示更清晰）
    icon_ico = os.path.join(base_dir, "logo.ico")
    icon_png = os.path.join(base_dir, "logo.png")
    if os.path.exists(icon_ico):
        app.setWindowIcon(QIcon(icon_ico))
    elif os.path.exists(icon_png):
        app.setWindowIcon(QIcon(icon_png))

    # 设置应用信息
    app.setApplicationName("股票监控")
    app.setOrganizationName("StockWatching")

    # 创建主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
