#!/usr/bin/env python3
"""
GUIで操作する仮想PS4コントローラー（講習用）
virtual_ps4.py と同じ仮想デバイスを作るので、joy_nodeからは実機のDS4と同じ番号で見える

準備: sudo apt install python3-evdev python3-tk
      ./setup_uinput.sh （初回のみ。sudoなしで起動できるようにする）
実行: python3 virtual_ps4_gui.py

操作
- 左クリック: ボタンを押す / スティックをドラッグ（離すと中央に戻る）
- 右クリック: ボタンを押しっぱなしにする（もう一度で解除）
- 右ドラッグ: スティックをその位置で止める（右クリックだけで中央に戻す）
- キーボード: virtual_ps4.py と同じ割り当て（このウィンドウを選択しているときだけ）

Copyright (c) 2025 RRST-NHK-Project. All rights reserved.
"""

import sys
import tkinter as tk
from tkinter import messagebox

import evdev
from evdev import ecodes as e

import virtual_ps4 as vp

STICK_R = 50  # スティックの可動半径(px)
KNOB_R = 30
RELEASE_DELAY_MS = 40  # キーリピートで来る偽のKeyReleaseを無視する時間

# 色（講習資料と同じモノトーン）
INK = "#1A1A1A"
SUB = "#666666"
CARD = "#EDEDED"
BG = "#FFFFFF"

# tkinterのキー名 → evdevのキーコード（virtual_ps4.py の割り当てに合わせる）
KEYSYMS = {
    "w": e.KEY_W, "a": e.KEY_A, "s": e.KEY_S, "d": e.KEY_D,
    "i": e.KEY_I, "j": e.KEY_J, "k": e.KEY_K, "l": e.KEY_L,
    "Up": e.KEY_UP, "Down": e.KEY_DOWN, "Left": e.KEY_LEFT, "Right": e.KEY_RIGHT,
    "1": e.KEY_1, "2": e.KEY_2, "3": e.KEY_3, "4": e.KEY_4,
    "q": e.KEY_Q, "e": e.KEY_E, "z": e.KEY_Z, "c": e.KEY_C,
    "Tab": e.KEY_TAB, "Return": e.KEY_ENTER, "p": e.KEY_P,
    "f": e.KEY_F, "h": e.KEY_H, "Shift_L": e.KEY_LEFTSHIFT,
}

"""
画面上のボタン
| 名前 | 表示 | 中心(x, y) | 対応するキー |
"""
BUTTONS = [
    ("L2", "L2", (110, 40), e.KEY_Z),
    ("L1", "L1", (110, 85), e.KEY_Q),
    ("R2", "R2", (650, 40), e.KEY_C),
    ("R1", "R1", (650, 85), e.KEY_E),
    ("SHARE", "SHARE", (290, 85), e.KEY_TAB),
    ("PS", "PS", (380, 150), e.KEY_P),
    ("OPTIONS", "OPTIONS", (470, 85), e.KEY_ENTER),
    ("UP", "↑", (110, 160), e.KEY_UP),
    ("DOWN", "↓", (110, 240), e.KEY_DOWN),
    ("LEFT", "←", (70, 200), e.KEY_LEFT),
    ("RIGHT", "→", (150, 200), e.KEY_RIGHT),
    ("TRIANGLE", "△", (650, 160), e.KEY_4),
    ("CROSS", "×", (650, 240), e.KEY_2),
    ("SQUARE", "□", (610, 200), e.KEY_1),
    ("CIRCLE", "○", (690, 200), e.KEY_3),
    ("L3", "L3", (250, 390), e.KEY_F),
    ("R3", "R3", (510, 390), e.KEY_H),
]

# スティック: 名前, 中心, (X軸, Y軸)
STICKS = [
    ("LS", (250, 290), (e.ABS_X, e.ABS_Y)),
    ("RS", (510, 290), (e.ABS_RX, e.ABS_RY)),
]


def joy_stick(v):
    # joy_node と同じく左・上が +1
    span = (vp.STICK_MAX - vp.STICK_CENTER) if v > vp.STICK_CENTER else (vp.STICK_CENTER - vp.STICK_MIN)
    return -(v - vp.STICK_CENTER) / span


def joy_axes(state):
    # joy_node が publish する axes と同じ向き・範囲に変換（表示用）
    def trigger(v):
        return 1.0 - v / 127.5

    return [
        joy_stick(state[(e.EV_ABS, e.ABS_X)]), joy_stick(state[(e.EV_ABS, e.ABS_Y)]),
        trigger(state[(e.EV_ABS, e.ABS_Z)]),
        joy_stick(state[(e.EV_ABS, e.ABS_RX)]), joy_stick(state[(e.EV_ABS, e.ABS_RY)]),
        trigger(state[(e.EV_ABS, e.ABS_RZ)]),
        -state[(e.EV_ABS, e.ABS_HAT0X)], -state[(e.EV_ABS, e.ABS_HAT0Y)],
    ]


