"""
MySQL 集成测试。

使用 mysql-connector-python。

环境变量：

    SMARTOPS_MYSQL_HOST
    SMARTOPS_MYSQL_PORT
    SMARTOPS_MYSQL_USER
    SMARTOPS_MYSQL_PASSWORD
    SMARTOPS_MYSQL_DATABASE
"""

from __future__ import annotations

import pytest


def test_mysql_connection(
    test_config,
):
    """
    测试 MySQL TCP / SQL 连接。
    """
    mysql = pytest.importorskip(
        "mysql.connector"
    )

    try:
        connection = mysql.connect(
            host=test_config.mysql_host,
            port=test_config.mysql_port,
            user=test_config.mysql_user,
            password=test_config.mysql_password,
            database=test_config.mysql_database,
            connection_timeout=5,
        )
    except Exception as exc:
        pytest.skip(
            f"MySQL 当前不可用：{exc}"
        )

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT 1"
        )

        result = cursor.fetchone()

        assert result == (1,)

        cursor.close()

    finally:
        connection.close()


def test_mysql_server_version(
    test_config,
):
    """
    测试 MySQL VERSION()。
    """
    mysql = pytest.importorskip(
        "mysql.connector"
    )

    try:
        connection = mysql.connect(
            host=test_config.mysql_host,
            port=test_config.mysql_port,
            user=test_config.mysql_user,
            password=test_config.mysql_password,
            database=test_config.mysql_database,
            connection_timeout=5,
        )
    except Exception as exc:
        pytest.skip(
            f"MySQL 当前不可用：{exc}"
        )

    try:
        cursor = connection.cursor()

        cursor.execute(
            "SELECT VERSION()"
        )

        result = cursor.fetchone()

        assert result is not None
        assert isinstance(
            result[0],
            str,
        )

        cursor.close()

    finally:
        connection.close()