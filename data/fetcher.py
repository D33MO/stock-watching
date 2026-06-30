"""
股票数据获取模块
- 实时行情：新浪财经HTTP API（免费，无需API Key）
- 分时数据：akshare（当日分钟级）
- 历史K线：akshare
"""

import requests
import re
import time
import traceback
from datetime import datetime, timedelta
from typing import Optional
import akshare as ak


class StockData:
    """单只股票的数据"""

    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name
        self.current_price: float = 0.0
        self.open_price: float = 0.0
        self.close_price: float = 0.0  # 昨收
        self.high_price: float = 0.0
        self.low_price: float = 0.0
        self.change: float = 0.0
        self.change_pct: float = 0.0
        self.volume: int = 0           # 成交量（手）
        self.turnover: float = 0.0     # 成交额（元）
        self.volume_ratio: float = 0.0  # 量比（东方财富，每3分钟更新）
        self.turnover_rate: float = 0.0 # 换手率 %（东方财富，每3分钟更新）
        self.kline_data: list = []  # [(date, open, close, high, low), ...]
        self.intraday_data: list = []  # [(time_str, price), ...]
        self.last_update: float = 0
        self.error: str = ""


def get_market_prefix(code: str) -> str:
    """根据股票代码判断市场前缀（新浪API用）"""
    if code.startswith(("6", "9")):
        return "sh"
    else:
        return "sz"


def fetch_realtime(stock: StockData) -> bool:
    """通过新浪财经API获取实时行情"""
    try:
        prefix = get_market_prefix(stock.code)
        symbol = f"{prefix}{stock.code}"
        url = f"https://hq.sinajs.cn/list={symbol}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        # 解析返回数据
        # 格式: var hq_str_sh600519="贵州茅台,开盘,昨收,当前,最高,最低,...";
        match = re.search(r'"(.+)"', text)
        if not match:
            stock.error = "无法解析数据"
            return False

        fields = match.group(1).split(",")
        if len(fields) < 32:
            stock.error = "数据字段不足"
            return False

        stock.name = fields[0] if fields[0] else stock.name
        stock.open_price = float(fields[1]) if fields[1] else 0
        stock.close_price = float(fields[2]) if fields[2] else 0
        stock.current_price = float(fields[3]) if fields[3] else 0
        stock.high_price = float(fields[4]) if fields[4] else 0
        stock.low_price = float(fields[5]) if fields[5] else 0
        stock.volume = int(float(fields[8])) if len(fields) > 8 and fields[8] else 0
        stock.turnover = float(fields[9]) if len(fields) > 9 and fields[9] else 0.0

        if stock.close_price > 0:
            stock.change = stock.current_price - stock.close_price
            stock.change_pct = (stock.change / stock.close_price) * 100

        stock.error = ""
        stock.last_update = time.time()
        return True

    except Exception as e:
        stock.error = f"获取失败: {str(e)}"
        return False


def fetch_kline(stock: StockData, days: int = 30) -> bool:
    """通过akshare获取历史K线数据"""
    try:
        # 判断市场
        if stock.code.startswith(("6", "9")):
            symbol = f"sh{stock.code}"
        else:
            symbol = f"sz{stock.code}"

        # 使用akshare获取日K线
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(
            symbol=stock.code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"
        )

        if df is None or df.empty:
            stock.error = "K线数据为空"
            return False

        # 取最近N个交易日
        df = df.tail(days)
        stock.kline_data = []
        for _, row in df.iterrows():
            stock.kline_data.append((
                str(row["日期"]),
                float(row["开盘"]),
                float(row["收盘"]),
                float(row["最高"]),
                float(row["最低"]),
            ))

        stock.error = ""
        return True

    except Exception as e:
        stock.error = f"K线获取失败: {str(e)}"
        traceback.print_exc()
        return False


def fetch_stock_name(code: str) -> str:
    """通过股票代码获取股票名称（新浪财经API）"""
    try:
        prefix = get_market_prefix(code)
        url = f"https://hq.sinajs.cn/list={prefix}{code}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        # 格式: var hq_str_sh600519="贵州茅台,开盘,昨收,...";
        match = re.search(r'"(.+)"', text)
        if match:
            fields = match.group(1).split(",")
            if fields[0]:
                return fields[0].strip()
    except Exception:
        traceback.print_exc()

    return ""


def fetch_intraday(stock: StockData) -> bool:
    """通过新浪财经获取当日分时数据（1分钟级别）"""
    try:
        # 使用新浪的分钟数据接口（比东方财富更稳定）
        prefix = "sh" if stock.code.startswith(("6", "9")) else "sz"
        symbol = f"{prefix}{stock.code}"
        df = ak.stock_zh_a_minute(
            symbol=symbol,
            period="1",
            adjust="",
        )

        if df is None or df.empty:
            stock.error = "分时数据为空"
            return False

        # 只取今天的数据
        today_str = datetime.now().strftime("%Y-%m-%d")
        df["day"] = df["day"].astype(str)

        # 过滤出今天的分时数据
        today_data = df[df["day"].str.startswith(today_str)]

        if today_data.empty:
            # 可能还没开盘或已收盘，取最后的数据
            today_data = df.tail(242)  # A股一天最多242根分钟线

        stock.intraday_data = []
        for _, row in today_data.iterrows():
            time_str = str(row["day"])
            # 提取时:分 部分
            if " " in time_str:
                time_part = time_str.split(" ")[1][:5]
            else:
                time_part = time_str
            price = float(row["close"])
            stock.intraday_data.append((time_part, price))

        stock.error = ""
        return True

    except Exception as e:
        stock.error = f"分时获取失败: {str(e)}"
        traceback.print_exc()
        return False


def fetch_supplementary(stocks: list[StockData]) -> bool:
    """
    从腾讯财经获取补充数据（量比、换手率）。
    使用 qt.gtimg.cn 接口，比东方财富更稳定。
    建议每3分钟调用一次。
    """
    if not stocks:
        return False
    try:
        # 批量查询，用 ; 拼接多个股票
        symbols = []
        code_to_stock = {}
        for stock in stocks:
            prefix = "sh" if stock.code.startswith(("6", "9")) else "sz"
            sym = f"{prefix}{stock.code}"
            symbols.append(sym)
            code_to_stock[sym] = stock

        url = f"https://qt.gtimg.cn/q={';'.join(symbols)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gbk"
        text = resp.text.strip()

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # 格式: v_sh600519="...";
            match = re.search(r'v_([a-z]{2}\d+)="(.+)"', line)
            if not match:
                continue
            sym = match.group(1)
            fields = match.group(2).split("~")
            # fields[39] = 换手率(%), fields[46] = 量比
            stock = code_to_stock.get(sym)
            if stock is None:
                continue
            if len(fields) > 46:
                try:
                    tr = float(fields[39]) if fields[39] else 0.0
                    vr = float(fields[46]) if fields[46] else 0.0
                    stock.turnover_rate = tr
                    stock.volume_ratio = vr
                except (ValueError, IndexError):
                    pass

        return True

    except Exception as e:
        print(f"补充数据获取失败: {e}")
        traceback.print_exc()
        return False
