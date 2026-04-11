from flask import Flask, render_template, jsonify, request, session, redirect
import os, re, mysql.connector
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_fps_vault_key"

def get_db_connection():
    # Connected to your friend's Aiven Cloud Database!
    return mysql.connector.connect(
        host="mysql-24999bf4-fpsvault.f.aivencloud.com",
        user="avnadmin",        
        password=os.getenv("DB_PASSWORD"), 
        port=19241,
        database="defaultdb",
        ssl_disabled=False
    )

# ==========================================
# PAGE SERVING ROUTES (HTML)
# ==========================================
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/upload')
def upload_page():
    if 'user_id' not in session: return redirect('/login')
    return render_template('upload.html')

@app.route('/playlists')
def playlists_page():
    if 'user_id' not in session: return redirect('/login')
    return render_template('playlists.html')

@app.route('/channel/<int:channel_id>')
def channel_page(channel_id):
    return render_template('channel.html', channel_id=channel_id)

@app.route('/watch/<int:video_id>')
def watch_page(video_id):
    return render_template('watch.html', video_id=video_id)

# ==========================================
# MOCK API ENDPOINTS (NO DATABASE)
# ==========================================
@app.route('/api/current_user', methods=['GET'])
def current_user():
    if 'user_id' in session:
        return jsonify({"logged_in": True, "username": session['username'], "user_id": session['user_id']})
    return jsonify({"logged_in": False})

@app.route('/api/logout', methods=['POST'])
def logout_user():
    session.clear()
    return jsonify({"message": "Logged out"}), 200

@app.route('/api/register', methods=['POST'])
def register_user():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Insert the new user
        cursor.execute("INSERT INTO User (first_name, email, password) VALUES (%s, %s, %s)", (username, email, password))
        conn.commit()
        
        # 2. Get the new ID and automatically log them in!
        new_user_id = cursor.lastrowid
        session['user_id'] = new_user_id
        session['username'] = username
        
        return jsonify({"message": "Registered and logged in!", "redirect": "/"}), 201
        
    except mysql.connector.IntegrityError:
        return jsonify({"error": "Email already exists!"}), 400
    except Exception as e:
        # THIS IS CRITICAL: It will print the exact error in your VS Code terminal if it fails!
        print(f"\n❌ DATABASE ERROR DURING REGISTRATION: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def login_user():
    # Automatically log in anyone who tries to log in
    data = request.get_json()
    email = data.get('email', '')
    username = email.split('@')[0] if '@' in email else "DemoUser"
    session['user_id'] = 1
    session['username'] = username.capitalize()
    return jsonify({"message": "Login successful!"}), 200

@app.route('/api/channel/<int:channel_id>', methods=['GET'])
def get_channel_data(channel_id):
    # Mock Channel Data
    mock_channel = {
        "channel_id": channel_id,
        "channel_name": "GamerPro Official",
        "subscriber_cnt": "1.2M",
        "user_id": 1,
        "video_count": 6,
        "videos": [
            {"id": 101, "title": "Apex Legends Clutch - 1 HP WIN!", "views": "15k", "duration": "10:24"},
            {"id": 102, "title": "Valorant Radiant Grind EP. 5", "views": "8.2k", "duration": "45:12"},
            {"id": 103, "title": "Funny Fails Compilation 2026", "views": "500", "duration": "08:15"},
            {"id": 104, "title": "How to perfectly throw smokes in CS2", "views": "1.1M", "duration": "12:05"},
            {"id": 105, "title": "My new gaming setup tour!", "views": "250k", "duration": "15:30"},
            {"id": 106, "title": "Beating the final boss blindfolded", "views": "45k", "duration": "2:10:00"}
        ],
        "playlists": [
            {"id": 1, "title": "Favorites"},
            {"id": 2, "title": "Highlights"},
            {"id": 3, "title": "Tutorials"}
        ]
    }
    return jsonify(mock_channel)

@app.route('/api/watch/<int:video_id>', methods=['GET'])
def get_video_data(video_id):
    # Mock Video Data
    mock_video = {
        "vid_id": video_id,
        "title": f"Live Broadcast or Highlight #{video_id}",
        "description": "Welcome to the stream! Don't forget to like, subscribe, and turn on notifications.\n\nFollow me on my socials!",
        "views_cnt": "24,512",
        "likes_cnt": "3,402",
        "upload_date": "2026-04-11",
        "channel_id": 1,
        "channel_name": "GamerPro Official",
        "subscriber_cnt": "1.2M"
    }
    return jsonify(mock_video)

if __name__ == '__main__':
    print("FPS-VAULT Offline Server Running (No DB required)...")
    app.run(debug=True, port=5000)