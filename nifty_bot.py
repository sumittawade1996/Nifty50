"""
Nifty SIP Strategy Bot — v4 FINAL
Fixes:
  1. NSE India API as PRIMARY data source (real-time, most reliable)
  2. yfinance with proper MultiIndex column fix as BACKUP
  3. Correct PTB v20 cron days: (1,2,3,4,5) = Mon–Fri
  4. /test command to fire alert manually anytime
"""

import json
import logging
import os
import time as _time
from datetime import time as dtime
import pytz
import requests
import yfinance as yf
import pandas as pd
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

# ── Method 1: NSE India Official API ─────────────────────────────────
def fetch_from_nse() -> dict:
    """
    Fetches live Nifty 50 data directly from NSE India.
    Most accurate — same source as NSE website.
    """
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    }

    # Step 1 — get cookies from NSE homepage
    session.get("https://www.nseindia.com", headers=headers, timeout=10)
    _time.sleep(1)

    # Step 2 — fetch index data
    headers["Accept"] = "application/json"
    r = session.get(
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050",
        headers=headers,
        timeout=10,
    )
    r.raise_for_status()
    raw = r.json()

    # The first item in data[] is the index summary row
    idx = raw["data"][0]

    last  = float(idx["last"])
    prev  = float(idx["previousClose"])
    open_ = float(idx.get("open",    last))
    high  = float(idx.get("dayHigh", last))
    low   = float(idx.get("dayLow",  last))

    change_pts = last - prev
    change_pct = (change_pts / prev) * 100

    logger.info(f"✅ NSE API: Nifty={last:.0f}  change={change_pct:+.2f}%")
    return {
        "today": last, "prev": prev, "open": open_,
        "high": high, "low": low,
        "change_pts": change_pts, "change_pct": change_pct,
        "error": None,
    }

# ── Method 2: yfinance with MultiIndex fix ────────────────────────────
def fetch_from_yfinance() -> dict:
    """
    Backup: yfinance with proper handling of newer MultiIndex column format.
    yfinance v0.2+ returns columns like (Close, ^NSEI) — we flatten them.
    """
    for ticker in ["^NSEI", "NIFTY50.NS"]:
        try:
            hist = yf.download(
                ticker, period="10d", interval="1d",
                progress=False, auto_adjust=True,
            )

            # ── Fix MultiIndex columns (yfinance v0.2+ issue) ─────────
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)

            # Remove duplicate columns after flattening
            hist = hist.loc[:, ~hist.columns.duplicated(keep="first")]

            # Drop rows with missing Close
            hist = hist[hist["Close"].notna()]

            if len(hist) < 2:
                logger.warning(f"yfinance {ticker}: only {len(hist)} valid rows")
                continue

            today = float(hist["Close"].iloc[-1])
            prev  = float(hist["Close"].iloc[-2])
            chg   = today - prev
            pct   = (chg / prev) * 100

            logger.info(f"✅ yfinance {ticker}: Nifty={today:.0f}  change={pct:+.2f}%")
            return {
                "today": today, "prev": prev,
                "open":  float(hist["Open"].iloc[-1]),
                "high":  float(hist["High"].iloc[-1]),
                "low":   float(hist["Low"].iloc[-1]),
                "change_pts": chg, "change_pct": pct,
                "error": None,
            }
        except Exception as e:
            logger.warning(f"yfinance {ticker} failed: {e}")

    return {"error": "yfinance: all tickers failed"}

# ── Combined fetcher with fallback ────────────────────────────────────
def get_nifty_data() -> dict:
    """
    Tries NSE API first (most reliable), falls back to yfinance.
    Retries each method up to 2 times.
    """
    for attempt in range(2):
        # Primary: NSE India API
        try:
            return fetch_from_nse()
        except Exception as e:
            logger.warning(f"NSE API attempt {attempt+1} failed: {e}")

        # Backup: yfinance
        try:
            result = fetch_from_yfinance()
            if not result.get("error"):
                return result
        except Exception as e:
            logger.warning(f"yfinance attempt {attempt+1} failed: {e}")

        if attempt == 0:
            logger.info("Retrying in 3 seconds...")
            _time.sleep(3)

    return {
        "error": (
            "Could not fetch Nifty data from NSE or Yahoo Finance.\n"
            "Market may be closed or both APIs are temporarily down.\n"
            "Please check manually at nseindia.com"
        )
    }

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

