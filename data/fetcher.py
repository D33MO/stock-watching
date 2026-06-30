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
        self.volume: float = 0.0
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
    """通过股票代码获取股票名称"""
    try:
        # 方法1：stock_individual_info_em
        df = ak.stock_individual_info_em(symbol=code)
        if df is not None and not df.empty:
            # 找到股票名称行
            name_row = df[df["item"] == "股票简称"]
            if not name_row.empty:
                result = str(name_row.iloc[0]["value"])
                if result and result != code:
                    return result
    except Exception:
        traceback.print_exc()

    try:
        # 方法2：stock_info_a_code_name
        df2 = ak.stock_info_a_code_name()
        if df2 is not None and not df2.empty:
            match_row = df2[df2["code"] == code]
            if not match_row.empty:
                result = str(match_row.iloc[0]["name"]).strip()
                # 去掉末尾的X/x
                while result.endswith("X") or result.endswith("x"):
                    result = result[:-1]
                if result and result != code:
                    return result
    except Exception:
        traceback.print_exc()

    return ""


def fetch_intraday(stock: StockData) -> bool:
    """通过akshare获取当日分时数据（1分钟级别）"""
    try:
        # 使用东方财富的分钟级数据
        df = ak.stock_zh_a_hist_min_em(
            symbol=stock.code,
            period="1",
            adjust="",
        )

        if df is None or df.empty:
            stock.error = "分时数据为空"
            return False

        # 只取今天的数据
        today_str = datetime.now().strftime("%Y-%m-%d")
        df["时间"] = df["时间"].astype(str)

        # 过滤出今天的分时数据
        today_data = df[df["时间"].str.startswith(today_str)]

        if today_data.empty:
            # 可能还没开盘或已收盘，取最后的数据
            today_data = df.tail(242)  # A股一天最多242根分钟线

        stock.intraday_data = []
        for _, row in today_data.iterrows():
            time_str = str(row["时间"])
            # 提取时:分 部分
            if " " in time_str:
                time_part = time_str.split(" ")[1][:5]
            else:
                time_part = time_str
            price = float(row["收盘"])
            stock.intraday_data.append((time_part, price))

        stock.error = ""
        return True

    except Exception as e:
        stock.error = f"分时获取失败: {str(e)}"
        traceback.print_exc()
        return False
