# 📈 Stock Live Monitor

A real-time stock price monitoring application with automatic updates, 10:30 AM high/low tracking, and color-coded status indicators.

## Features

- ✅ Real-time stock price fetching from Yahoo Finance
- ✅ PostgreSQL database for persistent storage
- ✅ Automatic updates every 30 seconds during market hours
- ✅ 10:30 AM high/low capture
- ✅ Color-coded status indicators (RED/GREEN/AMBER/NEUTRAL)
- ✅ Market hours detection (9:15 AM - 3:30 PM IST)
- ✅ Beautiful responsive UI with Tailwind CSS

## Tech Stack

**Backend:**
- Flask
- PostgreSQL
- SQLAlchemy
- Yahoo Finance API
- APScheduler

**Frontend:**
- React
- Tailwind CSS
- Lucide Icons

## Installation

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm start
```

## Environment Variables

**Backend (.env):**
```
DATABASE_URL=postgresql://localhost/stockmonitor
PORT=5000
```

**Frontend (.env):**
