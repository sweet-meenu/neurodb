from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ShardInfo:
    shard_id: str
    owner_node_id: str


class ClusterNode(ABC):
    """Interface a NeuroDB storage/query node exposes to the rest of a
    cluster. The MVP ships only SingleNodeCluster below (this node is always
    its own leader for every shard it holds); a real Raft-based
    implementation — leader election and log replication across multiple
    nodes — is documented future work. This interface is the extension
    point it would plug into without any changes to the storage, index, or
    query layers above it.
    """

    @property
    @abstractmethod
    def node_id(self) -> str: ...

    @abstractmethod
    def is_leader_for(self, shard_id: str) -> bool: ...

    @abstractmethod
    def shards(self) -> list[ShardInfo]: ...


class SingleNodeCluster(ClusterNode):
    """The only ClusterNode implementation shipped in this MVP: a cluster of
    one, which owns every shard it's given and never needs consensus."""

    def __init__(self, node_id: str = "local"):
        self._node_id = node_id
        self._shards: dict[str, ShardInfo] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    def register_shard(self, shard_id: str) -> ShardInfo:
        info = ShardInfo(shard_id=shard_id, owner_node_id=self._node_id)
        self._shards[shard_id] = info
        return info

    def is_leader_for(self, shard_id: str) -> bool:
        return shard_id in self._shards

    def shards(self) -> list[ShardInfo]:
        return list(self._shards.values())


class ShardMap:
    """Maps a project to the shard that holds it. With a single-node cluster
    every project maps to exactly one shard owned by that node; a
    multi-node implementation would consult cluster membership and a
    partitioning strategy (e.g. consistent hashing) here instead.
    """

    def __init__(self, cluster: ClusterNode):
        self.cluster = cluster

    def shard_for(self, project_id: str) -> str:
        return f"shard-{project_id}"
