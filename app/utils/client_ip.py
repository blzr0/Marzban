import ipaddress

from fastapi import Request

from config import TRUSTED_PROXIES

_TRUSTED_PROXY_NETS = [ipaddress.ip_network(p, strict=False) for p in TRUSTED_PROXIES]


def is_trusted_proxy(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(addr in net for net in _TRUSTED_PROXY_NETS)


def get_client_ip(request: Request) -> str:
    """The client's IP address. Proxy headers are only believed when the
    request comes from one of TRUSTED_PROXIES; anyone else could send them to
    fake an IP and dodge the login limit. Behind such a proxy, X-Real-IP or the last
    X-Forwarded-For hop is the one the proxy itself saw."""
    peer = request.client.host if request.client else ""
    if peer and is_trusted_proxy(peer):
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return peer or "Unknown"


def get_request_host(request: Request) -> str:
    """Domain the client used to reach the panel (no port). X-Forwarded-Host is
    believed only from TRUSTED_PROXIES, like the IP headers above."""
    peer = request.client.host if request.client else ""
    host = ""
    if peer and is_trusted_proxy(peer):
        host = request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()
    host = host or request.headers.get("Host", "")
    if host.startswith("["):  # IPv6 literal: [::1]:8000
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host
