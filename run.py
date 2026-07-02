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
        state_file = os.path.join(base_dir, config["state"]["file"])
        state = StateManager(state_file, logger)
        scraper = IEEEScraper(config, logger)
        summarizer = Summarizer(config, logger)
        notifier = WeComNotifier(config, logger)

        keywords = config.get("keywords", [])
        logger.info(f"关键词语料库: {keywords}")

        for journal in config.get("journals", []):
            try:
                matched, others = scraper.scrape_journal(
                    journal,
                    keywords=keywords,
                    is_new_fn=state.is_new,
                )
            except Exception as e:
                logger.error(f"抓取期刊 {journal['name']} 失败: {e}")
                notifier.notify_error(f"抓取 {journal['name']} 失败: {e}")
                continue

            logger.info(
                f"期刊 {journal['name']}: 匹配 {len(matched)} 篇，其他 {len(others)} 篇"
            )

            # 匹配文章：LLM 全量总结（中文标题 + 摘要）
            matched_items = []
            for a in matched:
                summary = summarizer.summarize(a)
                matched_items.append({"article": a.to_dict(), "summary": summary})
                state.mark_seen(a.article_number)

            # 非匹配文章：仅标记已见，不推送
            for a in others:
                state.mark_seen(a.article_number)

            jname = journal.get("abbr") or journal.get("name", "")
            notifier.notify(matched_items, journal_name=jname)

        logger.info("任务完成")
    except Exception as e:
        logger.error(f"任务异常: {e}\n{traceback.format_exc()}")
        try:
            notifier = WeComNotifier(config, logger)
            notifier.notify_error(str(e))
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
