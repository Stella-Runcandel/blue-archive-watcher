"""Pipeline tests for bounded queue behavior."""
import unittest

from app.services.monitor_pipeline import FrameQueue


class PipelineTests(unittest.TestCase):
    """Validate ring buffer bounds and drops."""

    def test_frame_queue_drop(self):
        """FrameQueue drops oldest frames when full."""
        queue = FrameQueue(maxlen=2)
        queue.put("a")
        queue.put("b")
        queue.put("c")
        self.assertEqual(queue.dropped, 1)
        self.assertEqual(queue.get(), "b")
        self.assertEqual(queue.get(), "c")
        self.assertIsNone(queue.get(timeout=0.01))
