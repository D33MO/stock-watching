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
    """单个品种的数据（股票/期货）"""

    def __init__(self, code: str, name: str, instrument_type: str = "stock"):
        self.code = code
        self.name = name
        self.instrument_type = instrument_type  # "stock" 或 "futures"
        self.current_price: float = 0.0
        self.open_price: float = 0.0
        self.close_price: float = 0.0  # 昨收（股票）/ 昨结算（期货）
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

        # 期货特有字段
        self.last_settlement: float = 0.0   # 昨结算价（期货涨跌基准）
        self.open_interest: int = 0          # 持仓量（手）
        self.main_contract_symbol: str = ""  # 主力合约代码，如 "CU2409"


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
        df = None

        # 重试机制（新浪API偶尔超时）
        for attempt in range(3):
            try:
                df = ak.stock_zh_a_minute(
                    symbol=symbol,
                    period="1",
                    adjust="",
                )
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise

        if df is None or df.empty:
            stock.error = "分时数据为空"
            return False

        # 检查是否包含 "day" 列
        if "day" not in df.columns:
            stock.error = "分时数据格式异常"
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
        print(f"[INFO] 分时获取失败（{stock.code}）: {e}")
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
            if stock.instrument_type == "futures":
                continue  # 期货没有量比和换手率
            prefix = "sh" if stock.code.startswith(("6", "9")) else "sz"
            sym = f"{prefix}{stock.code}"
            symbols.append(sym)
            code_to_stock[sym] = stock

        if not symbols:
            return True

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


# ============================================================
# 期货数据获取
# ============================================================

# 常用期货代码 → 中文名称映射
FUTURES_NAME_MAP = {
    "CU": "沪铜", "RB": "螺纹钢", "MA": "甲醇", "SC": "原油",
    "AU": "黄金", "AG": "白银", "AL": "铝", "ZN": "锌",
    "PB": "铅", "RU": "橡胶", "BU": "沥青", "FU": "燃料油",
    "TA": "PTA", "CF": "棉花", "SR": "白糖", "OI": "菜油",
    "RM": "菜粕", "FG": "玻璃", "SA": "纯碱", "V": "PVC",
    "I": "铁矿石", "J": "焦炭", "JM": "焦煤", "HC": "热卷",
    "P": "棕榈油", "Y": "豆油", "M": "豆粕",
    "A": "豆一", "B": "豆二", "C": "玉米", "CS": "淀粉",
    "PP": "聚丙烯", "L": "聚乙烯", "EG": "乙二醇", "PF": "短纤",
    "PK": "花生", "AP": "苹果", "CJ": "红枣", "UR": "尿素",
    "SF": "硅铁", "SM": "锰硅", "CY": "棉纱",
    "LH": "生猪", "JD": "鸡蛋", "RR": "粳米",
    "EB": "苯乙烯", "PG": "液化气", "BZ": "苯",
    "PX": "对二甲苯", "SH": "烧碱", "PR": "瓶片", "PL": "聚氯乙烯",
}


def fetch_futures_main_contract(code: str) -> tuple[str, str]:
    """
    获取期货主力合约代码和名称。
    返回 (main_contract_symbol, full_name)，如 ("CU2409", "沪铜2409")
    失败返回 ("", "")
    """
    try:
        df = ak.futures_display_main_sina()
        # 查找匹配的品种（code 是 symbol 去掉末尾 0）
        row = df[df["symbol"].str.upper() == f"{code.upper()}0"]
        if row.empty:
            # 尝试精确匹配 symbol
            row = df[df["symbol"].str.upper() == code.upper()]
        if row.empty:
            return "", ""

        symbol = row.iloc[0]["symbol"]  # 如 "CU0"
        name = row.iloc[0]["name"]       # 如 "铜主力"

        # 用 futures_main_sina 获取主力合约历史（包含具体合约代码）
        hist = ak.futures_main_sina(symbol=symbol, start_date="20200101", end_date="22220101")
        if hist is not None and not hist.empty:
            # 取最近的一条记录，获取合约代码
            last = hist.iloc[-1]
            # 从 DataFrame 的列中找出合约代码
            # 格式：日期、开盘价、最高价、最低价、收盘价、成交量、持仓量、动态盈亏
            cols = hist.columns.tolist()
            # 使用 index 作为合约代码标识
            main_symbol = symbol  # 回退用
            return main_symbol, name

        return symbol, name

    except Exception as e:
        print(f"获取主力合约失败 ({code}): {e}")
        traceback.print_exc()
        return "", ""


