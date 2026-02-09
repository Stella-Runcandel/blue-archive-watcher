"""SQLite storage layer for profiles, frames, references, and debug metadata.

Design:
 - SQLite stores metadata only (no image blobs).
 - Filesystem stores actual images in Data/Profiles/... and Data/Debug.
 - Each call opens a short-lived connection (thread-safe, WAL mode).
"""
from __future__ import annotations

import contextlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

def _db_path() -> Path:
    """Resolve SQLite DB path from environment or default."""
    return Path(os.environ.get("APP_DB_PATH", Path("Data") / "app.db"))


@dataclass(frozen=True)
class ProfileRecord:
    id: int
    name: str
    created_at: str
    icon_path: str | None
    camera_device: str | None
    target_fps: int | None
    detection_threshold: float | None


def init_db() -> None:
    """Initialize SQLite schema and enable WAL mode."""
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                icon_path TEXT,
                camera_device TEXT,
                target_fps INTEGER,
                detection_threshold REAL
            );
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS reference_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                frame_name TEXT,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS debug_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                reference_name TEXT,
                path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )


@contextlib.contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Yield a short-lived SQLite connection (thread-safe)."""
    conn = sqlite3.connect(_db_path(), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    """Return UTC timestamp string."""
    return datetime.utcnow().isoformat()


def list_profiles() -> list[str]:
    """Return profile names from SQLite."""
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT name FROM profiles ORDER BY LOWER(name)").fetchall()
    return [row["name"] for row in rows]


def get_profile(name: str) -> ProfileRecord | None:
    """Return profile record by name."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE name = ?",
            (name,),
        ).fetchone()
    if not row:
        return None
    return ProfileRecord(**dict(row))


def create_profile(name: str) -> None:
    """Create a profile record."""
    init_db()
    with connect() as conn:
        conn.execute(
            "INSERT INTO profiles (name, created_at) VALUES (?, ?)",
            (name, _now()),
        )


def delete_profile(name: str) -> None:
    """Delete a profile record."""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM profiles WHERE name = ?", (name,))


def update_profile_fields(
    name: str,
    *,
    icon_path: str | None = None,
    camera_device: str | None = None,
    target_fps: int | None = None,
    detection_threshold: float | None = None,
) -> None:
    """Update mutable fields on a profile record."""
    init_db()
    updates = []
    values: list[object] = []
    if icon_path is not None:
        updates.append("icon_path = ?")
        values.append(icon_path)
    if camera_device is not None:
        updates.append("camera_device = ?")
        values.append(camera_device)
    if target_fps is not None:
        updates.append("target_fps = ?")
        values.append(target_fps)
    if detection_threshold is not None:
        updates.append("detection_threshold = ?")
        values.append(detection_threshold)
    if not updates:
        return
    values.append(name)
    with connect() as conn:
        conn.execute(
            f"UPDATE profiles SET {', '.join(updates)} WHERE name = ?",
            values,
        )


def add_frame(profile_name: str, name: str, path: str) -> None:
    """Insert frame metadata for a profile."""
    profile = get_profile(profile_name)
    if not profile:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO frames (profile_id, name, path, created_at) VALUES (?, ?, ?, ?)",
            (profile.id, name, path, _now()),
        )


def list_frames(profile_name: str) -> list[str]:
    """List frame names for a profile."""
    profile = get_profile(profile_name)
    if not profile:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM frames WHERE profile_id = ? ORDER BY LOWER(name)",
            (profile.id,),
        ).fetchall()
    return [row["name"] for row in rows]


def delete_frame(profile_name: str, name: str) -> None:
    """Delete a frame metadata row."""
    profile = get_profile(profile_name)
    if not profile:
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM frames WHERE profile_id = ? AND name = ?",
            (profile.id, name),
        )


def add_reference(profile_name: str, name: str, path: str, frame_name: str | None) -> None:
    """Insert reference metadata for a profile."""
    profile = get_profile(profile_name)
    if not profile:
        return
    with connect() as conn:
        conn.execute(
            "INSERT INTO reference_entries (profile_id, frame_name, name, path, created_at) VALUES (?, ?, ?, ?, ?)",
            (profile.id, frame_name, name, path, _now()),
        )


def list_references(profile_name: str) -> list[str]:
    """List reference names for a profile."""
    profile = get_profile(profile_name)
    if not profile:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT name FROM reference_entries WHERE profile_id = ? ORDER BY LOWER(name)",
            (profile.id,),
        ).fetchall()
    return [row["name"] for row in rows]


def delete_reference(profile_name: str, name: str) -> None:
    """Delete a reference metadata row."""
    profile = get_profile(profile_name)
    if not profile:
        return
    with connect() as conn:
        conn.execute(
            "DELETE FROM reference_entries WHERE profile_id = ? AND name = ?",
            (profile.id, name),
        )


def get_reference_parent_frame(profile_name: str, ref_name: str) -> str | None:
    """Fetch parent frame name for a reference."""
    profile = get_profile(profile_name)
    if not profile:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT frame_name FROM reference_entries WHERE profile_id = ? AND name = ?",
            (profile.id, ref_name),
        ).fetchone()
    return row["frame_name"] if row else None


def add_debug_entry(
    profile_name: str | None,
    reference_name: str | None,
    path: str,
    size_bytes: int,
) -> None:
    """Insert debug metadata row."""
    profile_id = None
    if profile_name:
        profile = get_profile(profile_name)
        if profile:
            profile_id = profile.id
    with connect() as conn:
        conn.execute(
            "INSERT INTO debug_entries (profile_id, reference_name, path, size_bytes, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (profile_id, reference_name, path, size_bytes, _now()),
        )


def list_debug_entries(profile_name: str | None) -> list[sqlite3.Row]:
    """List debug entries, optionally filtered by profile."""
    with connect() as conn:
        if profile_name:
            profile = get_profile(profile_name)
            if not profile:
                return []
            rows = conn.execute(
                "SELECT * FROM debug_entries WHERE profile_id = ? ORDER BY created_at DESC",
                (profile.id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM debug_entries ORDER BY created_at DESC",
            ).fetchall()
    return rows


def delete_debug_entries(ids: Iterable[int]) -> None:
    """Delete debug metadata rows by id."""
    id_list = list(ids)
    if not id_list:
        return
    with connect() as conn:
        conn.execute(
            f"DELETE FROM debug_entries WHERE id IN ({','.join('?' for _ in id_list)})",
            id_list,
        )


def prune_debug_entries(max_bytes: int, max_count: int) -> list[str]:
    """Evict oldest debug entries to enforce size/count bounds. Returns removed file paths."""
    removed_paths: list[str] = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, path, size_bytes FROM debug_entries ORDER BY created_at ASC"
        ).fetchall()
        total_bytes = sum(row["size_bytes"] for row in rows)
        while rows and (total_bytes > max_bytes or len(rows) > max_count):
            row = rows.pop(0)
            removed_paths.append(row["path"])
            total_bytes -= row["size_bytes"]
            conn.execute("DELETE FROM debug_entries WHERE id = ?", (row["id"],))
    return removed_paths


def set_app_state(key: str, value: str | None) -> None:
    """Persist a single app state value."""
    init_db()
    with connect() as conn:
        if value is None:
            conn.execute("DELETE FROM app_state WHERE key = ?", (key,))
        else:
            conn.execute(
                "INSERT INTO app_state (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def get_app_state(key: str) -> str | None:
    """Fetch a stored app state value."""
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None
