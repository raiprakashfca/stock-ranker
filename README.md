📊 TMV Stock Ranking Dashboard
Version: v1.0-Stable-Apr25
Last Updated: April 2025

🚀 About the App
The TMV Stock Ranking Dashboard is a multi-timeframe stock analyzer designed for Indian markets using real market data.
It auto-ranks stocks based on Trend, Momentum, and Volume indicators across 15m and 1d timeframes.

🛠️ Core Features
🔐 Zerodha API Login & Token Management

Sidebar login with request token generation

Auto token verification before app proceeds

📈 Live TMV Stock Ranking

Fetches data from Google Sheet (BackgroundAnalysisStore > LiveScores tab)

Green/Red color coding on % Change

Clean multi-timeframe TMV Score display

🕒 Auto-Refresh System

Full app refreshes automatically every 1 minute

Countdown timer visible at top

All timestamps in Asia/Kolkata (IST) timezone

📥 Download Today's TMV Table

Export TMV table instantly as a CSV file

📘 TMV Indicator Explainer

Select any stock to view real-time indicator values (EMA, RSI, MACD, ADX, OBV, MFI)

15-minute and 1-day inputs separated with detailed explanations

➕ Admin Panel — Add New Stock

Search NSE stocks (live from Zerodha instrument list)

Add new stock to TMV Dashboard dynamically

Instant success toast and auto-refresh after addition

📋 Requirements
Python 3.8+

Streamlit

gspread

kiteconnect

pandas, pandas-ta

matplotlib

base64, os, time, pytz

All dependencies can be installed via:

bash
Copy
Edit
pip install -r requirements.txt
🔑 Environment and Secrets Required
Store secrets in .streamlit/secrets.toml as:

toml
Copy
Edit
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "xxx"
private_key = "-----BEGIN PRIVATE KEY-----\\nxxx\\n-----END PRIVATE KEY-----\\n"
client_email = "xxx@xxx.iam.gserviceaccount.com"
client_id = "xxx"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "xxx"

[other_secrets]
You must also configure:

Zerodha App (API Key and API Secret)

Google Sheet URLs:

BackgroundAnalysisStore (LiveScores Tab)

✨ How to Run
bash
Copy
Edit
streamlit run app.py
📌 Notes
App auto-refreshes every 60 seconds.

Access token must be freshly generated daily via sidebar login panel.

All times displayed in IST timezone.

🧠 Future Enhancements (Optional)
Add chart previews for stock indicators

Add Trend Reversal Probability badges

Integrate Telegram alerts for top TMV movers

📎 License
MIT License | © 2025 Prakash Rai

📫 Contact
For support or collaboration:

Email: raiprakashfca@gmail.com

GitHub: [your_github_profile]

🎯 Let's Build Smarter Trading Tools Together!