def fetch_futures_realtime(stock: StockData) -> bool:
    """
    获取期货实时行情。
    优先使用 akshare（国内期货），hf_ API 仅作为国际期货回退。
    """
    # 1. 优先用 akshare 获取国内期货行情
    if _fetch_futures_realtime_fallback(stock):
        return True

    # 2. 回退：尝试新浪 hf_ API（适用于国际期货）
    try:
        url = f"https://hq.sinajs.cn/list=hf_{stock.code}"
        headers = {
            "Referer": "https://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=5)
        resp.encoding = "gbk"
        text = resp.text.strip()

        match = re.search(r'"(.+)"', text)
        if not match:
            stock.error = "期货数据获取失败"
            return False

        fields = match.group(1).split(",")
        if not fields or len(fields) < 5:
            stock.error = "期货数据字段不足"
            return False

        # Sina hf_ API 格式：
        # 0: 品种名  1: 日期  2: 开盘  3: 最高  4: 最低  5: 收盘
        # 6: 买价  7: 卖价  8: 持仓量  9: 成交量
        stock.open_price = float(fields[2]) if fields[2] else 0.0
        stock.current_price = float(fields[5]) if fields[5] else 0.0
        stock.high_price = float(fields[3]) if fields[3] else 0.0
        stock.low_price = float(fields[4]) if fields[4] else 0.0
        stock.open_interest = int(float(fields[8])) if len(fields) > 8 and fields[8] else 0
        stock.volume = int(float(fields[9])) if len(fields) > 9 and fields[9] else 0

        stock.error = ""
        stock.last_update = time.time()
        return True

    except Exception as e:
        stock.error = f"期货获取失败: {str(e)}"
        return False


def _fetch_futures_realtime_fallback(stock: StockData) -> bool:
    """回退：通过 AKShare 获取期货行情"""
    try:
        # 从合约代码提取品种前缀（如 "CU2409" → "CU"）
        code = stock.code.upper()
        prefix_match = re.match(r'^([A-Z]+)', code)
        prefix = prefix_match.group(1) if prefix_match else code

        # 用中文名查询该品种所有合约
        chinese_name = FUTURES_NAME_MAP.get(prefix, code)
        df = ak.futures_zh_realtime(symbol=chinese_name)
        if df is None or df.empty:
            stock.error = "期货数据为空"
            return False

        # 精确匹配当前合约代码
        candidates = df[df["symbol"].str.upper() == code]
        if candidates.empty:
            # 回退：包含匹配
            candidates = df[df["symbol"].str.upper().str.contains(code, na=False)]
        if candidates.empty:
            stock.error = "未找到匹配的期货数据"
            return False

        row = candidates.iloc[0]

        stock.name = row.get("name", stock.name)
        stock.current_price = float(row.get("trade", 0))
        stock.last_settlement = float(row.get("presettlement", 0))
        stock.close_price = stock.last_settlement
        stock.open_price = float(row.get("open", 0))
        stock.high_price = float(row.get("high", 0))
        stock.low_price = float(row.get("low", 0))
        stock.open_interest = int(float(row.get("position", 0)))
        stock.volume = int(float(row.get("volume", 0)))

        if stock.last_settlement > 0:
            stock.change = stock.current_price - stock.last_settlement
            stock.change_pct = (stock.change / stock.last_settlement) * 100

        stock.main_contract_symbol = str(row.get("symbol", ""))
        stock.error = ""
        stock.last_update = time.time()
        return True

    except Exception as e:
        stock.error = f"期货回退获取失败: {str(e)}"
        traceback.print_exc()
        return False


def fetch_futures_intraday(stock: StockData) -> bool:
    """获取期货分时数据（1分钟级别）"""
    try:
        df = None
        # 依次尝试不同周期，增加获取数据的成功率
        for period in ["1", "5", "15", "30", "60"]:
            try:
                df = ak.futures_zh_minute_sina(symbol=stock.code, period=period)
                if df is not None and not df.empty:
                    break
            except ValueError:
                # akshare 在 API 返回空数据时会抛出 ValueError（列数不匹配）
                continue

        if df is None or df.empty:
            stock.error = "期货分时数据为空（可能处于非交易时段）"
            return False

        # 检查时间列（akshare 不同期货 API 返回不同列名）
        time_col = None
        for col_name in ["datetime", "day"]:
            if col_name in df.columns:
                time_col = col_name
                break
        if time_col is None:
            stock.error = "期货分时数据格式异常"
            return False

        # 只取今天的数据
        today_str = datetime.now().strftime("%Y-%m-%d")
        df[time_col] = df[time_col].astype(str)
        today_data = df[df[time_col].str.startswith(today_str)]

        if today_data.empty:
            today_data = df.tail(300)  # 期货全天最多约300根分钟线

        stock.intraday_data = []
        for _, row in today_data.iterrows():
            time_str = str(row[time_col])
            if " " in time_str:
                time_part = time_str.split(" ")[1][:5]
            else:
                time_part = time_str
            price = float(row["close"])
            stock.intraday_data.append((time_part, price))

        stock.error = ""
        return True

    except Exception as e:
        stock.error = f"期货分时获取失败: {str(e)}"
        traceback.print_exc()
        return False


def fetch_futures_name(code: str) -> str:
    """获取期货品种中文名称
    支持两种格式：
    - 品种代码：CU → 沪铜
    - 完整合约：CU2409 → 沪铜2409
    """
    code = code.upper()
    # 优先从内置映射表获取（品种码如 "CU"）
    if code in FUTURES_NAME_MAP:
        return FUTURES_NAME_MAP[code]

    # 尝试解析完整合约代码（如 "CU2409" → "沪铜2409"）
    match = re.match(r'^([A-Z]+)(\d{4})$', code)
    if match:
        prefix = match.group(1)
        suffix = match.group(2)
        if prefix in FUTURES_NAME_MAP:
            return f"{FUTURES_NAME_MAP[prefix]}{suffix}"

    # 尝试从新浪获取
    try:
        df = ak.futures_display_main_sina()
        row = df[df["symbol"].str.upper() == f"{code}0"]
        if not row.empty:
            return str(row.iloc[0]["name"])
    except Exception:
        pass
    return code
