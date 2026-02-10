# 🏦 基金实盘 (Fund Dashboard)

一个基于 Python Streamlit 的现代化基金实盘监控与管理系统。支持场外基金（支付宝/天天基金）和场内 ETF 的实时估值、持仓管理及盈亏分析。

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=for-the-badge&logo=python&logoColor=white)

## ✨ 主要功能

* **⚡ 极速行情**：多线程并发请求，支持秒级实时估值更新（接入天天基金/东财/腾讯/新浪接口）。
* **📊 资产全览**：自动计算持仓市值、今日盈亏、累计收益及日内波动。
* **🛡️ 智能防拦截**：内置随机 User-Agent 和请求伪装，有效解决云端部署时的接口反爬问题。
* **📝 持仓管理**：
    * 支持**添加观察仓**（0持仓份额）。
    * **编辑模式**：像 Excel 一样直接修改成本和份额。
    * **交易管理**：模拟买入/卖出结算，自动更新持仓成本。
* **📱 移动端适配**：完美适配手机浏览器，随时随地查看净值。
* **🌙 暗黑模式**：深度优化的 UI 界面，护眼且专业。

## 🚀 快速部署 (Streamlit Cloud) - **推荐**

最简单的方式是使用 Streamlit 官方提供的免费云服务。

1.  **准备工作**：
    * 确保你的 GitHub 仓库中有 `app.py` 和 `requirements.txt` 文件。
    * `requirements.txt` 内容应包含：
        ```text
        streamlit
        pandas
        requests
        ```

2.  **开始部署**：
    * 访问 [Streamlit Community Cloud](https://share.streamlit.io/) 并登录。
    * 点击右上角 **"New app"**。
    * 选择你的 GitHub 仓库 (`fund-dashboard`)。
    * **Main file path** 填写 `app.py`。
    * 点击 **"Deploy"**。

3.  **等待构建**：
    * 系统会自动安装依赖，大约 1-2 分钟后即可访问你的专属链接。

---

## 💻 本地运行

如果你想在自己的电脑上运行（数据最安全，永久保存）：

1.  **克隆仓库**：
    ```bash
    git clone [https://github.com/你的用户名/fund-dashboard.git](https://github.com/你的用户名/fund-dashboard.git)
    cd fund-dashboard
    ```

2.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```

3.  **启动应用**：
    ```bash
    streamlit run app.py
    ```

4.  **访问**：
    打开浏览器访问 `http://localhost:8501`。

---

## ⚠️ 关于数据保存的重要说明

本项目默认使用 **JSON 文件 (`portfolio.json`)** 在本地存储数据。

* **本地运行**：数据永久保存在你的电脑硬盘里，**不会丢失**。
* **Streamlit Cloud 部署**：
    * 由于云容器的特性，当应用重启或长时间未访问休眠后，**JSON 文件会被重置**，导致添加的基金丢失。
    * **解决方案**：如果需要长期在云端使用且保留数据，建议后续对接 Google Sheets 或 Supabase 数据库（需修改代码）。
    * **当前建议**：目前版本最适合作为**本地看板**使用，或者在云端仅用于临时查看行情。

---

## 🛠️ 项目结构

```text
fund-dashboard/
├── app.py                # 主程序代码
├── requirements.txt      # 依赖包列表
├── portfolio.json        # 持仓数据（自动生成）
├── transactions.json     # 交易记录（自动生成）
└── README.md             # 说明文档
