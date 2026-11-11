import random
import time
import datetime
import asyncio
import os
import json
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

TOKEN = "9077202951:AAHKKKGMzY5eY7SXpcGdiRPaidy-ln3oevM"
DB = "dog_rpg.db"
HOP_COOLDOWN = 5 * 60
WAITING_DOG_NAME = 1

class WebServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), WebServer)
    server.serve_forever()

def keep_alive():
    t = Thread(target=run_web_server)
    t.daemon = True
    t.start()

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                coins INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                last_bank_time INTEGER DEFAULT 0,
                player_xp INTEGER DEFAULT 0,
                player_level INTEGER DEFAULT 1,
                last_hop INTEGER DEFAULT 0,
                dog_type INTEGER DEFAULT 1,
                dog_level INTEGER DEFAULT 1,
                dog_xp INTEGER DEFAULT 0,
                dog_name TEXT DEFAULT 'هاپو',
                boss_hp INTEGER DEFAULT 0,
                boss_id INTEGER DEFAULT 0,
                dog_hp INTEGER DEFAULT 0,
                last_attack INTEGER DEFAULT 0,
                revive_time INTEGER DEFAULT 0,
                hunt_level INTEGER DEFAULT 1,
                last_hunt INTEGER DEFAULT 0,
                weapon_until INTEGER DEFAULT 0,
                armor_until INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '{}',
                prey TEXT DEFAULT '{}'
            )
        """)
        await db.commit()

DOG_BREEDS = {
    1: ("توله سگ ضعیف 🐶", 0, 50, 10),
    2: ("سگ زباله‌گرد 🐕", 500, 100, 20),
    3: ("سگ شکاری 🐕‍🦺", 850, 180, 35),
    4: ("سگ نگهبان 🦮", 1500, 300, 60),
    5: ("سگ گرگی 🐺", 3000, 600, 120),
    6: ("سگ جهنمی 🔥", 6000, 1200, 250),
    7: ("سگ افسانه‌ای 🐉", 20000, 3000, 600),
}

BOSSES = {
    1: ("باس ضعیف 👹", 500),
    2: ("باس متوسط 👺", 1500),
    3: ("باس قوی 👿", 4000),
    4: ("باس افسانه‌ای 💀", 10000),
}

WEAPONS = {
    "p1": ("پنجه کوچک 🐾", 200, 10),
    "p2": ("پنجه مسی 🥉", 500, 25),
    "p3": ("پنجه آهنی ⚙️", 1500, 60),
    "p4": ("پنجه الماسی 💎", 4000, 150),
}

ARMORS = {
    "a1": ("زره چرمی 🧥", 200, 50),
    "a2": ("زره زنجیری ⛓️", 500, 120),
    "a3": ("زره فولادی 🛡️", 1500, 300),
    "a4": ("زره افسانه‌ای ✨", 4000, 800),
}

HUNTS = [
    ("استخوان 🦴", 10, 100),
    ("مرغ 🐔", 15, 150),
    ("ماهی 🐟", 25, 250),
    ("خرگوش 🐇", 50, 500),
    ("گراز وحشی 🐗", 100, 1000),
    ("آهوی طلایی 🦌", 250, 2500),
    ("اسب افسانه‌ای 🦄", 600, 6000),
]

HUNT_TITLES = [
    "تازه کار", "نیمه ماهر", "ماهر", "حرفه‌ای", "شکارچی نخبه",
    "شکارچی افسانه‌ای", "استاد شکار", "قهرمان شکار", "شاه شکارچیان", "خدای شکار"
]

async def get_player(uid):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM players WHERE user_id=?", (uid,)) as cur:
            row = await cur.fetchone()
    if not row:
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT INTO players (user_id) VALUES (?)", (uid,))
            await db.commit()
        return {
            "coins": 0, "bank": 0, "last_bank_time": 0, "player_xp": 0, "player_level": 1,
            "last_hop": 0, "dog_type": 1, "dog_level": 1, "dog_xp": 0, "dog_name": "هاپو",
            "boss_hp": 0, "boss_id": 0, "dog_hp": 0, "last_attack": 0, "revive_time": 0,
            "hunt_level": 1, "last_hunt": 0, "weapon_until": 0, "armor_until": 0,
            "inventory": "{}", "prey": "{}"
        }
    keys = ["coins", "bank", "last_bank_time", "player_xp", "player_level",
            "last_hop", "dog_type", "dog_level", "dog_xp", "dog_name", "boss_hp", 
            "boss_id", "dog_hp", "last_attack", "revive_time",
            "hunt_level", "last_hunt", "weapon_until", "armor_until", "inventory", "prey"]
    p = dict(zip(keys, row[1:]))
    p["prey"] = json.loads(p["prey"])
    return p

async def update_player(uid, **kwargs):
    if "prey" in kwargs:
        kwargs["prey"] = json.dumps(kwargs["prey"])
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [uid]
    async with aiosqlite.connect(DB) as db:
        await db.execute(f"UPDATE players SET {cols} WHERE user_id=?", vals)
        await db.commit()

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🐶 لونه هاپو", callback_data="dog_menu")],
        [InlineKeyboardButton("🏦 بانک هاپویی", callback_data="bank")],
        [InlineKeyboardButton("⚔️ مبارزه با باس", callback_data="boss_menu")],
        [InlineKeyboardButton("🏹 شکار", callback_data="hunt")],
        [InlineKeyboardButton("🛒 فروشگاه", callback_data="shop_main")],
    ])

def get_player_status(p):
    dog_info = f"{DOG_BREEDS[p['dog_type']][0]} (لول {p['dog_level']})"
    return (
        f"👤 لول بازیکن: {p['player_level']} (XP: {p['player_xp']})\n"
        f"🐕 سگ: {p['dog_name']} | {dog_info}\n"
        f"🏹 لول شکار: {p['hunt_level']} ({HUNT_TITLES[p['hunt_level']-1]})\n"
        f"💰 سکه: {p['coins']}\n"
    )

async def send_main_menu(update, context, edit=False):
    p = await get_player(update.effective_user.id)
    text = "🎮 <b>پنل اصلی</b>\n\n" + get_player_status(p) + "\nکلمه <b>هاپ</b> رو بفرست تا سکه بگیری."
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu(), parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await get_player(update.effective_user.id)
    await send_main_menu(update, context)

async def cheat_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = await get_player(uid)
    await update_player(uid, coins=p["coins"] + 1000, dog_xp=p["dog_xp"] + 1000)
    await update.message.reply_text("💎 <b>کد تقلب فعال شد!</b>\n💰 +1000 سکه\n✨ +1000 اکس‌پی برای سگ", parse_mode="HTML")

async def hop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    p = await get_player(uid)
    now = int(time.time())
    if now - p["last_hop"] < HOP_COOLDOWN:
        rem = HOP_COOLDOWN - (now - p["last_hop"])
        m, s = divmod(rem, 60)
        await update.message.reply_text(f"⏳ {m} دقیقه و {s} ثانیه صبر کن.")
        return
    coins = random.randint(20, 50)
    await update_player(uid, coins=p["coins"] + coins, player_xp=p["player_xp"] + 10, last_hop=now)
    await update.message.reply_text(f"🐕 <b>هاپ!</b>\n💰 +{coins} سکه")

async def dog_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    breed = DOG_BREEDS[p["dog_type"]]
    txt = (
        f"🐕 <b>لونه هاپو</b>\n\n"
        f"اسم سگ: <b>{p['dog_name']}</b>\n"
        f"نژاد: {breed[0]}\nلول: {p['dog_level']} / 20\n"
    )
    kb = [
        [InlineKeyboardButton("✏️ تغییر اسم سگ", callback_data="rename_dog")],
        [InlineKeyboardButton("🍖 فروشگاه غذا", callback_data="shop_food")],
        [InlineKeyboardButton("🔄 تغییر نژاد سگ", callback_data="buy_dog_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("✏️ اسم جدید سگت رو بفرست (بین ۳ تا ۱۰ حرف):")
    return WAITING_DOG_NAME

async def rename_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text
    if not (3 <= len(new_name) <= 10):
        await update.message.reply_text("❌ اسم باید بین ۳ تا ۱۰ حرف باشه! دوباره بفرست:")
        return WAITING_DOG_NAME
    await update_player(update.effective_user.id, dog_name=new_name)
    await update.message.reply_text(f"✅ اسم سگت به <b>{new_name}</b> تغییر کرد!", parse_mode="HTML")
    await send_main_menu(update, context)
    return ConversationHandler.END

async def buy_dog_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    kb = []
    for key, (name, price, hp, dmg) in DOG_BREEDS.items():
        if key != 1:
            kb.append([InlineKeyboardButton(f"{name} - {price}💰", callback_data=f"buy_dog:{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="dog_menu")])
    await q.edit_message_text(f"🛒 <b>فروشگاه سگ‌ها</b>\n💰 سکه: {p['coins']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def buy_dog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    dog_id = int(q.data.split(":")[1])
    p = await get_player(q.from_user.id)
    name, price, hp, dmg = DOG_BREEDS[dog_id]
    if p["coins"] < price:
        await q.answer("❌ سکه کافی نداری!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"] - price, dog_type=dog_id, dog_level=1, dog_xp=0)
    await q.answer(f"✅ سگ {name} خریداری شد!", show_alert=True)
    await dog_menu(update, context)

async def cmd_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = await get_player(update.effective_user.id)
    lvl = p["hunt_level"]
    
    txt = f"🏹 <b>شکار</b>\nلول تو: {lvl} ({HUNT_TITLES[lvl-1]})\n\n<b>شانس شکار:</b>\n"
    for i, (name, xp, price) in enumerate(HUNTS):
        chance = max(5, 40 - lvl*5) if i < 4 else max(5, i*5 + lvl*2)
        txt += f"🔹 {name} → ~{chance}% ({xp}XP یا {price}💰)\n"
        
    kb = [
        [InlineKeyboardButton("🏹 شکار کن!", callback_data="do_hunt")],
        [InlineKeyboardButton(f"⬆️ ارتقا (💰 {(lvl)*1000})", callback_data="hunt_upgrade")],
        [InlineKeyboardButton("🎒 کوله شکار", callback_data="hunt_bag")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def hunt_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    p = await get_player(q.from_user.id)
    lvl = p["hunt_level"]
    if lvl >= 10:
        await q.answer("❌ لول شکارت حداکثر (۱۰) است!", show_alert=True)
        return
    cost = lvl * 1000
    if p["coins"] < cost:
        await q.answer(f"❌ نیاز به {cost} سکه داری!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"]-cost, hunt_level=lvl+1)
    await q.answer(f"✅ لول شکارت به {lvl+1} رسید!", show_alert=True)
    await cmd_hunt(update, context)

async def do_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    p = await get_player(q.from_user.id)
    now = int(time.time())
    if now - p["last_hunt"] < 3600:
        rem = 3600 - (now - p["last_hunt"])
        m, s = divmod(rem, 60)
        await q.answer(f"⏳ {m} دقیقه و {s} ثانیه صبر کن.", show_alert=True)
        return
    lvl = p["hunt_level"]
    chances = [max(5, 40 - lvl*5), max(5, 25 - lvl*2), max(5, 15 - lvl), max(5, 10), max(5, 5 + lvl), max(2, lvl*2), max(1, lvl)]
    total = sum(chances)
    r = random.randint(1, total)
    current = 0
    hunt_idx = 0
    for i, chance in enumerate(chances):
        current += chance
        if r <= current:
            hunt_idx = i
            break
    hunt_name, xp, price = HUNTS[hunt_idx]
    prey = p["prey"]
    prey[str(hunt_idx)] = prey.get(str(hunt_idx), 0) + 1
    await update_player(q.from_user.id, last_hunt=now, prey=prey)
    await q.edit_message_text(
        f"🏹 <b>شکار موفق!</b>\nیه {hunt_name} گرفتی!\nبه کوله‌ت اضافه شد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎒 کوله شکار", callback_data="hunt_bag")], [InlineKeyboardButton("🔙 منو", callback_data="main_menu")]]),
        parse_mode="HTML"
    )

async def hunt_bag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    prey = p["prey"]
    if not prey:
        await q.edit_message_text("🎒 کوله شکارت خالیه!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="hunt")]]))
        return
    txt = "🎒 <b>کوله شکار</b>\n\n"
    kb = []
    for idx, count in prey.items():
        if count > 0:
            name, xp, price = HUNTS[int(idx)]
            txt += f"🔹 {name} × {count}\n"
            kb.append([InlineKeyboardButton(f"بفروش {name} (هرکدام {price}💰)", callback_data=f"hunt_sell:{idx}")])
            kb.append([InlineKeyboardButton(f"بده به سگ ({name})", callback_data=f"hunt_feed:{idx}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="hunt")])
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
async def hunt_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    idx = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    prey = p["prey"]
    count = prey.get(idx, 0)
    if count <= 0:
        await q.answer("❌ این آیتم رو نداری!", show_alert=True)
        return
    name, xp, price = HUNTS[int(idx)]
    total_price = price * count
    del prey[idx]
    await update_player(q.from_user.id, coins=p["coins"] + total_price, prey=prey)
    await q.answer(f"✅ {count} عدد {name} به {total_price} سکه فروخته شد!", show_alert=True)
    await hunt_bag(update, context)

async def hunt_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    idx = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    prey = p["prey"]
    count = prey.get(idx, 0)
    if count <= 0:
        await q.answer("❌ این آیتم رو نداری!", show_alert=True)
        return
    name, xp, price = HUNTS[int(idx)]
    new_xp = p["dog_xp"] + (xp * count)
    new_lvl = p["dog_level"]
    if new_xp >= new_lvl * 50 and new_lvl < 20:
        new_xp -= new_lvl * 50
        new_lvl += 1
    del prey[idx]
    await update_player(q.from_user.id, dog_xp=new_xp, dog_level=new_lvl, prey=prey)
    await q.answer(f"✅ سگت {count} عدد {name} خورد ({xp * count} XP)!", show_alert=True)
    await hunt_bag(update, context)

async def shop_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("🍖 غذاهای سگ", callback_data="shop_food")],
        [InlineKeyboardButton("⚔️ سلاح‌ها (پنجه)", callback_data="shop_weapons")],
        [InlineKeyboardButton("🛡️ زره‌ها", callback_data="shop_armors")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    await q.edit_message_text("🛒 <b>فروشگاه</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def shop_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    kb = [
        [InlineKeyboardButton("🦴 استخوان (۳۰💰, +۲۰XP)", callback_data="buy_food:bone")],
        [InlineKeyboardButton("🍖 گوشت (۸۰💰, +۶۰XP)", callback_data="buy_food:meat")],
        [InlineKeyboardButton("🥫 کنسرو (۱۵۰💰, +۱۵۰XP)", callback_data="buy_food:can")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="shop_main")],
    ]
    await q.edit_message_text(f"🍖 <b>غذا</b>\n💰 سکه: {p['coins']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def buy_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    food_type = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    prices = {"bone": (30, 20), "meat": (80, 60), "can": (150, 150)}
    price, xp = prices[food_type]
    if p["coins"] < price:
        await q.answer("❌ سکه کافی نداری!", show_alert=True)
        return
    new_xp = p["dog_xp"] + xp
    new_lvl = p["dog_level"]
    if new_xp >= new_lvl * 50 and new_lvl < 20:
        new_xp -= new_lvl * 50
        new_lvl += 1
    await update_player(q.from_user.id, coins=p["coins"] - price, dog_xp=new_xp, dog_level=new_lvl)
    await q.answer(f"✅ سگت غذا خورد (+{xp} XP)", show_alert=True)
    await shop_food(update, context)

async def shop_weapons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    kb = []
    for key, (name, price, dmg) in WEAPONS.items():
        kb.append([InlineKeyboardButton(f"{name} - {price}💰 (+{dmg} DMG)", callback_data=f"buy_wpn:{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="shop_main")])
    await q.edit_message_text(f"⚔️ <b>سلاح‌ها</b>\n💰 سکه: {p['coins']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def buy_wpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    wpn_id = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    name, price, dmg = WEAPONS[wpn_id]
    if p["coins"] < price:
        await q.answer("❌ سکه کافی نداری!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"] - price, weapon_until=int(time.time()) + 3600)
    await q.answer(f"✅ {name} خریدی (۱ ساعت دمیج داری)", show_alert=True)
    await shop_weapons(update, context)

async def shop_armors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    kb = []
    for key, (name, price, hp) in ARMORS.items():
        kb.append([InlineKeyboardButton(f"{name} - {price}💰 (+{hp} HP)", callback_data=f"buy_arm:{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="shop_main")])
    await q.edit_message_text(f"🛡️ <b>زره‌ها</b>\n💰 سکه: {p['coins']}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def buy_arm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    arm_id = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    name, price, hp = ARMORS[arm_id]
    if p["coins"] < price:
        await q.answer("❌ سکه کافی نداری!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"] - price, armor_until=int(time.time()) + 3600)
    await q.answer(f"✅ {name} خریدی (۱ ساعت HP داری)", show_alert=True)
    await shop_armors(update, context)

async def bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    p = await get_player(q.from_user.id)
    now = int(time.time())
    msg = ""
    if p["bank"] > 0 and now - p["last_bank_time"] >= 86400:
        days = (now - p["last_bank_time"]) // 86400
        interest = int(p["bank"] * 0.10 * days)
        await update_player(q.from_user.id, bank=p["bank"]+interest, last_bank_time=now)
        msg = f"💰 سود {interest} سکه اضافه شد!\n"
    txt = f"🏦 <b>بانک</b>\n\n{msg}💰 بانک: <b>{p['bank']}</b>\n👛 در دسترس: <b>{p['coins']}</b>\nسود روزانه: ۱۰٪\n"
    kb = [
        [InlineKeyboardButton("📥 واریز ۱۰۰", callback_data="dep:100"), InlineKeyboardButton("📥 واریز ۵۰۰", callback_data="dep:500")],
        [InlineKeyboardButton("📥 واریز کل", callback_data="dep:all")],
        [InlineKeyboardButton("📤 برداشت کل", callback_data="withdraw_all")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")],
    ]
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def deposit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    amount_str = q.data.split(":")[1]
    p = await get_player(q.from_user.id)
    amount = p["coins"] if amount_str == "all" else int(amount_str)
    if p["coins"] < amount or amount <= 0:
        await q.answer("❌ سکه کافی نداری!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"] - amount, bank=p["bank"] + amount, last_bank_time=int(time.time()))
    await q.answer(f"✅ {amount} سکه واریز شد!", show_alert=True)
    await bank(update, context)

async def withdraw_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    p = await get_player(q.from_user.id)
    if p["bank"] == 0:
        await q.answer("❌ بانک خالیه!", show_alert=True)
        return
    await update_player(q.from_user.id, coins=p["coins"] + p["bank"], bank=0)
    await q.answer(f"✅ {p['bank']} سکه برداشت شد!", show_alert=True)
    await bank(update, context)

async def boss_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = await get_player(q.from_user.id)
    kb = []
    for key, (name, hp) in BOSSES.items():
        kb.append([InlineKeyboardButton(f"{name} (HP:{hp})", callback_data=f"fight_start:{key}")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    await q.edit_message_text("⚔️ <b>باس‌ها</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def fight_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    boss_id = int(q.data.split(":")[1])
    p = await get_player(q.from_user.id)
    now = int(time.time())
    if p["revive_time"] > now:
        await q.answer(f"❌ سگت مرده! {int((p['revive_time']-now)//60)} دقیقه دیگه زنده میشه.", show_alert=True)
        return
    breed = DOG_BREEDS[p["dog_type"]]
    armor_hp = max([hp for name, price, hp in ARMORS.values()]) if p["armor_until"] > now else 0
    max_hp = breed[2] + (p["dog_level"] * 20) + armor_hp
    if p["boss_hp"] <= 0 or p["boss_id"] != boss_id:
        await update_player(q.from_user.id, boss_id=boss_id, boss_hp=BOSSES[boss_id][1], dog_hp=max_hp, last_attack=0)
        boss_hp = BOSSES[boss_id][1]
        dog_hp = max_hp
    else:
        boss_hp = p["boss_hp"]
        dog_hp = p["dog_hp"]
    await show_fight_screen(update, context, boss_id, boss_hp, max_hp, dog_hp)

async def show_fight_screen(update, context, boss_id, boss_hp, max_hp, dog_hp):
    q = update.callback_query
    p = await get_player(q.from_user.id)
    now = int(time.time())
    breed = DOG_BREEDS[p["dog_type"]]
    my_dmg = breed[3] + (p["dog_level"] * 5) + (max([dmg for name, price, dmg in WEAPONS.values()]) if p["weapon_until"] > now else 0)
    cd_msg = f"\n⏳ {30 - (now - p['last_attack'])} ثانیه" if (now - p['last_attack']) < 30 else ""
    txt = f"⚔️ <b>مبارزه</b>\n\n👹 باس HP: {boss_hp}\n🐕 سگ HP: {dog_hp} / {max_hp}\n💥 دمیج: {my_dmg}{cd_msg}"
    kb = []
    if (now - p["last_attack"]) >= 30:
        kb.append([InlineKeyboardButton("⚔️ حمله!", callback_data=f"fight_attack:{boss_id}")])
    kb.append([InlineKeyboardButton("🔙 فرار", callback_data="boss_menu")])
    await q.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def fight_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    boss_id = int(q.data.split(":")[1])
    p = await get_player(q.from_user.id)
    now = int(time.time())
    if now - p["last_attack"] < 30:
        await q.answer("⏳ صبر کن!", show_alert=True)
        return
    breed = DOG_BREEDS[p["dog_type"]]
    my_dmg = breed[3] + (p["dog_level"] * 5)
    if p["weapon_until"] > now:
        my_dmg += max([dmg for name, price, dmg in WEAPONS.values()])
    boss_hp = p["boss_hp"] - my_dmg
    if boss_hp <= 0:
        reward = BOSSES[boss_id][1] // 2
        await update_player(q.from_user.id, boss_hp=0, boss_id=0, coins=p["coins"]+reward, dog_xp=p["dog_xp"]+50)
        await q.edit_message_text(f"🏆 <b>پیروز شدی!</b>\n💰 +{reward} سکه", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منو", callback_data="main_menu")]]))
        return
    boss_dmg = random.randint(10, 50)
    dog_hp = p["dog_hp"] - boss_dmg
    if dog_hp <= 0:
        await update_player(q.from_user.id, dog_hp=0, revive_time=now+900, boss_hp=0, boss_id=0)
        await q.edit_message_text(f"💀 <b>سگت مرد!</b>\n۱۵ دقیقه دیگه زنده میشه.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 منو", callback_data="main_menu")]]))
        return
    await update_player(q.from_user.id, boss_hp=boss_hp, dog_hp=dog_hp, last_attack=now)
    await q.answer(f"⚔️ {my_dmg} دمیج! باس {boss_dmg} دمیج زد.", show_alert=True)
    await show_fight_screen(update, context, boss_id, boss_hp, (breed[2] + p["dog_level"]*20), dog_hp)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    if data == "main_menu": await send_main_menu(update, context, edit=True)
    elif data == "dog_menu": await dog_menu(update, context)
    elif data == "buy_dog_menu": await buy_dog_menu(update, context)
    elif data.startswith("buy_dog:"): await buy_dog(update, context)
    elif data == "shop_main": await shop_main(update, context)
    elif data == "shop_food": await shop_food(update, context)
    elif data.startswith("buy_food:"): await buy_food(update, context)
    elif data == "shop_weapons": await shop_weapons(update, context)
    elif data.startswith("buy_wpn:"): await buy_wpn(update, context)
    elif data == "shop_armors": await shop_armors(update, context)
    elif data.startswith("buy_arm:"): await buy_arm(update, context)
    elif data == "bank": await bank(update, context)
    elif data.startswith("dep:"): await deposit_cb(update, context)
    elif data == "withdraw_all": await withdraw_all(update, context)
    elif data == "boss_menu": await boss_menu(update, context)
    elif data.startswith("fight_start:"): await fight_start(update, context)
    elif data.startswith("fight_attack:"): await fight_attack(update, context)
    elif data == "hunt": await cmd_hunt(update, context)
    elif data == "do_hunt": await do_hunt(update, context)
    elif data == "hunt_upgrade": await hunt_upgrade(update, context)
    elif data == "hunt_bag": await hunt_bag(update, context)
    elif data.startswith("hunt_sell:"): await hunt_sell(update, context)
    elif data.startswith("hunt_feed:"): await hunt_feed(update, context)

def main():
    keep_alive()
    asyncio.run(init_db())
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^هاپ$"), hop))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^شکار$"), cmd_hunt))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^FURY5776$"), cheat_code))
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(rename_start, pattern="^rename_dog$")],
        states={WAITING_DOG_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, rename_save)]},
        fallbacks=[]
    )
    app.add_handler(conv_handler)

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_main_menu))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()