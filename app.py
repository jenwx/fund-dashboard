import os
import streamlit as st
import pandas as pd
import requests
import json
import time
import re
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from streamlit_gsheets import GSheetsConnection  # 新增依赖

# ==========================================
# 0. 本地代理配置 (关键！仅Google Sheets需要，国内接口强制关闭)
# ==========================================
IS_LOCAL = False  # 无论本地/部署，都设为False（国内接口不走代理）
PROXY_PORT = "7890"

if IS_LOCAL:
    # 仅Google Sheets相关请求用代理，国内基金接口手动禁用
    os.environ["http_proxy"] = f"http://127.0.0.1:{PROXY_PORT}"
    os.environ["https_proxy"] = f"http://127.0.0.1:{PROXY_PORT}"
    print(f"⚡ 已开启本地代理加速 (仅Google Sheets): {PROXY_PORT}")
else:
    # 强制清空代理，避免干扰国内接口
    os.environ.pop("http_proxy", None)
    os.environ.pop("https_proxy", None)

# ==========================================
# 1. 全局配置与状态初始化
# ==========================================
st.set_page_config(page_title="基金实盘", layout="wide", page_icon="🏦")

# 替身映射 (QDII场外无估值时，借用场内ETF行情)
PROXY_MAP = {
    "019005": "161226",  # 白银C -> 白银LOF
    "019004": "161226",
    "017437": "513100",  # 华宝纳指 -> 纳指ETF
    "006479": "513100",
    "016702": "513100",  # 银华海外 -> 纳指ETF (暂借)
}

# 初始化Session状态
if 'finalized_cache' not in st.session_state:
    st.session_state.finalized_cache = {}
if 'bg_executor' not in st.session_state:
    st.session_state.bg_executor = ThreadPoolExecutor(max_workers=1)
if 'last_display_data' not in st.session_state:
    st.session_state.last_display_data = ([], 0.0, 0.0, 0.0)
if 'pending_future' not in st.session_state:
    st.session_state.pending_future = None
if 'last_fetch_time' not in st.session_state:
    st.session_state.last_fetch_time = 0

