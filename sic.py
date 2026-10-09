import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import time
import threading
import os
import re
import logging
import csv
import io
import random
from datetime import datetime, timedelta, timezone
from collections import Counter
from flask import Flask, jsonify

# ============================================================================
# CẤU HÌNH
# ============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8844628964:AAE3Wm5VUQIRqhBuwonAFRuuW5eHwPIczIw")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7564889663").split(",") if x.strip()]

PORT = int(os.getenv("PORT", 8080))
PREDICT_API = os.getenv("PREDICT_API", "https://sicsun-g34z.onrender.com/api/sicbo/sunwin")
HISTORY_API = os.getenv("HISTORY_API", "https://sicsun-g34z.onrender.com/api/sicsun/history")

DATA_FILE = "users.json"
STATE_FILE = "state.json"
MAX_HISTORY = 20
AUTO_INTERVAL = 5
VN_TZ = timezone(timedelta(hours=7))

STATUS_ACTIVE = "🟢 Hoạt động"
STATUS_BLOCKED = "🔴 Đã chặn bot"
PENDING = "⏳ Đang chờ"
WIN = "✔️ Thắng"
LOSE = "❌ Thua"
SKIPPED = "⏭ Bỏ lỡ"
UNKNOWN = "➖ Không xác định"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("sicbo-bot")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ============================================================================
# EMOJI PREMIUM
# ============================================================================
CE = {
    "eyes":   ("5210956306952758910", "👀"),
    "smile":  ("5461117441612462242", "🙂"),
    "zap":    ("5456140674028019486", "⚡️"),
    "stop":   ("5260293700088511294", "⛔️"),
    "block":  ("5240241223632954241", "🚫"),
    "excl":   ("5274099962655816924", "❗️"),
    "globe":  ("5447410659077661506", "🌐"),
    "chat":   ("5443038326535759644", "💬"),
    "chart":  ("5231200819986047254", "📊"),
    "up":     ("5449683594425410231", "🔼"),
    "dn":     ("5447183459602669338", "🔽"),
    "graph":  ("5244837092042750681", "📈"),
    "down":   ("5246762912428603768", "📉"),
    "ok":     ("5206607081334906820", "✔️"),
    "x":      ("5210952531676504517", "❌"),
    "bell":   ("5458603043203327669", "🔔"),
    "pin":    ("5397782960512444700", "📌"),
    "cash":   ("5409048419211682843", "💵"),
    "fly":    ("5233326571099534068", "💸"),
    "play":   ("5264919878082509254", "▶️"),
    "red":    ("5411225014148014586", "🔴"),
    "green":  ("5416081784641168838", "🟢"),
    "right":  ("5416117059207572332", "➡️"),
    "fire":   ("5424972470023104089", "🔥"),
    "boom":   ("5276032951342088188", "💥"),
    "mega":   ("5424818078833715060", "📣"),
    "shield": ("5251203410396458957", "🛡"),
    "info":   ("5334544901428229844", "ℹ️"),
    "like":   ("5337080053119336309", "👍"),
    "pause":  ("5359543311897998264", "⏸"),
    "100":    ("5341498088408234504", "💯"),
    "sync":   ("5375338737028841420", "🔄"),
    "top":    ("5415655814079723871", "🔝"),
    "new":    ("5382357040008021292", "🆕"),
    "plus":   ("5397916757333654639", "➕"),
    "gem":    ("5427168083074628963", "💎"),
    "star":   ("5438496463044752972", "⭐️"),
    "spark":  ("5325547803936572038", "✨"),
    "crown":  ("5217822164362739968", "👑"),
    "trash":  ("5445267414562389170", "🗑"),
    "lock":   ("5296369303661067030", "🔒"),
    "gear":   ("5341715473882955310", "⚙️"),
    "game":   ("5361741454685256344", "🎮"),
    "hour":   ("5386367538735104399", "⌛"),
    "idea":   ("5422439311196834318", "💡"),
    "edit":   ("5395444784611480792", "✏️"),
    "alert":  ("5395695537687123235", "🚨"),
    "home":   ("5416041192905265756", "🏠"),
    "flag":   ("5460755126761312667", "🚩"),
    "party":  ("5461151367559141950", "🎉"),
    "warn":   ("5447644880824181073", "⚠️"),
    "q":      ("5436113877181941026", "❓"),
    "joy":    ("5370953476635368811", "😂"),
    "think2": ("5370724846936267183", "🤔"),
    "cool2":  ("5373141891321699086", "😎"),
    "sob":    ("5370646412243510708", "😭"),
}

