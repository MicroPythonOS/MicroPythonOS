# print_error.py Error print for IR receiver

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

from ir_rx import IR_RX

_errors = {IR_RX.BADSTART : 'Invalid start pulse',
           IR_RX.BADBLOCK : 'Error: bad block',
           IR_RX.BADREP : 'Error: repeat',
           IR_RX.OVERRUN : 'Error: overrun',
           IR_RX.BADDATA : 'Error: invalid data',
           IR_RX.BADADDR : 'Error: invalid address'}

def print_error(data):
    if data in _errors:
        print(_errors[data])
    else:
        print('Unknown error code:', data)
