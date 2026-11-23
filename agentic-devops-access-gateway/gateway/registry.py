"""Registry of remote servers that DevOps agents may connect to.

Each remote server is a customer-environment endpoint the agent reaches
through the gateway. The registry tracks health from heartbeats: a
server that stops reporting goes unhealthy and the gateway refuses to
route agent actions to it until it recovers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RemoteServer:
    server_id: str
    name: str
    environment: str
    endpoint: str
    healthy: bool = True
    last_heartbeat: float = field(default_factory=time.time)


class ServerRegistry:
    def __init__(self, stale_after_seconds: int = 300):
        self._servers: dict[str, RemoteServer] = {}
        self.stale_after_seconds = stale_after_seconds

    def register(self, server_id: str, name: str, environment: str,
                 endpoint: str) -> RemoteServer:
        if server_id in self._servers:
            raise ValueError(f"server {server_id!r} already registered")
        server = RemoteServer(server_id=server_id, name=name,
                              environment=environment, endpoint=endpoint)
        self._servers[server_id] = server
        return server

    def get(self, server_id: str) -> RemoteServer | None:
        return self._servers.get(server_id)

    def heartbeat(self, server_id: str, now: float | None = None) -> RemoteServer:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"unknown server {server_id!r}")
        server.last_heartbeat = now if now is not None else time.time()
        server.healthy = True
        return server

    def mark_unhealthy(self, server_id: str) -> RemoteServer:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"unknown server {server_id!r}")
        server.healthy = False
        return server

    def health_check(self, now: float | None = None) -> list[RemoteServer]:
        """Mark stale servers unhealthy; return the currently unhealthy ones."""
        check_at = now if now is not None else time.time()
        unhealthy = []
        for server in self._servers.values():
            if check_at - server.last_heartbeat > self.stale_after_seconds:
                server.healthy = False
            if not server.healthy:
                unhealthy.append(server)
        return unhealthy

    def list(self, environment: str | None = None) -> list[RemoteServer]:
        servers = list(self._servers.values())
        if environment is not None:
            servers = [s for s in servers if s.environment == environment]
        return servers
