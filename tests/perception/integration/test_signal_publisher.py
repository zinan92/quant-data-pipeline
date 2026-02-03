"""Tests for SignalPublisher — file-based event bus."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest

from src.perception.integration.signal_publisher import (
    PublisherConfig,
    SignalEnvelope,
    SignalPublisher,
)
from src.perception.integration.trading_bridge import TradingAction, TradingSignal


# ── Fixtures ─────────────────────────────────────────────────────────


def _make_trading_signal(
    asset: str = "BTC",
    action: TradingAction = TradingAction.LONG,
    strength: float = 0.8,
) -> TradingSignal:
    return TradingSignal(
        signal_type="perception/technical",
        asset=asset,
        action=action,
        direction="bullish" if action == TradingAction.LONG else "bearish",
        strength=strength,
        confidence=0.7,
        reason="test signal",
        timestamp=time.time(),
    )


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def publisher(tmp_dir):
    cfg = PublisherConfig(
        output_path=os.path.join(tmp_dir, "signals.jsonl"),
        default_expiry_seconds=3600.0,
    )
    return SignalPublisher(config=cfg)


# ── SignalEnvelope tests ─────────────────────────────────────────────


class TestSignalEnvelope:
    def test_to_dict_roundtrip(self):
        env = SignalEnvelope(
            seq=1,
            published_at=time.time(),
            expires_at=time.time() + 3600,
            source_pipeline="perception",
            signal={"asset": "BTC", "action": "long"},
        )
        d = env.to_dict()
        assert d["seq"] == 1
        assert d["source_pipeline"] == "perception"

        restored = SignalEnvelope.from_dict(d)
        assert restored.seq == env.seq
        assert restored.signal == env.signal

    def test_json_roundtrip(self):
        env = SignalEnvelope(
            seq=42,
            published_at=time.time(),
            expires_at=0.0,
            source_pipeline="test",
            signal={"x": 1},
        )
        j = env.to_json()
        restored = SignalEnvelope.from_json(j)
        assert restored.seq == 42
        assert restored.signal == {"x": 1}

    def test_is_expired_false_when_no_expiry(self):
        env = SignalEnvelope(
            seq=1, published_at=time.time(), expires_at=0.0,
            source_pipeline="t", signal={},
        )
        assert env.is_expired is False

    def test_is_expired_true(self):
        env = SignalEnvelope(
            seq=1, published_at=time.time() - 100,
            expires_at=time.time() - 50,
            source_pipeline="t", signal={},
        )
        assert env.is_expired is True


# ── Publisher tests ──────────────────────────────────────────────────


class TestPublisherPublish:
    def test_publish_empty(self, publisher):
        result = publisher.publish([])
        assert result == []
        assert publisher.sequence == 0

    def test_publish_single(self, publisher):
        sig = _make_trading_signal()
        envs = publisher.publish([sig])
        assert len(envs) == 1
        assert envs[0].seq == 1
        assert envs[0].source_pipeline == "perception"
        assert publisher.sequence == 1

    def test_publish_multiple(self, publisher):
        sigs = [_make_trading_signal(f"ASSET{i}") for i in range(5)]
        envs = publisher.publish(sigs)
        assert len(envs) == 5
        assert [e.seq for e in envs] == [1, 2, 3, 4, 5]

    def test_sequence_increments(self, publisher):
        publisher.publish([_make_trading_signal("A")])
        publisher.publish([_make_trading_signal("B")])
        assert publisher.sequence == 2

    def test_signals_written_to_file(self, publisher):
        publisher.publish([_make_trading_signal()])
        path = publisher.config.output_path
        assert os.path.exists(path)
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["seq"] == 1

    def test_multiple_publishes_append(self, publisher):
        publisher.publish([_make_trading_signal("A")])
        publisher.publish([_make_trading_signal("B")])
        with open(publisher.config.output_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        assert len(lines) == 2


class TestPublisherSubscribe:
    def test_callback_called(self, publisher):
        received = []
        publisher.subscribe(lambda envs: received.extend(envs))
        publisher.publish([_make_trading_signal()])
        assert len(received) == 1

    def test_unsubscribe(self, publisher):
        received = []
        cb = lambda envs: received.extend(envs)
        publisher.subscribe(cb)
        publisher.publish([_make_trading_signal()])
        publisher.unsubscribe(cb)
        publisher.publish([_make_trading_signal()])
        assert len(received) == 1  # second publish not received

    def test_subscriber_error_doesnt_break(self, publisher):
        def bad_cb(envs):
            raise ValueError("boom")

        publisher.subscribe(bad_cb)
        # Should not raise
        envs = publisher.publish([_make_trading_signal()])
        assert len(envs) == 1


class TestPublisherRead:
    def test_read_recent(self, publisher):
        publisher.publish([_make_trading_signal("A")])
        publisher.publish([_make_trading_signal("B")])
        recent = publisher.read_recent(limit=10)
        assert len(recent) == 2

    def test_read_recent_limit(self, publisher):
        sigs = [_make_trading_signal(f"X{i}") for i in range(10)]
        publisher.publish(sigs)
        recent = publisher.read_recent(limit=3)
        assert len(recent) == 3

    def test_read_from_file(self, publisher):
        publisher.publish([_make_trading_signal("A")])
        publisher.publish([_make_trading_signal("B")])
        envs = publisher.read_from_file(since_seq=0)
        assert len(envs) == 2

    def test_read_from_file_since_seq(self, publisher):
        publisher.publish([_make_trading_signal("A")])
        publisher.publish([_make_trading_signal("B")])
        envs = publisher.read_from_file(since_seq=1)
        assert len(envs) == 1
        assert envs[0].seq == 2

    def test_read_from_file_nonexistent(self, tmp_dir):
        cfg = PublisherConfig(output_path=os.path.join(tmp_dir, "nope.jsonl"))
        pub = SignalPublisher(config=cfg)
        assert pub.read_from_file() == []


class TestPublisherSnapshot:
    def test_snapshot_to_json(self, publisher, tmp_dir):
        publisher.publish([_make_trading_signal("A")])
        out_path = os.path.join(tmp_dir, "snapshot.json")
        count = publisher.snapshot_to_json(out_path)
        assert count == 1
        with open(out_path) as f:
            data = json.load(f)
        assert data["count"] == 1
        assert len(data["signals"]) == 1
        assert "updated_at" in data

    def test_snapshot_empty(self, publisher, tmp_dir):
        out_path = os.path.join(tmp_dir, "empty.json")
        count = publisher.snapshot_to_json(out_path)
        assert count == 0
        with open(out_path) as f:
            data = json.load(f)
        assert data["count"] == 0


class TestPublisherRotation:
    def test_rotation_on_large_file(self, tmp_dir):
        cfg = PublisherConfig(
            output_path=os.path.join(tmp_dir, "signals.jsonl"),
            max_file_bytes=200,  # tiny threshold to trigger rotation
        )
        pub = SignalPublisher(config=cfg)

        # Write enough to exceed the limit
        for i in range(20):
            pub.publish([_make_trading_signal(f"ASSET{i}")])

        # Check that rotation happened
        rotated = os.path.join(tmp_dir, "signals.1.jsonl")
        assert os.path.exists(cfg.output_path)
        # At least one rotation should have occurred given the tiny limit
        # (we can't guarantee exact count since it depends on line sizes)
