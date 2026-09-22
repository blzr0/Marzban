import time
import traceback

from app import app, logger, scheduler, xray
from app.db import GetDB, crud
from app.models.node import NodeStatus
from app.xray.node import ReSTXRayNode
from config import JOB_CORE_HEALTH_CHECK_INTERVAL
from xray_api import exc as xray_exc


def _node_core_recovers(node) -> bool:
    """Second opinion before restarting a node's core after a failed API check:
    a single failed gRPC call or a short network blip isn't Xray being down,
    and a restart drops every client on the node. Retry once, then ask the
    node itself (REST /status, independent of the gRPC channel); if Xray is
    running there, rebuild only the gRPC channel. RPyC nodes keep the old
    restart-on-first-failure behavior.
    """
    if not isinstance(node, ReSTXRayNode):
        return False

    time.sleep(2)
    try:
        assert node.started
        node.api.get_sys_stats(timeout=6)
        return True
    except (ConnectionError, xray_exc.XrayError, AssertionError):
        pass

    try:
        status = node.get_status()
    except Exception:
        return False
    return bool(status.get("xray_running")) and node.reopen_api()


def core_health_check():
    config = None

    # main core
    if not xray.core.started:
        if not config:
            config = xray.config.include_db_users()
        xray.core.restart(config)

    # nodes' core
    for node_id, node in list(xray.nodes.items()):
        if node.connected:
            try:
                assert node.started
                node.api.get_sys_stats(timeout=6)
            except (ConnectionError, xray_exc.XrayError, AssertionError):
                if _node_core_recovers(node):
                    logger.info(f"Node {node_id}: Xray API check failed but the core is alive, not restarting")
                    continue
                if not config:
                    config = xray.config.include_db_users()
                xray.operations.restart_node(node_id, config)

        if not node.connected:
            if not config:
                config = xray.config.include_db_users()
            xray.operations.connect_node(node_id, config)


@app.on_event("startup")
def start_core():
    logger.info("Generating Xray core config")

    start_time = time.time()
    config = xray.config.include_db_users()
    logger.info(f"Xray core config generated in {(time.time() - start_time):.2f} seconds")

    # main core
    logger.info("Starting main Xray core")
    try:
        xray.core.start(config)
    except Exception:
        traceback.print_exc()

    # nodes' core
    logger.info("Starting nodes Xray core")
    with GetDB() as db:
        dbnodes = crud.get_nodes(db=db, enabled=True)
        node_ids = [dbnode.id for dbnode in dbnodes]
        for dbnode in dbnodes:
            crud.update_node_status(db, dbnode, NodeStatus.connecting)

    for node_id in node_ids:
        xray.operations.connect_node(node_id, config)

    scheduler.add_job(core_health_check, 'interval',
                      seconds=JOB_CORE_HEALTH_CHECK_INTERVAL,
                      coalesce=True, max_instances=1)


@app.on_event("shutdown")
def app_shutdown():
    logger.info("Stopping main Xray core")
    xray.core.stop()

    logger.info("Stopping nodes Xray core")
    for node in list(xray.nodes.values()):
        try:
            node.disconnect()
        except Exception:
            pass
