import json
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import Mock, patch

from config import ConfigStore
from tunnel import TunnelConfig, TunnelManager, TunnelStatus, status_presentation, validate_tunnel_config


class TunnelConfigTests(unittest.TestCase):
    def test_status_presentation_uses_text_and_semantic_colors(self):
        self.assertEqual(status_presentation(TunnelStatus.RUNNING), ("运行中", "#2e9b62"))
        self.assertEqual(status_presentation(TunnelStatus.STOPPED), ("已停止", "#7a7a7a"))
        self.assertEqual(status_presentation(TunnelStatus.ERROR), ("连接失败", "#c33c3c"))
    def test_config_contains_forward_target_ssh_and_settings_fields(self):
        config = TunnelConfig(
            name="db",
            tunnel_type="LOCAL",
            listen_host="127.0.0.1",
            listen_port=15432,
            target_host="db.internal",
            target_port=5432,
            ssh_host="bastion.internal",
            ssh_port=22,
            ssh_user="ops",
            keepalive_seconds=30,
        )
        validate_tunnel_config(config)
        self.assertEqual(config.listen_port, 15432)
        self.assertEqual(config.target_host, "db.internal")
        self.assertEqual(config.ssh_host, "bastion.internal")
        self.assertEqual(config.keepalive_seconds, 30)

    def test_ssh_authentication_accepts_password_or_private_key(self):
        password_config = TunnelConfig(name="password", ssh_host="bastion", ssh_user="ops", auth_method="password", listen_port=1080, target_host="target", target_port=80)
        key_config = TunnelConfig(name="key", ssh_host="bastion", ssh_user="ops", auth_method="private_key", private_key_path="C:/keys/id_ed25519", listen_port=1080, target_host="target", target_port=80)
        validate_tunnel_config(password_config)
        validate_tunnel_config(key_config)
        with self.assertRaises(ValueError):
            validate_tunnel_config(TunnelConfig(name="invalid", ssh_host="bastion", ssh_user="ops", auth_method="private_key"))

    def test_local_and_remote_modes_require_a_listen_port(self):
        for tunnel_type in ("LOCAL", "REMOTE"):
            with self.assertRaises(ValueError):
                validate_tunnel_config(TunnelConfig(name=tunnel_type, tunnel_type=tunnel_type, ssh_host="bastion", ssh_user="ops", listen_port=0))

    def test_local_and_remote_modes_require_target_host_and_port(self):
        for tunnel_type in ("LOCAL", "REMOTE"):
            with self.assertRaises(ValueError):
                validate_tunnel_config(TunnelConfig(name=tunnel_type, tunnel_type=tunnel_type, ssh_host="bastion", ssh_user="ops", listen_port=1080, target_host=""))
        validate_tunnel_config(TunnelConfig(name="dynamic", tunnel_type="DYNAMIC", ssh_host="bastion", ssh_user="ops", listen_port=1080, target_host="", target_port=0))

    def test_accepts_supported_forwarding_types_and_rejects_unknown_type(self):
        for tunnel_type in ("LOCAL", "REMOTE", "DYNAMIC"):
            config = TunnelConfig(name=tunnel_type, tunnel_type=tunnel_type, ssh_host="bastion", ssh_port=22, ssh_user="ops", listen_port=1080, target_host="target" if tunnel_type != "DYNAMIC" else "", target_port=80 if tunnel_type != "DYNAMIC" else 0)
            validate_tunnel_config(config)
        with self.assertRaises(ValueError):
            validate_tunnel_config(TunnelConfig(name="bad", tunnel_type="FTP", ssh_host="bastion", ssh_port=22, ssh_user="ops"))

    def test_rejects_invalid_ports_and_missing_hosts(self):
        with self.assertRaises(ValueError):
            validate_tunnel_config(TunnelConfig(name="", ssh_host="", ssh_port=0))

    def test_config_store_does_not_persist_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tunnels.json"
            store = ConfigStore(path)
            config = TunnelConfig(name="db", ssh_host="bastion", ssh_port=22, ssh_user="ops", password="secret")
            store.save([config])
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotIn("password", raw[0])
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))

    def test_default_config_file_is_config_json_and_loads_saved_tunnels(self):
        with tempfile.TemporaryDirectory() as directory:
            old_dir = Path.cwd()
            try:
                import os
                os.chdir(directory)
                store = ConfigStore()
                config = TunnelConfig(name="loaded", ssh_host="bastion", ssh_user="ops", listen_port=1080, target_host="target", target_port=80)
                store.save([config])
                self.assertEqual(store.path.name, "config.json")
                loaded = ConfigStore().load()
                self.assertEqual([item.name for item in loaded], ["loaded"])
            finally:
                os.chdir(old_dir)


class TunnelManagerTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "manager"):
            self.manager.close()

    def test_start_all_keeps_starting_remaining_tunnels_after_one_failure(self):
        manager = TunnelManager()
        self.manager = manager
        manager.start = Mock(side_effect=[None, RuntimeError("connect failed")])
        configs = [
            TunnelConfig(name="one", ssh_host="a", ssh_user="ops"),
            TunnelConfig(name="two", ssh_host="b", ssh_user="ops"),
        ]

        result = manager.start_all(configs, password_provider=lambda _config: "secret")

        self.assertEqual(result["started"], ["one"])
        self.assertEqual(result["failed"], {"two": "connect failed"})
        self.assertEqual(manager.start.call_count, 2)

    @patch("tunnel.paramiko.SSHClient")
    def test_start_runs_connection_in_background_and_stop_closes_client(self, ssh_client_cls):
        client = ssh_client_cls.return_value
        manager = TunnelManager()
        self.manager = manager
        config = TunnelConfig(name="web", ssh_host="bastion", ssh_port=22, ssh_user="ops", listen_port=18080, target_port=8080, target_host="web")

        manager.start(config, password="secret")

        for _ in range(50):
            if manager.status(config.name) == TunnelStatus.RUNNING:
                break
            time.sleep(0.01)
        self.assertEqual(manager.status(config.name), TunnelStatus.RUNNING)
        self.assertTrue(client.connect.called)
        manager.stop(config.name)
        self.assertEqual(manager.status(config.name), TunnelStatus.STOPPED)
        client.close.assert_called_once()

    @patch("tunnel.paramiko.SSHClient")
    def test_disconnect_is_detected_and_status_changes_to_error(self, ssh_client_cls):
        client = ssh_client_cls.return_value
        transport = Mock()
        transport.is_active.return_value = False
        client.get_transport.return_value = transport
        manager = TunnelManager()
        self.manager = manager
        config = TunnelConfig(name="watched", ssh_host="bastion", ssh_user="ops", listen_port=18081, target_host="web", target_port=80)
        manager.start(config, password="secret")
        for _ in range(50):
            if manager.status(config.name) == TunnelStatus.RUNNING:
                break
            time.sleep(0.01)
        time.sleep(1.2)
        self.assertEqual(manager.status(config.name), TunnelStatus.ERROR)

    @patch("tunnel.paramiko.SSHClient")
    def test_stop_closes_forward_server_and_joins_listener_thread(self, ssh_client_cls):
        client = ssh_client_cls.return_value
        transport = Mock()
        transport.is_active.return_value = True
        client.get_transport.return_value = transport
        manager = TunnelManager()
        self.manager = manager
        config = TunnelConfig(name="cleanup", ssh_host="bastion", ssh_user="ops", listen_port=18082, target_host="web", target_port=80)
        manager.start(config, password="secret")
        for _ in range(50):
            if manager.status(config.name) == TunnelStatus.RUNNING:
                break
            time.sleep(0.01)
        manager.stop(config.name)
        self.assertEqual(manager.status(config.name), TunnelStatus.STOPPED)
        self.assertNotIn(config.name, manager._active)
        client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
