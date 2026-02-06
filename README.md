# FrameTrace >.<
Visual state monitoring & detection tool

by Stella Group ✨

“Stop staring at the screen. Let FrameTrace do it.”

👀 What is FrameTrace?

FrameTrace is a profile-based visual monitoring desktop app.

It watches a live video input (via OBS Virtual Camera), compares what it sees against user-defined visual references, and alerts you when a specific visual state appears.

It is:

🧠 deterministic (no mystery logic)

🧱 modular (layers matter)

🧹 safe with files (nothing important gets overwritten)

😴 boring to extend (this is a feature)

FrameTrace is not game-specific, not cloud-based, and not AI hype.
It’s a local, power-user tool for people who want control.
## Detection + artifact persistence

- Monitoring now runs detection directly against in-memory camera frames (`frame_comp_from_array`) to avoid per-cycle disk round-trips.
- File-based detection (`frame_comp`) remains available for manual/debug workflows that intentionally operate on `captures/latest.png`.
- Capture persistence is optional and throttled via `core/detector.py::ARTIFACT_POLICY`.
  - `capture_snapshot_interval_s`: minimum interval for periodic snapshots.
  - `capture_retention_count`: max number of `captures/snapshot_*.png` files retained.
  - `debug_retention_count`: max number of `debug/match_*.png` files retained.
- A forced capture snapshot is also recorded when a new detection event starts, then retention is enforced.
