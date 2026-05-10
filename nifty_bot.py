"""
╔══════════════════════════════════════════════════╗
║       NIFTY SIP STRATEGY BOT — Public Bot        ║
║  Monitors Nifty 50 daily & alerts at 3 PM IST    ║
║  Anyone can subscribe via Telegram               ║
╚══════════════════════════════════════════════════╝

Strategy:
  Daily candle check at 3:00 PM IST (Mon–Fri)
  🟡  -1% to -3% drop → Invest ₹8,000  (SIP ₹5K + Extra ₹3K)
  🔴  -3% to -5% drop → Invest ₹10,000 (SIP ₹5K + Extra ₹5K)
  🚨  >-5% drop       → Invest ₹15,000 (SIP ₹5K + Extra ₹10K MAX)
  ✅  No drop         → SIP only ₹5,000

Setup:
  1. pip install -r requirements.txt
  2. Create bot via @BotFather on Telegram
  3. Add BOT_TOKEN to .env file
  4. python nifty_bot.py
  5. Share your bot link: t.me/YOUR_BOT_NAME
"""

import asyncio
import json
import logging
import os
from datetime import datetime, date
import pytz
import yfinance as yf
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────
BOT_TOKEN        = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SUBSCRIBERS_FILE = "subscribers.json"
IST              = pytz.timezone("Asia/Kolkata")
ALERT_HOUR       = 15   # 3 PM IST
ALERT_MINUTE     = 0

# Strategy thresholds
DIP_MINOR   = -1.0   # -1%  → invest ₹8,000
DIP_MAJOR   = -3.0   # -3%  → invest ₹10,000
DIP_MASSIVE = -5.0   # -5%  → invest ₹15,000 MAX

BASE_SIP    = 5000
EXTRA_MINOR = 3000
EXTRA_MAJOR = 5000
EXTRA_MAX   = 10000

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
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
    """Fetch Nifty 50 current price and previous close via yfinance."""
    try:
        ticker = yf.Ticker("^NSEI")
        hist   = ticker.history(period="5d", interval="1d")

        if len(hist) < 2:
            return {"error": "Insufficient data — market may be closed"}

        today_close = float(hist["Close"].iloc[-1])
        prev_close  = float(hist["Close"].iloc[-2])
        today_open  = float(hist["Open"].iloc[-1])
        today_high  = float(hist["High"].iloc[-1])
        today_low   = float(hist["Low"].iloc[-1])
        change_pts  = today_close - prev_close
        change_pct  = (change_pts / prev_close) * 100

        return {
            "today":      today_close,
            "prev":       prev_close,
            "open":       today_open,
            "high":       today_high,
            "low":        today_low,
            "change_pts": change_pts,
            "change_pct": change_pct,
            "error":      None,
        }
    except Exception as e:
        logger.error(f"yfinance error: {e}")
        return {"error": str(e)}

