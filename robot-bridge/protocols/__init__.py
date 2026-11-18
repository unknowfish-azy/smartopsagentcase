"""协议适配器包：按 device_key 的 transport.protocolId 选择实现。"""

from __future__ import annotations

from .base import BridgeProtocolError, ProtocolAdapter
from .generic_ble_car_v1 import GenericBleCarV1Adapter
from .generic_ble_dog_v1 import GenericBleDogV1Adapter
from .generic_ble_robot_v1 import GenericBleRobotV1Adapter
from .generic_ble_spider_v1 import GenericBleSpiderV1Adapter
from .generic_mcu_v1 import GenericMcuV1Adapter

_REGISTRY: dict[str, type[ProtocolAdapter]] = {
    GenericBleCarV1Adapter.PROTOCOL_ID: GenericBleCarV1Adapter,
    GenericBleDogV1Adapter.PROTOCOL_ID: GenericBleDogV1Adapter,
    GenericBleRobotV1Adapter.PROTOCOL_ID: GenericBleRobotV1Adapter,
    GenericBleSpiderV1Adapter.PROTOCOL_ID: GenericBleSpiderV1Adapter,
    GenericMcuV1Adapter.PROTOCOL_ID: GenericMcuV1Adapter,
}


# form_factor → 推荐协议 ID（台账里 form_factor 确定后 bridge.py run 模式
# 可查表选 adapter，避免台账 transport.protocolId 为空时无协议可用）
FORM_FACTOR_PROTOCOL: dict[str, str] = {
    "CAR": "generic-ble-car-v1",
    "DOG": "generic-ble-dog-v1",
    "ROBOT": "generic-ble-robot-v1",
    "SPIDER": "generic-ble-spider-v1",
}


def get_adapter(protocol_id: str, **options) -> ProtocolAdapter:
    """按 protocolId 取适配器；未登记的协议如实报错，不静默兜底。"""
    cls = _REGISTRY.get(protocol_id)
    if cls is None:
        raise BridgeProtocolError(f"未登记的协议适配器：{protocol_id}")
    return cls(**options)


def get_adapter_for_form_factor(form_factor: str) -> ProtocolAdapter:
    """按 form_factor 取适配器；未登记的形态如实报错。"""
    pf = FORM_FACTOR_PROTOCOL.get((form_factor or "").strip().upper())
    if pf is None:
        raise BridgeProtocolError(f"未登记形态的协议适配器：{form_factor}")
    return get_adapter(pf)
