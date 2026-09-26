import base64
import re
import urllib.parse
from distutils.version import LooseVersion

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response
from fastapi.responses import HTMLResponse

from app.db import Session, crud, get_db
from app.dependencies import ResolvedSub, SubState, get_resolved_sub, get_validated_sub, validate_dates
from app.models.user import SubscriptionUserResponse, UserResponse
from app.subscription.share import encode_title, generate_stub_subscription, generate_subscription
from app.templates import render_template
from config import (
    DELETED_SUB_ANNOUNCE,
    DELETED_SUB_LINK,
    DELETED_SUB_SUPPORT_URL,
    DELETED_SUB_TITLES,
    DELETED_SUB_UPDATE_INTERVAL,
    EXPIRED_SUB_ANNOUNCE,
    EXPIRED_SUB_ENABLED,
    EXPIRED_SUB_LINK,
    EXPIRED_SUB_SUPPORT_URL,
    EXPIRED_SUB_TITLES,
    EXPIRED_SUB_UPDATE_INTERVAL,
    EXTRA_SUB_ENABLED,
    EXTRA_SUB_LINKS,
    EXTRA_SUB_REQUIRED_INBOUND,
    REVOKED_SUB_ANNOUNCE,
    REVOKED_SUB_LINK,
    REVOKED_SUB_SUPPORT_URL,
    REVOKED_SUB_TITLES,
    REVOKED_SUB_UPDATE_INTERVAL,
    SUB_ANNOUNCE,
    SUB_PROFILE_TITLE,
    SUB_PROFILE_TITLE_EMOJI,
    SUB_SUPPORT_URL,
    SUB_UPDATE_INTERVAL,
    SUBSCRIPTION_PAGE_TEMPLATE,
    USE_CUSTOM_JSON_DEFAULT,
    USE_CUSTOM_JSON_FOR_HAPP,
    USE_CUSTOM_JSON_FOR_INCY,
    USE_CUSTOM_JSON_FOR_STREISAND,
    USE_CUSTOM_JSON_FOR_V2RAYN,
    USE_CUSTOM_JSON_FOR_V2RAYNG,
    XRAY_SUBSCRIPTION_PATH,
)

client_config = {
    "clash-meta": {"config_format": "clash-meta", "media_type": "text/yaml", "as_base64": False, "reverse": False},
    "sing-box": {"config_format": "sing-box", "media_type": "application/json", "as_base64": False, "reverse": False},
    "clash": {"config_format": "clash", "media_type": "text/yaml", "as_base64": False, "reverse": False},
    "v2ray": {"config_format": "v2ray", "media_type": "text/plain", "as_base64": True, "reverse": False},
    "outline": {"config_format": "outline", "media_type": "application/json", "as_base64": False, "reverse": False},
    "v2ray-json": {"config_format": "v2ray-json", "media_type": "application/json", "as_base64": False,
                   "reverse": False}
}

router = APIRouter(tags=['Subscription'], prefix=f'/{XRAY_SUBSCRIPTION_PATH}')

EXTRA_SUB_LINKS_LIST = [link.strip() for link in EXTRA_SUB_LINKS.split("|") if link.strip()]
EXTRA_SUB_REQUIRED_INBOUND_TAGS = {
    tag.strip() for tag in EXTRA_SUB_REQUIRED_INBOUND.split(",") if tag.strip()
}


def get_subscription_user_info(user: UserResponse) -> dict:
    """Retrieve user subscription information including upload, download, total data, and expiry."""
    return {
        "upload": 0,
        "download": user.used_traffic,
        "total": user.data_limit if user.data_limit is not None else 0,
        "expire": user.expire if user.expire is not None else 0,
    }


