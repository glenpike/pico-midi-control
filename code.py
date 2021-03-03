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
midi_solo_cc = 32
midi_solo_note = 8

class MidiMode:
    CUSTOM = 0
    MACKIE = 1

midi_mode = MidiMode.CUSTOM

class ButtonState:
    RELEASED = 0
    PRESSED = 1

class Color:
    MUTED = (127, 0, 0)
    LIVE = (0, 127, 0)
    SOLO = (127, 127, 0)

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
                #button_press(i, ButtonState.PRESSED)
            #elif button_states[i] == 1:
            #    if last_button_pressed_times[i] + 0.5 < now:
            #        button_press(i, ButtonState.LONGPRESSED)
            elif button_states[i] == 0 and last_button_states[i] == 1:
                if last_button_pressed_times[i] + 0.5 < now:
                    toggle_solo(i)
                else:
                    toggle_mute(i)
                last_button_pressed_times[i] = None

        last_button_states = button_states
        time.sleep(0.001)

def toggle_mute(index):
    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_mute(index)
    else:
        toggle_custom_mute(index)
        
def toggle_custom_mute(index):
    global mute_states
    global midi_mute_cc

    mute_state = mute_states[index]

    if mute_state == 1:
        mute_states[index] = 0
        midi.send(ControlChange(midi_mute_cc + index, 0))
    else:
        mute_states[index] = 1
        midi.send(ControlChange(midi_mute_cc + index, 127))


def toggle_mackie_mute(index):
    global mute_states
    global midi_mute_note

    mute_state = mute_states[index]

    if mute_state == 1:
        mute_states[index] = 0
    else:
        mute_states[index] = 1

    midi.send(NoteOn(midi_mute_note + index, 127))

def toggle_solo(index):
    if midi_mode == MidiMode.MACKIE:
        toggle_mackie_solo(index)
    else:
        toggle_custom_solo(index)
        
def toggle_mackie_solo(index):
    global solo_states
    global midi_solo_note

    solo_state = solo_states[index]

    if solo_state == 1:
        solo_states[index] = 0
    else:
        solo_states[index] = 1

    midi.send(NoteOn(midi_solo_note + index, 127))

def toggle_custom_solo(index):
    global solo_states
    global midi_solo_cc

    solo_state = solo_states[index]

    if solo_state == 1:
        solo_states[index] = 0
        midi.send(ControlChange(midi_solo_cc + index, 0))
    else:
        solo_states[index] = 1
        midi.send(ControlChange(midi_solo_cc + index, 127))

def update_leds():
    global solo_states
    global mute_states
    for i in range(16):
        isSolod = solo_states[i]
        isMuted = mute_states[i]
        if isSolod:
            pixels[i] = Color.SOLO
        else:
            pixels[i] = Color.MUTED if isMuted == 1 else Color.LIVE



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
