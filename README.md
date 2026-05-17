# 📰 Daily News Summarizer AI

> **Eliminate doom-scrolling.** Get a curated, AI-powered tech digest delivered straight to your WhatsApp — every morning, automatically.

## 🧠 Overview

**Daily_News_Summarizer_AI** is a personal data-engineering and AI assistant that fetches, filters, and delivers a tailored tech-news digest to your WhatsApp daily — fully automated, no manual effort required.

It focuses on what matters most to data engineers and AI practitioners:

| Domain | Coverage |
|---|---|
| 🔷 Databricks | Platform updates, releases, best practices |
| ⚡ Apache Spark | Performance tips, new features, ecosystem news |
| 🏗️ Data Engineering | Architecture, tools, workflows |
| 🤖 AI / LLMs | Model releases, research, industry moves |

---

## ✨ Key Features

- **🎯 Targeted Scraping** — Tracks specific technical domains and top content creators, cutting through the noise.
- **🤖 AI-Powered Filtering** — Uses the Gemini API to analyze content and extract only high-value updates from the last 24 hours.
- **📲 Automated Delivery** — Formats curated insights into a clean, readable digest and sends it via Twilio's WhatsApp API.

---

## 🚀 Getting Started

### Prerequisites

Before you begin, make sure you have:

- ✅ Python **3.10** or higher
- ✅ A **Gemini API Key** ([Google AI Studio](https://aistudio.google.com/))
- ✅ A **Twilio Account** configured with the WhatsApp Sandbox

---

### Local Setup & Execution

**1. Clone the repository**
```bash
git clone https://github.com/AvinashNarala/Daily_News_Summarizer_AI.git
cd Daily_News_Summarizer_AI
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Configure environment variables**

Copy the example env file:
```bash
cp .env.example .env
```

Open `.env` and fill in your credentials:
```env
GEMINI_API_KEY=your_gemini_api_key_here
TWILIO_ACCOUNT_SID=your_twilio_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886   # Default Twilio Sandbox number
TARGET_WHATSAPP_NUMBER=whatsapp:+1XXXXXXXXXX   # Your verified phone number
```

**4. Run the script**
```bash
python news_feed_summarizer.py
```

---

## ⚙️ Automation & Deployment (GitHub Actions)

Want it to run **automatically every day** without touching your computer? Use GitHub Actions — it's free.

### Step 1 — Add the Workflow File

Create `.github/workflows/daily_digest.yml` in your repository:

```yaml
name: Daily Tech News Digest

on:
  schedule:
    - cron: '0 7 * * *'   # Runs daily at 07:00 UTC — adjust to your timezone
  workflow_dispatch:        # Allows manual trigger from the GitHub Actions UI

jobs:
  run-automation:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run Summarizer
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          TWILIO_ACCOUNT_SID: ${{ secrets.TWILIO_ACCOUNT_SID }}
          TWILIO_AUTH_TOKEN: ${{ secrets.TWILIO_AUTH_TOKEN }}
          TWILIO_WHATSAPP_NUMBER: ${{ secrets.TWILIO_WHATSAPP_NUMBER }}
          TARGET_WHATSAPP_NUMBER: ${{ secrets.TARGET_WHATSAPP_NUMBER }}
        run: python news_feed_summarizer.py
```

### Step 2 — Configure Repository Secrets

> ⚠️ **Never commit your `.env` file to GitHub.** Use GitHub Secrets to keep credentials safe.

1. Go to your repository on GitHub
2. Navigate to **Settings → Secrets and variables → Actions**
3. Click **New repository secret**
4. Add each of the 5 keys from your `.env` file as individual secrets:

| Secret Name | Description |
|---|---|
| `GEMINI_API_KEY` | Your Google AI Studio API key |
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_WHATSAPP_NUMBER` | Twilio sandbox WhatsApp number |
| `TARGET_WHATSAPP_NUMBER` | Your personal WhatsApp number |

Once saved, GitHub Actions will securely inject these into each run — no hardcoding required. ✅

---

## 📁 Project Structure

```
Daily_News_Summarizer_AI/
├── .github/
│   └── workflows/
│       └── daily_digest.yml    # GitHub Actions automation
├── news_feed_summarizer.py     # Main script
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
└── README.md
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open a pull request or file an issue.

---

*Built for data engineers who want signal, not noise.*
