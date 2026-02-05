import streamlit as st
import pandas as pd
import requests
import json
import os
import time
import re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
# ==========================================
# 1. 全局配置与状态初始化
# ==========================================
st.set_page_config(page_title="基金实盘驾驶舱", layout="wide", page_icon="🏦")

PORTFOLIO_FILE = "portfolio.json"
TRANSACTION_FILE = "transactions.json"

# 替身映射 (QDII场外无估值时，借用场内ETF行情)
PROXY_MAP = {
    "019005": "161226",  # 白银C -> 白银LOF
    "019004": "161226",
    "017437": "513100",  # 华宝纳指 -> 纳指ETF
    "006479": "513100",
    "016702": "513100",  # 银华海外 -> 纳指ETF (暂借)
}

# 初始化Session状态
if 'finalized_cache' not in st.session_state: st.session_state.finalized_cache = {}
if 'editor_key' not in st.session_state: st.session_state.editor_key = 1000

# ==========================================
# 2. CSS 样式注入 (完美等距版)
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

    /* 输入框、下拉框、数字框样式 */
    .stTextInput > div > div, .stNumberInput > div > div, .stSelectbox > div > div {
        background-color: #1e1e1e !important; color: white !important; border-color: #41424b !important;
    }
    input[type="text"], input[type="number"] { color: white !important; }
    div[data-baseweb="select"] > div, ul[data-baseweb="menu"] {
        background-color: #1e1e1e !important; color: white !important;
    }

    /* 按钮样式 */
    .stButton > button {
        background-color: #1e1e1e !important; color: white !important; border: 1px solid #41424b !important; width: 100%;
    }
    .stButton > button:hover {
        border-color: #ff4b4b !important; color: #ff4b4b !important;
    }

    /* 折叠面板 (Expander) 样式 */
    div[data-testid="stExpander"] details summary {
        background-color: #1e1e1e !important;
        color: #e0e0e0 !important;
        border-radius: 5px;
        margin-bottom: 0px !important; /* 强制归零，由分割线控制间距 */
    }
    div[data-testid="stExpander"] details summary:hover {
        color: #ff4b4b !important;
    }
    div[data-testid="stExpander"] details { 
        border-color: transparent !important;
    }

    /* === 核心修复：侧边栏间距归零 === */
    /* 1. 让开关容器没有下边距 */
    section[data-testid="stSidebar"] div.element-container:has(div[data-testid="stToggle"]) {
        margin-bottom: 0px !important;
    }
    /* 2. 让 Expander 容器没有下边距 */
    section[data-testid="stSidebar"] div.element-container:has(div[data-testid="stExpander"]) {
        margin-bottom: 0px !important;
    }

    /* === 核心修复：分割线统御间距 === */
    hr {
        margin-top: 10px !important;    /* 线上方间距 */
        margin-bottom: 20px !important; /* 线下方间距 (保持一致) */
        border-color: #41424b !important;
        opacity: 1 !important;
        border-bottom-width: 1px !important;
    }

    h1, h2, h3, p, span, div, label { color: #e0e0e0 !important; }

    /* === 3. 指标卡片样式 === */
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

    /* === 4. 其他 === */
    div[data-testid="stStatusWidget"] { visibility: hidden; }
    .element-container, .stVerticalBlock, div[data-testid="stFragment"] {
        opacity: 1 !important; transition: none !important; filter: none !important; animation: none !important;
    }
</style>
""", unsafe_allow_html=True)

# === 1. 定义伪装头 (关键！假装自己是浏览器) ===
def get_headers():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Referer": "http://fund.eastmoney.com/",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }
# ==========================================
# 3. 数据存取层（无修改）
# ==========================================
def load_json(filename, default=None):
    if default is None: default = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return default


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def guess_confirm_days(name):
    if not name: return 1
    n = str(name).upper()
    keywords = ["QDII", "全球", "美国", "纳斯达克", "标普", "恒生", "海外", "油气", "商品", "德国", "日经", "越南",
                "印度", "法国"]
    if any(k in n for k in keywords): return 2
    return 1


def load_portfolio():
    data = load_json(PORTFOLIO_FILE, [])
    df = pd.DataFrame(data) if data else pd.DataFrame(
        columns=['code', 'name', 'channel', 'cost', 'shares', 'confirm_days'])
    for c in ['code', 'name', 'channel', 'cost', 'shares', 'confirm_days']:
        if c not in df.columns: df[c] = ""
    df['code'] = df['code'].astype(str).str.strip().apply(lambda x: x.zfill(6))
    df['channel'] = df['channel'].replace([None, "nan", ""], "场外(支付宝)").astype(str)
    df['shares'] = pd.to_numeric(df['shares'], errors='coerce').fillna(0.0)
    df['cost'] = pd.to_numeric(df['cost'], errors='coerce').fillna(0.0)
    df['confirm_days'] = pd.to_numeric(df['confirm_days'], errors='coerce').fillna(1).astype(int)
    return df


def save_portfolio_df(df):
    save_list = []
    for _, row in df.iterrows():
        save_list.append({
            "code": str(row['code']).zfill(6),
            "name": str(row['name']),
            "channel": str(row['channel']),
            "cost": float(row['cost']),
            "shares": float(row['shares']),
            "confirm_days": int(row['confirm_days'])
        })
    save_json(PORTFOLIO_FILE, save_list)


def load_transactions(): return load_json(TRANSACTION_FILE, [])


def add_transaction(r):
    h = load_transactions()
    h.append(r)
    save_json(TRANSACTION_FILE, h)


# === 2. 增强版：获取基金名称 (用于添加基金) ===
def fast_get_name(code):
    try:
        # 接口 A: 天天基金搜索接口 (通常响应最快)
        url = f"http://fundgz.1234567.com.cn/js/{code}.js"
        # 必须加 headers，否则云端会被 403 Forbidden
        r = requests.get(url, headers=get_headers(), timeout=3)
        
        if r.status_code == 200 and "jsonpgz" in r.text:
            # 提取 json: jsonpgz({"fundcode":"...","name":"这里是名字",...});
            content = re.findall(r'jsonpgz\((.*?)\);', r.text)
            if content:
                data = json.loads(content[0])
                return data.get('name', '')
                
    except Exception as e:
        print(f"Name fetch error ({code}): {e}") # 会打印到 Streamlit 后台 Logs
    return ""

def fetch_market_rate_only(code):
    try:
        r = requests.get(f"http://qt.gtimg.cn/q=sh{code},sz{code}", timeout=1.5)
        lines = r.text.split(';')
        for line in lines:
            if (f"sh{code}" in line or f"sz{code}" in line) and '="' in line:
                parts = line.split('="')[1].split('~')
                if len(parts) > 30:
                    curr = float(parts[3])
                    close = float(parts[4])
                    if close > 0: return (curr - close) / close, "腾讯"
    except:
        pass
    try:
        prefix = "sh" if code.startswith(('5', '6')) else "sz"
        r = requests.get(f"http://hq.sinajs.cn/list={prefix}{code}",
                         headers={'Referer': 'https://finance.sina.com.cn/'}, timeout=1.5)
        if '="' in r.text:
            parts = r.text.split('="')[1].split(',')
            if len(parts) > 3:
                curr = float(parts[3])
                close = float(parts[2])
                if close > 0: return (curr - close) / close, "新浪"
    except:
        pass
    try:
        p = "1" if code.startswith(('5', '6')) else "0"
        url = f"http://push2.eastmoney.com/api/qt/stock/get?fields=f3,f43,f60&secid={p}.{code}"
        r = requests.get(url, timeout=1.5).json()
        if r.get('data') and r['data']['f3'] != "-":
            return float(r['data']['f3']) / 100, "东财"
    except:
        pass
    return 0.0, "-"


def get_previous_nav(code, today_str):
    try:
        url = f"http://api.fund.eastmoney.com/f10/lsjz?fundCode={code}&pageIndex=1&pageSize=5"
        headers = {'Referer': 'http://fundf10.eastmoney.com/', 'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=3)
        data = r.json()
        if data and 'Data' in data and 'LSJZList' in data['Data']:
            for item in data['Data']['LSJZList']:
                if item['FSRQ'] != today_str:
                    return float(item['DWJZ'])
    except:
        pass
    return None


@st.cache_data(ttl=1, show_spinner=False)
# === 3. 增强版：获取实时数据 (核心函数) ===
def fetch_fund_data_core(code, channel):
    # 默认返回值 (防止报错)
    default_res = {
        'live_price': 0.0, 'base_nav': 0.0, 'est_rate': 0.0, 
        'nav_date': '-', 'source': 'Error'
    }
    
    try:
        # 针对 场外基金 (使用天天基金估值接口)
        if "场外" in channel:
            ts = int(time.time() * 1000)
            url = f"http://fundgz.1234567.com.cn/js/{code}.js?rt={ts}"
            
            # === 关键修正：添加 Headers ===
            r = requests.get(url, headers=get_headers(), timeout=5)
            
            if r.status_code == 200:
                text = r.text
                if "jsonpgz" in text:
                    # 解析 JSONP
                    content = re.findall(r'jsonpgz\((.*?)\);', text)
                    if content:
                        data = json.loads(content[0])
                        # 获取数据
                        est_val = float(data['gsz'])  # 实时估值
                        last_nav = float(data['dwjz']) # 昨日净值
                        est_rate = float(data['gszzl']) / 100 # 涨跌幅
                        last_date = data['gztime'].split(' ')[0] # 更新时间
                        
                        return {
                            'live_price': est_val,
                            'base_nav': last_nav,
                            'est_rate': est_rate,
                            'nav_date': last_date,
                            'source': '天天基金'
                        }
            else:
                print(f"Cloud fetch failed code={r.status_code}") # 调试日志
                
        # (可选) 针对场内基金或其他渠道...
        # 如果你之前写了场内基金的逻辑，请保留，这里只演示最容易出错的场外部分
        
    except Exception as e:
        print(f"Fetch Error {code}: {e}")
        
    return default_res

# ==========================================
# 5. UI 组件封装（无修改）
# ==========================================
def render_metric_card(label, value, delta_text, is_positive):
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
    """
    纯净版计算函数：接收数据快照，返回计算结果。
    完全不依赖 st.session_state，方便在后台线程运行。
    """
    rows = []
    t_d, t_a, t_v = 0.0, 0.0, 0.0
    today_str = str(datetime.now().date())

    # 内部使用的处理函数
    def process_row(row):
        c, ch = row['code'], row['channel']
        cache_key = f"{c}_{today_str}"

        # 1. 尝试从快照中读缓存
        cached_item = cache_snapshot.get(cache_key)

        if cached_item:
            d = cached_item
            updated = True
        else:
            # 2. 无缓存，发起网络请求
            d = fetch_fund_data_core(c, ch)
            updated = ("场外" in ch and d.get('nav_date') == today_str)

        # 3. 计算
        live, base, sh, cst = d['live_price'], d['base_nav'], float(row['shares']), float(row['cost'])
        val = live * sh
        day_gain = (live - base) * sh
        acc_gain = (live - cst) * sh
        rate_str = f"{d['est_rate'] * 100:+.2f}%" + (" (已更新)" if updated else "")

        return {
            "result": {
                "基金代码": c, "基金名称": row['name'], "渠道": ch, "持仓成本": cst, "持有份额": sh,
                "持仓金额": val, "最新净值": live, "今日盈亏": day_gain, "总盈亏": acc_gain,
                "涨跌幅": rate_str, "数据源": d['source']
            },
            "stats": (day_gain, acc_gain, val),
            "cache_update": (cache_key, d) if updated and not cached_item else None
        }

    # 使用多线程加速请求
    # 这里不需要太激进，5个线程足够，保证稳定性
    with ThreadPoolExecutor(max_workers=5) as executor:
        # 提交任务
        futures = [executor.submit(process_row, row) for _, row in current_df.iterrows()]

        # 收集结果
        for future in futures:
            try:
                data = future.result()
                rows.append(data["result"])
                dg, ag, v = data["stats"]
                t_d += dg;
                t_a += ag;
                t_v += v

                # 如果有新数据，更新传进来的快照（注意：这里只是更新局部变量，需要返回给主线程）
                if data["cache_update"]:
                    k, val = data["cache_update"]
                    cache_snapshot[k] = val
            except:
                pass

    # 排序
    rows.sort(key=lambda x: x['持仓金额'], reverse=True)

    # 返回: 显示用的行数据, 统计数据, 更新后的缓存字典
    return rows, t_d, t_a, t_v, cache_snapshot


# ==========================================
# 6. 主要 Fragment（无修改）
# ==========================================
# ==========================================
# 6. 主要 Fragment (修改版：包含编辑模式开关)
# ==========================================

# ==========================================
# 6. 主要 Fragment (修复宽度参数版)
# ==========================================
def sidebar_fragment():
    st.header("⚡ 控制台")
    st.divider()
    # 1. 编辑模式开关
    st.toggle("✏️ 编辑模式", key="edit_mode_toggle")

    st.divider()

    # 2. 添加新基金
    with st.expander("➕ 添加新基金", expanded=False):
        new_code = st.text_input("基金代码", key="sb_new_code", placeholder="6位数字")
        new_cost = st.number_input("持仓成本价", key="sb_new_cost", value=0.0, step=0.0001, format="%.4f")
        new_shares = st.number_input("持有份额", key="sb_new_shares", value=0.0, step=0.01, format="%.2f")

        fund_name = fast_get_name(new_code) if new_code.strip() else ""
        if fund_name:
            st.success(f"已查询：{fund_name}")
        elif new_code.strip():
            st.caption("正在查询...")

        # === 修改点 1：use_container_width -> width="stretch" ===
        if st.button("确认添加", width="stretch"):
            if len(new_code.strip()) != 6:
                st.error("代码错误")
            elif new_cost <= 0 or new_shares <= 0:
                st.error("数值错误")
            elif not fund_name:
                st.error("查询失败")
            else:
                df = load_portfolio()
                if new_code in df['code'].values:
                    st.warning("已存在")
                else:
                    new_row = {
                        "code": new_code.zfill(6), "name": fund_name, "channel": "场外(支付宝)",
                        "cost": new_cost, "shares": new_shares, "confirm_days": guess_confirm_days(fund_name)
                    }
                    save_portfolio_df(pd.concat([df, pd.DataFrame([new_row])], ignore_index=True))
                    st.success(f"已添加")
                    time.sleep(1)
                    st.rerun()

    st.divider()

    # 3. 发起交易
    with st.expander("💸 发起交易", expanded=False):
        current_df = load_portfolio()
        if not current_df.empty:
            opts = current_df.apply(lambda x: f"{x['name']} ({x['code']})", axis=1).tolist()
            sel = st.selectbox("标的", opts, key="sb_trade_sel")
            row = current_df.iloc[opts.index(sel)]

            c_days = int(row.get('confirm_days', 1))
            rt = fetch_fund_data_core(row['code'], row['channel'])

            st.caption(f"当前净值: **{rt['live_price']:.4f}** (T+{c_days})")

            ts = st.radio("时间", ["15:00前", "15:00后"], horizontal=True, label_visibility="collapsed",
                          key="sb_trade_ts")
            t_date = datetime.now().date() + (timedelta(days=1) if "15:00后" in ts else timedelta(days=0))

            c1, c2 = st.columns(2)
            act = c1.selectbox("方向", ["买入", "卖出"], key="sb_trade_act")
            mod = c2.selectbox("单位", ["金额", "份额"], key="sb_trade_mod")
            val = st.number_input("数值", 1.0, step=100.0, key="sb_trade_val")

            # === 修改点 2：use_container_width -> width="stretch" ===
            if st.button("🔴 提交委托", width="stretch", type="primary"):
                add_transaction({
                    "submit_date": str(datetime.now().date()), "trade_date": str(t_date),
                    "confirm_date": str(t_date + timedelta(days=c_days)),
                    "code": row['code'], "name": row['name'], "type": "buy" if act == "买入" else "sell",
                    "mode": "amount" if mod == "金额" else "share", "value": val, "status": "pending",
                    "channel": row['channel']
                })
                st.success("✅ 已提交")
        else:
            st.info("请先添加基金")


# 初始化后台执行器
if 'bg_executor' not in st.session_state:
    st.session_state.bg_executor = ThreadPoolExecutor(max_workers=1)


@st.fragment(run_every=1)
def dashboard_live_fragment():
    now_ts = time.time()

    # 1. 初始化状态
    if 'last_display_data' not in st.session_state:
        st.session_state.last_display_data = ([], 0.0, 0.0, 0.0)
    if 'pending_future' not in st.session_state:
        st.session_state.pending_future = None
    if 'last_fetch_time' not in st.session_state:
        st.session_state.last_fetch_time = 0

    # 2. 检查后台任务
    if st.session_state.pending_future:
        if st.session_state.pending_future.done():
            try:
                rows, t_d, t_a, t_v, new_cache = st.session_state.pending_future.result()
                st.session_state.last_display_data = (rows, t_d, t_a, t_v)
                st.session_state.finalized_cache.update(new_cache)
                st.session_state.last_fetch_time = now_ts
            except Exception as e:
                print(f"Background update failed: {e}")
            finally:
                st.session_state.pending_future = None

    # 3. 触发新任务 (间隔 > 4秒)
    if not st.session_state.pending_future:
        if (now_ts - st.session_state.last_fetch_time >= 4) or (not st.session_state.last_display_data[0]):
            current_df = load_portfolio()
            cache_snapshot = dict(st.session_state.finalized_cache)
            future = st.session_state.bg_executor.submit(
                calculate_dashboard_data, current_df, cache_snapshot
            )
            st.session_state.pending_future = future

    # 4. 渲染 UI
    rows, t_d, t_a, t_v = st.session_state.last_display_data

    c1, c2 = st.columns([8, 2])
    c1.caption(f"⚡ 实时监控: {datetime.now().strftime('%H:%M:%S')}")

    k1, k2, k3 = st.columns(3)
    with k1:
        render_metric_card("今日盈亏", f"{t_d:+.2f}", "今日波动", t_d >= 0)
    with k2:
        render_metric_card("历史盈亏", f"{t_a:+.2f}", "累计收益", t_a >= 0)
    with k3:
        render_metric_card("总资产", f"{t_v:,.0f}", "当前市值", True)

    st.write("")
    if not rows:
        if st.session_state.pending_future:
            st.info("🚀 正在极速加载数据...")
        else:
            st.info("暂无持仓，请在左侧添加基金。")
        return

    df = pd.DataFrame(rows)

    def color_val(val):
        return f'color: #ff4d4f; font-weight: bold' if val > 0 else f'color: #2cc995; font-weight: bold' if val < 0 else 'color: #e0e0e0'

    all_columns = ["基金代码", "基金名称", "渠道", "持有份额", "持仓成本", "最新净值", "涨跌幅", "今日盈亏", "总盈亏",
                   "持仓金额", "数据源"]
    col_config = {col: st.column_config.TextColumn(col, width="small") for col in all_columns}
    col_config["基金名称"] = st.column_config.TextColumn("基金名称", width=300)
    col_config["数据源"] = st.column_config.TextColumn("数据源", width="small")

    st.dataframe(
        df.style
        .set_table_styles([
            {'selector': 'th', 'props': [('text-align', 'left'), ('border-bottom', '1px solid #41424b !important'),
                                         ('background-color', '#1e1e1e !important')]},
            {'selector': 'td', 'props': [('text-align', 'left')]}
        ])
        .map(color_val, subset=['今日盈亏', '总盈亏'])
        .map(lambda x: 'color: #ff4d4f; font-weight:bold' if "+" in str(x)
        else 'color: #2cc995; font-weight:bold' if "-" in str(x)
        else 'color:#888' if "更新" in str(x)
        else 'color: #e0e0e0', subset=['涨跌幅'])
        .format({"持仓成本": "{:.4f}", "持有份额": "{:.2f}", "持仓金额": "{:,.0f}", "最新净值": "{:.4f}",
                 "今日盈亏": "{:+.2f}", "总盈亏": "{:+.2f}"}),

        # === 核心修改：use_container_width=True 改为 width="stretch" ===
        width="stretch",
        # =========================================================

        height=(len(df) + 1) * 35 + 3,
        hide_index=True,
        column_order=all_columns,
        column_config=col_config
    )


def dashboard_edit_fragment():
    # 1. 主动准备数据
    current_df = load_portfolio()

    # 准备缓存快照
    if 'finalized_cache' not in st.session_state:
        st.session_state.finalized_cache = {}
    cache_snapshot = dict(st.session_state.finalized_cache)

    # 2. 调用计算函数 (保持数据热度)
    rows, t_d, t_a, t_v, _ = calculate_dashboard_data(current_df, cache_snapshot)

    # 3. 渲染编辑界面
    st.caption("✏️ 编辑模式: 直接修改下方表格，修改后自动保存。")

    if current_df.empty:
        st.info("暂无持仓数据，请在侧边栏添加。")
        return

    # === 核心修改：动态计算表格高度 ===
    # (行数 + 1个表头 + 1个添加行) * 35像素
    # 这样可以保证所有数据行 + 底部的添加行都能直接显示，不需要滚动
    table_height = (len(current_df) + 2) * 35 + 3

    # 使用 data_editor 让表格可编辑
    edited_df = st.data_editor(
        current_df,
        column_config={
            "code": "基金代码",
            "name": "基金名称",
            "channel": st.column_config.SelectboxColumn("渠道", options=["场外(支付宝)", "场内(证券)", "场内(借用)"],
                                                        required=True),
            "cost": st.column_config.NumberColumn("持仓成本", min_value=0.0, format="%.4f"),
            "shares": st.column_config.NumberColumn("持有份额", min_value=0.0, format="%.2f"),
            "confirm_days": st.column_config.NumberColumn("确认天数(T+N)", min_value=0, step=1, format="%d"),
        },
        column_order=["code", "name", "channel", "cost", "shares", "confirm_days"],
        hide_index=True,
        width="stretch",  # 保持之前的宽度修复
        height=table_height,  # <--- 关键：应用动态高度，撑开表格
        num_rows="dynamic",  # 允许添加/删除行
        key="portfolio_editor"
    )

    # 4. 自动保存逻辑
    if not edited_df.equals(current_df):
        try:
            # 过滤掉空行
            edited_df = edited_df[edited_df["code"].notna() & (edited_df["code"] != "")]
            save_portfolio_df(edited_df)
            st.toast("✅ 持仓已更新", icon="💾")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"保存失败: {e}")


def transaction_manager_fragment():
    st.subheader("交易管理")
    trans = load_transactions()
    pend = [t for t in trans if t['status'] == 'pending']
    if not pend:
        st.info("🎉 暂无待处理交易")
        return
    now = str(datetime.now().date())
    cols = st.columns([3, 1, 2, 1, 1])
    cols[0].caption("标的/方向")
    cols[1].caption("状态")
    cols[2].caption("预估详情")
    cols[3].caption("结算")
    cols[4].caption("撤销")
    for i, t in enumerate(pend):
        c1, c2, c3, c4, c5 = st.columns([3, 1, 2, 1, 1])
        color = "red" if t['type'] == 'buy' else "green"
        c1.markdown(f"**{t['name']}** :{color}[{t['type']}]")
        c1.caption(f"{t['channel']} | {t['trade_date']}")
        ready = now >= t['confirm_date']
        # 修复核心：将单行三元表达式改为标准if-else（Streamlit强制要求）
        if ready:
            c2.success("✅ 可结算")
        else:
            c2.info(f"⏳ {t['confirm_date']}")
        unit = "元" if t['mode'] == 'amount' else "份"
        c3.caption(f"委托: {t['value']} {unit}")
        rt = fetch_fund_data_core(t['code'], t['channel'])
        if ready:
            rp = c3.number_input(f"净#{i}", value=float(rt['live_price']), format="%.4f", label_visibility="collapsed")
            if c4.button("确认", key=f"btn_ok_{i}"):
                pdf = load_portfolio()
                matches = pdf[pdf['code'] == t['code']]
                if matches.empty:
                    new_row = {"code": t['code'], "name": t['name'], "channel": t['channel'], "cost": 0.0, "shares": 0.0, "confirm_days": 1}
                    pdf = pd.concat([pdf, pd.DataFrame([new_row])], ignore_index=True)
                    idx = len(pdf)-1
                else:
                    idx = matches.index[0]
                cur = pdf.loc[idx]
                fs = float(t['value'])/rp if t['mode'] == "amount" else float(t['value'])
                fa = float(t['value']) if t['mode'] == "amount" else float(t['value'])*rp
                if t['type'] == 'buy':
                    ns = float(cur['shares']) + fs
                    nc = (float(cur['shares'])*float(cur['cost']) + fa)/ns if ns>0 else 0
                    pdf.at[idx, 'shares'], pdf.at[idx, 'cost'] = ns, nc
                else:
                    ns = float(cur['shares']) - fs
                    pdf.at[idx, 'shares'] = ns if ns>0 else 0
                save_portfolio_df(pdf)
                save_json(TRANSACTION_FILE, [x for x in trans if x != t])
                st.toast("结算完成"); time.sleep(1); st.rerun()
        else:
            c4.write("-")
        if c5.button("🗑️", key=f"btn_del_{i}"):
            save_json(TRANSACTION_FILE, [x for x in trans if x != t])
            st.toast("已撤销"); time.sleep(0.5); st.rerun()


# ==========================================
# 7. 页面主入口 (无需改动)
# ==========================================
with st.sidebar:
    sidebar_fragment()

st.title("🏦 基金实盘驾驶舱")

tab1, tab2 = st.tabs(["📊 资产全览", "📝 交易管理"])

with tab1:
    # 依然监听 sidebar 里的 key="edit_mode_toggle"
    if st.session_state.get("edit_mode_toggle", False):
        dashboard_edit_fragment()
    else:
        dashboard_live_fragment()

with tab2:
    transaction_manager_fragment()
