import threading
import requests
import queue
import time
import json
import os
from flask import Flask, render_template, request, jsonify, redirect, Response

app = Flask(__name__, template_folder='.')

# File paths for persistent storage
MESSAGES_FILE = 'chat_messages.json'
REACTIONS_FILE = 'chat_reactions.json'
RECEIPTS_FILE = 'chat_receipts.json'

# In-memory storage
messages = [] # Each msg will have a 'room' key
active_users = {} # Room -> IP -> {"nickname": str, "last_seen": timestamp, "avatar": str}
message_id_counter = 0
message_reactions = {} # message_id -> {emoji: [ip1, ip2, ...]}
read_receipts = {} # message_id -> [ip1, ip2, ...]

# SSE Queues for real-time updates
update_queues = []

def notify_clients(room='public'):
    """Notify all connected SSE clients in a specific room that an update is available."""
    for q, q_room in update_queues:
        if q_room == str(room):
            q.put(True)

# Centralized saving logic with periodic sync if needed
def save_all_data():
    try:
        with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        with open(REACTIONS_FILE, 'w', encoding='utf-8') as f:
            # Convert keys to strings for JSON
            json_reactions = {str(k): v for k, v in message_reactions.items()}
            json.dump(json_reactions, f, ensure_ascii=False, indent=2)
        with open(RECEIPTS_FILE, 'w', encoding='utf-8') as f:
            # Convert keys to strings for JSON
            json_receipts = {str(k): v for k, v in read_receipts.items()}
            json.dump(json_receipts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")

# Load existing data from files
def load_data():
    global messages, message_reactions, read_receipts, message_id_counter
    
    # Load messages
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                messages = json.load(f)
                if messages:
                    message_id_counter = max(msg['id'] for msg in messages) + 1
                print(f"✅ Loaded {len(messages)} messages from {MESSAGES_FILE}")
        except Exception as e:
            print(f"⚠️ Error loading messages: {e}")
    
    # Load reactions
    if os.path.exists(REACTIONS_FILE):
        try:
            with open(REACTIONS_FILE, 'r', encoding='utf-8') as f:
                loaded_reactions = json.load(f)
                message_reactions = {int(k): v for k, v in loaded_reactions.items()}
                print(f"✅ Loaded reactions from {REACTIONS_FILE}")
        except Exception as e:
            print(f"⚠️ Error loading reactions: {e}")
    
    # Load read receipts
    if os.path.exists(RECEIPTS_FILE):
        try:
            with open(RECEIPTS_FILE, 'r', encoding='utf-8') as f:
                loaded_receipts = json.load(f)
                read_receipts = {int(k): v for k, v in loaded_receipts.items()}
                print(f"✅ Loaded read receipts from {RECEIPTS_FILE}")
        except Exception as e:
            print(f"⚠️ Error loading receipts: {e}")

# --- CAPTIVE PORTAL DETECTION ROUTES ---
@app.route('/generate_204') # Android
@app.route('/hotspot-detect.html') # iOS
@app.route('/ncsi.txt') # Windows
@app.route('/success.txt') # General
def captive_portal():
    return redirect('/')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/my_ip')
def get_ip():
    return jsonify({"ip": request.remote_addr})

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    room = data.get('room', 'public')
    ip = request.remote_addr
    nick = data.get('nickname', 'Anonymous')
    avatar = data.get('avatar', '')
    
    if room not in active_users:
        active_users[room] = {}
        
    active_users[room][ip] = {
        "nickname": nick,
        "avatar": avatar,
        "last_seen": time.time()
    }
    return jsonify({"status": "ok"})

@app.route('/active_users')
def get_active_users():
    room = request.args.get('room', 'public')
    now = time.time()
    
    if room not in active_users:
        return jsonify({})
        
    for ip in list(active_users[room].keys()):
        if now - active_users[room][ip]['last_seen'] > 15:
            del active_users[room][ip]
            
    return jsonify(active_users[room])

@app.route('/send', methods=['POST'])
def send():
    data = request.json
    user = data.get('user', 'Anonymous')
    text = data.get('text', '')
    room = data.get('room', 'public')
    msg_type = data.get('type', 'chat')
    target_ip = data.get('target', None)
    avatar = data.get('avatar', '')
    
    if text.strip():
        global message_id_counter
        msg = {
            "id": message_id_counter,
            "room": str(room),
            "user": user,
            "text": text,
            "time": time.strftime("%H:%M"),
            "ip": request.remote_addr,
            "type": msg_type,
            "target": target_ip,
            "avatar": avatar,
            "edited": False
        }
        messages.append(msg)
        message_id_counter += 1
        # Keep only last 200 messages total or per room logic could be added
        if len(messages) > 1000:
            messages.pop(0)
        save_all_data()
        notify_clients(room)
            
    return jsonify({"status": "ok"})

@app.route('/messages')
def get_messages():
    room = request.args.get('room', 'public')
    after_id = request.args.get('after', -1, type=int)
    
    # Filter by room and id
    new_messages = [m.copy() for m in messages if m.get('room') == str(room) and m['id'] > after_id]
    
    # Attach reactions and read receipts
    for msg in new_messages:
        msg['reactions'] = message_reactions.get(msg['id'], {})
        msg['read_by'] = read_receipts.get(msg['id'], [])
    
    return jsonify(new_messages)

@app.route('/edit_message', methods=['POST'])
def edit_message():
    data = request.json
    msg_id = data.get('id')
    new_text = data.get('text', '')
    ip = request.remote_addr
    
    for msg in messages:
        if msg['id'] == msg_id and msg['ip'] == ip:
            msg['text'] = new_text
            msg['edited'] = True
            save_all_data()
            notify_clients(msg.get('room', 'public'))
            return jsonify({"status": "ok"})
    
    return jsonify({"status": "error", "message": "Unauthorized"}), 403

@app.route('/delete_message', methods=['POST'])
def delete_message():
    data = request.json
    msg_id = data.get('id')
    ip = request.remote_addr
    
    global messages
    for i, msg in enumerate(messages):
        if msg['id'] == msg_id and msg['ip'] == ip:
            messages.pop(i)
            message_reactions.pop(msg_id, None)
            read_receipts.pop(msg_id, None)
            room = msg.get('room', 'public')
            save_all_data()
            notify_clients(room)
            return jsonify({"status": "ok"})
    
    return jsonify({"status": "error", "message": "Unauthorized"}), 403

@app.route('/react_message', methods=['POST'])
def react_message():
    data = request.json
    msg_id = data.get('id')
    emoji = data.get('emoji', '👍')
    ip = request.remote_addr
    
    if msg_id not in message_reactions:
        message_reactions[msg_id] = {}
    
    if emoji not in message_reactions[msg_id]:
        message_reactions[msg_id][emoji] = []
    
    if ip in message_reactions[msg_id][emoji]:
        message_reactions[msg_id][emoji].remove(ip)
        if not message_reactions[msg_id][emoji]:
            del message_reactions[msg_id][emoji]
    else:
        message_reactions[msg_id][emoji].append(ip)
    
    save_all_data()
    # Find the room for this message to notify correct clients
    room = 'public'
    for msg in messages:
        if msg['id'] == msg_id:
            room = msg.get('room', 'public')
            break
    notify_clients(room)
    return jsonify({"status": "ok"})

@app.route('/mark_read', methods=['POST'])
def mark_read():
    data = request.json
    msg_id = data.get('id')
    ip = request.remote_addr
    
    if msg_id not in read_receipts:
        read_receipts[msg_id] = []
    
    if ip not in read_receipts[msg_id]:
        read_receipts[msg_id].append(ip)
        save_all_data()
        room = 'public'
        for msg in messages:
            if msg['id'] == msg_id:
                room = msg.get('room', 'public')
                break
        notify_clients(room)
    
    return jsonify({"status": "ok"})

@app.route('/stream')
def stream():
    room = request.args.get('room', 'public')
    def event_stream(r):
        q = queue.Queue()
        update_queues.append((q, str(r)))
        try:
            while True:
                # Wait for a signal that something changed
                q.get()
                yield 'data: update\n\n'
        except GeneratorExit:
            for item in update_queues:
                if item[0] == q:
                    update_queues.remove(item)
                    break

    return Response(event_stream(room), mimetype="text/event-stream")

@app.route('/ping')
def ping():
    return "pong", 200

def self_ping(port):
    """Background task to keep Render instance alive."""
    # Wait for server to start
    time.sleep(10)
    while True:
        try:
            # Pings itself locally on the correct port
            requests.get(f"http://127.0.0.1:{port}/ping", timeout=5)
            # This counts as activity to prevent Render from idling
            print(f"🕒 Self-ping executed on port {port}")
        except Exception as e:
            print(f"⚠️ Self-ping failed: {e}")
        # Ping every 10 minutes (Render free tier sleeps after 15m)
        time.sleep(600)

if __name__ == '__main__':
    load_data()
    # Get port from environment or default to 5000
    port = int(os.environ.get("PORT", 5000))
    is_render = "RENDER" in os.environ
    
    # Start self-ping thread
    threading.Thread(target=self_ping, args=(port,), daemon=True).start()
    
    print(f"🚀 Chat server starting on port {port}")
    # Enable debug mode only when NOT on Render to allow auto-reloading during development
    # On Render, debug=False is safer and more performant
    app.run(host='0.0.0.0', port=port, debug=not is_render, threaded=True)
