"""
Nifty SIP Strategy Bot — FIXED VERSION
Fix: replaced APScheduler with PTB's built-in JobQueue
     removed asyncio.run() — PTB manages its own event loop
"""

import json
import logging
import os
from datetime import time as dtime
import pytz
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()  # loads .env file locally; Railway injects vars automatically

# ── Config ────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")  # no fallback — fails clearly if missing

if not BOT_TOKEN:
    raise SystemExit(
        "\n\n"
        "❌ ERROR: BOT_TOKEN environment variable is not set!\n"
        "   → On Railway: go to your service → Variables tab\n"
        "     → click '+ New Variable'\n"
        "     → Name: BOT_TOKEN\n"
        "     → Value: paste your token from @BotFather\n"
        "     → press Enter → wait for redeploy\n"
    )

logger_temp = logging.getLogger(__name__)
logger_temp.info(f"✅ BOT_TOKEN loaded — starts with: {BOT_TOKEN[:10]}...")
SUBSCRIBERS_FILE = "subscribers.json"
IST              = pytz.timezone("Asia/Kolkata")
ALERT_HOUR       = 15
ALERT_MINUTE     = 0

DIP_MINOR   = -1.0
DIP_MAJOR   = -3.0
DIP_MASSIVE = -5.0

BASE_SIP    = 5000
EXTRA_MINOR = 3000
EXTRA_MAJOR = 5000
EXTRA_MAX   = 10000

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Subscriber Storage ────────────────────────────────────────────────
def load_subscribers() -> set:
    try:
        with open(SUBSCRIBERS_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def save_subscribers(subs: set):
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subs), f)

subscribers = load_subscribers()

# ── Nifty Data ────────────────────────────────────────────────────────
def get_nifty_data() -> dict:
    try:
        ticker = yf.Ticker("^NSEI")
        hist   = ticker.history(period="5d", interval="1d")
        if len(hist) < 2:
            return {"error": "Not enough data — market may be closed"}

        today_close = float(hist["Close"].iloc[-1])
        prev_close  = float(hist["Close"].iloc[-2])
        change_pts  = today_close - prev_close
        change_pct  = (change_pts / prev_close) * 100

        return {
            "today":      today_close,
            "prev":       prev_close,
            "open":       float(hist["Open"].iloc[-1]),
            "high":       float(hist["High"].iloc[-1]),
            "low":        float(hist["Low"].iloc[-1]),
            "change_pts": change_pts,
            "change_pct": change_pct,
            "error":      None,
        }
    except Exception as e:
        logger.error(f"yfinance error: {e}")
        return {"error": str(e)}

# ── Message Builder ───────────────────────────────────────────────────
def build_message(data: dict, scheduled: bool = False) -> str:
    from datetime import datetime
    now_str = datetime.now(IST).strftime("%d %b %Y  %I:%M %p IST")
    pct = data["change_pct"]
    pts = data["change_pts"]

    if pct <= DIP_MASSIVE:
        level  = "🚨 MASSIVE DIP"
        invest = BASE_SIP + EXTRA_MAX
        action = f"Invest *₹{invest:,}* today!\n   ₹{BASE_SIP:,} SIP + ₹{EXTRA_MAX:,} Extra (MAX)"
        tip    = "💥 Rare crash — deploy maximum capital!"
        bar    = "🟥🟥🟥🟥🟥"
    elif pct <= DIP_MAJOR:
        level  = "🔴 MAJOR DIP"
        invest = BASE_SIP + EXTRA_MAJOR
        action = f"Invest *₹{invest:,}* today!\n   ₹{BASE_SIP:,} SIP + ₹{EXTRA_MAJOR:,} Extra"
        tip    = "📉 Big dip — great buying window"
        bar    = "🟧🟧🟧🟧⬜"
    elif pct <= DIP_MINOR:
        level  = "🟡 MINOR DIP"
        invest = BASE_SIP + EXTRA_MINOR
        action = f"Invest *₹{invest:,}* today!\n   ₹{BASE_SIP:,} SIP + ₹{EXTRA_MINOR:,} Extra"
        tip    = "📊 Small dip — buy a few extra units"
        bar    = "🟨🟨⬜⬜⬜"
    else:
        level  = "✅ NORMAL DAY"
        invest = BASE_SIP
        action = f"Stick to *₹{invest:,}* monthly SIP only"
        tip    = "😎 No extra action needed today"
        bar    = "🟩⬜⬜⬜⬜"

    header = "📢 *NIFTY DAILY ALERT*" if scheduled else "📊 *NIFTY STATUS*"

    return (
        f"{header}\n{now_str}\n\n"
        f"{level}  {bar}\n\n"
        f"📈 *Nifty 50 Today*\n"
        f"  Close : `{data['today']:>10,.0f}`\n"
        f"  Change: `{pct:>+10.2f}%`  (`{pts:>+,.0f}` pts)\n"
        f"  ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\n"
        f"  Open  : `{data['open']:>10,.0f}`\n"
        f"  High  : `{data['high']:>10,.0f}`\n"
        f"  Low   : `{data['low']:>10,.0f}`\n"
        f"  Prev  : `{data['prev']:>10,.0f}`\n\n"
        f"💡 *Your Action Today*\n   {action}\n\n"
        f"_{tip}_\n\n"
        f"🤖 _Nifty SIP Bot — share with friends!_"
    )

