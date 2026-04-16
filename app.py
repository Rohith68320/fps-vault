from flask import Flask, render_template, jsonify, request, session, redirect
import os, re, mysql.connector
from dotenv import load_dotenv
from mysql.connector import pooling
import urllib.request
from flask import Response
from thefuzz import fuzz

load_dotenv()

app = Flask(__name__)
app.secret_key = "super_secret_fps_vault_key"

# Build the config dictionary using the hidden variables
dbconfig = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME"),
    # Port must be converted to an integer!
    "port": int(os.environ.get("DB_PORT", 19241)) 
}

# Create a pool of 5 permanent connections
db_pool = pooling.MySQLConnectionPool(
    pool_name="fps_pool",
    pool_size=5,
    **dbconfig
)

# The ultra-fast connection function
def get_db_connection():
    return db_pool.get_connection()

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

@app.route('/my_channel')
def my_channel():
    # If they aren't logged in, send them away
    if 'user_id' not in session:
        return redirect('/') # Or redirect to a login page if you have one

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Ask the database: What is the channel ID for this specific user?
        cursor.execute("SELECT channel_id FROM Channel WHERE user_id = %s", (session['user_id'],))
        channel = cursor.fetchone()
        
        if channel:
            # Redirect them to the correct URL!
            return redirect(f"/channel/{channel['channel_id']}")
        else:
            return "Error: You do not have a channel set up.", 404
    finally:
        cursor.close()
        conn.close()

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
    password = data.get('password') # Keeping it plain-text as requested!
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Insert the new user
        cursor.execute("INSERT INTO User (first_name, email, password) VALUES (%s, %s, %s)", 
                       (username, email, password))
        
        # 2. Grab the brand new user's ID
        new_user_id = cursor.lastrowid
        
        # 3. ⭐️ AUTOMATICALLY CREATE THEIR CHANNEL ⭐️
        default_channel_name = f"{username}'s Channel"
        default_description = "Welcome to my FPS Vault channel!"
        cursor.execute("INSERT INTO Channel (channel_name, description, user_id) VALUES (%s, %s, %s)", 
                       (default_channel_name, default_description, new_user_id))
        
        # Save both the user and the channel to the database at the same time
        conn.commit()
        
        # 4. Automatically log them in
        session['user_id'] = new_user_id
        session['username'] = username
        
        return jsonify({"message": "Registered and Channel created!", "redirect": "/"}), 201
        
    except mysql.connector.IntegrityError:
        return jsonify({"error": "Email already exists!"}), 400
    except Exception as e:
        print(f"\n❌ DATABASE ERROR DURING REGISTRATION: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/recommendations/<int:video_id>', methods=['GET'])
def get_recommendations(video_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Get all tag IDs for the current video
        cursor.execute("SELECT tag_id FROM Video_Tag WHERE video_id = %s", (video_id,))
        tag_ids = [row['tag_id'] for row in cursor.fetchall()]

        if not tag_ids:
            # Fallback: Just get latest videos if no tags exist
            cursor.execute("""
                SELECT v.video_id, v.title, v.thumbnail_url, v.views_count, c.channel_name, c.channel_id,
                (SELECT COUNT(*) FROM Like_Table WHERE video_id = v.video_id) as likes_cnt
                FROM Video v JOIN Channel c ON v.channel_id = c.channel_id 
                WHERE v.video_id != %s LIMIT 15
            """, (video_id,))
        else:
            # 2. Find videos sharing ANY of these tags, diversified
            format_strings = ','.join(['%s'] * len(tag_ids))
            query = f"""
                SELECT DISTINCT v.video_id, v.title, v.thumbnail_url, v.views_count, c.channel_name, c.channel_id,
                (SELECT COUNT(*) FROM Like_Table WHERE video_id = v.video_id) as likes_cnt
                FROM Video v
                JOIN Channel c ON v.channel_id = c.channel_id
                JOIN Video_Tag vt ON v.video_id = vt.video_id
                WHERE vt.tag_id IN ({format_strings}) AND v.video_id != %s
                ORDER BY RAND() -- Diversifies the mix from education, gaming, food, etc.
                LIMIT 15
            """
            cursor.execute(query, tuple(tag_ids + [video_id]))
        
        recs = cursor.fetchall()
        return jsonify(recs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()
        
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. SECRET CHECK: Is this an Admin?
        cursor.execute("SELECT admin_id, first_name FROM Admin WHERE email=%s AND password=%s", (email, password))
        admin = cursor.fetchone()

        if admin:
            session.clear() # Clear any existing sessions
            session['admin_id'] = admin['admin_id']
            session['admin_name'] = admin['first_name']
            # Send back a special redirect URL just for admins
            return jsonify({"message": "Admin login successful", "redirect": "/admin"}), 200

        # 2. NORMAL CHECK: Is this a regular User?
        cursor.execute("SELECT user_id, first_name FROM User WHERE email=%s AND password=%s", (email, password))
        user = cursor.fetchone()

        if user:
            session.clear()
            session['user_id'] = user['user_id']
            # Re-adding these just in case your frontend requires them!
            session['username'] = user['first_name'] 
            session['logged_in'] = True 
            
            # Send back the standard homepage redirect
            return jsonify({"message": "Login successful", "redirect": "/"}), 200
        
        # 3. Neither? Block them.
        return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

@app.route('/api/upload_video', methods=['POST'])
def handle_video_upload():
    if 'user_id' not in session:
        return jsonify({"error": "You must be logged in to upload."}), 401

    data = request.get_json()
    title = data.get('title')
    description = data.get('description')
    drive_link = data.get('drive_link')
    
    # Grab the new fields!
    thumbnail_url = data.get('thumbnail_url')
    duration = data.get('duration')
    visibility = data.get('visibility', 'public')
    tags_string = data.get('tags', '') # e.g., "gaming, clutch, valorant"
    
    if not title or not drive_link:
        return jsonify({"error": "Title and Drive Link are required!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Find the user's channel
        cursor.execute("SELECT channel_id FROM Channel WHERE user_id = %s", (session['user_id'],))
        channel = cursor.fetchone()
        if not channel:
            return jsonify({"error": "You must create a Channel before uploading a video!"}), 403

        # 2. Insert the Video with ALL the new fields
        cursor.execute("""
            INSERT INTO Video (title, description, drive_link, thumbnail_url, duration, visibility, channel_id, format) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (title, description, drive_link, thumbnail_url, duration, visibility, channel['channel_id'], "Drive Link")) 
        
        # Get the new Video's ID so we can attach tags to it
        new_video_id = cursor.lastrowid
        
        # 3. Process the Tags (The SQL Magic)
        if tags_string:
            # Split the string by commas and clean up extra spaces
            tags_list = [t.strip().lower() for t in tags_string.split(',') if t.strip()]
            
            for tag_name in tags_list:
                # Check if this tag already exists in the database
                cursor.execute("SELECT tag_id FROM Tag WHERE tag_name = %s", (tag_name,))
                existing_tag = cursor.fetchone()
                
                if existing_tag:
                    tag_id = existing_tag['tag_id']
                else:
                    # If it's a brand new tag, create it!
                    cursor.execute("INSERT INTO Tag (tag_name) VALUES (%s)", (tag_name,))
                    tag_id = cursor.lastrowid
                
                # Finally, link the tag to the video in the Video_Tag table
                cursor.execute("INSERT INTO Video_Tag (video_id, tag_id) VALUES (%s, %s)", (new_video_id, tag_id))

        conn.commit()
        return jsonify({"message": "Video linked successfully!", "redirect": f"/channel/{channel['channel_id']}"}), 201
        
    except Exception as e:
        print(f"\n❌ UPLOAD ERROR: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/feed', methods=['GET'])
def get_video_feed():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the newest 20 videos, along with the channel name that uploaded them
        cursor.execute("""
            SELECT v.video_id, v.title, v.thumbnail_url, v.views_count, 
                   c.channel_name, c.channel_id
            FROM Video v
            JOIN Channel c ON v.channel_id = c.channel_id
            ORDER BY v.upload_date DESC
            LIMIT 20
        """)
        videos = cursor.fetchall()
        
        return jsonify(videos), 200
    except Exception as e:
        print(f"\n❌ FEED ERROR: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/feed/tag/<tag_name>', methods=['GET'])
def get_videos_by_tag(tag_name):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Complex Join: Connects Videos to their specific Tags
        cursor.execute("""
            SELECT v.video_id, v.title, v.description, v.thumbnail_url, v.views_count, 
                   c.channel_name, c.channel_id
            FROM Video v
            JOIN Channel c ON v.channel_id = c.channel_id
            JOIN Video_Tag vt ON v.video_id = vt.video_id
            JOIN Tag t ON vt.tag_id = t.tag_id
            WHERE t.tag_name = %s
            ORDER BY v.upload_date DESC
            LIMIT 20
        """, (tag_name,))
        
        videos = cursor.fetchall()
        return jsonify(videos), 200
    except Exception as e:
        print(f"\n❌ TAG FEED ERROR: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/proxy_thumb/<file_id>')
def proxy_thumb(file_id):
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    try:
        # Disguise Python as a web browser so Google doesn't block us
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return Response(response.read(), content_type=response.headers.get('Content-Type', 'image/jpeg'))
    except Exception as e:
        print(f"Proxy Error: {e}")
        return redirect('https://via.placeholder.com/640x360.png?text=No+Thumbnail')

@app.route('/api/tags', methods=['GET'])
def get_all_tags():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch the most popular tags (up to 20)
        cursor.execute("SELECT tag_name FROM Tag LIMIT 20")
        tags = cursor.fetchall()
        # Convert it to a simple list of strings: ['gaming', 'valorant', ...]
        return jsonify([t['tag_name'] for t in tags]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/add_comment/<int:video_id>', methods=['POST'])
def add_comment(video_id):
    if 'user_id' not in session:
        return jsonify({"error": "You must be logged in to comment."}), 401
    
    data = request.get_json()
    text = data.get('text')
    
    if not text or text.strip() == "":
        return jsonify({"error": "Comment cannot be empty."}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO Comment (content, user_id, video_id) VALUES (%s, %s, %s)", 
                       (text, session['user_id'], video_id))
        conn.commit()
        return jsonify({"message": "Comment added successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/comments/<int:video_id>', methods=['GET'])
def get_comments(video_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch comments and the username of the person who wrote it
        cursor.execute("""
            SELECT c.content, DATE_FORMAT(c.timestamp, '%M %d, %Y') as date, u.first_name as username
            FROM Comment c
            JOIN User u ON c.user_id = u.user_id
            WHERE c.video_id = %s
            ORDER BY c.timestamp DESC
        """, (video_id,))
        comments = cursor.fetchall()
        return jsonify(comments), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/channel/<int:channel_id>', methods=['GET'])
def get_channel_data(channel_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 1. Get the Channel details
    cursor.execute("""
        SELECT c.channel_id, c.channel_name, c.description, c.user_id,
               (SELECT COUNT(*) FROM Subscription WHERE channel_id = c.channel_id) as subscriber_cnt
        FROM Channel c WHERE c.channel_id = %s
    """, (channel_id,))
    channel = cursor.fetchone()
    
    if not channel:
        return jsonify({"error": "Channel not found"}), 404

    # 2. Get ALL videos uploaded by this channel (Notice we added thumbnail_url here!)
    cursor.execute("""
        SELECT video_id, title, views_count, thumbnail_url, DATE_FORMAT(upload_date, '%M %d, %Y') as upload_date 
        FROM Video 
        WHERE channel_id = %s 
        ORDER BY upload_date DESC
    """, (channel_id,))
    channel['videos'] = cursor.fetchall()
        
    cursor.close()
    conn.close()
    return jsonify(channel)

# 1. Serve the HTML page
@app.route('/history')
def history_page():
    if 'user_id' not in session: return redirect('/login')
    return render_template('history.html')

# 2. Fetch the user's history
@app.route('/api/history', methods=['GET'])
def get_watch_history():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Notice we are grabbing 'watch_progress' and the video's total 'duration' now!
        cursor.execute("""
            SELECT v.video_id, v.title, v.thumbnail_url, v.duration, v.views_count, 
                   c.channel_name, c.channel_id, h.watch_duration,
                   DATE_FORMAT(h.watch_timestamp, '%M %d, %Y') as watched_on
            FROM Watch_History h
            JOIN Video v ON h.video_id = v.video_id
            JOIN Channel c ON v.channel_id = c.channel_id
            WHERE h.user_id = %s
            ORDER BY h.watch_timestamp DESC
        """, (session['user_id'],))
        
        return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# 3. The "Silent Tracker" that saves video progress
@app.route('/api/history/progress', methods=['POST'])
def update_watch_progress():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    video_id = data.get('video_id')
    progress = data.get('progress', 0)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE Watch_History 
            SET watch_duration = %s 
            WHERE user_id = %s AND video_id = %s
        """, (progress, session['user_id'], video_id))
        conn.commit()
        return jsonify({"success": True}), 200
    finally:
        cursor.close(); conn.close()

@app.route('/api/watch/<int:video_id>', methods=['GET'])
def get_video_data(video_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Notice we don't have an open 'try:' here anymore!
    cursor.execute("""
        SELECT v.video_id, v.title, v.description, v.drive_link, v.thumbnail_url, v.views_count as views_cnt, 
               DATE_FORMAT(v.upload_date, '%M %d, %Y') as upload_date,
               (SELECT COUNT(*) FROM Like_Table WHERE video_id = v.video_id) as likes_cnt,
               c.channel_id, c.channel_name,
               (SELECT COUNT(*) FROM Subscription WHERE channel_id = c.channel_id) as subscriber_cnt
        FROM Video v 
        JOIN Channel c ON v.channel_id = c.channel_id 
        WHERE v.video_id = %s
    """, (video_id,))
    video = cursor.fetchone()
    
    if video:
        cursor.execute("UPDATE Video SET views_count = views_count + 1 WHERE video_id = %s", (video_id,))
        
        # Grab the tags
        cursor.execute("SELECT t.tag_name FROM Tag t JOIN Video_Tag vt ON t.tag_id = vt.tag_id WHERE vt.video_id = %s", (video_id,))
        video['tags'] = [t['tag_name'] for t in cursor.fetchall()]
        
        # Check if the current logged-in user already liked/subscribed
        video['user_liked'] = False
        video['user_subscribed'] = False
        
        if 'user_id' in session:
            user_id = session['user_id']
            # Silent Watch History Tracker
            cursor.execute("""
                INSERT INTO Watch_History (user_id, video_id) 
                VALUES (%s, %s) 
                ON DUPLICATE KEY UPDATE watch_timestamp = CURRENT_TIMESTAMP
            """, (user_id, video_id))

            cursor.execute("SELECT 1 FROM Like_Table WHERE user_id = %s AND video_id = %s", (user_id, video_id))
            video['user_liked'] = bool(cursor.fetchone())
            
            cursor.execute("SELECT 1 FROM Subscription WHERE user_id = %s AND channel_id = %s", (user_id, video['channel_id']))
            video['user_subscribed'] = bool(cursor.fetchone())

        conn.commit()

    cursor.close()
    conn.close()
    
    return jsonify(video) if video else (jsonify({"error": "Video not found"}), 404)

@app.route('/api/toggle_like/<int:video_id>', methods=['POST'])
def toggle_like(video_id):
    if 'user_id' not in session: return jsonify({"error": "You must be logged in to like."}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if they already liked it
        cursor.execute("SELECT 1 FROM Like_Table WHERE user_id=%s AND video_id=%s", (user_id, video_id))
        if cursor.fetchone():
            # UN-LIKE
            cursor.execute("DELETE FROM Like_Table WHERE user_id=%s AND video_id=%s", (user_id, video_id))
            is_liked = False
        else:
            # LIKE
            cursor.execute("INSERT INTO Like_Table (user_id, video_id) VALUES (%s, %s)", (user_id, video_id))
            is_liked = True
            
        # Get the new total
        cursor.execute("SELECT COUNT(*) FROM Like_Table WHERE video_id=%s", (video_id,))
        new_count = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({"liked": is_liked, "likes_cnt": new_count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()


@app.route('/api/toggle_subscribe/<int:channel_id>', methods=['POST'])
def toggle_subscribe(channel_id):
    if 'user_id' not in session: return jsonify({"error": "You must be logged in to subscribe."}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Changed to user_id
        cursor.execute("SELECT 1 FROM Subscription WHERE user_id=%s AND channel_id=%s", (user_id, channel_id))
        if cursor.fetchone():
            # UN-SUBSCRIBE (Changed to user_id)
            cursor.execute("DELETE FROM Subscription WHERE user_id=%s AND channel_id=%s", (user_id, channel_id))
            is_subbed = False
        else:
            # SUBSCRIBE (Changed to user_id)
            cursor.execute("INSERT INTO Subscription (user_id, channel_id) VALUES (%s, %s)", (user_id, channel_id))
            is_subbed = True
            
        cursor.execute("SELECT COUNT(*) FROM Subscription WHERE channel_id=%s", (channel_id,))
        new_count = cursor.fetchone()[0]
        conn.commit()
        
        return jsonify({"subscribed": is_subbed, "subscriber_cnt": new_count}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# ==========================================
# PLAYLIST APIs
# ==========================================
# ==========================================
# PLAYLIST APIs
# ==========================================
@app.route('/api/playlists', methods=['GET', 'POST'])
def handle_playlists():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if request.method == 'POST':
            data = request.get_json()
            name = data.get('name')
            visibility = data.get('visibility', 'private') # Default to private
            
            if not name: return jsonify({"error": "Name required"}), 400
            
            # Now saving visibility as well!
            cursor.execute("INSERT INTO Playlist (user_id, name, visibility) VALUES (%s, %s, %s)", 
                           (session['user_id'], name, visibility))
            conn.commit()
            return jsonify({"message": "Playlist created!", "playlist_id": cursor.lastrowid}), 201
            
        elif request.method == 'GET':
            cursor.execute("""
                SELECT p.playlist_id, p.name, p.visibility, DATE_FORMAT(p.creation_date, '%M %d, %Y') as created_on,
                       (SELECT COUNT(*) FROM Playlist_Video WHERE playlist_id = p.playlist_id) as video_count
                FROM Playlist p
                WHERE p.user_id = %s
                ORDER BY p.creation_date DESC
            """, (session['user_id'],))
            return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# NEW ROUTE: Save a video to a specific playlist
@app.route('/api/playlists/<int:playlist_id>/add_video', methods=['POST'])
def add_video_to_playlist(playlist_id):
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    video_id = request.get_json().get('video_id')
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if the video is already in this playlist to prevent duplicates
        cursor.execute("SELECT 1 FROM Playlist_Video WHERE playlist_id=%s AND video_id=%s", (playlist_id, video_id))
        if cursor.fetchone():
            return jsonify({"message": "Already in playlist!"}), 200

        # Add it!
        cursor.execute("INSERT INTO Playlist_Video (playlist_id, video_id) VALUES (%s, %s)", (playlist_id, video_id))
        conn.commit()
        return jsonify({"message": "Saved to playlist!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# ... keep your existing get_playlist_videos route below here ...
@app.route('/api/feed/playlists', methods=['GET'])
def get_feed_playlists():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Grabs public playlists, video count, creator, and a cover thumbnail
        cursor.execute("""
            SELECT p.playlist_id, p.name, c.channel_name,
                   (SELECT COUNT(*) FROM Playlist_Video WHERE playlist_id = p.playlist_id) as video_count,
                   (SELECT v.thumbnail_url 
                    FROM Playlist_Video pv 
                    JOIN Video v ON pv.video_id = v.video_id 
                    WHERE pv.playlist_id = p.playlist_id 
                    LIMIT 1) as thumbnail_url
            FROM Playlist p
            JOIN Channel c ON p.user_id = c.user_id
            WHERE p.visibility = 'public'
            HAVING video_count > 0
            ORDER BY p.creation_date DESC
            LIMIT 15
        """)
        return jsonify(cursor.fetchall()), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

@app.route('/api/playlists/<int:playlist_id>', methods=['GET'])
def get_playlist_videos(playlist_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Check if the playlist exists and get its visibility
        cursor.execute("SELECT name, visibility, user_id FROM Playlist WHERE playlist_id = %s", (playlist_id,))
        playlist = cursor.fetchone()
        
        if not playlist: 
            return jsonify({"error": "Playlist not found"}), 404

        # 2. Security Check: If it's private, only the owner can view it
        if playlist['visibility'] == 'private':
            if 'user_id' not in session or session['user_id'] != playlist['user_id']:
                return jsonify({"error": "This playlist is private"}), 403

        # 3. Get all the videos!
        cursor.execute("""
            SELECT v.video_id, v.title, v.thumbnail_url, v.views_count, c.channel_name
            FROM Playlist_Video pv
            JOIN Video v ON pv.video_id = v.video_id
            JOIN Channel c ON v.channel_id = c.channel_id
            WHERE pv.playlist_id = %s
        """, (playlist_id,))
        
        return jsonify({"name": playlist['name'], "videos": cursor.fetchall()}), 200

    except Exception as e:
        print(f"\n❌ PLAYLIST FETCH ERROR: {e}\n") # This will print to your terminal if it crashes!
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ==========================================
# PLAYLIST HELPER ROUTE
# ==========================================
@app.route('/play/playlist/<int:playlist_id>')
def start_playlist(playlist_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Just grab the first video ID attached to this playlist!
        cursor.execute("SELECT video_id FROM Playlist_Video WHERE playlist_id = %s LIMIT 1", (playlist_id,))
        first_video = cursor.fetchone()
        
        if first_video:
            # Redirect to the watch page, but attach the playlist ID so the queue opens!
            return redirect(f"/watch/{first_video['video_id']}?list={playlist_id}")
        else:
            return "Playlist is empty", 404
    except Exception as e:
        print(f"PLAYLIST START ERROR: {e}")
        return str(e), 500
    finally:
        cursor.close(); conn.close()

# ==========================================
# TICKETING & REPORTING APIs
# ==========================================
@app.route('/api/report/video', methods=['POST'])
def report_video():
    if 'user_id' not in session: return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    video_id = data.get('video_id')
    category = data.get('category')
    description = data.get('description')
    
    if not all([video_id, category, description]):
        return jsonify({"error": "All fields are required"}), 400
        
    # Auto-generate a title for the admin to read easily!
    title = f"Report for Video ID: {video_id} - {category.title()}"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Using YOUR exact column names: title, category, description, video_id
        cursor.execute("""
            INSERT INTO Ticket (user_id, video_id, title, category, description, status) 
            VALUES (%s, %s, %s, %s, %s, 'new')
        """, (session['user_id'], video_id, title, category, description))
        conn.commit()
        return jsonify({"message": "Report submitted successfully!"}), 201
    except Exception as e:
        print(f"\n❌ TICKET INSERT ERROR: {e}\n")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# The Bouncer for the HTML Page
@app.route('/admin')
def admin_page():
    # If they don't have a staff badge, kick them to the staff login!
    if 'admin_id' not in session: 
        return redirect('/staff-login')
    return render_template('admin.html')

# The API that feeds data to the dashboard
@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    # Strict API Security
    if 'admin_id' not in session: 
        return jsonify({"error": "Forbidden. Staff only."}), 403
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Gather Platform Metrics
        cursor.execute("SELECT COUNT(*) as total_users FROM User")
        users_count = cursor.fetchone()['total_users']
        
        cursor.execute("SELECT COUNT(*) as total_videos, SUM(views_count) as total_views FROM Video")
        video_stats = cursor.fetchone()
        
        # 2. Get the active tickets! (Using your exact Ticket table layout)
        cursor.execute("""
            SELECT t.ticket_id, t.title, t.category, t.status, t.date_created, u.first_name as reported_by
            FROM Ticket t
            JOIN User u ON t.user_id = u.user_id
            WHERE t.status != 'resolved'
            ORDER BY t.date_created DESC
            LIMIT 20
        """)
        active_tickets = cursor.fetchall()
        
        return jsonify({
            "metrics": {
                "users": users_count,
                "videos": video_stats['total_videos'] or 0,
                "views": int(video_stats['total_views'] or 0) if video_stats['total_views'] else 0
            },
            "tickets": active_tickets # We will show these in the dashboard next!
        }), 200
        
    except Exception as e:
        print(f"ADMIN STATS ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

@app.route('/api/admin/ticket/<int:ticket_id>/resolve', methods=['POST'])
def resolve_ticket(ticket_id):
    # Security: Only admins can resolve tickets
    if 'admin_id' not in session: 
        return jsonify({"error": "Unauthorized"}), 403
        
    data = request.get_json()
    resolution = data.get('resolution_description')
    
    if not resolution:
        return jsonify({"error": "Please provide a resolution description"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Update the ticket using your exact custom columns!
        cursor.execute("""
            UPDATE Ticket 
            SET status = 'resolved', 
                resolution_description = %s, 
                admin_id = %s 
            WHERE ticket_id = %s
        """, (resolution, session['admin_id'], ticket_id))
        
        conn.commit()
        return jsonify({"message": "Ticket resolved successfully"}), 200
    except Exception as e:
        print(f"TICKET RESOLVE ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

# ==========================================
# SEARCH APIs
# ==========================================

# 1. This route loads the visual web page
@app.route('/search')
def search_page():
    return render_template('search.html')

# 2. This route handles the fuzzy AI brain logic
@app.route('/api/search', methods=['GET'])
def api_search():
    q = request.args.get('q', '').strip().lower() 
    
    if not q:
        return jsonify([]), 200

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT v.video_id, v.title, v.thumbnail_url, v.views_count, 
                   DATE_FORMAT(v.upload_date, '%M %d, %Y') as date,
                   c.channel_name, c.channel_id,
                   (SELECT COUNT(*) FROM Like_Table WHERE video_id = v.video_id) as likes_cnt
            FROM Video v
            JOIN Channel c ON v.channel_id = c.channel_id
            ORDER BY v.views_count DESC
            LIMIT 300
        """)
        all_videos = cursor.fetchall()
        
        results = []
        for v in all_videos:
            title_score = fuzz.partial_ratio(q, v['title'].lower())
            channel_score = fuzz.partial_ratio(q, v['channel_name'].lower())
            best_score = max(title_score, channel_score)
            
            if best_score >= 60:
                v['match_score'] = best_score 
                results.append(v)
                
        results = sorted(results, key=lambda x: x['match_score'], reverse=True)
        return jsonify(results), 200
        
    except Exception as e:
        print(f"FUZZY SEARCH ERROR: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); conn.close()

if __name__ == '__main__':
    print("FPS-VAULT Offline Server Running (No DB required)...")
    app.run(debug=True, port=5000)