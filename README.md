# **virtual_ps4**

実機の PS4 コントローラー（DS4）がなくても、`joy_node` から PS4 コントローラーとして認識される仮想ゲームパッドを作るツールです。
uinput で OS の入力デバイスを作るので、`joy_node` から先は実機とまったく同じ経路を通ります。軸・ボタンの番号も実機の DS4 と同じです。

## 動作環境

| 項目 | 内容 |
|:---|:---|
| OS | Ubuntu 24.04 LTS |
| ROS | ROS 2 Jazzy（`ros-jazzy-joy`） |
| Python | `python3-evdev`、GUI 版は `python3-tk` |

## セットアップ

```bash
sudo apt install python3-evdev python3-tk ros-jazzy-joy

# GUI 版を sudo なしで使う場合のみ（初回のみ）
./setup_uinput.sh
```

`setup_uinput.sh` は、ログイン中のユーザーが `/dev/uinput` を使えるようにする udev ルール（`/etc/udev/rules.d/60-uinput.rules`）を追加します。

## 使い方

### GUI 版

```bash
python3 virtual_ps4_gui.py
```

| 操作 | 動作 |
|:---|:---|
| 左クリック | ボタンを押す ／ スティックをドラッグ（離すと中央に戻る） |
| 右クリック | ボタンを押しっぱなしにする（もう一度で解除） |
| 右ドラッグ | スティックをその位置で止める（右クリックだけで中央に戻す） |
| キーボード | 下の割り当てと同じ（ウィンドウを選択しているときだけ） |

画面下に `/joy` で届く axes / buttons の値が表示されます。

### キーボード版

```bash
sudo python3 virtual_ps4.py
```

キーボードを PC 全体から読むため、`sudo` が必要です。他のウィンドウで打ったキーも入力になる点に注意してください。

### 動作確認

```bash
ros2 run joy joy_enumerate_devices   # Virtual PS4 Controller が出れば OK
ros2 run joy joy_node
ros2 topic echo /joy
```

## キー割り当て

| キー | 入力 | joy の番号 |
|:---|:---|:---|
| W / A / S / D | 左スティック | `axes[0]`, `axes[1]` |
| I / J / K / L | 右スティック | `axes[3]`, `axes[4]` |
| 矢印キー | 十字キー | `axes[6]`, `axes[7]` |
| 2 / 3 / 4 / 1 | × / ○ / △ / □ | `buttons[0]`〜`[3]` |
| Q / E | L1 / R1 | `buttons[4]`, `[5]` |
| Z / C | L2 / R2 | `buttons[6]`, `[7]`（`axes[2]`, `[5]` も連動） |
| Tab / Enter | SHARE / OPTIONS | `buttons[8]`, `[9]` |
| P | PS | `buttons[10]` |
| F / H | L3 / R3 | `buttons[11]`, `[12]` |
| 左 Shift（押しながら） | スティックを半分だけ倒す | - |

## 注意

- 実機の DS4 も同時につなぐと、`joy_node` は先に見つけた方を開きます。仮想パッドを使うときは実機を外してください。
- Docker の中で使う場合は、`/dev/uinput` と `/dev/input` をコンテナに渡す必要があります。
