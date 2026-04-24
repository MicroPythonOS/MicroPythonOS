from micropython import const  # NOQA
import machine
import time


_SX126X_FREQUENCY_STEP_SIZE = 0.9536743164
_SX126X_MAX_PACKET_LENGTH = const(255)
_SX126X_CRYSTAL_FREQ = 32.0
_SX126X_DIV_EXPONENT = const(25)
_SX126X_CMD_NOP = const(0x00)
_SX126X_CMD_SET_SLEEP = const(0x84)
_SX126X_CMD_SET_STANDBY = const(0x80)
_SX126X_CMD_SET_FS = const(0xC1)
_SX126X_CMD_SET_TX = const(0x83)
_SX126X_CMD_SET_RX = const(0x82)
_SX126X_CMD_STOP_TIMER_ON_PREAMBLE = const(0x9F)
_SX126X_CMD_SET_RX_DUTY_CYCLE = const(0x94)
_SX126X_CMD_SET_CAD = const(0xC5)
_SX126X_CMD_SET_TX_CONTINUOUS_WAVE = const(0xD1)
_SX126X_CMD_SET_TX_INFINITE_PREAMBLE = const(0xD2)
_SX126X_CMD_SET_REGULATOR_MODE = const(0x96)
_SX126X_CMD_CALIBRATE = const(0x89)
_SX126X_CMD_CALIBRATE_IMAGE = const(0x98)
_SX126X_CMD_SET_PA_CONFIG = const(0x95)
_SX126X_CMD_SET_RX_TX_FALLBACK_MODE = const(0x93)
_SX126X_CMD_WRITE_REGISTER = const(0x0D)
_SX126X_CMD_READ_REGISTER = const(0x1D)
_SX126X_CMD_WRITE_BUFFER = const(0x0E)
_SX126X_CMD_READ_BUFFER = const(0x1E)
_SX126X_CMD_SET_DIO_IRQ_PARAMS = const(0x08)
_SX126X_CMD_GET_IRQ_STATUS = const(0x12)
_SX126X_CMD_CLEAR_IRQ_STATUS = const(0x02)
_SX126X_CMD_SET_DIO2_AS_RF_SWITCH_CTRL = const(0x9D)
_SX126X_CMD_SET_DIO3_AS_TCXO_CTRL = const(0x97)
_SX126X_CMD_SET_RF_FREQUENCY = const(0x86)
_SX126X_CMD_SET_PACKET_TYPE = const(0x8A)
_SX126X_CMD_GET_PACKET_TYPE = const(0x11)
_SX126X_CMD_SET_TX_PARAMS = const(0x8E)
_SX126X_CMD_SET_MODULATION_PARAMS = const(0x8B)
_SX126X_CMD_SET_PACKET_PARAMS = const(0x8C)
_SX126X_CMD_SET_CAD_PARAMS = const(0x88)
_SX126X_CMD_SET_BUFFER_BASE_ADDRESS = const(0x8F)
_SX126X_CMD_SET_LORA_SYMB_NUM_TIMEOUT = const(0x0A)
_SX126X_CMD_GET_STATUS = const(0xC0)
_SX126X_CMD_GET_RSSI_INST = const(0x15)
_SX126X_CMD_GET_RX_BUFFER_STATUS = const(0x13)
_SX126X_CMD_GET_PACKET_STATUS = const(0x14)
_SX126X_CMD_GET_DEVICE_ERRORS = const(0x17)
_SX126X_CMD_CLEAR_DEVICE_ERRORS = const(0x07)
_SX126X_CMD_GET_STATS = const(0x10)
_SX126X_CMD_RESET_STATS = const(0x00)
_SX126X_REG_WHITENING_INITIAL_MSB = const(0x06B8)
_SX126X_REG_WHITENING_INITIAL_LSB = const(0x06B9)
_SX126X_REG_CRC_INITIAL_MSB = const(0x06BC)
_SX126X_REG_CRC_INITIAL_LSB = const(0x06BD)
_SX126X_REG_CRC_POLYNOMIAL_MSB = const(0x06BE)
_SX126X_REG_CRC_POLYNOMIAL_LSB = const(0x06BF)
_SX126X_REG_SYNC_WORD_0 = const(0x06C0)
_SX126X_REG_SYNC_WORD_1 = const(0x06C1)
_SX126X_REG_SYNC_WORD_2 = const(0x06C2)
_SX126X_REG_SYNC_WORD_3 = const(0x06C3)
_SX126X_REG_SYNC_WORD_4 = const(0x06C4)
_SX126X_REG_SYNC_WORD_5 = const(0x06C5)
_SX126X_REG_SYNC_WORD_6 = const(0x06C6)
_SX126X_REG_SYNC_WORD_7 = const(0x06C7)
_SX126X_REG_NODE_ADDRESS = const(0x06CD)
_SX126X_REG_BROADCAST_ADDRESS = const(0x06CE)
_SX126X_REG_LORA_SYNC_WORD_MSB = const(0x0740)
_SX126X_REG_LORA_SYNC_WORD_LSB = const(0x0741)
_SX126X_REG_RANDOM_NUMBER_0 = const(0x0819)
_SX126X_REG_RANDOM_NUMBER_1 = const(0x081A)
_SX126X_REG_RANDOM_NUMBER_2 = const(0x081B)
_SX126X_REG_RANDOM_NUMBER_3 = const(0x081C)
_SX126X_REG_RX_GAIN = const(0x08AC)
_SX126X_REG_OCP_CONFIGURATION = const(0x08E7)
_SX126X_REG_XTA_TRIM = const(0x0911)
_SX126X_REG_XTB_TRIM = const(0x0912)
_SX126X_REG_SENSITIVITY_CONFIG = const(0x0889)
_SX126X_REG_TX_CLAMP_CONFIG = const(0x08D8)
_SX126X_REG_RTC_STOP = const(0x0920)
_SX126X_REG_RTC_EVENT = const(0x0944)
_SX126X_REG_IQ_CONFIG = const(0x0736)
_SX126X_REG_RX_GAIN_RETENTION_0 = const(0x029F)
_SX126X_REG_RX_GAIN_RETENTION_1 = const(0x02A0)
_SX126X_REG_RX_GAIN_RETENTION_2 = const(0x02A1)
_SX126X_SLEEP_START_COLD = const(0b00000000)
_SX126X_SLEEP_START_WARM = const(0b00000100)
_SX126X_SLEEP_RTC_OFF = const(0b00000000)
_SX126X_SLEEP_RTC_ON = const(0b00000001)
_SX126X_STANDBY_RC = const(0x00)
_SX126X_STANDBY_XOSC = const(0x01)
_SX126X_RX_TIMEOUT_NONE = const(0x000000)
_SX126X_RX_TIMEOUT_INF = const(0xFFFFFF)
_SX126X_TX_TIMEOUT_NONE = const(0x000000)
_SX126X_STOP_ON_PREAMBLE_OFF = const(0x00)
_SX126X_STOP_ON_PREAMBLE_ON = const(0x01)
_SX126X_REGULATOR_LDO = const(0x00)
_SX126X_REGULATOR_DC_DC = const(0x01)
_SX126X_CALIBRATE_IMAGE_OFF = const(0b00000000)
_SX126X_CALIBRATE_IMAGE_ON = const(0b01000000)
_SX126X_CALIBRATE_ADC_BULK_P_OFF = const(0b00000000)
_SX126X_CALIBRATE_ADC_BULK_P_ON = const(0b00100000)
_SX126X_CALIBRATE_ADC_BULK_N_OFF = const(0b00000000)
_SX126X_CALIBRATE_ADC_BULK_N_ON = const(0b00010000)
_SX126X_CALIBRATE_ADC_PULSE_OFF = const(0b00000000)
_SX126X_CALIBRATE_ADC_PULSE_ON = const(0b00001000)
_SX126X_CALIBRATE_PLL_OFF = const(0b00000000)
_SX126X_CALIBRATE_PLL_ON = const(0b00000100)
_SX126X_CALIBRATE_RC13M_OFF = const(0b00000000)
_SX126X_CALIBRATE_RC13M_ON = const(0b00000010)
_SX126X_CALIBRATE_RC64K_OFF = const(0b00000000)
_SX126X_CALIBRATE_RC64K_ON = const(0b00000001)
_SX126X_CALIBRATE_ALL = const(0b01111111)
_SX126X_CAL_IMG_430_MHZ_1 = const(0x6B)
_SX126X_CAL_IMG_430_MHZ_2 = const(0x6F)
_SX126X_CAL_IMG_470_MHZ_1 = const(0x75)
_SX126X_CAL_IMG_470_MHZ_2 = const(0x81)
_SX126X_CAL_IMG_779_MHZ_1 = const(0xC1)
_SX126X_CAL_IMG_779_MHZ_2 = const(0xC5)
_SX126X_CAL_IMG_863_MHZ_1 = const(0xD7)
_SX126X_CAL_IMG_863_MHZ_2 = const(0xDB)
_SX126X_CAL_IMG_902_MHZ_1 = const(0xE1)
_SX126X_CAL_IMG_902_MHZ_2 = const(0xE9)
_SX126X_PA_CONFIG_HP_MAX = const(0x07)
_SX126X_PA_CONFIG_PA_LUT = const(0x01)
_SX126X_PA_CONFIG_SX1262_8 = const(0x00)
_SX126X_RX_TX_FALLBACK_MODE_FS = const(0x40)
_SX126X_RX_TX_FALLBACK_MODE_STDBY_XOSC = const(0x30)
_SX126X_RX_TX_FALLBACK_MODE_STDBY_RC = const(0x20)
_SX126X_IRQ_TIMEOUT = const(0b1000000000)
_SX126X_IRQ_CAD_DETECTED = const(0b0100000000)
_SX126X_IRQ_CAD_DONE = const(0b0010000000)
_SX126X_IRQ_CRC_ERR = const(0b0001000000)
_SX126X_IRQ_HEADER_ERR = const(0b0000100000)
_SX126X_IRQ_HEADER_VALID = const(0b0000010000)
_SX126X_IRQ_SYNC_WORD_VALID = const(0b0000001000)
_SX126X_IRQ_PREAMBLE_DETECTED = const(0b0000000100)
_SX126X_IRQ_RX_DONE = const(0b0000000010)
_SX126X_IRQ_TX_DONE = const(0b0000000001)
_SX126X_IRQ_ALL = const(0b1111111111)
_SX126X_IRQ_NONE = const(0b0000000000)
_SX126X_DIO2_AS_IRQ = const(0x00)
_SX126X_DIO2_AS_RF_SWITCH = const(0x01)
_SX126X_DIO3_OUTPUT_1_6 = const(0x00)
_SX126X_DIO3_OUTPUT_1_7 = const(0x01)
_SX126X_DIO3_OUTPUT_1_8 = const(0x02)
_SX126X_DIO3_OUTPUT_2_2 = const(0x03)
_SX126X_DIO3_OUTPUT_2_4 = const(0x04)
_SX126X_DIO3_OUTPUT_2_7 = const(0x05)
_SX126X_DIO3_OUTPUT_3_0 = const(0x06)
_SX126X_DIO3_OUTPUT_3_3 = const(0x07)
_SX126X_PACKET_TYPE_GFSK = const(0x00)
_SX126X_PACKET_TYPE_LORA = const(0x01)
_SX126X_PA_RAMP_10U = const(0x00)
_SX126X_PA_RAMP_20U = const(0x01)
_SX126X_PA_RAMP_40U = const(0x02)
_SX126X_PA_RAMP_80U = const(0x03)
_SX126X_PA_RAMP_200U = const(0x04)
_SX126X_PA_RAMP_800U = const(0x05)
_SX126X_PA_RAMP_1700U = const(0x06)
_SX126X_PA_RAMP_3400U = const(0x07)
_SX126X_GFSK_FILTER_NONE = const(0x00)
_SX126X_GFSK_FILTER_GAUSS_0_3 = const(0x08)
_SX126X_GFSK_FILTER_GAUSS_0_5 = const(0x09)
_SX126X_GFSK_FILTER_GAUSS_0_7 = const(0x0A)
_SX126X_GFSK_FILTER_GAUSS_1 = const(0x0B)
_SX126X_GFSK_RX_BW_4_8 = const(0x1F)
_SX126X_GFSK_RX_BW_5_8 = const(0x17)
_SX126X_GFSK_RX_BW_7_3 = const(0x0F)
_SX126X_GFSK_RX_BW_9_7 = const(0x1E)
_SX126X_GFSK_RX_BW_11_7 = const(0x16)
_SX126X_GFSK_RX_BW_14_6 = const(0x0E)
_SX126X_GFSK_RX_BW_19_5 = const(0x1D)
_SX126X_GFSK_RX_BW_23_4 = const(0x15)
_SX126X_GFSK_RX_BW_29_3 = const(0x0D)
_SX126X_GFSK_RX_BW_39_0 = const(0x1C)
_SX126X_GFSK_RX_BW_46_9 = const(0x14)
_SX126X_GFSK_RX_BW_58_6 = const(0x0C)
_SX126X_GFSK_RX_BW_78_2 = const(0x1B)
_SX126X_GFSK_RX_BW_93_8 = const(0x13)
_SX126X_GFSK_RX_BW_117_3 = const(0x0B)
_SX126X_GFSK_RX_BW_156_2 = const(0x1A)
_SX126X_GFSK_RX_BW_187_2 = const(0x12)
_SX126X_GFSK_RX_BW_234_3 = const(0x0A)
_SX126X_GFSK_RX_BW_312_0 = const(0x19)
_SX126X_GFSK_RX_BW_373_6 = const(0x11)
_SX126X_GFSK_RX_BW_467_0 = const(0x09)
_SX126X_LORA_BW_7_8 = const(0x00)
_SX126X_LORA_BW_10_4 = const(0x08)
_SX126X_LORA_BW_15_6 = const(0x01)
_SX126X_LORA_BW_20_8 = const(0x09)
_SX126X_LORA_BW_31_25 = const(0x02)
_SX126X_LORA_BW_41_7 = const(0x0A)
_SX126X_LORA_BW_62_5 = const(0x03)
_SX126X_LORA_BW_125_0 = const(0x04)
_SX126X_LORA_BW_250_0 = const(0x05)
_SX126X_LORA_BW_500_0 = const(0x06)
_SX126X_LORA_CR_4_5 = const(0x01)
_SX126X_LORA_CR_4_6 = const(0x02)
_SX126X_LORA_CR_4_7 = const(0x03)
_SX126X_LORA_CR_4_8 = const(0x04)
_SX126X_LORA_LOW_DATA_RATE_OPTIMIZE_OFF = const(0x00)
_SX126X_LORA_LOW_DATA_RATE_OPTIMIZE_ON = const(0x01)
_SX126X_GFSK_PREAMBLE_DETECT_OFF = const(0x00)
_SX126X_GFSK_PREAMBLE_DETECT_8 = const(0x04)
_SX126X_GFSK_PREAMBLE_DETECT_16 = const(0x05)
_SX126X_GFSK_PREAMBLE_DETECT_24 = const(0x06)
_SX126X_GFSK_PREAMBLE_DETECT_32 = const(0x07)
_SX126X_GFSK_ADDRESS_FILT_OFF = const(0x00)
_SX126X_GFSK_ADDRESS_FILT_NODE = const(0x01)
_SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST = const(0x02)
_SX126X_GFSK_PACKET_FIXED = const(0x00)
_SX126X_GFSK_PACKET_VARIABLE = const(0x01)
_SX126X_GFSK_CRC_OFF = const(0x01)
_SX126X_GFSK_CRC_1_BYTE = const(0x00)
_SX126X_GFSK_CRC_2_BYTE = const(0x02)
_SX126X_GFSK_CRC_1_BYTE_INV = const(0x04)
_SX126X_GFSK_CRC_2_BYTE_INV = const(0x06)
_SX126X_GFSK_WHITENING_OFF = const(0x00)
_SX126X_GFSK_WHITENING_ON = const(0x01)
_SX126X_LORA_HEADER_EXPLICIT = const(0x00)
_SX126X_LORA_HEADER_IMPLICIT = const(0x01)
_SX126X_LORA_CRC_OFF = const(0x00)
_SX126X_LORA_CRC_ON = const(0x01)
_SX126X_LORA_IQ_STANDARD = const(0x00)
_SX126X_LORA_IQ_INVERTED = const(0x01)
_SX126X_CAD_ON_1_SYMB = const(0x00)
_SX126X_CAD_ON_2_SYMB = const(0x01)
_SX126X_CAD_ON_4_SYMB = const(0x02)
_SX126X_CAD_ON_8_SYMB = const(0x03)
_SX126X_CAD_ON_16_SYMB = const(0x04)
_SX126X_CAD_GOTO_STDBY = const(0x00)
_SX126X_CAD_GOTO_RX = const(0x01)
_SX126X_STATUS_MODE_STDBY_RC = const(0b00100000)
_SX126X_STATUS_MODE_STDBY_XOSC = const(0b00110000)
_SX126X_STATUS_MODE_FS = const(0b01000000)
_SX126X_STATUS_MODE_RX = const(0b01010000)
_SX126X_STATUS_MODE_TX = const(0b01100000)
_SX126X_STATUS_DATA_AVAILABLE = const(0b00000100)
_SX126X_STATUS_CMD_TIMEOUT = const(0b00000110)
_SX126X_STATUS_CMD_INVALID = const(0b00001000)
_SX126X_STATUS_CMD_FAILED = const(0b00001010)
_SX126X_STATUS_TX_DONE = const(0b00001100)
_SX126X_STATUS_SPI_FAILED = const(0b11111111)
_SX126X_GFSK_RX_STATUS_PREAMBLE_ERR = const(0b10000000)
_SX126X_GFSK_RX_STATUS_SYNC_ERR = const(0b01000000)
_SX126X_GFSK_RX_STATUS_ADRS_ERR = const(0b00100000)
_SX126X_GFSK_RX_STATUS_CRC_ERR = const(0b00010000)
_SX126X_GFSK_RX_STATUS_LENGTH_ERR = const(0b00001000)
_SX126X_GFSK_RX_STATUS_ABORT_ERR = const(0b00000100)
_SX126X_GFSK_RX_STATUS_PACKET_RECEIVED = const(0b00000010)
_SX126X_GFSK_RX_STATUS_PACKET_SENT = const(0b00000001)
_SX126X_PA_RAMP_ERR = const(0b100000000)
_SX126X_PLL_LOCK_ERR = const(0b001000000)
_SX126X_XOSC_START_ERR = const(0b000100000)
_SX126X_IMG_CALIB_ERR = const(0b000010000)
_SX126X_ADC_CALIB_ERR = const(0b000001000)
_SX126X_PLL_CALIB_ERR = const(0b000000100)
_SX126X_RC13M_CALIB_ERR = const(0b000000010)
_SX126X_RC64K_CALIB_ERR = const(0b000000001)
_SX126X_SYNC_WORD_PUBLIC = const(0x34)
_SX126X_SYNC_WORD_PRIVATE = const(0x12)