# ==========================================
# 2. CSS 样式注入 (完美融合版)
# ==========================================
st.markdown("""
<style>
    /* === 1. 页面容器调整 === */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 3rem !important;
        max-width: 100% !important;
    }

    /* === 2. 暗黑模式基础样式 === */
    .stApp { background-color: #0e1117; }
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 1 !important; }
    header[data-testid="stHeader"] * { color: #e0e0e0 !important; }
    section[data-testid="stSidebar"] { background-color: #262730; }

    /* === 3. 核心修复：输入框样式 === */
    div[data-baseweb="input"], div[data-baseweb="base-input"] {
        background-color: #1e1e1e !important;
        border: 1px solid #41424b !important;
        border-radius: 5px !important;
    }
    input[type="text"], input[type="number"], .stTextInput input, .stNumberInput input {
        color: white !important;
        background-color: transparent !important;
    }
    div[data-testid="stNumberInput"] div[data-baseweb="input"] > div {
        background-color: transparent !important;
        border-color: #41424b !important;
    }
    div[data-testid="stNumberInput"] button {
        background-color: transparent !important;
        color: #e0e0e0 !important;
        border: none !important;
        border-left: 1px solid #41424b !important;
    }
    div[data-testid="stNumberInput"] button:hover {
        background-color: #333 !important;
        color: #ff4b4b !important;
    }
    div[data-testid="stNumberInput"] button:focus {
        box-shadow: none !important;
        outline: none !important;
    }

    /* === 4. 其他组件样式 === */
    div[data-baseweb="select"] > div, ul[data-baseweb="menu"] {
        background-color: #1e1e1e !important; color: white !important;
        border-color: #41424b !important;
    }
    .stButton > button {
        background-color: #1e1e1e !important; color: white !important; border: 1px solid #41424b !important; width: 100%;
    }
    .stButton > button:hover {
        border-color: #ff4b4b !important; color: #ff4b4b !important;
    }
    div[data-testid="stExpander"] details summary {
        background-color: #1e1e1e !important; color: #e0e0e0 !important; border-radius: 5px; margin-bottom: 0px !important;
    }
    div[data-testid="stExpander"] details { border-color: transparent !important; }

    /* 间距 */
    section[data-testid="stSidebar"] div.element-container:has(div[data-testid="stToggle"]) { margin-bottom: 0px !important; }
    section[data-testid="stSidebar"] div.element-container:has(div[data-testid="stExpander"]) { margin-bottom: 0px !important; }
    hr { margin-top: 10px !important; margin-bottom: 20px !important; border-color: #41424b !important; opacity: 1 !important; }
    h1, h2, h3, p, span, div, label { color: #e0e0e0 !important; }

    /* 指标卡 */
    .metric-card {
        background-color: #1e1e1e; border: 1px solid #333; border-radius: 10px; padding: 16px 20px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2); display: flex; flex-direction: column; justify-content: space-between; 
        height: 100%; margin-bottom: 10px;
    }
    .metric-label { font-size: 14px; color: #a0a0a0 !important; font-weight: 500; margin-bottom: 5px; }
    .metric-value { font-family: 'Roboto Mono', monospace; font-size: 28px; font-weight: 700; color: #ffffff !important; }
    .metric-delta { font-size: 13px; font-weight: 600; padding: 3px 8px; border-radius: 4px; display: flex; align-items: center; gap: 4px; }
    .up-bg { background-color: rgba(245, 34, 45, 0.2); color: #ff4d4f !important; }
    .down-bg { background-color: rgba(0, 181, 120, 0.2); color: #2cc995 !important; }
    div[data-testid="stStatusWidget"] { visibility: hidden; }
    .element-container, .stVerticalBlock, div[data-testid="stFragment"] {
        opacity: 1 !important; transition: none !important; filter: none !important; animation: none !important;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 3. 数据存取层 (Google Sheets 缓存优化版)
# ==========================================
def get_conn():
    """建立Google Sheets连接（自动读取secrets配置）"""
    return st.connection("gsheets", type=GSheetsConnection)


def guess_confirm_days(name):
    """根据基金名称猜测确认天数（QDII为T+2，普通为T+1）"""
    if not name:
        return 1
    n = str(name).upper()
    keywords = ["QDII", "全球", "美国", "纳斯达克", "标普", "恒生", "海外", "油气", "商品", "德国", "日经", "越南",
                "印度", "法国"]
    if any(k in n for k in keywords):
        return 2
    return 1


def load_portfolio():
    """从 Google Sheets 读取持仓数据（修复代码格式）"""
    try:
        conn = get_conn()
        df = conn.read(worksheet="portfolio", ttl=60)
        expected_cols = ['code', 'name', 'channel', 'cost', 'shares', 'confirm_days']

        # 处理空数据或列缺失
        if df.empty or len(df.columns) < len(expected_cols):
            df = pd.DataFrame(columns=expected_cols)

        # 补全缺失列
        for c in expected_cols:
            if c not in df.columns:
                df[c] = ""

        # 处理浮点数/带小数点的代码（如24307.0 → 024307）
        df['code'] = df['code'].apply(
            lambda x: str(int(float(x))).zfill(6) if pd.notna(x) and str(x).strip() else ""
        ).str.strip()

        # 数据类型转换
        df['channel'] = df['channel'].replace([None, "nan", ""], "场外(支付宝)").astype(str)
        df['shares'] = pd.to_numeric(df['shares'], errors='coerce').fillna(0.0)
        df['cost'] = pd.to_numeric(df['cost'], errors='coerce').fillna(0.0)
        df['confirm_days'] = pd.to_numeric(df['confirm_days'], errors='coerce').fillna(1).astype(int)

        # 过滤无效数据
        df = df[df["code"].notna() & (df["code"] != "") & (df["code"] != "nan")]
        return df
    except Exception as e:
        print(f"Google Sheets Load Error: {e}")
        return pd.DataFrame(columns=['code', 'name', 'channel', 'cost', 'shares', 'confirm_days'])


def save_portfolio_df(df):
    """保存持仓数据到 Google Sheets"""
    try:
        conn = get_conn()
        conn.update(worksheet="portfolio", data=df)
        st.cache_data.clear()  # 清除缓存，确保下次读取最新数据
    except Exception as e:
        st.error(f"保存失败 (Google Sheets): {e}")


def load_transactions():
    """读取交易记录"""
    try:
        conn = get_conn()
        df = conn.read(worksheet="transactions", ttl=60)
        if df.empty:
            return []
        return df.to_dict('records')
    except Exception as e:
        print(f"加载交易记录失败: {e}")
        return []


def add_transaction(r):
    """追加交易记录"""
    try:
        conn = get_conn()
        current_df = conn.read(worksheet="transactions", ttl=0)  # 强制读取最新数据

        # 追加新数据
        new_df = pd.DataFrame([r])
        final_df = pd.concat([current_df, new_df], ignore_index=True)

        conn.update(worksheet="transactions", data=final_df)
        st.cache_data.clear()  # 清除缓存
    except Exception as e:
        st.error(f"交易记录保存失败: {e}")


# ==========================================
# 4. 网络请求层 (终极修复：强制直连 + 手动算涨幅)
# ==========================================
def get_headers():
    """生成随机请求头，避免被风控"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Referer": "http://fund.eastmoney.com/",
        "Accept": "*/*"
    }