_VS16 = "\ufe0f"
_BY_EMOJI = {e.replace(_VS16, ""): i for i, e in CE.values()}
_PATTERN = re.compile(
    "(?:" + "|".join(re.escape(k) for k in sorted(_BY_EMOJI, key=len, reverse=True)) + ")" + _VS16 + "?"
)


def ce(key: str) -> str:
    emoji_id, fallback = CE.get(key, ("", "❓"))
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def premium(text: str) -> str:
    if not text or "<tg-emoji" in text:
        return text

    def repl(m):
        base = m.group(0).replace(_VS16, "")
        return f'<tg-emoji emoji-id="{_BY_EMOJI[base]}">{m.group(0)}</tg-emoji>'

    return _PATTERN.sub(repl, text)


def leading_emoji(text: str):
    m = _PATTERN.match(text)
    if not m:
        return None, text
    base = m.group(0).replace(_VS16, "")
    return _BY_EMOJI[base], text[m.end():].lstrip()


def btn(text: str, **kwargs):
    emoji_id, rest = leading_emoji(text)
    if emoji_id and rest:
        kwargs["api_kwargs"] = {"icon_custom_emoji_id": emoji_id}
        text = rest
    return InlineKeyboardButton(text, **kwargs)


# ============================================================================
# FLASK HEALTH CHECK
# ============================================================================
app = Flask(__name__)
_start_time = time.time()

@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "service": "Sicbo Sunwin Bot",
        "uptime": int(time.time() - _start_time),
        "auto_chats": len([c for c in state["auto"].values() if c.get("enabled")]),
        "users": len(state["users"]),
        "last_session": _last_session,
        "last_update": _last_update_time,
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ============================================================================
# STORAGE
# ============================================================================
state = {
    "auto": {},       # { chat_id: { enabled, last_prediction, last_session, ... } }
    "users": {},      # { user_id: { name, username, joined, last_active, banned } }
    "history": {},    # { chat_id: [ {session, prediction, confidence, top3, correct, actual, time} ] }
    "stats": {
        "total_predictions": 0,
        "correct": 0,
        "streak": {"type": None, "count": 0},
    }
}

_last_session = None
_last_prediction_data = None
_last_history_map = {}   # session -> result ('tai'/'xiu')
_last_update_time = None


def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Load {path} error: {e}")
    return default


def save_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"Save {path} error: {e}")


_save_lock = threading.Lock()

def save_state():
    with _save_lock:
        save_json(STATE_FILE, state)


def load_state():
    global state
    loaded = load_json(STATE_FILE, {})
    if loaded:
        state["auto"] = {int(k): v for k, v in loaded.get("auto", {}).items()}
        state["users"] = {int(k): v for k, v in loaded.get("users", {}).items()}
        state["history"] = {int(k): v for k, v in loaded.get("history", {}).items()}
        state["stats"] = loaded.get("stats", state["stats"])
    logger.info(f"Loaded: {len(state['auto'])} auto, {len(state['users'])} users")


def is_admin(user_id):
    return int(user_id) in ADMIN_IDS


def is_banned(chat_id):
    return state["users"].get(chat_id, {}).get("banned", False)


# ============================================================================
# API
# ============================================================================
def fetch_predict():
    """Lấy dự đoán từ API."""
    try:
        r = requests.get(PREDICT_API, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"Predict API error: {e}")
    return None


def fetch_history():
    """Lấy lịch sử từ API."""
    try:
        r = requests.get(HISTORY_API, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"History API error: {e}")
    return None