_ERR_NONE = const(0)
_ERR_UNKNOWN = const(-1)
_ERR_CHIP_NOT_FOUND = const(-2)
_ERR_MEMORY_ALLOCATION_FAILED = const(-3)
_ERR_PACKET_TOO_LONG = const(-4)
_ERR_TX_TIMEOUT = const(-5)
_ERR_RX_TIMEOUT = const(-6)
_ERR_CRC_MISMATCH = const(-7)
_ERR_INVALID_BANDWIDTH = const(-8)
_ERR_INVALID_SPREADING_FACTOR = const(-9)
_ERR_INVALID_CODING_RATE = const(-10)
_ERR_INVALID_BIT_RANGE = const(-11)
_ERR_INVALID_FREQUENCY = const(-12)
_ERR_INVALID_OUTPUT_POWER = const(-13)
_PREAMBLE_DETECTED = const(-14)
_CHANNEL_FREE = const(-15)
_ERR_SPI_WRITE_FAILED = const(-16)
_ERR_INVALID_CURRENT_LIMIT = const(-17)
_ERR_INVALID_PREAMBLE_LENGTH = const(-18)
_ERR_INVALID_GAIN = const(-19)
_ERR_WRONG_MODEM = const(-20)
_ERR_INVALID_NUM_SAMPLES = const(-21)
_ERR_INVALID_RSSI_OFFSET = const(-22)
_ERR_INVALID_ENCODING = const(-23)
_ERR_INVALID_BIT_RATE = const(-101)
_ERR_INVALID_FREQUENCY_DEVIATION = const(-102)
_ERR_INVALID_BIT_RATE_BW_RATIO = const(-103)
_ERR_INVALID_RX_BANDWIDTH = const(-104)
_ERR_INVALID_SYNC_WORD = const(-105)
_ERR_INVALID_DATA_SHAPING = const(-106)
_ERR_INVALID_MODULATION = const(-107)
_ERR_AT_FAILED = const(-201)
_ERR_URL_MALFORMED = const(-202)
_ERR_RESPONSE_MALFORMED_AT = const(-203)
_ERR_RESPONSE_MALFORMED = const(-204)
_ERR_MQTT_CONN_VERSION_REJECTED = const(-205)
_ERR_MQTT_CONN_ID_REJECTED = const(-206)
_ERR_MQTT_CONN_SERVER_UNAVAILABLE = const(-207)
_ERR_MQTT_CONN_BAD_USERNAME_PASSWORD = const(-208)
_ERR_MQTT_CONN_NOT_AUTHORIZED = const(-208)
_ERR_MQTT_UNEXPECTED_PACKET_ID = const(-209)
_ERR_MQTT_NO_NEW_PACKET_AVAILABLE = const(-210)
_ERR_CMD_MODE_FAILED = const(-301)
_ERR_FRAME_MALFORMED = const(-302)
_ERR_FRAME_INCORRECT_CHECKSUM = const(-303)
_ERR_FRAME_UNEXPECTED_ID = const(-304)
_ERR_FRAME_NO_RESPONSE = const(-305)
_ERR_INVALID_RTTY_SHIFT = const(-401)
_ERR_UNSUPPORTED_ENCODING = const(-402)
_ERR_INVALID_DATA_RATE = const(-501)
_ERR_INVALID_ADDRESS_WIDTH = const(-502)
_ERR_INVALID_PIPE_NUMBER = const(-503)
_ERR_ACK_NOT_RECEIVED = const(-504)
_ERR_INVALID_NUM_BROAD_ADDRS = const(-601)
_ERR_INVALID_CRC_CONFIGURATION = const(-701)
_LORA_DETECTED = const(-702)
_ERR_INVALID_TCXO_VOLTAGE = const(-703)
_ERR_INVALID_MODULATION_PARAMETERS = const(-704)
_ERR_SPI_CMD_TIMEOUT = const(-705)
_ERR_SPI_CMD_INVALID = const(-706)
_ERR_SPI_CMD_FAILED = const(-707)
_ERR_INVALID_SLEEP_PERIOD = const(-708)
_ERR_INVALID_RX_PERIOD = const(-709)
_ERR_INVALID_CALLSIGN = const(-801)
_ERR_INVALID_NUM_REPEATERS = const(-802)
_ERR_INVALID_REPEATER_CALLSIGN = const(-803)
_ERR_INVALID_PACKET_TYPE = const(-804)
_ERR_INVALID_PACKET_LENGTH = const(-805)

