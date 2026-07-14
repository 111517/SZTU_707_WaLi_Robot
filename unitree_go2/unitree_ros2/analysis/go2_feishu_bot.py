#!/usr/bin/env python3
"""
go2_feishu_bot.py — Go2 机器狗 飞书 Bot 控制通道

    通过飞书自定义机器人 Webhook 接收消息，转发给本地 HTTP API 执行。
    支持群聊和私聊，所有群成员均可发送指令。

使用方式：
    1. 在飞书群中添加自定义机器人 → Webhook URL 指向此服务的 /feishu_webhook
       （或者让本服务主动轮询飞书开放平台 API，但 Webhook 更简单）

    2. 群成员通过以下指令控制狗：
        /stand    站起来
        /sit      坐下
        /lie      趴下
        /stop     停下
        /hello    打招呼
        /dance    跳舞
        /heart    比心
        /walk     往前走
        /back     往后退
        /left     左转
        /right    右转
        /jump     跳跃
        /status   查询状态
        /photo    拍照
        /follow   跟随模式
        /cruise   巡航
        /patrol   巡逻
        /emergency 紧急停止

    3. 本服务监听 8002 端口，收到飞书 Webhook 后调用 localhost:8001 的 API。

依赖：
    pip3 install flask requests

启动：
    python3 go2_feishu_bot.py [--port 8002] [--api-url http://localhost:8001]
"""

import os
import sys
import json
import time
import base64
import argparse
import logging
import threading
from urllib.parse import urlparse, parse_qs

import requests
from flask import Flask, request, jsonify


# ============================================================
# 飞书 Bot 服务
# ============================================================

FEISHU_CMD_MAP = {
    "stand":      "站起来",
    "sit":        "坐下",
    "lie":        "趴下",
    "stop":       "停下",
    "hello":      "打招呼",
    "dance":      "跳舞",
    "heart":      "比心",
    "stretch":    "伸展",
    "walk":       "往前走",
    "back":       "往后退",
    "left":       "左转",
    "right":      "右转",
    "jump":       "跳跃",
    "status":     "查询状态",
    "photo":      "拍照",
    "recovery":   "恢复站立",
    "damping":    "阻尼卸力",
    "emergency":  "紧急停止",
    "follow":     "跟随模式",
    "cruise":     "巡航",
    "patrol":     "巡逻",
    "unfollow":   "停止跟随",
    "uncruise":   "停止巡航",
    "advance":    "前进指定距离",
    "move_to":    "移动到坐标",
    "help":       "帮助",
}

# 带参数指令
PARAM_CMDS = {
    "walk":   {"vx": 0.3, "desc": "/walk [速度]  例: /walk 0.5"},
    "back":   {"vx": -0.2, "desc": "/back [速度]  例: /back 0.3"},
    "left":   {"vyaw": 0.5, "desc": "/left [角速度]  例: /left 1.0"},
    "right":  {"vyaw": -0.5, "desc": "/right [角速度]  例: /right 1.0"},
    "advance": {"distance": 1.0, "speed": 0.3,
                "desc": "/advance <米> [速度]  例: /advance 2"},
    "jump":   {"height": 0.3, "desc": "/jump [高度]  例: /jump 0.5"},
}

CMD_ENDPOINT = {
    "stand":      "/stand",
    "sit":        "/sit",
    "lie":        "/lie",
    "stop":       "/stop",
    "hello":      ("/action", {"name": "hello"}),
    "dance":      ("/action", {"name": "dance"}),
    "heart":      ("/action", {"name": "heart"}),
    "stretch":    ("/action", {"name": "stretch"}),
    "walk":       ("/walk", None),
    "back":       ("/walk", {"vx": -0.2, "vy": 0, "vyaw": 0}),
    "left":       ("/turn", {"vyaw": 0.5}),
    "right":      ("/turn", {"vyaw": -0.5}),
    "jump":       ("/jump", None),
    "status":     ("/health", None),
    "photo":      ("/photo", None),
    "recovery":   "/recovery",
    "damping":    "/damping",
    "emergency":  "/emergency_stop",
    "follow":     "/follow",
    "cruise":     "/cruise",
    "patrol":     "/patrol",
    "unfollow":   "/stop_follow",
    "uncruise":   "/stop_cruise",
    "advance":    ("/advance", None),
    "move_to":    ("/move_to", None),
}