# ============================================================================
# FORMAT
# ============================================================================
def format_prediction(data, history_list):
    next_session = data.get("phien_hien_tai", "?")
    du_doan = (data.get("du_doan") or "").upper()
    do_tin_cay = data.get("do_tin_cay", "0%")
    top3 = data.get("du_doan_vi", "?")
    top5 = data.get("du_doan_top5", "?")
    accuracy = data.get("accuracy", "N/A")

    emoji_tx = ce("red") if "TÀI" in du_doan else ce("green")

    # Chuỗi + trạng thái
    streak_text = "Chưa có chuỗi"
    status_text = "⏳ Chờ kết quả"

    if history_list:
        last = history_list[-1]
        if last.get("correct") is True:
            status_text = f"{ce('ok')} <b>THẮNG</b>"
        elif last.get("correct") is False:
            status_text = f"{ce('x')} <b>THUA</b>"

        wins = 0
        losses = 0
        for h in reversed(history_list):
            if h.get("correct") is True:
                if losses > 0: break
                wins += 1
            elif h.get("correct") is False:
                if wins > 0: break
                losses += 1
            else:
                break
        if wins > 0:
            streak_text = f"{ce('fire')} Thắng <b>{wins}</b>"
        elif losses > 0:
            streak_text = f"{ce('warn')} Thua <b>{losses}</b>"

    # Đếm W/L tổng
    total = len([h for h in history_list if h.get("correct") is not None])
    wins_total = len([h for h in history_list if h.get("correct") is True])

    return (
        f"{ce('spark')} <b>DỰ ĐOÁN PHIÊN {next_session}</b>\n\n"
        f"{emoji_tx} <b>{du_doan}</b>\n"
        f"{ce('chart')} Độ tin cậy: <b>{do_tin_cay}</b>\n"
        f"{ce('gem')} Top 3 vị: <b>[{top3}]</b>\n"
        f"{ce('top')} Top 5 vị: <b>[{top5}]</b>\n\n"
        f"{ce('info')} {status_text}\n"
        f"{streak_text}\n"
        f"{ce('graph')} Accuracy bot: <b>{accuracy}</b>\n"
        f"{ce('100')} Lịch sử: <b>{wins_total}W/{total - wins_total}L</b>\n\n"
        f"{ce('hour')} {datetime.now(VN_TZ).strftime('%H:%M:%S')}"
    )


def format_history(history_list):
    if not history_list:
        return f"{ce('info')} Chưa có lịch sử"

    lines = [f"{ce('info')} <b>LỊCH SỬ DỰ ĐOÁN ({len(history_list)})</b>\n"]
    for h in reversed(history_list[-MAX_HISTORY:]):
        session = h.get("session", "?")
        pred = (h.get("prediction") or "?").upper()
        actual = (h.get("actual") or "?").upper()
        correct = h.get("correct")

        emoji_tx = ce("red") if "TÀI" in pred else ce("green")
        if correct is True:
            status = ce("ok")
        elif correct is False:
            status = ce("x")
        else:
            status = "⏳"

        # Dòng ngắn
        lines.append(f"{status} #{session} | {emoji_tx} {pred} → {actual}")

    # Thống kê
    tested = [h for h in history_list if h.get("correct") is not None]
    wins = len([h for h in tested if h.get("correct") is True])
    rate = (wins / len(tested) * 100) if tested else 0

    lines.append(f"\n{ce('chart')} Tỷ lệ: <b>{rate:.1f}%</b> ({wins}/{len(tested)})")

    return "\n".join(lines)


# ============================================================================
# BACKGROUND LOOP
# ============================================================================
def auto_loop():
    global _last_session, _last_prediction_data, _last_update_time, _last_history_map
    logger.info("Auto loop started")

    while True:
        try:
            # 1. Fetch dự đoán
            pred_data = fetch_predict()
            _last_update_time = datetime.now(VN_TZ).isoformat()

            # 2. Fetch lịch sử để đối chiếu
            hist_data = fetch_history()
            if hist_data and isinstance(hist_data, list):
                # Dedupe + build map
                new_map = {}
                for item in hist_data:
                    session = item.get("session")
                    if session and session not in new_map:
                        new_map[session] = item.get("result", "").lower()
                _last_history_map = new_map

            # 3. Đối chiếu dự đoán cũ với kết quả mới
            if _last_history_map:
                for chat_id, hist_list in state["history"].items():
                    changed = False
                    for entry in hist_list:
                        if entry.get("correct") is None:
                            sess = entry.get("session")
                            result = _last_history_map.get(sess)
                            if result in ("tai", "xiu"):
                                actual = "TÀI" if result == "tai" else "XỈU"
                                entry["actual"] = actual
                                pred_upper = (entry.get("prediction") or "").upper()
                                entry["correct"] = (pred_upper == actual)
                                changed = True
                    if changed:
                        save_state()

            # 4. Push dự đoán mới nếu có phiên mới
            if pred_data:
                current_session = pred_data.get("phien_hien_tai")
                _last_prediction_data = pred_data

                if current_session != _last_session:
                    _last_session = current_session

                    for chat_id_str, cfg in list(state["auto"].items()):
                        if not cfg.get("enabled"):
                            continue

                        chat_id = int(chat_id_str)
                        history_list = state["history"].get(chat_id, [])

                        # Thêm dự đoán mới
                        new_entry = {
                            "session": current_session,
                            "prediction": pred_data.get("du_doan", "?"),
                            "confidence": pred_data.get("do_tin_cay", "0%"),
                            "top3": pred_data.get("du_doan_vi", "?"),
                            "correct": None,
                            "actual": None,
                            "time": datetime.now(VN_TZ).isoformat(),
                        }
                        history_list.append(new_entry)
                        if len(history_list) > MAX_HISTORY:
                            history_list = history_list[-MAX_HISTORY:]
                        state["history"][chat_id] = history_list

                        # Cập nhật stats
                        state["stats"]["total_predictions"] += 1

                        # Gửi tin
                        try:
                            text = format_prediction(pred_data, history_list)
                            bot.send_message(chat_id, text, parse_mode="HTML")
                        except Exception as e:
                            logger.error(f"Send {chat_id} failed: {e}")

                    save_state()

            time.sleep(AUTO_INTERVAL)

        except Exception as e:
            logger.error(f"Loop error: {e}")
            time.sleep(AUTO_INTERVAL)