# ── Keyboards ─────────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Check Now",   callback_data="check"),
         InlineKeyboardButton("ℹ️ Strategy",    callback_data="strategy")],
        [InlineKeyboardButton("👥 Bot Stats",   callback_data="stats"),
         InlineKeyboardButton("❌ Unsubscribe", callback_data="unsub")],
    ])

def back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])

# ── Command Handlers ──────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name
    subscribers.add(uid)
    save_subscribers(subscribers)
    await update.message.reply_text(
        f"👋 *Welcome, {name}!*\n\n"
        "You are now *subscribed* to Nifty SIP Alerts!\n\n"
        "🕒 Every trading day at *3:00 PM IST* you will get:\n"
        "  🟡 -1% dip  → Invest ₹8,000\n"
        "  🔴 -3% dip  → Invest ₹10,000\n"
        "  🚨 -5% dip  → Invest ₹15,000 MAX\n"
        "  ✅ No dip   → SIP ₹5,000 only\n\n"
        "Use the buttons below 👇",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_user.id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "❌ *Unsubscribed.* Type /start to re-subscribe anytime.",
        parse_mode="Markdown",
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching Nifty data...")
    data = get_nifty_data()
    if data["error"]:
        await update.message.reply_text(f"⚠️ {data['error']}")
        return
    await update.message.reply_text(
        build_message(data, scheduled=False),
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Nifty SIP Bot — Help*\n\n"
        "Commands:\n"
        "  /start  — Subscribe to daily alerts\n"
        "  /stop   — Unsubscribe\n"
        "  /status — Check Nifty right now\n"
        "  /help   — This message\n\n"
        "Daily alert at *3:00 PM IST* (Mon–Fri)\n"
        "Data: NSE via Yahoo Finance 🇮🇳",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )

# ── Button Handler ────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if q.data == "check":
        data = get_nifty_data()
        if data["error"]:
            await q.edit_message_text(f"⚠️ {data['error']}", reply_markup=back_kb())
        else:
            await q.edit_message_text(
                build_message(data, scheduled=False),
                parse_mode="Markdown",
                reply_markup=back_kb(),
            )

    elif q.data == "strategy":
        await q.edit_message_text(
            "📈 *Dip-Buying SIP Strategy*\n\n"
            "Monthly budget: ₹15,000\n\n"
            "  No drop    → ₹5,000 SIP\n"
            "  -1% to -3% → ₹8,000\n"
            "  -3% to -5% → ₹10,000\n"
            "  Below -5%  → ₹15,000 MAX 🔥\n\n"
            "Backtested 2021–2026 — beats plain SIP ✅\n\n"
            "_Be greedy when others are fearful — Buffett_",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )

    elif q.data == "stats":
        await q.edit_message_text(
            f"📊 *Bot Stats*\n"
            f"• Subscribers: *{len(subscribers)}* investors\n"
            f"• Daily alert: *3:00 PM IST* (Mon–Fri)\n"
            f"• Data: Yahoo Finance (NSE)",
            parse_mode="Markdown",
            reply_markup=back_kb(),
        )

    elif q.data == "unsub":
        subscribers.discard(uid)
        save_subscribers(subscribers)
        await q.edit_message_text(
            "❌ *Unsubscribed.* Type /start to re-subscribe.",
            parse_mode="Markdown",
        )

    elif q.data == "back":
        await q.edit_message_text(
            "👋 *Nifty SIP Bot*\nUse the buttons below:",
            parse_mode="Markdown",
            reply_markup=main_kb(),
        )

# ── Scheduled Alert — PTB Built-in JobQueue ───────────────────────────
async def scheduled_alert(context: ContextTypes.DEFAULT_TYPE):
    """
    Called by PTB's built-in job queue at 3 PM IST Mon–Fri.
    NOTE: signature must be (context,) — not (bot,)
    """
    from datetime import datetime
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return

    logger.info(f"Daily alert — {now.strftime('%d %b %Y %H:%M IST')}")
    data = get_nifty_data()
    if data["error"]:
        logger.warning(f"Fetch failed: {data['error']}")
        return

    msg  = build_message(data, scheduled=True)
    dead = set()

    for uid in list(subscribers):
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=msg,
                parse_mode="Markdown",
                reply_markup=main_kb(),
            )
        except Exception as e:
            logger.warning(f"Failed → {uid}: {e}")
            dead.add(uid)

    if dead:
        subscribers.difference_update(dead)
        save_subscribers(subscribers)

    logger.info(
        f"Sent to {len(subscribers)} | change={data['change_pct']:+.2f}%"
    )

# ── Main — synchronous, NO asyncio.run() ─────────────────────────────
def main():
    logger.info("🚀 Starting Nifty SIP Bot (fixed)...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Schedule using PTB's built-in JobQueue — no APScheduler conflict
    alert_time = dtime(hour=ALERT_HOUR, minute=ALERT_MINUTE, tzinfo=IST)
    app.job_queue.run_daily(
        scheduled_alert,
        time=alert_time,
        days=(0, 1, 2, 3, 4),   # Monday=0 to Friday=4
        name="daily_nifty_alert",
    )
    logger.info(f"Scheduled daily alert at {ALERT_HOUR:02d}:{ALERT_MINUTE:02d} IST (Mon–Fri)")
    logger.info(f"Bot is LIVE! Subscribers: {len(subscribers)}")

    # PTB manages its own event loop — do NOT use asyncio.run()
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
