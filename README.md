# 📊 股票监控 — A股实时行情悬浮窗

一个基于 **PyQt6** 的桌面悬浮窗工具，实时监控 **A股** 和 **期货** 行情，每只品种一行，显示**名称 · 现价 · 涨跌幅 · 迷你分时图**。

![界面预览](image.png)

## 功能特点

- **悬浮窗设计** — 无边框、半透明、置顶显示，拖拽移动位置
- **实时行情** — 通过新浪财经 HTTP API 获取实时报价，默认 5 秒刷新
- **期货支持** — 支持上期所、大商所、郑商所、中金所等主力合约
- **迷你分时图** — 每只品种右侧绘制当日分时走势，涨红跌绿一目了然
- **可选显示字段** — 自由配置显示的字段：现价、涨跌幅、涨跌额、成交量、成交额、最高价、最低价、量比、换手率、持仓量等
- **系统托盘** — 关闭时最小化到托盘，后台静默运行
- **开机自启** — 支持一键设置 Windows 开机自启动
- **自动更新检查** — 启动时自动检测新版本，一键跳转下载
- **深色主题** — 低调深色 UI，适合长时间挂屏

## 快速开始

### 环境要求

- Windows 7+
- Python 3.10+

### 安装与运行

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/Scripts/activate  # 或 venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 打包成独立 EXE

```bash
.\build.bat
```

打包后的可执行文件在 `dist/` 目录，可直接运行。

> 也可以从 [GitHub Releases](https://github.com/D33MO/stock-watching/releases) 下载最新版 exe。

## 使用指南

### 基本操作

| 操作 | 说明 |
|------|------|
| **左键拖拽** | 拖动窗口任意位置 |
| **点击 ⚙** | 打开设置面板 |
| **右键窗口** | 弹出快捷菜单（删除品种 / 退出） |
| **关闭按钮** | 最小化到系统托盘 |
| **双击托盘图标** | 显示 / 隐藏窗口 |

### 设置面板

- **品种管理** — 输入股票代码（如 `600519`）或期货代码（如 `CU2609`）添加，选中后删除
- **品种类型** — 股票无需指定类型；期货需要在添加时选择「期货」类型
- **显示字段** — 勾选要显示的字段，拖动排序
- **数据刷新** — 可选 3秒 / 5秒 / 10秒 / 30秒 / 60秒
- **窗口行为** — 开机自启动、窗口置顶、透明度调节

### 配置文件

在 `config.json` 中可手动编辑配置：

```json
{
    "stocks": [
        { "code": "600519", "name": "贵州茅台", "type": "stock" },
        { "code": "CU2609", "name": "沪铜2609", "type": "futures" }
    ],
    "refresh_interval": 5,
    "opacity": 0.9,
    "auto_start": true,
    "always_on_top": true,
    "display_fields": ["price", "change_pct", "change", "volume", "intraday"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `stocks` | array | 监控的品种列表，`code` 为代码，`name` 为名称，`type` 为 `stock` 或 `futures` |
| `refresh_interval` | int | 行情刷新间隔（秒） |
| `window_x` / `window_y` | int | 窗口屏幕坐标（自动记忆） |
| `opacity` | float | 窗口透明度 0.0 ~ 1.0 |
| `auto_start` | bool | 是否开机自启动 |
| `always_on_top` | bool | 是否窗口置顶 |
| `display_fields` | array | 显示字段列表，可选值见下方 |

**可用显示字段：**

| 字段 key | 说明 |
|----------|------|
| `price` | 现价 |
| `change_pct` | 涨跌幅 |
| `change` | 涨跌额 |
| `volume` | 成交量（手） |
| `turnover` | 成交额 |
| `high` | 当日最高 |
| `low` | 当日最低 |
| `volume_ratio` | 量比 |
| `turnover_rate` | 换手率 |
| `open_interest` | 持仓量 |
| `intraday` | 迷你分时图 |

## 期货支持说明

- **代码格式**：品种代码 + 年份后两位 + 月份，如 `CU2609`（沪铜2609合约）
- **涨跌基准**：期货使用**昨结算价**计算涨跌幅（非昨收）
- **特有字段**：期货品种可显示 **持仓量**
- **主力合约**：系统支持切换到主力合约

## 项目结构

```
stock-watching/
├── main.py                  # 程序入口
├── config.json              # 配置文件
├── requirements.txt         # Python 依赖
├── version.py               # 版本信息（自动检测更新用）
├── 股票监控.spec            # PyInstaller 打包配置
├── build.bat                # 一键打包脚本
├── README.md                # 本文件
│
├── ui/                      # 界面模块
│   ├── main_window.py       # 主窗口（悬浮窗、托盘、定时器）
│   ├── stock_widget.py      # 品种行组件（价格、涨跌、迷你分时图）
│   └── settings_dialog.py   # 设置对话框（含版本检测）
│
├── data/                    # 数据模块
│   ├── __init__.py
│   └── fetcher.py           # 行情获取（新浪 API + akshare）
│
├── .github/workflows/       # GitHub Actions 自动发布
│   └── release.yml          # 打 tag 自动打包并发布 Release
│
├── build/                   # 打包临时文件（已 gitignore）
├── dist/                    # 打包输出目录（已 gitignore）
└── venv/                    # Python 虚拟环境（已 gitignore）
```

## 技术栈

| 组件 | 用途 |
|------|------|
| **PyQt6** | 桌面 GUI 框架 |
| **新浪财经 API** | 实时行情 HTTP 接口（免费，无需 Key） |
| **akshare** | 分时数据和 K 线数据（东方财富数据源） |
| **PyInstaller** | 打包为独立 EXE |

## 数据来源

- **实时行情** — [新浪财经](https://hq.sinajs.cn/) HTTP API（免费开放接口）
- **分时图 / K线** — [AKShare](https://github.com/akfamily/akshare) 开源金融数据接口（东方财富数据源）

> 所有数据均来自公开免费 API，仅供个人学习和参考，不构成投资建议。

## 常见问题

**Q: 行情数据不刷新？**
A: 检查网络连接；新浪 API 在交易时段返回实时数据，非交易时段返回收盘数据。

**Q: 分时图显示为空？**
A: 非交易时段分时接口不返回数据，属于正常现象。

**Q: 如何开机自启动？**
A: 在设置面板勾选「开机自启动」即可；也可将 EXE 快捷方式放入 `shell:startup` 文件夹。

**Q: 期货代码怎么填？**
A: 格式为品种代码 + 年份后两位 + 月份，例如 `CU2609`（沪铜 2026 年 9 月合约）。添加时需在类型中选择「期货」。

**Q: 提示有新版本怎么更新？**
A: 点击「前往下载」按钮跳转到 GitHub Releases 页面，下载最新版 exe 覆盖即可。

## License

MIT