def fast_get_name(code):
    """获取基金名称（修复代码格式）"""
    # 处理不规范代码
    code = str(code).strip()
    if '.' in code:
        code = str(int(float(code))).zfill(6)
    else:
        code = code.zfill(6)

    no_proxy = {"http": None, "https": None}
    try:
        # 优先从估值接口获取
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        r = requests.get(url, headers=get_headers(), timeout=3, proxies=no_proxy)
        if r.status_code == 200 and "jsonpgz" in r.text:
            content = re.findall(r'jsonpgz\((.*?)\);', r.text)
            if content:
                data = json.loads(content[0])
                return data.get('name', '')
    except Exception as e:
        print(f"估值接口获取名称失败 {code}: {e}")

    try:
        # 备用接口
        url = f"https://fund.1234567.com.cn/fundpage/v1/info?productId={code}"
        r = requests.get(url, headers=get_headers(), timeout=3, proxies=no_proxy).json()
        if r.get("data") and r["data"].get("fund_name"):
            return r["data"]["fund_name"]
    except Exception as e:
        print(f"备用接口获取名称失败 {code}: {e}")

    return ""


def fetch_market_rate_only(code):
    """获取场内/ETF行情涨跌幅"""
    no_proxy = {"http": None, "https": None}
    try:
        # 腾讯接口
        r = requests.get(f"http://qt.gtimg.cn/q=sh{code},sz{code}", timeout=2, proxies=no_proxy)
        lines = r.text.split(';')
        for line in lines:
            if (f"sh{code}" in line or f"sz{code}" in line) and '="' in line:
                parts = line.split('="')[1].split('~')
                if len(parts) > 30:
                    curr = float(parts[3])
                    close = float(parts[4])
                    if close > 0:
                        return (curr - close) / close, "腾讯"
    except Exception as e:
        print(f"腾讯场内接口失败 {code}: {e}")

    try:
        # 东方财富接口
        p = "1" if code.startswith(('5', '6')) else "0"
        url = f"http://push2.eastmoney.com/api/qt/stock/get?fields=f3&secid={p}.{code}"
        r = requests.get(url, headers=get_headers(), timeout=2, proxies=no_proxy).json()
        if r.get('data') and r['data']['f3'] != "-":
            return float(r['data']['f3']) / 100, "东财"
    except Exception as e:
        print(f"东财场内接口失败 {code}: {e}")

    return 0.0, "-"


def get_previous_nav(code, today_str):
    """获取历史净值（增强容错）"""
    no_proxy = {"http": None, "https": None}
    try:
        url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=10"
        headers = {
            'Referer': 'http://fundf10.eastmoney.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate'
        }
        r = requests.get(
            url,
            headers=headers,
            timeout=5,
            proxies=no_proxy,
            verify=False
        )
        data = r.json()
        if data and 'Data' in data and 'LSJZList' in data['Data']:
            for item in data['Data']['LSJZList']:
                if item.get('FSRQ') and item['FSRQ'] != today_str and item.get('DWJZ'):
                    return float(item['DWJZ'])
    except Exception as e:
        print(f"获取历史净值失败 {code}: {e}")
    return None