def get_extra_sub_links(user: "UserResponse") -> list:
    """Extra links appended to the end of v2ray-format subscriptions.

    Only for strictly active users (not on_hold/expired/limited/disabled), and
    only when EXTRA_SUB_REQUIRED_INBOUND is empty or the user has at least one
    of the listed inbound tags. Flat v2ray gets them as raw links, v2ray-json
    as parsed outbounds; other formats never include them.
    """
    if not EXTRA_SUB_ENABLED or not EXTRA_SUB_LINKS_LIST:
        return []
    if user.status != "active":
        return []
    if EXTRA_SUB_REQUIRED_INBOUND_TAGS:
        user_tags = {tag for tags in (user.inbounds or {}).values() for tag in tags}
        if not user_tags & EXTRA_SUB_REQUIRED_INBOUND_TAGS:
            return []
    return EXTRA_SUB_LINKS_LIST


def build_v2ray_response(user: "UserResponse", headers: dict, extra_links: list) -> Response:
    if not extra_links:
        conf = generate_subscription(user=user, config_format="v2ray", as_base64=True, reverse=False)
        return Response(content=conf, media_type="text/plain", headers=headers)

    raw_conf = generate_subscription(user=user, config_format="v2ray", as_base64=False, reverse=False)
    combined = raw_conf.rstrip("\n") + "\n" + "\n".join(extra_links)
    encoded = base64.b64encode(combined.encode()).decode()
    return Response(content=encoded, media_type="text/plain", headers=headers)


def resolve_client_format(user_agent: str) -> tuple:
    """(config_format, reverse) served to a client, picked by its User-Agent."""
    if re.match(r'^([Cc]lash-verge|[Cc]lash[-\.]?[Mm]eta|[Ff][Ll][Cc]lash|[Mm]ihomo)', user_agent):
        return "clash-meta", False
    if re.match(r'^([Cc]lash|[Ss]tash)', user_agent):
        return "clash", False
    if re.match(r'^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext|[Ii]n[Hh]ive)', user_agent):
        return "sing-box", False
    if re.match(r'^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)', user_agent):
        return "outline", False

    if match := re.match(r'^v2rayN/(\d+\.\d+)', user_agent):
        if (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_V2RAYN) and LooseVersion(match.group(1)) >= LooseVersion("6.40"):
            return "v2ray-json", False
        return "v2ray", False

    if match := re.match(r'^v2rayNG/(\d+\.\d+\.\d+)', user_agent):
        if USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_V2RAYNG:
            if LooseVersion(match.group(1)) >= LooseVersion("1.8.29"):
                return "v2ray-json", False
            if LooseVersion(match.group(1)) >= LooseVersion("1.8.18"):
                return "v2ray-json", True
        return "v2ray", False

    if re.match(r'^[Ss]treisand', user_agent):
        return ("v2ray-json" if USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_STREISAND else "v2ray"), False

    if match := re.match(r'^Happ/(\d+\.\d+\.\d+)', user_agent):
        if (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_HAPP) and LooseVersion(match.group(1)) >= LooseVersion("1.63.1"):
            return "v2ray-json", False
        return "v2ray", False

    if (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_INCY) and re.match(r'^INCY/', user_agent):
        return "v2ray-json", False

    return "v2ray", False


def build_subscription_response(user: "UserResponse", headers: dict, config_format: str, reverse: bool) -> Response:
    """The user's real subscription in `config_format`, with EXTRA_SUB_LINKS
    for the formats that carry them."""
    extra_links = get_extra_sub_links(user)
    if config_format == "v2ray":
        return build_v2ray_response(user, headers, extra_links)
    conf = generate_subscription(user=user, config_format=config_format, as_base64=False, reverse=reverse,
                                 extra_links=extra_links if config_format == "v2ray-json" else None)
    return Response(content=conf, media_type=client_config[config_format]["media_type"], headers=headers)


def make_stub_links(link: str, titles: str) -> list:
    return [f"{link}#{urllib.parse.quote(title.strip())}" for title in titles.split("|") if title.strip()]


