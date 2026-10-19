"""Host-only accounting checks; no simulation dependencies imported."""
import asyncio
import unittest

from internal_timing import Timeline, ActionQueue, difference, instrument_source


class FakeClock:
    value = 0.0

    def __call__(self):
        return self.value


class AccountingTests(unittest.TestCase):
    def test_nested_scopes_partition_including_open_scope(self):
        clock = FakeClock()
        timeline = Timeline(clock, clock)
        start = timeline.snapshot()
        clock.value = 1
        with timeline.scope("outer"):
            clock.value = 3
            with timeline.scope("inner"):
                clock.value = 6
                open_snapshot = timeline.snapshot()
                self.assertEqual(open_snapshot[1]["inner"], 3)
            clock.value = 10
        end = timeline.snapshot()
        parts = difference(end[1], start[1])
        self.assertEqual(parts, {"unattributed": 1, "outer": 6, "inner": 3})
        self.assertEqual(sum(parts.values()), end[0] - start[0])
        self.assertEqual(timeline.inclusive["outer"], 9)

    def test_overlapping_windows_are_separately_partitioned(self):
        clock = FakeClock()
        timeline = Timeline(clock, clock)
        first = timeline.snapshot()
        clock.value = 1
        second = timeline.snapshot()
        with timeline.scope("physics"):
            clock.value = 4
        first_end = timeline.snapshot()
        clock.value = 5
        second_end = timeline.snapshot()
        self.assertEqual(sum(difference(first_end[1], first[1]).values()), 4)
        self.assertEqual(sum(difference(second_end[1], second[1]).values()), 4)
        self.assertEqual(timeline.wall["physics"], 3)

    def test_queue_preserves_join_barrier(self):
        async def exercise():
            queue = ActionQueue()
            await queue.put((0, "action"))
            waiter = asyncio.create_task(queue.join())
            await asyncio.sleep(0)
            self.assertFalse(waiter.done())
            self.assertEqual(await queue.get(), (0, "action"))
            queue.task_done()
            await waiter
        asyncio.run(exercise())

    def test_source_changes_refuse_unknown_anchors(self):
        with self.assertRaises(AssertionError):
            instrument_source("print('changed upstream')")


if __name__ == "__main__":
    unittest.main()
