"""PySide6 图形界面：每条隧道独立启停。"""

from __future__ import annotations

import sys
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QLineEdit, QMainWindow, QMessageBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPushButton, QInputDialog,
)

from config import ConfigStore
from tunnel import TunnelConfig, TunnelManager, TunnelStatus, status_presentation


class TunnelDialog(QDialog):
    """新建/编辑隧道：将连接参数、转发目标和运行设置分组录入。"""
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建隧道")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.tunnel_type = QComboBox()
        self.tunnel_type.addItem("本地转发（Local -L）", "LOCAL")
        self.tunnel_type.addItem("远程转发（Remote -R）", "REMOTE")
        self.tunnel_type.addItem("动态代理（Dynamic -D）", "DYNAMIC")
        self.listen_host = QLineEdit("127.0.0.1")
        self.listen_port = QSpinBox(); self.listen_port.setRange(1, 65535); self.listen_port.setValue(1080)
        self.target_host = QLineEdit()
        self.target_port = QSpinBox(); self.target_port.setRange(1, 65535); self.target_port.setValue(22)
        self.ssh_host = QLineEdit()
        self.ssh_port = QSpinBox(); self.ssh_port.setRange(1, 65535); self.ssh_port.setValue(22)
        self.ssh_user = QLineEdit()
        self.auth_method = QComboBox()
        self.auth_method.addItem("密码", "password")
        self.auth_method.addItem("私钥文件", "private_key")
        self.private_key_path = QLineEdit()
        self.private_key_button = QPushButton("选择私钥")
        self.private_key_button.clicked.connect(self.choose_private_key)
        self.auth_method.currentIndexChanged.connect(self._sync_auth_controls)
        self.tunnel_type.currentIndexChanged.connect(self._sync_forward_controls)
        self.connect_timeout = QSpinBox(); self.connect_timeout.setRange(1, 120); self.connect_timeout.setValue(10)
        self.keepalive = QSpinBox(); self.keepalive.setRange(0, 3600); self.keepalive.setValue(30)
        self.compression = QCheckBox("启用 SSH 压缩")
        self.auto_reconnect = QCheckBox("断线后自动重连")
        form.addRow("名称", self.name)
        form.addRow("类型", self.tunnel_type)
        form.addRow("监听地址", self.listen_host)
        form.addRow("转发端口", self.listen_port)
        form.addRow("目标服务器", self.target_host)
        form.addRow("目标端口", self.target_port)
        form.addRow("SSH 服务器", self.ssh_host)
        form.addRow("SSH 端口", self.ssh_port)
        form.addRow("SSH 用户", self.ssh_user)
        form.addRow("认证方式", self.auth_method)
        key_row = QWidget()
        key_layout = QVBoxLayout(key_row); key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.private_key_path); key_layout.addWidget(self.private_key_button)
        form.addRow("私钥文件", key_row)
        form.addRow("连接超时（秒）", self.connect_timeout)
        form.addRow("Keepalive（秒，0 为关闭）", self.keepalive)
        form.addRow("压缩", self.compression)
        form.addRow("自动重连", self.auto_reconnect)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._sync_auth_controls()
        self._sync_forward_controls()

    def choose_private_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 SSH 私钥文件")
        if path:
            self.private_key_path.setText(path)

    def _sync_auth_controls(self) -> None:
        enabled = self.auth_method.currentData() == "private_key"
        self.private_key_path.setEnabled(enabled)
        self.private_key_button.setEnabled(enabled)

    def _sync_forward_controls(self) -> None:
        # 三种模式都需要本地监听端口；动态代理只隐藏固定目标字段。
        dynamic = self.tunnel_type.currentData() == "DYNAMIC"
        self.target_host.setEnabled(not dynamic)
        self.target_port.setEnabled(not dynamic)

    def load_config(self, config: TunnelConfig) -> None:
        self.name.setText(config.name)
        index = self.tunnel_type.findData(config.tunnel_type)
        if index >= 0:
            self.tunnel_type.setCurrentIndex(index)
        self.listen_host.setText(config.listen_host)
        self.listen_port.setValue(config.listen_port)
        self.target_host.setText(config.target_host)
        self.target_port.setValue(config.target_port or 1)
        self.ssh_host.setText(config.ssh_host)
        self.ssh_port.setValue(config.ssh_port)
        self.ssh_user.setText(config.ssh_user)
        auth_index = self.auth_method.findData(config.auth_method)
        if auth_index >= 0:
            self.auth_method.setCurrentIndex(auth_index)
        self.private_key_path.setText(config.private_key_path)
        self.connect_timeout.setValue(config.connect_timeout)
        self.keepalive.setValue(config.keepalive_seconds)
        self.compression.setChecked(config.compression)
        self.auto_reconnect.setChecked(config.auto_reconnect)

    def config(self) -> TunnelConfig:
        return TunnelConfig(
            name=self.name.text().strip(), tunnel_type=self.tunnel_type.currentData(),
            listen_host=self.listen_host.text().strip(), listen_port=self.listen_port.value(),
            target_host=self.target_host.text().strip(), target_port=self.target_port.value(),
            ssh_host=self.ssh_host.text().strip(), ssh_port=self.ssh_port.value(), ssh_user=self.ssh_user.text().strip(),
            auth_method=self.auth_method.currentData(), private_key_path=self.private_key_path.text().strip(),
            connect_timeout=self.connect_timeout.value(), keepalive_seconds=self.keepalive.value(),
            compression=self.compression.isChecked(), auto_reconnect=self.auto_reconnect.isChecked(),
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("图形化的端口转发工具")
        self.resize(980, 560)
        self.store = ConfigStore()
        self.manager = TunnelManager()
        self.configs = self.store.load()
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["名称", "类型", "转发端口", "目标服务器", "SSH 服务器", "状态", "设置", "操作"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout = QVBoxLayout()
        layout.addWidget(self.table)
        self.add_button = QPushButton("新建隧道")
        self.add_button.clicked.connect(self.add_tunnel)
        self.open_all_button = QPushButton("打开所有隧道")
        self.open_all_button.clicked.connect(self.open_all)
        self.stop_all_button = QPushButton("停止所有隧道")
        self.stop_all_button.clicked.connect(self.stop_all)
        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.close)
        for button in (self.add_button, self.open_all_button, self.stop_all_button, self.exit_button):
            layout.addWidget(button)
        root = QWidget()
        root.setLayout(layout)
        self.setCentralWidget(root)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.refresh)
        self.status_timer.start()
        self.refresh()

    def refresh(self) -> None:
        self.table.setRowCount(len(self.configs))
        for row, config in enumerate(self.configs):
            target = "SOCKS5 动态目标" if config.tunnel_type == "DYNAMIC" else f"{config.target_host}:{config.target_port}"
            settings = f"超时 {config.connect_timeout}s · 保活 {config.keepalive_seconds}s" + (" · 压缩" if config.compression else "")
            values = [config.name, {"LOCAL": "本地转发（Local -L）", "REMOTE": "远程转发（Remote -R）", "DYNAMIC": "动态代理（Dynamic -D）"}[config.tunnel_type], f"{config.listen_host}:{config.listen_port}", target, f"{config.ssh_user}@{config.ssh_host}:{config.ssh_port}", settings, ""]
            for column, value in enumerate(values[:-1]):
                self.table.setItem(row, column, QTableWidgetItem(value))
            status_item = QTableWidgetItem()
            status_text, status_color = status_presentation(self.manager.status(config.name))
            status_item.setText(status_text)
            status_item.setForeground(QColor(status_color))
            status_item.setData(Qt.ItemDataRole.UserRole, self.manager.status(config.name).value)
            self.table.setItem(row, 5, status_item)
            action_widget = QWidget()
            action_layout = QVBoxLayout(action_widget)
            action_layout.setContentsMargins(2, 2, 2, 2)
            toggle_button = QPushButton("停止" if self.manager.status(config.name) == TunnelStatus.RUNNING else "启用")
            toggle_button.clicked.connect(lambda _checked=False, item=config: self.toggle(item))
            edit_button = QPushButton("编辑")
            edit_button.clicked.connect(lambda _checked=False, item=config: self.edit_tunnel(item))
            delete_button = QPushButton("删除")
            delete_button.clicked.connect(lambda _checked=False, item=config: self.delete_tunnel(item))
            for control in (toggle_button, edit_button, delete_button):
                action_layout.addWidget(control)
            self.table.setCellWidget(row, 7, action_widget)

    def add_tunnel(self) -> None:
        dialog = TunnelDialog(self)
        if not dialog.exec():
            return
        config = dialog.config()
        try:
            from tunnel import validate_tunnel_config
            validate_tunnel_config(config)
        except ValueError as error:
            QMessageBox.warning(self, "配置无效", str(error))
            return
        self.configs.append(config)
        self.store.save(self.configs)
        self.refresh()

    def edit_tunnel(self, original: TunnelConfig) -> None:
        """编辑已有隧道；运行中的隧道先停止，保存后保持停止状态。"""
        dialog = TunnelDialog(self)
        dialog.setWindowTitle("编辑隧道")
        dialog.load_config(original)
        if not dialog.exec():
            return
        updated = dialog.config()
        try:
            from tunnel import validate_tunnel_config
            validate_tunnel_config(updated)
        except ValueError as error:
            QMessageBox.warning(self, "配置无效", str(error))
            return
        if original.name != updated.name and any(item.name == updated.name for item in self.configs):
            QMessageBox.warning(self, "名称重复", "隧道名称已存在，请使用其他名称。")
            return
        if self.manager.status(original.name) == TunnelStatus.RUNNING:
            self.manager.stop(original.name)
        index = self.configs.index(original)
        self.configs[index] = updated
        self.store.save(self.configs)
        self.refresh()

    def delete_tunnel(self, config: TunnelConfig) -> None:
        """删除隧道前必须二次确认，并先关闭活动转发。"""
        answer = QMessageBox.question(
            self, "确认删除", f"确定要删除隧道“{config.name}”吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.manager.stop(config.name)
        self.configs = [item for item in self.configs if item is not config]
        self.store.save(self.configs)
        self.refresh()

    def toggle(self, config: TunnelConfig) -> None:
        try:
            if self.manager.status(config.name) == TunnelStatus.RUNNING:
                self.manager.stop(config.name)
            else:
                password = None
                if config.auth_method == "password":
                    password, ok = QInputDialog.getText(self, "SSH 认证", f"请输入 {config.ssh_user}@{config.ssh_host} 的密码", echo=QLineEdit.EchoMode.Password)
                    if not ok:
                        return
                self.manager.start(config, password=password)
        except Exception as error:
            QMessageBox.critical(self, "隧道启动失败", str(error))
        self.refresh()

    def open_all(self) -> None:
        """批量启动，密码按隧道逐条询问，失败项保留异常状态。"""
        def password_provider(config):
            if config.auth_method == "private_key":
                return None
            password, ok = QInputDialog.getText(self, "SSH 认证", f"请输入 {config.ssh_user}@{config.ssh_host} 的密码", echo=QLineEdit.EchoMode.Password)
            if not ok:
                raise RuntimeError("用户取消认证")
            return password

        result = self.manager.start_all(self.configs, password_provider)
        self.refresh()
        if result["failed"]:
            QMessageBox.warning(self, "部分隧道启动失败", "\n".join(f"{name}: {error}" for name, error in result["failed"].items()))

    def stop_all(self) -> None:
        self.manager.stop_all()
        self.refresh()

    def closeEvent(self, event) -> None:
        self.status_timer.stop()
        self.manager.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
