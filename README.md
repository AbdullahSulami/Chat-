# 🗨️ Chatting App with Private Rooms

A real-time chatting application built with Python (Flask) and Vanilla JavaScript. Features private chat rooms that require a room number to join, making it easy to create private spaces for groups.

## ✨ Features

- **Private Rooms**: Join using a room number. Only users with the same number can see each other's messages.
- **Real-time Updates**: Powered by Server-Sent Events (SSE) for instant messaging.
- **Persistent Chat**: Messages are saved on the server in JSON files.
- **Rich Interaction**: Edit messages, delete messages, and react with emojis.
- **Premium Design**: Modern WhatsApp-style dark mode interface.
- **Render Ready**: Includes a self-ping mechanism to keep the server active 24/7 on Render's free tier.

## 🚀 Deployment on Render

This project is configured for easy deployment on [Render](https://render.com).

1. Create a new **Web Service**.
2. Connect your GitHub repository.
3. Use the following settings:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Add an Environment Variable:
   - `PORT`: `5000` (optional, the code detects Render's port automatically)

## 🛠️ Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application:
   ```bash
   python app.py
   ```
3. Open `http://localhost:5000` in your browser.

