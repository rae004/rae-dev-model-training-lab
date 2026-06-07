"""Sample Python module used to exercise the tokenizer and data loader."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)


@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return (dx * dx + dy * dy) ** 0.5


@dataclass
class Cluster:
    name: str
    points: list[Point] = field(default_factory=list)

    def centroid(self) -> Point:
        if not self.points:
            raise ValueError(f"cluster {self.name!r} is empty")
        cx = sum(p.x for p in self.points) / len(self.points)
        cy = sum(p.y for p in self.points) / len(self.points)
        return Point(cx, cy)

    def radius(self) -> float:
        center = self.centroid()
        return max(p.distance_to(center) for p in self.points)


def average(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        raise ValueError("cannot average an empty sequence")
    return sum(items) / len(items)


def chunks(seq: list[int], size: int) -> Iterator[list[int]]:
    if size <= 0:
        raise ValueError("size must be positive")
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


def load_clusters(path: Path) -> list[Cluster]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        Cluster(
            name=entry["name"],
            points=[Point(p["x"], p["y"]) for p in entry["points"]],
        )
        for entry in raw
    ]


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    origin = Point(0.0, 0.0)
    points = [Point(1.0, 1.0), Point(3.0, 4.0), Point(-1.0, 2.0)]
    cluster = Cluster(name="demo", points=points)
    log.info("centroid=%s radius=%.3f", cluster.centroid(), cluster.radius())
    log.info("avg distance from origin=%.3f", average(p.distance_to(origin) for p in points))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
