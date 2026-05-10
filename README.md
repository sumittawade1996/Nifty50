# 🤖 Nifty SIP Strategy Bot

A free, public Telegram bot that monitors Nifty 50 daily
and alerts subscribers at 3 PM IST with smart SIP investment signals.

## 📱 What subscribers see

Every trading day at 3:00 PM IST, all subscribers get:

🟡 -1% to -3% drop → "Invest ₹8,000 today!"
🔴 -3% to -5% drop → "Invest ₹10,000 today!"
🚨 >-5% drop       → "Invest ₹15,000 MAX!"
✅ No drop          → "SIP ₹5,000 only"

## ⚡ Setup in 5 Steps

### Step 1 — Create Telegram Bot (5 min)
1. Open Telegram → search @BotFather
2. Send /newbot → give it a name (e.g. "Nifty SIP Alert Bot")
3. Give it a username (e.g. niftysip_alert_bot)
4. Copy the API token BotFather gives you

### Step 2 — Install & Run Locally
```bash
git clone <your-repo>
cd nifty_sip_bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env and paste your BOT_TOKEN
python nifty_bot.py
```

### Step 3 — Test It
- Open Telegram → search your bot name
- Send /start → you should see welcome message
- Send /status → should show current Nifty price

### Step 4 — Deploy Free (so it runs 24/7)

#### Option A: Railway.app (Recommended — Free)
1. Push code to GitHub
2. Go to railway.app → New Project → Deploy from GitHub
3. Add environment variable: BOT_TOKEN = your_token
4. Deploy! Your bot runs 24/7 for free

#### Option B: Render.com (Free)
1. Push to GitHub
2. New Web Service on Render → connect repo
3. Build: pip install -r requirements.txt
4. Start: python nifty_bot.py
5. Add BOT_TOKEN in Environment Variables

#### Option C: PythonAnywhere (Free)
1. Create free account at pythonanywhere.com
2. Upload files → install requirements in console
3. Set up Always-On task (paid) OR use scheduled task

### Step 5 — Share with Everyone!
Your bot link: t.me/YOUR_BOT_USERNAME

Share it in:
- WhatsApp groups of investor friends
- Zerodha community / Varsity forum
- Reddit r/IndiaInvestments
- Twitter/X with #NiftyAlert hashtag

## 🛠️ Bot Commands

| Command   | Action                        |
|-----------|-------------------------------|
| /start    | Subscribe to daily alerts     |
| /stop     | Unsubscribe                   |
| /status   | Check Nifty right now         |
| /help     | Show help & strategy details  |

## 📊 Strategy Logic

Daily candle (checked at 3 PM IST):

| Nifty Change | Invest   | = SIP + Extra       |
|--------------|----------|---------------------|
| No drop      | ₹5,000   | ₹5,000 + ₹0         |
| -1% to -3%   | ₹8,000   | ₹5,000 + ₹3,000     |
| -3% to -5%   | ₹10,000  | ₹5,000 + ₹5,000     |
| Below -5%    | ₹15,000  | ₹5,000 + ₹10,000    |

## 🆓 100% Free Stack

- Telegram Bot API — Free forever
- yfinance (Yahoo Finance) — Free NSE data
- Railway.app hosting — Free tier
- No database needed (JSON file storage)

## ⚠️ Disclaimer

This bot is for informational purposes only and does not
constitute financial advice. Always consult a SEBI-registered
advisor before investing.
