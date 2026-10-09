import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import time
import threading
import os
import logging
from datetime import datetime
from flask import Flask, jsonify

# ================================================================
# CẤU HÌNH
# ================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8844628964:AAE3Wm5VUQIRqhBuwonAFRuuW5eHwPIczIw")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "7564889663").split(",") if x.strip()]

PORT = int(os.getenv("PORT", 8080))
API_URL = "https://sicsun-g34z.onrender.com/api/sicbo/sunwin"
FETCH_INTERVAL = 4
STATE_FILE = "bot_state.json"
MAX_HISTORY = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sicbo-bot")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ================================================================
# FLASK HEALTH CHECK (để Render không sleep)
# ================================================================
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

# ================================================================
# EMOJI PREMIUM
# ================================================================
CE = {
    "fire":   ("5424972470023104089", "🔥"),
    "star":   ("5438496463044752972", "⭐️"),
    "spark":  ("5325547803936572038", "✨"),
    "crown":  ("5217822164362739968", "👑"),
    "gem":    ("5427168083074628963", "💎"),
    "100":    ("5341498088408234504", "💯"),
    "chart":  ("5231200819986047254", "📊"),
    "graph":  ("5244837092042750681", "📈"),
    "down":   ("5246762912428603768", "📉"),
    "hour":   ("5386367538735104399", "⌛"),
    "bell":   ("5458603043203327669", "🔔"),
    "warn":   ("5447644880824181073", "⚠️"),
    "info":   ("5334544901428229844", "ℹ️"),
    "gear":   ("5341715473882955310", "⚙️"),
    "lock":   ("5296369303661067030", "🔒"),
    "shield": ("5251203410396458957", "🛡"),
    "red":    ("5411225014148014586", "🔴"),
    "green":  ("5416081784641168838", "🟢"),
    "ok":     ("5206607081334906820", "✔️"),
    "x":      ("5210952531676504517", "❌"),
    "stop":   ("5260293700088511294", "⛔️"),
    "play":   ("5264919878082509254", "▶️"),
    "pause":  ("5359543311897998264", "⏸"),
    "cash":   ("5409048419211682843", "💵"),
    "game":   ("5361741454685256344", "🎮"),
    "sync":   ("5375338737028841420", "🔄"),
    "top":    ("5415655814079723871", "🔝"),
    "new":    ("5382357040008021292", "🆕"),
    "right":  ("5416117059207572332", "➡️"),
    "party":  ("5461151367559141950", "🎉"),
    "clown":  ("5269531045165816230", "🤡"),
    "like":   ("5337080053119336309", "👍"),
    "down2":  ("5449875686837726134", "👎"),
    "flag":   ("5460755126761312667", "🚩"),
    "pin":    ("5397782960512444700", "📌"),
    "trash":  ("5445267414562389170", "🗑"),
    "plus":   ("5397916757333654639", "➕"),
    "edit":   ("5395444784611480792", "✏️"),
    "q":      ("5436113877181941026", "❓"),
    "alert":  ("5395695537687123235", "🚨"),
    "mega":   ("5424818078833715060", "📣"),
    "eyes":   ("5210956306952758910", "👀"),
}

def ce(key):
    emoji_id, fallback = CE.get(key, ("", "❓"))
    if not emoji_id:
        return fallback
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# ================================================================
# STATE
# ================================================================
state = {
    "auto": {},       # { chat_id: { enabled, chat_type, added_by, added_at } }
    "users": {},      # { user_id: { name, username, joined, last_active } }
    "history": {},    # { chat_id: [ {...}, ... ] }
}

_last_session = None
_last_data = None
_last_update_time = None

def load_state():
    global state
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            state["auto"] = {int(k): v for k, v in data.get("auto", {}).items()}
            state["users"] = {int(k): v for k, v in data.get("users", {}).items()}
            state["history"] = {int(k): v for k, v in data.get("history", {}).items()}
            logger.info(f"Loaded: {len(state['auto'])} auto, {len(state['users'])} users")
    except Exception as e:
        logger.error(f"Load state error: {e}")

_save_lock = threading.Lock()
def save_state():
    with _save_lock:
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            logger.error(f"Save state error: {e}")