@st.cache_data(ttl=5, show_spinner=False)
def fetch_fund_data_core(fund_code, channel):
    """核心数据获取函数（修复代码格式 + 多层兜底）"""
    # 处理不规范代码（如24307.0 → 024307）
    code = str(fund_code).strip()
    if '.' in code:
        code = str(int(float(code))).zfill(6)
    else:
        code = code.zfill(6)

    res = {
        "est_rate": 0.0,
        "base_nav": 1.0,
        "live_price": 1.0,
        "source": "-",
        "nav_date": ""
    }
    today_str = str(datetime.now().date())
    no_proxy = {"http": None, "https": None}  # 强制不走代理

    # ===== 第一步：场内基金优先获取 =====
    if "场内" in str(channel):
        rate, src = fetch_market_rate_only(code)
        if src != "-" and rate != 0.0:  # 确保获取到有效涨跌幅
            res.update({
                "est_rate": rate,
                "source": src + "(场内)",
                "live_price": 1.0 * (1 + rate)
            })
            print(f"场内基金 {code} 涨跌幅: {rate * 100:.2f}%")
            return res

    # ===== 第二步：场外基金获取估值/净值 =====
    try:
        ts = int(time.time() * 1000)
        url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={ts}"
        r = requests.get(
            url,
            headers=get_headers(),
            timeout=5,  # 延长超时时间
            proxies=no_proxy,
            verify=False  # 跳过SSL验证（部分环境可能有证书问题）
        )
        r.encoding = "utf-8"  # 强制指定编码，避免解析乱码

        if r.status_code == 200 and "jsonpgz" in r.text:
            content = re.findall(r'jsonpgz\((.*?)\);', r.text)
            if content:
                js = json.loads(content[0])
                # 关键：判空 + 类型转换容错
                dwjz = float(js.get('dwjz', 0.0)) if js.get('dwjz') not in [None, "", "0"] else 0.0
                gsz = float(js.get('gsz', 0.0)) if js.get('gsz') not in [None, "", "0"] else 0.0
                jzrq = js.get('jzrq', "")

                if dwjz <= 0 or gsz <= 0:
                    print(f"基金 {code} 净值/估值为0: dwjz={dwjz}, gsz={gsz}")
                else:
                    # 手动计算涨跌幅（核心修复：避免依赖接口返回的gszzl）
                    est_rate = (gsz - dwjz) / dwjz
                    res["base_nav"] = dwjz
                    res["nav_date"] = jzrq

                    # 盘中/盘后逻辑
                    if jzrq == today_str:
                        # 净值已更新，获取前一日净值算真实涨幅
                        prev_nav = get_previous_nav(code, today_str)
                        if prev_nav and prev_nav > 0:
                            est_rate = (dwjz - prev_nav) / prev_nav
                            res["live_price"] = dwjz
                            res["source"] = "净值已更新"
                        else:
                            res["live_price"] = gsz
                            res["source"] = "已更新(估)"
                    else:
                        res["live_price"] = gsz
                        res["source"] = "官方估值"

                    res["est_rate"] = est_rate
                    print(f"场外基金 {code} 涨跌幅: {est_rate * 100:.2f}% (来源: {res['source']})")
                    return res
    except Exception as e:
        print(f"场外基金 {code} 获取失败: {str(e)}")

    # ===== 第三步：QDII/场外基金借用场内ETF行情（兜底）=====
    target = PROXY_MAP.get(code)
    if not target and code.startswith(('16', '15', '50', '51')):
        target = code
    if "场外" in str(channel) and target:
        m_rate, m_src = fetch_market_rate_only(target)
        if m_rate != 0.0 and m_src != "-":
            res.update({
                "est_rate": m_rate,
                "source": f"借用{target}",
                "live_price": res['base_nav'] * (1 + m_rate)
            })
            print(f"基金 {code} 借用 {target} 涨跌幅: {m_rate * 100:.2f}%")
            return res

    # ===== 最终兜底：若所有方式都失败，打印日志提醒 =====
    print(f"基金 {code} 所有接口获取失败，涨跌幅默认0")
    return res


# ==========================================
# 5. UI 组件封装
# ==========================================
def render_metric_card(label, value, delta_text, is_positive):
    """渲染自定义指标卡片"""
    color, bg, arrow = ("#f5222d", "up-bg", "▲") if is_positive else ("#00b578", "down-bg", "▼")
    html = f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div style="display: flex; align-items: baseline; justify-content: space-between;">
            <div class="metric-value">{value}</div>
            <div class="metric-delta {bg}"><span>{arrow}</span><span>{delta_text}</span></div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def calculate_dashboard_data(current_df, cache_snapshot):
    """计算仪表盘核心数据"""
    rows = []
    total_day_gain = 0.0
    total_acc_gain = 0.0
    total_value = 0.0
    today_str = str(datetime.now().date())

    def process_row(row):
        """处理单条持仓数据"""
        code = row['code']
        channel = row['channel']
        cache_key = f"{code}_{today_str}"
        cached_item = cache_snapshot.get(cache_key)

        if cached_item:
            data = cached_item
            updated = True
        else:
            data = fetch_fund_data_core(code, channel)
            updated = ("场外" in channel and data.get('nav_date') == today_str)

        live_price = data['live_price']
        base_nav = data['base_nav']
        shares = float(row['shares'])
        cost = float(row['cost'])

        # 计算核心指标
        position_value = live_price * shares
        day_gain = (live_price - base_nav) * shares
        acc_gain = (live_price - cost) * shares
        rate_str = f"{data['est_rate'] * 100:+.2f}%" + (" (已更新)" if updated else "")

        return {
            "result": {
                "基金代码": code, "基金名称": row['name'], "渠道": channel, "持仓成本": cost,
                "持有份额": shares, "持仓金额": position_value, "最新净值": live_price,
                "今日盈亏": day_gain, "总盈亏": acc_gain, "涨跌幅": rate_str, "数据源": data['source']
            },
            "stats": (day_gain, acc_gain, position_value),
            "cache_update": (cache_key, data) if updated and not cached_item else None
        }

    # 多线程处理持仓数据
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_row, row) for _, row in current_df.iterrows()]
        for future in futures:
            try:
                data = future.result()
                rows.append(data["result"])
                dg, ag, v = data["stats"]
                total_day_gain += dg
                total_acc_gain += ag
                total_value += v
                if data["cache_update"]:
                    k, val = data["cache_update"]
                    cache_snapshot[k] = val
            except Exception as e:
                print(f"处理持仓行失败: {e}")

    # 按持仓金额降序排序
    rows.sort(key=lambda x: x['持仓金额'], reverse=True)
    return rows, total_day_gain, total_acc_gain, total_value, cache_snapshot