# ============================================================================
# HELPERS
# ============================================================================
def register_user(message):
    user = message.from_user
    chat = message.chat
    now = int(time.time())

    info = state["users"].get(user.id)
    if info is None:
        state["users"][user.id] = {
            "id": user.id,
            "name": user.full_name or "Không rõ",
            "username": f"@{user.username}" if user.username else "Không có",
            "status": STATUS_ACTIVE,
            "joined": now,
            "last_active": now,
            "banned": False,
        }
    else:
        info["last_active"] = now
    save_state()


def safe_edit(call, text, reply_markup=None):
    try:
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.error(f"edit error: {e}")


# ============================================================================
# KEYBOARDS
# ============================================================================
def home_kb(user_id):
    kb = [
        [btn("🎮 DỰ ĐOÁN NGAY", callback_data="predict_now")],
        [btn("🚀 BẬT AUTO DỰ ĐOÁN", callback_data="auto_on")],
        [btn("🛑 DỪNG AUTO", callback_data="auto_off")],
        [btn("📜 LỊCH SỬ", callback_data="menu_history")],
        [btn("📊 THỐNG KÊ", callback_data="menu_stats")],
        [btn("🛠 HỖ TRỢ ADMIN", callback_data="menu_support")],
    ]
    if is_admin(user_id):
        kb.append([btn("👑 ADMIN PANEL", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)


def admin_kb():
    kb = [
        [btn("📊 Thống Kê", callback_data="admin_stats")],
        [btn("👥 Danh Sách User", callback_data="admin_users_0")],
        [btn("🚫 Danh Sách Ban", callback_data="admin_banned")],
        [btn("📥 Xuất CSV", callback_data="admin_export")],
        [btn("📢 Broadcast", callback_data="admin_guide_broadcast")],
        [btn("🏠 Trang Chủ", callback_data="menu_home")],
    ]
    return InlineKeyboardMarkup(kb)


# ============================================================================
# COMMAND HANDLERS
# ============================================================================
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if not is_admin(message.from_user.id) and is_banned(message.from_user.id):
        bot.reply_to(message, f"{ce('block')} Bạn đã bị chặn.", parse_mode="HTML")
        return
    register_user(message)

    user = message.from_user
    text = (
        f"{ce('spark')} <b>SICBO SUNWIN BOT</b>\n\n"
        f"{ce('info')} Xin chào <b>{user.full_name}</b>\n"
        f"{ce('game')} Bot dự đoán Tài/Xỉu Sunwin Sicbo\n\n"
        f"{ce('right')} Chọn chức năng bên dưới:"
    )
    bot.send_message(message.chat.id, text, reply_markup=home_kb(user.id), parse_mode="HTML")


@bot.message_handler(commands=["help"])
def cmd_help(message):
    cmd_start(message)


@bot.message_handler(commands=["auto"])
def cmd_auto(message):
    register_user(message)
    chat_id = message.chat.id
    state["auto"][chat_id] = {
        "enabled": True,
        "chat_type": message.chat.type,
        "added_by": message.from_user.id,
        "added_at": int(time.time()),
    }
    save_state()
    bot.send_message(chat_id,
        f"{ce('play')} <b>Đã BẬT auto dự đoán</b>\n"
        f"{ce('info')} Chat ID: <code>{chat_id}</code>\n"
        f"{ce('hour')} Push mỗi khi có phiên mới\n"
        f"{ce('stop')} Gõ /stop để dừng",
        parse_mode="HTML")


@bot.message_handler(commands=["stop"])
def cmd_stop(message):
    chat_id = message.chat.id
    if chat_id in state["auto"]:
        state["auto"][chat_id]["enabled"] = False
        save_state()
        bot.send_message(chat_id,
            f"{ce('stop')} <b>Đã DỪNG auto</b>",
            parse_mode="HTML")
    else:
        bot.send_message(chat_id, f"{ce('warn')} Chat chưa bật auto", parse_mode="HTML")


@bot.message_handler(commands=["status"])
def cmd_status(message):
    chat_id = message.chat.id
    cfg = state["auto"].get(chat_id)
    if cfg:
        status = "BẬT" if cfg.get("enabled") else "TẮT"
        emoji = ce("ok") if cfg.get("enabled") else ce("x")
        text = (
            f"{ce('info')} <b>TRẠNG THÁI</b>\n\n"
            f"{emoji} Auto: <b>{status}</b>\n"
            f"{ce('pin')} Chat ID: <code>{chat_id}</code>"
        )
    else:
        text = f"{ce('x')} Auto chưa bật. Gõ /auto"
    bot.send_message(chat_id, text, parse_mode="HTML")


@bot.message_handler(commands=["history"])
def cmd_history(message):
    history_list = state["history"].get(message.chat.id, [])
    bot.send_message(message.chat.id, format_history(history_list), parse_mode="HTML")


@bot.message_handler(commands=["predict"])
def cmd_predict(message):
    data = _last_prediction_data or fetch_predict()
    if not data:
        bot.send_message(message.chat.id, f"{ce('warn')} Không lấy được dự đoán", parse_mode="HTML")
        return
    history_list = state["history"].get(message.chat.id, [])
    bot.send_message(message.chat.id, format_prediction(data, history_list), parse_mode="HTML")


@bot.message_handler(commands=["admin"])
def cmd_admin(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, f"{ce('lock')} Không có quyền", parse_mode="HTML")
        return
    bot.send_message(message.chat.id,
        f"{ce('crown')} <b>ADMIN PANEL</b>",
        reply_markup=admin_kb(),
        parse_mode="HTML")


@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(message.chat.id, f"{ce('warn')} Dùng: /broadcast &lt;nội dung&gt;", parse_mode="HTML")
        return

    success, fail = 0, 0
    for chat_id, cfg in state["auto"].items():
        if cfg.get("enabled"):
            try:
                bot.send_message(chat_id, f"{ce('mega')} <b>THÔNG BÁO</b>\n\n{html.escape(text)}", parse_mode="HTML")
                success += 1
            except Exception:
                fail += 1

    bot.send_message(message.chat.id,
        f"{ce('ok')} Gửi: {success} | Lỗi: {fail}",
        parse_mode="HTML")


# ============================================================================
# CALLBACK HANDLERS
# ============================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    if is_banned(chat_id) and not is_admin(user_id):
        bot.answer_callback_query(call.id, "🚫 Bạn đã bị chặn", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    # ---- HOME ----
    if data == "menu_home":
        text = (
            f"{ce('spark')} <b>SICBO SUNWIN BOT</b>\n\n"
            f"{ce('right')} Chọn chức năng:"
        )
        safe_edit(call, text, home_kb(user_id))
        return

    # ---- PREDICT NGAY ----
    if data == "predict_now":
        pred = fetch_predict()
        if not pred:
            bot.send_message(chat_id, f"{ce('warn')} Không lấy được dự đoán", parse_mode="HTML")
            return
        history_list = state["history"].get(chat_id, [])
        bot.send_message(chat_id, format_prediction(pred, history_list), parse_mode="HTML")
        return

    # ---- AUTO ON ----
    if data == "auto_on":
        state["auto"][chat_id] = {
            "enabled": True,
            "chat_type": call.message.chat.type,
            "added_by": user_id,
            "added_at": int(time.time()),
        }
        save_state()
        bot.send_message(chat_id,
            f"{ce('play')} <b>Đã BẬT auto dự đoán</b>\n"
            f"{ce('stop')} Gõ /stop để dừng",
            parse_mode="HTML")
        return

    # ---- AUTO OFF ----
    if data == "auto_off":
        if chat_id in state["auto"]:
            state["auto"][chat_id]["enabled"] = False
            save_state()
        bot.send_message(chat_id, f"{ce('stop')} <b>Đã DỪNG auto</b>", parse_mode="HTML")
        return

    # ---- MENU HISTORY ----
    if data == "menu_history":
        history_list = state["history"].get(chat_id, [])
        kb = [
            [btn("🔄 Làm Mới", callback_data="menu_history")],
            [btn("🏠 Trang Chủ", callback_data="menu_home")],
        ]
        safe_edit(call, format_history(history_list), InlineKeyboardMarkup(kb))
        return

    # ---- MENU STATS ----
    if data == "menu_stats":
        history_list = state["history"].get(chat_id, [])
        tested = [h for h in history_list if h.get("correct") is not None]
        wins = len([h for h in tested if h.get("correct") is True])
        rate = (wins / len(tested) * 100) if tested else 0

        text = (
            f"{ce('chart')} <b>THỐNG KÊ CỦA BẠN</b>\n\n"
            f"{ce('100')} Tổng dự đoán: <b>{len(history_list)}</b>\n"
            f"{ce('ok')} Đúng: <b>{wins}</b>\n"
            f"{ce('x')} Sai: <b>{len(tested) - wins}</b>\n"
            f"{ce('graph')} Tỷ lệ: <b>{rate:.1f}%</b>"
        )
        kb = [
            [btn("🔄 Làm Mới", callback_data="menu_stats")],
            [btn("🏠 Trang Chủ", callback_data="menu_home")],
        ]
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return

    # ---- SUPPORT ----
    if data == "menu_support":
        text = (
            f"{ce('chat')} <b>HỖ TRỢ</b>\n\n"
            f"Liên hệ admin để được hỗ trợ."
        )
        kb = [[btn("🏠 Trang Chủ", callback_data="menu_home")]]
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return

    # ---- ADMIN PANEL ----
    if data == "admin_panel":
        if not is_admin(user_id):
            return
        text = (
            f"{ce('crown')} <b>ADMIN PANEL</b>\n\n"
            f"{ce('eyes')} Users: <b>{len(state['users'])}</b>\n"
            f"{ce('play')} Auto: <b>{len([c for c in state['auto'].values() if c.get('enabled')])}</b>\n"
            f"{ce('chart')} Total predictions: <b>{state['stats']['total_predictions']}</b>"
        )
        safe_edit(call, text, admin_kb())
        return

    if data == "admin_stats":
        if not is_admin(user_id):
            return
        total_pred = state["stats"]["total_predictions"]
        # Tính W/L từ tất cả history
        all_tested = []
        for hl in state["history"].values():
            all_tested.extend([h for h in hl if h.get("correct") is not None])
        wins = len([h for h in all_tested if h.get("correct") is True])
        rate = (wins / len(all_tested) * 100) if all_tested else 0

        text = (
            f"{ce('chart')} <b>THỐNG KÊ HỆ THỐNG</b>\n\n"
            f"{ce('eyes')} Users: <b>{len(state['users'])}</b>\n"
            f"{ce('play')} Auto chats: <b>{len([c for c in state['auto'].values() if c.get('enabled')])}</b>\n"
            f"{ce('100')} Total: <b>{total_pred}</b>\n"
            f"{ce('ok')} Wins: <b>{wins}</b> / <b>{len(all_tested)}</b>\n"
            f"{ce('graph')} Rate: <b>{rate:.1f}%</b>"
        )
        kb = [
            [btn("🔄 Làm Mới", callback_data="admin_stats")],
            [btn("🔙 Admin", callback_data="admin_panel")],
        ]
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return

    if data.startswith("admin_users_"):
        if not is_admin(user_id):
            return
        try:
            page = int(data.rsplit("_", 1)[1])
        except ValueError:
            page = 0
        users = list(state["users"].values())
        per_page = 15
        total_pages = max(1, (len(users) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        chunk = users[page * per_page:(page + 1) * per_page]

        body = ""
        for i, u in enumerate(chunk, page * per_page + 1):
            ban_tag = " 🚫" if u.get("banned") else ""
            body += f"{i}. {html.escape(u.get('name', ''))} (<code>{u['id']}</code>){ban_tag}\n"

        text = f"{ce('eyes')} <b>USERS (trang {page + 1}/{total_pages})</b>\n\n{body or 'Trống'}"
        nav = []
        if page > 0:
            nav.append(btn("⬅️", callback_data=f"admin_users_{page - 1}"))
        if page < total_pages - 1:
            nav.append(btn("➡️", callback_data=f"admin_users_{page + 1}"))
        kb = []
        if nav:
            kb.append(nav)
        kb.append([btn("🔙 Admin", callback_data="admin_panel")])
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return

    if data == "admin_banned":
        if not is_admin(user_id):
            return
        banned = [u for u in state["users"].values() if u.get("banned")]
        body = "\n".join([f"• {html.escape(u.get('name', ''))} (<code>{u['id']}</code>)" for u in banned]) or "Không có ai"
        text = f"{ce('block')} <b>DANH SÁCH BAN</b>\n\n{body}"
        kb = [[btn("🔙 Admin", callback_data="admin_panel")]]
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return

    if data == "admin_export":
        if not is_admin(user_id):
            return
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "name", "username", "status", "banned", "joined", "last_active"])
        for uid, u in state["users"].items():
            w.writerow([
                uid, u.get("name", ""), u.get("username", ""),
                u.get("status", ""), "yes" if u.get("banned") else "no",
                u.get("joined", ""), u.get("last_active", "")
            ])
        data_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
        bot.send_document(chat_id, data_bytes, visible_file_name="users.csv")
        return

    if data == "admin_guide_broadcast":
        if not is_admin(user_id):
            return
        text = (
            f"{ce('mega')} <b>HƯỚNG DẪN BROADCAST</b>\n\n"
            f"Gõ: <code>/broadcast &lt;nội dung&gt;</code>\n"
            f"VD: <code>/broadcast Bot vừa nâng cấp!</code>"
        )
        kb = [[btn("🔙 Admin", callback_data="admin_panel")]]
        safe_edit(call, text, InlineKeyboardMarkup(kb))
        return


# ============================================================================
# ADMIN TEXT COMMANDS
# ============================================================================
@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text and not m.text.startswith("/"))
def admin_text(message):
    text = message.text.strip()
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("ban", "unban"):
        if not arg:
            bot.send_message(message.chat.id, f"Dùng: <code>{cmd} &lt;id&gt;</code>", parse_mode="HTML")
            return
        try:
            target = int(arg.split()[0])
        except ValueError:
            bot.send_message(message.chat.id, "ID không hợp lệ", parse_mode="HTML")
            return
        if target not in state["users"]:
            bot.send_message(message.chat.id, "User không tồn tại", parse_mode="HTML")
            return
        if target in ADMIN_IDS and cmd == "ban":
            bot.send_message(message.chat.id, "Không thể ban admin", parse_mode="HTML")
            return
        state["users"][target]["banned"] = (cmd == "ban")
        if cmd == "ban":
            state["auto"].pop(target, None)
        save_state()
        bot.send_message(message.chat.id,
            f"{ce('ok')} Đã {'ban' if cmd == 'ban' else 'unban'} <code>{target}</code>",
            parse_mode="HTML")
        return

    if cmd in ("stats", "thongke"):
        all_tested = []
        for hl in state["history"].values():
            all_tested.extend([h for h in hl if h.get("correct") is not None])
        wins = len([h for h in all_tested if h.get("correct") is True])
        rate = (wins / len(all_tested) * 100) if all_tested else 0
        bot.send_message(message.chat.id,
            f"{ce('chart')} Users: <b>{len(state['users'])}</b>\n"
            f"{ce('play')} Auto: <b>{len([c for c in state['auto'].values() if c.get('enabled')])}</b>\n"
            f"{ce('graph')} Rate: <b>{rate:.1f}%</b>",
            parse_mode="HTML")
        return


# ============================================================================
# MAIN
# ============================================================================
def main():
    load_state()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask running: http://0.0.0.0:{PORT}/")

    loop_thread = threading.Thread(target=auto_loop, daemon=True)
    loop_thread.start()
    logger.info("Auto loop started")

    logger.info("Bot polling started")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)


if __name__ == "__main__":
    main()
