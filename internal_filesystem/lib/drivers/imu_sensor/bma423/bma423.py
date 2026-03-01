# BMA423 driver that aims to support features detection.
#
# Copyright (C) 2024 Salvatore Sanfilippo -- All Rights Reserved
# This code is released under the MIT license
# https://opensource.org/license/mit/
#
# Written reading the specification at:
# https://www.mouser.com/datasheet/2/783/BST-BMA423-DS000-1509600.pdf

from machine import Pin
import time

# Registers
REG_CHIP_ID = const(0x00)       # Chip identification number.
REG_INT_STATUS_0 = const(0x1C)  # Interrupt status for features detection.
REG_INT_STATUS_1 = const(0x1D)  # Interrupt status for data ready.
REG_STEP_COUNTER_0 = const(0x1E) # For bytes starting here. Number of steps.
REG_TEMPERATURE = const(0x22) # Temperature sensor reading: kelvin units.
REG_INTERNAL_STATUS = const(0x2A) # Error / status bits.
REG_ACC_CONF = const(0x40)  # Out data rate, bandwidth, read mode.
REG_ACC_RANGE = const(0x41) # Acceleration range selection.
REG_PWR_CONF = const(0x7c)  # Power mode configuration.
REG_PWR_CTL = const(0x7d)   # Used to power-on the device parts
REG_CMD = const(0x7e)       # Write there to send commands
REG_INT1_IO_CTRL = const(0x53) # Electrical config of interrupt 1 pin.
REG_INT2_IO_CTRL = const(0x54) # Electrical config of interrupt 2 pin.
REG_INT_LATCH = const(0x55) # Interrupt latch mode.
REG_INT1_MAP = const(0x56)  # Interrput map for detected features and pin1.
REG_INT2_MAP = const(0x57)  # Interrput map for detected features and pin2.
REG_INT_MAP_DATA = const(0x58) # Interrupt map for pin1/2 data events.
REG_INIT_CTRL = const(0x59) # Initialization register.
FEATURES_IN_SIZE = const(70) # Size of the features configuration area

# Commands for the REG_CMD register
REG_CMD_SOFTRESET = const(0xB6)

