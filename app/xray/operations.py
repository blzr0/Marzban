from functools import lru_cache
from typing import TYPE_CHECKING

from google.protobuf import descriptor_pool, message_factory
from sqlalchemy.exc import SQLAlchemyError

from app import logger, xray
from app.db import GetDB, crud
from app.models.node import NodeStatus
from app.models.proxy import ProxyTypes
from app.models.user import UserResponse
from app.utils.concurrency import threaded_function
from app.xray.node import XRayNode
from config import INBOUNDS
from xray_api import XRay as XRayAPI
from xray_api.types.account import Account, XTLSFlows
from xray_api.types.message import TypedMessage


def _is_on_local_core(inbound_tag: str) -> bool:
    # when INBOUNDS filters the master's local Xray, tags not in the list
    # were never started there, so skip the local API call to avoid
    # TagNotFoundError; nodes are unaffected as they always get all tags
    return not INBOUNDS or inbound_tag in INBOUNDS


if TYPE_CHECKING:
    from app.db import User as DBUser
    from app.db.models import Node as DBNode
    from app.xray.config import XRayConfig


@lru_cache(maxsize=None)
def get_tls():
    from app.db import GetDB, get_tls_certificate
    with GetDB() as db:
        tls = get_tls_certificate(db)
        return {
            "key": tls.key,
            "certificate": tls.certificate
        }


@threaded_function
def _add_user_to_inbound(api: XRayAPI, inbound_tag: str, account: Account):
    try:
        api.add_inbound_user(tag=inbound_tag, user=account, timeout=30)
    except (xray.exc.EmailExistsError, xray.exc.ConnectionError):
        pass


@threaded_function
def _remove_user_from_inbound(api: XRayAPI, inbound_tag: str, email: str):
    try:
        api.remove_inbound_user(tag=inbound_tag, email=email, timeout=30)
    except (xray.exc.EmailNotFoundError, xray.exc.ConnectionError):
        pass


@threaded_function
def _alter_inbound_user(api: XRayAPI, inbound_tag: str, account: Account):
    try:
        api.remove_inbound_user(tag=inbound_tag, email=account.email, timeout=30)
    except (xray.exc.EmailNotFoundError, xray.exc.ConnectionError):
        pass
    try:
        api.add_inbound_user(tag=inbound_tag, user=account, timeout=30)
    except (xray.exc.EmailExistsError, xray.exc.ConnectionError):
        pass


def add_user(dbuser: "DBUser"):
    user = UserResponse.model_validate(dbuser)
    email = f"{dbuser.id}.{dbuser.username}"

    for proxy_type, inbound_tags in user.inbounds.items():
        for inbound_tag in inbound_tags:
            inbound = xray.config.inbounds_by_tag.get(inbound_tag, {})

            try:
                proxy_settings = user.proxies[proxy_type].dict(no_obj=True)
            except KeyError:
                continue
            account = proxy_type.account_model(email=email, **proxy_settings)

            # XTLS currently only supports transmission methods of TCP and mKCP
            if getattr(account, 'flow', None) and (
                inbound.get('network', 'tcp') not in ('tcp', 'kcp')
                or
                (
                    inbound.get('network', 'tcp') in ('tcp', 'kcp')
                    and
                    inbound.get('tls') not in ('tls', 'reality')
                )
                or
                inbound.get('header_type') == 'http'
            ):
                account.flow = XTLSFlows.NONE

            if _is_on_local_core(inbound_tag):
                _add_user_to_inbound(xray.api, inbound_tag, account)  # main core
            for node in list(xray.nodes.values()):
                if node.connected and node.started:
                    _add_user_to_inbound(node.api, inbound_tag, account)


def remove_user(dbuser: "DBUser"):
    email = f"{dbuser.id}.{dbuser.username}"

    for inbound_tag in xray.config.inbounds_by_tag:
        if _is_on_local_core(inbound_tag):
            _remove_user_from_inbound(xray.api, inbound_tag, email)
        for node in list(xray.nodes.values()):
            if node.connected and node.started:
                _remove_user_from_inbound(node.api, inbound_tag, email)


