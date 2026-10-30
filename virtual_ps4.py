#!/usr/bin/env python3
"""
キーボードで操作する仮想PS4コントローラー（講習用）
uinputで仮想ゲームパッドを作るので、joy_nodeから実機のDS4と同じ番号で見える
実機がなくても PS4_Turtle_Teleop.cpp をそのまま試せる

準備: sudo apt install python3-evdev
実行: sudo python3 virtual_ps4.py
※ キーボードは端末に関係なく全体から読むので、他のウィンドウで打ったキーも入力になる

Copyright (c) 2025 RRST-NHK-Project. All rights reserved.
"""

import selectors
import sys
import termios

import evdev
from evdev import AbsInfo, UInput
from evdev import ecodes as e

DEVICE_NAME = "Virtual PS4 Controller"

# スティックの値域（実機のDS4と同じ 0〜255、中央128）
STICK_MIN = 0
STICK_MAX = 255
STICK_CENTER = 128

# Shiftを押している間のスティックの倒し量（デッドゾーンや低速の確認用）
HALF_RATIO = 0.5

"""
キー割り当て
| キー | 入力 | joy の番号 |
| ---- | ---- | ---- |
| W/A/S/D | 左スティック | axes[0], axes[1] |
| I/J/K/L | 右スティック | axes[3], axes[4] |
| 矢印キー | 十字キー | axes[6], axes[7] |
| 2 / 3 / 4 / 1 | × / ○ / △ / □ | buttons[0]〜[3] |
| Q / E | L1 / R1 | buttons[4], [5] |
| Z / C | L2 / R2 | buttons[6], [7]（axes[2], axes[5]も連動） |
| Tab / Enter | SHARE / OPTIONS | buttons[8], [9] |
| P | PS | buttons[10] |
| F / H | L3 / R3 | buttons[11], [12] |
| 左Shift（押しながら） | スティックを半分だけ倒す | - |
"""
BUTTON_KEYS = {
    e.KEY_2: e.BTN_SOUTH,      # ×
    e.KEY_3: e.BTN_EAST,       # ○
    e.KEY_4: e.BTN_NORTH,      # △
    e.KEY_1: e.BTN_WEST,       # □
    e.KEY_Q: e.BTN_TL,         # L1
    e.KEY_E: e.BTN_TR,         # R1
    e.KEY_Z: e.BTN_TL2,        # L2
    e.KEY_C: e.BTN_TR2,        # R2
    e.KEY_TAB: e.BTN_SELECT,   # SHARE
    e.KEY_ENTER: e.BTN_START,  # OPTIONS
    e.KEY_P: e.BTN_MODE,       # PS
    e.KEY_F: e.BTN_THUMBL,     # L3
    e.KEY_H: e.BTN_THUMBR,     # R3
}

# (負方向のキー, 正方向のキー)  evdevではYは上が負
STICK_KEYS = {
    e.ABS_X: (e.KEY_A, e.KEY_D),
    e.ABS_Y: (e.KEY_W, e.KEY_S),
    e.ABS_RX: (e.KEY_J, e.KEY_L),
    e.ABS_RY: (e.KEY_I, e.KEY_K),
}

HAT_KEYS = {
    e.ABS_HAT0X: (e.KEY_LEFT, e.KEY_RIGHT),
    e.ABS_HAT0Y: (e.KEY_UP, e.KEY_DOWN),
}

# アナログトリガー（ボタンと連動、押したら最大）
TRIGGER_KEYS = {
    e.ABS_Z: e.KEY_Z,   # L2
    e.ABS_RZ: e.KEY_C,  # R2
}


