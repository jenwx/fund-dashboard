🏦 基金实盘驾驶舱 (Fund Dashboard)一个基于 Streamlit 构建的现代化基金实盘监控与管理系统。支持 Google Sheets 云端数据同步，完美解决 Streamlit Cloud 重启导致数据丢失的问题。专为中国场外基金（支付宝/天天基金）及场内 ETF 设计。✨ 核心功能☁️ 云端数据同步：集成 Google Sheets API，无论部署在哪里，数据永久保存，永不丢失。⚡ 极速实时行情：智能接入天天基金、东财、腾讯等多源接口。抗干扰优化：内置随机 User-Agent 和静默容错机制，有效解决云端 IP 封锁问题。智能兜底：当场外估值缺失时（如 QDII），自动借用场内 ETF 行情。📊 资产全景监控：实时计算今日盈亏、持仓市值、累计收益。精确的涨跌幅计算（优先使用实时净值差，估值仅作参考）。🛠️ 强大的控制台：手风琴交互：互斥式侧边栏设计，操作逻辑清晰流畅。交易管理：支持买入/卖出记录，自动加权计算持仓成本。观察模式：支持 0 成本/0 份额添加基金，仅作行情观察。💻 双模运行：本地模式：支持配置本地代理（VPN）连接 Google 服务。云端模式：自动识别环境，直连海外服务器。📸 界面预览(建议在此处上传你的运行截图，放在 images/ 目录下)资产全览交易管理🚀 快速部署 (Streamlit Cloud) - 推荐这是最省心的方式，免费且无需维护服务器。1. 准备工作Fork 本仓库到你的 GitHub。在 Google Drive 创建一个新的电子表格：将 Sheet1 重命名为 portfolio。新建一个工作表，重命名为 transactions。在 Google Cloud Console 启用 Google Sheets API，创建 Service Account 并下载 JSON 密钥。关键步骤：在你的 Google 表格点击右上角“共享”，将 Service Account 的邮箱（xxx@xxx.iam.gserviceaccount.com）添加为 编辑者 (Editor)。2. 配置 Secrets在 Streamlit Cloud 的应用设置页 (App Settings -> Secrets) 中，填入以下内容：Ini, TOML[connections.gsheets]
spreadsheet = "https://docs.google.com/spreadsheets/d/你的表格ID/edit"
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
(将下载的 JSON 文件内容对应填入即可)3. 修改代码配置打开 app.py，确保顶部配置如下（云端部署不需要代理）：Python# app.py 第 5 行
IS_LOCAL = False 
4. 启动点击 Deploy，系统会自动安装 requirements.txt 中的依赖并启动应用。💻 本地开发运行如果你在中国大陆地区本地运行，需要解决 Google API 连接问题。克隆项目：Bashgit clone https://github.com/你的用户名/fund-dashboard.git
cd fund-dashboard
安装依赖：Bashpip install -r requirements.txt
配置本地 Secrets：在项目根目录创建 .streamlit/secrets.toml，填入与上面相同的 Google Sheets 配置。开启本地代理加速：修改 app.py 顶部配置，填入你的 VPN 端口号：Python# app.py
IS_LOCAL = True  # 开启本地代理模式
PROXY_PORT = "7890" # 修改为你梯子的端口 (如 Clash 通常是 7890/7897)
运行：Bashstreamlit run app.py
📂 数据迁移指南如果你之前使用的是旧版（本地 JSON 存储），可以通过内置工具一键迁移到 Google Sheets：确保项目根目录下有 portfolio.json 和 transactions.json。启动应用，在侧边栏点击 "🚚 数据迁移 (本地 -> 云端)"。点击 "🚀 一键上传本地数据"。提示成功后，即可删除本地 JSON 文件。🛠️ 技术栈Frontend: StreamlitData Processing: PandasDatabase: Google Sheets (via st-gsheets-connection)Network: Requests (with custom headers & proxy logic)
