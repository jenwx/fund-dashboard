# 🏦 基金实盘 (Fund Dashboard)

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google%20Sheets-API-green?style=for-the-badge&logo=google-sheets&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)

一个基于 **Streamlit** 构建的现代化基金实盘监控与管理系统。
核心特色是支持 **Google Sheets 云端双向同步**，完美解决 Streamlit Cloud 重启导致本地数据丢失的问题，支持实时估值与盈亏分析。

---

## ✨ 核心功能

* **☁️ 云端数据同步**：集成 `st-gsheets-connection`，无论部署在云端还是本地，数据永久保存在 Google Sheets，永不丢失。
* **⚡ 极速实时行情**：
    * 智能接入天天基金、东财、腾讯等多源接口。
    * **抗干扰优化**：内置随机 User-Agent 和静默容错机制，有效解决云端 IP 封锁问题。
    * **智能兜底**：当场外估值缺失时（如 QDII），自动借用场内 ETF 行情。
    * **精准计算**：优先使用实时净值差计算涨跌，官方估值仅作参考。
* **📊 资产全景监控**：
    * 实时计算今日盈亏、持仓市值、累计收益。
    * 支持暗黑模式 (Dark Mode) UI 深度适配。
* **🛠️ 强大的控制台**：
    * **交易管理**：支持买入/卖出记录，自动加权计算持仓成本。
    * **观察模式**：支持 0 成本/0 份额添加基金，仅作行情观察。
* **💻 双模运行**：
    * **本地模式**：支持配置本地代理（VPN）连接 Google 服务。
    * **云端模式**：自动识别环境，直连海外服务器。

---

## 📸 界面预览

![Dashboard](https://img.acyaer.nyc.mn/file/fund-dashboard/1770715882446_image.png) 

---

## 🚀 快速部署 (Streamlit Cloud) - 推荐

这是最省心的方式，免费且无需维护服务器。

### 1. 准备工作
1.  **Fork** 本仓库到你的 GitHub。
2.  在 **Google Drive** 创建一个新的电子表格：
    * 将底部的 `Sheet1` 重命名为 **`portfolio`** (必须小写)。
    * 点击 `+` 新建一个工作表，重命名为 **`transactions`** (必须小写)。
3.  在 [Google Cloud Console](https://console.cloud.google.com/) 启用 **Google Sheets API** 和 **Google Drive API**。
4.  创建 **Service Account** 并下载 **JSON 密钥文件**。
5.  **关键步骤**：打开你的 Google 表格，点击右上角 **Share (共享)**，将 Service Account 的邮箱（`xxx@xxx.iam.gserviceaccount.com`）添加为 **编辑者 (Editor)**。

### 2. 配置 Secrets
在 Streamlit Cloud 的应用设置页 (**App Settings** -> **Secrets**) 中，填入以下内容（将 JSON 内容对应填入）：

```toml
[connections.gsheets]
spreadsheet = "[https://docs.google.com/spreadsheets/d/你的表格ID/edit](https://docs.google.com/spreadsheets/d/你的表格ID/edit)"
type = "service_account"
project_id = "你的project_id"
private_key_id = "你的private_key_id"
private_key = "-----BEGIN PRIVATE KEY-----\n..."
client_email = "你的服务账号邮箱"
client_id = "你的client_id"
auth_uri = "[https://accounts.google.com/o/oauth2/auth](https://accounts.google.com/o/oauth2/auth)"
token_uri = "[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)"
auth_provider_x509_cert_url = "[https://www.googleapis.com/oauth2/v1/certs](https://www.googleapis.com/oauth2/v1/certs)"
client_x509_cert_url = "你的client_x509_cert_url"
```
### 3. 代码配置检查
打开 app.py，确保顶部配置如下（云端部署不需要代理）：

```Python
# app.py 第 7 行左右
IS_LOCAL = False
```
### 4. 启动
点击 Deploy，系统会自动安装 requirements.txt 中的依赖并启动应用。

# 💻 本地开发运行
如果你在中国大陆地区本地运行，由于 Google 服务被墙，你需要配置本地代理。

### 1. 环境安装
```Bash
# 1. 克隆项目
git clone [https://github.com/jenwx/fund-dashboard.git](https://github.com/jenwx/fund-dashboard.git)
cd fund-dashboard

# 2. 创建并激活虚拟环境 (可选)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt
```
### 2. 配置本地 Secrets
在项目根目录创建 .streamlit 文件夹，并在其中新建 secrets.toml 文件，填入与上面云端部署相同的 Google Sheets 配置。

### 3. 开启本地代理加速
修改 app.py 顶部配置，填入你的 VPN 端口号（例如 Clash 通常是 7890/7897）：

```Python
# app.py
IS_LOCAL = True  # 开启本地代理模式
PROXY_PORT = "7890" # 修改为你梯子的端口
```
4. 运行
```Bash
streamlit run app.py
```
