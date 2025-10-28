from flask import Flask, render_template, request, redirect, url_for, jsonify
from telethon import TelegramClient, events
import asyncio, threading, time, traceback

app = Flask(__name__)

# Global state
api_id = None
api_hash = None
bot_token = None
client = None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

chats = []
forward_from = None
forward_to = None
keyword_filter = ""
delay_seconds = 0
is_running = False
logs = []
restart_enabled = True  # 👈 Auto-restart flag


@app.route('/', methods=['GET', 'POST'])
def index():
    global api_id, api_hash, bot_token, chats
    if request.method == 'POST':
        api_id = int(request.form['api_id'])
        api_hash = request.form['api_hash']
        bot_token = request.form['bot_token']
        threading.Thread(target=lambda: loop.run_until_complete(load_chats())).start()
        return redirect(url_for('select_chats'))
    return render_template('index.html')


@app.route('/select', methods=['GET', 'POST'])
def select_chats():
    global forward_from, forward_to, keyword_filter, delay_seconds
    if request.method == 'POST':
        forward_from = int(request.form['from_chat'])
        forward_to = int(request.form['to_chat'])
        keyword_filter = request.form.get('keyword', '').lower()
        delay = request.form['delay']
        delay_seconds = 180 if delay == '3' else 300 if delay == '5' else 600
        threading.Thread(target=start_bot).start()
        return redirect(url_for('dashboard'))
    return render_template('select.html', chats=chats)


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    global is_running
    if request.method == 'POST':
        if 'stop' in request.form:
            stop_forwarding()
        elif 'send_message' in request.form:
            msg = request.form['custom_message']
            asyncio.run_coroutine_threadsafe(send_custom_message(msg), loop)
    return render_template('dashboard.html',
                           keyword=keyword_filter,
                           delay=delay_seconds,
                           running=is_running)


@app.route('/logs')
def get_logs():
    """Endpoint for AJAX polling logs"""
    return jsonify(logs[-100:])  # last 100 log lines


async def load_chats():
    global client, chats
    try:
        client = TelegramClient('forwardbot', api_id, api_hash)
        await client.start(bot_token=bot_token)
        chats = []
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                chats.append((dialog.id, dialog.name))
        logs.append(f"✅ Loaded {len(chats)} chats.")
    except Exception as e:
        logs.append(f"❌ Error loading chats: {e}")


def start_bot():
    """Start the Telegram forwarding bot in an async loop with auto-reconnect"""
    global client, is_running

    async def bot_main():
        global is_running
        try:
            @client.on(events.NewMessage(chats=forward_from))
            async def handler(event):
                if not is_running:
                    return
                text = event.message.message.lower() if event.message.message else ""
                if keyword_filter and keyword_filter not in text:
                    logs.append(f"⏩ Skipped (no keyword): {text[:40]}")
                    return
                logs.append(f"⏳ Waiting {delay_seconds}s to forward...")
                await asyncio.sleep(delay_seconds)
                await client.send_message(forward_to, event.message)
                logs.append(f"✅ Forwarded message ID {event.id}")

            is_running = True
            logs.append("🤖 Bot started and running...")

            # Start the restart monitor in another thread
            threading.Thread(target=restart_watcher, daemon=True).start()

            await client.run_until_disconnected()
        except Exception as e:
            logs.append(f"❌ Bot crashed: {e}")
            traceback.print_exc()
            await restart_bot()

    loop.create_task(bot_main())


def stop_forwarding():
    global is_running
    is_running = False
    logs.append("🔴 Bot stopped by user")


async def send_custom_message(msg):
    if client and forward_to:
        try:
            await client.send_message(forward_to, msg)
            logs.append(f"📝 Sent custom message: {msg}")
        except Exception as e:
            logs.append(f"⚠️ Failed to send message: {e}")


def restart_watcher():
    """Background thread that keeps the bot alive"""
    global client, restart_enabled
    while restart_enabled:
        time.sleep(10)
        try:
            if not client.is_connected():
                logs.append("⚠️ Disconnected — trying to reconnect...")
                asyncio.run_coroutine_threadsafe(reconnect_client(), loop)
        except Exception as e:
            logs.append(f"⚠️ Connection check failed: {e}")


async def reconnect_client():
    """Reconnect client safely"""
    global client
    try:
        await client.disconnect()
        await client.connect()
        if not await client.is_user_authorized():
            await client.start(bot_token=bot_token)
        logs.append("✅ Reconnected successfully!")
    except Exception as e:
        logs.append(f"❌ Reconnect failed: {e}")


async def restart_bot():
    """Restart entire bot process if it crashes"""
    global client, is_running
    try:
        is_running = False
        logs.append("♻️ Restarting bot automatically...")
        await client.disconnect()
        await asyncio.sleep(5)
        await client.connect()
        if not await client.is_user_authorized():
            await client.start(bot_token=bot_token)
        start_bot()
    except Exception as e:
        logs.append(f"❌ Restart failed: {e}")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
