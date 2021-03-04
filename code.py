# usb midi control for Reaper based on Pixlwave's work
# https://github.com/pixlwave/Pico/blob/main/seq3.py
# works with the pimoroni rgb keypad
# written for circuitpython v6.2.0
# requires the following libs:
# - adafruit_bus_device
# - adafruit_dotstar
# - adafruit_midi

import board
import time
import random

# led control
import adafruit_dotstar
from digitalio import DigitalInOut, Direction

# button access
import busio
from adafruit_bus_device.i2c_device import I2CDevice

# midi comms
import usb_midi
import adafruit_midi
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_on import NoteOn
from adafruit_midi.note_off import NoteOff
from adafruit_midi.midi_message import MIDIUnknownEvent

# led setup
cs = DigitalInOut(board.GP17)
cs.direction = Direction.OUTPUT
cs.value = 0
pixels = adafruit_dotstar.DotStar(board.GP18, board.GP19, 16,
                                  brightness=0.5, auto_write=True)

# button setup
i2c = busio.I2C(board.GP5, board.GP4)
device = I2CDevice(i2c, 0x20)

# midi setup
channel = 15
midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1], out_channel=channel)
midi_mute_cc = 16
midi_mute_note = 16
midi_solo_cc = 64
midi_solo_note = 8
bank_size = 12
bank_offset = 0

class MidiMode:
    CUSTOM = 0
    MACKIE = 1

class Mackie:
    BANK_LEFT = 46
    BANK_RIGHT = 47
    MUTE_BASE_NOTE = 16
    SOLO_BASE_NOTE = 8

midi_mode = MidiMode.MACKIE

class ButtonState:
    RELEASED = 0
    PRESSED = 1

class Color:
    OFF = (0, 0, 0)
    MUTED = (127, 0, 0)
    LIVE = (0, 127, 0)
    SOLO = (127, 127, 0)
    BANK = (0, 64, 127)
    ACTIVE_BANK = (127, 127, 127)

def dim_color(color):
    return tuple([int(0.1 * value) for value in color])

button_map = [12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3]

last_button_states = [0] * 16
last_button_pressed_times = [None] * 16
mute_states = [0] * 16
solo_states = [0] * 16

def read_button_states():
    pressed = [0] * 16
    with device:
        device.write(bytes([0x0]))
        result = bytearray(2)
        device.readinto(result)
        b = result[0] | result[1] << 8
        for i in range(16):
            if not (1 << i) & b:
                pressed[i] = 1
            else:
                pressed[i] = 0
    return pressed


def wait(delay):
    update_leds()
    
    global midi_mode
    global button_mode
    global last_button_states
    global last_button_pressed_times

    now = time.monotonic()
    while time.monotonic() < now + delay:
        button_states = read_button_states()

        for i in range(16):
            if button_states[i] == 1 and last_button_states[i] == 0:
                last_button_pressed_times[i] = now
            elif button_states[i] == 0 and last_button_states[i] == 1:
                if last_button_pressed_times[i] + 0.5 < now:
                    long_press(i)
                else:
                    short_press(i)
                last_button_pressed_times[i] = None

        last_button_states = button_states
        time.sleep(0.001)

def short_press(index):
    if index < 12:
        toggle_mute(index)
    else:
        bank_sel(index)

def long_press(index):
    if index < 12:
        toggle_solo(index)
    else:
        bank_sel(index)

def toggle_mute(index):
    global mute_states
    global midi_mute_note

    mute_state = mute_states[index]

    if mute_state == 1:
        mute_states[index] = 0
    else:
        mute_states[index] = 1

    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_mute(index, mute_states[index])
    else:
        toggle_custom_mute(index, mute_states[index])
        
def toggle_custom_mute(index, mute_state):
    cc_num = bank_offset * bank_size + midi_mute_cc + index
    if mute_state == 1:
        midi.send(ControlChange(cc_num, 0))
    else:
        midi.send(ControlChange(cc_num, 127))

def toggle_mackie_mute(index, _mute_state):
    midi.send(NoteOn(Mackie.MUTE_BASE_NOTE + index, 127))

def toggle_solo(index):
    global solo_states
    global midi_solo_note

    solo_state = solo_states[index]

    if solo_state == 1:
        solo_states[index] = 0
    else:
        solo_states[index] = 1

    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_solo(index, solo_states[index])
    else:
        toggle_custom_solo(index, solo_states[index])
        
def toggle_mackie_solo(index, solo_state):
    midi.send(NoteOn(Mackie.SOLO_BASE_NOTE + index, 127))

def toggle_custom_solo(index, solo_state):
    cc_num = bank_offset * bank_size + midi_solo_cc + index
    if solo_state == 1:
        midi.send(ControlChange(cc_num, 0))
    else:
        midi.send(ControlChange(cc_num, 127))

def bank_sel(index):
    global bank_offset
    last_bank_offset = bank_offset
    bank_offset = index - 12
    
    if midi_mode == MidiMode.MACKIE:
        if bank_offset < last_bank_offset:
            midi.send(NoteOn(Mackie.BANK_LEFT, 127))
        elif bank_offset > last_bank_offset:
            midi.send(NoteOn(Mackie.BANK_RIGHT, 127))

def update_leds():
    global solo_states
    global mute_states
    global bank_offset
    for i in range(12):
        isSolod = solo_states[i]
        isMuted = mute_states[i]
        if isSolod:
            pixels[i] = Color.SOLO
        else:
            pixels[i] = Color.MUTED if isMuted == 1 else Color.LIVE
    for i in range(12,16):
        if bank_offset == i - 12:
            pixels[i] = Color.ACTIVE_BANK
        else:
            pixels[i] = Color.BANK


# main loop
while True:
    msg_in = midi.receive()  # non-blocking read
    if msg_in is not None:
        if isinstance(msg_in, NoteOn):
            print(f"NoteOn {msg_in.note}, v{msg_in.velocity}, ch {msg_in.channel + 1}")
        elif isinstance(msg_in, NoteOff):
            print(f"NoteOff {msg_in.note}, ch {msg_in.channel + 1}")
        elif isinstance(msg_in, ControlChange):
            print(f"ControlChange {msg_in.control}, v{msg_in.value}, ch {msg_in.channel + 1}")
        elif isinstance(msg_in, MIDIUnknownEvent) is not True:
            print("msg_in ", msg_in)
    wait(0.105)