# ==========================================
# 6. 核心 Fragment
# ==========================================
def sidebar_fragment():
    """侧边栏组件"""
    st.header("⚡ 控制台")
    st.divider()

    # ========== 初始化各展开项的状态（默认全收起） ==========
    if 'expander_data_migrate' not in st.session_state:
        st.session_state.expander_data_migrate = False  # 数据迁移默认收起
    if 'expander_add_fund' not in st.session_state:
        st.session_state.expander_add_fund = False       # 添加新基金默认收起
    if 'expander_init_trade' not in st.session_state:
        st.session_state.expander_init_trade = False     # 发起交易默认收起





    # =========== 2. 编辑模式 ===========
    st.toggle("✏️ 编辑模式", key="edit_mode_toggle")
    st.divider()
    # =========== 1. 数据迁移（本地 -> 云端） ===========
    with st.expander(
        "🚚 数据迁移 (本地 -> 云端)",
        expanded=st.session_state.expander_data_migrate  # 绑定状态（默认收起）
    ):
        st.caption("检测到你切换了Google Sheets，点此将本地JSON上传到云端。")
        if st.button("🚀 一键上传本地数据"):
            try:
                # 1. 读取本地 portfolio.json
                if os.path.exists("portfolio.json"):
                    with open("portfolio.json", "r", encoding="utf-8") as f:
                        local_data = json.load(f)
                    if local_data:
                        df = pd.DataFrame(local_data)
                        # 写入 Google Sheets
                        conn = get_conn()
                        conn.update(worksheet="portfolio", data=df)
                        st.success(f"成功上传 {len(df)} 条持仓记录！")
                    else:
                        st.warning("本地 portfolio.json 是空的")
                else:
                    st.error("找不到本地 portfolio.json 文件")

                # 2. 迁移交易记录 (如果有)
                if os.path.exists("transactions.json"):
                    with open("transactions.json", "r", encoding="utf-8") as f:
                        trans_data = json.load(f)
                    if trans_data:
                        df_trans = pd.DataFrame(trans_data)
                        conn = get_conn()
                        conn.update(worksheet="transactions", data=df_trans)
                        st.success(f"成功上传 {len(df_trans)} 条交易记录！")

                st.cache_data.clear()  # 清除缓存
                time.sleep(2)
                st.rerun()

            except Exception as e:
                st.error(f"迁移失败: {e}")
    st.divider()

    # =========== 3. 添加新基金（互斥逻辑） ===========
    with st.expander(
        "➕ 添加新基金",
        expanded=st.session_state.expander_add_fund  # 绑定状态（默认收起）
    ):
        new_code = st.text_input("基金代码", key="sb_new_code", placeholder="6位数字")
        new_cost = st.number_input("持仓成本价", key="sb_new_cost", value=0.0, step=0.0001, format="%.4f")
        new_shares = st.number_input("持有份额", key="sb_new_shares", value=0.0, step=0.01, format="%.2f")

        # 自动查询基金名称
        fund_name = fast_get_name(new_code) if new_code.strip() else ""
        if fund_name:
            st.success(f"已查询：{fund_name}")
        elif new_code.strip():
            st.caption("正在查询...")

        # 确认添加按钮逻辑
        if st.button("确认添加", width="stretch"):
            if len(new_code.strip()) != 6:
                st.error("代码错误：必须是6位数字")
            elif new_cost < 0 or new_shares < 0:
                st.error("数值错误：成本和份额不能为负数")
            elif not fund_name:
                st.error("查询失败：无法获取基金名称，请检查代码是否正确")
            else:
                # 校验该基金能否获取到涨跌幅
                test_data = fetch_fund_data_core(new_code, "场外(支付宝)")
                if test_data["est_rate"] == 0.0 and test_data["source"] == "-":
                    st.error("该基金暂无估值数据，无法添加")
                else:
                    # 原有添加逻辑
                    df = load_portfolio()
                    if new_code in df['code'].values:
                        st.warning("该基金已存在，请勿重复添加")
                    else:
                        new_row = {
                            "code": new_code.zfill(6),
                            "name": fund_name,
                            "channel": "场外(支付宝)",
                            "cost": new_cost,
                            "shares": new_shares,
                            "confirm_days": guess_confirm_days(fund_name)
                        }
                        save_portfolio_df(pd.concat([df, pd.DataFrame([new_row])], ignore_index=True))
                        st.success(f"已成功添加：{fund_name}");
                        time.sleep(1);
                        st.rerun()

    # 互斥逻辑：若“添加新基金”展开 → 收起“发起交易”
    if st.session_state.expander_add_fund:
        st.session_state.expander_init_trade = False
    st.divider()


    # =========== 4. 发起交易（互斥逻辑） ===========
    with st.expander(
        "💸 发起交易",
        expanded=st.session_state.expander_init_trade  # 绑定状态（默认收起）
    ):
        current_df = load_portfolio()
        if not current_df.empty:
            opts = current_df.apply(lambda x: f"{x['name']} ({x['code']})", axis=1).tolist()
            sel = st.selectbox("标的", opts, key="sb_trade_sel")
            row = current_df.iloc[opts.index(sel)]

            # 获取确认天数和当前净值
            confirm_days = int(row.get('confirm_days', 1))
            rt = fetch_fund_data_core(row['code'], row['channel'])
            st.caption(f"当前净值: **{rt['live_price']:.4f}** (T+{confirm_days})")

            # 交易时间选择
            trade_time = st.radio(
                "时间", ["15:00前", "15:00后"],
                horizontal=True,
                label_visibility="collapsed",
                key="sb_trade_ts"
            )
            trade_date = datetime.now().date() + (timedelta(days=1) if "15:00后" in trade_time else timedelta(days=0))

            # 交易方向和单位
            col1, col2 = st.columns(2)
            action = col1.selectbox("方向", ["买入", "卖出"], key="sb_trade_act")
            mode = col2.selectbox("单位", ["金额", "份额"], key="sb_trade_mod")
            value = st.number_input("数值", 1.0, step=100.0, key="sb_trade_val")

            # 提交委托
            if st.button("🔴 提交委托", width="stretch", type="primary"):
                add_transaction({
                    "submit_date": str(datetime.now().date()),
                    "trade_date": str(trade_date),
                    "confirm_date": str(trade_date + timedelta(days=confirm_days)),
                    "code": row['code'],
                    "name": row['name'],
                    "type": "buy" if action == "买入" else "sell",
                    "mode": "amount" if mode == "金额" else "share",
                    "value": value,
                    "status": "pending",
                    "channel": row['channel']
                })
                st.success("✅ 委托已提交")
        else:
            st.info("请先在左侧添加基金持仓")

    # 互斥逻辑：若“发起交易”展开 → 收起“添加新基金”
    if st.session_state.expander_init_trade:
        st.session_state.expander_add_fund = False
    st.divider()


