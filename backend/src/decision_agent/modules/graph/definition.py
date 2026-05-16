from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from decision_agent.modules.agents.base import AgentBase
from decision_agent.modules.state.decision_state import DecisionState


@dataclass(frozen=True)
class DecisionGraph:
    agents: dict[str, AgentBase]
    edges: list[tuple[str, str]]
    initial_state: DecisionState
    policies: dict[str, Any] = field(default_factory=dict)

    def topological_order(self) -> list[str]:
        in_degree: dict[str, int] = {aid: 0 for aid in self.agents}
        adj: dict[str, list[str]] = defaultdict(list)
        for src, dst in self.edges:
            adj[src].append(dst)
            in_degree[dst] = in_degree.get(dst, 0) + 1

        queue = deque(aid for aid, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.agents):
            raise ValueError("Decision graph contains a cycle")
        return order

    def predecessors(self, agent_id: str) -> list[str]:
        return [src for src, dst in self.edges if dst == agent_id]

    def successors(self, agent_id: str) -> list[str]:
        return [dst for src, dst in self.edges if src == agent_id]