def build_stub_content(stub_links: list, config_format: str, reverse: bool, user: "UserResponse" = None) -> tuple:
    """(content, media_type) of a stub subscription: in the client's own
    format when it can carry the stub link, else the flat base64 v2ray list
    every v2ray-style client understands."""
    conf = generate_stub_subscription(stub_links, config_format, reverse=reverse, user=user)
    if conf is not None:
        return conf, client_config[config_format]["media_type"]

    lines = list(stub_links)
    if user is not None:
        raw_conf = generate_subscription(user=user, config_format="v2ray", as_base64=False, reverse=False)
        lines.append(raw_conf.lstrip())
    return base64.b64encode("\n".join(lines).encode()).decode(), "text/plain"


def build_expired_subscription_response(
    user: "UserResponse", request: Request, config_format: str = "v2ray", reverse: bool = False,
) -> Response:
    stub_links = make_stub_links(EXPIRED_SUB_LINK, EXPIRED_SUB_TITLES)
    content, media_type = build_stub_content(stub_links, config_format, reverse, user=user)

    support_url = EXPIRED_SUB_SUPPORT_URL or SUB_SUPPORT_URL
    announce_text = EXPIRED_SUB_ANNOUNCE.replace("\\n", "\n") if EXPIRED_SUB_ANNOUNCE else None

    headers = {
        "content-disposition": f'attachment; filename="{user.username}"',
        "profile-web-page-url": str(request.url),
        "support-url": support_url,
        "profile-title": encode_title(f"{SUB_PROFILE_TITLE} {SUB_PROFILE_TITLE_EMOJI} {user.username}"),
        "profile-update-interval": EXPIRED_SUB_UPDATE_INTERVAL,
        "subscription-userinfo": "; ".join(
            f"{k}={v}" for k, v in get_subscription_user_info(user).items()
        ),
        **({"announce": encode_title(announce_text)} if announce_text else {}),
    }
    return Response(content=content, media_type=media_type, headers=headers)


def build_stub_subscription_response(
    username: str,
    request: Request,
    *,
    link: str,
    titles: str,
    support_url: str,
    update_interval: str,
    announce: str,
    config_format: str = "v2ray",
    reverse: bool = False,
) -> Response:
    """Stub subscription for a signature-valid token that can't be served a
    real config: user deleted (DELETED_SUB_*) or link revoked
    (REVOKED_SUB_*). Only ever reads `username` from the token - never
    touches real account data - so this stays safe to call regardless of
    whether a live user exists behind the token.
    """
    content, media_type = build_stub_content(make_stub_links(link, titles), config_format, reverse)

    resolved_support_url = support_url or SUB_SUPPORT_URL
    announce_text = announce.replace("\\n", "\n") if announce else None

    headers = {
        "content-disposition": f'attachment; filename="{username}"',
        "profile-web-page-url": str(request.url),
        "support-url": resolved_support_url,
        "profile-title": encode_title(f"{SUB_PROFILE_TITLE} {SUB_PROFILE_TITLE_EMOJI} {username}"),
        "profile-update-interval": update_interval,
        "subscription-userinfo": "; ".join(
            f"{k}={v}" for k, v in {"upload": 0, "download": 0, "total": 0, "expire": 0}.items()
        ),
        **({"announce": encode_title(announce_text)} if announce_text else {}),
    }
    return Response(content=content, media_type=media_type, headers=headers)


def build_response_headers(user: "UserResponse", request: Request) -> dict:
    return {
        "content-disposition": f'attachment; filename="{user.username}"',
        "profile-web-page-url": str(request.url),
        "support-url": SUB_SUPPORT_URL,
        "profile-title": encode_title(f"{SUB_PROFILE_TITLE} {SUB_PROFILE_TITLE_EMOJI} {user.username}"),
        "profile-update-interval": SUB_UPDATE_INTERVAL,
        "subscription-userinfo": "; ".join(
            f"{key}={val}"
            for key, val in get_subscription_user_info(user).items()
        ),
        **({"announce": encode_title(SUB_ANNOUNCE.replace("\\n", "\n"))} if SUB_ANNOUNCE else {}),
    }


