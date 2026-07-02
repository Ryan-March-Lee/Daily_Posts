# Daily IEEE Early Access 日报

每日自动抓取 IEEE 期刊 Early Access 文章，用 DeepSeek 生成中文总结，推送到企业微信群，辅助判断是否需要精读。

## 工作流程

1. Playwright 驱动系统 Edge 打开期刊 Recent Issue 页 → 点击 Early Access 标签
2. 提取每篇文章的标题 / 作者 / 摘要（从文章页 `xplGlobal.document.metadata`）
3. 调用 DeepSeek 生成结构化中文总结（研究问题 / 方法 / 创新点 / 阅读建议+评分）
4. 通过企业微信群机器人推送 Markdown 消息（超 4096 字节自动分条）
5. 本地 `data/seen_articles.json` 记录已推文章，仅推送新增

## 环境与依赖

- Python 3.12（独立 conda 环境 `daily_posts`，与 base 隔离）
- 使用系统已安装的 Microsoft Edge，**无需下载专用浏览器**
- 依赖见 `requirements.txt`：playwright / httpx / pyyaml / tenacity

## 安装

```powershell
# 创建独立环境（已完成）
conda create -n daily_posts python=3.12 -y

# 安装依赖
C:\My_Document\Anaconda\envs\daily_posts\python.exe -m pip install -r requirements.txt

# 无需执行 playwright install —— config.yaml 中 channel="msedge" 直接用系统 Edge
```

## 配置

所有配置在 `config.yaml`：

- `journals`：监控的期刊列表（name + punumber）。添加新期刊只需追加条目
- `scraping.channel`：浏览器通道，`msedge` 用系统 Edge（免下载），可改 `chrome` 或留空
- `llm`：LLM 配置（OpenAI 兼容接口）。切换 provider 只需改 base_url / api_key / model
- `notifier.webhook`：企业微信群机器人 webhook
- `notifier.notify_when_empty`：无新文章时是否推送提示

> 注意：`config.yaml` 含 API key 与 webhook key，请勿提交至公开仓库。

## 手动运行

```powershell
# 用 daily_posts 环境的 Python 运行
C:\My_Document\Anaconda\envs\daily_posts\python.exe run.py
```

## 定时任务

每天 08:00 自动执行，注册方式（需管理员权限的 PowerShell）：

```powershell
.\register_task.ps1
```

管理命令：

```powershell
Get-ScheduledTask -TaskName 'Daily_IEEE_EarlyAccess'     # 查看状态
Start-ScheduledTask -TaskName 'Daily_IEEE_EarlyAccess'    # 立即触发一次
Unregister-ScheduledTask -TaskName 'Daily_IEEE_EarlyAccess' -Confirm:$false  # 删除
```

## 调试

- `config.yaml` 中 `scraping.headless: false` 可观察浏览器实际操作
- `logging.level: DEBUG` 输出详细日志
- 日志文件：`logs/daily.log`（滚动，保留 5 个 2MB 文件）
- 去重状态：`data/seen_articles.json`，删除此文件可重新推送全部文章

## 目录结构

```
Daily_Posts/
├── config.yaml              # 配置（含凭据）
├── requirements.txt
├── run.py                   # 入口编排
├── run_daily.bat            # 定时任务启动脚本
├── register_task.ps1        # 注册 Windows 定时任务
├── src/
│   ├── scraper.py           # Playwright 抓取（系统 Edge）
│   ├── summarizer.py        # DeepSeek 总结
│   ├── notifier.py          # 企业微信推送
│   ├── state.py             # 去重
│   └── logger.py            # 日志
├── data/seen_articles.json  # 已推文章记录
└── logs/daily.log           # 运行日志
```

## 如何添加新期刊

在 `config.yaml` 的 `journals` 下追加：

```yaml
journals:
  - name: "IEEE Transactions on Microwave Theory and Techniques"
    punumber: "22"
  - name: "IEEE Microwave and Wireless Technology Letters"
    punumber: "9944983"
  - name: "IEEE Transactions on Circuits and Systems I: Regular Papers"
    punumber: "8919"
  - name: "IEEE Transactions on Circuits and Systems II: Express Briefs"
    punumber: "8920"
```

punumber 在期刊 IEEE Xplore 主页 URL 的 `punumber=` 参数中获取。

## 切换 LLM

`llm` 配置兼容任何 OpenAI 接口格式的服务：

```yaml
llm:
  provider: "qwen"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "YOUR_QWEN_KEY"
  model: "qwen-plus"
```