def is_admin(user_id):
    return int(user_id) in ADMIN_IDS

# ================================================================
# API
# ================================================================
def fetch_api():
    try:
        r = requests.get(API_URL, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"API error: {e}")
    return None

# ================================================================
# FORMAT
# ================================================================
def format_prediction(data, history_list):
    next_session = data.get("phien_hien_tai", "?")
    du_doan = data.get("du_doan", "?")
    do_tin_cay = data.get("do_tin_cay", "0%")
    top3 = data.get("du_doan_vi", "?")
    top5 = data.get("du_doan_top5", "?")
    accuracy = data.get("accuracy", "N/A")

    emoji_tx = ce("red") if du_doan.lower() == "tài" else ce("green")
    tx_upper = du_doan.upper()

    streak_text = "Chưa có dữ liệu"
    if history_list:
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
            streak_text = f"{ce('fire')} Chuỗi thắng: <b>{wins}</b>"
        elif losses > 0:
            streak_text = f"{ce('warn')} Chuỗi thua: <b>{losses}</b>"

    status_text = "⏳ Chờ kết quả"
    if history_list:
        last = history_list[-1]
        if last.get("correct") is True:
            status_text = f"{ce('ok')} <b>THẮNG</b>"
        elif last.get("correct") is False:
            status_text = f"{ce('x')} <b>THUA</b>"

    return (
        f"{ce('spark')} <b>DỰ ĐOÁN PHIÊN {next_session}</b>\n\n"
        f"{emoji_tx} <b>{tx_upper}</b>\n"
        f"{ce('chart')} Độ tin cậy: <b>{do_tin_cay}</b>\n"
        f"{ce('gem')} Top 3 vị: <b>[{top3}]</b>\n"
        f"{ce('top')} Top 5 vị: <b>[{top5}]</b>\n\n"
        f"{ce('info')} {status_text}\n"
        f"{streak_text}\n"
        f"{ce('graph')} Accuracy bot: <b>{accuracy}</b>\n\n"
        f"{ce('hour')} {datetime.now().strftime('%H:%M:%S')}"
    )