class BMA423:
    # Acceleration range can be selected among the available settings of
    # 2G, 4G, 8G and 16G. If we want to be able to measure higher
    # max accelerations, the relative precision decreases as we have
    # a fixed 12 bit reading.
    def __init__(self,i2c,*,acc_range=2):
        default_addr = [0x18,0x19] # Changes depending on SDO pin
                                   # pulled to ground or V+
        self.i2c = i2c
        self.myaddr = None
        self.features_in = bytearray(FEATURES_IN_SIZE)

        found_devices = i2c.scan()
        print("BMA423: scan i2c bus:", [hex(x) for x in found_devices])
        for addr in default_addr:
            if addr in found_devices:
                self.myaddr = addr
                break
        if self.myaddr == None:
            raise Exception("BMA423 not found at i2c bus")
        print("BMA423: device with matching address found at",hex(self.myaddr))

        # Device initialization.
        self.reset()
        chip_id = self.get_reg(REG_CHIP_ID)
        if chip_id != 0x13:
            raise Exception("BMA423 chip ID is not 0x13 as expected. Different sensor connected?")
        print("BMA423: chip correctly identified.")

        # Set default parameters. By default we enable the accelerometer
        # so that the user can read the acceleration vector from the
        # device without much setup work.
        self.enable_accelerometer(acc=True,aux=False)
        self.set_accelerometer_perf(True)
        self.set_accelerometer_avg(2)
        self.set_accelerometer_freq(100)
        self.set_advanced_power_save(False,False)
        self.set_range(acc_range)

    # Soft reset using the commands register.
    def reset(self):
        self.set_reg(REG_CMD,REG_CMD_SOFTRESET) # Reset the chip.
        time.sleep(1) # Datasheet claims we need to wait that much. I know.

    # Enable or disable advanced power saving (ADP).
    #
    # When data is not being sampled, power saving mode slows down the
    # clock and makes latency higher.
    # Fifo self wakeup controls if the FIFO works when ADP is enabled.
    # Step counting less reliable if APS is enabled (note of the implementator).
    def set_advanced_power_save(self,adp=False,fifo_self_wakeup=False):
        adp = int(adp) & 1
        fifo_self_wakeup = (int(fifo_self_wakeup) & 1) << 1
        self.set_reg(REG_PWR_CONF,adp|fifo_self_wakeup)

    # Enable/Disable accelerometer and aux sensor.
    def enable_accelerometer(self,*,acc=True,aux=False):
        val = 0
        if acc: val |= 0x4  # acc_en bit, enable accelerometer acquisition.
        if aux: val |= 0x1  # aux_en bit, enable aux sensor.
        self.set_reg(REG_PWR_CTL,val)

    # Enable/Disable performance mode. When performance mode is enabled
    # the accelerometer performs continuous sampling at the specified
    # sampling rate.
    def set_accelerometer_perf(self,perf_mode):
        val = self.get_reg(REG_ACC_CONF)
        val = (val & 0b01111111) | (int(perf_mode) << 7)
        self.set_reg(REG_ACC_CONF,val)

    # Set average mode. The mode selected depends on the fact performance
    # mode is enabled/disabled.
    # Valid values:
    # perf mode on:  0 = osr4, 1 = osr2, 2 = normal, 3 = cic.
    # perf mode off: 0 = avg1, 1 = avg2, 2 = avg4, 3 = avg8
    #                4 = avg16, 5 = avg32, 6 = avg64, 7 = avg128.
    def set_accelerometer_avg(self,avg_mode):
        val = self.get_reg(REG_ACC_CONF)
        val = (val & 0b10001111) | avg_mode << 4
        self.set_reg(REG_ACC_CONF,val)

    # Set accelerometer sampling frequency, either as a frequency in
    # hz that we convert using a table, or as immediate value if the
    # user wants to select one of the low frequency modes (see datasheet).
    def set_accelerometer_freq(self,freq):
        table = {25:6, 50:7, 100:8, 200:9, 400:10, 800:11, 1600:12}
        if freq in table:
            freq = table[freq]
        elif freq == 0 or freq >= 0x0d:
            raise Exception("Invalid frequency or raw value")
        val = self.get_reg(REG_ACC_CONF)
        val = (val & 0b11110000) | freq
        self.set_reg(REG_ACC_CONF,val)

    # Write in the FEATURES-IN configuration to enable specific
    # features.
    def enable_features_detection(self,*features):
        self.read_features_in()
        for f in features:
            if f == "step-count":
                self.features_in[0x3B] |= 0x10 # Enable step counter.
            else:
                raise Exception("Unrecognized feature name",f)
        self.write_features_in()

    # Prepare the device to load the binary configuration in the
    # bma423conf.bin file (data from Bosch). This step is required for
    # features detection.
    def load_features_config(self):
        saved_pwr_conf = self.get_reg(REG_PWR_CONF) # To restore it later.
        self.set_reg(REG_PWR_CONF,0x00)  # Disable adv_power_save.
        time.sleep_us(500)               # Wait time synchronization.
        self.set_reg(REG_INIT_CTRL,0x00) # Prepare for loading configuration.
        self.transfer_config()           # Load binary features config.
        self.set_reg(REG_INIT_CTRL,0x01) # Enable features.
        time.sleep_ms(140)               # Wait ASIC initialization.

        # The chip is ready for further configuration when the
        # status "message" turns 1.
        wait_epoch = 0
        while True:
            status = self.get_reg(REG_INTERNAL_STATUS) & 0b11111
            if status == 1: break # Initialization successful
            time.sleep_ms(50)
            wait_epoch += 1
            if wait_epoch == 20:
                raise Exception("Timeout during init, internal_status: ",
                    status)
        print("BMA423: features engine initialized successfully.")
        self.set_reg(REG_PWR_CONF,saved_pwr_conf)

    # Write to the ASIC memory. This is useful to set the device
    # features configuration.
    #
    # Writing / reading from ASIC works setting two registers that
    # point to the memory area(0x5B/5C), and then reading/writing from/to
    # the register 0x5E. Note that while normally writing / reading
    # to a given register will write bytes to successive registers, in
    # the case of 0x5E it works like a "port", so we keep reading
    # or writing from successive parts of the ASIC memory.
    def write_config_mem(self,idx,buf):
        # The index of the half-word (so index/2) must
        # be placed into this two undocumented registers
        # 0x5B and 0x5C. Data goes in 0xE.
        # Thanks for the mess, Bosch!
        self.set_reg(0x5b,(idx//2)&0xf) # Set LSB (bits 3:0)
        self.set_reg(0x5c,(idx//2)>>4)  # Set MSB (bits 11:5)
        self.set_reg(0x5e,buf)

    # see write_config_mem().
    def read_config_mem(self,idx,count):
        self.set_reg(0x5b,(idx//2)&0xf) # Set LSB (bits 3:0)
        self.set_reg(0x5c,(idx//2)>>4)  # Set MSB (bits 11:5)
        return self.get_reg(0x5e,count)

    # Read the steps counter.
    def get_steps(self):
        data = self.get_reg(REG_STEP_COUNTER_0,4)
        return data[0] | data[1]<<8 | data[2]<<16 | data[3]<<24

    # The BMA423 features detection requires that we transfer a binary
    # blob via the features configuration register (and other two undocumented
    # registers that set the internal target address at which the register
    # points). If this are the weights of a small neural network, or just
    # parameters, I'm not sure. More info (LOL, not really) here:
    #
    # https://github.com/boschsensortec/BMA423_SensorDriver
    def transfer_config(self):
        print("Uploading features configuration...")
        f = open("bma423conf.bin","rb")
        buf = bytearray(8) # Binary config is multiple of 8 in len.
        idx = 0
        while f.readinto(buf,8) == 8:
            self.write_config_mem(idx,buf)
            idx += 8
        print("Done: total transfer: ", idx)

        # Verify the content.
        print("BMA423: Verifying stored configuration...")
        idx = 0
        f.seek(0)
        while f.readinto(buf,8) == 8:
            content = self.read_config_mem(idx,8)
            idx += 8
            if content != buf:
                raise Exception("Feature config data mismatch at",idx)
        f.close()

    # Enable interrupt for the specified list of events.
    #
    # 'chip_pin' is 1 or 2 (the chip has two interrupt pins), you should
    # select the one you want to use or the one you have an actual
    # connection to with your host.
    # 'pin' is your machine.Pin instance in your host.
    # 'callback' is the function to call when the specified events will fire.
    # 'events' is a list of strings specifying what events you want to
    # listen for. Valid events are:
    #    "data": new acceleration reading available.
    #    "fifo-wm: fifo watermark reached.
    #    "fifo-full": fifo is full.
    #    "step": step feature.
    #    "activity": detect walking, running, ...
    #    "tilt": tilt on wrist.
    #    "double-tap": double tap.
    #    "single-tap": single tap.
    #    "any-none": any motion / no motion detected.
    # Note: you can't subscribe to both double and single tap.
    def enable_interrupt(self,chip_pin,pin,callback,events):
        self.callback = callback

        # Features detection only work in latch mode.
        self.set_reg(REG_INT_LATCH,0x01)
        # feature name -> bit to set in INT1/2_MAP.
        feature_bits = {"any-none":6,"tilt":3,"activity":2,"step":1}
        # data source name -> bit to set for [pin1,pin2] in
        # INT_MAP_DATA.
        data_bits = {"data":[2,6],"fifo-wm":[1,5],"fifo-full":[0,4]}

        # Set features/data interrupt maps register values.
        feature_map,data_map = 0,0
        for e in events:
            if e in feature_bits:
                feature_map |= (1 << feature_bits[e])
            elif e in data_bits:
                data_map |= data_bits[e][chip_pin-1]
            else:
                raise Exception(f"Unknown event {e} when enabling interrupt.")
        if feature_map != 0:
            map_int_reg = REG_INT1_MAP if chip_pin == 1 else REG_INT2_MAP
            self.set_reg(map_int_reg,feature_map)
        if data_map != 0: self.set_reg(REG_INT_MAP_DATA,data_map)

        # XXX: set config registers according to single/double tap.
        # XXX: set FEATURES_IN registers.

        # Configure the electrical interrput pin behavior.
        ctrl_reg = REG_INT1_IO_CTRL if chip_pin == 1 else REG_INT2_IO_CTRL
        # Output enabled 0x8, active high 0x2, all other bits zero, that
        # is: input_enabled=no, edge_ctrl=level-trigger, od=push-pull.
        self.set_reg(ctrl_reg, 0x8 | 0x2)

        # Finally enable the interrupt in the host pin.
        pin.irq(handler=self.irq, trigger=Pin.IRQ_RISING)

    # Set range of 2, 4 or 8 or 16g
    def set_range(self,acc_range):
        range_to_regval = {2:0,4:1,8:2,16:3}
        if not acc_range in range_to_regval:
            raise Exception(f"Invalid range {acc_range}: use 2, 4, 8, 16",
                acc_range)
        self.range = acc_range
        self.set_reg(REG_ACC_RANGE,range_to_regval[acc_range])

    # Convert the raw 12 bit number in two's complement as a signed
    # number.
    def convert_to_int12(self,raw_value):
        if not raw_value & 0x800: return raw_value
        raw_value = ((~raw_value) & 0x7ff) + 1
        return -raw_value

    # Normalize the signed 12 bit acceleration value to
    # acceleration value in "g" according to the currently
    # selected range.
    def normalize_reading(self,reading):
        return self.range / 2047 * reading

    # Return x,y,z acceleration.
    def get_xyz(self):
        rawdata = self.get_reg(0x12,6)
        acc_x = (rawdata[0] >> 4) | (rawdata[1] << 4)
        acc_y = (rawdata[2] >> 4) | (rawdata[3] << 4)
        acc_z = (rawdata[4] >> 4) | (rawdata[5] << 4)
        acc_x = self.convert_to_int12(acc_x)
        acc_y = self.convert_to_int12(acc_y)
        acc_z = self.convert_to_int12(acc_z)
        acc_x = self.normalize_reading(acc_x)
        acc_y = self.normalize_reading(acc_y)
        acc_z = self.normalize_reading(acc_z)
        return (acc_x,acc_y,acc_z)

    # Return the chip tempereature in celsius.
    # If the temperature is invalid, None is returned.
    def get_temperature(self):
        raw = self.get_reg(REG_TEMPERATURE)
        if raw == 0x80: return None
        if raw & 0x80:
            raw = -((~raw)+1) # Conver 2 complement to signed integer.
        return 23+raw

    def irq(self,pin):
        if self.callback == None:
            printf("BMA423: not handled IRQ. Please, set a callback.")
            return
        data = {}

        print("IRQ CALLED")

        if len(data) == None: return
        self.callback(data)

    # Return the single byte at the specified register
    def get_reg(self, register, count=1):
        if count == 1:
            return self.i2c.readfrom_mem(self.myaddr,register,1)[0]
        else:
            return self.i2c.readfrom_mem(self.myaddr,register,count)

    # Write 'value' to the specified register
    def set_reg(self, register, value):
        if isinstance(value,bytearray) or isinstance(value,bytes):
            self.i2c.writeto_mem(self.myaddr,register,value)
        else:
            self.i2c.writeto_mem(self.myaddr,register,bytes([value]))

    def read_features_in(self):
        self.i2c.readfrom_mem_into(self.myaddr,0x5E,self.features_in)

    def write_features_in(self):
        self.i2c.writeto_mem(self.myaddr,0x5E,self.features_in)

# Example usage and quick test to see if your device is working.
if  __name__ == "__main__":
    from machine import SoftI2C, Pin
    import time

    # Called when a feature/data interrupt triggers.
    def mycallback(data):
        print(data)

    i2c = SoftI2C(scl=11,sda=10)
    sensor = BMA423(i2c)
    sensor.enable_interrupt(1,Pin(14,Pin.IN),mycallback,["data"])

    # Enable steps counting
    sensor.load_features_config()
    sensor.enable_features_detection("step-count")

    while True:
        print("(x,y,z),temp,steps",
            sensor.get_xyz(),
            sensor.get_temperature(),
            sensor.get_steps())
        time.sleep(.1)
