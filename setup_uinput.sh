#!/bin/bash
# ログイン中のユーザーが sudo なしで /dev/uinput を使えるようにする（初回のみ）
# virtual_ps4_gui.py を普通のユーザーで起動するために必要
set -e

RULE=/etc/udev/rules.d/60-uinput.rules

echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' | sudo tee "$RULE" > /dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --name-match=uinput

echo "$RULE を作成しました"
getfacl -p /dev/uinput 2>/dev/null | grep "user:$USER" || echo "反映されない場合は一度ログアウトしてください"