ERROR = {
    0: 'ERR_NONE',
    -1: 'ERR_UNKNOWN',
    -2: 'ERR_CHIP_NOT_FOUND',
    -3: 'ERR_MEMORY_ALLOCATION_FAILED',
    -4: 'ERR_PACKET_TOO_LONG',
    -5: 'ERR_TX_TIMEOUT',
    -6: 'ERR_RX_TIMEOUT',
    -7: 'ERR_CRC_MISMATCH',
    -8: 'ERR_INVALID_BANDWIDTH',
    -9: 'ERR_INVALID_SPREADING_FACTOR',
    -10: 'ERR_INVALID_CODING_RATE',
    -11: 'ERR_INVALID_BIT_RANGE',
    -12: 'ERR_INVALID_FREQUENCY',
    -13: 'ERR_INVALID_OUTPUT_POWER',
    -14: 'PREAMBLE_DETECTED',
    -15: 'CHANNEL_FREE',
    -16: 'ERR_SPI_WRITE_FAILED',
    -17: 'ERR_INVALID_CURRENT_LIMIT',
    -18: 'ERR_INVALID_PREAMBLE_LENGTH',
    -19: 'ERR_INVALID_GAIN',
    -20: 'ERR_WRONG_MODEM',
    -21: 'ERR_INVALID_NUM_SAMPLES',
    -22: 'ERR_INVALID_RSSI_OFFSET',
    -23: 'ERR_INVALID_ENCODING',
    -101: 'ERR_INVALID_BIT_RATE',
    -102: 'ERR_INVALID_FREQUENCY_DEVIATION',
    -103: 'ERR_INVALID_BIT_RATE_BW_RATIO',
    -104: 'ERR_INVALID_RX_BANDWIDTH',
    -105: 'ERR_INVALID_SYNC_WORD',
    -106: 'ERR_INVALID_DATA_SHAPING',
    -107: 'ERR_INVALID_MODULATION',
    -201: 'ERR_AT_FAILED',
    -202: 'ERR_URL_MALFORMED',
    -203: 'ERR_RESPONSE_MALFORMED_AT',
    -204: 'ERR_RESPONSE_MALFORMED',
    -205: 'ERR_MQTT_CONN_VERSION_REJECTED',
    -206: 'ERR_MQTT_CONN_ID_REJECTED',
    -207: 'ERR_MQTT_CONN_SERVER_UNAVAILABLE',
    -208: 'ERR_MQTT_CONN_BAD_USERNAME_PASSWORD',
    -208: 'ERR_MQTT_CONN_NOT_AUTHORIZED',
    -209: 'ERR_MQTT_UNEXPECTED_PACKET_ID',
    -210: 'ERR_MQTT_NO_NEW_PACKET_AVAILABLE',
    -301: 'ERR_CMD_MODE_FAILED',
    -302: 'ERR_FRAME_MALFORMED',
    -303: 'ERR_FRAME_INCORRECT_CHECKSUM',
    -304: 'ERR_FRAME_UNEXPECTED_ID',
    -305: 'ERR_FRAME_NO_RESPONSE',
    -401: 'ERR_INVALID_RTTY_SHIFT',
    -402: 'ERR_UNSUPPORTED_ENCODING',
    -501: 'ERR_INVALID_DATA_RATE',
    -502: 'ERR_INVALID_ADDRESS_WIDTH',
    -503: 'ERR_INVALID_PIPE_NUMBER',
    -504: 'ERR_ACK_NOT_RECEIVED',
    -601: 'ERR_INVALID_NUM_BROAD_ADDRS',
    -701: 'ERR_INVALID_CRC_CONFIGURATION',
    -702: 'LORA_DETECTED',
    -703: 'ERR_INVALID_TCXO_VOLTAGE',
    -704: 'ERR_INVALID_MODULATION_PARAMETERS',
    -705: 'ERR_SPI_CMD_TIMEOUT',
    -706: 'ERR_SPI_CMD_INVALID',
    -707: 'ERR_SPI_CMD_FAILED',
    -708: 'ERR_INVALID_SLEEP_PERIOD',
    -709: 'ERR_INVALID_RX_PERIOD',
    -801: 'ERR_INVALID_CALLSIGN',
    -802: 'ERR_INVALID_NUM_REPEATERS',
    -803: 'ERR_INVALID_REPEATER_CALLSIGN',
    -804: 'ERR_INVALID_PACKET_TYPE',
    -805: 'ERR_INVALID_PACKET_LENGTH'
}

#2000000

def ASSERT(state):
    assert state == _ERR_NONE, ERROR[state]
    

def yield_():
    time.sleep_ms(1)