@st.fragment(run_every=1)
def dashboard_live_fragment():
    """实时仪表盘组件"""
    now_ts = time.time()

    # 处理后台异步任务结果
    if st.session_state.pending_future:
        if st.session_state.pending_future.done():
            try:
                rows, t_d, t_a, t_v, new_cache = st.session_state.pending_future.result()
                st.session_state.last_display_data = (rows, t_d, t_a, t_v)
                st.session_state.finalized_cache.update(new_cache)
                st.session_state.last_fetch_time = now_ts
            except Exception as e:
                print(f"后台更新失败: {e}")
            finally:
                st.session_state.pending_future = None

    # 触发新的异步数据获取
    if not st.session_state.pending_future:
        if (now_ts - st.session_state.last_fetch_time >= 4) or (not st.session_state.last_display_data[0]):
            current_df = load_portfolio()
            cache_snapshot = dict(st.session_state.finalized_cache)
            future = st.session_state.bg_executor.submit(
                calculate_dashboard_data, current_df, cache_snapshot
            )
            st.session_state.pending_future = future

    # 获取最新显示数据
    rows, total_day_gain, total_acc_gain, total_value = st.session_state.last_display_data

    # 渲染顶部指标
    col1, col2 = st.columns([8, 2])
    col1.caption(f"⚡ 实时监控: {datetime.now().strftime('%H:%M:%S')}")

    k1, k2, k3 = st.columns(3)
    with k1:
        render_metric_card("今日盈亏", f"{total_day_gain:+.2f}", "今日波动", total_day_gain >= 0)
    with k2:
        render_metric_card("历史盈亏", f"{total_acc_gain:+.2f}", "累计收益", total_acc_gain >= 0)
    with k3:
        render_metric_card("总资产", f"{total_value:,.0f}", "当前市值", True)

    st.write("")

    # 渲染持仓表格
    if not rows:
        if st.session_state.pending_future:
            st.info("🚀 正在极速加载数据...")
        else:
            st.info("暂无持仓数据，请在左侧边栏添加基金。")
        return

    df = pd.DataFrame(rows)

    # 表格样式函数
    def color_val(val):
        if val > 0:
            return f'color: #ff4d4f; font-weight: bold'
        elif val < 0:
            return f'color: #2cc995; font-weight: bold'
        else:
            return 'color: #e0e0e0'

    # 表格列配置
    all_columns = ["基金代码", "基金名称", "渠道", "持有份额", "持仓成本", "最新净值", "涨跌幅", "今日盈亏", "总盈亏",
                   "持仓金额", "数据源"]
    col_config = {col: st.column_config.TextColumn(col, width="small") for col in all_columns}
    col_config["基金名称"] = st.column_config.TextColumn("基金名称", width=300)
    col_config["数据源"] = st.column_config.TextColumn("数据源", width="small")

    # 渲染带样式的表格
    st.dataframe(
        df.style
        .set_table_styles([
            {'selector': 'th', 'props': [
                ('text-align', 'left'),
                ('border-bottom', '1px solid #41424b !important'),
                ('background-color', '#1e1e1e !important')
            ]},
            {'selector': 'td', 'props': [('text-align', 'left')]}
        ])
        .map(color_val, subset=['今日盈亏', '总盈亏'])
        .map(
            lambda x: 'color: #ff4d4f; font-weight:bold' if "+" in str(x)
            else 'color: #2cc995; font-weight:bold' if "-" in str(x)
            else 'color:#888' if "更新" in str(x)
            else 'color: #e0e0e0',
            subset=['涨跌幅']
        )
        .format({
            "持仓成本": "{:.4f}",
            "持有份额": "{:.2f}",
            "持仓金额": "{:,.0f}",
            "最新净值": "{:.4f}",
            "今日盈亏": "{:+.2f}",
            "总盈亏": "{:+.2f}"
        }),
        width="stretch",
        height=(len(df) + 1) * 35 + 3,
        hide_index=True,
        column_order=all_columns,
        column_config=col_config
    )


