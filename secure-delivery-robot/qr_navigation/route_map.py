"""
FUTURE SCOPE STUB - multi-destination routing.

Right now the robot follows whatever markers it happens to see. A real
delivery robot is told "go to Room 102" and must know which corridor to take.

This module is the place for that. A simple adjacency graph plus BFS gives
you turn-by-turn expectations, and lets the robot notice when it has gone the
wrong way (a marker it did not expect) instead of cheerfully continuing.

Implemented enough to be useful and tested; extend as your map grows.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional

# node -> neighbours reachable from it
ROUTE_GRAPH: Dict[str, List[str]] = {
    "WP-HOME":   ["WP-START"],
    "WP-START":  ["WP-CORR-A"],
    "WP-CORR-A": ["WP-TURN-L", "WP-TURN-R"],
    "WP-TURN-L": ["WP-DEST-01"],
    "WP-TURN-R": ["WP-CORR-B"],
    "WP-CORR-B": ["WP-DEST-02"],
    "WP-DEST-01": [],
    "WP-DEST-02": [],
}


def plan_route(start: str, goal: str) -> Optional[List[str]]:
    """Shortest marker sequence from start to goal, or None if unreachable."""
    if start not in ROUTE_GRAPH or goal not in ROUTE_GRAPH:
        return None
    queue = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        if path[-1] == goal:
            return path
        for nxt in ROUTE_GRAPH.get(path[-1], []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(path + [nxt])
    return None


def next_expected(path: List[str], current: str) -> Optional[str]:
    """Given a plan and where we are, what marker should we see next?"""
    try:
        i = path.index(current)
    except ValueError:
        return None
    return path[i + 1] if i + 1 < len(path) else None


def is_off_route(path: List[str], seen_marker: str) -> bool:
    return seen_marker not in path
