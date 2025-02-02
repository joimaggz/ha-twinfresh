"""Helper api function for sending commands to the fan controller."""
import logging
import socket

from .const import DIRECTION_ALTERNATING
from .const import DIRECTIONS
from .const import FAN_SPEEDS
from .const import PRESET_MODE_AUTO
from .const import PRESET_MODE_PARTY
from .const import PRESET_MODE_SLEEP

LOGGER = logging.getLogger(__name__)

# forward = pull air out of the room
# reverse = pull air into the room from outside
# alternating = change directions (used for oscilating option in fan)

PACKET_PREFIX = "FDFD"
PACKET_PROTOCOL_TYPE = "02"
PACKET_SIZE_ID = "10"

FUNC_READ = "01"
FUNC_WRITE = "02"
FUNC_READ_WRITE = "03"
FUNC_INC = "04"
FUNC_DEC = "05"
FUNC_RESULT = "06"  # result func (FUNC = 0x01, 0x03, 0x04, 0x05).

RETURN_CHANGE_FUNC = "FC"
RETURN_INVALID = "FD"
RETURN_VALUE_SIZE = "FE"
RETURN_HIGH_BYTE = "FF"

COMMAND_ON_OFF = "01"
COMMAND_SPEED = "02"
COMMAND_CURRENT_HUMIDITY = "25"
COMMAND_DIRECTION = "B7"
COMMAND_DEVICE_TYPE = "B9"
COMMAND_MODE = "07"

COMMAND_FUNCTION_R = "01"
COMMAND_FUNCTION_W = "02"
COMMAND_FUNCTION_RW = "03"
COMMAND_FUNCTION_INC = "04"
COMMAND_FUNCTION_DEC = "05"

POWER_OFF = "00"
POWER_ON = "01"
POWER_TOGGLE = "02"

MODE_OFF = "01"
MODE_SLEEP = "01"
MODE_PARTY = "02"
MODES = {
    MODE_OFF: PRESET_MODE_AUTO,
    MODE_SLEEP: PRESET_MODE_SLEEP,
    MODE_PARTY: PRESET_MODE_PARTY,
}