class SX126X:

    def __init__(self, spi_device, irq, rst, gpio, cs_pin):
        self._irq = irq
        self.spi = spi_device

        self._rx_buf = bytearray(_SX126X_MAX_PACKET_LENGTH)
        self._rx_mv = memoryview(self._rx_buf)
        self._tx_buf = bytearray(_SX126X_MAX_PACKET_LENGTH)
        self._tx_mv = memoryview(self._tx_buf)

        self.cs = machine.Pin(cs_pin, mode=machine.Pin.OUT)
        self.cs.value(1)          # CS inactive
        self.irq = machine.Pin(irq, mode=machine.Pin.IN)
        self.rst = machine.Pin(rst, mode=machine.Pin.OUT)
        self.gpio = machine.Pin(gpio, mode=machine.Pin.IN)

        self._bwKhz = 0
        self._sf = 0
        self._bw = 0
        self._cr = 0
        self._ldro = 0
        self._crcType = 0
        self._preambleLength = 0
        self._tcxoDelay = 0
        self._headerType = 0
        self._implicitLen = 0
        self._txIq = 0
        self._rxIq = 0
        self._invertIQ = 0
        self._ldroAuto = True

        self._br = 0
        self._freqDev = 0
        self._rxBw = 0
        self._rxBwKhz = 0
        self._pulseShape = 0
        self._crcTypeFSK = 0
        self._preambleLengthFSK = 0
        self._addrComp = 0
        self._syncWordLength = 0
        self._whitening = 0
        self._packetType = 0
        self._dataRate = 0
        self._packetLength = 0
        self._preambleDetectorLength = 0

    def begin(
        self,
        bw,
        sf,
        cr,
        syncWord,
        currentLimit,
        preambleLength,
        tcxoVoltage,
        useRegulatorLDO=False,
        txIq=False,
        rxIq=False
    ):
        self._bwKhz = bw
        self._sf = sf

        self._bw = _SX126X_LORA_BW_125_0
        self._cr = _SX126X_LORA_CR_4_7
        self._ldro = 0x00
        self._crcType = _SX126X_LORA_CRC_ON
        self._preambleLength = preambleLength
        self._tcxoDelay = 0
        self._headerType = _SX126X_LORA_HEADER_EXPLICIT
        self._implicitLen = 0xFF

        self._txIq = txIq
        self._rxIq = rxIq
        self._invertIQ = _SX126X_LORA_IQ_STANDARD

        state = self.reset()
        ASSERT(state)

        state = self.standby()
        ASSERT(state)

        if tcxoVoltage > 0.0:
            state = self.setTCXO(tcxoVoltage)
            ASSERT(state)

        state = self.config(_SX126X_PACKET_TYPE_LORA)
        ASSERT(state)

        if useRegulatorLDO:
            state = self.setRegulatorLDO()
        else:
            state = self.setRegulatorDCDC()
        ASSERT(state)

        state = self.setSpreadingFactor(sf)
        ASSERT(state)

        state = self.setBandwidth(bw)
        ASSERT(state)

        state = self.setCodingRate(cr)
        ASSERT(state)

        state = self.setSyncWord(syncWord)
        ASSERT(state)

        state = self.setCurrentLimit(currentLimit)
        ASSERT(state)

        state = self.setPreambleLength(preambleLength)
        ASSERT(state)

        state = self.setDio2AsRfSwitch(True)
        ASSERT(state)

        return state

    def beginFSK(
        self,
        br,
        freqDev,
        rxBw,
        currentLimit,
        preambleLength,
        dataShaping,
        preambleDetectorLength,
        tcxoVoltage,
        useRegulatorLDO=False
    ):
        self._br = 21333
        self._freqDev = 52428
        self._rxBw = _SX126X_GFSK_RX_BW_156_2
        self._rxBwKhz = 156.2
        self._pulseShape = _SX126X_GFSK_FILTER_GAUSS_0_5
        self._crcTypeFSK = _SX126X_GFSK_CRC_2_BYTE_INV
        self._preambleLengthFSK = preambleLength
        self._addrComp = _SX126X_GFSK_ADDRESS_FILT_OFF
        self._preambleDetectorLength = preambleDetectorLength

        state = self.reset()
        ASSERT(state)

        state = self.standby()
        ASSERT(state)

        if tcxoVoltage > 0.0:
            state = self.setTCXO(tcxoVoltage)
            ASSERT(state)

        state = self.config(_SX126X_PACKET_TYPE_GFSK)
        ASSERT(state)

        if useRegulatorLDO:
            state = self.setRegulatorLDO()
        else:
            state = self.setRegulatorDCDC()
        ASSERT(state)

        state = self.setBitRate(br)
        ASSERT(state)

        state = self.setFrequencyDeviation(freqDev)
        ASSERT(state)

        state = self.setRxBandwidth(rxBw)
        ASSERT(state)

        state = self.setCurrentLimit(currentLimit)
        ASSERT(state)

        state = self.setDataShaping(dataShaping)
        ASSERT(state)

        state = self.setPreambleLength(preambleLength)
        ASSERT(state)

        sync = [0x2D, 0x01]
        state = self.setSyncWord(sync, 2)
        ASSERT(state)

        state = self.setWhitening(True, 0x0100)
        ASSERT(state)

        state = self.variablePacketLengthMode(_SX126X_MAX_PACKET_LENGTH)
        ASSERT(state)

        state = self.setDio2AsRfSwitch(True)
        ASSERT(state)

        return state

    def reset(self, verify=True):
        self.rst.value(1)
        time.sleep_us(150)
        self.rst.value(0)
        time.sleep_us(150)
        self.rst.value(1)
        time.sleep_us(150)

        if not verify:
            return _ERR_NONE

        start = time.ticks_ms()
        while True:
            state = self.standby()
            if state == _ERR_NONE:
                return _ERR_NONE
            if abs(time.ticks_diff(start, time.ticks_ms())) >= 3000:
                return state
            time.sleep_ms(10)

    def transmit(self, data, len_, addr=0):
        state = self.standby()
        ASSERT(state)

        if len_ > _SX126X_MAX_PACKET_LENGTH:
            return _ERR_PACKET_TOO_LONG

        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            timeout = int((self.getTimeOnAir(len_) * 3) / 2)

        elif modem == _SX126X_PACKET_TYPE_GFSK:
            timeout = int(self.getTimeOnAir(len_) * 5)

        else:
            return _ERR_UNKNOWN

        state = self.startTransmit(data, len_, addr)
        ASSERT(state)

        start = time.ticks_us()
        while not self.irq.value():
            yield_()
            if abs(time.ticks_diff(start, time.ticks_us())) > timeout:
                self.clearIrqStatus()
                self.standby()
                return _ERR_TX_TIMEOUT

        elapsed = abs(time.ticks_diff(start, time.ticks_us()))

        self._dataRate = (len_ * 8.0) / (float(elapsed) / 1000000.0)

        state = self.clearIrqStatus()
        ASSERT(state)

        state = self.standby()

        return state

    def receive(self, data, len_, timeout_en, timeout_ms):
        state = self.standby()
        ASSERT(state)

        timeout = 0

        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            symbolLength = float(1 << self._sf) / float(self._bwKhz)
            timeout = int(symbolLength * 100.0 * 1000.0)
        elif modem == _SX126X_PACKET_TYPE_GFSK:
            maxLen = len_
            if len_ == 0:
                maxLen = 0xFF
            brBps = (float(_SX126X_CRYSTAL_FREQ) * 1000000.0 * 32.0) / float(
                self._br
                )
            timeout = int(((maxLen * 8.0) / brBps) * 1000000.0 * 5.0)
        else:
            return _ERR_UNKNOWN

        if timeout_ms == 0:
            pass
        else:
            timeout = timeout_ms * 1000

        if timeout_en:
            timeoutValue = int(float(timeout) / 15.625)
        else:
            timeoutValue = _SX126X_RX_TIMEOUT_NONE

        state = self.startReceive(timeoutValue)
        ASSERT(state)

        start = time.ticks_us()
        while not self.irq.value():
            yield_()
            if timeout_en:
                if abs(time.ticks_diff(start, time.ticks_us())) > timeout:
                    self.fixImplicitTimeout()
                    self.clearIrqStatus()
                    self.standby()
                    return _ERR_RX_TIMEOUT

        if self._headerType == _SX126X_LORA_HEADER_IMPLICIT and self.getPacketType() == _SX126X_PACKET_TYPE_LORA:
            state = self.fixImplicitTimeout()
            ASSERT(state)

        return self.readData(data, len_)

    def transmitDirect(self, frf=0):
        state = _ERR_NONE
        if frf != 0:
            state = self.setRfFrequency(frf)
        ASSERT(state)

        data = [_SX126X_CMD_NOP]
        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_TX_CONTINUOUS_WAVE],
            1,
            data,
            1
        )

    def receiveDirect(self):
        return _ERR_UNKNOWN

    def scanChannel(self):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        state = self.standby()
        ASSERT(state)

        state = self.setDioIrqParams(
            _SX126X_IRQ_CAD_DETECTED | _SX126X_IRQ_CAD_DONE,
            _SX126X_IRQ_CAD_DETECTED | _SX126X_IRQ_CAD_DONE
        )
        ASSERT(state)

        state = self.clearIrqStatus()
        ASSERT(state)

        state = self.setCad()
        ASSERT(state)

        while not self.irq.value():
            yield_()

        cadResult = self.getIrqStatus()
        if cadResult & _SX126X_IRQ_CAD_DETECTED:
            self.clearIrqStatus()
            return _LORA_DETECTED
        elif cadResult & _SX126X_IRQ_CAD_DONE:
            self.clearIrqStatus()
            return _CHANNEL_FREE

        return _ERR_UNKNOWN

    def sleep(self, retainConfig=True):
        sleepMode = [_SX126X_SLEEP_START_WARM | _SX126X_SLEEP_RTC_OFF]
        if not retainConfig:
            sleepMode = [_SX126X_SLEEP_START_COLD | _SX126X_SLEEP_RTC_OFF]
        state = self.SPIwriteCommand(
            [_SX126X_CMD_SET_SLEEP],
            1,
            sleepMode,
            1,
            False
            )

        time.sleep_us(500)

        return state

    def standby(self, mode=_SX126X_STANDBY_RC):
        data = [mode]
        return self.SPIwriteCommand([_SX126X_CMD_SET_STANDBY], 1, data, 1)

    def setDio1Action(self, func):
        self.irq.irq(
            trigger=machine.Pin.IRQ_RISING,
            handler=func
        )  # Generic variant uPy

    def clearDio1Action(self):
        self.irq = machine.Pin(self._irq, mode=machine.Pin.IN)

    def startTransmit(self, data, len_, addr=0):
        if len_ > _SX126X_MAX_PACKET_LENGTH:
            return _ERR_PACKET_TOO_LONG

        if (
            self._addrComp != _SX126X_GFSK_ADDRESS_FILT_OFF and
            len_ > _SX126X_MAX_PACKET_LENGTH - 1
        ):
            return _ERR_PACKET_TOO_LONG

        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            if self._txIq:
                self._invertIQ = _SX126X_LORA_IQ_INVERTED
            else:
                self._invertIQ = _SX126X_LORA_IQ_STANDARD

            if self._headerType == _SX126X_LORA_HEADER_IMPLICIT:
                if len_ != self._implicitLen:
                    return _ERR_INVALID_PACKET_LENGTH

            state = self.setPacketParams(
                self._preambleLength,
                self._crcType,
                len_,
                self._headerType,
                self._invertIQ
            )
        elif modem == _SX126X_PACKET_TYPE_GFSK:
            if self._packetType == _SX126X_GFSK_PACKET_FIXED:
                if len_ != self._packetLength:
                    return _ERR_INVALID_PACKET_LENGTH

            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                len_,
                self._preambleDetectorLength
            )
        else:
            return _ERR_UNKNOWN
        ASSERT(state)

        state = self.setDioIrqParams(
            _SX126X_IRQ_TX_DONE | _SX126X_IRQ_TIMEOUT,
            _SX126X_IRQ_TX_DONE
        )
        ASSERT(state)

        state = self.setBufferBaseAddress()
        ASSERT(state)

        state = self.writeBuffer(data, len_)
        ASSERT(state)

        state = self.clearIrqStatus()
        ASSERT(state)

        state = self.fixSensitivity()
        ASSERT(state)

        state = self.setTx(_SX126X_TX_TIMEOUT_NONE)
        ASSERT(state)

        while self.gpio.value():
            yield_()

        return state

    def startReceive(self, timeout=_SX126X_RX_TIMEOUT_INF):
        state = _ERR_NONE
        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            if self._rxIq:
                self._invertIQ = _SX126X_LORA_IQ_INVERTED
            else:
                self._invertIQ = _SX126X_LORA_IQ_STANDARD

            state = self.setPacketParams(
                self._preambleLength,
                self._crcType,
                self._implicitLen,
                self._headerType,
                self._invertIQ
            )
        elif modem == _SX126X_PACKET_TYPE_GFSK:
            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )
        else:
            return _ERR_UNKNOWN
        ASSERT(state)

        state = self.startReceiveCommon()
        ASSERT(state)

        state = self.setRx(timeout)

        return state

    def startReceiveDutyCycle(self, rxPeriod, sleepPeriod):
        transitionTime = int(self._tcxoDelay + 1000)
        sleepPeriod -= transitionTime

        rxPeriodRaw = int((rxPeriod * 8) / 125)
        sleepPeriodRaw = int((sleepPeriod * 8) / 125)

        if rxPeriodRaw & 0xFF000000 or rxPeriodRaw == 0:
            return _ERR_INVALID_RX_PERIOD

        if sleepPeriodRaw & 0xFF000000 or sleepPeriodRaw == 0:
            return _ERR_INVALID_SLEEP_PERIOD

        state = self.startReceiveCommon()
        ASSERT(state)

        data = [
            int((rxPeriodRaw >> 16) & 0xFF),
            int((rxPeriodRaw >> 8) & 0xFF),
            int(rxPeriodRaw & 0xFF),
            int((sleepPeriodRaw >> 16) & 0xFF),
            int((sleepPeriodRaw >> 8) & 0xFF),
            int(sleepPeriodRaw & 0xFF)
        ]
        return self.SPIwriteCommand([_SX126X_CMD_SET_RX_DUTY_CYCLE], 1, data, 6)

    def startReceiveDutyCycleAuto(self, senderPreambleLength=0, minSymbols=8):
        if senderPreambleLength == 0:
            senderPreambleLength = self._preambleLength

        sleepSymbols = int(senderPreambleLength - 2 * minSymbols)

        if 2 * minSymbols > senderPreambleLength:
            return self.startReceive()

        symbolLength = int(((10 * 1000) << self._sf) / (10 * self._bwKhz))
        sleepPeriod = symbolLength * sleepSymbols

        wakePeriod = int(max(
            (symbolLength * (senderPreambleLength + 1) - (sleepPeriod - 1000)) / 2,
            symbolLength * (minSymbols + 1)
        ))

        if sleepPeriod < (self._tcxoDelay + 1016):
            return self.startReceive()

        return self.startReceiveDutyCycle(wakePeriod, sleepPeriod)

    def startReceiveCommon(self):
        state = self.setDioIrqParams(
            _SX126X_IRQ_RX_DONE | _SX126X_IRQ_TIMEOUT | _SX126X_IRQ_CRC_ERR | _SX126X_IRQ_HEADER_ERR,
            _SX126X_IRQ_RX_DONE
        )

        ASSERT(state)

        state = self.setBufferBaseAddress()
        ASSERT(state)

        state = self.clearIrqStatus()

        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            state = self.setPacketParams(
                self._preambleLength,
                self._crcType,
                self._implicitLen,
                self._headerType,
                self._invertIQ
            )
        elif modem == _SX126X_PACKET_TYPE_GFSK:
            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType
            )
        else:
            return _ERR_UNKNOWN

        return state

    def readData(self, data, len_):
        state = self.standby()
        ASSERT(state)

        irq = self.getIrqStatus()
        crcState = _ERR_NONE
        if irq & _SX126X_IRQ_CRC_ERR or irq & _SX126X_IRQ_HEADER_ERR:
            crcState = _ERR_CRC_MISMATCH

        length = len_
        if len_ == _SX126X_MAX_PACKET_LENGTH:
            length = self.getPacketLength()

        state = self.readBuffer(data, length)
        ASSERT(state)

        state = self.clearIrqStatus()

        ASSERT(crcState)

        return state

    def setBandwidth(self, bw):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        if not 0 < bw < 510:
            return _ERR_INVALID_BANDWIDTH

        bw_div2 = int(bw / 2 + 0.01)
        switch = {
            3: _SX126X_LORA_BW_7_8,
            5: _SX126X_LORA_BW_10_4,
            7: _SX126X_LORA_BW_15_6,
            10: _SX126X_LORA_BW_20_8,
            15: _SX126X_LORA_BW_31_25,
            20: _SX126X_LORA_BW_41_7,
            31: _SX126X_LORA_BW_62_5,
            62: _SX126X_LORA_BW_125_0,
            125: _SX126X_LORA_BW_250_0,
            250: _SX126X_LORA_BW_500_0
        }
        try:
            self._bw = switch[bw_div2]
        except:
            return _ERR_INVALID_BANDWIDTH

        self._bwKhz = bw
        return self.setModulationParams(
            self._sf,
            self._bw,
            self._cr,
            self._ldro
        )

    def setSpreadingFactor(self, sf):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        if not ((sf >= 5) and (sf <= 12)):
            return _ERR_INVALID_SPREADING_FACTOR

        self._sf = sf
        return self.setModulationParams(
            self._sf,
            self._bw,
            self._cr,
            self._ldro
        )

    def setCodingRate(self, cr):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        if not ((cr >= 5) and (cr <= 8)):
            return _ERR_INVALID_CODING_RATE

        self._cr = cr - 4
        return self.setModulationParams(
            self._sf,
            self._bw,
            self._cr,
            self._ldro
        )

    def setSyncWord(self, syncWord, *args):
        if self.getPacketType() == _SX126X_PACKET_TYPE_LORA:
            if len(args) > 0:
                controlBits = args[0]
            else:
                controlBits = 0x44
            data = [
                int((syncWord & 0xF0) | ((controlBits & 0xF0) >> 4)),
                int(((syncWord & 0x0F) << 4) | (controlBits & 0x0F))
            ]

            return self.writeRegister(_SX126X_REG_LORA_SYNC_WORD_MSB, data, 2)

        elif self.getPacketType() == _SX126X_PACKET_TYPE_GFSK:
            len_ = args[0]
            if len_ > 8:
                return _ERR_INVALID_SYNC_WORD

            state = self.writeRegister(_SX126X_REG_SYNC_WORD_0, syncWord, len_)
            ASSERT(state)

            self._syncWordLength = len_ * 8
            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )

            return state

        else:
            return _ERR_WRONG_MODEM

    def setCurrentLimit(self, currentLimit):
        if not ((currentLimit >= 0) and (currentLimit <= 140)):
            return _ERR_INVALID_CURRENT_LIMIT

        rawLimit = [int(currentLimit / 2.5)]

        return self.writeRegister(_SX126X_REG_OCP_CONFIGURATION, rawLimit, 1)

    def getCurrentLimit(self):
        ocp = bytearray(1)
        ocp_mv = memoryview(ocp)
        self.readRegister(_SX126X_REG_OCP_CONFIGURATION, ocp_mv, 1)

        return float(ocp[0]) * 2.5

    def setPreambleLength(self, preambleLength):
        modem = self.getPacketType()
        if modem == _SX126X_PACKET_TYPE_LORA:
            self._preambleLength = preambleLength
            return self.setPacketParams(
                self._preambleLength,
                self._crcType,
                self._implicitLen,
                self._headerType,
                self._invertIQ
            )
        elif modem == _SX126X_PACKET_TYPE_GFSK:
            self._preambleLengthFSK = preambleLength
            return self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )

        return _ERR_UNKNOWN

    def setFrequencyDeviation(self, freqDev):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        if not (freqDev <= 200.0):
            return _ERR_INVALID_FREQUENCY_DEVIATION

        freqDevRaw = int(
            ((freqDev * 1000.0) * float(1 << 25)) / (_SX126X_CRYSTAL_FREQ * 1000000.0)
        )

        self._freqDev = freqDevRaw
        return self.setModulationParamsFSK(
            self._br,
            self._pulseShape,
            self._rxBw,
            self._freqDev
        )

    def setBitRate(self, br):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        if not 0.6 <= br <= 300.0:
            return _ERR_INVALID_BIT_RATE

        brRaw = int((_SX126X_CRYSTAL_FREQ * 1000000.0 * 32.0) / (br * 1000.0))

        self._br = brRaw

        return self.setModulationParamsFSK(
            self._br,
            self._pulseShape,
            self._rxBw,
            self._freqDev
        )

    def setRxBandwidth(self, rxBw):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        self._rxBwKhz = rxBw

        if abs(rxBw - 4.8) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_4_8
        elif abs(rxBw - 5.8) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_5_8
        elif abs(rxBw - 7.3) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_7_3
        elif abs(rxBw - 9.7) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_9_7
        elif abs(rxBw - 11.7) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_11_7
        elif abs(rxBw - 14.6) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_14_6
        elif abs(rxBw - 19.5) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_19_5
        elif abs(rxBw - 23.4) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_23_4
        elif abs(rxBw - 29.3) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_29_3
        elif abs(rxBw - 39.0) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_39_0
        elif abs(rxBw - 46.9) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_46_9
        elif abs(rxBw - 58.6) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_58_6
        elif abs(rxBw - 78.2) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_78_2
        elif abs(rxBw - 93.8) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_93_8
        elif abs(rxBw - 117.3) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_117_3
        elif abs(rxBw - 156.2) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_156_2
        elif abs(rxBw - 187.2) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_187_2
        elif abs(rxBw - 234.3) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_234_3
        elif abs(rxBw - 312.0) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_312_0
        elif abs(rxBw - 373.6) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_373_6
        elif abs(rxBw - 467.0) <= 0.001:
            self._rxBw = _SX126X_GFSK_RX_BW_467_0
        else:
            return _ERR_INVALID_RX_BANDWIDTH

        return self.setModulationParamsFSK(
            self._br,
            self._pulseShape,
            self._rxBw,
            self._freqDev
        )

    def setDataShaping(self, sh):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        sh *= 10.0
        if abs(sh - 0.0) <= 0.001:
            self._pulseShape = _SX126X_GFSK_FILTER_NONE
        elif abs(sh - 3.0) <= 0.001:
            self._pulseShape = _SX126X_GFSK_FILTER_GAUSS_0_3
        elif abs(sh - 5.0) <= 0.001:
            self._pulseShape = _SX126X_GFSK_FILTER_GAUSS_0_5
        elif abs(sh - 7.0) <= 0.001:
            self._pulseShape = _SX126X_GFSK_FILTER_GAUSS_0_7
        elif abs(sh - 10.0) <= 0.001:
            self._pulseShape = _SX126X_GFSK_FILTER_GAUSS_1
        else:
            return _ERR_INVALID_DATA_SHAPING

        return self.setModulationParamsFSK(
            self._br,
            self._pulseShape,
            self._rxBw,
            self._freqDev
        )

    def setSyncBits(self, syncWord, bitsLen):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        if bitsLen > 0x40:
            return _ERR_INVALID_SYNC_WORD

        bytesLen = int(bitsLen / 8)
        if (bitsLen % 8) != 0:
            bytesLen += 1

        state = self.writeRegister(_SX126X_REG_SYNC_WORD_0, syncWord, bytesLen)
        ASSERT(state)

        self._syncWordLength = bitsLen
        state = self.setPacketParamsFSK(
            self._preambleLengthFSK,
            self._crcTypeFSK,
            self._syncWordLength,
            self._addrComp,
            self._whitening,
            self._packetType,
            self._packetLength,
            self._preambleDetectorLength
        )

        return state

    def setNodeAddress(self, nodeAddr):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        self._addrComp = _SX126X_GFSK_ADDRESS_FILT_NODE

        state = self.setPacketParamsFSK(
            self._preambleLengthFSK,
            self._crcTypeFSK,
            self._syncWordLength,
            self._addrComp,
            self._whitening,
            self._packetType,
            self._packetLength,
            self._preambleDetectorLength
        )
        ASSERT(state)

        state = self.writeRegister(_SX126X_REG_NODE_ADDRESS, [nodeAddr], 1)

        return state

    def setBroadcastAddress(self, broadAddr):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        self._addrComp = _SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST
        state = self.setPacketParamsFSK(
            self._preambleLengthFSK,
            self._crcTypeFSK,
            self._syncWordLength,
            self._addrComp,
            self._whitening,
            self._packetType,
            self._packetLength,
            self._preambleDetectorLength
        )
        ASSERT(state)

        state = self.writeRegister(_SX126X_REG_BROADCAST_ADDRESS, [broadAddr], 1)

        return state

    def disableAddressFiltering(self):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        self._addrComp = _SX126X_GFSK_ADDRESS_FILT_OFF
        return self.setPacketParamsFSK(
            self._preambleLengthFSK,
            self._crcTypeFSK,
            self._syncWordLength,
            self._addrComp,
            self._whitening,
            self._packetType,
            self._packetLength,
            self._preambleDetectorLength
        )

    def setCRC(self, len_, initial=0x1D0F, polynomial=0x1021, inverted=True):
        modem = self.getPacketType()

        if modem == _SX126X_PACKET_TYPE_GFSK:
            if len_ == 0:
                self._crcTypeFSK = _SX126X_GFSK_CRC_OFF
            elif len_ == 1:
                if inverted:
                    self._crcTypeFSK = _SX126X_GFSK_CRC_1_BYTE_INV
                else:
                    self._crcTypeFSK = _SX126X_GFSK_CRC_1_BYTE
            elif len_ == 2:
                if inverted:
                    self._crcTypeFSK = _SX126X_GFSK_CRC_2_BYTE_INV
                else:
                    self._crcTypeFSK = _SX126X_GFSK_CRC_2_BYTE
            else:
                return _ERR_INVALID_CRC_CONFIGURATION

            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )
            ASSERT(state)

            data = [int((initial >> 8) & 0xFF), int(initial & 0xFF)]
            state = self.writeRegister(_SX126X_REG_CRC_INITIAL_MSB, data, 2)
            ASSERT(state)

            data[0] = int((polynomial >> 8) & 0xFF)
            data[1] = int(polynomial & 0xFF)
            state = self.writeRegister(_SX126X_REG_CRC_POLYNOMIAL_MSB, data, 2)

            return state

        elif modem == _SX126X_PACKET_TYPE_LORA:

            if len_:
                self._crcType = _SX126X_LORA_CRC_ON
            else:
                self._crcType = _SX126X_LORA_CRC_OFF

            return self.setPacketParams(
                self._preambleLength,
                self._crcType,
                self._implicitLen,
                self._headerType,
                self._invertIQ
            )

        return _ERR_UNKNOWN

    def setWhitening(self, enabled, initial=0x0100):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        if enabled is not True:
            self._whitening = _SX126X_GFSK_WHITENING_OFF

            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )
            ASSERT(state)
        else:
            self._whitening = _SX126X_GFSK_WHITENING_ON

            data = bytearray(1)
            data_mv = memoryview(data)
            state = self.readRegister(
                _SX126X_REG_WHITENING_INITIAL_MSB,
                data_mv,
                1
            )
            ASSERT(state)
            data2 = [
                (data[0] & 0xFE) | int((initial >> 8) & 0x01),
                int(initial & 0xFF)
            ]
            state = self.writeRegister(
                _SX126X_REG_WHITENING_INITIAL_MSB,
                data2,
                2
            )
            ASSERT(state)

            state = self.setPacketParamsFSK(
                self._preambleLengthFSK,
                self._crcTypeFSK,
                self._syncWordLength,
                self._addrComp,
                self._whitening,
                self._packetType,
                self._packetLength,
                self._preambleDetectorLength
            )
            ASSERT(state)
        return state

    def getDataRate(self):
        return self._dataRate

    def getRSSI(self):
        packetStatus = self.getPacketStatus()
        rssiPkt = int(packetStatus & 0xFF)
        return -1.0 * rssiPkt / 2.0

    def getSNR(self):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        packetStatus = self.getPacketStatus()
        snrPkt = int((packetStatus >> 8) & 0xFF)
        if snrPkt < 128:
            return snrPkt / 4.0
        else:
            return (snrPkt - 256) / 4.0

    def getPacketLength(self, update=True):
        rxBufStatus = bytearray(2)
        rxBufStatus_mv = memoryview(rxBufStatus)
        self.SPIreadCommand(
            [_SX126X_CMD_GET_RX_BUFFER_STATUS],
            1,
            rxBufStatus_mv,
            2
        )
        return rxBufStatus[0]

    def fixedPacketLengthMode(self, len_=_SX126X_MAX_PACKET_LENGTH):
        return self.setPacketMode(_SX126X_GFSK_PACKET_FIXED, len_)

    def variablePacketLengthMode(self, maxLen=_SX126X_MAX_PACKET_LENGTH):
        return self.setPacketMode(_SX126X_GFSK_PACKET_VARIABLE, maxLen)

    def getTimeOnAir(self, len_):
        if self.getPacketType() == _SX126X_PACKET_TYPE_LORA:
            symbolLength_us = int(
                ((1000 * 10) << self._sf) / (self._bwKhz * 10)
            )
            sfCoeff1_x4 = 17

            sfCoeff2 = 8
            if self._sf == 5 or self._sf == 6:
                sfCoeff1_x4 = 25
                sfCoeff2 = 0

            sfDivisor = 4 * self._sf
            if symbolLength_us >= 16000:
                sfDivisor = 4 * (self._sf - 2)

            bitsPerCrc = 16
            N_symbol_header = 20 if self._headerType == _SX126X_LORA_HEADER_EXPLICIT else 0

            bitCount = int(
                8 * len_ + self._crcType * bitsPerCrc - 4 * self._sf + sfCoeff2 + N_symbol_header
            )
            if bitCount < 0:
                bitCount = 0

            nPreCodedSymbols = int((bitCount + (sfDivisor - 1)) / sfDivisor)

            nSymbol_x4 = int((self._preambleLength + 8) * 4 + sfCoeff1_x4 + nPreCodedSymbols * (self._cr + 4) * 4)

            return int((symbolLength_us * nSymbol_x4) / 4)
        else:
            return int((len_ * 8 * self._br) / (_SX126X_CRYSTAL_FREQ * 32))

    def implicitHeader(self, len_):
        return self.setHeaderType(_SX126X_LORA_HEADER_IMPLICIT, len_)

    def explicitHeader(self):
        return self.setHeaderType(_SX126X_LORA_HEADER_EXPLICIT)

    def setRegulatorLDO(self):
        return self.setRegulatorMode(_SX126X_REGULATOR_LDO)

    def setRegulatorDCDC(self):
        return self.setRegulatorMode(_SX126X_REGULATOR_DC_DC)

    def setEncoding(self, encoding):
        return self.setWhitening(encoding)

    def forceLDRO(self, enable):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        self._ldroAuto = False
        self._ldro = enable
        return self.setModulationParams(
            self._sf,
            self._bw,
            self._cr,
            self._ldro
        )

    def autoLDRO(self):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        self._ldroAuto = True
        return self.setModulationParams(
            self._sf,
            self._bw,
            self._cr,
            self._ldro
        )

    def setTCXO(self, voltage, delay=5000):
        self.standby()

        if self.getDeviceErrors() & _SX126X_XOSC_START_ERR:
            self.clearDeviceErrors()

        if abs(voltage - 0.0) <= 0.001:
            return self.reset()

        data = [0, 0, 0, 0]
        if abs(voltage - 1.6) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_1_6
        elif abs(voltage - 1.7) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_1_7
        elif abs(voltage - 1.8) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_1_8
        elif abs(voltage - 2.2) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_2_2
        elif abs(voltage - 2.4) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_2_4
        elif abs(voltage - 2.7) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_2_7
        elif abs(voltage - 3.0) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_3_0
        elif abs(voltage - 3.3) <= 0.001:
            data[0] = _SX126X_DIO3_OUTPUT_3_3
        else:
            return _ERR_INVALID_TCXO_VOLTAGE

        delayValue = int(float(delay) / 15.625)
        data[1] = int((delayValue >> 16) & 0xFF)
        data[2] = int((delayValue >> 8) & 0xFF)
        data[3] = int(delayValue & 0xFF)

        self._tcxoDelay = delay

        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_DIO3_AS_TCXO_CTRL],
            1,
            data,
            4
        )

    def setDio2AsRfSwitch(self, enable=True):
        data = [0]
        if enable:
            data = [_SX126X_DIO2_AS_RF_SWITCH]
        else:
            data = [_SX126X_DIO2_AS_IRQ]
        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_DIO2_AS_RF_SWITCH_CTRL],
            1,
            data,
            1
        )

    def setTx(self, timeout=0):
        data = [
            int((timeout >> 16) & 0xFF),
            int((timeout >> 8) & 0xFF),
            int(timeout & 0xFF)
        ]

        return self.SPIwriteCommand([_SX126X_CMD_SET_TX], 1, data, 3)

    def setRx(self, timeout):
        data = [
            int((timeout >> 16) & 0xFF),
            int((timeout >> 8) & 0xFF),
            int(timeout & 0xFF)
        ]

        return self.SPIwriteCommand([_SX126X_CMD_SET_RX], 1, data, 3)

    def setCad(self):
        return self.SPIwriteCommand([_SX126X_CMD_SET_CAD], 1, [], 0)

    def setPaConfig(
        self,
        paDutyCycle,
        deviceSel,
        hpMax=_SX126X_PA_CONFIG_HP_MAX,
        paLut=_SX126X_PA_CONFIG_PA_LUT
    ):
        data = [paDutyCycle, hpMax, deviceSel, paLut]
        return self.SPIwriteCommand([_SX126X_CMD_SET_PA_CONFIG], 1, data, 4)

    def writeRegister(self, addr, data, numBytes):
        cmd = [
            _SX126X_CMD_WRITE_REGISTER, int((addr >> 8) & 0xFF),
            int(addr & 0xFF)
        ]
        state = self.SPIwriteCommand(cmd, 3, data, numBytes)
        return state

    def readRegister(self, addr, data, numBytes):
        cmd = [
            _SX126X_CMD_READ_REGISTER, int((addr >> 8) & 0xFF),
            int(addr & 0xFF)
        ]
        return self.SPItransfer(cmd, 3, False, [], data, numBytes, True)

    def writeBuffer(self, data, numBytes, offset=0x00):
        cmd = [_SX126X_CMD_WRITE_BUFFER, offset]
        state = self.SPIwriteCommand(cmd, 2, data, numBytes)

        return state

    def readBuffer(self, data, numBytes):
        cmd = [_SX126X_CMD_READ_BUFFER, _SX126X_CMD_NOP]
        state = self.SPIreadCommand(cmd, 2, data, numBytes)

        return state

    def setDioIrqParams(
        self,
        irqMask,
        dio1Mask,
        dio2Mask=_SX126X_IRQ_NONE,
        dio3Mask=_SX126X_IRQ_NONE
    ):
        data = [
            (irqMask >> 8) & 0xFF,
            irqMask & 0xFF,
            (dio1Mask >> 8) & 0xFF,
            dio1Mask & 0xFF,
            (dio2Mask >> 8) & 0xFF,
            dio2Mask & 0xFF,
            (dio3Mask >> 8) & 0xFF,
            dio3Mask & 0xFF
        ]
        return self.SPIwriteCommand([_SX126X_CMD_SET_DIO_IRQ_PARAMS], 1, data, 8)

    def getIrqStatus(self):
        data = bytearray(2)
        data_mv = memoryview(data)
        self.SPIreadCommand([_SX126X_CMD_GET_IRQ_STATUS], 1, data_mv, 2)
        return (data[0] << 8) | data[1]

    def clearIrqStatus(self, clearIrqParams=_SX126X_IRQ_ALL):
        data = [
            (clearIrqParams >> 8) & 0xFF,
            clearIrqParams & 0xFF
        ]
        return self.SPIwriteCommand([_SX126X_CMD_CLEAR_IRQ_STATUS], 1, data, 2)

    def setRfFrequency(self, frf):
        data = [
            (frf >> 24) & 0xFF,
            (frf >> 16) & 0xFF,
            (frf >> 8) & 0xFF,
            frf & 0xFF
        ]
        return self.SPIwriteCommand([_SX126X_CMD_SET_RF_FREQUENCY], 1, data, 4)

    def calibrateImage(self, data):
        return self.SPIwriteCommand([_SX126X_CMD_CALIBRATE_IMAGE], 1, data, 2)

    def getPacketType(self):
        data = bytearray([0xFF])
        data_mv = memoryview(data)
        self.SPIreadCommand([_SX126X_CMD_GET_PACKET_TYPE], 1, data_mv, 1)
        return data[0]

    def setTxParams(self, power, rampTime=_SX126X_PA_RAMP_200U):
        if power < 0:
            power += 256
        data = [power, rampTime]
        return self.SPIwriteCommand([_SX126X_CMD_SET_TX_PARAMS], 1, data, 2)

    def setPacketMode(self, mode, len_):
        if self.getPacketType() != _SX126X_PACKET_TYPE_GFSK:
            return _ERR_WRONG_MODEM

        state = self.setPacketParamsFSK(
            self._preambleLengthFSK,
            self._crcTypeFSK,
            self._syncWordLength,
            self._addrComp,
            self._whitening,
            mode,
            len_,
            self._preambleDetectorLength
        )
        ASSERT(state)

        self._packetType = mode
        self._packetLength = len_
        return state

    def setHeaderType(self, headerType, len_=0xFF):
        if self.getPacketType() != _SX126X_PACKET_TYPE_LORA:
            return _ERR_WRONG_MODEM

        state = self.setPacketParams(
            self._preambleLength,
            self._crcType,
            len_,
            headerType,
            self._invertIQ
        )
        ASSERT(state)

        self._headerType = headerType
        self._implicitLen = len_

        return state

    def setModulationParams(self, sf, bw, cr, ldro):
        if self._ldroAuto:
            symbolLength = float((1 << self._sf)) / float(self._bwKhz)
            if symbolLength >= 16.0:
                self._ldro = _SX126X_LORA_LOW_DATA_RATE_OPTIMIZE_ON
            else:
                self._ldro = _SX126X_LORA_LOW_DATA_RATE_OPTIMIZE_OFF
        else:
            self._ldro = ldro

        data = [sf, bw, cr, self._ldro]
        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_MODULATION_PARAMS],
            1,
            data,
            4
        )

    def setModulationParamsFSK(self, br, pulseShape, rxBw, freqDev):
        data = [
            (br >> 16) & 0xFF,
            (br >> 8) & 0xFF,
            br & 0xFF,
            pulseShape,
            rxBw,
            (freqDev >> 16) & 0xFF,
            (freqDev >> 8) & 0xFF,
            freqDev & 0xFF
        ]

        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_MODULATION_PARAMS],
            1,
            data,
            8
        )

    def setPacketParams(
        self,
        preambleLength,
        crcType,
        payloadLength,
        headerType,
        invertIQ=_SX126X_LORA_IQ_STANDARD
    ):
        state = self.fixInvertedIQ(invertIQ)
        ASSERT(state)
        data = [
            (preambleLength >> 8) & 0xFF,
            preambleLength & 0xFF,
            headerType,
            payloadLength,
            crcType,
            invertIQ
        ]

        return self.SPIwriteCommand([_SX126X_CMD_SET_PACKET_PARAMS], 1, data, 6)

    def setPacketParamsFSK(
        self,
        preambleLength,
        crcType,
        syncWordLength,
        addrComp,
        whitening,
        packetType=_SX126X_GFSK_PACKET_VARIABLE,
        payloadLength=0xFF,
        preambleDetectorLength=_SX126X_GFSK_PREAMBLE_DETECT_16
    ):
        data = [
            (preambleLength >> 8) & 0xFF,
            preambleLength & 0xFF,
            preambleDetectorLength,
            syncWordLength,
            addrComp,
            packetType,
            payloadLength,
            crcType,
            whitening
        ]
        return self.SPIwriteCommand([_SX126X_CMD_SET_PACKET_PARAMS], 1, data, 9)

    def setBufferBaseAddress(self, txBaseAddress=0x00, rxBaseAddress=0x00):
        data = [txBaseAddress, rxBaseAddress]
        return self.SPIwriteCommand(
            [_SX126X_CMD_SET_BUFFER_BASE_ADDRESS],
            1,
            data,
            2
        )

    def setRegulatorMode(self, mode):
        data = [mode]
        return self.SPIwriteCommand([_SX126X_CMD_SET_REGULATOR_MODE], 1, data, 1)

    def getStatus(self):
        data = bytearray(1)
        data_mv = memoryview(data)
        self.SPIreadCommand([_SX126X_CMD_GET_STATUS], 1, data_mv, 1)
        return data[0]

    def getPacketStatus(self):
        data = bytearray(3)
        data_mv = memoryview(data)
        self.SPIreadCommand([_SX126X_CMD_GET_PACKET_STATUS], 1, data_mv, 3)
        return (data[0] << 16) | (data[1] << 8) | data[2]

    def getDeviceErrors(self):
        data = bytearray(2)
        data_mv = memoryview(data)
        self.SPIreadCommand([_SX126X_CMD_GET_DEVICE_ERRORS], 1, data_mv, 2)
        opError = ((data[0] & 0xFF) << 8) & data[1]
        return opError

    def clearDeviceErrors(self):
        data = [_SX126X_CMD_NOP, _SX126X_CMD_NOP]
        return self.SPIwriteCommand(
            [_SX126X_CMD_CLEAR_DEVICE_ERRORS],
            1,
            data,
            2
        )

    def setFrequencyRaw(self, freq):
        frf = int((freq * (1 << _SX126X_DIV_EXPONENT)) / _SX126X_CRYSTAL_FREQ)
        return self.setRfFrequency(frf)

    def fixSensitivity(self):
        sensitivityConfig = bytearray(1)
        sensitivityConfig_mv = memoryview(sensitivityConfig)
        state = self.readRegister(
            _SX126X_REG_SENSITIVITY_CONFIG,
            sensitivityConfig_mv,
            1
        )
        ASSERT(state)

        if self.getPacketType() == _SX126X_PACKET_TYPE_LORA and abs(self._bwKhz - 500.0) <= 0.001:
            sensitivityConfig_mv[0] &= 0xFB
        else:
            sensitivityConfig_mv[0] |= 0x04
        return self.writeRegister(
            _SX126X_REG_SENSITIVITY_CONFIG,
            sensitivityConfig,
            1
        )

    def fixPaClamping(self):
        clampConfig = bytearray(1)
        clampConfig_mv = memoryview(clampConfig)
        state = self.readRegister(_SX126X_REG_TX_CLAMP_CONFIG, clampConfig_mv, 1)
        ASSERT(state)

        clampConfig_mv[0] |= 0x1E
        return self.writeRegister(_SX126X_REG_TX_CLAMP_CONFIG, clampConfig, 1)

    def fixImplicitTimeout(self):
        if not (
            self._headerType == _SX126X_LORA_HEADER_IMPLICIT and
            self.getPacketType() == _SX126X_PACKET_TYPE_LORA
        ):
            return _ERR_WRONG_MODEM

        rtcStop = [0x00]
        state = self.writeRegister(_SX126X_REG_RTC_STOP, rtcStop, 1)
        ASSERT(state)

        rtcEvent = bytearray(1)
        rtcEvent_mv = memoryview(rtcEvent)
        state = self.readRegister(_SX126X_REG_RTC_EVENT, rtcEvent_mv, 1)
        ASSERT(state)

        rtcEvent_mv[0] |= 0x02
        return self.writeRegister(_SX126X_REG_RTC_EVENT, rtcEvent, 1)

    def fixInvertedIQ(self, iqConfig):
        iqConfigCurrent = bytearray(1)
        iqConfigCurrent_mv = memoryview(iqConfigCurrent)
        state = self.readRegister(_SX126X_REG_IQ_CONFIG, iqConfigCurrent_mv, 1)
        ASSERT(state)

        if iqConfig == _SX126X_LORA_IQ_STANDARD:
            iqConfigCurrent_mv[0] &= 0xFB
        else:
            iqConfigCurrent_mv[0] |= 0x04

        return self.writeRegister(_SX126X_REG_IQ_CONFIG, iqConfigCurrent, 1)

    def config(self, modem):
        state = self.setBufferBaseAddress()
        ASSERT(state)

        data = [0, 0, 0, 0, 0, 0, 0]
        data[0] = modem
        state = self.SPIwriteCommand([_SX126X_CMD_SET_PACKET_TYPE], 1, data, 1)
        ASSERT(state)

        data[0] = _SX126X_RX_TX_FALLBACK_MODE_STDBY_RC
        state = self.SPIwriteCommand(
            [_SX126X_CMD_SET_RX_TX_FALLBACK_MODE],
            1,
            data,
            1
        )
        ASSERT(state)

        data[0] = _SX126X_CAD_ON_8_SYMB
        data[1] = self._sf + 13
        data[2] = 10
        data[3] = _SX126X_CAD_GOTO_STDBY
        data[4] = 0x00
        data[5] = 0x00
        data[6] = 0x00
        state = self.SPIwriteCommand([_SX126X_CMD_SET_CAD_PARAMS], 1, data, 7)
        ASSERT(state)

        state = self.clearIrqStatus()
        state |= self.setDioIrqParams(_SX126X_IRQ_NONE, _SX126X_IRQ_NONE)
        ASSERT(state)

        data[0] = _SX126X_CALIBRATE_ALL
        state = self.SPIwriteCommand([_SX126X_CMD_CALIBRATE], 1, data, 1)
        ASSERT(state)

        time.sleep_ms(5)

        while self.gpio.value():
            yield_()

        return _ERR_NONE

    def SPIwriteCommand(self, cmd, cmdLen, data, numBytes, waitForBusy=True):
        return self.SPItransfer(cmd, cmdLen, True, data, [], numBytes,  waitForBusy)

    def SPIreadCommand(self, cmd, cmdLen, data, numBytes, waitForBusy=True):
        return self.SPItransfer(cmd, cmdLen, False, [], data, numBytes, waitForBusy)

    def SPItransfer(
        self,
        cmd,
        cmdLen,
        write,
        dataOut,
        dataIn,
        numBytes,
        waitForBusy,
        timeout=5000
    ):
    
        self.cs.value(0)

        start = time.ticks_ms()
        while self.gpio.value():
            yield_()
            if time.ticks_diff(time.ticks_ms(), start) >= timeout:
                self.cs.value(1)
                return _ERR_SPI_CMD_TIMEOUT

        for i in range(cmdLen):
            self.spi.write(bytes([cmd[i]]))

        status = 0

        if write:
            for i in range(numBytes):
                try:
                    in_ = self.spi.read(1, dataOut[i])
                except:
                    in_ = self.spi.read(1, write=dataOut[i])

                if (
                    in_[0] & 0b00001110 == _SX126X_STATUS_CMD_TIMEOUT or
                    in_[0] & 0b00001110 == _SX126X_STATUS_CMD_INVALID or
                    in_[0] & 0b00001110 == _SX126X_STATUS_CMD_FAILED
                ):
                    status = in_[0] & 0b00001110
                    break
                elif in_[0] == 0x00 or in_[0] == 0xFF:
                    status = _SX126X_STATUS_SPI_FAILED
                    break
        else:

            try:
                in_ = self.spi.read(1, _SX126X_CMD_NOP)
            except:
                in_ = self.spi.read(1, write=_SX126X_CMD_NOP)

            if (
                in_[0] & 0b00001110 == _SX126X_STATUS_CMD_TIMEOUT or
                in_[0] & 0b00001110 == _SX126X_STATUS_CMD_INVALID or
                in_[0] & 0b00001110 == _SX126X_STATUS_CMD_FAILED
            ):
                status = in_[0] & 0b00001110
            elif in_[0] == 0x00 or in_[0] == 0xFF:
                status = _SX126X_STATUS_SPI_FAILED
            else:
                for i in range(numBytes):
                    try:
                        dataIn[i] = self.spi.read(1, _SX126X_CMD_NOP)[0]
                    except:
                        dataIn[i] = self.spi.read(1, write=_SX126X_CMD_NOP)[0]

        self.cs.value(1)

        if waitForBusy:
            time.sleep_us(1)
            start = time.ticks_ms()
            while self.gpio.value():
                yield_()
                if time.ticks_diff(time.ticks_ms(), start) >= timeout:
                    status = _SX126X_STATUS_CMD_TIMEOUT
                    break

        switch = {
            _SX126X_STATUS_CMD_TIMEOUT: _ERR_SPI_CMD_TIMEOUT,
            _SX126X_STATUS_CMD_INVALID: _ERR_SPI_CMD_INVALID,
            _SX126X_STATUS_CMD_FAILED: _ERR_SPI_CMD_FAILED,
            _SX126X_STATUS_SPI_FAILED: _ERR_CHIP_NOT_FOUND
        }
        try:
            return switch[status]
        except:
            return _ERR_NONE


