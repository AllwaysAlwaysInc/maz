"""
Fibonacci Memory Librarian for CROW Chain
Adapted from ECHO Blockchain `fibonacci_librarian.py` for synchronous
ThreadingHTTPServer execution with automatic load-based head splitting,
Fibonacci scaling (3, 5, 8, 13, 21, 34, 55, 89, 144), and consolidation.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


FIBONACCI_THRESHOLDS = [3, 5, 8, 13, 21, 34, 55, 89, 144]


class LibrarianRole(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    SPECIALIZED = "specialized"
    COORDINATOR = "coordinator"


@dataclass
class LibrarianHead:
    head_id: str
    block_height: int
    block_hash: str
    last_updated: float = field(default_factory=time.time)
    status: str = "active"
    assigned_librarian: Optional[str] = None
    blocks_handled: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "head_id": self.head_id,
            "block_height": self.block_height,
            "block_hash": self.block_hash,
            "last_updated": self.last_updated,
            "status": self.status,
            "assigned_librarian": self.assigned_librarian,
            "blocks_handled": self.blocks_handled,
        }


class MemoryLibrarianWorker:
    """Lightweight synchronous worker representing a single MemoryLibrarian."""

    def __init__(self, librarian_id: str, role: LibrarianRole):
        self.librarian_id = librarian_id
        self.role = role
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.blocks_processed = 0
        self.created_at = time.time()

    def process_block(self) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.blocks_processed += 1

    def get_stats(self) -> Dict[str, Any]:
        return {
            "librarian_id": self.librarian_id,
            "role": self.role.value,
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "blocks_processed": self.blocks_processed,
        }


class FibonacciLibrarianSystem:
    """
    Distributed librarian system following a Fibonacci scaling pattern
    (3, 5, 8, 13, 21, 34, 55, 89, 144) to manage blockchain heads under load.
    """

    def __init__(self, fibonacci_thresholds: Optional[List[int]] = None):
        self.fibonacci_thresholds = list(fibonacci_thresholds or FIBONACCI_THRESHOLDS)
        self.librarians: Dict[str, MemoryLibrarianWorker] = {}
        self.heads: Dict[str, LibrarianHead] = {}
        self.librarian_head_assignments: Dict[str, Set[str]] = {}
        self.scaling_events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._create_librarian("librarian_1", LibrarianRole.PRIMARY)

    def _create_librarian(self, librarian_id: str, role: LibrarianRole) -> MemoryLibrarianWorker:
        worker = MemoryLibrarianWorker(librarian_id=librarian_id, role=role)
        self.librarians[librarian_id] = worker
        self.librarian_head_assignments[librarian_id] = set()
        return worker

    def _assign_head_to_librarian(self, head: LibrarianHead) -> str:
        head_counts = {
            lid: len(hset) for lid, hset in self.librarian_head_assignments.items()
        }
        librarian_id = min(head_counts.keys(), key=lambda lid: head_counts[lid])
        current_count = head_counts[librarian_id]

        # Scale up along Fibonacci thresholds when all existing librarians reach capacity
        threshold_idx = min(len(self.librarians) - 1, len(self.fibonacci_thresholds) - 1)
        active_threshold = self.fibonacci_thresholds[threshold_idx]
        if current_count >= active_threshold:
            next_index = len(self.librarians)
            next_fib = (
                self.fibonacci_thresholds[-1]
                if next_index >= len(self.fibonacci_thresholds)
                else self.fibonacci_thresholds[next_index]
            )
            librarian_id = f"librarian_{len(self.librarians) + 1}"
            self._create_librarian(librarian_id, LibrarianRole.SECONDARY)
            self.scaling_events.append({
                "event": "scale_up",
                "librarian_id": librarian_id,
                "librarian_count": len(self.librarians),
                "head_count": len(self.heads) + 1,
                "fibonacci_threshold": next_fib,
                "ts": time.time(),
            })

        self.librarian_head_assignments[librarian_id].add(head.head_id)
        head.assigned_librarian = librarian_id
        return librarian_id

    def register_head(self, head_id: str, block_height: int, block_hash: str) -> Optional[str]:
        with self._lock:
            if head_id in self.heads:
                head = self.heads[head_id]
                head.block_height = block_height
                head.block_hash = block_hash
                head.last_updated = time.time()
                return head.assigned_librarian
            head = LibrarianHead(
                head_id=head_id,
                block_height=block_height,
                block_hash=block_hash,
            )
            librarian_id = self._assign_head_to_librarian(head)
            self.heads[head_id] = head
            return librarian_id

    def record_block(self, head_id: str, block_height: int, block_hash: str) -> str:
        with self._lock:
            if head_id not in self.heads:
                head = LibrarianHead(head_id=head_id, block_height=block_height, block_hash=block_hash)
                lid = self._assign_head_to_librarian(head)
                self.heads[head_id] = head
            else:
                head = self.heads[head_id]
                head.block_height = block_height
                head.block_hash = block_hash
                head.last_updated = time.time()
                lid = head.assigned_librarian or "librarian_1"
            head.blocks_handled += 1
            worker = self.librarians.get(lid)
            if worker:
                worker.process_block()
            return lid

    def unregister_head(self, head_id: str) -> bool:
        with self._lock:
            if head_id not in self.heads:
                return False
            head = self.heads[head_id]
            if head.assigned_librarian and head.assigned_librarian in self.librarian_head_assignments:
                self.librarian_head_assignments[head.assigned_librarian].discard(head_id)
            del self.heads[head_id]
            self._consolidate_librarians_unlocked()
            return True

    def _consolidate_librarians_unlocked(self) -> None:
        if len(self.librarians) <= 1:
            return
        total_heads = sum(len(h) for h in self.librarian_head_assignments.values())
        librarians_needed = 1
        for i, threshold in enumerate(self.fibonacci_thresholds):
            if total_heads <= threshold:
                librarians_needed = i + 1
                break
        else:
            return

        librarians_needed = max(1, librarians_needed)
        if len(self.librarians) > librarians_needed:
            sorted_libs = sorted(
                self.librarian_head_assignments.items(),
                key=lambda x: len(x[1]),
            )
            keep = {"librarian_1"} | {lid for lid, _ in sorted_libs[-(librarians_needed - 1):]} if librarians_needed > 1 else {"librarian_1"}
            for lid, heads in sorted_libs:
                if lid in keep:
                    continue
                target_lid = next(iter(keep - {"librarian_1"})) if len(keep) > 1 else "librarian_1"
                for hid in heads:
                    if hid in self.heads:
                        self.librarian_head_assignments[target_lid].add(hid)
                        self.heads[hid].assigned_librarian = target_lid
                del self.librarians[lid]
                del self.librarian_head_assignments[lid]
            self.scaling_events.append({
                "event": "consolidate",
                "librarian_count": len(self.librarians),
                "head_count": total_heads,
                "ts": time.time(),
            })

    def get_system_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_requests = sum(w.total_requests for w in self.librarians.values())
            total_ok = sum(w.successful_requests for w in self.librarians.values())
            return {
                "librarianCount": len(self.librarians),
                "headCount": len(self.heads),
                "totalRequests": total_requests,
                "totalSuccessful": total_ok,
                "fibonacciThresholds": self.fibonacci_thresholds,
                "recentScalingEvents": self.scaling_events[-10:],
                "librarians": {
                    lid: {
                        **w.get_stats(),
                        "head_count": len(self.librarian_head_assignments.get(lid, set())),
                    }
                    for lid, w in self.librarians.items()
                },
            }


def _merkle_root(leaves: List[str]) -> Tuple[str, int]:
    if not leaves:
        return hashlib.sha256(b"").hexdigest(), 0
    layer = list(leaves)
    depth = 0
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [
            hashlib.sha256((layer[i] + layer[i + 1]).encode("ascii")).hexdigest()
            for i in range(0, len(layer), 2)
        ]
        depth += 1
    return layer[0], depth


def run_fibonacci_block_stress_test(
    block_count: int = 10000,
    difficulty: int = 2,
    start_height: int = 0,
    genesis_hash: Optional[str] = None,
    head_split_interval: int = 250,
) -> Dict[str, Any]:
    """
    Mine and chain `block_count` sequential blocks (100..100,000) in memory while
    automatically splitting load across Fibonacci-scaled Librarian heads whenever
    load crosses `head_split_interval`, then verify every block link & PoW prefix.
    """
    block_count = max(100, min(100000, int(block_count)))
    difficulty = max(1, min(4, int(difficulty)))
    prefix = "0" * difficulty
    head_split_interval = max(50, int(head_split_interval))

    fib_sys = FibonacciLibrarianSystem()
    prev_hash = genesis_hash or hashlib.sha256(b"CROW_CHAIN_STRESS_GENESIS").hexdigest()
    current_head_id = "head_main"
    fib_sys.register_head(current_head_id, start_height, prev_hash)

    peak_librarians = len(fib_sys.librarians)
    peak_heads = len(fib_sys.heads)
    shard_heads: List[str] = []

    blocks: List[Tuple[int, str, str, int]] = []
    block_hashes: List[str] = []

    t_mine_start = time.perf_counter()
    for i in range(1, block_count + 1):
        bnum = start_height + i
        # When load grows, Fibonacci Librarian catches it and opens a new shard head
        if i % head_split_interval == 0:
            current_head_id = f"head_shard_{len(shard_heads) + 1}"
            shard_heads.append(current_head_id)
            fib_sys.register_head(current_head_id, bnum, prev_hash)
            peak_librarians = max(peak_librarians, len(fib_sys.librarians))
            peak_heads = max(peak_heads, len(fib_sys.heads))

        nonce = 0
        base_str = f"{bnum}:{prev_hash}:{current_head_id}:"
        while True:
            bhash = hashlib.sha256(f"{base_str}{nonce}".encode("ascii")).hexdigest()
            if bhash.startswith(prefix):
                break
            nonce += 1

        fib_sys.record_block(current_head_id, bnum, bhash)
        blocks.append((bnum, bhash, prev_hash, nonce))
        block_hashes.append(bhash)
        prev_hash = bhash

    mine_ms = max(0.01, (time.perf_counter() - t_mine_start) * 1000.0)
    blocks_per_sec = round(block_count / (mine_ms / 1000.0))

    # Full sequential chain + PoW verification across all generated blocks
    t_verify_start = time.perf_counter()
    broken = 0
    expected_prev = genesis_hash or hashlib.sha256(b"CROW_CHAIN_STRESS_GENESIS").hexdigest()
    expected_num = start_height + 1
    for bnum, bhash, phash, _ in blocks:
        if bnum != expected_num or phash != expected_prev or not bhash.startswith(prefix):
            broken += 1
        expected_prev = bhash
        expected_num += 1
    merkle_root, tree_depth = _merkle_root(block_hashes)
    verify_ms = round((time.perf_counter() - t_verify_start) * 1000.0, 2)

    # Consolidate temporary shard heads after burst completes
    for sh in shard_heads:
        fib_sys.unregister_head(sh)

    stats = fib_sys.get_system_stats()
    return {
        "ok": True,
        "blockCount": block_count,
        "difficulty": difficulty,
        "mineMs": round(mine_ms, 2),
        "verifyMs": verify_ms,
        "blocksPerSec": blocks_per_sec,
        "valid": broken == 0,
        "brokenLinks": broken,
        "merkleRoot": merkle_root,
        "treeDepth": tree_depth,
        "latestBlockNumber": blocks[-1][0],
        "latestBlockHash": blocks[-1][1],
        "fibonacci": {
            "peakLibrarians": peak_librarians,
            "peakHeads": peak_heads,
            "consolidatedLibrarians": stats["librarianCount"],
            "consolidatedHeads": stats["headCount"],
            "totalBlocksHandled": stats["totalRequests"],
            "scalingEvents": len(fib_sys.scaling_events),
            "thresholds": fib_sys.fibonacci_thresholds,
        },
    }


_GLOBAL_FIB_LIBRARIAN: Optional[FibonacciLibrarianSystem] = None


def get_crow_fibonacci_librarian() -> FibonacciLibrarianSystem:
    global _GLOBAL_FIB_LIBRARIAN
    if _GLOBAL_FIB_LIBRARIAN is None:
        _GLOBAL_FIB_LIBRARIAN = FibonacciLibrarianSystem()
        _GLOBAL_FIB_LIBRARIAN.register_head("crow_main", 0, "0" * 64)
    return _GLOBAL_FIB_LIBRARIAN
