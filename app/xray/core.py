import atexit
import re
import subprocess
import threading
from collections import deque
from contextlib import contextmanager

from app import logger
from app.xray.config import XRayConfig
from config import DEBUG, INBOUNDS

# tag of the inbound Marzban injects for its own API/stats access;
# must always survive local filtering or the panel loses control of its own core
API_INBOUND_TAG = "API_INBOUND"


class XRayCore:
    def __init__(self,
                 executable_path: str = "/usr/bin/xray",
                 assets_path: str = "/usr/share/xray"):
        self.executable_path = executable_path
        self.assets_path = assets_path

        self.version = self.get_version()
        self.process = None
        self._restart_lock = threading.Lock()

        self._logs_buffer = deque(maxlen=100)
        self._temp_log_buffers = {}
        self._on_start_funcs = []
        self._on_stop_funcs = []
        self._env = {
            "XRAY_LOCATION_ASSET": assets_path
        }

        atexit.register(lambda: self.stop() if self.started else None)

    def get_version(self):
        cmd = [self.executable_path, "version"]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
        m = re.match(r'^Xray (\d+\.\d+\.\d+)', output)
        if m:
            return m.groups()[0]

    def get_x25519(self, private_key: str = None):
        cmd = [self.executable_path, "x25519"]
        if private_key:
            cmd.extend(['-i', private_key])
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
        m = re.match(r'Private\s*[Kk]ey:\s*(.+)\n(?:Public\s*[Kk]ey|Password(?:\s*\(PublicKey\))?):\s*(.+)', output)
        if m:
            private, public = m.groups()
            return {
                "private_key": private,
                "public_key": public
            }

    def __capture_process_logs(self, proc):
        def capture_and_debug_log():
            while proc.poll() is None:
                output = proc.stdout.readline()
                if output:
                    output = output.strip()
                    self._logs_buffer.append(output)
                    for buf in list(self._temp_log_buffers.values()):
                        buf.append(output)
                    logger.debug(output)

        def capture_only():
            while proc.poll() is None:
                output = proc.stdout.readline()
                if output:
                    output = output.strip()
                    self._logs_buffer.append(output)
                    for buf in list(self._temp_log_buffers.values()):
                        buf.append(output)

        if DEBUG:
            threading.Thread(target=capture_and_debug_log, daemon=True).start()
        else:
            threading.Thread(target=capture_only, daemon=True).start()

    @contextmanager
    def get_logs(self):
        buf = deque(self._logs_buffer, maxlen=100)
        buf_id = id(buf)
        try:
            self._temp_log_buffers[buf_id] = buf
            yield buf
        finally:
            del self._temp_log_buffers[buf_id]
            del buf

    @property
    def started(self):
        if not self.process:
            return False

        if self.process.poll() is None:
            return True

        return False

    def _filter_local_inbounds(self, config: XRayConfig) -> XRayConfig:
        """Restrict the config used to start the *local* Xray process to the
        inbounds listed in INBOUNDS (master-only setting). Returns a separate
        copy; the config object passed in (which is also handed to nodes) is
        never mutated, so nodes keep receiving the full, unfiltered config.
        """
        if not INBOUNDS:
            return config

        keep_tags = set(INBOUNDS) | {API_INBOUND_TAG}
        inbounds = config.get("inbounds", [])
        kept = [inbound for inbound in inbounds if inbound.get("tag") in keep_tags]
        dropped = [inbound.get("tag") for inbound in inbounds if inbound.get("tag") not in keep_tags]

        if not dropped:
            return config

        filtered = config.copy()
        filtered["inbounds"] = kept
        logger.info(
            f"INBOUNDS filter: starting local Xray with {[i.get('tag') for i in kept]}, "
            f"skipping {dropped} (still sent to nodes unfiltered)"
        )
        return filtered

    def start(self, config: XRayConfig):
        if self.started is True:
            raise RuntimeError("Xray is started already")

        config = self._filter_local_inbounds(config)

        if config.get('log', {}).get('logLevel') in ('none', 'error'):
            config['log']['logLevel'] = 'warning'

        cmd = [
            self.executable_path,
            "run",
            '-config',
            'stdin:'
        ]
        self.process = subprocess.Popen(
            cmd,
            env=self._env,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True
        )
        self.process.stdin.write(config.to_json())
        self.process.stdin.flush()
        self.process.stdin.close()
        logger.warning(f"Xray core {self.version} started")

        self.__capture_process_logs(self.process)

        # execute on start functions
        for func in self._on_start_funcs:
            threading.Thread(target=func).start()

    def stop(self):
        if not self.started:
            return

        proc = self.process
        self.process = None
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        logger.warning("Xray core stopped")

        # execute on stop functions
        for func in self._on_stop_funcs:
            threading.Thread(target=func).start()

    def restart(self, config: XRayConfig):
        if not self._restart_lock.acquire(blocking=False):
            return

        try:
            logger.warning("Restarting Xray core...")
            self.stop()
            self.start(config)
        finally:
            self._restart_lock.release()

    def on_start(self, func: callable):
        self._on_start_funcs.append(func)
        return func

    def on_stop(self, func: callable):
        self._on_stop_funcs.append(func)
        return func
