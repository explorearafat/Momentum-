# -*- coding: utf-8 -*-
#!/usr/bin/env python3
from flask import Flask, request, redirect, session, render_template_string, jsonify
import sqlite3, os, datetime, json, requests, random
from werkzeug.utils import secure_filename
import random

app = Flask(__name__)
app.secret_key = "supersecret"
#Random Search
my_list = ["Foreign Tradition", "Traveling", "5 minutes Craft"]
searches = random.choice(my_list)
# YouTube API Configuration
YOUTUBE_API_KEY = "AIzaSyDKM9rADELr0B9_wpcY-t4Ei4A8AhnIbn4"
YOUTUBE_SEARCH_QUERY = searches

# -------------- STATIC FOLDERS --------------
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("static/photos"):
    os.makedirs("static/photos")
if not os.path.exists("static/posts"):
    os.makedirs("static/posts")
if not os.path.exists("static/messages"):
    os.makedirs("static/messages")

DB_PATH = "users.db"

# -------------- DB CONNECTION --------------
def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

# -------------- INIT DATABASE --------------
def init_db():
    conn = get_db_conn()
    c = conn.cursor()

    # USERS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fullname TEXT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        age TEXT,
        photo TEXT
    );
    """)

    # FOLLOWERS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS followers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        follower_id INTEGER,
        UNIQUE(user_id, follower_id)
    );
    """)

    # POSTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        caption TEXT,
        media TEXT,
        media_type TEXT,
        timestamp TEXT,
        is_youtube INTEGER DEFAULT 0,
        youtube_data TEXT DEFAULT '{}'
    );
    """)

    # LIKES TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS likes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER,
        user_id INTEGER,
        UNIQUE(post_id, user_id)
    );
    """)

    # COMMENTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS comments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER,
        user_id INTEGER,
        comment TEXT,
        timestamp TEXT
    );
    """)

    # MESSAGES TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id INTEGER,
        receiver_id INTEGER,
        message TEXT,
        media TEXT,
        media_type TEXT,
        location_data TEXT,
        timestamp TEXT,
        is_read INTEGER DEFAULT 0,
        reply_to INTEGER DEFAULT NULL,
        reactions TEXT DEFAULT '{}'
    );
    """)

    # NOTIFICATIONS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS notifications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        source_user_id INTEGER,
        source_id INTEGER,
        message TEXT,
        timestamp TEXT,
        is_read INTEGER DEFAULT 0
    );
    """)

    # LOGIN_ALERTS TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS login_alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        device_name TEXT,
        ip_address TEXT,
        location TEXT,
        user_agent TEXT,
        timestamp TEXT,
        is_read INTEGER DEFAULT 0
    );
    """)

    conn.commit()
    conn.close()

init_db()

# ----------- BASIC USER FUNCTIONS -----------
def fetch_user_by_username(username):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    return user

