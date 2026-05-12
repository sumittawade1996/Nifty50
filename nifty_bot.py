"""
Nifty SIP Strategy Bot — v3 FINAL
Fixes:
  1. yfinance: retry logic + 3 fallback methods for reliable Nifty data
  2. Scheduling: days=(1,2,3,4,5) for Mon-Fri in PTB v20 cron scheme
  3. Added /test command to manually fire alert any time
"""

import json
import logging
import os
import time as _time
from datetime import time as dtime
import pytz
import yfinance as yf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise SystemExit(
        "\n\n❌ ERROR: BOT_TOKEN not set!\n"
        "   Railway → service → Variables tab → add BOT_TOKEN\n"
    )

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logger.info(f"✅ BOT_TOKEN loaded — starts with: {BOT_TOKEN[:10]}...")

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

# ── Nifty Data — retry + 3 fallback methods ───────────────────────────
def get_nifty_data() -> dict:
    """
    Tries multiple methods to fetch Nifty 50 data reliably.
      Method 1: yf.download("^NSEI")
      Method 2: yf.download("NIFTY50.NS")
      Method 3: yf.Ticker("^NSEI").history()
    Retries up to 3 times with 2s delay between attempts.
    """
    methods = [
        lambda: yf.download("^NSEI",      period="7d", interval="1d", progress=False, auto_adjust=True),
        lambda: yf.download("NIFTY50.NS", period="7d", interval="1d", progress=False, auto_adjust=True),
        lambda: yf.Ticker("^NSEI").history(period="7d", interval="1d"),
    ]

    for attempt in range(3):
        for i, method in enumerate(methods):
            try:
                hist = method()
                if hasattr(hist.columns, 'levels'):   # multi-level columns from download
                    hist.columns = hist.columns.droplevel(1)
                hist = hist.dropna()

                if len(hist) < 2:
                    logger.warning(f"Method {i+1}: only {len(hist)} rows — skipping")
                    continue

                today_close = float(hist["Close"].iloc[-1])
                prev_close  = float(hist["Close"].iloc[-2])
                change_pts  = today_close - prev_close
                change_pct  = (change_pts / prev_close) * 100

                logger.info(f"✅ Nifty data fetched (method {i+1}, attempt {attempt+1}): {today_close:.0f} ({change_pct:+.2f}%)")

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
                logger.warning(f"Method {i+1} attempt {attempt+1} failed: {e}")
                continue

        if attempt < 2:
            logger.info(f"All methods failed — retrying in 2s (attempt {attempt+1}/3)")
            _time.sleep(2)

    return {"error": "Could not fetch Nifty data after 3 attempts. Market may be closed or API is down."}

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
        f"🤖 _Nifty SIP Bot — share: t.me/your\_bot\_name_"
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
        "  /test   — Manually fire today's alert\n"
        "  /help   — This message\n\n"
        "Daily alert at *3:00 PM IST* (Mon–Fri)\n"
        "Data: NSE via Yahoo Finance 🇮🇳",
        parse_mode="Markdown",
        reply_markup=main_kb(),
    )

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually fires the scheduled alert — use to test without waiting for 3 PM."""
    await update.message.reply_text("🧪 Firing test alert to all subscribers...")
    await scheduled_alert(context)
    await update.message.reply_text(f"✅ Test done — sent to {len(subscribers)} subscriber(s).")

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
                parse_mode="Markdown", reply_markup=back_kb(),
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
            parse_mode="Markdown", reply_markup=back_kb(),
        )

    elif q.data == "stats":
        await q.edit_message_text(
            f"📊 *Bot Stats*\n"
            f"• Subscribers: *{len(subscribers)}* investors\n"
            f"• Daily alert: *3:00 PM IST* (Mon–Fri)\n"
            f"• Data: Yahoo Finance (NSE)",
            parse_mode="Markdown", reply_markup=back_kb(),
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
            parse_mode="Markdown", reply_markup=main_kb(),
        )

# ── Scheduled Alert ───────────────────────────────────────────────────
async def scheduled_alert(context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    now = datetime.now(IST)
    if now.weekday() >= 5:
        logger.info("Weekend — skipping alert")
        return

    logger.info(f"🔔 Running alert — {now.strftime('%d %b %Y %H:%M IST')}")
    data = get_nifty_data()

    if data["error"]:
        logger.warning(f"Data fetch failed: {data['error']}")
        # Notify subscribers of the fetch failure
        for uid in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"⚠️ Could not fetch Nifty data today.\n_{data['error']}_\nPlease check manually.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
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

    logger.info(f"✅ Alert sent to {len(subscribers)} | {data['change_pct']:+.2f}%")

# ── Main ──────────────────────────────────────────────────────────────
def main():
    logger.info("🚀 Starting Nifty SIP Bot v3...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("test",   cmd_test))   # ← new test command
    app.add_handler(CallbackQueryHandler(button_handler))

    # ── FIX: PTB v20 uses cron weekday scheme ────────────────────────
    # Cron: Sun=0, Mon=1, Tue=2, Wed=3, Thu=4, Fri=5, Sat=6
    # So Mon–Fri = (1, 2, 3, 4, 5)  ← was wrong: (0,1,2,3,4) = Sun–Thu!
    alert_time = dtime(hour=ALERT_HOUR, minute=ALERT_MINUTE, tzinfo=IST)
    app.job_queue.run_daily(
        scheduled_alert,
        time=alert_time,
        days=(1, 2, 3, 4, 5),       # ✅ Mon=1 to Fri=5 in cron scheme
        name="daily_nifty_alert",
    )

    logger.info(f"✅ Scheduled: {ALERT_HOUR:02d}:{ALERT_MINUTE:02d} IST Mon–Fri (cron days 1–5)")
    logger.info(f"✅ Subscribers: {len(subscribers)}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
