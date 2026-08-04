import base64
import re
import urllib.parse
from distutils.version import LooseVersion

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, Response
from fastapi.responses import HTMLResponse

from app.db import Session, crud, get_db
from app.dependencies import SubOrDeleted, get_sub_or_deleted, get_validated_sub, validate_dates
from app.models.user import SubscriptionUserResponse, UserResponse
from app.subscription.share import encode_title, generate_subscription
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
    SUB_ANNOUNCE,
    SUB_PROFILE_TITLE,
    SUB_PROFILE_TITLE_EMOJI,
    SUB_SUPPORT_URL,
    SUB_UPDATE_INTERVAL,
    SUBSCRIPTION_PAGE_TEMPLATE,
    USE_CUSTOM_JSON_DEFAULT,
    USE_CUSTOM_JSON_FOR_HAPP,
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
    of the listed inbound tags. Clients routed to v2ray-json (any
    USE_CUSTOM_JSON_* setting) never see these links, since that format is
    built from parsed proxy objects, not raw links - this is expected, not a bug.
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


def build_expired_subscription_response(user: "UserResponse", request: Request) -> Response:
    titles = [t.strip() for t in EXPIRED_SUB_TITLES.split("|") if t.strip()]
    stub_links = "\n".join(
        f"{EXPIRED_SUB_LINK}#{urllib.parse.quote(title)}"
        for title in titles
    )
    raw_conf = generate_subscription(user=user, config_format="v2ray", as_base64=False, reverse=False)
    combined = stub_links + "\n" + raw_conf.lstrip()
    encoded = base64.b64encode(combined.encode()).decode()

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
    return Response(content=encoded, media_type="text/plain", headers=headers)


def build_deleted_subscription_response(username: str, request: Request) -> Response:
    """Stub subscription for a signature-valid token whose user no longer
    exists. Only reads `username` from the token - never touches the DB, so
    this stays safe to call for any signature-valid token regardless of
    whether the user (or a same-named replacement) exists.
    """
    titles = [t.strip() for t in DELETED_SUB_TITLES.split("|") if t.strip()]
    stub_links = "\n".join(
        f"{DELETED_SUB_LINK}#{urllib.parse.quote(title)}"
        for title in titles
    )
    encoded = base64.b64encode(stub_links.encode()).decode()

    support_url = DELETED_SUB_SUPPORT_URL or SUB_SUPPORT_URL
    announce_text = DELETED_SUB_ANNOUNCE.replace("\\n", "\n") if DELETED_SUB_ANNOUNCE else None

    headers = {
        "content-disposition": f'attachment; filename="{username}"',
        "profile-web-page-url": str(request.url),
        "support-url": support_url,
        "profile-title": encode_title(f"{SUB_PROFILE_TITLE} {SUB_PROFILE_TITLE_EMOJI} {username}"),
        "profile-update-interval": DELETED_SUB_UPDATE_INTERVAL,
        "subscription-userinfo": "; ".join(
            f"{k}={v}" for k, v in {"upload": 0, "download": 0, "total": 0, "expire": 0}.items()
        ),
        **({"announce": encode_title(announce_text)} if announce_text else {}),
    }
    return Response(content=encoded, media_type="text/plain", headers=headers)


