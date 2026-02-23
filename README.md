# 🚀 Advanced Python Price Tracker & Automation Bot

This project is a high-performance, automated price monitoring tool designed to track product prices from major e-commerce platforms like **Amazon** and **eBay** in real-time.

## ✨ Key Features
* **Anti-Bot Bypass:** Utilizes `undetected-chromedriver` to mimic human behavior and avoid detection.
* **Smart Price Parsing:** Robust Regex-based logic to handle multiple currency formats (e.g., $1,299.99 or 1.299,99 EUR).
* **Automated Data Logging:** Tracks price history with timestamps in a structured CSV database using `pandas`.
* **Real-time Alerts:** Integrated notification system that triggers when a product hits a specific target price.
* **Professional Logging:** Uses `loguru` for clean, readable, and color-coded terminal outputs.

## 🛠️ Tech Stack
* **Language:** Python 3.10+
* **Automation:** Selenium / Undetected-Chromedriver
* **Data Analysis:** Pandas
* **Logging:** Loguru

## 📥 Installation & Usage
1. Clone the repo: `git clone https://github.com/Homauon1992/Advanced-Python-Price-Tracker-Automation.git`
2. Install dependencies: `pip install pandas undetected-chromedriver loguru selenium`
3. Run the script: `python price_tracker.py`

## 📊 Sample Output
The tool generates a `price_history.csv` containing:
- Timestamp
- Product Name
- Site Source
- Price