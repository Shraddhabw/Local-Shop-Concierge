"""In-memory sliding-window rate limiter and real-client-IP helper.

Single uvicorn worker is a project rule, so in-process state is consistent.
"""
import ipaddress
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit, window_seconds, enabled=True):
        self.limit, self.window, self.enabled = limit, window_seconds, enabled
        self.hits = defaultdict(deque)

    def allow(self, key):
        """Record a hit; return False if the key is over its limit."""
        if not self.enabled:
            return True
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 10_000:       # keep memory bounded
            for k in [k for k, v in self.hits.items() if not v or now - v[-1] > self.window]:
                del self.hits[k]
        return True


def _in_networks(ip, networks):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for net in networks:
        try:
            if addr in ipaddress.ip_network(net, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request, trusted_proxies):
    """Real client IP. X-Forwarded-For is trusted only when the direct peer is a trusted proxy."""
    peer = request.client.host if request.client else "unknown"
    if trusted_proxies and _in_networks(peer, trusted_proxies):
        forwarded = request.headers.get("x-forwarded-for", "")
        # rightmost entry is the one our proxy appended; ignore anything the client prepended
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return peer