class SikuV2Api:
    """Handle requests to the fan controller."""

    def __init__(self, host: str, port: int, idnum: str, password: str) -> None:
        """Initialize."""
        self.host = host
        self.port = port
        self.idnum = idnum
        self.password = password

    async def status(self) -> dict:
        """Get status from fan controller."""
        cmd = f"{COMMAND_DEVICE_TYPE}{COMMAND_ON_OFF}{COMMAND_SPEED}{COMMAND_CURRENT_HUMIDITY}{COMMAND_DIRECTION}{COMMAND_MODE}".upper()
        hexlist = await self._send_command(FUNC_READ, cmd)
        data = await self._parse_response(hexlist)
        return await self._translate_response(data)

    async def power_on(self) -> None:
        """Power on fan."""
        cmd = f"{COMMAND_ON_OFF}{POWER_ON}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def power_off(self) -> None:
        """Power off fan."""
        cmd = f"{COMMAND_ON_OFF}{POWER_OFF}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def speed(self, speed: str) -> None:
        """Set fan speed."""
        if speed not in FAN_SPEEDS:
            raise ValueError(f"Invalid fan speed: {speed}")
        cmd = f"{COMMAND_SPEED}{speed}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def direction(self, direction: str) -> None:
        """Set fan direction."""
        # if direction is in DIRECTIONS values translate it to the key value
        if direction in DIRECTIONS.values():
            direction = list(DIRECTIONS.keys())[
                list(DIRECTIONS.values()).index(direction)
            ]
        if direction not in DIRECTIONS:
            raise ValueError(f"Invalid fan direction: {direction}")
        cmd = f"{COMMAND_DIRECTION}{direction}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def sleep(self) -> None:
        """Set fan to sleep mode."""
        cmd = f"{COMMAND_ON_OFF}{POWER_ON}{COMMAND_MODE}{MODE_SLEEP}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def party(self) -> None:
        """Set fan to party mode."""
        cmd = f"{COMMAND_ON_OFF}{POWER_ON}{COMMAND_MODE}{MODE_PARTY}".upper()
        await self._send_command(FUNC_READ_WRITE, cmd)
        return await self.status()

    async def humidity(self) -> dict:
        """Get humidity data from the fan controller."""
        cmd = f"{COMMAND_CURRENT_HUMIDITY}".upper()
        hexlist = await self._send_command(FUNC_READ, cmd)
        data = await self._parse_response(hexlist)
        return data.get(COMMAND_CURRENT_HUMIDITY, None)

    def _checksum(self, data: str) -> str:
        """Calculate checksum for packet and return it as high order byte hex string."""
        hexlist = self._hexlist(data)

        checksum = 0
        for hexstr in hexlist[2:]:
            checksum += int(hexstr, 16)
        checksum_str = f"{checksum:04X}"
        return f"{checksum_str[2:4]:02}{checksum_str[0:2]:02}"

    def _verify_checksum(self, hexlist: list[str]) -> bool:
        """Verify checksum of packet."""
        checksum = self._checksum("".join(hexlist[0:-2]))
        LOGGER.debug("checksum: %s", checksum)
        LOGGER.debug("verify if %s == %s", checksum, hexlist[-2] + hexlist[-1])
        return checksum == hexlist[-2] + hexlist[-1]

    def _hexlist(self, hexstr: str) -> list[str]:
        """Convert hex string to list of hex strings."""
        return [hexstr[i : i + 2] for i in range(0, len(hexstr), 2)]

    def _login_packet(self) -> str:
        """Build initial login part of packet."""
        id_hex = self.idnum.encode("utf-8").hex()
        password_size = f"{len(self.password):02x}"
        password_hex = self.password.encode("utf-8").hex()
        packet_str = (
            PACKET_PREFIX
            + PACKET_PROTOCOL_TYPE
            + PACKET_SIZE_ID
            + id_hex
            + password_size
            + str(password_hex)
        ).upper()
        return packet_str

    def _build_packet(self, func: str, data: str) -> str:
        """Build packet for sending to fan controller."""
        packet_str = (self._login_packet() + func + data).upper()
        LOGGER.debug("packet string: %s", packet_str)
        packet_str += self._checksum(packet_str)
        LOGGER.debug("packet string: %s", packet_str)
        return packet_str

    async def _send_command(self, func: str, data: str) -> list[str]:
        """Send command to fan controller."""
        # enter the data content of the UDP packet as hex
        packet_str = self._build_packet(func, data)
        packet_data = bytes.fromhex(packet_str)
        LOGGER.debug("packet data: %s", packet_data)

        # initialize a socket, think of it as a cable
        # SOCK_DGRAM specifies that this is UDP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0) as s:
            s.settimeout(10)

            server_address = (self.host, self.port)
            LOGGER.debug(
                'sending "%s" size(%s) to %s',
                packet_data.hex(),
                len(packet_data),
                server_address,
            )
            s.sendto(packet_data, server_address)

            # Receive response
            result_data, server = s.recvfrom(256)
            LOGGER.debug(
                "receive data: %s size(%s) from %s",
                result_data,
                len(result_data),
                server,
            )
            result_str = result_data.hex().upper()
            LOGGER.debug("receive string: %s", result_str)

            result_hexlist = ["".join(x) for x in zip(*[iter(result_str)] * 2)]
            if not self._verify_checksum(result_hexlist):
                raise Exception("Checksum error")
            LOGGER.debug("returning hexlist %s", result_hexlist)
            return result_hexlist

    async def _translate_response(self, data: dict) -> dict:
        """Translate response data to dict."""
        LOGGER.debug("translate response: %s", data)
        try:
            is_on = bool(data[COMMAND_ON_OFF] == POWER_ON)
        except KeyError:
            is_on = False
        try:
            speed = f"{int(data[COMMAND_SPEED], 16):02}"
        except KeyError:
            speed = "00"
        try:
            direction = DIRECTIONS[data[COMMAND_DIRECTION]]
            oscillating = bool(direction == DIRECTION_ALTERNATING)
        except KeyError:
            direction = None
            oscillating = True
        try:
            mode = MODES[data[COMMAND_MODE]]
        except KeyError:
            mode = PRESET_MODE_AUTO
        return {
            "is_on": is_on,
            "speed": speed,
            "oscillating": oscillating,
            "direction": direction,
            "mode": mode,
        }

    async def _parse_response(self, hexlist: list[str]) -> dict:
        """Translate response from fan controller."""
        data = {}
        try:
            start = 0

            # prefix
            LOGGER.debug("start: %s", start)
            LOGGER.debug("hexlist: %s", "".join(hexlist[start:2]))
            if "".join(hexlist[0:2]) != PACKET_PREFIX:
                raise Exception("Invalid packet prefix")
            start += 2

            # protocol type
            LOGGER.debug("start: %s", start)
            LOGGER.debug("hexlist: %s", "".join(hexlist[start]))
            if "".join(hexlist[start]) != PACKET_PROTOCOL_TYPE:
                raise Exception("Invalid packet protocol type")
            start += 1

            # id
            LOGGER.debug("start: %s", start)
            LOGGER.debug("hexlist: %s", "".join(hexlist[start]))
            start += 1 + int("".join(hexlist[start]), 16)

            # password
            LOGGER.debug("start: %s", start)
            LOGGER.debug("hexlist: %s", "".join(hexlist[start]))
            start += 1 + int("".join(hexlist[start]), 16)

            # function
            if "".join(hexlist[start]) != FUNC_RESULT:
                raise Exception("Invalid result function")
            LOGGER.debug("start: %s", start)
            LOGGER.debug("hexlist: %s", "".join(hexlist[start]))
            start += 1

            # data
            LOGGER.debug("loop data %s %s", start, len(hexlist) - 2)
            i = start
            while i < (len(hexlist) - 2):
                LOGGER.debug("parse data %s : %s", i, hexlist[i])
                parameter = hexlist[i]
                value_size = 1
                cmd = ""
                value = ""
                if parameter == RETURN_CHANGE_FUNC:
                    LOGGER.debug("special function, change base function")
                    raise Exception(
                        "special function, change base function not implemented"
                    )
                elif parameter == RETURN_INVALID:
                    i += 1
                    cmd = hexlist[i]
                    LOGGER.debug("special function, invalid cmd:%s", cmd)
                elif parameter == RETURN_VALUE_SIZE:
                    i += 1
                    value_size = int(hexlist[i], 16)
                    LOGGER.debug("special function, value size %s", value_size)
                    i += 1
                    cmd = hexlist[i]
                    value = "".join(hexlist[i + 1 : i + 1 + value_size])
                    # reverse byte order
                    value = "".join(
                        [value[idx : idx + 2] for idx in range(0, len(value), 2)][::-1]
                    )
                    i += value_size
                elif parameter == RETURN_HIGH_BYTE:
                    LOGGER.debug("special function, high byte")
                    raise Exception("special function, high byte not implemented")
                else:
                    cmd = parameter
                    i += 1
                    value = hexlist[i]
                    LOGGER.debug("normal function, cmd:%s value:%s", cmd, value)

                data.update({cmd: value})
                LOGGER.debug(
                    "return data cmd:%s value:%s",
                    cmd,
                    value,
                )
                i += 1
        except KeyError as ex:
            raise Exception(
                f"Error translating response from fan controller: {str(ex)}"
            ) from ex
        return data