def create_gamepad():
    # 軸とボタンはコード順に番号が振られるので、実機のDS4と同じ並びになる
    stick = AbsInfo(value=STICK_CENTER, min=STICK_MIN, max=STICK_MAX, fuzz=0, flat=0, resolution=0)
    trigger = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
    hat = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)
    capabilities = {
        e.EV_KEY: sorted(BUTTON_KEYS.values()),
        e.EV_ABS: [
            (e.ABS_X, stick),
            (e.ABS_Y, stick),
            (e.ABS_Z, trigger),
            (e.ABS_RX, stick),
            (e.ABS_RY, stick),
            (e.ABS_RZ, trigger),
            (e.ABS_HAT0X, hat),
            (e.ABS_HAT0Y, hat),
        ],
    }
    return UInput(capabilities, name=DEVICE_NAME, vendor=0x1234, product=0x5678, version=1)


def find_keyboards():
    keyboards = []
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        keys = dev.capabilities().get(e.EV_KEY, [])
        if e.KEY_A in keys and e.KEY_SPACE in keys and dev.name != DEVICE_NAME:
            keyboards.append(dev)
        else:
            dev.close()
    return keyboards


def direction(pressed, keys):
    # 両方押したら打ち消し合って0
    neg, pos = keys
    return (pos in pressed) - (neg in pressed)


def compute_state(pressed):
    ratio = HALF_RATIO if e.KEY_LEFTSHIFT in pressed else 1.0
    state = {}
    for axis, keys in STICK_KEYS.items():
        d = direction(pressed, keys)
        span = (STICK_MAX - STICK_CENTER) if d > 0 else (STICK_CENTER - STICK_MIN)
        state[(e.EV_ABS, axis)] = STICK_CENTER + round(d * span * ratio)
    for axis, keys in HAT_KEYS.items():
        state[(e.EV_ABS, axis)] = direction(pressed, keys)
    for axis, key in TRIGGER_KEYS.items():
        state[(e.EV_ABS, axis)] = 255 if key in pressed else 0
    for key, btn in BUTTON_KEYS.items():
        state[(e.EV_KEY, btn)] = int(key in pressed)
    return state


def main():
    try:
        gamepad = create_gamepad()
    except (PermissionError, evdev.uinput.UInputError) as ex:
        sys.exit(f"仮想デバイスを作れません（sudoで実行してください）: {ex}")

    keyboards = find_keyboards()
    if not keyboards:
        gamepad.close()
        sys.exit("キーボードが見つかりません（sudoで実行してください）")

    sel = selectors.DefaultSelector()
    for kb in keyboards:
        sel.register(kb, selectors.EVENT_READ)

    # 押したキーが端末に表示されないようにエコーを切る（Ctrl+Cは効く）
    tty_attr = None
    if sys.stdin.isatty():
        tty_attr = termios.tcgetattr(sys.stdin)
        no_echo = termios.tcgetattr(sys.stdin)
        no_echo[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, no_echo)

    print(f"'{DEVICE_NAME}' を作成しました: {gamepad.device.path}")
    print("左スティック:WASD  右スティック:IJKL  十字:矢印  ×○△□:2341")
    print("L1/R1:Q/E  L2/R2:Z/C  SHARE:Tab  OPTIONS:Enter  PS:P  L3/R3:F/H  半分:左Shift")
    print("終了: Ctrl+C")

    pressed = set()
    last_state = {}
    try:
        while True:
            for key, _ in sel.select():
                for ev in key.fileobj.read():
                    if ev.type != e.EV_KEY or ev.value == 2:  # 2はキーリピート
                        continue
                    if ev.value == 1:
                        pressed.add(ev.code)
                    else:
                        pressed.discard(ev.code)

            state = compute_state(pressed)
            changed = False
            for (ev_type, code), value in state.items():
                if last_state.get((ev_type, code)) != value:
                    gamepad.write(ev_type, code, value)
                    changed = True
            if changed:
                gamepad.syn()
                last_state = state
    except KeyboardInterrupt:
        pass
    finally:
        if tty_attr is not None:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, tty_attr)
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        gamepad.close()
        for kb in keyboards:
            kb.close()
        print("\n終了しました")


if __name__ == "__main__":
    main()
