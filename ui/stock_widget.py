"""
单只股票行组件
一行显示：股票名称 | 代码 | 现价 | 涨跌幅 | 迷你分时图
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPolygonF

from data.fetcher import StockData


class MiniIntradayChart(QWidget):
    """迷你分时图组件"""

    def __init__(self, parent=None, width=180, height=28):
        super().__init__(parent)
        self.setFixedWidth(width)
        self.setFixedHeight(height)
        self.intraday_data = []  # [(time_str, price), ...]
        self.close_price = 0.0   # 昨收价（基准线）

    def set_intraday_data(self, data, close_price=0.0):
        self.intraday_data = data
        self.close_price = close_price
        self.update()

    def paintEvent(self, event):
        if not self.intraday_data:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(80, 80, 80), 1))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "加载中...")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin_x = 3
        margin_y = 2
        draw_w = w - 2 * margin_x
        draw_h = h - 2 * margin_y

        prices = [p for _, p in self.intraday_data]
        if not prices:
            painter.end()
            return

        max_price = max(prices)
        min_price = min(prices)

        # 以昨收价为中心，确保涨跌区域对称
        if self.close_price > 0:
            ref = self.close_price
            diff = max(abs(max_price - ref), abs(min_price - ref))
            max_price = ref + diff
            min_price = ref - diff

        price_range = max_price - min_price
        if price_range <= 0:
            price_range = 1

        # 增加上下边距
        price_margin = price_range * 0.05
        max_price += price_margin
        min_price -= price_margin
        price_range = max_price - min_price

        n = len(self.intraday_data)
        gap = draw_w / max(n - 1, 1)

        # 画昨收基准虚线
        if self.close_price > 0:
            y_ref = margin_y + (1 - (self.close_price - min_price) / price_range) * draw_h
            pen_ref = QPen(QColor(120, 120, 120), 1)
            pen_ref.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen_ref)
            painter.drawLine(QPointF(margin_x, y_ref), QPointF(w - margin_x, y_ref))

        # 构建折线点
        all_points = []

        for i, (_, price) in enumerate(self.intraday_data):
            x = margin_x + i * gap
            y = margin_y + (1 - (price - min_price) / price_range) * draw_h
            pt = QPointF(x, y)
            all_points.append(pt)

        # 填充区域颜色
        if self.close_price > 0:
            ref_y = margin_y + (1 - (self.close_price - min_price) / price_range) * draw_h
        else:
            ref_y = h / 2

        # 画走势折线和区域填充
        if len(all_points) >= 2:
            # 判断涨跌趋势（最后价格 vs 基准）
            is_up = all_points[-1].y() <= ref_y if self.close_price > 0 else True

            # 折线颜色
            if is_up:
                line_color = QColor(220, 50, 50)    # 红色
                fill_color = QColor(220, 50, 50, 30)  # 半透明红色
            else:
                line_color = QColor(50, 180, 50)    # 绿色
                fill_color = QColor(50, 180, 50, 30)  # 半透明绿色

            # 画填充区域
            fill_points = QPolygonF(all_points)
            fill_points.append(QPointF(all_points[-1].x(), ref_y))
            fill_points.append(QPointF(all_points[0].x(), ref_y))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawPolygon(fill_points)

            # 画折线
            pen = QPen(line_color, 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(len(all_points) - 1):
                painter.drawLine(all_points[i], all_points[i + 1])

        painter.end()


class StockRow(QWidget):
    """单只股票行：名称 | 代码 | 现价 | 涨跌幅 | 迷你分时图"""

    clicked = pyqtSignal(str)  # 点击信号，传递股票代码

    def __init__(self, stock_data: StockData, parent=None):
        super().__init__(parent)
        self.stock_data = stock_data
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(6)

        # 股票名称
        self.label_name = QLabel(self.stock_data.name)
        self.label_name.setFixedWidth(70)
        self.label_name.setStyleSheet("color: #E0E0E0; font-size: 12px;")
        font = QFont("Microsoft YaHei", 10, QFont.Weight.Bold)
        self.label_name.setFont(font)

        # 股票代码
        self.label_code = QLabel(self.stock_data.code)
        self.label_code.setFixedWidth(55)
        self.label_code.setStyleSheet("color: #999999; font-size: 11px;")

        # 现价
        self.label_price = QLabel("--")
        self.label_price.setFixedWidth(70)
        self.label_price.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: bold;")
        self.label_price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 涨跌幅
        self.label_change = QLabel("--")
        self.label_change.setFixedWidth(65)
        self.label_change.setStyleSheet("color: #999999; font-size: 11px;")
        self.label_change.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # 迷你分时图
        self.mini_chart = MiniIntradayChart(width=90, height=40)

        layout.addWidget(self.label_name)
        layout.addWidget(self.label_code)
        layout.addWidget(self.label_price)
        layout.addWidget(self.label_change)
        layout.addWidget(self.mini_chart)

        self.setFixedHeight(56)

    def update_display(self):
        """更新显示数据"""
        s = self.stock_data

        # 更新价格
        if s.current_price > 0:
            self.label_price.setText(f"{s.current_price:.2f}")
        else:
            self.label_price.setText("--")

        # 更新涨跌幅
        if s.current_price > 0 and s.close_price > 0:
            sign = "+" if s.change_pct >= 0 else ""
            self.label_change.setText(f"{sign}{s.change_pct:.2f}%")

            # 颜色
            if s.change_pct > 0:
                color = "#FF4444"  # 红色
            elif s.change_pct < 0:
                color = "#44BB44"  # 绿色
            else:
                color = "#999999"
            self.label_change.setStyleSheet(f"color: {color}; font-size: 11px;")
            self.label_price.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold;")
        else:
            self.label_change.setText("--")
            self.label_change.setStyleSheet("color: #999999; font-size: 11px;")
            self.label_price.setStyleSheet("color: #999999; font-size: 12px;")

        # 更新分时图
        if s.intraday_data:
            self.mini_chart.set_intraday_data(s.intraday_data, s.close_price)

    def mousePressEvent(self, event):
        self.clicked.emit(self.stock_data.code)
        super().mousePressEvent(event)
