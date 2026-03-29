import hashlib, logging, re, os, json, secrets
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from functools import wraps
from datetime import datetime, timedelta

# === Cấu hình ===
BOT_TOKEN = '8273056780:AAFKBkxgQ3nwmsqkEEy0UF7envy3fV1wGfA'
logging.basicConfig(filename='bot_md5_tai_xiu.log', level=logging.INFO, format='%(asctime)s - %(message)s')

ADMIN_FILE = 'admin_list.json'
KEY_FILE = 'keys.json'
USER_KEYS_FILE = 'user_keys.json'
ADMIN_USER_ID = '7071414779'
ADMIN_KEY = 'adminkey120666'

# === Tạo mặc định ===
def init_admin_and_key():
    admins = load_json(ADMIN_FILE)
    admins.setdefault("admins", [])
    if ADMIN_USER_ID not in admins["admins"]:
        admins["admins"].append(ADMIN_USER_ID)
    save_json(ADMIN_FILE, admins)

    keys = load_json(KEY_FILE)
    keys[ADMIN_KEY] = {"used": True}
    save_json(KEY_FILE, keys)

    user_keys = load_json(USER_KEYS_FILE)
    user_keys[ADMIN_USER_ID] = ADMIN_KEY
    save_json(USER_KEYS_FILE, user_keys)

    cleanup_expired_keys()

# === Biến toàn cục ===
adjustment = 0.0
wrong_streak = 0
history = []
last_prediction = {}

