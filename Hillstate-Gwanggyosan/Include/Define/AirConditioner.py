import json
from Device import *


class AirConditioner(Device):
    temp_current: int = 0  # 현재 온도
    temp_current_prev: int = 0  # 현재 온도 버퍼
    temp_config: int = 0  # 냉방 설정 온도
    temp_config_prev: int = 0  # 냉방 설정 온도 버퍼
    temp_range: List[int]  # 설정 가능한 온도값의 범위
    mode: int = -1  # 운전모드
    mode_prev: int = -1  # 운전모드 버퍼
    rotation_speed: int = -1  # 풍량
    rotation_speed_prev: int = -1  # 풍량 버퍼

    def __init__(self, name: str = 'AirConditioner', index: int = 0, room_index: int = 0):
        super().__init__(name, index, room_index)
        self.dev_type = DeviceType.AIRCONDITIONER
        self.unique_id = f'airconditioner_{self.room_index}_{self.index}'
        self.mqtt_publish_topic = f'home/state/airconditioner/{self.room_index}/{self.index}'
        self.mqtt_subscribe_topic = f'home/command/airconditioner/{self.room_index}/{self.index}'
        self.setHomeAssistantConfigTopic()
        self.temp_range = [0, 100]
    
    def setDefaultName(self):
        self.name = 'AirConditioner'

    def publishMQTT(self):
        # https://ddhometech.wordpress.com/2021/01/03/ha-mqtt-hvac-integration-using-tasmota-ir-bridge/
        if self.state:
            state = 'COOLING'
        else:
            state = 'INACTIVE'
        target_state = 'COOL'
        obj = {
            "active": self.state,
            "state": state,
            "target_state": target_state,
            "currentTemperature": self.temp_current,
            "targetTemperature": self.temp_config,
            "timer": int(self.isTimerOnOffRunning())
        }
        if self.rotation_speed == 0x02:  # 미풍
            obj['rotationspeed'] = 50
            obj['rotationspeed_name'] = 'Min'
        elif self.rotation_speed == 0x03:  # 약풍
            obj['rotationspeed'] = 75
            obj['rotationspeed_name'] = 'Medium'
        elif self.rotation_speed == 0x04:  # 강풍
            obj['rotationspeed'] = 100
            obj['rotationspeed_name'] = 'Max'
        else:
            obj['rotationspeed'] = 25
            obj['rotationspeed_name'] = 'Auto'
        if self.mqtt_client is not None:
            self.mqtt_client.publish(self.mqtt_publish_topic, json.dumps(obj), 1)

    def setHomeAssistantConfigTopic(self):
        self.mqtt_config_topic = f'{self.ha_discovery_prefix}/climate/{self.unique_id}/config'

    def configMQTT(self):
        obj = {
            "name": self.name,
            "object_id": self.unique_id,
            "unique_id": self.unique_id,
            "modes": ["off", "cool"],
            "fan_modes": ["Max", "Medium", "Min", "Auto"],
            "mode_state_topic": self.mqtt_publish_topic,
            "mode_state_template": "{% if value_json.active %} cool {% else %} off {% endif %}",
            "mode_command_topic": self.mqtt_subscribe_topic,
            "mode_command_template": '{% set values = {"off": 0, "cool": 1} %} \
                                      { "active": {{ values[value] if value in values.keys() else 0 }} }',
            "temperature_state_topic": self.mqtt_publish_topic,
            "temperature_state_template": "{{ value_json.targetTemperature }}",
            "temperature_command_topic": self.mqtt_subscribe_topic,
            "temperature_command_template": '{ "targetTemperature": {{ value }} }',
            "current_temperature_topic": self.mqtt_publish_topic,
            "current_temperature_template": "{{ value_json.currentTemperature }}",
            "fan_mode_command_topic": self.mqtt_subscribe_topic,
            "fan_mode_command_template": '{ "rotationspeed_name": "{{ value }}" }',
            "fan_mode_state_topic": self.mqtt_publish_topic,
            "fan_mode_state_template": "{{ value_json.rotationspeed_name }}",
            "min_temp": self.temp_range[0],
            "max_temp": self.temp_range[1],
            "precision": 1,
        }
        if self.mqtt_client is not None:
            self.mqtt_client.publish(self.mqtt_config_topic, json.dumps(obj), 1, True)

    def setTemperatureRange(self, range_min: int, range_max: int):
        self.temp_range[0] = range_min
        self.temp_range[1] = range_max
        self.temp_current = max(range_min, min(range_max, self.temp_current))
        self.temp_config = max(range_min, min(range_max, self.temp_config))
        writeLog(f"{str(self)} Set Temperature Range ({self.temp_range[0]}~{self.temp_range[1]}), {self.temp_current}, {self.temp_config}", self)
    
    def updateState(self, state: int, **kwargs):
        self.state = state
        if not self.init:
            self.publishMQTT()
            self.init = True
        if self.state != self.state_prev:
            self.publishMQTT()
        self.state_prev = self.state
        # 현재온도
        temp_current = kwargs.get('temp_current')
        if temp_current is not None:
            # self.temp_current = temp_current
            self.temp_current = max(self.temp_range[0], min(self.temp_range[1], temp_current))
            if self.temp_current != self.temp_current_prev:
                self.publishMQTT()
            self.temp_current_prev = self.temp_current
        # 희망온도
        temp_config = kwargs.get('temp_config')
        if temp_config is not None:
            # self.temp_config = temp_config
            self.temp_config = max(self.temp_range[0], min(self.temp_range[1], temp_config))
            if self.temp_config != self.temp_config_prev:
                self.publishMQTT()
            self.temp_config_prev = self.temp_config
        # 모드
        # 0=자동, 1=냉방, 2=제습, 3=공기청정
        mode = kwargs.get('mode')
        if mode is not None:
            self.mode = mode
            if self.mode != self.mode_prev:
                self.publishMQTT()
            self.mode_prev = self.mode
        # 풍량
        # 1=자동, 2=미풍, 3=약풍, 4=강풍
        rotation_speed = kwargs.get('rotation_speed')
        if rotation_speed is not None:
            self.rotation_speed = rotation_speed
            if self.rotation_speed != self.rotation_speed_prev:
                self.publishMQTT()
            self.rotation_speed_prev = self.rotation_speed

    def makePacketQueryState(self) -> bytearray:
        # F7 0B 01 1C 01 40 XX 00 00 YY EE
        # XX: 상위 4비트=공간 인덱스, 하위 4비트=디바이스 인덱스 (1-based
        # YY: Checksum (XOR SUM)
        packet = bytearray([0xF7, 0x0B, 0x01, 0x1C, 0x01, 0x40])
        packet.append((self.room_index << 4) + (self.index + 1))
        packet.extend([0x00, 0x00])
        packet.append(self.calcXORChecksum(packet))
        packet.append(0xEE)
        return packet

    def makePacketSetState(self, state: bool) -> bytearray:
        # F7 0B 01 1C 02 40 XX YY 00 ZZ EE
        # XX: 상위 4비트=공간 인덱스, 하위 4비트=디바이스 인덱스 (1-based
        # YY: 0x01=On, 0x02=Off
        # ZZ: Checksum (XOR SUM)
        packet = bytearray([0xF7, 0x0B, 0x01, 0x1C, 0x02, 0x40])
        packet.append((self.room_index << 4) + (self.index + 1))
        if state:
            packet.extend([0x01, 0x00])
        else:
            packet.extend([0x02, 0x00])
        packet.append(self.calcXORChecksum(packet))
        packet.append(0xEE)
        return packet

    def makePacketSetTemperature(self, temperature: int) -> bytearray:
        # F7 0B 01 1C 02 45 XX YY 00 ZZ EE
        # XX: 상위 4비트=공간 인덱스, 하위 4비트=디바이스 인덱스 (1-based
        # YY: 온도 설정값
        # ZZ: Checksum (XOR SUM)
        packet = bytearray([0xF7, 0x0B, 0x01, 0x1C, 0x02, 0x45])
        packet.append((self.room_index << 4) + (self.index + 1))
        packet.extend([temperature & 0xFF, 0x00])
        packet.append(self.calcXORChecksum(packet))
        packet.append(0xEE)
        return packet

    def makePacketSetRotationSpeed(self, rotation_speed: int) -> bytearray:
        # F7 0B 01 1C 02 5D XX YY 00 ZZ EE
        # XX: 상위 4비트=공간 인덱스, 하위 4비트=디바이스 인덱스 (1-based)
        # YY: 0x01=자동, 0x02=미풍, 0x03=약풍, 0x04=강풍
        # ZZ: Checksum (XOR SUM)
        packet = bytearray([0xF7, 0x0B, 0x01, 0x1C, 0x02, 0x5D])
        packet.append((self.room_index << 4) + (self.index + 1))
        packet.extend([rotation_speed & 0xFF, 0x00])
        packet.append(self.calcXORChecksum(packet))
        packet.append(0xEE)
        return packet

    def makePacketSetMode(self, mode: int) -> bytearray:
        # F7 0B 01 1C 02 5C XX YY 00 ZZ EE
        # XX: 상위 4비트=공간 인덱스, 하위 4비트=디바이스 인덱스 (1-based
        # YY: 0x0=자동, 0x01=냉방, 0x03=제습, 0x04=공기청정
        # ZZ: Checksum (XOR SUM)
        packet = bytearray([0xF7, 0x0B, 0x01, 0x1C, 0x02, 0x5C])
        packet.append((self.room_index << 4) + (self.index + 1))
        packet.extend([mode & 0xFF, 0x00])
        packet.append(self.calcXORChecksum(packet))
        packet.append(0xEE)
        return packet