def update_user(dbuser: "DBUser"):
    user = UserResponse.model_validate(dbuser)
    email = f"{dbuser.id}.{dbuser.username}"

    active_inbounds = []
    for proxy_type, inbound_tags in user.inbounds.items():
        for inbound_tag in inbound_tags:
            active_inbounds.append(inbound_tag)
            inbound = xray.config.inbounds_by_tag.get(inbound_tag, {})

            try:
                proxy_settings = user.proxies[proxy_type].dict(no_obj=True)
            except KeyError:
                continue
            account = proxy_type.account_model(email=email, **proxy_settings)

            # XTLS currently only supports transmission methods of TCP and mKCP
            if getattr(account, 'flow', None) and (
                inbound.get('network', 'tcp') not in ('tcp', 'kcp')
                or
                (
                    inbound.get('network', 'tcp') in ('tcp', 'kcp')
                    and
                    inbound.get('tls') not in ('tls', 'reality')
                )
                or
                inbound.get('header_type') == 'http'
            ):
                account.flow = XTLSFlows.NONE

            if _is_on_local_core(inbound_tag):
                _alter_inbound_user(xray.api, inbound_tag, account)  # main core
            for node in list(xray.nodes.values()):
                if node.connected and node.started:
                    _alter_inbound_user(node.api, inbound_tag, account)

    for inbound_tag in xray.config.inbounds_by_tag:
        if inbound_tag in active_inbounds:
            continue
        # remove disabled inbounds
        if _is_on_local_core(inbound_tag):
            _remove_user_from_inbound(xray.api, inbound_tag, email)
        for node in list(xray.nodes.values()):
            if node.connected and node.started:
                _remove_user_from_inbound(node.api, inbound_tag, email)


def _same_account(current: TypedMessage, desired: TypedMessage) -> bool:
    """Whether a user's account on the core already matches what we'd load.
    Compared field by field on what the panel sets, not as raw bytes: the core
    re-serializes accounts and may fill in fields the panel leaves default,
    which would otherwise flag every user as changed.
    """
    if current.type != desired.type:
        return False
    cls = message_factory.GetMessageClass(descriptor_pool.Default().FindMessageTypeByName(desired.type))
    current_msg, desired_msg = cls(), cls()
    current_msg.ParseFromString(current.value)
    desired_msg.ParseFromString(desired.value)
    return all(getattr(current_msg, field.name) == value for field, value in desired_msg.ListFields())


def _config_accounts(config: "XRayConfig") -> dict:
    """{inbound_tag: {email: Account}} of the users `config` would load, for
    every inbound the panel manages users on (not API_INBOUND nor
    XRAY_EXCLUDE_INBOUND_TAGS - their clients are static in xray_config.json)."""
    desired = {}
    for inbound in config.get("inbounds", []):
        managed = xray.config.inbounds_by_tag.get(inbound.get("tag"))
        if not managed:
            continue
        proxy_type = ProxyTypes(managed["protocol"])
        accounts = {}
        for client in (inbound.get("settings") or {}).get("clients") or []:
            fields = dict(client)
            if proxy_type == ProxyTypes.Hysteria2 and "auth" in fields:
                fields["password"] = fields.pop("auth")  # see include_db_users
            account = proxy_type.account_model(**fields)
            accounts[account.email] = account
        desired[inbound["tag"]] = accounts
    return desired


def sync_node_users(node, config: "XRayConfig") -> dict:
    """Make the users on a node's running core match `config`, over the API,
    without restarting it. Covers whatever add_user/update_user/remove_user
    couldn't push while the node was unreachable - they only reach nodes that
    are connected at the time. Runs in the caller's thread, one call at a time
    (not through the @threaded_function helpers, which would start a thread
    per user). Raises if the core can't be synced; callers fall back to a
    restart.
    """
    counts = {"added": 0, "updated": 0, "removed": 0}
    for tag, accounts in _config_accounts(config).items():
        try:
            users = node.api.get_inbound_users(tag, timeout=30)
        except xray.exc.TagNotFoundError:
            continue  # inbound filtered out by the node's own INBOUNDS setting
        current = {user.email: user.account for user in users}

        for email, account in accounts.items():
            if email in current and _same_account(current[email], account.message):
                continue
            if email in current:
                try:
                    node.api.remove_inbound_user(tag, email, timeout=30)
                except xray.exc.EmailNotFoundError:
                    pass
                counts["updated"] += 1
            else:
                counts["added"] += 1
            try:
                node.api.add_inbound_user(tag, account, timeout=30)
            except xray.exc.EmailExistsError:
                pass  # pushed concurrently by add_user/update_user

        for email in current.keys() - accounts.keys():
            try:
                node.api.remove_inbound_user(tag, email, timeout=30)
            except xray.exc.EmailNotFoundError:
                pass
            counts["removed"] += 1

    return counts