def dashboard_edit_fragment():
    """编辑模式仪表盘"""
    current_df = load_portfolio()
    cache_snapshot = dict(st.session_state.finalized_cache)
    rows, _, _, _, _ = calculate_dashboard_data(current_df, cache_snapshot)

    st.caption("✏️ 编辑模式: 直接修改下方表格，修改后自动保存。")
    if current_df.empty:
        st.info("暂无持仓数据，请在侧边栏添加。")
        return

    # 渲染可编辑表格
    table_height = (len(current_df) + 2) * 35 + 3
    edited_df = st.data_editor(
        current_df,
        column_config={
            "code": "基金代码",
            "name": "基金名称",
            "channel": st.column_config.SelectboxColumn(
                "渠道",
                options=["场外(支付宝)", "场内(证券)", "场内(借用)"],
                required=True
            ),
            "cost": st.column_config.NumberColumn("持仓成本", min_value=0.0, format="%.4f"),
            "shares": st.column_config.NumberColumn("持有份额", min_value=0.0, format="%.2f"),
            "confirm_days": st.column_config.NumberColumn("确认天数(T+N)", min_value=0, step=1, format="%d"),
        },
        column_order=["code", "name", "channel", "cost", "shares", "confirm_days"],
        hide_index=True,
        width="stretch",
        height=table_height,
        num_rows="dynamic",
        key="portfolio_editor"
    )

    # 自动保存修改
    if not edited_df.equals(current_df):
        try:
            # 过滤无效数据
            edited_df = edited_df[edited_df["code"].notna() & (edited_df["code"] != "")]
            # 保存到 Google Sheets
            save_portfolio_df(edited_df)
            st.toast("✅ 持仓数据已更新", icon="💾");
            time.sleep(0.5);
            st.rerun()
        except Exception as e:
            st.error(f"保存失败: {e}")