# ================================================================
# BACKGROUND LOOP
# ================================================================
def auto_loop():
    global _last_session, _last_data, _last_update_time
    logger.info("Auto loop started")

    while True:
        try:
            data = fetch_api()
            if not data:
                time.sleep(FETCH_INTERVAL)
                continue

            current_session = data.get("phien_hien_tai")
            _last_update_time = datetime.now().isoformat()

            if current_session == _last_session:
                time.sleep(FETCH_INTERVAL)
                continue

            _last_data = data

            # Cập nhật đánh giá + push dự đoán
            for chat_id_str, cfg in list(state["auto"].items()):
                if not cfg.get("enabled"):
                    continue

                chat_id = int(chat_id_str)
                history_list = state["history"].get(chat_id, [])

                # Đánh giá dự đoán trước
                if history_list:
                    last_entry = history_list[-1]
                    if last_entry.get("actual") is None:
                        actual = (data.get("ket_qua") or "").upper()
                        if actual in ["TAI", "TÀI", "XIU", "XỈU"]:
                            actual_norm = "TÀI" if actual in ["TAI", "TÀI"] else "XỈU"
                            last_entry["actual"] = actual_norm
                            last_entry["correct"] = (last_entry.get("prediction", "").upper() == actual_norm)

                # Thêm dự đoán mới
                history_list.append({
                    "session": current_session + 1,
                    "prediction": data.get("du_doan", "?"),
                    "confidence": data.get("do_tin_cay", "0%"),
                    "top3": data.get("du_doan_vi", "?"),
                    "correct": None,
                    "actual": None,
                    "time": datetime.now().isoformat(),
                })

                if len(history_list) > MAX_HISTORY:
                    history_list = history_list[-MAX_HISTORY:]
                state["history"][chat_id] = history_list

                # Gửi tin nhắn
                try:
                    text = format_prediction(data, history_list)
                    bot.send_message(chat_id, text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Send to {chat_id} failed: {e}")

            _last_session = current_session
            save_state()

        except Exception as e:
            logger.error(f"Loop error: {e}")

        time.sleep(FETCH_INTERVAL)

# ================================================================
# HANDLERS
# ================================================================
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    user = msg.from_user
    chat = msg.chat
    now = int(time.time())

    # Đăng ký user
    state["users"][user.id] = {
        "name": user.full_name or "Không rõ",
        "username": f"@{user.username}" if user.username else "Không có",
        "joined": state["users"].get(user.id, {}).get("joined", now),
        "last_active": now,
    }
    save_state()

    text = (
        f"{ce('spark')} <b>SICBO SUNWIN BOT</b>\n\n"
        f"{ce('info')} Xin chào <b>{user.full_name}</b>\n\n"
        f"{ce('play')} <b>Lệnh có sẵn:</b>\n"
        f"/auto - Bật tự động dự đoán\n"
        f"/stop - Dừng tự động\n"
        f"/status - Xem trạng thái\n"
        f"/predict - Dự đoán hiện tại\n"
        f"/history - Lịch sử dự đoán\n"
        f"/stats - Thống kê\n"
        f"/help - Trợ giúp\n"
    )

    if is_admin(user.id):
        text += (
            f"\n{ce('crown')} <b>Lệnh admin:</b>\n"
            f"/admin - Panel admin\n"
            f"/broadcast &lt;msg&gt; - Gửi thông báo\n"
            f"/listchats - Danh sách chat\n"
        )

    bot.send_message(chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    cmd_start(msg)

@bot.message_handler(commands=["auto"])
def cmd_auto(msg):
    chat = msg.chat
    user = msg.from_user

    state["auto"][chat.id] = {
        "enabled": True,
        "chat_type": chat.type,
        "added_by": user.id,
        "added_at": int(time.time()),
    }
    save_state()

    bot.send_message(chat.id,
        f"{ce('play')} <b>Đã BẬT auto dự đoán</b>\n"
        f"{ce('info')} Chat ID: <code>{chat.id}</code>\n"
        f"{ce('hour')} Nhận dự đoán mỗi 5 giây\n"
        f"{ce('stop')} Gõ /stop để dừng",
        parse_mode="HTML")

@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    chat = msg.chat
    if chat.id in state["auto"]:
        state["auto"][chat.id]["enabled"] = False
        save_state()
        bot.send_message(chat.id,
            f"{ce('stop')} <b>Đã DỪNG auto dự đoán</b>\n"
            f"{ce('info')} Gõ /auto để bật lại",
            parse_mode="HTML")
    else:
        bot.send_message(chat.id,
            f"{ce('warn')} Chat này chưa bật auto",
            parse_mode="HTML")

@bot.message_handler(commands=["status"])
def cmd_status(msg):
    chat = msg.chat
    cfg = state["auto"].get(chat.id)
    if cfg:
        status = "BẬT" if cfg.get("enabled") else "TẮT"
        emoji = ce("ok") if cfg.get("enabled") else ce("x")
        text = (
            f"{ce('info')} <b>TRẠNG THÁI</b>\n\n"
            f"{emoji} Auto: <b>{status}</b>\n"
            f"{ce('pin')} Chat ID: <code>{chat.id}</code>\n"
            f"{ce('hour')} Từ: {datetime.fromtimestamp(cfg.get('added_at', 0)).strftime('%d/%m %H:%M')}"
        )
    else:
        text = (
            f"{ce('info')} <b>TRẠNG THÁI</b>\n\n"
            f"{ce('x')} Auto: <b>CHƯA BẬT</b>\n"
            f"{ce('right')} Gõ /auto để bật"
        )
    bot.send_message(chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=["predict"])
def cmd_predict(msg):
    data = _last_data or fetch_api()
    if not data:
        bot.send_message(msg.chat.id, f"{ce('warn')} Không lấy được dữ liệu", parse_mode="HTML")
        return
    history_list = state["history"].get(msg.chat.id, [])
    bot.send_message(msg.chat.id, format_prediction(data, history_list), parse_mode="HTML")

@bot.message_handler(commands=["history"])
def cmd_history(msg):
    history_list = state["history"].get(msg.chat.id, [])
    if not history_list:
        bot.send_message(msg.chat.id, f"{ce('info')} Chưa có lịch sử", parse_mode="HTML")
        return

    lines = [f"{ce('info')} <b>LỊCH SỬ DỰ ĐOÁN ({len(history_list)})</b>\n"]
    for h in reversed(history_list[-MAX_HISTORY:]):
        session = h.get("session", "?")
        pred = h.get("prediction", "?").upper()
        actual = (h.get("actual") or "?").upper()
        correct = h.get("correct")
        emoji_tx = ce("red") if pred == "TÀI" else ce("green")
        if correct is True:
            status = ce("ok")
        elif correct is False:
            status = ce("x")
        else:
            status = "⏳"
        lines.append(f"{status} <b>#{session}</b> | {emoji_tx} {pred} → {actual}")

    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="HTML")

@bot.message_handler(commands=["stats"])
def cmd_stats(msg):
    data = fetch_api()
    if not data:
        bot.send_message(msg.chat.id, f"{ce('warn')} Không lấy được dữ liệu", parse_mode="HTML")
        return
    accuracy = data.get("accuracy", "N/A")
    text = (
        f"{ce('chart')} <b>THỐNG KÊ BOT</b>\n\n"
        f"{ce('graph')} Accuracy: <b>{accuracy}</b>\n"
        f"{ce('info')} Tổng chat auto: <b>{len([c for c in state['auto'].values() if c.get('enabled')])}</b>\n"
        f"{ce('eyes')} Tổng user: <b>{len(state['users'])}</b>"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=["admin"])
def cmd_admin(msg):
    if not is_admin(msg.from_user.id):
        bot.send_message(msg.chat.id, f"{ce('lock')} Bạn không phải admin", parse_mode="HTML")
        return
    text = (
        f"{ce('crown')} <b>ADMIN PANEL</b>\n\n"
        f"{ce('info')} Tổng chat auto: <b>{len([c for c in state['auto'].values() if c.get('enabled')])}</b>\n"
        f"{ce('eyes')} Tổng user: <b>{len(state['users'])}</b>\n"
        f"{ce('bell')} Tổng chat đăng ký: <b>{len(state['auto'])}</b>\n\n"
        f"<b>Lệnh:</b>\n"
        f"/broadcast &lt;msg&gt; - Gửi tin\n"
        f"/listchats - Danh sách chat\n"
        f"/resetai - Reset AI (nếu có)"
    )
    bot.send_message(msg.chat.id, text, parse_mode="HTML")

@bot.message_handler(commands=["listchats"])
def cmd_listchats(msg):
    if not is_admin(msg.from_user.id):
        return
    lines = [f"{ce('info')} <b>DANH SÁCH CHAT AUTO</b>\n"]
    for cid, cfg in state["auto"].items():
        if cfg.get("enabled"):
            lines.append(f"{ce('ok')} <code>{cid}</code> ({cfg.get('chat_type', '?')})")
    if len(lines) == 1:
        lines.append("Chưa có chat nào")
    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="HTML")

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(msg):
    if not is_admin(msg.from_user.id):
        return
    text = msg.text.replace("/broadcast", "").strip()
    if not text:
        bot.send_message(msg.chat.id, f"{ce('warn')} Dùng: /broadcast &lt;nội dung&gt;", parse_mode="HTML")
        return

    success = 0
    fail = 0
    for cid, cfg in state["auto"].items():
        if cfg.get("enabled"):
            try:
                bot.send_message(cid, f"{ce('mega')} <b>THÔNG BÁO</b>\n\n{text}", parse_mode="HTML")
                success += 1
            except Exception:
                fail += 1
    bot.send_message(msg.chat.id,
        f"{ce('ok')} Gửi thành công: <b>{success}</b>\n{ce('x')} Lỗi: <b>{fail}</b>",
        parse_mode="HTML")

# ================================================================
# START
# ================================================================
def main():
    load_state()

    # Chạy Flask server (health check cho Render)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask health check: http://0.0.0.0:{PORT}/")

    # Chạy auto loop
    loop_thread = threading.Thread(target=auto_loop, daemon=True)
    loop_thread.start()

    logger.info("Bot polling started")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    main()
