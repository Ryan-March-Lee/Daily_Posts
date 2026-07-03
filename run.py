import os
import sys
import traceback

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.logger import setup_logger
from src.state import StateManager
from src.scraper import IEEEScraper
from src.summarizer import Summarizer
from src.notifier import WeComNotifier


def load_config(path="config.yaml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.yaml")
    config = load_config(config_path)

    logger = setup_logger(config)
    logger.info("=" * 50)
    logger.info("IEEE Early Access 日报任务启动")

    try:
        directions = config.get("directions", [])
        if not directions:
            raise ValueError("未配置任何研究方向（directions）")

        # 各方向关键词（保留顺序），以及全方向并集（用于抓取，确保任一方向命中都能拿到摘要）
        direction_keywords = [
            [k.lower().strip() for k in d.get("keywords", []) if k.strip()]
            for d in directions
        ]
        union_keywords = []
        seen_kw = set()
        for kws in direction_keywords:
            for k in kws:
                if k not in seen_kw:
                    seen_kw.add(k)
                    union_keywords.append(k)
        logger.info(f"研究方向: {[d.get('name', '') for d in directions]}")
        logger.info(f"关键词并集（用于抓取匹配）: {union_keywords}")

        # 每个方向一个 notifier
        notifiers = [
            WeComNotifier(config, logger, direction=d) for d in directions
        ]

        state_file = os.path.join(base_dir, config["state"]["file"])
        state = StateManager(state_file, logger)
        scraper = IEEEScraper(config, logger)
        summarizer = Summarizer(config, logger)

        # 收集阶段：每方向维护 有匹配期刊列表 与 无匹配期刊名列表
        dir_matched = [[] for _ in directions]
        dir_empty_jnames = [[] for _ in directions]

        for journal in config.get("journals", []):
            try:
                matched, others = scraper.scrape_journal(
                    journal,
                    keywords=union_keywords,
                    is_new_fn=state.is_new,
                )
            except Exception as e:
                logger.error(f"抓取期刊 {journal['name']} 失败: {e}")
                for nt in notifiers:
                    nt.notify_error(f"抓取 {journal['name']} 失败: {e}")
                continue

            logger.info(
                f"期刊 {journal['name']}: 匹配 {len(matched)} 篇，其他 {len(others)} 篇"
            )

            # 匹配文章：LLM 全量总结一次（摘要与方向无关，跨方向共享）
            summarized = []
            for a in matched:
                summary = summarizer.summarize(a)
                summarized.append((a, summary))
                state.mark_seen(a.article_number)

            # 非匹配文章：仅标记已见，不推送
            for a in others:
                state.mark_seen(a.article_number)

            jname = journal.get("abbr") or journal.get("name", "")

            # 按方向收集：一篇文章可命中多个方向，进入对应多个群
            for idx, kw_lower in enumerate(direction_keywords):
                dir_items = [
                    {"article": a.to_dict(), "summary": s}
                    for (a, s) in summarized
                    if kw_lower and IEEEScraper._match_keywords(a.title, kw_lower)
                ]
                dname = directions[idx].get("name", "")
                logger.info(
                    f"方向 [{dname}] 期刊 {journal['name']}: 命中 {len(dir_items)} 篇"
                )
                if dir_items:
                    dir_matched[idx].append((jname, dir_items))
                else:
                    dir_empty_jnames[idx].append(jname)

        # 分发阶段：有匹配期刊逐条推送，无匹配期刊合并为一条汇总
        for idx, d in enumerate(directions):
            for jname, dir_items in dir_matched[idx]:
                notifiers[idx].notify(dir_items, journal_name=jname)
            if dir_empty_jnames[idx]:
                notifiers[idx].notify_empty_summary(dir_empty_jnames[idx])

        logger.info("任务完成")
    except Exception as e:
        logger.error(f"任务异常: {e}\n{traceback.format_exc()}")
        try:
            # 兜底：用顶层兜底 notifier（若 directions 已配置）通知所有方向群
            for d in config.get("directions", []):
                try:
                    nt = WeComNotifier(config, logger, direction=d)
                    nt.notify_error(str(e))
                except Exception:
                    pass
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
