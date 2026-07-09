# Daily IEEE Early Access 日报

每日自动抓取 IEEE 期刊 Early Access 文章，用 DeepSeek 生成中文总结，推送到企业微信群，辅助判断是否需要精读。

## 工作流程

1. Playwright 驱动系统 Edge 打开期刊 Recent Issue 页 → 点击 Early Access 标签
2. 提取每篇文章的标题 / 作者 / 摘要（从文章页 `xplGlobal.document.metadata`）
3. 调用 DeepSeek 生成结构化中文总结（研究问题 / 方法 / 创新点 / 阅读建议+评分）
4. 按研究方向拆分：一篇文章可命中多个方向，分别推送到对应企业微信群机器人（超 4096 字节自动分条）
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

1. 复制配置模板：

   ```powershell
   Copy-Item config.example.yaml config.yaml
   ```

2. 编辑 `config.yaml`，填入你的真实 API key 和 webhook。

配置项说明：

- `journals`：监控的期刊列表（name + punumber）。添加新期刊只需追加条目
- `directions`：研究方向列表，每个方向独立关键词 + 独立推送机器人（期刊共享）
  - `name`：方向名称（显示在推送标题前缀，如 `[预失真]`）
  - `keywords`：标题整词匹配关键词（大小写不敏感、允许复数 s、OR 逻辑）。一篇文章可命中多个方向，分别推送到对应群
  - `notifier.webhook`：该方向对应的企业微信群机器人 webhook
  - `notifier.notify_when_empty`：该方向无匹配文章时是否推送提示
- `scraping.channel`：浏览器通道，`msedge` 用系统 Edge（免下载），可改 `chrome` 或留空
- `llm`：LLM 配置（OpenAI 兼容接口）。切换 provider 只需改 base_url / api_key / model

> 注意：`config.yaml` 含 API key 与 webhook key，已被 `.gitignore` 忽略，**请勿手动取消忽略或提交到公开仓库**。

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

注册后任务具备两个保障机制，确保到点准时推送而非等到手动唤醒屏幕：

- **`WakeToRun`**：到点主动唤醒系统（覆盖笔记本 S0 Modern Standby 低功耗空闲状态，此时屏幕关闭、CPU 进入 DRIPS，普通任务会被挂起）
- **`StartWhenAvailable`**：唤醒失败或系统当时关机时，下次可用时自动补跑

> 笔记本 Modern Standby 对 `WakeToRun` 的支持依机型/固件而异。为稳妥起见，**插电过夜**时建议将 AC 电源的睡眠超时设为「从不」（屏幕仍会自动关闭，不影响省电）：
> ```powershell
> powercfg /change standby-timeout-ac 0   # 仅影响插电状态，电池模式仍会正常睡眠
> ```
> 这样系统保持清醒、Task Scheduler 必然准时触发，`WakeToRun` 则作为「系统因故睡了」的兜底。两者叠加即可保证 08:00 准点推送。

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
├── config.yaml              # 配置（含凭据，本地生成，不提交）
├── config.example.yaml      # 配置模板（可提交）
├── requirements.txt
├── run.py                   # 入口编排
├── run_daily.bat            # 定时任务启动脚本
├── register_task.ps1        # 注册 Windows 定时任务
├── src/
│   ├── scraper.py           # Playwright 抓取（系统 Edge）
│   ├── summarizer.py        # DeepSeek 总结
│   ├── notifier.py          # 企业微信推送（多方向，每方向独立机器人）
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

## 如何添加 / 修改研究方向

研究方向定义在 `config.yaml` 的 `directions` 下，每个方向独立关键词与推送机器人，期刊对所有方向共享。一篇文章可同时命中多个方向，会分别推送到对应群。

新增一个方向（含独立机器人）只需追加条目：

```yaml
directions:
  - name: "有源电路"
    keywords:
      - "Amplifier"
      - "Doherty"
      - "MMIC"
      - "PA"
    notifier:
      type: "wecom_bot"
      webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
      notify_when_empty: true
  # 新增方向示例：
  - name: "天线"
    keywords:
      - "antenna"
      - "MIMO"
    notifier:
      type: "wecom_bot"
      webhook: "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_OTHER_KEY"
      notify_when_empty: true
```

> 抓取与 LLM 总结只执行一次（按所有方向关键词的并集判断是否抓取详情页摘要），随后按各方向关键词分别路由推送，避免重复抓取。

## 切换 LLM

`llm` 配置兼容任何 OpenAI 接口格式的服务：

```yaml
llm:
  provider: "qwen"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "YOUR_QWEN_KEY"
  model: "qwen-plus"
```