class FeishuBot:
    """飞书 Bot — 接收 Webhook，调用 Go2 API"""

    def __init__(self, api_base="http://localhost:8001"):
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self._log = logging.getLogger("feishu_bot")

    def _call_api(self, endpoint, payload=None, method="POST"):
        url = f"{self.api_base}{endpoint}"
        try:
            if method == "GET":
                resp = self.session.get(url, timeout=5)
            else:
                resp = self.session.post(url, json=payload or {},
                                         timeout=10)
            return True, resp.json()
        except requests.ConnectionError:
            return False, {"error": f"无法连接 Go2 API: {self.api_base}"}
        except Exception as e:
            return False, {"error": str(e)}

    def handle_command(self, cmd: str, args: list[str]) -> dict:
        """处理一条指令，返回格式化为飞书消息的回复"""
        cmd = cmd.lower().strip()

        if cmd == "help":
            lines = ["🤖 Go2 机器狗 飞书控制指令\n"]
            for c, desc in FEISHU_CMD_MAP.items():
                pinfo = PARAM_CMDS.get(c)
                if pinfo:
                    lines.append(f"  /{c} — {pinfo['desc']}")
                else:
                    lines.append(f"  /{c} — {desc}")
            return {"reply": "\n".join(lines)}

        entry = CMD_ENDPOINT.get(cmd)
        if entry is None:
            available = sorted(FEISHU_CMD_MAP.keys())
            return {"reply": f"❌ 未知指令: /{cmd}\n可用指令: /help 查看全部"}

        # 解析参数
        endpoint = entry
        extra_payload = {}

        if isinstance(entry, tuple):
            endpoint, extra_payload = entry

        if endpoint == "/walk":
            if extra_payload is None:
                extra_payload = {}
            if args:
                extra_payload["vx"] = float(args[0])

        elif endpoint == "/turn":
            if extra_payload is None:
                extra_payload = {}
            if args:
                extra_payload["vyaw"] = float(args[0])

        elif endpoint == "/jump":
            if args:
                extra_payload = {"height": float(args[0])}

        elif endpoint == "/advance":
            extra_payload = {"distance": 1.0, "speed": 0.3}
            if args:
                extra_payload["distance"] = float(args[0])
            if len(args) > 1:
                extra_payload["speed"] = float(args[1])

        # 调用 API
        method = "GET" if endpoint == "/health" else "POST"
        ok, result = self._call_api(endpoint, extra_payload, method)

        if not ok:
            return {"reply": f"❌ 连接失败: {result.get('error', '服务不可达')}"}

        # 格式化结果
        if cmd == "status":
            s = result
            bat = s.get("battery", {})
            mode = s.get("mode", {}).get("name", "?")
            pos = s.get("position", {})
            obs = s.get("obstacles", {})
            reply = (
                f"📊 Go2 状态\n"
                f"模式: {mode}\n"
                f"电量: {bat.get('soc', '?')}% ({bat.get('voltage_v', '?')}V)\n"
                f"位置: ({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f})\n"
                f"姿态: roll={s.get('attitude',{}).get('roll',0):.1f}° pitch={s.get('attitude',{}).get('pitch',0):.1f}°\n"
                f"障碍: 前{obs.get('front',0):.2f}m 左{obs.get('left',0):.2f}m 右{obs.get('right',0):.2f}m\n"
                f"跟随: {'🟢' if s.get('following') else '⚪'}\n"
                f"巡航: {'🟢' if s.get('cruising') else '⚪'}"
            )
            return {"reply": reply}

        if cmd == "photo":
            if result.get("ok"):
                img_b64 = result.get("image_base64", "")
                return {
                    "reply": "📸 拍照成功",
                    "image_base64": img_b64,
                }
            return {"reply": "❌ 拍照失败"}

        if isinstance(result, dict):
            if result.get("ok") or result.get("status") == "ok":
                desc = FEISHU_CMD_MAP.get(cmd, cmd)
                return {"reply": f"✅ {desc} 成功"}
            # 检查 "mode" 字段作为 ok 信号
            if "mode" in result:
                desc = FEISHU_CMD_MAP.get(cmd, cmd)
                return {"reply": f"✅ {desc} 成功"}

        return {"reply": f"❌ 操作失败: {json.dumps(result, ensure_ascii=False)[:200]}"}


# ============================================================
# Flask App
# ============================================================

def create_app(bot: FeishuBot):
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    @app.route("/feishu_webhook", methods=["POST"])
    def feishu_webhook():
        """
        飞书自定义机器人 Webhook 入口。
        飞书机器人发送 POST 请求到此端点。
        """
        data = request.get_json(silent=True) or {}

        # 兼容多种飞书消息格式
        text = data.get("text", data.get("content", "")).strip()
        # 兼容飞书卡片消息格式
        if not text and "header" in data:
            text = data.get("header", {}).get("title", "")

        if not text:
            return jsonify({"reply": "请发送指令，例如 /stand"})

        # 解析指令
        parts = text.strip().split()
        cmd = parts[0].lstrip("/") if parts else ""
        args = parts[1:] if len(parts) > 1 else []

        if not cmd:
            return jsonify({"reply": "请发送指令，例如 /stand"})

        bot._log.info(f"收到指令: /{cmd} {' '.join(args)}")
        reply = bot.handle_command(cmd, args)
        return jsonify(reply)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "service": "Go2 Feishu Bot",
            "api_base": bot.api_base,
            "status": "running",
        })

    @app.route("/", methods=["GET"])
    def index():
        cmds = "/" + ", /".join(sorted(FEISHU_CMD_MAP.keys()))
        return jsonify({
            "service": "Go2 Feishu Bot",
            "webhook": "POST /feishu_webhook",
            "commands": cmds,
        })

    return app


def main():
    parser = argparse.ArgumentParser(description="Go2 飞书 Bot 控制通道")
    parser.add_argument("--port", type=int, default=8002,
                        help="监听端口 (默认: 8002)")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--api-url", type=str,
                        default="http://localhost:8001",
                        help="Go2 HTTP API 地址 (默认: http://localhost:8001)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    bot = FeishuBot(api_base=args.api_url)
    app = create_app(bot)

    print(f"\n🕶️ Go2 飞书 Bot 启动")
    print(f"   ➜ 飞书 Webhook: POST http://{args.host}:{args.port}/feishu_webhook")
    print(f"   ➜ 后端 API:     {args.api_url}")
    print(f"   ➜ 可用指令:     /help 查看全部")
    print(f"\n   在飞书自定义机器人中配置 Webhook 指向此地址即可使用。")
    print(f"   所有群成员均可在群内发送 /walk 等指令控制机器狗。\n")

    app.run(host=args.host, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()