def remove_node(node_id: int):
    if node_id in xray.nodes:
        try:
            xray.nodes[node_id].disconnect()
        except Exception:
            pass
        finally:
            try:
                del xray.nodes[node_id]
            except KeyError:
                pass


def add_node(dbnode: "DBNode"):
    remove_node(dbnode.id)

    tls = get_tls()
    xray.nodes[dbnode.id] = XRayNode(address=dbnode.address,
                                     port=dbnode.port,
                                     api_port=dbnode.api_port,
                                     ssl_key=tls['key'],
                                     ssl_cert=tls['certificate'],
                                     usage_coefficient=dbnode.usage_coefficient)

    return xray.nodes[dbnode.id]


def _change_node_status(node_id: int, status: NodeStatus, message: str = None, version: str = None):
    with GetDB() as db:
        try:
            dbnode = crud.get_node_by_id(db, node_id)
            if not dbnode:
                return

            if dbnode.status == NodeStatus.disabled:
                remove_node(dbnode.id)
                return

            crud.update_node_status(db, dbnode, status, message, version)
        except SQLAlchemyError:
            db.rollback()


global _connecting_nodes
_connecting_nodes = {}


@threaded_function
def connect_node(node_id, config=None):
    global _connecting_nodes

    if _connecting_nodes.get(node_id):
        return

    with GetDB() as db:
        dbnode = crud.get_node_by_id(db, node_id)

    if not dbnode:
        return

    try:
        node = xray.nodes[dbnode.id]
        assert node.connected
    except (KeyError, AssertionError):
        node = xray.operations.add_node(dbnode)

    try:
        _connecting_nodes[node_id] = True

        _change_node_status(node_id, NodeStatus.connecting)
        logger.info(f"Connecting to \"{dbnode.name}\" node")

        if config is None:
            config = xray.config.include_db_users()

        node.start(config)
        if getattr(node, "attached", False):
            try:
                counts = sync_node_users(node, config)
                logger.info(f"Attached to running Xray core of \"{dbnode.name}\" node without restart, "
                            f"users synced: {counts['added']} added, {counts['updated']} updated, "
                            f"{counts['removed']} removed")
            except Exception as e:
                logger.warning(f"Unable to sync users on \"{dbnode.name}\" node ({e}), restarting its core instead")
                node.restart(config)
        version = node.get_version()
        _change_node_status(node_id, NodeStatus.connected, version=version)
        logger.info(f"Connected to \"{dbnode.name}\" node, xray run on v{version}")

    except Exception as e:
        _change_node_status(node_id, NodeStatus.error, message=str(e))
        logger.info(f"Unable to connect to \"{dbnode.name}\" node")

    finally:
        try:
            del _connecting_nodes[node_id]
        except KeyError:
            pass


@threaded_function
def restart_node(node_id, config=None):
    with GetDB() as db:
        dbnode = crud.get_node_by_id(db, node_id)

    if not dbnode:
        return

    try:
        node = xray.nodes[dbnode.id]
    except KeyError:
        node = xray.operations.add_node(dbnode)

    if not node.connected:
        return connect_node(node_id, config)

    try:
        logger.info(f"Restarting Xray core of \"{dbnode.name}\" node")

        if config is None:
            config = xray.config.include_db_users()

        node.restart(config)
        logger.info(f"Xray core of \"{dbnode.name}\" node restarted")
    except Exception as e:
        _change_node_status(node_id, NodeStatus.error, message=str(e))
        logger.info(f"Unable to restart node {node_id}")
        try:
            node.disconnect()
        except Exception:
            pass


__all__ = [
    "add_user",
    "remove_user",
    "add_node",
    "remove_node",
    "connect_node",
    "restart_node",
]
