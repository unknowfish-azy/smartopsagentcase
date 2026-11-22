"""数字人情绪识别输入（P2-8 收口）。

对外只暴露 `engine` 模块；使用方式：

    from app.emotion import engine
    result = engine.recognize("今天告警全恢复了，真开心")
    engine.get_emotion_info()
"""

from . import engine

__all__ = ["engine"]