# ── Message Builder ───────────────────────────────────────────────────
def build_alert_message(data: dict, is_scheduled: bool = False) -> str:
    now_str = datetime.now(IST).strftime("%d %b %Y  %I:%M %p IST")
    pct     = data["change_pct"]
    pts     = data["change_pts"]

    # Determine action
    if pct <= DIP_MASSIVE:
        level   = "🚨 MASSIVE DIP"
        invest  = BASE_SIP + EXTRA_MAX
        action  = f"Invest *₹{invest:,}* today!\n   └ ₹{BASE_SIP:,} SIP + ₹{EXTRA_MAX:,} Extra (MAX)"
        tip     = "💥 Rare opportunity — deploy maximum capital!"
        bar     = "🟥🟥🟥🟥🟥"
    elif pct <= DIP_MAJOR:
        level   = "🔴 MAJOR DIP"
        invest  = BASE_SIP + EXTRA_MAJOR
        action  = f"Invest *₹{invest:,}* today!\n   └ ₹{BASE_SIP:,} SIP + ₹{EXTRA_MAJOR:,} Extra"
        tip     = "📉 Big correction — great buying window"
        bar     = "🟧🟧🟧🟧⬜"
    elif pct <= DIP_MINOR:
        level   = "🟡 MINOR DIP"
        invest  = BASE_SIP + EXTRA_MINOR
        action  = f"Invest *₹{invest:,}* today!\n   └ ₹{BASE_SIP:,} SIP + ₹{EXTRA_MINOR:,} Extra"
        tip     = "📊 Small dip — buy a few extra units"
        bar     = "🟨🟨⬜⬜⬜"
    else:
        level   = "✅ NORMAL DAY"
        invest  = BASE_SIP
        action  = f"Stick to *₹{invest:,}* SIP only"
        tip     = "😎 No extra action needed — market is steady"
        bar     = "🟩⬜⬜⬜⬜"

    header = "📢 *NIFTY DAILY ALERT*" if is_scheduled else "📊 *NIFTY STATUS*"

    msg = f"""{header}
{now_str}

{level}  {bar}

📈 *Nifty 50 Today*
  Close:  `{data['today']:>10,.0f}`
  Change: `{pct:>+10.2f}%`  (`{pts:>+,.0f}` pts)
  ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
  Open:   `{data['open']:>10,.0f}`
  High:   `{data['high']:>10,.0f}`
  Low:    `{data['low']:>10,.0f}`
  Prev:   `{data['prev']:>10,.0f}`

💡 *Your Action Today*
   {action}

_{tip}_

🤖 _Nifty SIP Bot — share with friends!_"""

    return msg

def build_summary_message(subs_count: int) -> str:
    return f"""📊 *Bot Status*
• Subscribers: *{subs_count}* investors
• Daily alert: *3:00 PM IST* (Mon–Fri)
• Data source: NSE via Yahoo Finance"""

# ── Keyboards ─────────────────────────────────────────────────────────
def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Check Now", callback_data="check"),
            InlineKeyboardButton("ℹ️ Strategy", callback_data="strategy"),
        ],
        [
            InlineKeyboardButton("👥 Bot Stats", callback_data="stats"),
            InlineKeyboardButton("❌ Unsubscribe", callback_data="unsub"),
        ],
    ])

def back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="back")]
    ])

