"""
单只股票行组件
一行显示：股票名称 | 可选字段（现价/涨跌幅/成交量/...） | 迷你分时图
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPolygonF

from data.fetcher import StockData


# ===== 字段定义 =====
# 实时字段（从新浪API获取，~3秒刷新）
REALTIME_FIELDS = {
    "price":      {"label": "现价",   "group": "realtime"},
    "change_pct": {"label": "涨跌幅", "group": "realtime"},
    "change":     {"label": "涨跌额", "group": "realtime"},
    "volume":     {"label": "成交量", "group": "realtime"},
    "turnover":   {"label": "成交额", "group": "realtime"},
    "high":       {"label": "最高",   "group": "realtime"},
    "low":        {"label": "最低",   "group": "realtime"},
}

# 补充字段（从东方财富获取，~3分钟更新）
SUPPLEMENTARY_FIELDS = {
    "volume_ratio":  {"label": "量比",   "group": "supplementary"},
    "turnover_rate": {"label": "换手率", "group": "supplementary"},
}

# 合并所有字段
ALL_FIELD_SPECS = {}
ALL_FIELD_SPECS.update(REALTIME_FIELDS)
ALL_FIELD_SPECS.update(SUPPLEMENTARY_FIELDS)

# 涨跌颜色相关的字段
CHANGE_COLORED_FIELDS = {"price", "change_pct", "change"}

ALL_FIELD_WIDTH = 70  # 所有字段统一宽度


def format_volume(val: int) -> str:
    """格式化成交量（手 → 万手/亿手）"""
    if val <= 0:
        return "--"
    if val >= 100000000:
        return f"{val / 100000000:.2f}亿"
    if val >= 10000:
        return f"{val / 10000:.2f}万"
    return f"{val}手"


def format_turnover(val: float) -> str:
    """格式化成交额（元 → 万/亿）"""
    if val <= 0:
        return "--"
    if val >= 100000000:
        return f"{val / 100000000:.2f}亿"
    if val >= 10000:
        return f"{val / 10000:.2f}万"
    return f"{val:.0f}元"


# ===== 迷你分时图 =====

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


# ===== 股票行 =====

class StockRow(QWidget):
    """单只股票行：名称 | 可选字段 | 迷你分时图"""

    clicked = pyqtSignal(str)  # 点击信号，传递股票代码

    def __init__(self, stock_data: StockData, display_fields: list[str] = None, parent=None):
        super().__init__(parent)
        self.stock_data = stock_data
        self.display_fields = display_fields or ["price", "change_pct", "intraday"]
        self.field_labels: dict[str, QLabel] = {}  # field_key -> QLabel
        self.chart_widget: MiniIntradayChart | None = None
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

        layout.addWidget(self.label_name)

        # 动态字段
        for field_key in self.display_fields:
            if field_key == "intraday":
                self.chart_widget = MiniIntradayChart(width=90, height=40)
                layout.addWidget(self.chart_widget)
            elif field_key in ALL_FIELD_SPECS:
                label = QLabel("--")
                label.setFixedWidth(ALL_FIELD_WIDTH)
                label.setStyleSheet("color: #E0E0E0; font-size: 11px;")
                label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.field_labels[field_key] = label
                layout.addWidget(label)

        self.setFixedHeight(56)

    def rebuild(self, display_fields: list[str]):
        """重建显示字段布局（设置保存后调用）"""
        self.display_fields = display_fields
        self.field_labels.clear()
        self.chart_widget = None

        # 清除旧布局
        old_layout = self.layout()
        if old_layout:
            # 删除旧布局中的所有 widget
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            # 删除旧布局本身（但 QWidget.setLayout 会自动处理）
            # 直接删除再重建

        new_layout = QHBoxLayout(self)
        new_layout.setContentsMargins(8, 3, 8, 3)
        new_layout.setSpacing(6)

        # 重新添加名称
        new_layout.addWidget(self.label_name)

        # 动态字段
        for field_key in self.display_fields:
            if field_key == "intraday":
                self.chart_widget = MiniIntradayChart(width=90, height=40)
                new_layout.addWidget(self.chart_widget)
            elif field_key in ALL_FIELD_SPECS:
                label = QLabel("--")
                label.setFixedWidth(ALL_FIELD_WIDTH)
                label.setStyleSheet("color: #E0E0E0; font-size: 11px;")
                label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.field_labels[field_key] = label
                new_layout.addWidget(label)

        # 更新显示
        self.update_display()

    def update_display(self):
        """更新所有字段的显示"""
        s = self.stock_data

        # 涨跌颜色
        if s.change_pct > 0:
            up_color = "#FF4444"
            dn_color = "#FF4444"
            neutral_color = "#E0E0E0"
        elif s.change_pct < 0:
            up_color = "#44BB44"
            dn_color = "#44BB44"
            neutral_color = "#E0E0E0"
        else:
            up_color = "#E0E0E0"
            dn_color = "#E0E0E0"
            neutral_color = "#E0E0E0"

        colored = s.current_price > 0 and s.close_price > 0

        for field_key, label in self.field_labels.items():
            text = "--"
            color = neutral_color

            if field_key == "price":
                if s.current_price > 0:
                    text = f"{s.current_price:.2f}"
                    color = up_color if s.change_pct >= 0 else dn_color if colored else neutral_color
                else:
                    text = "--"

            elif field_key == "change_pct":
                if colored:
                    text = f"{s.change_pct:+.2f}%"
                    color = up_color if s.change_pct >= 0 else dn_color
                else:
                    text = "--"

            elif field_key == "change":
                if colored:
                    text = f"{s.change:+.2f}"
                    color = up_color if s.change_pct >= 0 else dn_color
                else:
                    text = "--"

            elif field_key == "volume":
                text = format_volume(s.volume)

            elif field_key == "turnover":
                text = format_turnover(s.turnover)

            elif field_key == "high":
                text = f"{s.high_price:.2f}" if s.high_price > 0 else "--"

            elif field_key == "low":
                text = f"{s.low_price:.2f}" if s.low_price > 0 else "--"

            elif field_key == "volume_ratio":
                text = f"{s.volume_ratio:.2f}" if s.volume_ratio > 0 else "--"

            elif field_key == "turnover_rate":
                text = f"{s.turnover_rate:.2f}%" if s.turnover_rate > 0 else "--"

            label.setText(text)
            if field_key in CHANGE_COLORED_FIELDS and colored:
                label.setStyleSheet(f"color: {color}; font-size: 11px;")
            else:
                label.setStyleSheet("color: #E0E0E0; font-size: 11px;")

        # 更新分时图
        if self.chart_widget and s.intraday_data:
            self.chart_widget.set_intraday_data(s.intraday_data, s.close_price)

    def mousePressEvent(self, event):
        self.clicked.emit(self.stock_data.code)
        super().mousePressEvent(event)
