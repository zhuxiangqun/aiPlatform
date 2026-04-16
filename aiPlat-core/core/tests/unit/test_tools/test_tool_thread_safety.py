import threading

from core.apps.tools.base import CalculatorTool


def test_tool_stats_thread_safety():
    tool = CalculatorTool()

    def worker():
        # Directly update stats to simulate concurrent calls
        for _ in range(1000):
            tool._update_stats(True, 0.001)  # type: ignore[attr-defined]

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stats = tool.get_stats()
    assert stats["call_count"] == 10000
    assert stats["success_count"] == 10000

