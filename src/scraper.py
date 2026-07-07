import random
import re
import time
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError, Error as PWError


@dataclass
class Article:
    article_number: str
    title: str
    authors: str
    abstract: str
    url: str
    journal: str = ""
    first_author: str = ""

    def to_dict(self):
        return {
            "article_number": self.article_number,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "url": self.url,
            "journal": self.journal,
            "first_author": self.first_author,
        }


class IEEEScraper:
    BASE = "https://ieeexplore.ieee.org"

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        s = config.get("scraping", {})
        self.headless = s.get("headless", True)
        self.channel = s.get("channel") or None
        self.delay = s.get("delay_seconds", 3)
        self.timeout = s.get("page_timeout_ms", 60000)
        self.max_articles = s.get("max_articles", 50)

    def _human_delay(self):
        time.sleep(self.delay + random.uniform(0, 1.5))

    def _goto_with_retry(self, page, url, wait_until="domcontentloaded", retries=3):
        """带重试的 page.goto，覆盖网络超时与连接重置。

        Playwright 的 TimeoutError（ERR_TIMED_OUT）与 Error（ERR_CONNECTION_RESET 等）
        均视为可重试。指数退避：4/8/16 秒。
        """
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                page.goto(url, wait_until=wait_until)
                return
            except (PWTimeoutError, PWError) as e:
                last_exc = e
                self.logger.warning(
                    f"页面加载失败（第 {attempt}/{retries} 次）: {url} -> {e.__class__.__name__}"
                )
                if attempt < retries:
                    wait = 2 ** (attempt + 1)  # 4, 8, 16
                    self.logger.info(f"等待 {wait}s 后重试...")
                    time.sleep(wait)
        raise last_exc

    def scrape_journal(self, journal, keywords=None, is_new_fn=None):
        """抓取期刊 Early Access 文章列表，按关键词分组。

        返回 (matched_articles, other_articles)：
        - matched: 标题命中关键词的新文章，已抓取摘要
        - other: 未命中的新文章，仅含标题

        is_new_fn: 可选回调，接收 article_number 返回 bool。提供时只处理新文章。
        """
        name = journal["name"]
        puno = journal["punumber"]
        display_name = journal.get("abbr") or name
        self.logger.info(f"开始抓取期刊: {name} (punumber={puno})")

        matched, others = [], []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, channel=self.channel)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = ctx.new_page()
            page.set_default_timeout(self.timeout)

            articles = self._get_early_access_list(page, puno, display_name)
            if not articles:
                self.logger.warning(f"期刊 {name} 未找到 Early Access 文章")
                browser.close()
                return [], []

            articles = articles[: self.max_articles]
            self.logger.info(f"期刊 {name} 共发现 {len(articles)} 篇 Early Access 文章")

            if is_new_fn:
                articles = [a for a in articles if is_new_fn(a.article_number)]
                self.logger.info(f"过滤后新文章 {len(articles)} 篇")

            if not articles:
                browser.close()
                return [], []

            kw_lower = [k.lower().strip() for k in (keywords or []) if k.strip()]
            for a in articles:
                if kw_lower and self._match_keywords(a.title, kw_lower):
                    matched.append(a)
                else:
                    others.append(a)
            self.logger.info(
                f"期刊 {name}: 匹配 {len(matched)} 篇，其他 {len(others)} 篇"
            )

            for i, a in enumerate(matched, 1):
                meta = self._fetch_meta(page, a.article_number)
                if meta:
                    a.abstract = meta.get("abstract", "").strip()
                    authors_list = meta.get("authors", [])
                    a.authors = self._format_authors(authors_list)
                    a.first_author = self._format_first_author(authors_list)
                    if authors_list:
                        self.logger.debug(
                            f"首作者原始结构 [{a.article_number}]: {authors_list[0]}"
                        )
                    detail_title = meta.get("title", "").strip()
                    if detail_title:
                        a.title = detail_title
                    self.logger.info(
                        f"[匹配 {i}/{len(matched)}] 已抓取摘要: {a.title[:60]}"
                    )
                else:
                    self.logger.warning(
                        f"[匹配 {i}/{len(matched)}] 抓取摘要失败: {a.article_number}"
                    )

            browser.close()

        self.logger.info(f"期刊 {name} 抓取完成")
        return matched, others

    def _get_early_access_list(self, page, puno, name):
        """从 Early Access 列表页提取文章（含标题），返回 List[Article]。"""
        recent_url = f"{self.BASE}/xpl/RecentIssue.jsp?punumber={puno}"
        self.logger.info(f"加载期刊主页: {recent_url}")
        self._goto_with_retry(page, recent_url)

        try:
            page.wait_for_selector("xpl-issue-list, .issue-tabs, xpl-root", timeout=20000)
        except PWTimeoutError:
            pass
        self._human_delay()

        ea_clicked = False
        locators = [
            lambda: page.get_by_role("tab", name="Early Access"),
            lambda: page.get_by_role("link", name="Early Access"),
            lambda: page.get_by_text("Early Access", exact=True),
            lambda: page.locator('a:has-text("Early Access")').first,
            lambda: page.locator('button:has-text("Early Access")').first,
        ]
        for loc_fn in locators:
            try:
                el = loc_fn()
                el.wait_for(state="visible", timeout=6000)
                el.click()
                ea_clicked = True
                self.logger.info("已点击 Early Access 标签")
                break
            except Exception:
                continue

        if not ea_clicked:
            self.logger.warning("未找到 Early Access 标签，尝试直接提取当前页文档链接")

        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PWTimeoutError:
            pass
        self._human_delay()

        try:
            page.wait_for_selector('a[href*="/document/"]', timeout=15000)
        except PWTimeoutError:
            pass

        items = page.eval_on_selector_all(
            'a[href*="/document/"]',
            r"""els => {
                const result = [];
                const seen = {};
                for (const e of els) {
                    const href = e.getAttribute('href') || '';
                    const m = href.match(/\/document\/(\d+)/);
                    if (!m) continue;
                    const num = m[1];
                    const text = (e.textContent || '').trim();
                    if (!(num in seen)) {
                        seen[num] = result.length;
                        result.push({num: num, text: text});
                    } else {
                        if (text.length > result[seen[num]].text.length) {
                            result[seen[num]].text = text;
                        }
                    }
                }
                return result;
            }""",
        )
        articles = []
        for it in items or []:
            num = it.get("num", "")
            title = it.get("text", "").strip()
            if not num:
                continue
            articles.append(Article(
                article_number=num,
                title=title,
                authors="",
                abstract="",
                url=f"{self.BASE}/document/{num}",
                journal=name,
            ))
        self.logger.info(f"从列表页解析到 {len(articles)} 篇文章（含标题）")
        return articles

    def _fetch_meta(self, page, article_number):
        """打开文章详情页，返回 metadata dict 或 None。"""
        url = f"{self.BASE}/document/{article_number}"
        try:
            self._goto_with_retry(page, url)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except PWTimeoutError:
                pass

            meta = None
            try:
                page.wait_for_function(
                    "() => !!(window.xplGlobal && window.xplGlobal.document "
                    "&& window.xplGlobal.document.metadata)",
                    timeout=12000,
                )
                meta = page.evaluate(
                    "() => (window.xplGlobal && window.xplGlobal.document "
                    "&& window.xplGlobal.document.metadata) || null"
                )
            except Exception as e:
                self.logger.debug(f"xplGlobal 等待/读取失败 {article_number}: {e}")

            if not meta:
                meta = self._extract_meta_from_html(page, article_number)
            return meta
        except Exception as e:
            self.logger.error(f"抓取文章 {article_number} 异常: {e}")
            return None

    def _extract_meta_from_html(self, page, article_number):
        try:
            content = page.content()
            m = re.search(
                r"xplGlobal\.document\.metadata\s*=\s*(\{.*?\});",
                content,
                re.DOTALL,
            )
            if m:
                import json
                return json.loads(m.group(1))
        except Exception as e:
            self.logger.debug(f"HTML 正则提取失败 {article_number}: {e}")
        return None

    @staticmethod
    def _match_keywords(title, kw_lower):
        if not title or not kw_lower:
            return False
        title_lower = title.lower()
        for kw in kw_lower:
            pattern = r'\b' + re.escape(kw) + r's?\b'
            if re.search(pattern, title_lower):
                return True
        return False

    @staticmethod
    def _format_authors(authors):
        if not authors:
            return ""
        names = []
        for a in authors:
            if isinstance(a, dict):
                names.append(a.get("preferredName") or a.get("name") or "")
            elif isinstance(a, str):
                names.append(a)
        return ", ".join([n for n in names if n])

    @staticmethod
    def _format_first_author(authors):
        """提取第一作者名字与单位，用 '. ' 分隔。"""
        if not authors or not isinstance(authors, list):
            return ""
        first = authors[0]
        if not isinstance(first, dict):
            return ""
        name = (first.get("preferredName") or first.get("name") or "").strip()
        aff = ""
        for key in ("affiliation", "affiliationName"):
            val = first.get(key)
            if isinstance(val, str) and val.strip():
                aff = val.strip()
                break
            if isinstance(val, list) and val:
                item = val[0]
                if isinstance(item, dict):
                    for sub_key in ("name", "affiliationName", "affiliation"):
                        sub_val = item.get(sub_key)
                        if isinstance(sub_val, str) and sub_val.strip():
                            aff = sub_val.strip()
                            break
                elif isinstance(item, str) and item.strip():
                    aff = item.strip()
                if aff:
                    break
        if not aff:
            affs = first.get("affiliations")
            if isinstance(affs, list) and affs:
                item = affs[0]
                if isinstance(item, dict):
                    for sub_key in ("name", "affiliationName", "affiliation"):
                        sub_val = item.get(sub_key)
                        if isinstance(sub_val, str) and sub_val.strip():
                            aff = sub_val.strip()
                            break
                elif isinstance(item, str) and item.strip():
                    aff = item.strip()
        parts = [p for p in (name, aff) if p]
        return ". ".join(parts)
