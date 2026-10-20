from __future__ import annotations

import heapq
import math
import random

import numpy as np


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))  # vectors are kept L2-normalized on insert/search


class HNSWIndex:
    """Hand-written Hierarchical Navigable Small World graph index
    (Malkov & Yashunin, 2018): a multi-layer proximity graph giving
    logarithmic-complexity approximate nearest-neighbor search. No
    hnswlib/faiss — the insertion and greedy-search routines below are the
    actual algorithm, built on numpy for vector math only.
    """

    def __init__(self, dims: int, *, M: int = 16, ef_construction: int = 200, seed: int = 42):
        self.dims = dims
        self.M = M
        self.M0 = M * 2  # layer-0 gets twice the connectivity, per the paper
        self.ef_construction = ef_construction
        self.ml = 1.0 / math.log(M)
        self._rng = random.Random(seed)

        self.vectors: dict[str, np.ndarray] = {}
        self.levels: dict[str, int] = {}
        self.graph: list[dict[str, set[str]]] = []  # graph[layer][node_id] -> neighbor ids
        self.entry_point: str | None = None
        self.top_level: int = -1

    def __len__(self) -> int:
        return len(self.vectors)

    def _random_level(self) -> int:
        return int(-math.log(self._rng.random() + 1e-12) * self.ml)

    def _ensure_layers(self, level: int) -> None:
        while len(self.graph) <= level:
            self.graph.append({})

    def _distance(self, a: np.ndarray, b: np.ndarray) -> float:
        return 1.0 - _cosine_sim(a, b)

    def _search_layer(
        self, query: np.ndarray, entry_points: list[str], ef: int, layer: int
    ) -> list[tuple[float, str]]:
        """Greedy best-first search within a single layer, maintaining a
        candidate frontier and a bounded (size ef) result set — the core
        HNSW search routine."""
        visited = set(entry_points)
        candidates = [(self._distance(query, self.vectors[ep]), ep) for ep in entry_points]
        heapq.heapify(candidates)
        found = [(-d, n) for d, n in candidates]  # max-heap (negated) of best-so-far
        heapq.heapify(found)

        while candidates:
            dist_c, c = heapq.heappop(candidates)
            worst_found = -found[0][0]
            if dist_c > worst_found and len(found) >= ef:
                break
            for neighbor in self.graph[layer].get(c, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                dist_n = self._distance(query, self.vectors[neighbor])
                worst_found = -found[0][0]
                if len(found) < ef or dist_n < worst_found:
                    heapq.heappush(candidates, (dist_n, neighbor))
                    heapq.heappush(found, (-dist_n, neighbor))
                    if len(found) > ef:
                        heapq.heappop(found)
        return [(-d, n) for d, n in found]

    def _select_neighbors(self, candidates: list[tuple[float, str]], m: int) -> list[str]:
        return [n for _, n in sorted(candidates)[:m]]

    def add(self, id_: str, vector: list[float] | np.ndarray) -> None:
        vec = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        if id_ in self.vectors:
            self.remove(id_)

        level = self._random_level()
        self._ensure_layers(level)
        self.vectors[id_] = vec
        self.levels[id_] = level
        for lc in range(level + 1):
            self.graph[lc].setdefault(id_, set())

        if self.entry_point is None:
            self.entry_point = id_
            self.top_level = level
            return

        old_top_level = self.top_level
        cur_nearest = [self.entry_point]
        for lc in range(old_top_level, level, -1):
            cur_nearest = [self._search_layer(vec, cur_nearest, ef=1, layer=lc)[0][1]]

        for lc in range(min(level, old_top_level), -1, -1):
            candidates = self._search_layer(vec, cur_nearest, ef=self.ef_construction, layer=lc)
            m = self.M0 if lc == 0 else self.M
            neighbors = self._select_neighbors(candidates, m)

            self.graph[lc][id_].update(neighbors)
            for n in neighbors:
                self.graph[lc].setdefault(n, set()).add(id_)
                if len(self.graph[lc][n]) > m:
                    n_candidates = [
                        (self._distance(self.vectors[n], self.vectors[o]), o)
                        for o in self.graph[lc][n]
                    ]
                    self.graph[lc][n] = set(self._select_neighbors(n_candidates, m))

            cur_nearest = [n for _, n in candidates] or cur_nearest

        if level > old_top_level:
            self.top_level = level
            self.entry_point = id_

    def remove(self, id_: str) -> None:
        if id_ not in self.vectors:
            return
        level = self.levels.pop(id_)
        del self.vectors[id_]
        for lc in range(level + 1):
            neighbors = self.graph[lc].pop(id_, set())
            for n in neighbors:
                self.graph[lc].get(n, set()).discard(id_)

        if self.entry_point == id_:
            if self.vectors:
                self.entry_point = max(self.levels, key=lambda n: self.levels[n])
                self.top_level = self.levels[self.entry_point]
            else:
                self.entry_point = None
                self.top_level = -1

    def search(
        self, query: list[float] | np.ndarray, k: int = 10, ef: int | None = None
    ) -> list[tuple[str, float]]:
        if self.entry_point is None:
            return []
        q = np.asarray(query, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        ef = ef or max(self.ef_construction, k)
        cur_nearest = [self.entry_point]
        for lc in range(self.top_level, 0, -1):
            cur_nearest = [self._search_layer(q, cur_nearest, ef=1, layer=lc)[0][1]]

        candidates = self._search_layer(q, cur_nearest, ef=ef, layer=0)
        candidates.sort(key=lambda dn: dn[0])
        return [(n, 1.0 - d) for d, n in candidates[:k]]
