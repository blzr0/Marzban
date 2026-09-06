import logging
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

logger = logging.getLogger("uvicorn.error")

_HYSTERIA2_SCHEMES = {"hysteria2", "hy2"}
_SUPPORTED_SCHEMES = {"vless"} | _HYSTERIA2_SCHEMES


def _log_skip(link: str, reason: str) -> None:
    try:
        scheme = link.strip().split("://", 1)[0][:20]
    except Exception:
        scheme = "?"
    try:
        host = urlsplit(link).hostname or "?"
    except Exception:
        host = "?"
    logger.warning("EXTRA_SUB_LINKS: skipping link (%s): scheme=%s host=%s", reason, scheme, host)


def parse_share_link(link: str) -> Optional[dict]:
    """Parse a vless:// link or a hysteria2:// / hy2:// link into a normalized
    dict usable to build a v2ray-json outbound.

    Never raises: any parsing problem (unsupported scheme, missing address,
    malformed query, etc.) is logged (scheme + host only, no credentials) and
    the function returns None so the caller can just skip this one link.
    """
    if not link or not isinstance(link, str):
        return None

    try:
        link = link.strip()
        if not link:
            return None

        parsed = urlsplit(link)
        scheme = (parsed.scheme or "").lower()
        if scheme not in _SUPPORTED_SCHEMES:
            return None

        host = parsed.hostname
        if not host:
            _log_skip(link, "no host")
            return None

        try:
            port = parsed.port
        except ValueError:
            _log_skip(link, "invalid port")
            return None
        port = port or 443

        credential = unquote(parsed.username) if parsed.username else ""
        if not credential:
            _log_skip(link, "no credential")
            return None

        remark = unquote(parsed.fragment) if parsed.fragment else ""

        query = parse_qs(parsed.query, keep_blank_values=True)
        params = {key: values[0] for key, values in query.items() if values}

        protocol = "vless" if scheme == "vless" else "hysteria2"

        if protocol == "hysteria2" and params.get("obfs"):
            # obfs/Salamander for hysteria2 is configured via finalmask, not
            # the transport - not implemented, so don't emit a config that
            # would silently fail to connect.
            _log_skip(link, "hysteria2 obfs unsupported")
            return None

        return {
            "protocol": protocol,
            "remark": remark,
            "address": host,
            "port": port,
            "credential": credential,
            "params": params,
        }
    except Exception:
        _log_skip(link, "parse error")
        return None
