import json
import os
from datetime import datetime


class StateManager:
    def __init__(self, state_file, logger=None):
        self.state_file = state_file
        self.logger = logger
        self.data = {"seen": {}}
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                if "seen" not in self.data:
                    self.data = {"seen": self.data}
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"状态文件读取失败，重置: {e}")
                self.data = {"seen": {}}

    def _save(self):
        tmp = self.state_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_file)

    def filter_new(self, article_ids):
        """返回尚未见过的 article id 列表（保持输入顺序）。"""
        seen = self.data.get("seen", {})
        return [aid for aid in article_ids if aid not in seen]

    def is_new(self, article_id):
        """返回单个 article id 是否未见。"""
        seen = self.data.get("seen", {})
        return article_id not in seen

    def mark_seen(self, article_id, journal="", title="", matched=False):
        today = datetime.now().strftime("%Y-%m-%d")
        self.data.setdefault("seen", {})[article_id] = {
            "date": today,
            "journal": journal,
            "title": title,
            "matched": matched,
        }
        self._save()

    def mark_seen_batch(self, article_ids):
        today = datetime.now().strftime("%Y-%m-%d")
        seen = self.data.setdefault("seen", {})
        for aid in article_ids:
            seen[aid] = today
        self._save()