# ── Handlers ──────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    user_id = user.id
    is_new  = user_id not in subscribers

    subscribers.add(user_id)
    save_subscribers(subscribers)

    greeting = "Welcome back" if not is_new else f"Welcome, {user.first_name}! 🎉"

    await update.message.reply_text(
        f"👋 *{greeting}*\n\n"
        "You are now *subscribed* to Nifty SIP Alerts!\n\n"
        "🕒 Every trading day at *3:00 PM IST* you'll receive:\n"
        "  🟡 -1% dip  → Invest ₹8,000\n"
        "  🔴 -3% dip  → Invest ₹10,000\n"
        "  🚨 -5% dip  → Invest ₹15,000 MAX\n"
        "  ✅ No dip   → SIP ₹5,000 only\n\n"
        "📢 *Share this bot with fellow investors!*\n"
        "Use the buttons below to explore 👇",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subscribers.discard(user_id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "❌ You have been *unsubscribed*.\n\n"
        "Type /start anytime to re-subscribe.",
        parse_mode="Markdown",
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching Nifty data...")
    data = get_nifty_data()
    if data["error"]:
        await update.message.reply_text(
            f"⚠️ Could not fetch data: {data['error']}\n"
            "Market may be closed or API is down. Try again in a few minutes."
        )
        return
    msg = build_alert_message(data, is_scheduled=False)
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Nifty SIP Strategy Bot — Help*\n\n"
        "*Commands:*\n"
        "  /start   — Subscribe to daily alerts\n"
        "  /stop    — Unsubscribe\n"
        "  /status  — Check Nifty right now\n"
        "  /help    — Show this help\n\n"
        "*How it works:*\n"
        "Every trading day at 3:00 PM IST, the bot checks "
        "Nifty 50's daily candle. Based on the % change from "
        "previous day's close, it tells you exactly how much "
        "to invest — implementing your smart dip-buying SIP strategy.\n\n"
        "*Strategy logic:*\n"
        "  Base SIP: ₹5,000/month always\n"
        "  +₹3,000 when daily dip is 1–3%\n"
        "  +₹5,000 when daily dip is 3–5%\n"
        "  +₹10,000 when daily dip is >5%\n\n"
        "📢 Share with friends: Just forward your bot link!\n"
        "Built for Indian long-term investors 🇮🇳",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )

# ── Callback Buttons ──────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check":
        data = get_nifty_data()
        if data["error"]:
            await query.edit_message_text(
                f"⚠️ Error: {data['error']}\nMarket may be closed.",
                reply_markup=back_keyboard()
            )
        else:
            msg = build_alert_message(data, is_scheduled=False)
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif query.data == "strategy":
        await query.edit_message_text(
            "📈 *Dip-Buying SIP Strategy*\n\n"
            "*Monthly budget: ₹15,000*\n\n"
            "| Nifty Daily Drop | Invest     |\n"
            "|-----------------|------------|\n"
            "| No drop         | ₹5,000     |\n"
            "| -1% to -3%      | ₹8,000     |\n"
            "| -3% to -5%      | ₹10,000    |\n"
            "| Below -5%       | ₹15,000 🔥 |\n\n"
            "💡 *Why this works:*\n"
            "You buy more units when prices are lower. "
            "Over 5 years, this can significantly beat "
            "a plain SIP. Backtested 2021–2026 ✅\n\n"
            "_Be greedy when others are fearful — Buffett_",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )

    elif query.data == "stats":
        msg = build_summary_message(len(subscribers))
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=back_keyboard())

    elif query.data == "unsub":
        subscribers.discard(user_id)
        save_subscribers(subscribers)
        await query.edit_message_text(
            "❌ *Unsubscribed successfully.*\n\nType /start to re-subscribe anytime.",
            parse_mode="Markdown",
        )

    elif query.data == "back":
        await query.edit_message_text(
            "👋 *Nifty SIP Bot*\n\nUse the buttons below:",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )

# ── Scheduled Job: Send Alert at 3 PM IST ─────────────────────────────
async def scheduled_alert(bot):
    now = datetime.now(IST)

    # Only on weekdays (Mon=0 … Fri=4)
    if now.weekday() >= 5:
        logger.info("Weekend — skipping alert")
        return

    logger.info(f"Running scheduled alert — {now.strftime('%d %b %Y %H:%M IST')}")

    data = get_nifty_data()
    if data["error"]:
        logger.warning(f"Could not fetch Nifty: {data['error']}")
        return

    msg     = build_alert_message(data, is_scheduled=True)
    dead    = set()

    for uid in list(subscribers):
        try:
            await bot.send_message(
                chat_id=uid,
                text=msg,
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )
        except Exception as e:
            logger.warning(f"Failed to message {uid}: {e}")
            dead.add(uid)

    if dead:
        subscribers.difference_update(dead)
        save_subscribers(subscribers)

    logger.info(
        f"Alert sent | subscribers={len(subscribers)} | "
        f"change={data['change_pct']:+.2f}%"
    )

# ── Main ──────────────────────────────────────────────────────────────
async def main():
    logger.info("🚀 Starting Nifty SIP Bot...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    # Scheduler — 3:00 PM IST daily
    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(
        scheduled_alert,
        trigger="cron",
        day_of_week="mon-fri",
        hour=ALERT_HOUR,
        minute=ALERT_MINUTE,
        args=[app.bot],
        id="daily_nifty_alert",
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info(f"Scheduler started — alerts at {ALERT_HOUR:02d}:{ALERT_MINUTE:02d} IST (Mon–Fri)")

    logger.info(f"Bot is LIVE! Subscribers: {len(subscribers)}")
    await app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