_SX126X_PA_CONFIG_SX1262 = const(0x00)


class SX1262(SX126X):
    TX_DONE = _SX126X_IRQ_TX_DONE
    RX_DONE = _SX126X_IRQ_RX_DONE
    ADDR_FILT_OFF = _SX126X_GFSK_ADDRESS_FILT_OFF
    ADDR_FILT_NODE = _SX126X_GFSK_ADDRESS_FILT_NODE
    ADDR_FILT_NODE_BROAD = _SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST
    PREAMBLE_DETECT_OFF = _SX126X_GFSK_PREAMBLE_DETECT_OFF
    PREAMBLE_DETECT_8 = _SX126X_GFSK_PREAMBLE_DETECT_8
    PREAMBLE_DETECT_16 = _SX126X_GFSK_PREAMBLE_DETECT_16
    PREAMBLE_DETECT_24 = _SX126X_GFSK_PREAMBLE_DETECT_24
    PREAMBLE_DETECT_32 = _SX126X_GFSK_PREAMBLE_DETECT_32
    STATUS = ERROR

    def __init__(self, spi_device, irq, rst, gpio, cs_pin):
        super().__init__(spi_device, irq, rst, gpio, cs_pin)
        self._callbackFunction = self._dummyFunction

    def begin(
        self,
        freq=434.0,
        bw=125.0,
        sf=9,
        cr=7,
        syncWord=_SX126X_SYNC_WORD_PRIVATE,
        power=14,
        currentLimit=60.0,
        preambleLength=8,
        implicit=False,
        implicitLen=0xFF,
        crcOn=True,
        txIq=False,
        rxIq=False,
        tcxoVoltage=1.6,
        useRegulatorLDO=False,
        blocking=True
    ):
        state = super().begin(bw, sf, cr, syncWord, currentLimit,
                              preambleLength, tcxoVoltage, useRegulatorLDO,
                              txIq, rxIq)
        ASSERT(state)

        if not implicit:
            state = super().explicitHeader()
        else:
            state = super().implicitHeader(implicitLen)
        ASSERT(state)

        state = super().setCRC(crcOn)
        ASSERT(state)

        state = self.setFrequency(freq)
        ASSERT(state)

        state = self.setOutputPower(power)
        ASSERT(state)

        state = super().fixPaClamping()
        ASSERT(state)

        state = self.setBlockingCallback(blocking)

        return state

    def beginFSK(
        self,
        freq=434.0,
        br=48.0,
        freqDev=50.0,
        rxBw=156.2,
        power=14,
        currentLimit=60.0,
        preambleLength=16,
        dataShaping=0.5,
        syncWord=[0x2D, 0x01],
        syncBitsLength=16,
        addrFilter=_SX126X_GFSK_ADDRESS_FILT_OFF,
        addr=0x00,
        crcLength=2,
        crcInitial=0x1D0F,
        crcPolynomial=0x1021,
        crcInverted=True,
        whiteningOn=True,
        whiteningInitial=0x0100,
        fixedPacketLength=False,
        packetLength=0xFF,
        preambleDetectorLength=_SX126X_GFSK_PREAMBLE_DETECT_16,
        tcxoVoltage=1.6,
        useRegulatorLDO=False,
        blocking=True
    ):
        state = super().beginFSK(br, freqDev, rxBw, currentLimit,
                                 preambleLength, dataShaping,
                                 preambleDetectorLength, tcxoVoltage,
                                 useRegulatorLDO)
        ASSERT(state)

        state = super().setSyncBits(syncWord, syncBitsLength)
        ASSERT(state)

        if addrFilter == _SX126X_GFSK_ADDRESS_FILT_OFF:
            state = super().disableAddressFiltering()
        elif addrFilter == _SX126X_GFSK_ADDRESS_FILT_NODE:
            state = super().setNodeAddress(addr)
        elif addrFilter == _SX126X_GFSK_ADDRESS_FILT_NODE_BROADCAST:
            state = super().setBroadcastAddress(addr)
        else:
            state = _ERR_UNKNOWN

        ASSERT(state)

        state = super().setCRC(crcLength, crcInitial,
                               crcPolynomial, crcInverted)
        ASSERT(state)

        state = super().setWhitening(whiteningOn, whiteningInitial)
        ASSERT(state)

        if fixedPacketLength:
            state = super().fixedPacketLengthMode(packetLength)
        else:
            state = super().variablePacketLengthMode(packetLength)

        ASSERT(state)

        state = self.setFrequency(freq)
        ASSERT(state)

        state = self.setOutputPower(power)
        ASSERT(state)

        state = super().fixPaClamping()
        ASSERT(state)

        state = self.setBlockingCallback(blocking)

        return state

    def setFrequency(self, freq, calibrate=True):
        if freq < 150.0 or freq > 960.0:
            return _ERR_INVALID_FREQUENCY

        if calibrate:
            #data = bytearray(2) # taken from https://github.com/ehong-tl/micropySX126X
            data = self._tx_buf
            if freq > 900.0:
                data[0] = _SX126X_CAL_IMG_902_MHZ_1
                data[1] = _SX126X_CAL_IMG_902_MHZ_2
            elif freq > 850.0:
                data[0] = _SX126X_CAL_IMG_863_MHZ_1
                data[1] = _SX126X_CAL_IMG_863_MHZ_2
            elif freq > 770.0:
                data[0] = _SX126X_CAL_IMG_779_MHZ_1
                data[1] = _SX126X_CAL_IMG_779_MHZ_2
            elif freq > 460.0:
                data[0] = _SX126X_CAL_IMG_470_MHZ_1
                data[1] = _SX126X_CAL_IMG_470_MHZ_2
            else:
                data[0] = _SX126X_CAL_IMG_430_MHZ_1
                data[1] = _SX126X_CAL_IMG_430_MHZ_2

            state = super().calibrateImage(self._tx_mv[:2])
            ASSERT(state)

        return super().setFrequencyRaw(freq)

    def setOutputPower(self, power):
        if not (-9 <= power <= 22):
            return _ERR_INVALID_OUTPUT_POWER

        ocp = bytearray(1)
        ocp_mv = memoryview(ocp)
        state = super().readRegister(_SX126X_REG_OCP_CONFIGURATION, ocp_mv, 1)
        ASSERT(state)

        state = super().setPaConfig(0x04, _SX126X_PA_CONFIG_SX1262)
        ASSERT(state)

        state = super().setTxParams(power)
        ASSERT(state)

        return super().writeRegister(_SX126X_REG_OCP_CONFIGURATION, ocp, 1)

    def setTxIq(self, txIq):
        self._txIq = txIq

    def setRxIq(self, rxIq):
        self._rxIq = rxIq
        if not self.blocking:
            ASSERT(super().startReceive())

    def setPreambleDetectorLength(self, preambleDetectorLength):
        self._preambleDetectorLength = preambleDetectorLength
        if not self.blocking:
            ASSERT(super().startReceive())

    def setBlockingCallback(self, blocking, callback=None):
        self.blocking = blocking
        if not self.blocking:
            state = super().startReceive()
            ASSERT(state)

            if callback is not None:
                self._callbackFunction = callback
                super().setDio1Action(self._onIRQ)
            else:
                self._callbackFunction = self._dummyFunction
                super().clearDio1Action()
            return state
        else:
            state = super().standby()
            ASSERT(state)
            self._callbackFunction = self._dummyFunction
            super().clearDio1Action()
            return state

    def recv(self, len=0, timeout_en=False, timeout_ms=0):
        if not self.blocking:
            return self._readData(len)
        else:
            return self._receive(len, timeout_en, timeout_ms)

    def send(self, data):
        if not self.blocking:
            return self._startTransmit(data)
        else:
            return self._transmit(data)

    def _events(self):
        return super().getIrqStatus()

    def _receive(self, len_=0, timeout_en=False, timeout_ms=0):
        length = len_

        if len_ == 0:
            length = _SX126X_MAX_PACKET_LENGTH

        data = bytearray(length)
        data_mv = memoryview(data)

        try:
            state = super().receive(data_mv, length, timeout_en, timeout_ms)
        except AssertionError as e:
            state = list(ERROR.keys())[list(ERROR.values()).index(str(e))]

        if state == _ERR_NONE or state == _ERR_CRC_MISMATCH:
            if len_ == 0:
                length = super().getPacketLength(False)
                data = data[:length]

        else:
            return b'', state

        return bytes(data), state

    def _transmit(self, data):
        if isinstance(data, bytes) or isinstance(data, bytearray):
            pass
        else:
            return 0, _ERR_INVALID_PACKET_TYPE

        state = super().transmit(data, len(data))
        return len(data), state

    def _readData(self, len_=0):
        length = super().getPacketLength()

        if len_ < length and len_ != 0:
            length = len_

        data = bytearray(length)
        data_mv = memoryview(data)

        try:
            state = super().readData(data_mv, length)
        except AssertionError as e:
            state = list(ERROR.keys())[list(ERROR.values()).index(str(e))]

        ASSERT(super().startReceive())

        if state == _ERR_NONE or state == _ERR_CRC_MISMATCH:
            return bytes(data), state

        else:
            return b'', state

    def _startTransmit(self, data):
        if isinstance(data, bytes) or isinstance(data, bytearray):
            pass
        else:
            return 0, _ERR_INVALID_PACKET_TYPE

        state = super().startTransmit(data, len(data))
        return len(data), state

    def _dummyFunction(self, *args):
        pass

    def _onIRQ(self, callback):
        events = self._events()
        if events & _SX126X_IRQ_TX_DONE:
            super().startReceive()
        self._callbackFunction(events)
