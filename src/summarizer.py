import re

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


SYSTEM_PROMPT = (
    "你是一位严谨的微波与无线技术领域的学术助手。"
    "用户会给你一篇 IEEE 期刊论文的英文标题、作者和英文摘要。"
    "请用{lang}输出两部分内容，严格遵守下面的格式，不要任何额外说明或前后缀：\n"
    "标题：论文标题的{lang}翻译\n"
    "摘要：用1-2句话简述文章的核心研究内容，不展开方法细节与具体结果，不超过{max_chars}字\n"
    "注意：第一行必须以“标题：”开头，第二行必须以“摘要：”开头。"
)

TRANSLATE_PROMPT = (
    "你是一位严谨的微波与无线技术领域的学术助手。"
    "请将下面列出的英文论文标题逐条翻译为{lang}。"
    "输出格式：每行一条，行首为编号加句点，空格后跟译文，不要输出原文和任何其他内容。"
    "示例输出：\n1. 中文译文一\n2. 中文译文二"
)


class Summarizer:
    def __init__(self, config, logger):
        self.logger = logger
        llm = config.get("llm", {})
        self.base_url = llm.get("base_url", "https://api.deepseek.com/v1").rstrip("/")
        self.api_key = llm.get("api_key", "")
        self.model = llm.get("model", "deepseek-chat")
        self.temperature = llm.get("temperature", 0.3)
        self.max_tokens = llm.get("max_tokens", 200)
        self.lang = llm.get("summary_lang", "中文")
        self.max_chars = llm.get("max_summary_chars", 100)
        self.timeout = 60.0

        if not self.api_key:
            raise ValueError("LLM api_key 未配置")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    def _call_api(self, messages, max_tokens=None):
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    def summarize(self, article):
        title = article.title or "(无标题)"
        authors = article.authors or "(未知作者)"
        abstract = article.abstract or "(无摘要，请基于标题判断)"

        system = SYSTEM_PROMPT.format(lang=self.lang, max_chars=self.max_chars)
        user = (
            f"标题: {title}\n"
            f"作者: {authors}\n"
            f"摘要: {abstract}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            raw = self._call_api(messages)
            return self._parse(raw, title)
        except Exception as e:
            self.logger.error(f"总结失败 [{article.article_number}]: {e}")
            return {"chinese_title": "", "summary": f"(总结失败: {e})"}

    def translate_titles(self, titles):
        """批量翻译标题。返回 {原文: 译文} 字典。"""
        if not titles:
            return {}
        system = TRANSLATE_PROMPT.format(lang=self.lang)
        lines = [f"{i+1}. {t}" for i, t in enumerate(titles)]
        user = "\n".join(lines)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        translate_max_tokens = min(60 * len(titles) + 100, 2000)
        try:
            raw = self._call_api(messages, max_tokens=translate_max_tokens)
            result = self._parse_translation_lines(raw, titles)
            self.logger.info(f"批量翻译 {len(titles)} 个标题，成功 {len(result)} 个")
            return result
        except Exception as e:
            self.logger.error(f"批量翻译标题失败: {e}")
            return {}

    @staticmethod
    def _parse(raw, fallback_title):
        chinese_title = ""
        summary = ""
        m_title = re.search(r"标题[:：]\s*(.+)", raw)
        m_summary = re.search(r"摘要[:：]\s*([\s\S]+)", raw)
        if m_title:
            chinese_title = m_title.group(1).strip()
        if m_summary:
            summary = m_summary.group(1).strip()
        if not chinese_title:
            chinese_title = fallback_title
        return {"chinese_title": chinese_title, "summary": summary}

    @staticmethod
    def _parse_translation_lines(raw, titles):
        result = {}
        for line in raw.strip().split("\n"):
            m = re.match(r"(\d+)[.、:：]\s*(.+)", line.strip())
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(titles):
                    result[titles[idx]] = m.group(2).strip()
        return result