@router.get("/{token}/")
@router.get("/{token}", include_in_schema=False)
def user_subscription(
    request: Request,
    db: Session = Depends(get_db),
    sub_result: SubOrDeleted = Depends(get_sub_or_deleted),
    user_agent: str = Header(default="")
):
    """Provides a subscription link based on the user agent (Clash, V2Ray, etc.)."""
    accept_header = request.headers.get("Accept", "")

    if sub_result.deleted_username is not None:
        if "text/html" in accept_header:
            # no user object to render the subscription page with
            raise HTTPException(status_code=404, detail="Not Found")
        return build_deleted_subscription_response(sub_result.deleted_username, request)

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

    if EXPIRED_SUB_ENABLED and EXPIRED_SUB_LINK and user.status in ("expired", "limited"):
        return build_expired_subscription_response(user, request)

    response_headers = {
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

    extra_links = get_extra_sub_links(user)

    if re.match(r'^([Cc]lash-verge|[Cc]lash[-\.]?[Mm]eta|[Ff][Ll][Cc]lash|[Mm]ihomo)', user_agent):
        conf = generate_subscription(user=user, config_format="clash-meta", as_base64=False, reverse=False)
        return Response(content=conf, media_type="text/yaml", headers=response_headers)

    elif re.match(r'^([Cc]lash|[Ss]tash)', user_agent):
        conf = generate_subscription(user=user, config_format="clash", as_base64=False, reverse=False)
        return Response(content=conf, media_type="text/yaml", headers=response_headers)

    elif re.match(r'^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext|[Ii]n[Hh]ive)', user_agent):
        conf = generate_subscription(user=user, config_format="sing-box", as_base64=False, reverse=False)
        return Response(content=conf, media_type="application/json", headers=response_headers)

    elif re.match(r'^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)', user_agent):
        conf = generate_subscription(user=user, config_format="outline", as_base64=False, reverse=False)
        return Response(content=conf, media_type="application/json", headers=response_headers)

    elif (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_V2RAYN) and re.match(r'^v2rayN/(\d+\.\d+)', user_agent):
        version_str = re.match(r'^v2rayN/(\d+\.\d+)', user_agent).group(1)
        if LooseVersion(version_str) >= LooseVersion("6.40"):
            conf = generate_subscription(user=user, config_format="v2ray-json", as_base64=False, reverse=False)
            return Response(content=conf, media_type="application/json", headers=response_headers)
        else:
            return build_v2ray_response(user, response_headers, extra_links)

    elif (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_V2RAYNG) and re.match(r'^v2rayNG/(\d+\.\d+\.\d+)', user_agent):
        version_str = re.match(r'^v2rayNG/(\d+\.\d+\.\d+)', user_agent).group(1)
        if LooseVersion(version_str) >= LooseVersion("1.8.29"):
            conf = generate_subscription(user=user, config_format="v2ray-json", as_base64=False, reverse=False)
            return Response(content=conf, media_type="application/json", headers=response_headers)
        elif LooseVersion(version_str) >= LooseVersion("1.8.18"):
            conf = generate_subscription(user=user, config_format="v2ray-json", as_base64=False, reverse=True)
            return Response(content=conf, media_type="application/json", headers=response_headers)
        else:
            return build_v2ray_response(user, response_headers, extra_links)

    elif re.match(r'^[Ss]treisand', user_agent):
        if USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_STREISAND:
            conf = generate_subscription(user=user, config_format="v2ray-json", as_base64=False, reverse=False)
            return Response(content=conf, media_type="application/json", headers=response_headers)
        else:
            return build_v2ray_response(user, response_headers, extra_links)

    elif (USE_CUSTOM_JSON_DEFAULT or USE_CUSTOM_JSON_FOR_HAPP) and re.match(r'^Happ/(\d+\.\d+\.\d+)', user_agent):
        version_str = re.match(r'^Happ/(\d+\.\d+\.\d+)', user_agent).group(1)
        if LooseVersion(version_str) >= LooseVersion("1.63.1"):
            conf = generate_subscription(user=user, config_format="v2ray-json", as_base64=False, reverse=False)
            return Response(content=conf, media_type="application/json", headers=response_headers)
        else:
            return build_v2ray_response(user, response_headers, extra_links)

    else:
        return build_v2ray_response(user, response_headers, extra_links)


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

    response_headers = {
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

    config = client_config.get(client_type)
    conf = generate_subscription(user=user,
                                 config_format=config["config_format"],
                                 as_base64=config["as_base64"],
                                 reverse=config["reverse"])

    return Response(content=conf, media_type=config["media_type"], headers=response_headers)