# ── Commands ──────────────────────────────────────────────────────────
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
        "Commands: /status /test /help\n\n"
        "Use the buttons below 👇",
        parse_mode="Markdown", reply_markup=main_kb(),
    )

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_user.id)
    save_subscribers(subscribers)
    await update.message.reply_text(
        "❌ *Unsubscribed.* Type /start anytime to re-subscribe.",
        parse_mode="Markdown",
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching Nifty data...")
    data = get_nifty_data()
    if data["error"]:
        await msg.edit_text(f"⚠️ {data['error']}")
        return
    await msg.edit_text(
        build_message(data, scheduled=False),
        parse_mode="Markdown", reply_markup=main_kb(),
    )

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually fires today's alert — use to test without waiting for 3 PM."""
    await update.message.reply_text(
        f"🧪 *Test alert firing...*\nSending to {len(subscribers)} subscriber(s)",
        parse_mode="Markdown",
    )
    await scheduled_alert(context)
    await update.message.reply_text("✅ Test complete! Check above for the alert.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Nifty SIP Bot — Help*\n\n"
        "Commands:\n"
        "  /start  — Subscribe\n"
        "  /stop   — Unsubscribe\n"
        "  /status — Live Nifty check\n"
        "  /test   — Fire today's alert now\n"
        "  /help   — This message\n\n"
        "📅 Auto alert: *3:00 PM IST* (Mon–Fri)\n"
        "📡 Data: NSE India API → Yahoo Finance fallback",
        parse_mode="Markdown", reply_markup=main_kb(),
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
            "_Be greedy when others are fearful — Buffett_",
            parse_mode="Markdown", reply_markup=back_kb(),
        )
    elif q.data == "stats":
        await q.edit_message_text(
            f"📊 *Bot Stats*\n"
            f"• Subscribers: *{len(subscribers)}*\n"
            f"• Alert: *3:00 PM IST* Mon–Fri\n"
            f"• Source: NSE India API",
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
        logger.info("Weekend — skipping")
        return

    logger.info(f"🔔 Alert — {now.strftime('%d %b %Y %H:%M IST')}")
    data = get_nifty_data()

    if data["error"]:
        logger.warning(f"Fetch failed: {data['error']}")
        for uid in list(subscribers):
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=f"⚠️ Could not fetch Nifty data today.\n{data['error']}",
                )
            except Exception:
                pass
        return

    msg  = build_message(data, scheduled=True)
    dead = set()
    for uid in list(subscribers):
        try:
            await context.bot.send_message(
                chat_id=uid, text=msg,
                parse_mode="Markdown", reply_markup=main_kb(),
            )
        except Exception as e:
            logger.warning(f"Failed → {uid}: {e}")
            dead.add(uid)

    if dead:
        subscribers.difference_update(dead)
        save_subscribers(subscribers)

    logger.info(f"✅ Sent to {len(subscribers)} | {data['change_pct']:+.2f}%")

# ── Main ──────────────────────────────────────────────────────────────
def main():
    logger.info("🚀 Nifty SIP Bot v4 starting...")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("stop",   cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("test",   cmd_test))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))

    # PTB v20 cron scheme: Sun=0 Mon=1 Tue=2 Wed=3 Thu=4 Fri=5 Sat=6
    alert_time = dtime(hour=ALERT_HOUR, minute=ALERT_MINUTE, tzinfo=IST)
    app.job_queue.run_daily(
        scheduled_alert,
        time=alert_time,
        days=(1, 2, 3, 4, 5),    # ✅ Mon–Fri
        name="daily_nifty_alert",
    )

    logger.info(f"✅ Alert scheduled: {ALERT_HOUR:02d}:{ALERT_MINUTE:02d} IST Mon–Fri")
    logger.info(f"✅ Subscribers: {len(subscribers)}")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