def transaction_manager_fragment():
    """交易管理组件"""
    st.subheader("交易管理")
    transactions = load_transactions()  # 从云端读取交易记录
    pending_trans = [t for t in transactions if t['status'] == 'pending']

    if not pending_trans:
        st.info("🎉 暂无待处理交易");
        return

    today = str(datetime.now().date())

    # 表头
    cols = st.columns([3, 1, 2, 1, 1])
    cols[0].caption("标的/方向");
    cols[1].caption("状态");
    cols[2].caption("预估详情");
    cols[3].caption("结算");
    cols[4].caption("撤销")

    # 渲染待处理交易
    for i, trans in enumerate(pending_trans):
        col1, col2, col3, col4, col5 = st.columns([3, 1, 2, 1, 1])

        # 标的和方向
        color = "red" if trans['type'] == 'buy' else "green"
        col1.markdown(f"**{trans['name']}** :{color}[{trans['type']}]")
        col1.caption(f"{trans['channel']} | {trans['trade_date']}")

        # 状态判断
        ready_to_confirm = today >= trans['confirm_date']
        if ready_to_confirm:
            col2.success("✅ 可结算")
        else:
            col2.info(f"⏳ {trans['confirm_date']}")

        # 委托信息
        unit = "元" if trans['mode'] == 'amount' else "份"
        col3.caption(f"委托: {trans['value']} {unit}")

        # 获取当前净值
        rt = fetch_fund_data_core(trans['code'], trans['channel'])

        # 结算按钮
        if ready_to_confirm:
            real_price = col3.number_input(
                f"净#{i}",
                value=float(rt['live_price']),
                format="%.4f",
                label_visibility="collapsed"
            )
            if col4.button("确认", key=f"btn_ok_{i}"):
                # 加载持仓数据
                portfolio_df = load_portfolio()
                matches = portfolio_df[portfolio_df['code'] == trans['code']]

                # 若无该基金则新增
                if matches.empty:
                    new_row = {
                        "code": trans['code'],
                        "name": trans['name'],
                        "channel": trans['channel'],
                        "cost": 0.0,
                        "shares": 0.0,
                        "confirm_days": 1
                    }
                    portfolio_df = pd.concat([portfolio_df, pd.DataFrame([new_row])], ignore_index=True)
                    idx = len(portfolio_df) - 1
                else:
                    idx = matches.index[0]

                # 计算份额和金额
                current_row = portfolio_df.loc[idx]
                if trans['mode'] == "amount":
                    trade_shares = float(trans['value']) / real_price
                    trade_amount = float(trans['value'])
                else:
                    trade_shares = float(trans['value'])
                    trade_amount = float(trans['value']) * real_price

                # 更新持仓
                if trans['type'] == 'buy':
                    new_shares = float(current_row['shares']) + trade_shares
                    if new_shares > 0:
                        new_cost = (float(current_row['shares']) * float(
                            current_row['cost']) + trade_amount) / new_shares
                    else:
                        new_cost = 0.0
                    portfolio_df.at[idx, 'shares'] = new_shares
                    portfolio_df.at[idx, 'cost'] = new_cost
                else:
                    new_shares = float(current_row['shares']) - trade_shares
                    portfolio_df.at[idx, 'shares'] = new_shares if new_shares > 0 else 0

                # 保存更新
                save_portfolio_df(portfolio_df)

                # 移除已结算交易
                remaining_trans = [x for x in transactions if x != trans]
                conn = get_conn()
                conn.update(worksheet="transactions", data=pd.DataFrame(remaining_trans))

                st.toast("✅ 交易结算完成");
                time.sleep(1);
                st.rerun()
        else:
            col4.write("-")

        # 撤销按钮
        if col5.button("🗑️", key=f"btn_del_{i}"):
            remaining_trans = [x for x in transactions if x != trans]
            conn = get_conn()
            conn.update(worksheet="transactions", data=pd.DataFrame(remaining_trans))
            st.toast("🗑️ 交易已撤销");
            time.sleep(0.5);
            st.rerun()


# ==========================================
# 7. 页面主入口
# ==========================================
if __name__ == "__main__":
    with st.sidebar:
        sidebar_fragment()

    st.title("🏦 基金实盘")
    tab1, tab2 = st.tabs(["📊 资产全览", "📝 交易管理"])

    with tab1:
        if st.session_state.get("edit_mode_toggle", False):
            dashboard_edit_fragment()
        else:
            dashboard_live_fragment()

    with tab2:
        transaction_manager_fragment()
