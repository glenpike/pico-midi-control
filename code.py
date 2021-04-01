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
from adafruit_midi.system_exclusive import SystemExclusive
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
midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1], out_channel=channel, debug=False)
midi_mute_cc = 0
midi_mute_note = 16
midi_solo_cc = 64
midi_solo_note = 8
bank_size = 8
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
mute_states = [0] * 64
solo_states = [0] * 64

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
    if index < 8:
        toggle_mute(index)
    else:
        bank_sel(index)

def long_press(button):
    if button < 8:
        toggle_solo(button)
    else:
        bank_sel(button)

def toggle_mute(button):
    global mute_states
    global midi_mute_note

    index = bank_offset * bank_size + button

    mute_state = mute_states[index]

    if mute_state == 1:
        mute_states[index] = 0
    else:
        mute_states[index] = 1

    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_mute(button, mute_states[index])
    else:
        toggle_custom_mute(button, mute_states[index])

def toggle_custom_mute(button, mute_state):
    cc_num = bank_offset * bank_size + midi_mute_cc + button
    if mute_state == 1:
        midi.send(ControlChange(cc_num, 0))
    else:
        midi.send(ControlChange(cc_num, 127))

def toggle_mackie_mute(button, _mute_state):
    midi.send(NoteOn(Mackie.MUTE_BASE_NOTE + button, 127))
    print(f"toggle_mackie_mute:  {button}: {_mute_state}")

def toggle_solo(button):
    global solo_states
    global midi_solo_note

    index = bank_offset * bank_size + button

    solo_state = solo_states[index]

    if solo_state == 1:
        solo_states[index] = 0
    else:
        solo_states[index] = 1

    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_solo(button, solo_states[index])
    else:
        toggle_custom_solo(button, solo_states[index])

def toggle_mackie_solo(button, solo_state):
    print(f"toggle_mackie_solo {button}")
    midi.send(NoteOn(Mackie.SOLO_BASE_NOTE + button, 127))

def toggle_custom_solo(button, solo_state):
    cc_num = bank_offset * bank_size + midi_solo_cc + button
    if solo_state == 1:
        midi.send(ControlChange(cc_num, 0))
    else:
        midi.send(ControlChange(cc_num, 127))

def bank_sel(button):
    global bank_offset
    last_bank_offset = bank_offset
    bank_offset = button - 8

    if midi_mode == MidiMode.MACKIE:
        if bank_offset < last_bank_offset:
            midi.send(NoteOn(Mackie.BANK_LEFT, 127))
        elif bank_offset > last_bank_offset:
            midi.send(NoteOn(Mackie.BANK_RIGHT, 127))

def update_leds():
    global solo_states
    global mute_states
    global bank_offset
    for i in range(8):
        index = bank_offset * bank_size + i
        isSolod = solo_states[index]
        isMuted = mute_states[index]
        if isSolod:
            pixels[i] = Color.SOLO
        else:
            pixels[i] = Color.MUTED if isMuted == 1 else Color.LIVE
    for i in range(8,16):
        if bank_offset == i - 8:
            pixels[i] = Color.ACTIVE_BANK
        else:
            pixels[i] = Color.BANK

def handle_note_on(msg_in):
    global mute_states
    global solo_states
    note = msg_in.note
    print(f"handle_note_on:  {note}: {msg_in.velocity}")
    index = note - Mackie.MUTE_BASE_NOTE
    if index >= 0 and index < len(mute_states):
        print(f"setting Mute:  {index}: {msg_in.velocity}")
        if msg_in.velocity == 127:
            mute_states[index] = 1
        else:
            mute_states[index] = 0
    else:
        index = note - Mackie.SOLO_BASE_NOTE
        if index >= 0 and index < len(solo_states):
            print(f"setting Solo:  {index}: {msg_in.velocity}")
            if msg_in.velocity != 0: #Reaper sends 1, Ableton 127
                solo_states[index] = 1
            else:
                solo_states[index] = 0


def handle_sysex(msg_in):
    print(f"SystemExclusive mfr: {msg_in.manufacturer_id}, data: {msg_in.data}")
    #midi.send(msg_in)

# main loop
while True:
    #buf = usb_midi.ports[0].read()
    #if buf is not None and len(buf):
    #    print(f"buf: {buf}")
    msg_in = midi.receive()  # non-blocking read
    #msg_in = None
    if msg_in is not None:
        if isinstance(msg_in, SystemExclusive):
            handle_sysex(msg_in)
        elif isinstance(msg_in, NoteOn):
            handle_note_on(msg_in)
        #elif isinstance(msg_in, NoteOff):
        #    print(f"NoteOff {msg_in.note}, ch {msg_in.channel + 1}")
        #elif isinstance(msg_in, ControlChange):
        #    print(f"ControlChange {msg_in.control}, v{msg_in.value}, ch {msg_in.channel + 1}")
        #elif isinstance(msg_in, MIDIUnknownEvent):
        #    print(f"MIDIUnknownEvent? status: {msg_in.status}")
        #else:
        #    print(f"Unknown Message? type: {type(msg_in)}, status: {msg_in.status}")
    wait(0.005)