def shows_expired_stub(user: "UserResponse") -> bool:
    return EXPIRED_SUB_ENABLED and bool(EXPIRED_SUB_LINK) and user.status in ("expired", "limited")


@router.get("/{token}/")
@router.get("/{token}", include_in_schema=False)
def user_subscription(
    request: Request,
    db: Session = Depends(get_db),
    sub_result: ResolvedSub = Depends(get_resolved_sub),
    user_agent: str = Header(default="")
):
    """Provides a subscription link based on the user agent (Clash, V2Ray, etc.)."""
    accept_header = request.headers.get("Accept", "")
    config_format, reverse = resolve_client_format(user_agent)

    if sub_result.state is SubState.DELETED:
        if "text/html" in accept_header:
            # no user object to render the subscription page with
            raise HTTPException(status_code=404, detail="Not Found")
        return build_stub_subscription_response(
            sub_result.username, request,
            link=DELETED_SUB_LINK, titles=DELETED_SUB_TITLES,
            support_url=DELETED_SUB_SUPPORT_URL, update_interval=DELETED_SUB_UPDATE_INTERVAL,
            announce=DELETED_SUB_ANNOUNCE, config_format=config_format, reverse=reverse,
        )

    if sub_result.state is SubState.REVOKED:
        if "text/html" in accept_header:
            # no user object to render the subscription page with, and the
            # link may not belong to the account owner regardless
            raise HTTPException(status_code=404, detail="Not Found")
        return build_stub_subscription_response(
            sub_result.username, request,
            link=REVOKED_SUB_LINK, titles=REVOKED_SUB_TITLES,
            support_url=REVOKED_SUB_SUPPORT_URL, update_interval=REVOKED_SUB_UPDATE_INTERVAL,
            announce=REVOKED_SUB_ANNOUNCE, config_format=config_format, reverse=reverse,
        )

    dbuser = sub_result.dbuser
    user: UserResponse = UserResponse.model_validate(dbuser)

    if "text/html" in accept_header:
        return HTMLResponse(
            render_template(
                SUBSCRIPTION_PAGE_TEMPLATE,
                {"user": user}
            )
        )

    crud.update_user_sub(db, dbuser, user_agent)

    if shows_expired_stub(user):
        return build_expired_subscription_response(user, request, config_format, reverse)

    return build_subscription_response(user, build_response_headers(user, request), config_format, reverse)


@router.get("/{token}/info", response_model=SubscriptionUserResponse)
def user_subscription_info(
    dbuser: UserResponse = Depends(get_validated_sub),
):
    """Retrieves detailed information about the user's subscription."""
    return dbuser


@router.get("/{token}/usage")
def user_get_usage(
    dbuser: UserResponse = Depends(get_validated_sub),
    start: str = "",
    end: str = "",
    db: Session = Depends(get_db)
):
    """Fetches the usage statistics for the user within a specified date range."""
    start, end = validate_dates(start, end)

    usages = crud.get_user_usages(db, dbuser, start, end)

    return {"usages": usages, "username": dbuser.username}


@router.get("/{token}/{client_type}")
def user_subscription_with_client_type(
    request: Request,
    dbuser: UserResponse = Depends(get_validated_sub),
    client_type: str = Path(..., regex="sing-box|clash-meta|clash|outline|v2ray|v2ray-json"),
    db: Session = Depends(get_db),
    user_agent: str = Header(default="")
):
    """Provides a subscription link based on the specified client type (e.g., Clash, V2Ray)."""
    user: UserResponse = UserResponse.model_validate(dbuser)
    reverse = client_config[client_type]["reverse"]

    if shows_expired_stub(user):
        return build_expired_subscription_response(user, request, client_type, reverse)

    return build_subscription_response(user, build_response_headers(user, request), client_type, reverse)