# === Tiện ích ===
def load_json(filename):
    return json.load(open(filename, 'r', encoding='utf-8')) if os.path.exists(filename) else {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def is_admin(user_id):
    admins = load_json(ADMIN_FILE)
    return str(user_id) in admins.get("admins", [])

def is_logged_in(user_id):
    keys = load_json(USER_KEYS_FILE)
    return str(user_id) in keys

def require_login(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_logged_in(user_id) and not is_admin(user_id):
            await update.message.reply_text("🔐 Bạn cần nhập key hợp lệ. Dùng: /key <mã>")
            return
        return await func(update, context)
    return wrapper

def cleanup_expired_keys():
    keys = load_json(KEY_FILE)
    now = datetime.now()
    updated = {k: v for k, v in keys.items() if 'expire_time' not in v or datetime.strptime(v['expire_time'], '%Y-%m-%d %H:%M:%S') > now}
    if len(updated) != len(keys):
        save_json(KEY_FILE, updated)

# === Phân tích MD5 ===
def is_valid_md5(md5):
    return bool(re.match(r'^[a-f0-9]{32}$', md5.lower()))

def analyze_md5(md5, adj):
    value = sum(ord(c) * (i + 1) for i, c in enumerate(md5)) % 1000
    base_ratio = value / 1000
    if len(history) >= 3 and history[-1] == history[-2] == history[-3]:
        if history[-1] == 'tài':
            base_ratio += 0.08
        elif history[-1] == 'xỉu':
            base_ratio -= 0.08
    tai_ratio = min(1, max(0, base_ratio + adj))
    return round(tai_ratio * 100, 2), round((1 - tai_ratio) * 100, 2)

def detect_trend(history, max_len=10):
    if len(history) < 3:
        return "Chưa đủ dữ liệu"

    recent = history[-max_len:]
    patterns = {
        ('tài', 'tài', 'xỉu'): "Mẫu: Tài Tài Xỉu",
        ('xỉu', 'tài', 'xỉu'): "Mẫu: Xỉu Tài Xỉu",
        ('xỉu', 'xỉu', 'tài'): "Mẫu: Xỉu Xỉu Tài",
        ('tài', 'xỉu', 'xỉu'): "Mẫu: Tài Xỉu Xỉu",
        ('tài', 'tài', 'xỉu'): "Mẫu: Tài Tài Xỉu",
        ('tài', 'tài', 'tài'): "Mẫu: Tài Tài Tài",
        ('xỉu', 'xỉu', 'xỉu'): "Mẫu: Xỉu Xỉu Xỉu",
        ('xỉu', 'tài', 'xỉu', 'tài'): "Mẫu: Xỉu Tài Xỉu Tài",
        ('tài', 'tài', 'tài', 'xỉu'): "Mẫu: 3 Tài ra Xỉu",
        ('xỉu', 'xỉu', 'xỉu', 'tài'): "Mẫu: 3 Xỉu ra Tài",
        ('tài', 'xỉu', 'tài'): "Mẫu: Tài Xỉu Tài",
        ('xỉu', 'tài', 'tài', 'xỉu'): "Mẫu: Xỉu Tài Tài Xỉu",
    }
    for length in range(4, 2, -1):
        seq = tuple(recent[-length:])
        if seq in patterns:
            return patterns[seq]

    for i in range(5, 2, -1):
        if len(recent) >= i and all(x == recent[-1] for x in recent[-i:]):
            return f"Cầu bệt ({recent[-1].capitalize()} x {i})"

    if len(recent) >= 4 and all(recent[i] != recent[i+1] for i in range(len(recent)-1)):
        return "Cầu đảo (Tài/Xỉu xen kẽ)"

    count_tai = recent.count("tài")
    count_xiu = recent.count("xỉu")
    if count_tai > count_xiu and recent[-1] == "tài":
        return "Xu hướng Tài tăng"
    elif count_xiu > count_tai and recent[-1] == "xỉu":
        return "Xu hướng Xỉu tăng"

    return "Xu hướng không rõ ràng"

# === Lệnh người dùng ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎲 Gửi mã MD5 để dự đoán Tài/Xỉu!\n🔐 Nhập key bằng lệnh: /key <mã>")

async def input_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text("📥 Dùng: /key <mã>")
        return
    key = context.args[0]
    keys = load_json(KEY_FILE)
    user_keys = load_json(USER_KEYS_FILE)
    if key in keys:
        info = keys[key]
        if 'expire_time' in info and datetime.now() > datetime.strptime(info['expire_time'], '%Y-%m-%d %H:%M:%S'):
            await update.message.reply_text("⛔ Key đã hết hạn.")
            return
        if not info.get("used", False):
            keys[key]["used"] = True
            user_keys[user_id] = key
            save_json(KEY_FILE, keys)
            save_json(USER_KEYS_FILE, user_keys)
            await update.message.reply_text("✅ Đăng nhập thành công! Gửi MD5 để dự đoán.")
            return
    await update.message.reply_text("❌ Key không hợp lệ hoặc đã dùng.")

@require_login
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global adjustment, history, last_prediction
    user_id = str(update.effective_user.id)
    md5 = update.message.text.strip().lower()
    if not is_valid_md5(md5):
        await update.message.reply_text("❌ MD5 không hợp lệ.")
        return
    tai, xiu = analyze_md5(md5, adjustment)
    prediction = "Tài" if tai > xiu else "Xỉu"
    last_prediction[user_id] = prediction.lower()
    history.append(prediction.lower())
    trend = detect_trend(history)
    msg = f"🔍 MD5: {md5}\n🎯 Tỷ lệ: Tài {tai}%, Xỉu {xiu}%\n👉 Dự đoán: {prediction}\n\n📊 {trend}\n📥 Nhập kết quả thật: /ketqua tài hoặc /ketqua xỉu"
    await update.message.reply_text(msg)

@require_login
async def handle_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global adjustment, wrong_streak, last_prediction
    user_id = str(update.effective_user.id)
    if user_id not in last_prediction:
        await update.message.reply_text("❗ Chưa có dự đoán nào.")
        return
    try:
        actual = context.args[0].lower()
        if actual not in ["tài", "xỉu"]:
            raise ValueError
        if actual == last_prediction[user_id]:
            msg = "✅ Đoán đúng!"
            wrong_streak = 0
            adjustment *= 0.9
        else:
            msg = f"❌ Đoán sai! Bot đoán {last_prediction[user_id].upper()}, kết quả là {actual.upper()}."
            wrong_streak += 1
            adjustment += 0.02
        del last_prediction[user_id]
        await update.message.reply_text(f"{msg}\n📈 Điều chỉnh hiện tại: {round(adjustment, 4)}")
    except:
        await update.message.reply_text("❌ Dùng đúng cú pháp: /ketqua tài hoặc /ketqua xỉu")

# === Admin ===
async def create_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bạn không có quyền admin.")
        return
    try:
        days = int(context.args[0]) if context.args else 1
    except:
        await update.message.reply_text("⚠️ Dùng: /newkey <số ngày>")
        return
    new_key = secrets.token_hex(4)
    expire = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    keys = load_json(KEY_FILE)
    keys[new_key] = {"used": False, "expire_time": expire}
    save_json(KEY_FILE, keys)
    await update.message.reply_text(f"🔑 Key mới: `{new_key}`\n⏳ Hạn dùng: {expire}", parse_mode='Markdown')

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Bạn không có quyền admin.")
        return
    user_keys = load_json(USER_KEYS_FILE)
    if not user_keys:
        await update.message.reply_text("📭 Chưa có người dùng nào sử dụng key.")
        return
    msg = "📋 Danh sách người dùng và key đang sử dụng:\n\n"
    for uid, key in user_keys.items():
        msg += f"👤 User ID: `{uid}` – 🔑 Key: `{key}`\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

# === Main ===
def main():
    init_admin_and_key()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key", input_key))
    app.add_handler(CommandHandler("ketqua", handle_result))
    app.add_handler(CommandHandler("newkey", create_key))
    app.add_handler(CommandHandler("listusers", list_users))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
    