def fetch_user_by_id(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    user = c.fetchone()
    conn.close()
    return user

def refresh_session_user():
    if "user" not in session:
        return
    username = session["user"][2]
    user = fetch_user_by_username(username)
    if user:
        session["user"] = tuple(user)

def followers_count(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM followers WHERE user_id=?", (uid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def following_count(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM followers WHERE follower_id=?", (uid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def is_following(target_id, visitor_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "SELECT 1 FROM followers WHERE user_id=? AND follower_id=?",
        (target_id, visitor_id),
    )
    r = c.fetchone()
    conn.close()
    return bool(r)

def detect_media_type(filename):
    ext = os.path.splitext(filename.lower())[1]
    if ext in (".mp4", ".mov", ".webm", ".mkv", ".ogg"):
        return "video"
    return "image"

def get_user_posts(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "SELECT p.*, u.username, u.photo AS user_photo FROM posts p JOIN users u ON p.user_id = u.id WHERE p.user_id=? ORDER BY datetime(timestamp) DESC",
        (uid,),
    )
    posts = c.fetchall()
    conn.close()
    return posts

def get_all_public_posts(limit=50):
    """Get all public posts randomly for feed"""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT p.*, u.username, u.photo AS user_photo 
        FROM posts p 
        JOIN users u ON p.user_id = u.id 
        ORDER BY RANDOM() 
        LIMIT ?
    """, (limit,))
    posts = c.fetchall()
    conn.close()
    return posts

def get_like_count(pid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM likes WHERE post_id=?", (pid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def get_comment_count(pid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM comments WHERE post_id=?", (pid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def is_liked(pid, uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (pid, uid))
    result = c.fetchone()
    conn.close()
    return bool(result)

def format_time(timestamp):
    try:
        dt = datetime.datetime.fromisoformat(timestamp)
        now = datetime.datetime.now()
        diff = now - dt
        if diff.days > 0:
            return f"{diff.days}d"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m"
        else:
            return "now"
    except:
        return timestamp

# MESSAGING FUNCTIONS
def get_unread_message_count(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM messages WHERE receiver_id=? AND is_read=0", (uid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def mark_messages_as_read(sender_id, receiver_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE messages SET is_read=1 WHERE sender_id=? AND receiver_id=?", (sender_id, receiver_id))
    conn.commit()
    conn.close()

def get_message_reactions(message_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT reactions FROM messages WHERE id=?", (message_id,))
    result = c.fetchone()
    conn.close()
    if result and result["reactions"]:
        return json.loads(result["reactions"])
    return {}

def add_reaction_to_message(message_id, user_id, emoji):
    reactions = get_message_reactions(message_id)
    if str(user_id) not in reactions:
        reactions[str(user_id)] = emoji
    
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE messages SET reactions=? WHERE id=?", (json.dumps(reactions), message_id))
    conn.commit()
    conn.close()

def remove_reaction_from_message(message_id, user_id):
    reactions = get_message_reactions(message_id)
    if str(user_id) in reactions:
        del reactions[str(user_id)]
    
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE messages SET reactions=? WHERE id=?", (json.dumps(reactions), message_id))
    conn.commit()
    conn.close()

def create_notification(user_id, type, source_user_id, source_id, message):
    ts = datetime.datetime.now().isoformat()
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO notifications(user_id, type, source_user_id, source_id, message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, type, source_user_id, source_id, message, ts))
    conn.commit()
    conn.close()

def get_replied_message(message_id):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT m.*, u.username FROM messages m JOIN users u ON m.sender_id = u.id WHERE m.id=?", (message_id,))
    message = c.fetchone()
    conn.close()
    return message

# NOTIFICATION FUNCTIONS
def get_unread_notification_count(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE user_id=? AND is_read=0", (uid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def get_unread_login_alerts_count(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) AS cnt FROM login_alerts WHERE user_id=? AND is_read=0", (uid,))
    count = c.fetchone()["cnt"]
    conn.close()
    return count

def mark_notifications_as_read(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def mark_login_alerts_as_read(uid):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE login_alerts SET is_read=1 WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()

def create_login_alert(user_id, device_name, ip_address, location, user_agent):
    ts = datetime.datetime.now().isoformat()
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO login_alerts(user_id, device_name, ip_address, location, user_agent, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, device_name, ip_address, location, user_agent, ts))
    conn.commit()
    conn.close()

# YOUTUBE FUNCTIONS
def fetch_youtube_shorts(search_query=None, video_duration=None, page_token=None):
    try:
        url = f"https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': search_query or YOUTUBE_SEARCH_QUERY,
            'type': 'video',
            'maxResults': 50,
            'key': YOUTUBE_API_KEY,
            'videoEmbeddable': 'true'
        }
        
        if video_duration:
            params['videoDuration'] = video_duration
        
        if page_token:
            params['pageToken'] = page_token
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        videos = []
        next_page_token = data.get('nextPageToken')
        
        if 'items' in data:
            for item in data['items']:
                video_id = item['id']['videoId']
                
                video_data = {
                    'video_id': video_id,
                    'title': item['snippet']['title'],
                    'description': item['snippet']['description'],
                    'channel_title': item['snippet']['channelTitle'],
                    'thumbnail': item['snippet']['thumbnails']['high']['url'],
                    'published_at': item['snippet']['publishedAt']
                }
                videos.append(video_data)
        
        return videos, next_page_token
    except Exception as e:
        print(f"YouTube API Error: {e}")
        return [], None

def get_youtube_embed_url(video_id):
    return f"https://www.youtube.com/embed/{video_id}?playsinline=1&rel=0&modestbranding=1"

# Global variables for YouTube cache
youtube_videos_cache = {}
current_page_tokens = {}

# ---------------- GLOBAL CSS -----------------
momentum_css = """
<style>
    :root {
        --border-gray: #dbdbdb;
        --text-light: #737373;
        --bg-light: #fafafa;
        --btn-blue: #0095f6;
        --btn-hover: #1877f2;
        --red: #ed4956;
    }
    * {
        -webkit-user-select: none;
        -moz-user-select: none;
        -ms-user-select: none;
        user-select: none;
        -webkit-touch-callout: none;
        -webkit-tap-highlight-color: transparent;
    }
    html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        position: fixed;
        font-family: Arial, sans-serif;
        background: var(--bg-light);
        touch-action: manipulation;
        -webkit-text-size-adjust: 100%;
        -ms-text-size-adjust: 100%;
        text-size-adjust: 100%;
    }
    body {
        zoom: 1;
        max-zoom: 1;
        min-zoom: 1;
    }
    .app-container {
        max-width: 100%;
        margin: 0 auto;
        padding: 15px;
        padding-top: 70px;
        padding-bottom: 60px; /* Reduced to prevent overlap with bottom nav */
        height: calc(100vh - 130px); /* Adjusted height */
        overflow-y: auto;
        -webkit-overflow-scrolling: touch;
        box-sizing: border-box;
    }
    .btn {
        background: var(--btn-blue);
        padding: 12px 18px;
        color: white;
        border-radius: 8px;
        border: none;
        cursor: pointer;
        text-decoration: none;
        display: inline-block;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
    }
    .btn:hover {
        background: var(--btn-hover);
    }
    .btn-outline {
        border: 1px solid var(--border-gray);
        padding: 12px 18px;
        border-radius: 8px;
        background: white;
        cursor: pointer;
        text-decoration: none;
        color: black;
        font-size: 14px;
        font-weight: 600;
        text-align: center;
    }
    .form-input {
        width: 100%;
        padding: 14px;
        margin-top: 8px;
        margin-bottom: 16px;
        border: 1px solid var(--border-gray);
        border-radius: 8px;
        box-sizing: border-box;
        font-size: 16px;
        background: white;
    }
    .file-input {
        width: 100%;
        padding: 14px;
        margin-top: 8px;
        margin-bottom: 16px;
        border: 2px dashed var(--border-gray);
        border-radius: 8px;
        box-sizing: border-box;
        font-size: 16px;
        background: #f8f9fa;
        text-align: center;
        cursor: pointer;
    }
    .file-input:hover {
        border-color: var(--btn-blue);
        background: #f0f8ff;
    }
    .nav-bar {
        height: 60px;
        border-bottom: 1px solid var(--border-gray);
        background: white;
        display: flex;
        justify-content: space-between;
        padding: 0 20px;
        align-items: center;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 1000;
        box-sizing: border-box;
    }
    .bottom-nav {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        height: 60px;
        background: white;
        border-top: 1px solid var(--border-gray);
        display: flex;
        justify-content: space-around;
        align-items: center;
        z-index: 1000;
        box-sizing: border-box;
    }
    .nav-icon {
        text-decoration: none;
        color: black;
        padding: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        position: relative;
    }
    .nav-icon.active {
        background: #f0f0f0;
    }
    .icon {
        width: 24px;
        height: 24px;
        fill: currentColor;
    }
    .badge {
        position: absolute;
        top: -5px;
        right: -5px;
        background: var(--red);
        color: white;
        border-radius: 50%;
        width: 18px;
        height: 18px;
        font-size: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        z-index: 1001;
    }
    .welcome-container {
        max-width: 400px;
        margin: 100px auto;
        padding: 30px 20px;
        text-align: center;
        box-sizing: border-box;
    }
    .welcome-title {
        font-size: 32px;
        font-weight: bold;
        margin-bottom: 20px;
        color: #333;
    }
    .welcome-subtitle {
        color: #666;
        margin-bottom: 30px;
        line-height: 1.5;
        font-size: 16px;
    }
    .post-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 2px;
        margin-top: 20px;
    }
    .post-grid-item {
        aspect-ratio: 1;
        overflow: hidden;
        background: #f0f0f0;
    }
    .post-grid-item img,
    .post-grid-item video {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .media-preview {
        width: 100%;
        max-height: 400px;
        object-fit: contain;
        background: #000;
        border-radius: 8px;
        margin-bottom: 15px;
    }
    .message-actions {
        position: absolute;
        background: white;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        padding: 8px;
        z-index: 1000;
        display: none;
    }
    .message-action-btn {
        padding: 8px 12px;
        border: none;
        background: none;
        width: 100%;
        text-align: left;
        cursor: pointer;
        border-radius: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .message-action-btn:hover {
        background: #f0f0f0;
    }
    .emoji-picker {
        position: absolute;
        background: white;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        padding: 8px;
        z-index: 1000;
        display: none;
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 5px;
    }
    .emoji-btn {
        font-size: 18px;
        padding: 5px;
        border: none;
        background: none;
        cursor: pointer;
        border-radius: 4px;
    }
    .emoji-btn:hover {
        background: #f0f0f0;
    }
    .reply-indicator {
        background: #f0f0f0;
        padding: 8px 12px;
        border-radius: 8px;
        margin-bottom: 8px;
        border-left: 3px solid var(--btn-blue);
        font-size: 12px;
        color: #666;
    }
    .reaction {
        font-size: 12px;
        background: white;
        border-radius: 10px;
        padding: 2px 6px;
        margin: 2px;
        border: 1px solid #ddd;
        display: inline-flex;
        align-items: center;
        gap: 2px;
    }
    .youtube-badge {
        background: #ff0000;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: bold;
        margin-left: 8px;
    }
    .video-container {
        position: relative;
        width: 100%;
        background: #000;
    }
    .video-player {
        width: 100%;
        height: 70vh;
        object-fit: cover;
        background: #000;
    }
    .video-placeholder {
        width: 100%;
        height: 70vh;
        background: #000;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 16px;
    }
    .video-controls {
        position: absolute;
        bottom: 10px;
        left: 0;
        right: 0;
        display: flex;
        justify-content: center;
        gap: 20px;
        opacity: 0;
        transition: opacity 0.3s;
    }
    .video-container:hover .video-controls {
        opacity: 1;
    }
    .control-btn {
        background: rgba(0,0,0,0.7);
        color: white;
        border: none;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
    }
    .infinite-loading {
        text-align: center;
        padding: 20px;
        color: #666;
    }
    .post-item {
        margin-bottom: 20px;
        scroll-snap-align: start;
    }
    .feed-container {
        height: 100%;
        overflow-y: auto;
        scroll-snap-type: y mandatory;
    }
    .category-tabs {
        display: flex;
        gap: 10px;
        margin-bottom: 20px;
        border-bottom: 1px solid var(--border-gray);
        padding-bottom: 10px;
    }
    .category-tab {
        flex: 1;
        padding: 12px;
        text-align: center;
        background: white;
        border: 1px solid var(--border-gray);
        border-radius: 8px;
        cursor: pointer;
        font-weight: 600;
        transition: all 0.3s;
    }
    .category-tab.active {
        background: var(--btn-blue);
        color: white;
        border-color: var(--btn-blue);
    }
    .search-container {
        margin-bottom: 20px;
    }
    .search-input {
        width: 100%;
        padding: 12px 16px;
        border: 1px solid var(--border-gray);
        border-radius: 8px;
        font-size: 16px;
        box-sizing: border-box;
    }
    .view-more {
        text-align: center;
        padding: 15px;
        background: var(--btn-blue);
        color: white;
        border-radius: 8px;
        margin-top: 20px;
        cursor: pointer;
        font-weight: 600;
    }
    .social-login-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        width: 100%;
        padding: 12px;
        border: 1px solid #ddd;
        border-radius: 8px;
        background: white;
        cursor: pointer;
        font-weight: 600;
        margin-bottom: 10px;
        transition: all 0.3s;
    }
    .social-login-btn.facebook {
        background: #1877f2;
        color: white;
        border-color: #1877f2;
    }
    .social-login-btn.google {
        background: white;
        color: #333;
        border-color: #ddd;
    }
    .social-login-btn:hover {
        opacity: 0.9;
        transform: translateY(-2px);
    }
    .forgot-password {
        text-align: center;
        margin-top: 15px;
    }
    .forgot-password a {
        color: #0095f6;
        text-decoration: none;
        font-size: 14px;
    }
    .logo-m {
        font-size: 42px;
        font-weight: 800;
        background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        display: inline-block;
        transform: rotate(-5deg);
        margin-bottom: 10px;
    }
    .settings-option {
        display: flex;
        align-items: center;
        gap: 15px;
        padding: 15px;
        border-bottom: 1px solid #eee;
        text-decoration: none;
        color: #333;
    }
    .settings-option:hover {
        background: #f9f9f9;
    }
    .settings-icon {
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .notification-item {
        padding: 15px;
        border-bottom: 1px solid #eee;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .notification-item.unread {
        background: #f0f8ff;
    }
    .login-alert-item {
        padding: 15px;
        border-bottom: 1px solid #eee;
    }
    .login-alert-item.unread {
        background: #fff0f0;
    }
    .login-alert-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .login-alert-details {
        font-size: 12px;
        color: #666;
    }
    .notification-bubble {
        position: fixed;
        top: 70px;
        right: 20px;
        background: var(--btn-blue);
        color: white;
        padding: 12px 16px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 9999;
        animation: slideInRight 0.3s ease-out;
        max-width: 300px;
        font-size: 14px;
    }
    .message-dot-menu {
        position: absolute;
        top: 5px;
        right: 5px;
        background: rgba(0,0,0,0.7);
        color: white;
        border-radius: 50%;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 12px;
        cursor: pointer;
        opacity: 0;
        transition: opacity 0.3s;
        z-index: 10;
    }
    .message-bubble:hover .message-dot-menu {
        opacity: 1;
    }
    .media-attachment {
        max-width: 200px;
        max-height: 200px;
        border-radius: 12px;
        margin: 5px 0;
    }
    .location-share {
        background: #f0f0f0;
        padding: 10px;
        border-radius: 8px;
        margin: 5px 0;
    }
    .message-input-container {
        display: flex;
        gap: 10px;
        align-items: center;
        padding: 15px;
        border-top: 1px solid #eee;
        background: white;
    }
    .attachment-btn {
        background: none;
        border: none;
        font-size: 20px;
        cursor: pointer;
        padding: 8px;
        border-radius: 50%;
    }
    .attachment-btn:hover {
        background: #f0f0f0;
    }
    .attachment-menu {
        position: absolute;
        bottom: 60px;
        left: 15px;
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        padding: 10px;
        z-index: 1000;
        display: none;
    }
    .attachment-option {
        padding: 12px 16px;
        border: none;
        background: none;
        width: 100%;
        text-align: left;
        cursor: pointer;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .attachment-option:hover {
        background: #f0f0f0;
    }
    .touch-hold-menu {
        position: fixed;
        background: white;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        padding: 8px;
        z-index: 10000;
        display: none;
        animation: fadeIn 0.2s ease-out;
    }
    .touch-hold-option {
        padding: 12px 16px;
        border: none;
        background: none;
        width: 100%;
        text-align: left;
        cursor: pointer;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 14px;
        color: #333;
    }
    .touch-hold-option:hover {
        background: #f0f0f0;
    }
    @keyframes fadeIn {
        from { opacity: 0; transform: scale(0.9); }
        to { opacity: 1; transform: scale(1); }
    }
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
</style>
"""

# SVG ICONS
SVG_ICONS = {
    'home': '<svg class="icon" viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>',
    'search': '<svg class="icon" viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
    'add': '<svg class="icon" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>',
    'message': '<svg class="icon" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>',
    'profile': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>',
    'settings': '<svg class="icon" viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>',
    'heart': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>',
    'heart_outline': '<svg class="icon" viewBox="0 0 24 24"><path d="M16.5 3c-1.74 0-3.41.81-4.5 2.09C10.91 3.81 9.24 3 7.5 3 4.42 3 2 5.42 2 8.5c0 3.78 3.4 6.86 8.55 11.54L12 21.35l1.45-1.32C18.6 15.36 22 12.28 22 8.5 22 5.42 19.58 3 16.5 3zm-4.4 15.55l-.1.1-.1-.1C7.14 14.24 4 11.39 4 8.5 4 6.5 5.5 5 7.5 5c1.54 0 3.04.99 3.57 2.36h1.87C13.46 5.99 14.96 5 16.5 5c2 0 3.5 1.5 3.5 3.5 0 2.89-3.14 5.74-7.9 10.05z"/></svg>',
    'comment': '<svg class="icon" viewBox="0 0 24 24"><path d="M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h11c.55 0 1-.45 1-1z"/></svg>',
    'reply': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg>',
    'edit': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    'delete': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>',
    'like': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z"/></svg>',
    'youtube': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z" fill="red"/></svg>',
    'play': '<svg class="icon" viewBox="0 0 24 24" style="width: 20px; height: 20px;"><path d="M8 5v14l11-7z" fill="white"/></svg>',
    'pause': '<svg class="icon" viewBox="0 0 24 24" style="width: 20px; height: 20px;"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" fill="white"/></svg>',
    'volume': '<svg class="icon" viewBox="0 0 24 24" style="width: 20px; height: 20px;"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" fill="white"/></svg>',
    'shorts': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M17.77 10.32c-.77-.32-1.2-.5-1.2-.5L18 9.06c1.84-.96 2.53-3.23 1.56-5.06s-3.24-2.53-5.07-1.56L6 6.94c-1.29.68-2.07 2.04-2 3.49.07 1.42.93 2.67 2.22 3.25.03.01 1.2.5 1.2.5L6 14.94c-1.84.96-2.53 3.23-1.56 5.06.96 1.84 3.24 2.53 5.07 1.56l8.49-4.5c1.29-.68 2.06-2.04 1.99-3.49-.07-1.42-.93-2.67-2.22-3.25zM10 14.44V9.56c0-.25.26-.4.46-.3l3.33 1.67c.17.09.27.26.27.44s-.1.35-.27.44l-3.33 1.67c-.2.1-.46-.05-.46-.3z"/></svg>',
    'notification': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.93 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>',
    'privacy': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    'security': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/></svg>',
    'help': '<svg class="icon" viewBox="0 0 24 24"><path d="M11 18h2v-2h-2v2zm1-16C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-12S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm0-14c-2.21 0-4 1.79-4 4h2c0-1.1.9-2 2-2s2 .9 2 2c0 2-3 1.75-3 5h2c0-2.25 3-2.5 3-5 0-2.21-1.79-4-4-4z"/></svg>',
    'about': '<svg class="icon" viewBox="0 0 24 24"><path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-12S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>',
    'dots': '<svg class="icon" viewBox="0 0 24 24" style="width: 16px; height: 16px;"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>',
    'attachment': '<svg class="icon" viewBox="0 0 24 24"><path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/></svg>',
    'location': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>',
    'camera': '<svg class="icon" viewBox="0 0 24 24"><path d="M12 15.2C13.767 15.2 15.2 13.767 15.2 12 15.2 10.233 13.767 8.8 12 8.8 10.233 8.8 8.8 10.233 8.8 12 8.8 13.767 10.233 15.2 12 15.2zM20 7h-2.422l-1.5-2h-4.156l-1.5 2H8v2H6V5h4.922l1.5-2h3.156l1.5 2H20v14H4V9h2v10h14V7h-2V9h2V7zm-8 9c-2.488 0-4.5-2.012-4.5-4.5S9.512 7.5 12 7.5s4.5 2.012 4.5 4.5S14.488 16 12 16z"/></svg>'
}

# ---------------- HEADER FUNCTION -----------------
def get_header(user, current_page=""):
    if isinstance(user, dict):
        username = user["username"]
        uid = user["id"]
    else:
        try:
            if len(user) == 8:
                uid, fullname, username, email, password, age, height, photo = user
            else:
                uid, fullname, username, email, password, age, photo = user
        except:
            username = user[2] if len(user) > 2 else "user"
            uid = user[0] if len(user) > 0 else 0

    # Get unread notification count
    unread_notification_count = get_unread_notification_count(uid)
    notification_badge = f"<span class='badge'>{unread_notification_count}</span>" if unread_notification_count > 0 else ""

    return f"""
    <div class='nav-bar'>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <div style="font-size:22px; font-weight:700;">Momentum</div>
        <div style="display: flex; gap: 10px;">
            <a class='nav-icon' href="/notifications" style="position: relative;">{SVG_ICONS['notification']}{notification_badge}</a>
            <a class='nav-icon' href="/settings">{SVG_ICONS['settings']}</a>
        </div>
    </div>
    """

# ---------------- BOTTOM NAV FUNCTION -----------------
def get_bottom_nav(user, current_page=""):
    if isinstance(user, dict):
        username = user["username"]
        uid = user["id"]
    else:
        try:
            if len(user) == 8:
                uid, fullname, username, email, password, age, height, photo = user
            else:
                uid, fullname, username, email, password, age, photo = user
        except:
            username = user[2] if len(user) > 2 else "user"
            uid = user[0] if len(user) > 0 else 0
    
    home_active = "active" if current_page == "feed" else ""
    search_active = "active" if current_page == "search" else ""
    add_active = "active" if current_page == "create" else ""
    message_active = "active" if current_page == "direct" else ""
    profile_active = "active" if current_page == "profile" else ""
    
    unread_count = get_unread_message_count(uid)
    badge_html = f"<span class='badge'>{unread_count}</span>" if unread_count > 0 else ""
    
    return f"""
    <div class='bottom-nav'>
        <a class='nav-icon {home_active}' href="/feed">{SVG_ICONS['home']}</a>
        <a class='nav-icon {search_active}' href="/search">{SVG_ICONS['search']}</a>
        <a class='nav-icon {add_active}' href="/create">{SVG_ICONS['add']}</a>
        <a class='nav-icon {message_active}' href="/direct">{SVG_ICONS['message']}{badge_html}</a>
        <a class='nav-icon {profile_active}' href="/profile/{username}">{SVG_ICONS['profile']}</a>
    </div>
    """

# ================= AUTH ROUTES ===================
@app.route("/")
def home():
    if "user" in session:
        return redirect("/feed")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Momentum - Connect & Share</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: white; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }
            .logo-container { margin: 30px 0; text-align: center; }
            .logo-m { font-size: 72px; font-weight: 800; color: #262626; display: inline-block; margin-bottom: 10px; }
            .tagline { color: #8e8e8e; font-size: 16px; margin-top: 5px; letter-spacing: -0.3px; }
            .auth-container { width: 100%; max-width: 350px; }
            .form-tabs { display: flex; border-bottom: 1px solid #dbdbdb; margin-bottom: 20px; }
            .tab { flex: 1; padding: 16px; text-align: center; font-weight: 600; cursor: pointer; color: #8e8e8e; background: white; transition: all 0.3s; font-size: 14px; }
            .tab.active { color: #262626; border-bottom: 1px solid #262626; }
            .form-content {  }
            .form { display: none; }
            .form.active { display: block; }
            .form-group { margin-bottom: 16px; position: relative; }
            .form-group input { width: 100%; padding: 12px; border: 1px solid #dbdbdb; border-radius: 3px; font-size: 14px; background: #fafafa; transition: all 0.3s; }
            .form-group input:focus { border-color: #a8a8a8; outline: none; background: white; }
            .submit-btn { width: 100%; padding: 12px; background: #0095f6; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 8px; transition: all 0.3s; }
            .submit-btn:hover { background: #1877f2; }
            .divider { display: flex; align-items: center; margin: 20px 0; color: #8e8e8e; font-size: 13px; }
            .divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid #dbdbdb; }
            .divider::before { margin-right: 10px; }
            .divider::after { margin-left: 10px; }
            .social-login-btn { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 10px; border: 1px solid #dbdbdb; border-radius: 8px; background: white; cursor: pointer; font-weight: 600; margin-bottom: 8px; transition: all 0.3s; font-size: 14px; }
            .social-login-btn.facebook { background: #1877f2; color: white; border-color: #1877f2; }
            .social-login-btn.google { background: white; color: #262626; border-color: #dbdbdb; }
            .forgot-password { text-align: center; margin-top: 20px; }
            .forgot-password a { color: #00376b; text-decoration: none; font-size: 12px; }
            .signup-link { text-align: center; margin-top: 20px; padding: 20px; border: 1px solid #dbdbdb; border-radius: 1px; }
            .signup-link a { color: #0095f6; text-decoration: none; font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="logo-container">
            <div class="logo-m">M</div>
            <h1 style="font-size: 32px; font-weight: 700; margin-bottom: 5px; color: #262626;">Momentum</h1>
            <p class="tagline">Connect with friends and the world</p>
        </div>
        
        <div class="auth-container">
            <div class="form active" id="loginForm">
                <form method="POST" action="/login">
                    <div class="form-group">
                        <input type="text" name="username" placeholder="Username" required>
                    </div>
                    <div class="form-group">
                        <input type="password" name="password" placeholder="Password" required>
                    </div>
                    <button type="submit" class="submit-btn">Log In</button>
                </form>
                
                <div class="divider">OR</div>
                
                <button type="button" class="social-login-btn facebook">
                    <i class="fab fa-facebook-f"></i>
                    Continue with Facebook
                </button>
                <button type="button" class="social-login-btn google">
                    <i class="fab fa-google"></i>
                    Continue with Google
                </button>
                
                <div class="forgot-password">
                    <a href="/forgot_password">Forgot password?</a>
                </div>
            </div>
        </div>

        <div class="signup-link">
            Don't have an account? <a href="/register">Sign up</a>
        </div>

        <script>
            // Social login buttons
            document.querySelectorAll('.social-login-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const type = this.classList.contains('facebook') ? 'Facebook' : 'Google';
                    alert(`${type} login integration would be implemented here in a production app`);
                });
            });
        </script>
    </body>
    </html>
    """)

@app.route("/register")
def register():
    if "user" in session:
        return redirect("/feed")
    
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Sign Up - Momentum</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: white; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 20px; }
            .logo-container { margin: 30px 0; text-align: center; }
            .logo-m { font-size: 48px; font-weight: 800; color: #262626; display: inline-block; }
            .auth-container { width: 100%; max-width: 350px; }
            .form-group { margin-bottom: 16px; position: relative; }
            .form-group input { width: 100%; padding: 12px; border: 1px solid #dbdbdb; border-radius: 3px; font-size: 14px; background: #fafafa; transition: all 0.3s; }
            .form-group input:focus { border-color: #a8a8a8; outline: none; background: white; }
            .file-input { width: 100%; padding: 12px; border: 1px solid #dbdbdb; border-radius: 3px; font-size: 14px; background: #fafafa; cursor: pointer; text-align: center; }
            .submit-btn { width: 100%; padding: 12px; background: #0095f6; color: white; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 8px; transition: all 0.3s; }
            .submit-btn:hover { background: #1877f2; }
            .divider { display: flex; align-items: center; margin: 20px 0; color: #8e8e8e; font-size: 13px; }
            .divider::before, .divider::after { content: ''; flex: 1; border-bottom: 1px solid #dbdbdb; }
            .divider::before { margin-right: 10px; }
            .divider::after { margin-left: 10px; }
            .social-login-btn { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 10px; border: 1px solid #dbdbdb; border-radius: 8px; background: white; cursor: pointer; font-weight: 600; margin-bottom: 8px; transition: all 0.3s; font-size: 14px; }
            .social-login-btn.facebook { background: #1877f2; color: white; border-color: #1877f2; }
            .social-login-btn.google { background: white; color: #262626; border-color: #dbdbdb; }
            .login-link { text-align: center; margin-top: 20px; padding: 20px; border: 1px solid #dbdbdb; border-radius: 1px; }
            .login-link a { color: #0095f6; text-decoration: none; font-weight: 600; }
        </style>
    </head>
    <body>
        <div class="logo-container">
            <div class="logo-m">M</div>
            <h2 style="font-size: 20px; font-weight: 600; margin: 10px 0; color: #262626;">Sign up to see photos and videos from your friends.</h2>
        </div>
        
        <div class="auth-container">
            <form method="POST" action="/register_now" enctype="multipart/form-data">
                <div class="form-group">
                    <input type="text" name="fullname" placeholder="Full Name" required>
                </div>
                <div class="form-group">
                    <input type="text" name="username" placeholder="Username" required>
                </div>
                <div class="form-group">
                    <input type="email" name="email" placeholder="Email" required>
                </div>
                <div class="form-group">
                    <input type="password" name="password" placeholder="Password" required>
                </div>
                <div class="form-group">
                    <input type="number" name="age" placeholder="Age" required>
                </div>
                <div class="form-group">
                    <input type="file" name="photo" accept="image/*" class="file-input" required>
                </div>
                <button type="submit" class="submit-btn">Sign Up</button>
            </form>
            
            <div class="divider">OR</div>
            
            <button type="button" class="social-login-btn facebook">
                <i class="fab fa-facebook-f"></i>
                Sign up with Facebook
            </button>
            <button type="button" class="social-login-btn google">
                <i class="fab fa-google"></i>
                Sign up with Google
            </button>
        </div>

        <div class="login-link">
            Have an account? <a href="/">Log in</a>
        </div>

        <script>
            // Social login buttons
            document.querySelectorAll('.social-login-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const type = this.classList.contains('facebook') ? 'Facebook' : 'Google';
                    alert(`${type} login integration would be implemented here in a production app`);
                });
            });
        </script>
    </body>
    </html>
    """)

@app.route("/forgot_password")
def forgot_password():
    return render_template_string(momentum_css + """
    <div class='app-container'>
        <div style="max-width: 400px; margin: 0 auto; text-align: center;">
            <h2 style="margin-bottom: 20px;">Reset Password</h2>
            <p style="color: #666; margin-bottom: 30px;">Enter your email address and we'll send you a link to reset your password.</p>
            <form method="POST" action="/send_reset_link">
                <input class="form-input" type="email" name="email" placeholder="Enter your email" required>
                <button class="btn" style="width: 100%;">Send Reset Link</button>
            </form>
            <a href="/" class="btn-outline" style="display: block; margin-top: 15px; text-align: center;">Back to Login</a>
        </div>
    </div>
    """)

@app.route("/send_reset_link", methods=["POST"])
def send_reset_link():
    email = request.form.get("email")
    # In a real app, you would send an email with a reset link
    return "Password reset link has been sent to your email!"

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()

    if user:
        session["user"] = tuple(user)
        
        # Create login alert
        device_name = request.headers.get('User-Agent', 'Unknown Device')[:50]
        ip_address = request.remote_addr
        location = "Unknown Location"  # In production, use IP geolocation service
        user_agent = request.headers.get('User-Agent', 'Unknown')[:100]
        
        create_login_alert(user["id"], device_name, ip_address, location, user_agent)
        
        return redirect("/feed")
    else:
        return "Invalid username or password!"

@app.route("/register_now", methods=["POST"])
def register_now():
    fullname = request.form["fullname"]
    username = request.form["username"]
    email = request.form["email"]
    password = request.form["password"]
    age = request.form["age"]

    file = request.files["photo"]
    filename = secure_filename(file.filename)
    file.save(os.path.join("static/photos", filename))

    conn = get_db_conn()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO users(fullname, username, email, password, age, photo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fullname, username, email, password, age, filename))
        conn.commit()
    except Exception as e:
        conn.close()
        return f"Username or Email already taken. Error: {str(e)}"

    conn.close()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= FEED PAGE ====================
@app.route("/feed")
def feed():
    if "user" not in session:
        return redirect("/")

    refresh_session_user()
    user = session["user"]
    uid = user[0] if isinstance(user, tuple) else user["id"]

    # Get category and search from request
    category = request.args.get('category', 'feed')
    search_query = request.args.get('search', '')
    
    # Determine video duration based on category
    video_duration = None
    if category == 'shorts':
        video_duration = 'short'
    elif category == 'long':
        video_duration = 'medium'

    # Get YouTube videos based on search and category (only for long and shorts)
    youtube_videos = []
    next_page_token = None
    if category in ['long', 'shorts']:
        youtube_videos, next_page_token = fetch_youtube_shorts(
            search_query=search_query if search_query else None,
            video_duration=video_duration
        )
        youtube_videos_cache[uid] = youtube_videos
        current_page_tokens[uid] = next_page_token

    # Get user posts (for feed category only)
    user_posts = []
    if category == 'feed':
        # For feed, show posts from user and followed users (like mom.py)
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            SELECT p.*, u.username, u.photo AS user_photo
            FROM posts p
            JOIN users u ON p.user_id = u.id
            WHERE p.user_id = ? OR p.user_id IN
                  (SELECT user_id FROM followers WHERE follower_id=?)
            ORDER BY datetime(p.timestamp) DESC
            LIMIT 50
        """, (uid, uid))
        user_posts = c.fetchall()
        conn.close()

    # Combine posts and YouTube videos
    all_posts = []
    
    # Add user posts (for feed only)
    if category == 'feed':
        for post in user_posts:
            all_posts.append({
                'type': 'user',
                'data': post,
                'id': f"user_{post['id']}"
            })
    
    # Add YouTube videos (only for long and shorts)
    if category in ['long', 'shorts']:
        for video in youtube_videos:
            all_posts.append({
                'type': 'youtube',
                'data': video,
                'id': f"youtube_{video['video_id']}",
                'is_short': category == 'shorts'
            })

    # Shuffle posts for better mix (only if no search query)
    if not search_query and category != 'feed':
        random.shuffle(all_posts)

    posts_html = ""
    for post in all_posts:
        if post['type'] == 'user':
            p = post['data']
            like_count = get_like_count(p["id"])
            comment_count = get_comment_count(p["id"])
            is_liked_flag = is_liked(p["id"], uid)

            like_icon = SVG_ICONS['heart'] if is_liked_flag else SVG_ICONS['heart_outline']

            media_html = ""
            if p["media_type"] == "image":
                media_html = f"<img src='/static/posts/{p['media']}' style='width:100%; max-height: 400px; object-fit: contain; background: #000; border-radius: 8px;'>"
            else:
                media_html = f"""
                <div class="video-container">
                    <video class="video-player" controls playsinline style="border-radius: 8px;">
                        <source src='/static/posts/{p["media"]}' type='video/mp4'>
                        Your browser does not support the video tag.
                    </video>
                    <div class="video-controls">
                        <button class="control-btn" onclick="togglePlayPause(this)">{SVG_ICONS['play']}</button>
                        <button class="control-btn" onclick="toggleMute(this)">{SVG_ICONS['volume']}</button>
                    </div>
                </div>
                """

            posts_html += f"""
            <div class="post-item" id="{post['id']}">
                <div style='background:white; border:1px solid var(--border-gray); border-radius:12px; overflow: hidden; margin-bottom: 20px;'>
                    <div style='display:flex; align-items:center; padding:12px;'>
                        <img src='/static/photos/{p['user_photo']}' style='width:40px;height:40px;border-radius:50%;margin-right:10px; object-fit: cover;'>
                        <b><a href='/profile/{p['username']}' style='color:black; text-decoration:none;'>{p['username']}</a></b>
                    </div>

                    {media_html}

                    <div style='padding:12px;'>
                        <div style='display:flex; gap:12px; font-size:22px;'>
                            <a href='/like/{p["id"]}' style='text-decoration:none; color: {"#ed4956" if is_liked_flag else "black"};'>{like_icon}</a>
                            <a href='/post/{p["id"]}/comments' style='text-decoration:none; color: black;'>{SVG_ICONS['comment']}</a>
                        </div>

                        <p style='margin-top:5px; font-weight:bold;'>{like_count} likes</p>

                        <p style='margin: 8px 0;'><b>{p['username']}</b> {p['caption']}</p>

                        <a href='/post/{p["id"]}/comments' style='color:gray; text-decoration: none;'>View all {comment_count} comments</a>
                    </div>
                </div>
            </div>
            """
        else:
            # YouTube post
            video = post['data']
            embed_url = get_youtube_embed_url(video['video_id'])
            is_short = post.get('is_short', False)
            
            posts_html += f"""
            <div class="post-item" id="{post['id']}">
                <div style='background:white; border:1px solid var(--border-gray); border-radius:12px; overflow: hidden; margin-bottom: 20px;'>
                    <div style='display:flex; align-items:center; padding:12px;'>
                        <img src='{video['thumbnail']}' style='width:40px;height:40px;border-radius:50%;margin-right:10px; object-fit: cover;'>
                        <div style='flex: 1;'>
                            <b style='color:black; text-decoration:none;'>Momentum</b>
                            <span class='youtube-badge'>YouTube {'Short' if is_short else 'Video'}</span>
                        </div>
                        {SVG_ICONS['youtube']}
                    </div>

                    <div class="video-container">
                        <iframe 
                            src='{embed_url}'
                            class="video-player"
                            frameborder="0"
                            style="border-radius: 8px;"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowfullscreen
                            loading="lazy">
                        </iframe>
                    </div>

                    <div style='padding:12px;'>
                        <div style='display:flex; gap:12px; font-size:22px;'>
                            <span style='text-decoration:none; color: black;'>{SVG_ICONS['heart_outline']}</span>
                            <span style='text-decoration:none; color: black;'>{SVG_ICONS['comment']}</span>
                        </div>

                        <p style='margin-top:5px; font-weight:bold;'>0 likes</p>

                        <p style='margin: 8px 0;'><b>Momentum</b> {video['title']} - Momentum College IT from YouTube</p>
                        <p style='color: #666; font-size: 14px;'>Channel: {video['channel_title']}</p>

                        <span style='color:gray; text-decoration: none;'>View all 0 comments</span>
                    </div>
                </div>
            </div>
            """

    # Category tabs and search
    category_tabs = f"""
    <div class="category-tabs">
        <div class="category-tab {'active' if category == 'feed' else ''}" onclick="switchCategory('feed')">
            Feed
        </div>
        <div class="category-tab {'active' if category == 'long' else ''}" onclick="switchCategory('long')">
            Long Video
        </div>
        <div class="category-tab {'active' if category == 'shorts' else ''}" onclick="switchCategory('shorts')">
            {SVG_ICONS['shorts']} Shorts
        </div>
    </div>
    
    <div class="search-container">
        <form method="GET" action="/feed" onsubmit="return handleSearch()">
            <input type="hidden" name="category" id="categoryInput" value="{category}">
            <input type="text" name="search" class="search-input" placeholder="Search for your video..." value="{search_query}">
        </form>
    </div>
    """

    # View More button
    view_more_btn = """
    <div class="view-more" onclick="loadMoreVideos()">
        View More Videos
    </div>
    """ if not search_query and category in ['long', 'shorts'] else ""

    # JavaScript for category switching and search
    category_js = f"""
    <script>
        let currentCategory = '{category}';
        let currentSearch = '{search_query}';
        let isLoading = false;
        let page = 1;
        
        function switchCategory(cat) {{
            currentCategory = cat;
            document.getElementById('categoryInput').value = cat;
            window.location.href = `/feed?category=${{cat}}&search=${{currentSearch}}`;
        }}
        
        function handleSearch() {{
            currentSearch = document.querySelector('input[name="search"]').value;
            return true;
        }}
        
        function loadMoreVideos() {{
            if (isLoading) return;
            isLoading = true;
            
            const viewMoreBtn = document.querySelector('.view-more');
            viewMoreBtn.innerHTML = 'Loading...';
            
            // Reload the page with next set of videos
            setTimeout(() => {{
                window.location.href = `/feed?category=${{currentCategory}}&search=${{currentSearch}}&refresh=${{Date.now()}}`;
            }}, 1000);
        }}
        
        // Video controls
        function togglePlayPause(btn) {{
            const container = btn.closest('.video-container');
            const video = container.querySelector('video');
            if (video.paused) {{
                video.play();
                btn.innerHTML = `{SVG_ICONS['pause']}`;
            }} else {{
                video.pause();
                btn.innerHTML = `{SVG_ICONS['play']}`;
            }}
        }}
        
        function toggleMute(btn) {{
            const container = btn.closest('.video-container');
            const video = container.querySelector('video');
            video.muted = !video.muted;
            btn.style.opacity = video.muted ? '0.5' : '1';
        }}
        
        // Auto-play videos when they come into view
        const observer = new IntersectionObserver((entries) => {{
            entries.forEach(entry => {{
                if (entry.isIntersecting) {{
                    const video = entry.target.querySelector('video');
                    const iframe = entry.target.querySelector('iframe');
                    if (video) {{
                        video.play().catch(e => console.log('Auto-play failed:', e));
                    }}
                }} else {{
                    const video = entry.target.querySelector('video');
                    if (video) {{
                        video.pause();
                    }}
                }}
            }});
        }}, {{ threshold: 0.8 }});
        
        // Observe all video containers
        document.querySelectorAll('.video-container').forEach(container => {{
            observer.observe(container);
        }});
    </script>
    """

    html = momentum_css + get_header(session["user"], "feed") + f"""
    <div class="app-container">
        {category_tabs}
        <div id="posts-container" class="feed-container">
            {posts_html if posts_html else "<h3 style='text-align: center; color: #666; padding: 40px;'>No content found. Try searching with different terms or switch categories.</h3>"}
            {view_more_btn}
        </div>
    </div>
    {category_js}
    """ + get_bottom_nav(session["user"], "feed")

    return render_template_string(html)

# ================= CREATE POST ====================
@app.route("/create")
def create():
    if "user" not in session:
        return redirect("/")
    return render_template_string(momentum_css + get_header(session["user"], "create") + """
        <div class='app-container'>
            <h2 style='text-align: center; margin-bottom: 30px;'>Create Post</h2>
            <form method='POST' enctype="multipart/form-data" action='/create_now'>
                <textarea class='form-input' name='caption' placeholder="Write a caption..." style='height: 100px; resize: vertical;'></textarea>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Select Media</label>
                <input class='file-input' type='file' name='media' accept='image/*,video/*' required>
                <button class='btn' style='width:100%; margin-top: 20px;'>Share Post</button>
            </form>
        </div>
        """ + get_bottom_nav(session["user"], "create"))

@app.route("/create_now", methods=["POST"])
def create_now():
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    caption = request.form.get("caption", "")

    file = request.files["media"]
    filename = secure_filename(file.filename)
    file.save(os.path.join("static/posts", filename))

    media_type = detect_media_type(filename)
    timestamp = datetime.datetime.now().isoformat()

    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO posts(user_id, caption, media, media_type, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (uid, caption, filename, media_type, timestamp))
    conn.commit()
    conn.close()

    return redirect("/feed")

# ================= LIKE SYSTEM ====================
@app.route("/like/<pid>")
def like(pid):
    if "user" not in session:
        return redirect("/")
    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]

    conn = get_db_conn()
    c = conn.cursor()

    if is_liked(pid, uid):
        c.execute("DELETE FROM likes WHERE post_id=? AND user_id=?", (pid, uid))
    else:
        c.execute("INSERT INTO likes(post_id, user_id) VALUES (?, ?)", (pid, uid))
        # Create notification for post owner
        c.execute("SELECT user_id FROM posts WHERE id=?", (pid,))
        post = c.fetchone()
        if post and post["user_id"] != uid:
            user = fetch_user_by_id(uid)
            create_notification(post["user_id"], "like", uid, pid, f"{user['username']} liked your post")

    conn.commit()
    conn.close()
    return redirect("/feed")

# ================= COMMENT SYSTEM ====================
@app.route("/comment/<pid>", methods=["POST"])
def comment(pid):
    if "user" not in session:
        return redirect("/")
    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    comment_text = request.form.get("comment", "").strip()

    if comment_text:
        ts = datetime.datetime.now().isoformat()
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO comments(post_id, user_id, comment, timestamp)
            VALUES (?, ?, ?, ?)
        """, (pid, uid, comment_text, ts))
        
        # Create notification for post owner
        c.execute("SELECT user_id FROM posts WHERE id=?", (pid,))
        post = c.fetchone()
        if post and post["user_id"] != uid:
            user = fetch_user_by_id(uid)
            create_notification(post["user_id"], "comment", uid, pid, f"{user['username']} commented on your post")
            
        conn.commit()
        conn.close()

    return redirect(f"/post/{pid}/comments")

# ================= VIEW SINGLE POST COMMENTS PAGE ===================
@app.route("/post/<pid>/comments")
def post_comments(pid):
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]

    conn = get_db_conn()
    c = conn.cursor()

    # Fetch post
    c.execute("""
        SELECT p.*, u.username, u.photo AS user_photo
        FROM posts p 
        JOIN users u ON p.user_id = u.id
        WHERE p.id=?
    """, (pid,))
    post = c.fetchone()

    # Fetch comments
    c.execute("""
        SELECT c.*, u.username, u.photo AS user_photo
        FROM comments c
        JOIN users u ON c.user_id = u.id
        WHERE c.post_id=?
        ORDER BY datetime(c.timestamp)
    """, (pid,))
    comments = c.fetchall()

    conn.close()

    comments_html = ""
    for cm in comments:
        comments_html += f"""
        <div style='display:flex; gap:10px; padding:12px 0; border-bottom:1px solid #eee;'>
            <img src='/static/photos/{cm["user_photo"]}' style='width:36px;height:36px;border-radius:50%; object-fit: cover;'>
            <div style='flex: 1;'>
                <b>{cm["username"]}</b><br>
                <span style='color: #333;'>{cm["comment"]}</span>
            </div>
        </div>
        """

    media_html = ""
    if post["media_type"] == "image":
        media_html = f"<img src='/static/posts/{post['media']}' style='width:100%; border-radius: 8px;'>"
    else:
        media_html = f"<video src='/static/posts/{post['media']}' controls style='width:100%; border-radius: 8px;'></video>"

    html = momentum_css + get_header(session["user"]) + f"""
        <div class='app-container'>
            <div style="margin-bottom:20px;">
                <div style='display:flex; align-items:center; gap:10px; margin-bottom: 15px;'>
                    <img src='/static/photos/{post["user_photo"]}' style='width:40px;height:40px;border-radius:50%; object-fit: cover;'>
                    <b>{post["username"]}</b>
                </div>
                <div style="margin-top:10px;">{media_html}</div>
                <p style='margin: 12px 0;'><b>{post["username"]}</b> {post["caption"]}</p>
            </div>

            <h3 style='margin-bottom: 15px;'>Comments</h3>
            <div style='max-height: 300px; overflow-y: auto;'>
                {comments_html if comments_html else "<p style='text-align: center; color: #666;'>No comments yet</p>"}
            </div>

            <form method='POST' action='/comment/{pid}' style='margin-top:20px;'>
                <input name='comment' class='form-input' placeholder='Write a comment...' style='margin-bottom: 10px;'>
                <button class='btn' style='width: 100%;'>Post Comment</button>
            </form>
        </div>
        """ + get_bottom_nav(session["user"])

    return render_template_string(html)

# =================== SEARCH PAGE =====================
@app.route("/search", methods=["GET", "POST"])
def search():
    if "user" not in session:
        return redirect("/")

    query = ""

    results_html = ""

    if request.method == "POST":
        query = request.form.get("query", "").strip()

        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            SELECT * FROM users 
            WHERE username LIKE ? OR fullname LIKE ?
        """, (f"%{query}%", f"%{query}%"))
        results = c.fetchall()
        conn.close()

        for u in results:
            results_html += f"""
            <a href='/profile/{u["username"]}' 
               style='display:flex; gap:12px; padding:12px;
                      border-bottom:1px solid #eee; text-decoration:none; color:black; align-items: center;'>
                <img src='/static/photos/{u["photo"]}' 
                    style='width:50px; height:50px; border-radius:50%; object-fit: cover;'>
                <div>
                    <b style='display: block; margin-bottom: 4px;'>{u["username"]}</b>
                    <span style='color:gray; font-size:14px;'>{u["fullname"]}</span>
                </div>
            </a>
            """

    html = momentum_css + get_header(session["user"], "search") + f"""
        <div class='app-container'>
            <h2 style='margin-bottom: 20px;'>Search</h2>

            <form method='POST'>
                <input class='form-input' name='query' value='{query}' placeholder='Search users by username or name...'>
            </form>

            <div style='margin-top:20px; background: white; border-radius: 12px; overflow: hidden;'>
                {results_html if results_html else "<p style='text-align: center; padding: 30px; color: #666;'>No users found. Try searching with different terms.</p>"}
            </div>
        </div>
        """ + get_bottom_nav(session["user"], "search")

    return render_template_string(html)

# ================= FOLLOW USER =====================
@app.route("/follow/<tid>")
def follow(tid):
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]

    conn = get_db_conn()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO followers(user_id, follower_id) VALUES (?, ?)", (tid, uid))
        conn.commit()
        
        # Create notification for followed user
        user = fetch_user_by_id(uid)
        create_notification(tid, "follow", uid, tid, f"{user['username']} started following you")
    except Exception as e:
        print(f"Follow error: {e}")
        # Don't rollback, just continue

    conn.close()

    target = fetch_user_by_id(tid)
    return redirect(f"/profile/{target['username']}")

# ================= UNFOLLOW USER =====================
@app.route("/unfollow/<tid>")
def unfollow(tid):
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]

    conn = get_db_conn()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM followers WHERE user_id=? AND follower_id=?", (tid, uid))
        conn.commit()
    except Exception as e:
        print(f"Unfollow error: {e}")
        # Don't rollback, just continue

    conn.close()

    target = fetch_user_by_id(tid)
    return redirect(f"/profile/{target['username']}")

# ================= PROFILE PAGE =====================
@app.route("/profile/<username>")
def profile(username):
    if "user" not in session:
        return redirect("/")

    viewer = session["user"]
    viewer_id = viewer[0] if isinstance(viewer, tuple) else viewer["id"]

    target = fetch_user_by_username(username)
    if not target:
        return "User not found."

    target_id = target["id"]

    # Follow Button Logic - FIXED
    if viewer_id != target_id:
        if is_following(target_id, viewer_id):
            follow_btn = f"<a href='/unfollow/{target_id}' class='btn-outline'>Unfollow</a>"
        else:
            follow_btn = f"<a href='/follow/{target_id}' class='btn'>Follow</a>"
    else:
        follow_btn = ""

    # Post grid
    posts = get_user_posts(target_id)
    grid_html = ""
    for p in posts:
        if p["media_type"] == "image":
            grid_html += f"""
            <div class='post-grid-item'>
                <a href='/post/{p["id"]}/comments'>
                    <img src='/static/posts/{p["media"]}' alt='Post'>
                </a>
            </div>
            """
        else:
            grid_html += f"""
            <div class='post-grid-item'>
                <a href='/post/{p["id"]}/comments'>
                    <video src='/static/posts/{p["media"]}' style='object-fit: cover;'>
                </a>
            </div>
            """

    # FOLLOW / MESSAGE BUTTON + FULL NAME
    action_buttons = ""
    if viewer_id != target_id:
        action_buttons = f"""
            <div style='display:flex; gap:12px; margin-top:10px;'>
                {follow_btn}
                <a href='/chat/{username}' class='btn' 
                   style='background:#0095F6; color:white;'>Message</a>
            </div>
        """

    html = momentum_css + get_header(session["user"], "profile") + f"""
        <div class='app-container'>

            <div style='display:flex; gap:20px; margin-top:20px; align-items:center;'>
                <img src='/static/photos/{target["photo"]}' 
                     style='width:90px; height:90px; border-radius:50%; object-fit:cover;'>

                <div style='flex: 1;'>
                    <h2 style='margin:0; padding:0; font-size: 24px;'>{target["fullname"]}</h2>
                    <p style='margin: 5px 0; color: #666;'>@{target["username"]}</p>
                    {action_buttons}
                </div>
            </div>

            <div style='display:flex; gap:25px; margin-top:20px; text-align: center;'>
                <div><b style='display: block; font-size: 18px;'>{len(posts)}</b><span style='color: #666;'>posts</span></div>
                <div><b style='display: block; font-size: 18px;'>{followers_count(target_id)}</b><span style='color: #666;'>followers</span></div>
                <div><b style='display: block; font-size: 18px;'>{following_count(target_id)}</b><span style='color: #666;'>following</span></div>
            </div>

            <hr style='margin:20px 0;'>

            <div class='post-grid'>
                {grid_html if grid_html else "<div style='grid-column: 1 / -1; text-align: center; padding: 40px; color: #666;'>No posts yet</div>"}
            </div>

        </div>
        """ + get_bottom_nav(session["user"], "profile")

    return render_template_string(html)

# ================= DIRECT MESSAGE (INBOX) =====================
@app.route("/direct")
def direct():
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]

    conn = get_db_conn()
    c = conn.cursor()

    # fetch all chat partners (unique) with unread count
    c.execute("""
        SELECT 
            CASE
                WHEN sender_id = ? THEN receiver_id
                ELSE sender_id
            END AS chat_user,
            COUNT(CASE WHEN receiver_id = ? AND is_read = 0 THEN 1 END) AS unread_count,
            MAX(timestamp) AS last_message_time
        FROM messages
        WHERE sender_id = ? OR receiver_id = ?
        GROUP BY chat_user
        ORDER BY last_message_time DESC
    """, (uid, uid, uid, uid))

    rows = c.fetchall()
    conn.close()

    chat_list_html = ""

    for r in rows:
        partner = fetch_user_by_id(r["chat_user"])
        unread_badge = f"<span style='background: var(--red); color: white; border-radius: 50%; width: 20px; height: 20px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; margin-left: 8px;'>{r['unread_count']}</span>" if r["unread_count"] > 0 else ""
        
        chat_list_html += f"""
        <a href='/chat/{partner["username"]}' 
           style='display:flex; align-items:center; gap:12px; padding:15px;
                  border-bottom:1px solid #eee; text-decoration:none; color:black;'>
            <img src='/static/photos/{partner["photo"]}' 
                 style='width:50px; height:50px; border-radius:50%; object-fit:cover;'>
            <div style='flex: 1;'>
                <div style='display: flex; align-items: center;'>
                    <b style='display: block; margin-bottom: 4px;'>{partner["username"]}</b>
                    {unread_badge}
                </div>
                <span style='color:gray; font-size:14px;'>Tap to message</span>
            </div>
        </a>
        """

    html = momentum_css + get_header(session["user"], "direct") + f"""
        <div class='app-container'>
            <h2 style='margin-bottom: 20px;'>Messages</h2>
            <div style='margin-top:20px; background: white; border-radius: 12px; overflow: hidden;'>
                {chat_list_html if chat_list_html else "<p style='text-align: center; padding: 40px; color: #666;'>No messages yet. Start a conversation!</p>"}
            </div>
        </div>
        """ + get_bottom_nav(session["user"], "direct")

    return render_template_string(html)

# ================= CHAT WINDOW =====================
@app.route("/chat/<username>", methods=["GET", "POST"])
def chat(username):
    if "user" not in session:
        return redirect("/")

    sender_id = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    receiver = fetch_user_by_username(username)

    if not receiver:
        return "User does not exist."

    receiver_id = receiver["id"]

    # Mark messages as read when opening chat
    mark_messages_as_read(receiver_id, sender_id)

    # SEND MESSAGE
    if request.method == "POST":
        msg = request.form.get("message", "").strip()
        reply_to = request.form.get("reply_to", "")
        media_file = request.files.get("media", None)
        location_data = request.form.get("location_data", "")
        
        if msg or media_file or location_data:
            ts = datetime.datetime.now().isoformat()
            conn = get_db_conn()
            c = conn.cursor()
            
            media_filename = None
            media_type = None
            if media_file and media_file.filename:
                media_filename = secure_filename(media_file.filename)
                # Save to messages folder instead of posts
                file_path = os.path.join("static/messages", media_filename)
                media_file.save(file_path)
                media_type = detect_media_type(media_filename)
            
            c.execute("""
                INSERT INTO messages(sender_id, receiver_id, message, media, media_type, location_data, timestamp, reply_to)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (sender_id, receiver_id, msg, media_filename, media_type, location_data, ts, reply_to if reply_to else None))
            conn.commit()
            conn.close()
            
            # Create notification for the receiver
            sender = fetch_user_by_id(sender_id)
            create_notification(receiver_id, "message", sender_id, c.lastrowid, f"{sender['username']} sent you a message")

        return redirect(f"/chat/{username}")

    # FETCH CHAT HISTORY
    conn = get_db_conn()
    c = conn.cursor()

    c.execute("""
        SELECT m.*, u.username, u.photo AS user_photo
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE (sender_id=? AND receiver_id=?) OR 
              (sender_id=? AND receiver_id=?)
        ORDER BY datetime(timestamp)
    """, (sender_id, receiver_id, receiver_id, sender_id))

    msgs = c.fetchall()
    conn.close()

    # MESSAGE BUBBLES
    msgs_html = ""
    for m in msgs:
        align = "right" if m["sender_id"] == sender_id else "left"
        color = "#DCF8C6" if m["sender_id"] == sender_id else "#ffffff"
        read_status = "✓✓" if m["is_read"] else "✓"
        read_color = "blue" if m["is_read"] else "gray"

        # Check if this message is a reply
        reply_html = ""
        if m["reply_to"]:
            replied_msg = get_replied_message(m["reply_to"])
            if replied_msg:
                reply_html = f"""
                <div class='reply-indicator'>
                    Replying to: {replied_msg['username']} - {replied_msg['message'][:50]}{'...' if len(replied_msg['message']) > 50 else ''}
                </div>
                """

        # Media content
        media_html = ""
        if m["media"]:
            if m["media_type"] == "image":
                media_html = f'<img src="/static/messages/{m["media"]}" class="media-attachment">'
            else:
                media_html = f'<video src="/static/messages/{m["media"]}" controls class="media-attachment">'
        
        # Location content
        location_html = ""
        if m["location_data"]:
            location_data = json.loads(m["location_data"])
            location_html = f"""
            <div class="location-share">
                <strong>📍 Live Location</strong><br>
                <small>Lat: {location_data.get('lat', 'N/A')}, Lng: {location_data.get('lng', 'N/A')}</small>
            </div>
            """

        # Get reactions for this message
        reactions_html = ""
        reactions = get_message_reactions(m["id"])
        if reactions:
            reaction_counts = {}
            for user_id, emoji in reactions.items():
                reaction_counts[emoji] = reaction_counts.get(emoji, 0) + 1
            
            for emoji, count in reaction_counts.items():
                reactions_html += f'<span class="reaction">{emoji} {count}</span>'

        msgs_html += f"""
        <div style='text-align:{align}; margin:8px 0; position: relative;' 
             id="message-container-{m['id']}"
             oncontextmenu="showTouchHoldMenu(event, {m['id']}, {m['sender_id'] == sender_id})">
            {reply_html}
            <div class='message-bubble' style='display:inline-block; padding:12px 16px;
                        background:{color};
                        border-radius:18px;
                        max-width:70%;
                        font-size:14px;
                        border:1px solid #e0e0e0;
                        position: relative;'
                 id="message-{m['id']}">
                <b style='font-size:12px; color: #666;'>{m["username"]}</b><br>
                {media_html}
                {location_html}
                <span style='word-break: break-word;'>{m["message"]}</span>
                <div style='text-align: right; margin-top: 4px;'>
                    <span style='font-size: 10px; color: {read_color};'>{read_status}</span>
                    <span style='font-size: 10px; color: #999; margin-left: 5px;'>{format_time(m["timestamp"])}</span>
                </div>
                {reactions_html}
            </div>
        </div>
        """

    # JavaScript for message actions with improved UI
    js_script = f"""
    <script>
        var box = document.getElementById('chatbox');
        if (box) box.scrollTop = box.scrollHeight;
        
        var currentMessageId = null;
        var isOwnMessage = false;
        var touchStartTime = 0;
        var longPressTimer = null;

        function showTouchHoldMenu(event, messageId, ownMessage) {{
            event.preventDefault();
            currentMessageId = messageId;
            isOwnMessage = ownMessage;
            
            var messageElement = document.getElementById('message-' + messageId);
            var rect = messageElement.getBoundingClientRect();
            
            var touchMenu = document.getElementById('touchHoldMenu');
            touchMenu.style.display = 'block';
            
            // Position menu based on message alignment
            if (ownMessage) {{
                // For own messages (right-aligned), show menu on the right side
                touchMenu.style.left = (rect.right - 150) + 'px';
            }} else {{
                // For other user's messages (left-aligned), show menu on the left side
                touchMenu.style.left = (rect.left) + 'px';
            }}
            touchMenu.style.top = (rect.top - 80) + 'px';
            
            document.getElementById('editBtn').style.display = ownMessage ? 'block' : 'none';
            document.getElementById('deleteBtn').style.display = ownMessage ? 'block' : 'none';
            
            document.getElementById('emojiPicker').style.display = 'none';
            document.getElementById('attachmentMenu').style.display = 'none';
        }}

        function hideTouchHoldMenu() {{
            document.getElementById('touchHoldMenu').style.display = 'none';
        }}

        // Add touch event listeners for hold gesture
        document.addEventListener('DOMContentLoaded', function() {{
            document.querySelectorAll('.message-bubble').forEach(bubble => {{
                bubble.addEventListener('touchstart', function(e) {{
                    touchStartTime = Date.now();
                    var messageId = this.id.replace('message-', '');
                    var isOwn = this.closest('div[style*="text-align:right"]') !== null;
                    
                    longPressTimer = setTimeout(() => {{
                        showTouchHoldMenu(e, messageId, isOwn);
                    }}, 500);
                }});
                
                bubble.addEventListener('touchend', function() {{
                    clearTimeout(longPressTimer);
                }});
                
                bubble.addEventListener('touchmove', function() {{
                    clearTimeout(longPressTimer);
                }});
            }});
        }});

        function showAttachmentMenu() {{
            var attachmentMenu = document.getElementById('attachmentMenu');
            attachmentMenu.style.display = 'block';
            hideTouchHoldMenu();
        }}

        function shareLocation() {{
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(position) {{
                    var lat = position.coords.latitude;
                    var lng = position.coords.longitude;
                    
                    document.getElementById('locationData').value = JSON.stringify({{lat: lat, lng: lng}});
                    document.getElementById('messageInput').value = '📍 Sharing my live location';
                    document.getElementById('messageForm').submit();
                }});
            }} else {{
                alert('Geolocation is not supported by this browser.');
            }}
            document.getElementById('attachmentMenu').style.display = 'none';
        }}

        function showEmojiPicker() {{
            var emojiPicker = document.getElementById('emojiPicker');
            var touchMenu = document.getElementById('touchHoldMenu');
            var rect = touchMenu.getBoundingClientRect();
            
            emojiPicker.style.display = 'grid';
            emojiPicker.style.left = (rect.left) + 'px';
            emojiPicker.style.top = (rect.top - 60) + 'px';
            
            hideTouchHoldMenu();
        }}

        function addReaction(emoji) {{
            if (currentMessageId) {{
                showNotification('Reaction added: ' + emoji);
                window.location.href = '/react/' + currentMessageId + '/' + encodeURIComponent(emoji);
            }}
            document.getElementById('emojiPicker').style.display = 'none';
        }}

        function replyToMessage() {{
            if (currentMessageId) {{
                var messageElement = document.getElementById('message-' + currentMessageId);
                var messageText = messageElement.querySelector('span').textContent;
                
                document.getElementById('replyIndicator').style.display = 'block';
                document.getElementById('replyText').textContent = messageText.substring(0, 50) + (messageText.length > 50 ? '...' : '');
                document.getElementById('replyTo').value = currentMessageId;
                
                document.getElementById('messageInput').focus();
                showNotification('Replying to message');
            }}
            hideTouchHoldMenu();
        }}

        function cancelReply() {{
            document.getElementById('replyIndicator').style.display = 'none';
            document.getElementById('replyTo').value = '';
            showNotification('Reply cancelled');
        }}

        function editMessage() {{
            if (currentMessageId && isOwnMessage) {{
                var messageElement = document.getElementById('message-' + currentMessageId);
                var messageText = messageElement.querySelector('span').textContent;
                
                document.getElementById('messageInput').value = messageText;
                document.getElementById('messageInput').focus();
                
                var form = document.getElementById('messageForm');
                form.action = '/edit_message/' + currentMessageId;
                form.querySelector('button').textContent = 'Update';
                
                if (!document.getElementById('cancelEdit')) {{
                    var cancelBtn = document.createElement('button');
                    cancelBtn.type = 'button';
                    cancelBtn.id = 'cancelEdit';
                    cancelBtn.textContent = 'Cancel';
                    cancelBtn.className = 'btn-outline';
                    cancelBtn.style.marginRight = '10px';
                    cancelBtn.onclick = cancelEdit;
                    form.insertBefore(cancelBtn, form.querySelector('button'));
                }}
                
                showNotification('Editing message');
            }}
            hideTouchHoldMenu();
        }}

        function cancelEdit() {{
            var form = document.getElementById('messageForm');
            form.action = '/chat/{username}';
            form.querySelector('button').textContent = 'Send';
            document.getElementById('messageInput').value = '';
            
            var cancelBtn = document.getElementById('cancelEdit');
            if (cancelBtn) cancelBtn.remove();
            
            showNotification('Edit cancelled');
        }}

        function deleteMessage() {{
            if (currentMessageId && isOwnMessage && confirm('Are you sure you want to delete this message?')) {{
                showNotification('Message deleted');
                window.location.href = '/delete_message/' + currentMessageId;
            }}
            hideTouchHoldMenu();
        }}

        function showNotification(message) {{
            var notification = document.createElement('div');
            notification.className = 'notification-bubble';
            notification.innerHTML = message;
            notification.style.animation = 'slideInRight 0.3s ease-out';
            
            document.body.appendChild(notification);
            
            setTimeout(() => {{
                if (notification.parentNode) {{
                    notification.style.animation = 'slideOutRight 0.3s ease-out';
                    setTimeout(() => {{
                        if (notification.parentNode) {{
                            notification.remove();
                        }}
                    }}, 300);
                }}
            }}, 2000);
        }}

        document.addEventListener('click', function(e) {{
            if (!e.target.closest('.touch-hold-menu') && 
                !e.target.closest('.emoji-picker') && 
                !e.target.closest('.attachment-menu')) {{
                hideTouchHoldMenu();
                document.getElementById('emojiPicker').style.display = 'none';
                document.getElementById('attachmentMenu').style.display = 'none';
            }}
        }});

        // Auto-scroll to bottom
        setTimeout(() => {{
            var chatbox = document.getElementById('chatbox');
            if (chatbox) chatbox.scrollTop = chatbox.scrollHeight;
        }}, 100);
    </script>
    """

    html = momentum_css + get_header(session["user"]) + f"""
        <div style="position: fixed; top: 60px; left: 0; right: 0; bottom: 60px; background: white; display: flex; flex-direction: column;">
            <!-- CHAT HEADER -->
            <div style="display: flex; align-items: center; gap: 12px; padding: 15px; border-bottom: 1px solid #eee; background: white;">
                <img src='/static/photos/{receiver["photo"]}' 
                     style='width:45px; height:45px; border-radius:50%; object-fit:cover;'>
                <div>
                    <b style='font-size: 16px;'>{receiver["username"]}</b><br>
                    <span style='color:gray; font-size:12px;'>Active now</span>
                </div>
            </div>

            <!-- CHAT MESSAGES -->
            <div id='chatbox'
                 style='flex: 1; padding: 15px; overflow-y: auto; background: #f8f8f8;'>
                {msgs_html if msgs_html else '<div style="text-align: center; color: #666; padding: 40px;">No messages yet. Start the conversation!</div>'}
            </div>

            <!-- REPLY INDICATOR (hidden by default) -->
            <div id="replyIndicator" style="display: none; padding: 10px 15px; background: #f0f0f0; border-bottom: 1px solid #ddd;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <small style="color: #666;">Replying to:</small>
                        <div id="replyText" style="font-size: 14px;"></div>
                    </div>
                    <button onclick="cancelReply()" style="background: none; border: none; color: #666; cursor: pointer;">✕</button>
                </div>
            </div>

            <!-- SEND FORM -->
            <form method='POST' id="messageForm" enctype="multipart/form-data" class="message-input-container">
                <input type="hidden" id="replyTo" name="reply_to" value="">
                <input type="hidden" id="locationData" name="location_data" value="">
                
                <button type="button" class="attachment-btn" onclick="showAttachmentMenu()">
                    {SVG_ICONS['attachment']}
                </button>
                
                <input name='message' id="messageInput" style='flex: 1; padding: 12px 16px; border: 1px solid #ddd; border-radius: 24px; font-size: 16px;' 
                       placeholder='Type a message...' autocomplete='off'>
                
                <input type="file" id="mediaInput" name="media" accept="image/*,video/*" style="display: none;" onchange="document.getElementById('messageForm').submit()">
                
                <button type="submit" class='btn' style='border-radius: 24px; padding: 12px 20px;'>Send</button>
            </form>
        </div>

        <!-- TOUCH HOLD MENU -->
        <div id="touchHoldMenu" class="touch-hold-menu">
            <button class="touch-hold-option" onclick="replyToMessage()">{SVG_ICONS['reply']} Reply</button>
            <button class="touch-hold-option" onclick="showEmojiPicker()">{SVG_ICONS['like']} React</button>
            <button class="touch-hold-option" id="editBtn" style="display:none;" onclick="editMessage()">{SVG_ICONS['edit']} Edit</button>
            <button class="touch-hold-option" id="deleteBtn" style="display:none;" onclick="deleteMessage()">{SVG_ICONS['delete']} Delete</button>
        </div>

        <!-- ATTACHMENT MENU -->
        <div id="attachmentMenu" class="attachment-menu">
            <button class="attachment-option" onclick="document.getElementById('mediaInput').click()">
                {SVG_ICONS['camera']} Photo/Video
            </button>
            <button class="attachment-option" onclick="shareLocation()">
                {SVG_ICONS['location']} Share Location
            </button>
        </div>

        <!-- EMOJI PICKER -->
        <div id="emojiPicker" class="emoji-picker">
            <button class="emoji-btn" onclick="addReaction('👍')">👍</button>
            <button class="emoji-btn" onclick="addReaction('❤️')">❤️</button>
            <button class="emoji-btn" onclick="addReaction('😂')">😂</button>
            <button class="emoji-btn" onclick="addReaction('😮')">😮</button>
            <button class="emoji-btn" onclick="addReaction('😢')">😢</button>
            <button class="emoji-btn" onclick="addReaction('😡')">😡</button>
            <button class="emoji-btn" onclick="addReaction('👏')">👏</button>
            <button class="emoji-btn" onclick="addReaction('🔥')">🔥</button>
        </div>

        {js_script}
        """ + get_bottom_nav(session["user"])

    return render_template_string(html)

# ================= MESSAGE REACTION =====================
@app.route("/react/<message_id>/<emoji>")
def react_to_message(message_id, emoji):
    if "user" not in session:
        return redirect("/")
    
    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    
    # Get the message to find the chat partner
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM messages WHERE id=?", (message_id,))
    message = c.fetchone()
    conn.close()
    
    if message:
        # Check if user already reacted with this emoji
        reactions = get_message_reactions(message_id)
        if str(uid) in reactions and reactions[str(uid)] == emoji:
            # Remove reaction if same emoji
            remove_reaction_from_message(message_id, uid)
        else:
            # Add or change reaction
            add_reaction_to_message(message_id, uid, emoji)
        
        # Redirect back to chat
        chat_partner = fetch_user_by_id(message["sender_id"] if message["sender_id"] != uid else message["receiver_id"])
        return redirect(f"/chat/{chat_partner['username']}")
    
    return redirect("/direct")

# ================= EDIT MESSAGE =====================
@app.route("/edit_message/<message_id>", methods=["POST"])
def edit_message(message_id):
    if "user" not in session:
        return redirect("/")
    
    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    new_message = request.form.get("message", "").strip()
    
    if new_message:
        conn = get_db_conn()
        c = conn.cursor()
        
        # Verify user owns the message and update it
        c.execute("UPDATE messages SET message=? WHERE id=? AND sender_id=?", 
                 (new_message, message_id, uid))
        conn.commit()
        
        # Get chat partner for redirect
        c.execute("SELECT * FROM messages WHERE id=?", (message_id,))
        message = c.fetchone()
        conn.close()
        
        if message:
            chat_partner = fetch_user_by_id(message["receiver_id"] if message["sender_id"] == uid else message["sender_id"])
            return redirect(f"/chat/{chat_partner['username']}")
    
    return redirect("/direct")

# ================= DELETE MESSAGE =====================
@app.route("/delete_message/<message_id>")
def delete_message(message_id):
    if "user" not in session:
        return redirect("/")
    
    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    
    conn = get_db_conn()
    c = conn.cursor()
    
    # Get message before deleting to find chat partner
    c.execute("SELECT * FROM messages WHERE id=?", (message_id,))
    message = c.fetchone()
    
    if message and message["sender_id"] == uid:
        # Delete the message
        c.execute("DELETE FROM messages WHERE id=?", (message_id,))
        conn.commit()
    
    conn.close()
    
    if message:
        chat_partner = fetch_user_by_id(message["receiver_id"])
        return redirect(f"/chat/{chat_partner['username']}")
    
    return redirect("/direct")

# ================= NOTIFICATIONS PAGE =====================
@app.route("/notifications")
def notifications():
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    
    # Mark notifications as read when opening the page
    mark_notifications_as_read(uid)

    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT n.*, u.username, u.photo AS user_photo
        FROM notifications n
        JOIN users u ON n.source_user_id = u.id
        WHERE n.user_id = ?
        ORDER BY datetime(n.timestamp) DESC
        LIMIT 50
    """, (uid,))
    notifications = c.fetchall()
    conn.close()

    notifications_html = ""
    for notif in notifications:
        user_photo = notif["user_photo"]
        username = notif["username"]
        message = notif["message"]
        timestamp = format_time(notif["timestamp"])
        
        # Determine icon based on notification type
        icon = SVG_ICONS['heart'] if notif["type"] == "like" else SVG_ICONS['comment'] if notif["type"] == "comment" else SVG_ICONS['profile'] if notif["type"] == "follow" else SVG_ICONS['message']
        
        notifications_html += f"""
        <div class="notification-item {'unread' if not notif['is_read'] else ''}">
            <img src='/static/photos/{user_photo}' style='width:40px; height:40px; border-radius:50%; object-fit:cover;'>
            <div style="flex: 1;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    {icon}
                    <div>
                        <b>{username}</b> {message}
                    </div>
                </div>
                <span style='color:gray; font-size:12px;'>{timestamp}</span>
            </div>
        </div>
        """

    html = momentum_css + get_header(session["user"]) + f"""
        <div class='app-container'>
            <h2 style='margin-bottom: 20px;'>Notifications</h2>
            <div style='margin-top:20px; background: white; border-radius: 12px; overflow: hidden;'>
                {notifications_html if notifications_html else "<p style='text-align: center; padding: 40px; color: #666;'>No notifications yet.</p>"}
            </div>
        </div>
        """ + get_bottom_nav(session["user"])

    return render_template_string(html)

# ================= LOGIN ALERTS PAGE =====================
@app.route("/login_alerts")
def login_alerts():
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    
    # Mark login alerts as read when opening the page
    mark_login_alerts_as_read(uid)

    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM login_alerts
        WHERE user_id = ?
        ORDER BY datetime(timestamp) DESC
        LIMIT 50
    """, (uid,))
    alerts = c.fetchall()
    conn.close()

    alerts_html = ""
    for alert in alerts:
        device_name = alert["device_name"]
        ip_address = alert["ip_address"]
        location = alert["location"]
        timestamp = format_time(alert["timestamp"])
        
        alerts_html += f"""
        <div class="login-alert-item {'unread' if not alert['is_read'] else ''}">
            <div class="login-alert-header">
                <b>New Login - {device_name}</b>
                <span style='color:gray; font-size:12px;'>{timestamp}</span>
            </div>
            <div class="login-alert-details">
                <div>IP Address: {ip_address}</div>
                <div>Location: {location}</div>
                <div>Device: {device_name}</div>
            </div>
        </div>
        """

    html = momentum_css + get_header(session["user"]) + f"""
        <div class='app-container'>
            <h2 style='margin-bottom: 20px;'>Login Alerts</h2>
            <p style='color: #666; margin-bottom: 20px;'>Recent login activity on your account</p>
            <div style='margin-top:20px; background: white; border-radius: 12px; overflow: hidden;'>
                {alerts_html if alerts_html else "<p style='text-align: center; padding: 40px; color: #666;'>No login alerts yet.</p>"}
            </div>
        </div>
        """ + get_bottom_nav(session["user"])

    return render_template_string(html)

# ================= SETTINGS PAGE =====================
@app.route("/settings")
def settings():
    if "user" not in session:
        return redirect("/")

    uid = session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"]
    
    # Get unread login alerts count for badge
    unread_login_alerts_count = get_unread_login_alerts_count(uid)
    login_alerts_badge = f"<span class='badge'>{unread_login_alerts_count}</span>" if unread_login_alerts_count > 0 else ""

    html = momentum_css + get_header(session["user"]) + f"""
        <div class='app-container'>
            <h2 style='text-align: center; margin-bottom: 30px;'>Settings</h2>

            <div style="background: white; border-radius: 12px; overflow: hidden; margin-bottom: 20px;">
                <a href='/edit_profile' class='settings-option'>
                    <div class="settings-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                            <path d="M12 12C14.21 12 16 10.21 16 8C16 5.79 14.21 4 12 4C9.79 4 8 5.79 8 8C8 10.21 9.79 12 12 12ZM12 14C9.33 14 4 15.34 4 18V20H20V18C20 15.34 14.67 14 12 14Z" fill="currentColor"/>
                        </svg>
                    </div>
                    <div>
                        <div style="font-weight: 600;">Edit Profile</div>
                        <div style="font-size: 12px; color: #666;">Change your profile information</div>
                    </div>
                </a>
                
                <a href='/change_password' class='settings-option'>
                    <div class="settings-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                            <path d="M18 8H17V6C17 3.24 14.76 1 12 1C9.24 1 7 3.24 7 6V8H6C4.9 8 4 8.9 4 10V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V10C20 8.9 19.1 8 18 8ZM12 17C10.9 17 10 16.1 10 15C10 13.9 10.9 13 12 13C13.1 13 14 13.9 14 15C14 16.1 13.1 17 12 17ZM15.1 8H8.9V6C8.9 4.29 10.29 2.9 12 2.9C13.71 2.9 15.1 4.29 15.1 6V8Z" fill="currentColor"/>
                        </svg>
                    </div>
                    <div>
                        <div style="font-weight: 600;">Change Password</div>
                        <div style="font-size: 12px; color: #666;">Update your password</div>
                    </div>
                </a>
            </div>

            <div style="background: white; border-radius: 12px; overflow: hidden; margin-bottom: 20px;">
                <a href='/notifications' class='settings-option'>
                    <div class="settings-icon">""" + SVG_ICONS['notification'] + """</div>
                    <div>
                        <div style="font-weight: 600;">Notifications</div>
                        <div style="font-size: 12px; color: #666;">Manage your notifications</div>
                    </div>
                </a>
                
                <a href='/login_alerts' class='settings-option' style="position: relative;">
                    <div class="settings-icon">""" + SVG_ICONS['security'] + """</div>
                    <div>
                        <div style="font-weight: 600;">Login Alerts</div>
                        <div style="font-size: 12px; color: #666;">Recent login activity</div>
                    </div>
                    {login_alerts_badge}
                </a>
                
                <a href='/privacy' class='settings-option'>
                    <div class="settings-icon">""" + SVG_ICONS['privacy'] + """</div>
                    <div>
                        <div style="font-weight: 600;">Privacy</div>
                        <div style="font-size: 12px; color: #666;">Control your privacy settings</div>
                    </div>
                </a>
            </div>

            <div style="background: white; border-radius: 12px; overflow: hidden; margin-bottom: 20px;">
                <a href='/help' class='settings-option'>
                    <div class="settings-icon">""" + SVG_ICONS['help'] + """</div>
                    <div>
                        <div style="font-weight: 600;">Help & Support</div>
                        <div style="font-size: 12px; color: #666;">Get help with Momentum</div>
                    </div>
                </a>
                
                <a href='/about' class='settings-option'>
                    <div class="settings-icon">""" + SVG_ICONS['about'] + """</div>
                    <div>
                        <div style="font-weight: 600;">About</div>
                        <div style="font-size: 12px; color: #666;">About Momentum app</div>
                    </div>
                </a>
            </div>

            <a href='/logout' class='btn-outline' style='display:block; margin-top:15px; color:red; border-color:red; width:100%; text-align:center; padding: 15px;'>Logout</a>
        </div>
        """ + get_bottom_nav(session["user"])

    return render_template_string(html)

# ================= EDIT PROFILE PAGE =====================
@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user" not in session:
        return redirect("/")

    user = fetch_user_by_id(session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"])

    if request.method == "POST":
        fullname = request.form.get("fullname", user["fullname"])
        email = request.form.get("email", user["email"])
        age = request.form.get("age", user["age"])

        photo_file = request.files.get("photo", None)
        filename = user["photo"]
        if photo_file and photo_file.filename:
            filename = secure_filename(photo_file.filename)
            photo_file.save(os.path.join("static/photos", filename))

        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE users 
            SET fullname=?, email=?, age=?, photo=?
            WHERE id=?
        """, (fullname, email, age, filename, user["id"]))
        conn.commit()
        conn.close()

        refresh_session_user()
        return redirect(f"/profile/{user['username']}")

    html = momentum_css + get_header(session["user"]) + f"""
        <div class='app-container'>
            <h2 style='text-align: center; margin-bottom: 30px;'>Edit Profile</h2>
            <form method='POST' enctype='multipart/form-data'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Full Name</label>
                <input class='form-input' name='fullname' value='{user["fullname"]}'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Email</label>
                <input class='form-input' name='email' value='{user["email"]}'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Age</label>
                <input class='form-input' name='age' value='{user["age"]}'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Profile Photo</label>
                <input class='file-input' type='file' name='photo' accept='image/*'>
                <button class='btn' style='width:100%; margin-top: 20px;'>Save Changes</button>
            </form>
        </div>
        """ + get_bottom_nav(session["user"])
    return render_template_string(html)

# ================= CHANGE PASSWORD =====================
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user" not in session:
        return redirect("/")

    user = fetch_user_by_id(session["user"][0] if isinstance(session["user"], tuple) else session["user"]["id"])

    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")

        if old != user["password"]:
            return "Old password incorrect!"

        conn = get_db_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET password=? WHERE id=?", (new, user["id"]))
        conn.commit()
        conn.close()

        refresh_session_user()
        return redirect("/settings")

    html = momentum_css + get_header(session["user"]) + """
        <div class='app-container'>
            <h2 style='text-align: center; margin-bottom: 30px;'>Change Password</h2>
            <form method='POST'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>Old Password</label>
                <input class='form-input' type='password' name='old_password'>
                <label style='font-weight: bold; display: block; margin-bottom: 8px;'>New Password</label>
                <input class='form-input' type='password' name='new_password'>
                <button class='btn' style='width:100%; margin-top: 20px;'>Change Password</button>
            </form>
        </div>
        """ + get_bottom_nav(session["user"])
    return render_template_string(html)

# ========== ROOT REDIRECT ==========
@app.route("/home")
def goto_home():
    return redirect("/feed")

# ========== FLASK RUNNER ==========
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