def joy_buttons(state):
    return [state[(e.EV_KEY, btn)] for btn in sorted(vp.BUTTON_KEYS.values())]


class VirtualPS4GUI:
    def __init__(self, root, gamepad):
        self.root = root
        self.gamepad = gamepad
        self.last_state = {}

        self.keys = set()      # キーボードで押しているキー
        self.mouse_key = None  # 左クリックで押しているボタンのキー
        self.latched = set()   # 右クリックで押しっぱなしのボタンのキー
        self.release_jobs = {}

        # スティックの位置(dx, dy)と、マウスで動かしているか
        self.stick_pos = {name: (0, 0) for name, _, _ in STICKS}
        self.stick_held = set()  # 右ドラッグで止めているスティック
        self.drag = None         # (スティック名, マウスボタン, 開始位置)

        root.title(vp.DEVICE_NAME)
        root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=760, height=520, bg=BG, highlightthickness=0)
        self.canvas.pack()
        self.draw()

        self.canvas.bind("<ButtonPress-1>", lambda ev: self.on_press(ev, 1))
        self.canvas.bind("<ButtonPress-3>", lambda ev: self.on_press(ev, 3))
        self.canvas.bind("<B1-Motion>", self.on_motion)
        self.canvas.bind("<B3-Motion>", self.on_motion)
        self.canvas.bind("<ButtonRelease-1>", lambda ev: self.on_release(ev, 1))
        self.canvas.bind("<ButtonRelease-3>", lambda ev: self.on_release(ev, 3))
        root.bind_all("<KeyPress>", self.on_key_press)
        root.bind_all("<KeyRelease>", self.on_key_release)
        root.bind("<FocusOut>", self.on_focus_out)

        self.refresh()

    # ---------- 描画 ----------
    def draw(self):
        c = self.canvas
        c.create_text(380, 30, text=vp.DEVICE_NAME, font=("Noto Sans CJK JP", 13, "bold"), fill=INK)
        c.create_text(380, 50, text=self.gamepad.device.path, font=("Noto Sans Mono", 9), fill=SUB)

        for name, label, (x, y), _ in BUTTONS:
            if name in ("L1", "L2", "R1", "R2", "SHARE", "OPTIONS", "L3", "R3"):
                w, h = (34, 16) if name in ("SHARE", "OPTIONS") else (30, 16)
                c.create_rectangle(x - w, y - h, x + w, y + h, outline=INK, width=1.5,
                                   fill=BG, tags=("btn", "btn:" + name, "shape:" + name))
            else:
                c.create_oval(x - 20, y - 20, x + 20, y + 20, outline=INK, width=1.5,
                              fill=BG, tags=("btn", "btn:" + name, "shape:" + name))
            size = 9 if len(label) > 2 else 13
            c.create_text(x, y, text=label, font=("Noto Sans CJK JP", size, "bold"), fill=INK,
                          tags=("btn", "btn:" + name, "label:" + name))

        for name, (x, y), _ in STICKS:
            c.create_oval(x - STICK_R - KNOB_R, y - STICK_R - KNOB_R, x + STICK_R + KNOB_R, y + STICK_R + KNOB_R,
                          fill=CARD, outline="", tags=("stick", "stick:" + name))
            c.create_oval(x - KNOB_R, y - KNOB_R, x + KNOB_R, y + KNOB_R, fill=INK, outline="",
                          tags=("stick", "stick:" + name, "knob:" + name))

        c.create_text(20, 440, anchor="nw", font=("Noto Sans Mono", 10), fill=INK, tags="joy")
        c.create_text(20, 500, anchor="nw", font=("Noto Sans CJK JP", 9), fill=SUB,
                      text="左クリック:押す  右クリック:押しっぱなし  右ドラッグ:スティック固定  キーボード:WASD/IJKL/矢印/1234 など")

    def update_view(self, state):
        c = self.canvas
        for name, _, _, key in BUTTONS:
            on = self.button_on(key)
            c.itemconfigure("shape:" + name, fill=INK if on else BG)
            c.itemconfigure("label:" + name, fill=BG if on else INK)
        for name, (x, y), (ax, ay) in STICKS:
            # キーボード操作も含めた実際の値からノブの位置を決める
            dx = -joy_stick(state[(e.EV_ABS, ax)]) * STICK_R
            dy = -joy_stick(state[(e.EV_ABS, ay)]) * STICK_R
            c.coords("knob:" + name, x + dx - KNOB_R, y + dy - KNOB_R, x + dx + KNOB_R, y + dy + KNOB_R)
        axes = ", ".join(f"{v:5.2f}" for v in joy_axes(state))
        buttons = ", ".join(str(b) for b in joy_buttons(state))
        c.itemconfigure("joy", text=f"axes:    [{axes}]\nbuttons: [{buttons}]")

    # ---------- 状態 ----------
    def button_on(self, key):
        return key in self.keys or key == self.mouse_key or key in self.latched

    def refresh(self):
        pressed = set(self.keys) | self.latched
        if self.mouse_key is not None:
            pressed.add(self.mouse_key)
        state = vp.compute_state(pressed)

        # マウスで動かしているスティックはキーボードより優先
        for name, _, (ax, ay) in STICKS:
            dragging = self.drag is not None and self.drag[0] == name
            if dragging or name in self.stick_held:
                dx, dy = self.stick_pos[name]
                state[(e.EV_ABS, ax)] = self.to_axis(dx)
                state[(e.EV_ABS, ay)] = self.to_axis(dy)

        changed = False
        for (ev_type, code), value in state.items():
            if self.last_state.get((ev_type, code)) != value:
                self.gamepad.write(ev_type, code, value)
                changed = True
        if changed:
            self.gamepad.syn()
            self.last_state = state
        self.update_view(state)

    @staticmethod
    def to_axis(d):
        span = (vp.STICK_MAX - vp.STICK_CENTER) if d > 0 else (vp.STICK_CENTER - vp.STICK_MIN)
        return vp.STICK_CENTER + round(d / STICK_R * span)

    # ---------- マウス ----------
    def hit(self):
        for tag in self.canvas.gettags("current"):
            if tag.startswith("btn:"):
                return "btn", tag[4:]
            if tag.startswith("stick:"):
                return "stick", tag[6:]
        return None, None

    def on_press(self, ev, mouse_button):
        kind, name = self.hit()
        if kind == "btn":
            key = next(k for n, _, _, k in BUTTONS if n == name)
            if mouse_button == 1:
                self.mouse_key = key
            else:
                self.latched ^= {key}
        elif kind == "stick":
            self.drag = (name, mouse_button, (ev.x, ev.y))
            self.move_stick(name, ev)
        self.refresh()

    def on_motion(self, ev):
        if self.drag is not None:
            self.move_stick(self.drag[0], ev)
            self.refresh()

    def on_release(self, ev, mouse_button):
        if mouse_button == 1:
            self.mouse_key = None
        if self.drag is not None and self.drag[1] == mouse_button:
            name, _, (sx, sy) = self.drag
            moved = abs(ev.x - sx) + abs(ev.y - sy) > 3
            if mouse_button == 3 and moved:
                self.stick_held.add(name)
            else:
                self.stick_held.discard(name)
                self.stick_pos[name] = (0, 0)
            self.drag = None
        self.refresh()

    def move_stick(self, name, ev):
        cx, cy = next(center for n, center, _ in STICKS if n == name)
        dx, dy = ev.x - cx, ev.y - cy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > STICK_R:
            dx, dy = dx * STICK_R / dist, dy * STICK_R / dist
        self.stick_pos[name] = (dx, dy)

    # ---------- キーボード ----------
    def on_key_press(self, ev):
        key = KEYSYMS.get(ev.keysym if len(ev.keysym) > 1 else ev.keysym.lower())
        if key is None:
            return None
        job = self.release_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)  # キーリピートなので離していない
        if key not in self.keys:
            self.keys.add(key)
            self.refresh()
        return "break"  # Tabでフォーカスが移らないように

    def on_key_release(self, ev):
        key = KEYSYMS.get(ev.keysym if len(ev.keysym) > 1 else ev.keysym.lower())
        if key is None:
            return None
        if key in self.release_jobs:
            self.root.after_cancel(self.release_jobs[key])
        self.release_jobs[key] = self.root.after(RELEASE_DELAY_MS, self.release_key, key)
        return "break"

    def release_key(self, key):
        self.release_jobs.pop(key, None)
        self.keys.discard(key)
        self.refresh()

    def on_focus_out(self, _ev):
        # 他のウィンドウに移ったらキーボード入力は全部離したことにする
        self.keys.clear()
        self.refresh()


def main():
    try:
        gamepad = vp.create_gamepad()
    except (PermissionError, evdev.uinput.UInputError) as ex:
        msg = f"仮想デバイスを作れません: {ex}\n\n初回は ./setup_uinput.sh を実行してください"
        print(msg, file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(vp.DEVICE_NAME, msg)
        except tk.TclError:
            pass
        sys.exit(1)

    root = tk.Tk()
    VirtualPS4GUI(root, gamepad)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        gamepad.close()


if __name__ == "__main__":
    main()
