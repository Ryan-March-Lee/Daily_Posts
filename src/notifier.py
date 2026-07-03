import httpx
from datetime import datetime


WECOM_BOT_LIMIT = 4096


class WeComNotifier:
    def __init__(self, config, logger, direction=None):
        self.logger = logger
        # 多方向支持：notifier 配置内嵌在 direction 内；兼容旧式顶层 notifier
        if direction is not None:
            self.direction_name = direction.get("name", "")
            n = direction.get("notifier", {})
        else:
            self.direction_name = ""
            n = config.get("notifier", {})
        self.webhook = n.get("webhook", "")
        self.notify_when_empty = n.get("notify_when_empty", True)
        self.timeout = 15.0
        if not self.webhook:
            raise ValueError("企业微信 webhook 未配置")

    def _send_one(self, content):
        payload = {"msgtype": "markdown", "markdown": {"content": content}}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(self.webhook, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"企业微信返回错误: {data}")
            return True

    def _build_full_block(self, item):
        """匹配文章全量块：英文标题+中文标题+第一作者及单位+链接+摘要"""
        a = item["article"]
        summ = item["summary"]
        title_en = a["title"]
        title_zh = summ.get("chinese_title", "") if isinstance(summ, dict) else ""
        summary = summ.get("summary", "") if isinstance(summ, dict) else (summ or "")
        url = a["url"]
        first_author = a.get("first_author", "") or "（未获取）"
        return (
            f"英文标题:\n**{title_en}**\n"
            f"中文标题:\n{title_zh}\n"
            f"第一作者及单位:\n{first_author}\n"
            f"链接:\n{url}\n"
            f"摘要:\n{summary}"
        )

    def _split_into_messages(self, header, items, block_fn):
        """按企业微信 4096 字节上限拆分。"""
        messages = []
        current = header + "\n\n"
        for item in items:
            block = block_fn(item)
            block_with_sep = block + "\n\n" + "-" * 34 + "\n\n"
            if (len(current.encode("utf-8")) + len(block_with_sep.encode("utf-8"))) > WECOM_BOT_LIMIT:
                if current.strip():
                    messages.append(current.rstrip())
                current = block_with_sep
            else:
                current += block_with_sep
        if current.strip():
            messages.append(current.rstrip())
        return messages

    def _send_messages(self, messages):
        total = len(messages)
        self.logger.info(f"将发送 {total} 条企业微信消息")
        for i, msg in enumerate(messages, 1):
            try:
                self._send_one(msg)
                self.logger.info(f"企业微信消息 {i}/{total} 发送成功")
            except Exception as e:
                self.logger.error(f"企业微信消息 {i} 发送失败: {e}")

    def notify(self, matched_items, journal_name=None):
        """仅推送匹配文章全量；无匹配时推送提示。

        两种情况：
        A. 无匹配文章 → 推送"今日无与语料库匹配的论文"提示
        B. 有匹配 → 推送匹配组（全量）
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        jname = journal_name or (matched_items[0]["article"].get("journal", "") if matched_items else "")
        tag = f"[{self.direction_name}] " if self.direction_name else ""

        # 情况 A：无匹配文章
        if not matched_items:
            if self.notify_when_empty:
                msg = (
                    f"## {tag}{jname} Early Access 日报 {date_str}\n"
                    f"今日无与语料库匹配的论文"
                )
                try:
                    self._send_one(msg)
                    self.logger.info("无匹配文章，已发送提示")
                except Exception as e:
                    self.logger.error(f"提示发送失败: {e}")
            else:
                self.logger.info("无匹配文章，跳过推送")
            return

        # 情况 B：有匹配文章
        header = (
            f"## {tag}{jname} Early Access 日报 {date_str}\n"
            f"★ 语料库匹配 {len(matched_items)} 篇"
        )
        messages = self._split_into_messages(header, matched_items, self._build_full_block)
        self._send_messages(messages)

    def notify_empty_summary(self, empty_jnames, date_str=None):
        """某方向下所有无匹配期刊的汇总提示（一条消息）。
        受 notify_when_empty 开关控制。
        """
        if not empty_jnames:
            return
        if not self.notify_when_empty:
            self.logger.info(
                f"方向[{self.direction_name}] {len(empty_jnames)} 个期刊无匹配，跳过汇总推送"
            )
            return
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        tag = f"[{self.direction_name}] " if self.direction_name else ""
        msg = (
            f"## {tag}Early Access 日报 {date_str}\n"
            f"以下期刊无匹配:\n"
            f"{'、'.join(empty_jnames)}"
        )
        try:
            self._send_one(msg)
            self.logger.info(
                f"方向[{self.direction_name}] 无匹配期刊汇总已发送: {empty_jnames}"
            )
        except Exception as e:
            self.logger.error(f"汇总提示发送失败: {e}")

    def notify_error(self, error_msg):
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        tag = f"[{self.direction_name}] " if self.direction_name else ""
        msg = (
            f"## {tag}IEEE Early Access 任务异常\n"
            f"时间: {date_str}\n"
            f"错误: {error_msg}"
        )
        try:
            self._send_one(msg)
        except Exception as e:
            self.logger.error(f"异常通知发送失败: {e}")
