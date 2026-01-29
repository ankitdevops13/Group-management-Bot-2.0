import asyncio
import re
import glob  # For backup system
import sqlite3
import csv
import os
import sys  # Added missing import
import psutil  # Added missing import
import time
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from pyrogram.enums import ChatAction, ChatMemberStatus

from pyrogram.errors import (
    ChatWriteForbidden,
    UserNotParticipant,
    FloodWait,
    PeerIdInvalid,
    MessageNotModified,
    MessageDeleteForbidden
)
from pyrogram import utils
import time
from config import API_ID, API_HASH, BOT_TOKEN
from pyrogram.enums import ChatMembersFilter
import shutil  # For backup system
# Add ChatPrivileges conditionally
try:
    from pyrogram.enums import ChatPrivileges
    CHAT_PRIVILEGES_AVAILABLE = True
except ImportError:
    # For older Pyrogram versions
    from pyrogram.types import ChatPrivileges
    CHAT_PRIVILEGES_AVAILABLE = True
    print("⚠️ Using ChatPrivileges from pyrogram.types (older version)")

import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)




def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

# ================= CONFIG =================

SUPER_ADMIN = 6748792256  # Main super admin
BOT_BRAND = "Ankit Shakya Support"
BOT_TAGLINE = "Fast • Secure • Reliable"
DB_FILE = "support.db"

# ================== GLOBAL TAG STOP ==================
STOP_TAG = set()
TAG_LIMIT = 5          # per message
DELAY = 2              # seconds
COOLDOWN = 120         # seconds

PURGE_REPORT_DELETE_AFTER = 15  # seconds
ADMIN_ABUSE_ENABLED = True

# Multiple bot admins - ADD ALL YOUR ADMIN IDs HERE
INITIAL_ADMINS = [
    6748792256,  # Super admin (you)
    6172401778,   # Admin 2
    8235194860,   # Admin 3
]

# ================= BOT =================
app = Client(
    "support-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ======================================================
# ============== MERGED DATABASE SETUP =================
# (main.py + fresh.py)
# ======================================================

import sqlite3

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# ======================================================
# ================= ADMINS =============================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS admins (
    admin_id INTEGER PRIMARY KEY
)
""")

cur.execute(
    "INSERT OR IGNORE INTO admins (admin_id) VALUES (?)",
    (SUPER_ADMIN,)
)

# ======================================================
# ================= BLOCKED USERS ======================
# (PM + global block)
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS blocked_users (
    user_id INTEGER PRIMARY KEY,
    blocked_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================================================
# ================= USER SUPPORT SYSTEM ================
# ======================================================

# Admin reply routing
cur.execute("""
CREATE TABLE IF NOT EXISTS admin_reply_target (
    admin_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    set_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# User ↔ Admin chat history
cur.execute("""
CREATE TABLE IF NOT EXISTS contact_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    sender TEXT CHECK(sender IN ('user','admin')),
    message_type TEXT,
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# First message auto-reply
cur.execute("""
CREATE TABLE IF NOT EXISTS auto_reply_sent (
    user_id INTEGER PRIMARY KEY,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# PM abuse warnings
cur.execute("""
CREATE TABLE IF NOT EXISTS pm_abuse_warns (
    user_id INTEGER PRIMARY KEY,
    warns INTEGER DEFAULT 0,
    last_warn DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================================================
# ================= GROUP ABUSE SYSTEM =================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS abuse_warns (
    chat_id INTEGER,
    user_id INTEGER,
    warns INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)
""")

# ======================================================
# ================= USER WARNINGS ======================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS user_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    user_id INTEGER,
    reason TEXT,
    warned_by INTEGER,
    warned_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================================================
# ================= MUTE SCHEDULER =====================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS mutes (
    chat_id INTEGER,
    user_id INTEGER,
    unmute_at INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")

# ======================================================
# ================= GROUP RULES ========================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS group_rules (
    chat_id INTEGER PRIMARY KEY,
    rules TEXT
)
""")

# ======================================================
# ================= WELCOME MESSAGES ===================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS welcome_messages (
    chat_id INTEGER PRIMARY KEY,
    message TEXT
)
""")

# ======================================================
# ================= USER REPORT SYSTEM =================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS user_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    reporter_id INTEGER,
    reported_user_id INTEGER,
    reason TEXT,
    status TEXT DEFAULT 'pending',
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_by INTEGER,
    resolved_at DATETIME
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS report_cooldown (
    user_id INTEGER,
    chat_id INTEGER,
    last_report_time DATETIME,
    PRIMARY KEY (user_id, chat_id)
)
""")
# ======================================================
# ================= ADMIN REPORT SYSTEM =================
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS notify_state (
    chat_id INTEGER PRIMARY KEY,
    last_index INTEGER DEFAULT 0
)
""")
# ======================================================
# ================= TAG / PING SYSTEM ==================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS tag_cooldown (
    chat_id INTEGER,
    user_id INTEGER,
    last_time INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS tag_cancel (
    chat_id INTEGER,
    admin_id INTEGER,
    cancelled INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, admin_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS admin_ping_cooldown (
    chat_id INTEGER,
    user_id INTEGER,
    last_ping INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")

# ======================================================
# ================= REMINDERS ==========================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    reminder_text TEXT,
    remind_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================================================
# ================= MASS DELETE CONFIRM ================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS mass_delete_pending (
    chat_id INTEGER,
    admin_id INTEGER,
    message_id INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, admin_id)
)
""")

# ======================================================
# ================= COOLDOWNS ==========================
# ======================================================

cur.execute("""
CREATE TABLE IF NOT EXISTS cooldown (
    user_id INTEGER PRIMARY KEY,
    last_used INTEGER
)
""")

# ======================================================
# ================= INDEXES =============================
# ======================================================

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_admins
ON admins(admin_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_history_user
ON contact_history(user_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_reports
ON user_reports(chat_id, status)
""")

# ======================================================
# ================= INITIAL ADMINS =====================
# ======================================================

for admin_id in INITIAL_ADMINS:
    cur.execute(
        "INSERT OR IGNORE INTO admins (admin_id) VALUES (?)",
        (admin_id,)
    )

conn.commit()

# ================= INITIALIZE WITH SAMPLE DATA =================
def init_broadcast_tables():
    """Initialize broadcast tables with sample data"""
    
    print("🔄 Setting up broadcast system...")
    
    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_active DATETIME DEFAULT CURRENT_TIMESTAMP,
            joined_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Groups table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            username TEXT,
            added_by INTEGER,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Broadcast history table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            target TEXT,
            message_type TEXT,
            caption TEXT,
            file_id TEXT,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    # Add bot admins automatically
    try:
        print("👥 Adding bot admins to users table...")
        
        # Add SUPER_ADMIN
        cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", 
                   (SUPER_ADMIN, "Super Admin"))
        
        # Add other admins
        for admin_id in INITIAL_ADMINS:
            cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", 
                       (admin_id, f"Admin {admin_id}"))
        
        conn.commit()
        
    except Exception as e:
        print(f"⚠️ Could not add admins: {e}")
    
    # Count records
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]
    
    print(f"✅ Broadcast system ready!")
    print(f"📊 Current data: {user_count} users, {group_count} groups")
    

# ================= INITIALIZE ADMINS FROM CONFIG =================
def initialize_admins():
    """Add initial admins from config to database"""
    print("📋 Initializing bot admins...")
    
    # Add SUPER_ADMIN first
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (SUPER_ADMIN,))
    
    # Add all initial admins from config
    for admin_id in INITIAL_ADMINS:
        cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
        print(f"  ✅ Added admin: {admin_id}")
    
    conn.commit()
    print(f"✅ Total {len(INITIAL_ADMINS)} admins initialized")

# Call this function to initialize
initialize_admins()

# ================= DATA STORES =================
user_warnings_cache = {}  # {chat_id: {user_id: [reasons]}}
user_mutes = {}  # {chat_id: {user_id: unmute_time}}
approved_users = {}  # {chat_id: [user_ids]}
abuse_tracker = {}
# ================= BEAUTIFUL UI COMPONENTS =================
# Add to your beautiful_header function for new headers
def beautiful_header(title: str) -> str:
    """Create beautiful header for messages"""
    headers = {
        "welcome": "╔═══════════════════╗\n        🌟 WELCOME 🌟\n╚═══════════════════╝",
        "moderation": "╔═══════════════════╗\n      🔧 MODERATION 🔧\n╚═══════════════════╝",
        "info": "╔═══════════════════╗\n       ℹ️ INFORMATION ℹ️\n╚═══════════════════╝",
        "admin": "╔═══════════════════╗\n      ⚡ ADMIN PANEL ⚡\n╚═══════════════════╝",
        "support": "╔═══════════════════╗\n     💬 SUPPORT SYSTEM 💬\n╚═══════════════════╝",
        "settings": "╔═══════════════════╗\n      ⚙️ SETTINGS ⚙️\n╚═══════════════════╝",
        "danger": "╔═══════════════════╗\n      ☢️ DANGER ☢️\n╚═══════════════════╝",
        "warning": "╔═══════════════════╗\n      ⚠️ WARNING ⚠️\n╚═══════════════════╝",
        "tools": "╔═══════════════════╗\n      🛠️ TOOLS 🛠️\n╚═══════════════════╝",
        "security": "╔═══════════════════╗\n      🛡️ SECURITY 🛡️\n╚═══════════════════╝",
        "guide": "╔═══════════════════╗\n      📚 GUIDE 📚\n╚═══════════════════╝",
        "loading": "╔═══════════════════╗\n      ⏳ LOADING ⏳\n╚═══════════════════╝",
        "sparkles": "╔═══════════════════╗\n      ✨ SPARKLES ✨\n╚═══════════════════╝",
        "stats": "╔═══════════════════╗\n      📊 STATISTICS 📊\n╚═══════════════════╝",
        "group": "╔═══════════════════╗\n      👥 GROUP 👥\n╚═══════════════════╝"
    }
    return headers.get(title, f"╔═══════════════════╗\n        {title}\n╚═══════════════════╝")


def beautiful_footer() -> str:
    """Add beautiful footer to messages"""
    footer_line = "─────────────────────"
    return f"\n{footer_line}\n✨ {BOT_BRAND} | {BOT_TAGLINE}\n{footer_line}"

def format_user_mention(user) -> str:
    """Format user mention beautifully"""
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
        return f"👤 **{name}**"
    return f"👤 User ID: `{user.id}`"

def progress_bar(percentage: int, length: int = 10) -> str:
    """Create a visual progress bar"""
    percentage = max(0, min(100, percentage))  # Ensure percentage is between 0-100
    filled = int(percentage * length / 100)
    filled = min(length, filled)  # Ensure not exceeding length
    empty = length - filled
    return f"[{'█' * filled}{'░' * empty}] {percentage}%"

def create_button_grid(buttons, columns=2):
    """Create beautiful button grid"""
    grid = []
    row = []
    for i, (text, callback) in enumerate(buttons):
        row.append(InlineKeyboardButton(text, callback_data=callback))
        if (i + 1) % columns == 0:
            grid.append(row)
            row = []
    if row:
        grid.append(row)
    return InlineKeyboardMarkup(grid)


def get_uptime() -> str:
    """Get bot uptime as formatted string"""
    try:
        # Create a simple uptime counter
        global START_TIME
        if 'START_TIME' not in globals():
            START_TIME = time.time()
        
        uptime_seconds = time.time() - START_TIME
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        return uptime_str
    except:
        return "Unknown"
      
# ================= FIXED ABUSE WARNING FUNCTION =================
def add_pm_abuse_warn(user_id: int) -> int:
    """
    PM abuse warning add karta hai
    Returns: total warns count
    """

    # create row if not exists
    cur.execute(
        "INSERT OR IGNORE INTO pm_abuse_warns (user_id, warns) VALUES (?, 0)",
        (user_id,)
    )

    # increment warning
    cur.execute(
        """
        UPDATE pm_abuse_warns
        SET warns = warns + 1,
            last_warn = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (user_id,)
    )

    conn.commit()

    # fetch updated count
    cur.execute(
        "SELECT warns FROM pm_abuse_warns WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()
    return row[0] if row else 0


def auto_block_if_needed(user_id: int, limit: int = 2) -> bool:
    """
    Returns True if user got blocked
    """
    warns = add_pm_abuse_warn(user_id)

    if warns >= limit:
        cur.execute(
            "INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        return True

    return False


def contains_abuse(text):
    text = re.sub(r"[^a-zA-Z ]", "", text.lower())
    return any(w in text for w in ABUSE_WORDS)


def save_auto_reply(user_id):
    cur.execute(
        "INSERT OR IGNORE INTO auto_reply_sent (user_id) VALUES (?)",
        (user_id,)
    )
    conn.commit()
    
# ================= ADMIN TYPE CHECKING =================
async def check_admin_type(client, chat_id, user_id):
    """
    Check admin type of user
    Returns: (is_bot_admin, is_group_admin, admin_type)
    admin_type: "super", "bot", "group", "none"
    """
    is_bot_admin = is_admin(user_id)
    is_group_admin = False
    admin_type = "none"
    
    # Check if user is group admin
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            is_group_admin = True
    except:
        pass
    
    # Determine admin type
    if user_id == SUPER_ADMIN:
        admin_type = "super"
    elif is_bot_admin:
        admin_type = "bot"
    elif is_group_admin:
        admin_type = "group"
    else:
        admin_type = "none"
    
    return is_bot_admin, is_group_admin, admin_type

async def get_admin_status_text(client, chat_id, user_id):
    """Get formatted admin status text"""
    is_bot_admin, is_group_admin, admin_type = await check_admin_type(client, chat_id, user_id)
    
    status_parts = []
    if admin_type == "super":
        status_parts.append("👑 **Super Admin** (Bot + Full Access)")
    elif admin_type == "bot":
        status_parts.append("⚡ **Bot Admin** (Bot Commands)")
    if is_group_admin:
        status_parts.append("🔧 **Group Admin** (Group Permissions)")
    
    if not status_parts:
        return "👤 **Regular User** (No admin rights)"
    
    return " + ".join(status_parts)



# Abude words auto detect helper function 

def get_warn(chat_id, user_id):
    cur.execute(
        "SELECT warns FROM abuse_warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    row = cur.fetchone()
    return row[0] if row else 0


def add_warn(chat_id, user_id):
    cur.execute(
        "INSERT OR IGNORE INTO abuse_warns (chat_id, user_id, warns) VALUES (?, ?, 0)",
        (chat_id, user_id)
    )
    cur.execute(
        "UPDATE abuse_warns SET warns = warns + 1 WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    return get_warn(chat_id, user_id)


def reset_warn(chat_id, user_id):
    cur.execute(
        "DELETE FROM abuse_warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()


def save_mute(chat_id, user_id, duration):
    unmute_at = int(time.time()) + duration
    cur.execute(
        "INSERT OR REPLACE INTO mutes (chat_id, user_id, unmute_at) VALUES (?, ?, ?)",
        (chat_id, user_id, unmute_at)
    )
    conn.commit()


def remove_mute(chat_id, user_id):
    cur.execute(
        "DELETE FROM mutes WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()

def contains_abuse(text):
    if not text:
        return False

    text = text.lower()
    words = re.findall(r"\b\w+\b", text)

    for w in ABUSE_WORDS:
        if w.lower() in words:
            return True
    return False

# ================= FIXED HELPER FUNCTIONS =================
def is_admin(uid):
    cur.execute("SELECT 1 FROM admins WHERE admin_id=?", (uid,))
    return cur.fetchone() is not None
    
def is_bot_admin(user_id):
    cur.execute("SELECT 1 FROM admins WHERE admin_id=?", (user_id,))
    return cur.fetchone() is not None

def is_super_admin(uid):
    """Check if user is super admin"""
    return uid == SUPER_ADMIN

def is_blocked_user(user_id: int) -> bool:
    cur.execute(
        "SELECT 1 FROM blocked_users WHERE user_id=?",
        (user_id,)
    )
    return cur.fetchone() is not None

def abuse_warning(user_id: int) -> int:
    """
    PM abuse warning system
    Returns total warning count for the user
    """

    # row create if not exists
    cur.execute(
        "INSERT OR IGNORE INTO pm_abuse_warns (user_id, warns) VALUES (?, 0)",
        (user_id,)
    )

    # increment warn count
    cur.execute(
        """
        UPDATE pm_abuse_warns
        SET warns = warns + 1,
            last_warn = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (user_id,)
    )

    conn.commit()

    # fetch updated count
    cur.execute(
        "SELECT warns FROM pm_abuse_warns WHERE user_id=?",
        (user_id,)
    )
    row = cur.fetchone()

    return row[0] if row else 0


def reset_abuse_warn(user_id: int):
    cur.execute(
        "DELETE FROM pm_abuse_warns WHERE user_id=?",
        (user_id,)
    )
    conn.commit()

def is_blocked(uid):
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (uid,))
    return cur.fetchone() is not None



async def is_group_admin(client, chat_id, user_id):
    """Check if user is group admin"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False


async def can_user_restrict(client, chat_id, user_id):
    """Check if user can restrict members - Fixed version"""
    try:
        # Check if chat_id is actually a user ID (starts with check)
        if isinstance(chat_id, (int, str)) and str(chat_id).isdigit():
            chat_id_int = int(chat_id)
            # User IDs are typically < group IDs, but better to check properly
            # Skip check for user IDs to avoid "belongs to a user" error
            if chat_id_int == user_id or chat_id_int < 0:
                # This is a group/supergroup/channel (negative IDs)
                pass
            else:
                # Might be a user ID, skip restrict check
                return False
        
        member = await client.get_chat_member(chat_id, user_id)
        
        # Owner can always restrict
        if member.status == ChatMemberStatus.OWNER:
            return True
        
        # For administrators, check privileges
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            # Pyrogram v2+ way to check permissions
            if hasattr(member, 'privileges'):
                return member.privileges.can_restrict_members
            # Alternative check for older versions
            elif hasattr(member, 'can_restrict_members'):
                return member.can_restrict_members
        
        return False
    except Exception as e:
        print(f"Restrict check error for chat {chat_id}, user {user_id}: {e}")
        return False

async def can_bot_restrict(client, chat_id):
    """Check if bot can restrict in this chat"""
    return await can_user_restrict(client, chat_id, "me")


async def extract_user(client, message):
    """Extract user from command or reply"""
    user_id = None
    user_obj = None
    
    if message.reply_to_message:
        user_obj = message.reply_to_message.from_user
        user_id = user_obj.id
    
    elif len(message.command) > 1:
        user = message.command[1]
        
        if user.startswith("@"):
            user = user[1:]
        
        try:
            user_obj = await client.get_users(user)
            user_id = user_obj.id
        except:
            try:
                user_id = int(user)
                user_obj = await client.get_users(user_id)
            except:
                return None, None
    
    return user_id, user_obj


# ================= INLINE BUTTONS =================
def moderation_buttons():
    return create_button_grid([
        ("🔇 Mute", "mute_menu"),
        ("🔊 Unmute", "unmute_menu"),
        ("🚫 Ban", "ban_menu"),
        ("✅ Unban", "unban_menu"),
        ("👢 Kick", "kick_menu"),
        ("⚠️ Warn", "warn_menu"),
        ("⚡ Promote", "promote_menu"),
        ("📉 Demote", "demote_menu"),
        ("📜 Rules", "rules_menu"),
        ("👋 Welcome", "welcome_menu"),
        ("📊 Info", "info_menu"),
        ("🧹 Purge", "purge_menu")
    ], columns=3)


# ================= peer id check=================

@app.on_message(filters.private & filters.command("testpeer"))
async def test_peer_id(client, message):
    """Test peer ID access"""
    
    if not is_bot_admin(message.from_user.id):
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: /testpeer -100123456789")
        return
    
    chat_id_str = message.command[1]
    
    try:
        chat_id = int(chat_id_str)
        
        info = f"""
🔍 **PEER ID TEST**

**Input:** `{chat_id_str}`
**As int:** `{chat_id}`
**Type:** {'Negative' if chat_id < 0 else 'Positive'}
**Starts with -100:** {'✅ Yes' if str(chat_id).startswith('-100') else '❌ No'}
"""
        
        # Try different access methods
        try:
            chat = await client.get_chat(chat_id)
            info += f"\n✅ **get_chat SUCCESS**"
            info += f"\n  • Title: {chat.title}"
            info += f"\n  • Type: {chat.type}"
        except Exception as e1:
            info += f"\n❌ **get_chat FAILED**: {type(e1).__name__}"
        
        # Try get_chat_member
        try:
            member = await client.get_chat_member(chat_id, "me")
            info += f"\n✅ **get_chat_member SUCCESS**"
            info += f"\n  • Status: {member.status}"
        except Exception as e2:
            info += f"\n❌ **get_chat_member FAILED**: {type(e2).__name__}"
        
        await message.reply_text(info)
        
    except ValueError:
        await message.reply_text(f"❌ Invalid number: `{chat_id_str}`")


# ================= HELPER FUNCTIONS =================
async def get_user_status_icon(client, user_id: int) -> str:
    """Get user status with icon"""
    try:
        user = await client.get_users(user_id)
        if hasattr(user, 'status'):
            if user.status.value == "online":
                return "🟢 Online"
            elif user.status.value == "offline":
                return "⚫ Offline"
            elif user.status.value == "recently":
                return "🟡 Recently"
            elif user.status.value == "within_week":
                return "🟡 This week"
            elif user.status.value == "within_month":
                return "🟡 This month"
        return "⚪ Unknown"
    except:
        return "⚪ Unknown"

async def get_admin_level_text(user_id: int, is_bot_admin: bool, is_super_admin: bool) -> str:
    """Get formatted admin level text"""
    if is_super_admin:
        return "👑 **Super Admin** (Full Access)"
    elif is_bot_admin:
        return "⚡ **Bot Admin** (Special Privileges)"
    else:
        return "👤 **Regular User**"

def parse_duration(duration_str: str):
    """Parse duration string like 1h, 30m, 2d, 1w into timedelta"""
    try:
        duration_str = duration_str.lower().strip()
        
        if duration_str.endswith("m"):
            minutes = int(duration_str[:-1])
            return timedelta(minutes=minutes)
        elif duration_str.endswith("h"):
            hours = int(duration_str[:-1])
            return timedelta(hours=hours)
        elif duration_str.endswith("d"):
            days = int(duration_str[:-1])
            return timedelta(days=days)
        elif duration_str.endswith("w"):
            weeks = int(duration_str[:-1])
            return timedelta(weeks=weeks)
        elif duration_str.isdigit():
            return timedelta(minutes=int(duration_str))
        else:
            return None
    except (ValueError, AttributeError):
        return None


ABUSE_WORDS = [
    # English abuse words
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "dick", "pussy",
    "whore", "slut", "motherfucker", "damn", "crap", "bullshit",
    "nigger", "nigga", "faggot", "retard", "idiot", "moron", "stupid",
    "fool", "dumb", "stupid", "dickhead", "arsehole", "cock", "wanker",
    "twat", "slag", "skank", "hoe", "slutty", "bitchy", "fucking",
    
    # Hindi abuse words (common)
    "madarchod", "behenchod", "chutiya", "gandu", "bhosdike", "lund", "randi",
    "harami", "kamina", "kutta", "kutte", "kuttiya", "lauda", "lavde", "lode",
    "chut", "gand", "bhenchod", "maderchod", "bosdike", "bosdi", "rand",
    "choot", "gaand", "bhosdi", "bhosda", "chodu", "chod", "chudai", "chud",
    "gandu", "gandoo", "gandwe", "gandfat", "gandmasti", "gandu", "gaand",
    
    # Romanized Hindi abuse (common variations)
    "mc", "bc", "randi", "chutiye", "bkl", "bsdk", "bsdka", "lodu", "lavdu",
    "madar", "behen", "chootiya", "chutiye", "gandu", "gandwe", "lund",
    "land", "laund", "launda", "chut", "choot",
    
    # Evasion attempts (common misspellings)
    "fuk", "shyt", "bich", "asshle", "mdrchod", "bhenchd", "chtiya", "gndu",
    "lundh", "rndi", "hrma", "kmina", "kuttaa", "kutti", "lawda", "lawde",
    "lauda", "laude", "choot", "gaandu", "bhonsdi", "bhosdika", "choduu",
    "fak", "shit", "bich", "ass", "mader", "chutia", "gando",
    
    # Number substitutions (common evasions)
    "f0ck", "sh1t", "b1tch", "4ss", "@ss", "@ssh0le", "m0therfucker",
    "n1gger", "f4gg0t", "r3tard", "1d10t", "m0r0n", "st00pid",
    
    # Character substitutions
    "f*ck", "sh*t", "b*tch", "a**hole", "a$$hole", "f**k", "s**t",
    "b****", "m*****f*****", "n*****", "f*****",
    
    # Additional abusive terms in context
    "suck my", "eat my", "kill you", "kill yourself", "die", "death",
    "hate you", "fuck off", "fuck you", "go to hell", "burn in hell",
    "son of a", "your mom", "your mother", "your sister", "your father",
]

ABUSE_REGEX = re.compile(
    r"\b(" + "|".join(map(re.escape, ABUSE_WORDS)) + r")\b",
    re.IGNORECASE
)



# ================= UNIVERSAL MODERATION COMMAND HANDLER =========
async def handle_moderation_command(client, message: Message, command_type="mute"):
    user = message.from_user
    chat = message.chat

    cmd = message.command[0].lower()   # mute / bmute / ban / bban

    is_bot_admin_user = is_bot_admin(user.id)
    is_group_admin_user = await can_user_restrict(client, chat.id, user.id)

    REGULAR_COMMANDS = ["ban", "mute", "unmute", "warn", "kick"]
    BOT_ADMIN_COMMANDS = ["b" + c for c in REGULAR_COMMANDS]

    is_bot_command = cmd in BOT_ADMIN_COMMANDS
    base_command = cmd[1:] if is_bot_command else cmd  # bmute -> mute

    # ---------------- PERMISSION CHECK ----------------
    if is_bot_command:
        # ONLY bot admin
        if not is_bot_admin_user:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Bot Admin Required**\n"
                "This command is restricted to bot admins."
                + beautiful_footer()
            )
            return None
    else:
        # normal command
        if not (is_group_admin_user or is_bot_admin_user):
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Permission Denied**\n"
                "You must be Group Admin or Bot Admin."
                + beautiful_footer()
            )
            return None

    # ---------------- BOT ADMIN RIGHTS ----------------
    if not await can_bot_restrict(client, chat.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "❌ **Bot Needs Admin Rights**\n"
            "Grant me 'Restrict Users' permission."
            + beautiful_footer()
        )
        return None

    # ---------------- TARGET USER ----------------
    target_user = None
    args = []

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        args = message.command[1:]

    elif len(message.command) > 1:
        user_arg = message.command[1]
        args = message.command[2:]
        try:
            target_user = await client.get_users(user_arg.lstrip("@"))
        except:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **User Not Found**"
                + beautiful_footer()
            )
            return None

    if not target_user:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **User Required**\n\n"
            f"Usage:\n"
            f"/{cmd} @user [duration] [reason]\n"
            f"or reply to user"
            + beautiful_footer()
        )
        return None

    # ---------------- SELF ACTION BLOCK ----------------
    if target_user.id == user.id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "😂 You cannot moderate yourself."
            + beautiful_footer()
        )
        return None

    # ---------------- TARGET ADMIN CHECK ----------------
    try:
        member = await client.get_chat_member(chat.id, target_user.id)
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            # bot admin override allowed
            if not is_bot_admin_user:
                await message.reply_text(
                    f"{beautiful_header('moderation')}\n\n"
                    "❌ Cannot moderate an admin."
                    + beautiful_footer()
                )
                return None
    except:
        pass

    return target_user, args, base_command


@app.on_message(filters.command(["mybotadmin", "myadmin", "botadmin"]) & filters.group)
async def my_bot_admin_group_command(client, message: Message):
    """Check bot admin status in groups"""
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check all statuses
    is_bot_admin_user = is_bot_admin(user_id)
    is_super_admin = user_id == SUPER_ADMIN
    
    # Check group admin status
    try:
        member = await client.get_chat_member(chat_id, user_id)
        is_group_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        is_group_owner = member.status == ChatMemberStatus.OWNER
    except:
        is_group_admin = False
        is_group_owner = False
    
    # Check bot permissions in group
    bot_can_restrict = await can_bot_restrict(client, chat_id)
    
    status_text = f"""
{beautiful_header('admin')}

📊 **ADMIN STATUS - {message.chat.title}**

**👤 Your Status:**
• Bot Super Admin: {'✅ Yes' if is_super_admin else '❌ No'}
• Bot Admin: {'✅ Yes' if is_bot_admin_user else '❌ No'}
• Group Admin: {'✅ Yes' if is_group_admin else '❌ No'}
• Group Owner: {'✅ Yes' if is_group_owner else '❌ No'}

**🤖 Bot Status:**
• Admin in Group: {'✅ Yes' if bot_can_restrict else '❌ No'}

**🔧 Available Commands:**
"""
    
    # Add available commands based on status
    if is_super_admin:
        status_text += "• All commands (Super Admin)\n"
    elif is_bot_admin_user:
        status_text += "• /bmute, /bban, /bwarn, etc.\n"
        status_text += "• /purge, /purgeall\n"
        status_text += "• /lock, /unlock\n"
        status_text += "• /promote, /demote\n"
    elif is_group_admin:
        status_text += "• /mute, /ban, /warn, /kick\n"
        status_text += "• /purge, /purgeall\n"
        status_text += "• /lock, /unlock\n"
        status_text += "• /promote, /demote\n"
    else:
        status_text += "• Regular user commands only\n"
        status_text += "• /id, /myid, /chatid\n"
        status_text += "• /tagadmin\n"
        status_text += "• /help\n"
    
    status_text += f"\n**💡 Tip:** Use `/mystatus` for detailed permission check"
    
    await message.reply_text(status_text + beautiful_footer())

@app.on_message(filters.command("mystatus") & filters.group)
async def my_status_command(client, message: Message):
    """Detailed status check"""
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Get all statuses
    is_bot_admin_user = is_bot_admin(user_id)
    is_super_admin = user_id == SUPER_ADMIN
    
    # Get group member info
    try:
        member = await client.get_chat_member(chat_id, user_id)
        member_status = member.status.value if hasattr(member.status, 'value') else str(member.status)
        is_group_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        is_group_owner = member.status == ChatMemberStatus.OWNER
        
        # Get specific permissions if admin
        if is_group_admin and hasattr(member, 'privileges'):
            can_delete = member.privileges.can_delete_messages
            can_restrict = member.privileges.can_restrict_members
            can_pin = member.privileges.can_pin_messages
            can_invite = member.privileges.can_invite_users
            can_promote = member.privileges.can_promote_members
            can_change = member.privileges.can_change_info
        else:
            can_delete = can_restrict = can_pin = can_invite = can_promote = can_change = False
    except:
        member_status = "Unknown"
        is_group_admin = is_group_owner = False
        can_delete = can_restrict = can_pin = can_invite = can_promote = can_change = False
    
    # Check bot permissions
    bot_can_restrict = await can_bot_restrict(client, chat_id)
    
    # Create status table
    status_text = f"""
{beautiful_header('info')}

📊 **DETAILED STATUS REPORT**

**👤 USER INFO:**
• Name: {message.from_user.first_name or ''} {message.from_user.last_name or ''}
• ID: `{user_id}`
• Username: @{message.from_user.username if message.from_user.username else 'Not set'}

**🏷️ GROUP INFO:**
• Title: {message.chat.title}
• ID: `{chat_id}`
• Your Status: {member_status}

**🔐 ADMIN STATUS:**
• Bot Super Admin: {'✅' if is_super_admin else '❌'}
• Bot Admin: {'✅' if is_bot_admin_user else '❌'}
• Group Admin: {'✅' if is_group_admin else '❌'}
• Group Owner: {'✅' if is_group_owner else '❌'}

**🛡️ YOUR PERMISSIONS:**
• Delete Messages: {'✅' if can_delete else '❌'}
• Restrict Users: {'✅' if can_restrict else '❌'}
• Pin Messages: {'✅' if can_pin else '❌'}
• Invite Users: {'✅' if can_invite else '❌'}
• Promote Admins: {'✅' if can_promote else '❌'}
• Change Info: {'✅' if can_change else '❌'}

**🤖 BOT STATUS:**
• Admin in Group: {'✅ Yes' if bot_can_restrict else '❌ No'}

**⚡ AVAILABLE COMMANDS:**
"""
    
    # Add commands based on permissions
    commands_list = []
    
    # Everyone can use
    commands_list.append("• /id, /myid, /chatid")
    commands_list.append("• /tagadmin")
    commands_list.append("• /help, /mystatus")
    
    # Group admins
    if is_group_admin or is_bot_admin_user:
        commands_list.append("• /mute, /unmute, /ban, /unban, /kick, /warn")
        commands_list.append("• /purge, /purgeall, /pin, /unpin")
        commands_list.append("• /lock, /unlock, /lockstatus")
        commands_list.append("• /promote, /demote")
        commands_list.append("• /setwelcome, /delwelcome")
        commands_list.append("• /tagall, /stop")
    
    # Bot admins only
    if is_bot_admin_user:
        commands_list.append("• /bmute, /bunmute, /bban, /bunban, /bkick, /bwarn")
    
    # Super admin only
    if is_super_admin:
        commands_list.append("• /addbotadmin, /removebotadmin")
        commands_list.append("• /exportcsv, /broadcast")
        commands_list.append("• /glock, /gunlock")
    
    status_text += "\n".join(commands_list)
    
    status_text += f"\n\n**💡 Note:** Bot admin commands work in PM only"
    
    await message.reply_text(status_text + beautiful_footer())


# ================= MUTE COMMANDS =================
@app.on_message(filters.command(["mute", "bmute"]) & filters.group)
async def universal_mute(client, message: Message):
    """Universal mute command for both bot admins and group admins"""
    
    result = await handle_moderation_command(client, message, "mute")
    if not result:
        return
    
    target_user, args, base_command = result
    
    # Parse duration and reason
    duration = None
    reason = "No reason provided"
    
    if args:
        duration = parse_duration(args[0])
        if duration:
            if len(args) > 1:
                reason = " ".join(args[1:])
        else:
            reason = " ".join(args)
    
    # Check admin type for message
    is_bot_admin_user = is_bot_admin(message.from_user.id)
    command_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    try:
        # Apply mute
        mute_kwargs = {
            "chat_id": message.chat.id,
            "user_id": target_user.id,
            "permissions": ChatPermissions()
        }
        
        if duration:
            mute_kwargs["until_date"] = datetime.now(timezone.utc) + duration
            duration_text = str(duration)
        else:
            duration_text = "Permanent"
        
        await client.restrict_chat_member(**mute_kwargs)
        
        # Save to cache if temporary
        if duration:
            if message.chat.id not in user_mutes:
                user_mutes[message.chat.id] = {}
            user_mutes[message.chat.id][target_user.id] = datetime.now(timezone.utc) + duration
        
        success_text = f"""
{beautiful_header('moderation')}

✅ **USER MUTED** (by {command_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
⏰ **Duration:** {duration_text}
📝 **Reason:** {reason}
👨‍💼 **By:** {message.from_user.mention}

🔇 User has been muted
        """
        
        await message.reply_text(success_text + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **Mute Failed**\nError: {str(e)[:150]}"
            + beautiful_footer()
  )



# ================= UNMUTE COMMANDS =================
@app.on_message(filters.command(["unmute", "bunmute"]) & filters.group)
async def universal_unmute(client, message: Message):
    """Universal unmute command for both bot admins and group admins"""
    
    # Check admin status
    user_id = message.from_user.id
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, message.chat.id, user_id)
    
    command_prefix = message.command[0]
    is_bot_command = command_prefix.startswith("b") and len(command_prefix) > 1
    
    # Check permissions
    if is_bot_command:
        if not is_bot_admin_user:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Bot Admin Required**\n"
                "This command is only for bot admins.\n"
                "Use `/mybotadmin` to check your status."
                + beautiful_footer()
            )
            return
    else:
        if not (is_group_admin_user or is_bot_admin_user):
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Permission Denied**\n"
                "You need to be either:\n"
                "• Group admin (with restrict permissions)\n"
                "• Bot admin (added to bot admin list)\n\n"
                "Use `/mystatus` to check your permissions."
                + beautiful_footer()
            )
            return
    
    # Check bot permissions
    if not await can_bot_restrict(client, message.chat.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "❌ **Bot Needs Admin Rights**\n"
            "I need admin permissions in this group.\n"
            "Please make me admin with 'Restrict Users' permission."
            + beautiful_footer()
        )
        return
    
    # Get target user
    target_user = None
    
    # Method 1: Reply to message
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
    
    # Method 2: User ID/Username from command
    elif len(message.command) > 1:
        user_arg = message.command[1]
        
        try:
            if user_arg.startswith("@"):
                target_user = await client.get_users(user_arg[1:])
            else:
                target_user = await client.get_users(int(user_arg))
        except Exception as e:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                f"❌ **User Not Found**\n`{user_arg}`"
                + beautiful_footer()
            )
            return
    
    if not target_user:
        usage_text = f"""
{beautiful_header('moderation')}

❌ **User Required**

**Usage:**
1. Reply to user + `/{command_prefix}`
2. `/{command_prefix} @username`

**Examples:**
• `/{command_prefix} @user`
• `/{command_prefix}` (reply to user)
"""
        
        await message.reply_text(usage_text + beautiful_footer())
        return
    
    # Check admin type for message
    admin_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    try:
        # Restore default permissions for the user
        await client.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False
            )
        )
        
        # Remove from mute cache
        if message.chat.id in user_mutes and target_user.id in user_mutes[message.chat.id]:
            del user_mutes[message.chat.id][target_user.id]
        
        success_text = f"""
{beautiful_header('moderation')}

✅ **USER UNMUTED** (by {admin_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
👨‍💼 **By:** {message.from_user.mention}

🔊 User can now send messages again
        """
        
        await message.reply_text(success_text + beautiful_footer())
        
        # Notify user
        try:
            await client.send_message(
                target_user.id,
                f"{beautiful_header('support')}\n\n"
                f"🔊 **You have been unmuted**\n\n"
                f"Your mute in **{message.chat.title}** has been lifted.\n"
                f"👨‍💼 **By:** {message.from_user.mention}\n\n"
                f"You can now send messages in the group again."
                f"{beautiful_footer()}"
            )
        except:
            pass
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **Unmute Failed**\nError: {str(e)[:150]}"
            + beautiful_footer()
        )


# ================= WARN COMMANDS =================
@app.on_message(filters.command(["warn", "bwarn"]) & filters.group)
async def universal_warn(client, message: Message):
    """Universal warn command"""
    
    result = await handle_moderation_command(client, message, "warn")
    if not result:
        return
    
    target_user, args, base_command = result
    
    # Parse reason
    reason = "No reason provided"
    if args:
        reason = " ".join(args)
    
    # Check admin type for message
    is_bot_admin_user = is_bot_admin(message.from_user.id)
    command_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    # Save warning to database
    cur.execute(
        "INSERT INTO user_warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
        (message.chat.id, target_user.id, reason)
    )
    conn.commit()
    
    # Get warning count
    cur.execute(
        "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
        (message.chat.id, target_user.id)
    )
    warning_count = cur.fetchone()[0]
    
    # Check for auto-ban
    action = None
    if warning_count >= 3:
        try:
            await client.ban_chat_member(message.chat.id, target_user.id)
            action = "banned"
            # Clear warnings
            cur.execute(
                "DELETE FROM user_warnings WHERE chat_id=? AND user_id=?",
                (message.chat.id, target_user.id)
            )
            conn.commit()
        except:
            action = "ban failed"
    
    warn_msg = f"""
{beautiful_header('moderation')}

⚠️ **WARNING #{warning_count} ISSUED** (by {command_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
📝 **Reason:** {reason}
📊 **Total Warnings:** {warning_count}/3
👨‍💼 **By:** {message.from_user.mention}
    """
    
    if action == "banned":
        warn_msg += "\n\n🚫 **AUTO-BANNED** for reaching 3 warnings!"
    elif action == "ban failed":
        warn_msg += "\n\n⚠️ **Auto-ban failed** (check bot permissions)"
    
    await message.reply_text(warn_msg + beautiful_footer())

# ================= BAN COMMANDS =================
@app.on_message(filters.command(["ban", "bban"]) & filters.group)
async def universal_ban(client, message: Message):
    """Universal ban command"""
    
    result = await handle_moderation_command(client, message, "ban")
    if not result:
        return
    
    target_user, args, base_command = result
    
    # Parse reason
    reason = "No reason provided"
    if args:
        reason = " ".join(args)
    
    # Check admin type for message
    is_bot_admin_user = is_admin(message.from_user.id)
    command_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    try:
        await client.ban_chat_member(message.chat.id, target_user.id)
        
        # Clear warnings for this user
        cur.execute(
            "DELETE FROM user_warnings WHERE chat_id=? AND user_id=?",
            (message.chat.id, target_user.id)
        )
        conn.commit()
        
        ban_msg = f"""
{beautiful_header('moderation')}

🚫 **USER BANNED** (by {command_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
📝 **Reason:** {reason}
👨‍💼 **By:** {message.from_user.mention}

⛔ User removed from group
        """
        
        await message.reply_text(ban_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Ban Failed**\n`{str(e)}`" + beautiful_footer()
  )



# ================= UNBAN COMMANDS =================
@app.on_message(filters.command(["unban", "bunban"]) & filters.group)
async def universal_unban(client, message: Message):
    """Universal unban command"""
    
    result = await handle_moderation_command(client, message, "unban")
    if not result:
        return
    
    target_user, args, base_command = result
    
    # Check admin type for message
    is_bot_admin_user = is_bot_admin(message.from_user.id)
    command_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    try:
        await client.unban_chat_member(message.chat.id, target_user.id)
        
        unban_msg = f"""
{beautiful_header('moderation')}

✅ **USER UNBANNED** (by {command_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
👨‍💼 **By:** {message.from_user.mention}

🔓 User can now join the group again
        """
        
        await message.reply_text(unban_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Unban Failed**\n`{str(e)}`" + beautiful_footer()
        )



# ================= KICK COMMANDS =================
@app.on_message(filters.command(["kick", "bkick"]) & filters.group)
async def universal_kick(client, message: Message):
    """Universal kick command"""
    
    result = await handle_moderation_command(client, message, "kick")
    if not result:
        return
    
    target_user, args, base_command = result
    
    # Parse reason
    reason = "No reason provided"
    if args:
        reason = " ".join(args)
    
    # Check admin type for message
    is_bot_admin_user = is_bot_admin(message.from_user.id)
    command_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
    
    try:
        await client.ban_chat_member(message.chat.id, target_user.id)
        await asyncio.sleep(1)
        await client.unban_chat_member(message.chat.id, target_user.id)
        
        kick_msg = f"""
{beautiful_header('moderation')}

👢 **USER KICKED** (by {command_type})

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
📝 **Reason:** {reason}
👨‍💼 **By:** {message.from_user.mention}

🚶 User removed from group
        """
        
        await message.reply_text(kick_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Failed to Kick**\n`{str(e)}`" + beautiful_footer()
        )



# ===== PERMISSION CHECK FUNCTIONS =====

async def is_user_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user is admin in the group"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [
            ChatMemberStatus.ADMINISTRATOR, 
            ChatMemberStatus.OWNER
        ]
    except Exception:
        return False

async def can_user_pin_messages(client: Client, chat_id: int, user_id: int) -> bool:
    """Check if user has permission to pin messages"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        
        # If user is owner, they can always pin
        if member.status == ChatMemberStatus.OWNER:
            return True
        
        # If user is admin, check their privileges
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            return member.privileges.can_pin_messages if member.privileges else False
        
        return False
    except Exception:
        return False

def bot_admin(user_id: int) -> bool:
    """Check if user is the bot admin/owner"""
    return user_id in INITIAL_ADMINS



# Pin message - requires bot admin OR group admin
@app.on_message(filters.command(["pin", "pinmsg"]) & filters.group)
async def pin_message(client: Client, message: Message):
    """Pin a message with admin permission check"""
    try:
        # Check if user replied to a message
        if not message.reply_to_message:
            await message.reply("❌ **Please reply to a message to pin it.**")
            return
        
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # ===== Permission check =====
        is_bot_admin_user = bot_admin(user_id)
        can_pin = await can_user_pin_messages(client, chat_id, user_id)
        
        if not (is_bot_admin_user or can_pin):
            await message.reply("❌ **You don't have permission to pin messages!**\n"
                              "You need to be either:\n"
                              "• Bot Administrator\n"
                              "• Group Administrator with pin permission")
            return
        
        # Pin the message
        disable_notification = False
        
        # Check for silent flag
        if len(message.command) > 1 and message.command[1].lower() in ['silent', 'quiet']:
            disable_notification = True
        
        await client.pin_chat_message(
            chat_id=chat_id,
            message_id=message.reply_to_message.id,
            disable_notification=disable_notification
        )
        
        # Send confirmation
        if disable_notification:
            await message.reply("🔕 **Message pinned silently!**")
        else:
            await message.reply("📌 **Message pinned successfully!**")
        
        # Optional: Delete the command message
        try:
            await message.delete()
        except:
            pass
        
    except Exception as e:
        await message.reply(f"❌ **Failed to pin message:** `{str(e)}`")


# Unpin specific message - requires bot admin OR group admin
@app.on_message(filters.command(["unpin", "unpinmsg"]) & filters.group)
async def unpin_message(client: Client, message: Message):
    """Unpin a specific message with admin permission check"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # ===== Permission check =====
        is_bot_admin_user = bot_admin(user_id)
        can_pin = await can_user_pin_messages(client, chat_id, user_id)
        
        if not (is_bot_admin_user or can_pin):
            await message.reply("❌ **You don't have permission to unpin messages!**")
            return
        
        if message.reply_to_message:
            # Unpin the specific replied message
            await client.unpin_chat_message(
                chat_id=chat_id,
                message_id=message.reply_to_message.id
            )
            await message.reply("✅ **Message unpinned successfully!**")
        else:
            await message.reply("❌ **Please reply to a pinned message to unpin it.**")
            
    except Exception as e:
        await message.reply(f"❌ **Failed to unpin:** `{str(e)}`")


# ================================= Pin System ========================




# ================= ADMIN MANAGEMENT COMMANDS =================
@app.on_message(filters.command("addbotadmin") & filters.private)
async def add_bot_admin_command(client, message: Message):
    """Add a bot admin (super admin only)"""
    if message.from_user.id != SUPER_ADMIN:
        await message.reply_text("❌ **Access Denied** - Super admin only")
        return
    
    if len(message.command) < 2:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Usage:** `/addbotadmin [user_id]`\n\n"
            "**Example:** `/addbotadmin 1234567890`"
            + beautiful_footer()
        )
        return
    
    try:
        admin_id = int(message.command[1])
        cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (admin_id,))
        conn.commit()
        
        try:
            user_obj = await client.get_users(admin_id)
            user_name = user_obj.mention
        except:
            user_name = f"User ID: `{admin_id}`"
        
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"✅ **Bot Admin Added**\n\n"
            f"👤 **User:** {user_name}\n"
            f"🆔 **ID:** `{admin_id}`\n"
            f"👑 **Added by:** {message.from_user.mention}"
            + beautiful_footer()
        )
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"❌ **Failed to Add Admin**\nError: {str(e)}"
            + beautiful_footer()
        )


@app.on_message(filters.command("listbotadmins") & filters.private)
async def list_bot_admins_command(client, message: Message):
    """List all bot admins"""
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ **Access Denied** - Bot admins only")
        return
    
    cur.execute("SELECT admin_id FROM admins ORDER BY admin_id")
    admins = cur.fetchall()
    
    if not admins:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "📭 **No Bot Admins Found**"
            + beautiful_footer()
        )
        return
    
    admin_list = []
    for (admin_id,) in admins:
        try:
            user = await client.get_users(admin_id)
            if admin_id == SUPER_ADMIN:
                admin_list.append(f"👑 **Super Admin:** {user.mention} (`{admin_id}`)")
            else:
                admin_list.append(f"⚡ **Admin:** {user.mention} (`{admin_id}`)")
        except:
            if admin_id == SUPER_ADMIN:
                admin_list.append(f"👑 **Super Admin:** `{admin_id}`")
            else:
                admin_list.append(f"⚡ **Admin:** `{admin_id}`")
    
    admin_text = "\n".join(admin_list)
    
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        f"👥 **Bot Administrators**\n\n"
        f"{admin_text}\n\n"
        f"📊 **Total:** {len(admins)} admins"
        + beautiful_footer()
    )



@app.on_message(filters.command("promote") & filters.group)
async def promote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    # ================= CALLER STATUS =================
    member = await client.get_chat_member(chat_id, caller_id)

    is_owner = member.status == ChatMemberStatus.OWNER
    is_group_admin = member.status == ChatMemberStatus.ADMINISTRATOR
    is_bot_admin_user = is_admin(caller_id)

    if not (is_owner or is_group_admin or is_bot_admin_user):
        return await message.reply_text("❌ Only admins can promote members")

    # ================= BOT PERMISSION =================
    bot = await client.get_chat_member(chat_id, "me")
    if bot.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await message.reply_text("❌ Make me admin with promote permission")

    if hasattr(bot, "privileges") and not bot.privileges.can_promote_members:
        return await message.reply_text("❌ I need Add New Admins permission")

    # ================= TARGET =================
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        args = message.command[1:]
    elif len(message.command) > 1:
        target = await client.get_users(message.command[1])
        args = message.command[2:]
    else:
        return await message.reply_text("❌ Reply or use `/promote @user [title]`")

    if target.id == caller_id:
        return await message.reply_text("❌ You cannot promote yourself")

    tm = await client.get_chat_member(chat_id, target.id)
    if tm.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await message.reply_text("⚠️ User already admin")

    # ================= ADMIN TITLE =================
    admin_title = "Admin"
    if args:
        admin_title = " ".join(args)

    admin_title = admin_title[:16]  # Telegram limit

    # ================= PRIVILEGES =================
    if is_owner or is_bot_admin_user:
        privileges = ChatPrivileges(
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_video_chats=True,
            can_promote_members=True,
            can_change_info=True,
            can_manage_chat=True,
            is_anonymous=False
        )
        promoter_type = "Owner" if is_owner else "Bot Admin"
    else:
        privileges = ChatPrivileges(
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_video_chats=True,
            can_promote_members=False,
            can_change_info=False,
            can_manage_chat=False,
            is_anonymous=False
        )
        promoter_type = "Group Admin"

    # ================= PROMOTE =================
    await client.promote_chat_member(
        chat_id=chat_id,
        user_id=target.id,
        privileges=privileges
    )

    # ================= SET TITLE (🔥 FIX) =================
    try:
        await client.set_administrator_title(
            chat_id,
            target.id,
            admin_title
        )
    except:
        pass  # title optional hai

    # ================= SUCCESS =================
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        f"✅ **PROMOTED SUCCESSFULLY**\n\n"
        f"👤 User: {target.mention}\n"
        f"🏷 Title: `{admin_title}`\n"
        f"👑 By: {caller.mention} ({promoter_type})"
        f"{beautiful_footer()}"
    )

@app.on_message(filters.command("demote") & filters.group)
async def demote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    # ================= CALLER STATUS =================
    try:
        member = await client.get_chat_member(chat_id, caller_id)
    except:
        return

    is_owner = member.status == ChatMemberStatus.OWNER
    is_group_admin = member.status == ChatMemberStatus.ADMINISTRATOR
    is_bot_admin_user = is_admin(caller_id)  # bot/super admin

    if not (is_owner or is_group_admin or is_bot_admin_user):
        return await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Only admins can demote members**"
            f"{beautiful_footer()}"
        )

    # ================= BOT PERMISSION =================
    try:
        bot = await client.get_chat_member(chat_id, "me")
    except:
        return await message.reply_text("❌ Unable to check bot permissions")

    if bot.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ Make me admin with **Add New Admins** permission"
            f"{beautiful_footer()}"
        )

    if hasattr(bot, "privileges"):
        if not bot.privileges.can_promote_members:
            return await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                "❌ I need **Add New Admins** permission"
                f"{beautiful_footer()}"
            )

    # ================= TARGET USER =================
    try:
        if message.reply_to_message:
            target = message.reply_to_message.from_user
        elif len(message.command) > 1:
            target = await client.get_users(message.command[1])
        else:
            return await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                "❌ Reply to a user or use `/demote @user`"
                f"{beautiful_footer()}"
            )
    except:
        return await message.reply_text("❌ User not found")

    # ================= SAFETY CHECKS =================
    if target.id == caller_id:
        return await message.reply_text("❌ You cannot demote yourself")

    try:
        target_member = await client.get_chat_member(chat_id, target.id)

        if target_member.status == ChatMemberStatus.OWNER:
            return await message.reply_text("❌ You cannot demote the group owner")

        if target_member.status != ChatMemberStatus.ADMINISTRATOR:
            return await message.reply_text("⚠️ User is not an admin")
    except:
        return

    # ================= DEMOTE =================
    try:
        # remove all admin privileges
        await client.promote_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            can_change_info=False,
            can_delete_messages=False,
            can_restrict_members=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_manage_video_chats=False,
            can_promote_members=False,
            can_manage_chat=False,
            is_anonymous=False
        )
    except Exception as e:
        return await message.reply_text(
            f"❌ Demote failed\n`{str(e)}`"
        )

    # ================= SUCCESS =================
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        "✅ **ADMIN REMOVED SUCCESSFULLY**\n\n"
        f"👤 **User:** {target.mention}\n"
        f"👑 **By:** {caller.mention}"
        f"{beautiful_footer()}"
    )
# ================= STORE LOCK STATES PER CHAT =================
chat_locks = {}

# ================= LOCK COMMAND =================
 # ================= FIXED LOCK COMMAND WITH WORKING AUTO-UNLOCK =================
@app.on_message(filters.command(["lock", "block"]) & filters.group)
async def lock_chat_permissions(client, message: Message):
    """Lock specific permissions in the group - FIXED with auto-unlock"""
    
    # Check permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('danger')}\n\n"
            "❌ **PERMISSION DENIED**\n\n"
            "**You need to be either:**\n"
            "• Group admin with restrict permissions\n"
            "• Bot admin (added to admin list)\n\n"
            "📊 **Your Status:**\n"
            f"- Group Admin: {'✅ Yes' if is_group_admin_user else '❌ No'}\n"
            f"- Bot Admin: {'✅ Yes' if is_bot_admin_user else '❌ No'}\n\n"
            "💡 **Use:** `/mystatus` to check your permissions"
            f"{beautiful_footer()}"
        )
        return
    
    # Check bot permissions
    bot_is_admin = await can_bot_restrict(client, chat_id)
    if not bot_is_admin:
        await message.reply_text(
            f"{beautiful_header('danger')}\n\n"
            "❌ **BOT NEEDS ADMIN RIGHTS**\n\n"
            "**Required Permissions:**\n"
            "✅ Delete Messages\n"
            "✅ Restrict Users\n"
            "✅ Change Chat Info\n\n"
            "**How to fix:**\n"
            "1. Open group settings\n"
            "2. Go to Administrators\n"
            "3. Select this bot\n"
            "4. Enable all permissions"
            f"{beautiful_footer()}"
        )
        return
    
    # All lock types available
    lock_types = [
        "all", "text", "media", "stickers", "polls", "invites",
        "pins", "info", "url", "games", "inline", "voice",
        "video", "audio", "documents", "photos", "forward"
    ]
    
    lock_descriptions = {
        "all": "🔒 Lock everything completely",
        "text": "📝 Disable text messages only",
        "media": "🖼️ Disable all media (photos, videos, audio, docs)",
        "stickers": "😀 Disable stickers & GIFs",
        "polls": "📊 Disable polls",
        "invites": "👥 Disable invite link sharing",
        "pins": "📌 Disable message pinning",
        "info": "ℹ️ Prevent changing group info",
        "url": "🔗 Block all links/URLs",
        "games": "🎮 Disable games",
        "inline": "🔍 Disable inline bots",
        "voice": "🎤 Disable voice messages",
        "video": "🎥 Disable video messages",
        "audio": "🎵 Disable audio messages",
        "documents": "📎 Disable documents/files",
        "photos": "📸 Disable photos only",
        "forward": "📨 Auto-delete forwarded messages"
    }
    
    # Show help if no lock type specified
    if len(message.command) < 2:
        help_text = f"""
{beautiful_header('guide')}

🔒 **LOCK COMMAND GUIDE**

**Usage:** `/lock [type] [duration]`

**Available Lock Types (17 total):**
• all, text, media, stickers, polls, invites
• pins, info, url, games, inline, voice
• video, audio, documents, photos, forward

**⏰ DURATION FORMAT:**
• `/lock text 30m` - Lock for 30 minutes
• `/lock all 2h` - Lock for 2 hours
• `/lock media 1d` - Lock for 1 day
• `/lock stickers 1w` - Lock for 1 week

**Examples:**
• `/lock all 1h` - Lock everything for 1 hour
• `/lock text` - Lock text permanently
• `/lock forward` - Auto-delete forwards
"""
        await message.reply_text(help_text + beautiful_footer())
        return
    
    # Parse lock type and duration
    lock_type = message.command[1].lower()
    
    # Check for duration
    duration = None
    duration_text = "Permanent"
    if len(message.command) > 2:
        duration = parse_duration(message.command[2])
        if duration:
            duration_text = f"{duration}"
        else:
            # If duration parsing failed, treat as reason
            pass
    
    # Validate lock type
    if lock_type not in lock_types:
        error_text = f"""
{beautiful_header('warning')}

❌ **INVALID LOCK TYPE**

You entered: `{lock_type}`

**Valid Lock Types:**
• all, text, media, stickers, polls, invites
• pins, info, url, games, inline, voice
• video, audio, documents, photos, forward

**Usage:** `/lock [type] [duration]`
**Example:** `/lock text 1h`

💡 **Tip:** Use `/lock` alone to see all options
"""
        await message.reply_text(error_text + beautiful_footer())
        return
    
    # Apply lock
    try:
        # Get current permissions
        current_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_send_polls=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        
        description = lock_descriptions.get(lock_type, "Custom lock")
        
        # Apply specific lock
        if lock_type == "all":
            current_permissions = ChatPermissions()  # All False
            action_text = "🔒 **COMPLETE LOCKDOWN**"
            details = "• All permissions disabled\n• No one can send anything"
        
        elif lock_type == "text":
            current_permissions.can_send_messages = False
            action_text = "📝 **TEXT LOCKED**"
            details = "• Text messages disabled\n• Media still allowed"
        
        elif lock_type == "media":
            current_permissions.can_send_media_messages = False
            current_permissions.can_send_other_messages = False
            action_text = "🖼️ **MEDIA LOCKED**"
            details = "• Photos, videos, audio blocked\n• Text messages allowed"
        
        elif lock_type == "stickers":
            current_permissions.can_send_other_messages = False
            action_text = "😀 **STICKERS LOCKED**"
            details = "• Stickers & GIFs disabled\n• Text/media still allowed"
        
        elif lock_type == "polls":
            current_permissions.can_send_polls = False
            action_text = "📊 **POLLS LOCKED**"
            details = "• Poll creation disabled\n• Other messages allowed"
        
        elif lock_type == "invites":
            current_permissions.can_invite_users = False
            action_text = "👥 **INVITES LOCKED**"
            details = "• Invite sharing disabled\n• Can join via existing links"
        
        elif lock_type == "pins":
            current_permissions.can_pin_messages = False
            action_text = "📌 **PINS LOCKED**"
            details = "• Message pinning disabled\n• Admins can still pin"
        
        elif lock_type == "info":
            current_permissions.can_change_info = False
            action_text = "ℹ️ **INFO LOCKED**"
            details = "• Group info changes disabled\n• Chat functions work normally"
        
        elif lock_type == "url":
            current_permissions.can_add_web_page_previews = False
            action_text = "🔗 **URLS LOCKED**"
            details = "• Link sharing disabled\n• Text without links allowed"
        
        elif lock_type == "games":
            current_permissions.can_send_other_messages = False
            action_text = "🎮 **GAMES LOCKED**"
            details = "• Game sharing disabled\n• Other content allowed"
        
        elif lock_type == "inline":
            current_permissions.can_send_other_messages = False
            action_text = "🔍 **INLINE BOTS LOCKED**"
            details = "• Inline bot usage disabled\n• Regular messages allowed"
        
        elif lock_type == "voice":
            current_permissions.can_send_media_messages = False
            action_text = "🎤 **VOICE LOCKED**"
            details = "• Voice messages disabled\n• Text/other media allowed"
        
        elif lock_type == "video":
            current_permissions.can_send_media_messages = False
            action_text = "🎥 **VIDEO LOCKED**"
            details = "• Video messages disabled\n• Photos/audio allowed"
        
        elif lock_type == "audio":
            current_permissions.can_send_media_messages = False
            action_text = "🎵 **AUDIO LOCKED**"
            details = "• Audio messages disabled\n• Other media allowed"
        
        elif lock_type == "documents":
            current_permissions.can_send_media_messages = False
            action_text = "📎 **DOCUMENTS LOCKED**"
            details = "• Document sharing disabled\n• Photos/videos allowed"
        
        elif lock_type == "photos":
            current_permissions.can_send_media_messages = False
            action_text = "📸 **PHOTOS LOCKED**"
            details = "• Photo sharing disabled\n• Videos/audio allowed"
        
        elif lock_type == "forward":
            # Special forward lock uses filtering
            action_text = "📨 **FORWARDS LOCKED**"
            details = "• Forwarded messages will be auto-deleted\n• Original messages allowed"
        
        # Apply permissions (except forward lock)
        if lock_type != "forward":
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=current_permissions
            )
        
        # Store lock state
        if chat_id not in chat_locks:
            chat_locks[chat_id] = {}
        
        lock_data = {
            "type": lock_type,
            "applied_at": datetime.now(timezone.utc),
            "applied_by": user_id,
            "applied_by_name": message.from_user.first_name,
            "duration": duration_text,
            "expires": datetime.now(timezone.utc) + duration if duration else None
        }
        
        chat_locks[chat_id][lock_type] = lock_data
        
        # Schedule auto-unlock if duration specified
        if duration:
            # Create a proper async task for auto-unlock
            asyncio.create_task(
                auto_unlock_with_logging(client, chat_id, lock_type, duration)
            )
            print(f"✅ Auto-unlock scheduled for {lock_type} in {duration}")
        
        # Get admin type
        admin_type = "⚡ Bot Admin" if is_bot_admin_user else "🔧 Group Admin"
        
        # Create success message
        success_text = f"""
{beautiful_header('moderation')}

✅ **LOCK APPLIED SUCCESSFULLY**

{action_text}

📋 **Lock Details:**
• **Type:** {lock_type.title()}
• **Description:** {description}
• **Duration:** {duration_text}
• **Admin:** {message.from_user.mention} ({admin_type})
• **Chat:** {message.chat.title}

🔒 **What's Locked:**
{details}
"""
        
        if duration:
            hours = duration.total_seconds() // 3600
            minutes = (duration.total_seconds() % 3600) // 60
            success_text += f"\n⏰ **Auto-unlock in:** {int(hours)}h {int(minutes)}m\n"
        
        success_text += f"""
📊 **To Check:** `/lockstatus`
🔓 **To Remove:** `/unlock {lock_type}`
"""
        
        await message.reply_text(success_text + beautiful_footer())
        
    except Exception as e:
        error_text = f"""
{beautiful_header('danger')}

❌ **LOCK FAILED**

**Error:** {str(e)[:100]}

**Possible Reasons:**
1. Bot missing 'Change Chat Info' permission
2. Telegram API limit reached
3. Network connectivity issue

**Solutions:**
1. Check bot permissions
2. Wait a moment and try again
3. Contact bot admin if issue persists
"""
        await message.reply_text(error_text + beautiful_footer())

# ================= UNLOCK COMMAND =================
@app.on_message(filters.command(["unlock", "unblock"]) & filters.group)
async def unlock_chat_permissions(client, message: Message):
    """Unlock specific permissions in the group - Command only version"""
    
    # Check permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('danger')}\n\n"
            "❌ **PERMISSION DENIED**\n\n"
            "**You need to be either:**\n"
            "• Group admin with restrict permissions\n"
            "• Bot admin (added to admin list)\n\n"
            "📊 **Your Status:**\n"
            f"- Group Admin: {'✅ Yes' if is_group_admin_user else '❌ No'}\n"
            f"- Bot Admin: {'✅ Yes' if is_bot_admin_user else '❌ No'}\n\n"
            "💡 **Use:** `/mystatus` to check your permissions"
            f"{beautiful_footer()}"
        )
        return
    
    # Check bot permissions
    bot_is_admin = await can_bot_restrict(client, chat_id)
    if not bot_is_admin:
        await message.reply_text(
            f"{beautiful_header('danger')}\n\n"
            "❌ **BOT NEEDS ADMIN RIGHTS**\n\n"
            "**Required Permissions:**\n"
            "✅ Delete Messages\n"
            "✅ Restrict Users\n"
            "✅ Change Chat Info\n\n"
            "**How to fix:**\n"
            "1. Open group settings\n"
            "2. Go to Administrators\n"
            "3. Select this bot\n"
            "4. Enable all permissions"
            f"{beautiful_footer()}"
        )
        return
    
    # All unlock types available
    unlock_types = [
        "all", "text", "media", "stickers", "polls", "invites",
        "pins", "info", "url", "games", "inline", "voice",
        "video", "audio", "documents", "photos", "forward"
    ]
    
    unlock_descriptions = {
        "all": "🔓 Unlock everything completely",
        "text": "📝 Allow text messages again",
        "media": "🖼️ Allow all media again",
        "stickers": "😀 Allow stickers & GIFs again",
        "polls": "📊 Allow polls again",
        "invites": "👥 Allow invite link sharing again",
        "pins": "📌 Allow message pinning again",
        "info": "ℹ️ Allow changing group info again",
        "url": "🔗 Allow links/URLs again",
        "games": "🎮 Allow games again",
        "inline": "🔍 Allow inline bots again",
        "voice": "🎤 Allow voice messages again",
        "video": "🎥 Allow video messages again",
        "audio": "🎵 Allow audio messages again",
        "documents": "📎 Allow documents/files again",
        "photos": "📸 Allow photos again",
        "forward": "📨 Allow forwarded messages again"
    }
    
    # Show help if no unlock type specified
    if len(message.command) < 2:
        # Check current locks first
        active_locks = []
        if chat_id in chat_locks:
            active_locks = list(chat_locks[chat_id].keys())
        
        if active_locks:
            help_text = f"""
{beautiful_header('guide')}

🔓 **UNLOCK COMMAND GUIDE**

**Currently Active Locks ({len(active_locks)}):**
{chr(10).join(f'• `{lock}`' for lock in active_locks)}

**Usage:** `/unlock [type]`
**Example:** `/unlock {active_locks[0] if active_locks else 'text'}`

**To unlock everything:** `/unlock all`

**Available Unlock Types:**
• all, text, media, stickers, polls, invites
• pins, info, url, games, inline, voice
• video, audio, documents, photos, forward

📊 **Check Status:** `/lockstatus`
🔒 **Lock Again:** `/lock [type]`
"""
        else:
            help_text = f"""
{beautiful_header('info')}

🔓 **UNLOCK COMMAND GUIDE**

**No Active Locks Found**
The chat is currently unlocked.

**Usage:** `/unlock [type]`
**Example:** `/unlock text`

**Available Unlock Types:**
• all, text, media, stickers, polls, invites
• pins, info, url, games, inline, voice
• video, audio, documents, photos, forward

💡 **Note:** Use this command to unlock
if something was previously locked.
"""
        await message.reply_text(help_text + beautiful_footer())
        return
    
    # Parse unlock type
    unlock_type = message.command[1].lower()
    
    # Validate unlock type
    if unlock_type not in unlock_types:
        error_text = f"""
{beautiful_header('warning')}

❌ **INVALID UNLOCK TYPE**

You entered: `{unlock_type}`

**Valid Unlock Types:**
• all, text, media, stickers, polls, invites
• pins, info, url, games, inline, voice
• video, audio, documents, photos, forward

**Usage:** `/unlock [type]`
**Example:** `/unlock text`

💡 **Tip:** Use `/unlock` alone to see active locks
"""
        await message.reply_text(error_text + beautiful_footer())
        return
    
    # Apply unlock
    try:
        description = unlock_descriptions.get(unlock_type, "Custom unlock")
        
        # Check if this lock is actually active
        was_locked = False
        lock_info = None
        
        if chat_id in chat_locks and unlock_type in chat_locks[chat_id]:
            was_locked = True
            lock_info = chat_locks[chat_id][unlock_type]
        
        # Restore default permissions
        default_permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_send_polls=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        
        if unlock_type == "all":
            # Unlock everything
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=default_permissions
            )
            
            # Clear all locks
            if chat_id in chat_locks:
                cleared_count = len(chat_locks[chat_id])
                chat_locks[chat_id].clear()
                action_text = "🔓 **COMPLETE UNLOCK**"
                details = f"• All {cleared_count} locks removed\n• Full permissions restored"
            
        elif unlock_type == "forward":
            # Remove forward lock
            if chat_id in chat_locks and "forward" in chat_locks[chat_id]:
                del chat_locks[chat_id]["forward"]
                action_text = "📨 **FORWARDS UNLOCKED**"
                details = "• Forwarded messages allowed\n• Auto-delete disabled"
            else:
                action_text = "📨 **FORWARDS ALREADY UNLOCKED**"
                details = "• Forwarded messages were not locked"
        
        else:
            # Unlock specific permission
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=default_permissions
            )
            
            # Remove from lock state
            if chat_id in chat_locks and unlock_type in chat_locks[chat_id]:
                del chat_locks[chat_id][unlock_type]
                action_text = f"🔓 **{unlock_type.upper()} UNLOCKED**"
                details = f"• {unlock_type.title()} permissions restored\n• Other locks remain active"
            else:
                action_text = f"🔓 **{unlock_type.upper()} ALREADY UNLOCKED**"
                details = f"• {unlock_type.title()} was not locked"
        
        # Get admin type
        admin_type = "⚡ Bot Admin" if is_bot_admin_user else "🔧 Group Admin"
        
        # Lock history
        lock_history = ""
        if was_locked and lock_info:
            applied_by = lock_info.get("applied_by_name", "Unknown")
            applied_at = lock_info.get("applied_at", datetime.now(timezone.utc))
            duration = lock_info.get("duration", "Unknown")
            
            # Calculate how long it was locked
            time_since = datetime.now(timezone.utc) - applied_at
            hours = int(time_since.total_seconds() // 3600)
            minutes = int((time_since.total_seconds() % 3600) // 60)
            
            lock_history = f"""
📜 **Lock History:**
• Applied by: {applied_by}
• Duration: {duration}
• Locked for: {hours}h {minutes}m
"""
        
        # Create success message
        success_text = f"""
{beautiful_header('moderation')}

✅ **UNLOCK APPLIED SUCCESSFULLY**

{action_text}

📋 **Unlock Details:**
• **Type:** {unlock_type.title()}
• **Description:** {description}
• **Admin:** {message.from_user.mention} ({admin_type})
• **Chat:** {message.chat.title}
• **Was Locked:** {'✅ Yes' if was_locked else '❌ No'}

{lock_history if lock_history else ''}

🔓 **What's Unlocked:**
{details}

📊 **Check Status:** `/lockstatus`
🔒 **Lock Again:** `/lock {unlock_type}`
"""
        
        await message.reply_text(success_text + beautiful_footer())
        
        # Send notification to chat for major unlocks
        if unlock_type in ["all", "text", "media"] and was_locked:
            await asyncio.sleep(1)
            notify_text = f"""
{beautiful_header('security')}

🎉 **GROUP NOTICE**

{action_text}

The {unlock_type} restriction has been removed.
Chat permissions have been restored.

Enjoy your conversations!
"""
            notification = await message.reply_text(notify_text + beautiful_footer())
            await asyncio.sleep(10)
            await notification.delete()
        
    except Exception as e:
        error_text = f"""
{beautiful_header('danger')}

❌ **UNLOCK FAILED**

**Error:** {str(e)[:80]}

**Possible Reasons:**
1. Bot missing 'Change Chat Info' permission
2. Telegram API limit reached
3. Network connectivity issue

**Solutions:**
1. Check bot permissions
2. Wait a moment and try again
3. Contact bot admin if issue persists

**Your Command:** `/unlock {unlock_type}`
"""
        await message.reply_text(error_text + beautiful_footer())




async def auto_unlock_with_logging(client, chat_id, lock_type, duration):
    """Reliable auto-unlock with logging"""
    
    try:
        # Convert duration to seconds
        wait_seconds = duration.total_seconds()
        print(f"⏰ Auto-unlock scheduled: Waiting {wait_seconds} seconds for {lock_type} in chat {chat_id}")
        
        # Wait for the duration
        await asyncio.sleep(wait_seconds)
        
        print(f"🔓 Auto-unlock executing: Unlocking {lock_type} in chat {chat_id}")
        
        # Remove lock from tracking
        if chat_id in chat_locks and lock_type in chat_locks[chat_id]:
            print(f"📝 Removing {lock_type} from chat_locks tracking")
            del chat_locks[chat_id][lock_type]
        
        # Restore default permissions
        if lock_type not in ["forward"]:  # Don't restore for forward lock
            print(f"🔧 Restoring permissions for {lock_type}")
            default_permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_send_polls=True,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True
            )
            
            try:
                await client.set_chat_permissions(
                    chat_id=chat_id,
                    permissions=default_permissions
                )
                print(f"✅ Permissions restored for {lock_type} in chat {chat_id}")
            except Exception as e:
                print(f"❌ Error restoring permissions: {e}")
        
        # Send notification
        try:
            await client.send_message(
                chat_id,
                f"{beautiful_header('security')}\n\n"
                f"⏰ **AUTO UNLOCK COMPLETE**\n\n"
                f"🔓 **Lock Type:** {lock_type.title()}\n"
                f"⏳ **Duration:** {duration} expired\n"
                f"🤖 **System:** Automatic Timer\n\n"
                f"✅ Permissions have been automatically restored."
                f"{beautiful_footer()}"
            )
            print(f"📢 Auto-unlock notification sent for {lock_type} in chat {chat_id}")
        except Exception as e:
            print(f"⚠️ Could not send auto-unlock notification: {e}")
            
    except Exception as e:
        print(f"❌ ERROR in auto-unlock task: {e}")
        import traceback
        traceback.print_exc()


# ================= LOCK STATUS COMMAND =================
@app.on_message(filters.command("lockstatus") & filters.group)
async def lock_status_command(client, message: Message):
    """Show current lock status with detailed information"""
    
    chat_id = message.chat.id
    
    try:
        # Get current permissions from Telegram
        chat = await client.get_chat(chat_id)
        permissions = chat.permissions
        
        # Get active locks from our tracking
        active_locks = []
        lock_details_list = []
        
        if chat_id in chat_locks and chat_locks[chat_id]:
            for lock_type, lock_data in chat_locks[chat_id].items():
                active_locks.append(lock_type)
                
                # Format lock details
                applied_at = lock_data.get("applied_at", datetime.now(timezone.utc))
                applied_by = lock_data.get("applied_by_name", "Unknown")
                duration = lock_data.get("duration", "Permanent")
                expires = lock_data.get("expires")
                
                # Time since applied
                time_since = datetime.now(timezone.utc) - applied_at
                hours = int(time_since.total_seconds() // 3600)
                minutes = int((time_since.total_seconds() % 3600) // 60)
                
                # Time remaining if has expiry
                time_remaining = ""
                if expires:
                    remaining = expires - datetime.now(timezone.utc)
                    if remaining.total_seconds() > 0:
                        rem_hours = int(remaining.total_seconds() // 3600)
                        rem_minutes = int((remaining.total_seconds() % 3600) // 60)
                        time_remaining = f"\n   ⏳ Remaining: {rem_hours}h {rem_minutes}m"
                
                lock_details_list.append(
                    f"• **{lock_type.upper()}**\n"
                    f"   👤 By: {applied_by}\n"
                    f"   ⏰ Active: {hours}h {minutes}m\n"
                    f"   📅 Duration: {duration}{time_remaining}"
                )
        
        # Build beautiful status message
        status_text = f"""
{beautiful_header('info')}

🔒 **CHAT LOCK STATUS REPORT**

🏷️ **Chat:** {chat.title}
🆔 **Chat ID:** `{chat_id}`
👥 **Type:** {chat.type.value.title() if hasattr(chat.type, 'value') else str(chat.type).title()}
📊 **Active Locks:** {len(active_locks)} / 17

"""
        
        # Add lock details if any
        if lock_details_list:
            status_text += "📋 **ACTIVE LOCKS:**\n\n"
            status_text += "\n\n".join(lock_details_list)
            status_text += "\n\n"
        else:
            status_text += "✅ **NO ACTIVE LOCKS**\nThe chat is fully unlocked.\n\n"
        
        # Add current permissions status
        status_text += f"""
📊 **CURRENT PERMISSIONS STATUS:**

📝 **Text Messages:** {'✅ Allowed' if permissions.can_send_messages else '❌ Locked'}
🖼️ **Media Messages:** {'✅ Allowed' if permissions.can_send_media_messages else '❌ Locked'}
😀 **Stickers/GIFs:** {'✅ Allowed' if permissions.can_send_other_messages else '❌ Locked'}
📊 **Polls:** {'✅ Allowed' if permissions.can_send_polls else '❌ Locked'}
🔗 **URLs/Links:** {'✅ Allowed' if permissions.can_add_web_page_previews else '❌ Locked'}
👥 **Invite Users:** {'✅ Allowed' if permissions.can_invite_users else '❌ Locked'}
📌 **Pin Messages:** {'✅ Allowed' if permissions.can_pin_messages else '❌ Locked'}
ℹ️ **Change Info:** {'✅ Allowed' if permissions.can_change_info else '❌ Locked'}

"""
        
        # Add quick command reference
        status_text += f"""
💡 **QUICK COMMANDS:**
• `/lock [type] [duration]` - Apply new lock
• `/unlock [type]` - Remove existing lock
• `/lockstatus` - Refresh this view

🔧 **Common Locks:**
• `/lock text` - Disable text
• `/lock media` - Disable all media
• `/lock all` - Complete lockdown
• `/unlock all` - Remove all locks

📚 **Need Help?** Use `/lock` or `/unlock` alone for guide
"""
        
        await message.reply_text(status_text + beautiful_footer())
        
    except Exception as e:
        error_text = f"""
{beautiful_header('danger')}

❌ **STATUS CHECK FAILED**

**Error:** {str(e)[:80]}

**Possible Reasons:**
1. Bot not admin in this group
2. Network connectivity issue
3. Telegram API limitation

**Solutions:**
1. Make bot admin with full permissions
2. Wait and try again
3. Contact support if persists
"""
        await message.reply_text(error_text + beautiful_footer())
# ================= Group lock by Bot admin COMMAND =================
group_locks = {}  

LOCK_PERMISSIONS = {
    "all": ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_send_polls=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False
    ),
    "text": ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "media": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "stickers": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=False,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "polls": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=False,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "invites": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=False,
        can_pin_messages=True
    ),
    "pins": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=False
    ),
    "info": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "url": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=False,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "games": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=False,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "inline": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=False,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "voice": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "video": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "audio": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "documents": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "photos": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=False,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    ),
    "forward": ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_send_polls=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True
    )
}

UNLOCK_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_send_polls=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True
)

async def apply_group_lock_by_id(client, chat_id, lock_type="all", lock=True, duration=None):
    """Apply lock to group using chat ID"""
    try:
        if lock:
            perms = LOCK_PERMISSIONS.get(lock_type, LOCK_PERMISSIONS["all"])
        else:
            perms = UNLOCK_PERMISSIONS
        
        await client.set_chat_permissions(chat_id, perms)
        
        # Store lock info
        if lock:
            group_locks[chat_id] = {
                "type": lock_type,
                "applied_at": datetime.now(timezone.utc),
                "duration": duration,
                "expires": datetime.now(timezone.utc) + duration if duration else None
            }
            
            # Schedule auto-unlock if duration specified
            if duration:
                asyncio.create_task(auto_unlock_by_id(client, chat_id, duration))
        else:
            # Remove from locks if unlocking
            group_locks.pop(chat_id, None)
        
        return True
    except Exception as e:
        print(f"Error applying lock: {e}")
        return False

async def auto_unlock_by_id(client, chat_id, duration):
    """Auto-unlock after duration"""
    await asyncio.sleep(duration.total_seconds())
    
    try:
        await apply_group_lock_by_id(client, chat_id, lock=False)
        
        # Send unlock notification
        await client.send_message(
            chat_id,
            f"{beautiful_header('settings')}\n\n"
            f"🔓 **AUTO UNLOCKED**\n\n"
            f"⏰ Duration expired\n"
            f"🤖 By: Bot Admin System\n\n"
            f"All permissions have been restored."
            f"{beautiful_footer()}"
        )
        
    except Exception as e:
        print(f"Error in auto-unlock: {e}")

def parse_time_duration(time_str):
    """Parse time duration string to timedelta"""
    try:
        time_str = time_str.lower().strip()
        
        if time_str.endswith("m"):
            minutes = int(time_str[:-1])
            return timedelta(minutes=minutes)
        elif time_str.endswith("h"):
            hours = int(time_str[:-1])
            return timedelta(hours=hours)
        elif time_str.endswith("d"):
            days = int(time_str[:-1])
            return timedelta(days=days)
        elif time_str.endswith("w"):
            weeks = int(time_str[:-1])
            return timedelta(weeks=weeks)
        elif time_str.isdigit():
            return timedelta(minutes=int(time_str))
        else:
            return None
    except:
        return None


# ================= BOT ADMIN LOCK COMMANDS =================
@app.on_message(filters.private & filters.command(["glock", "gblock"]))
async def bot_admin_lock_command_checked(client, message: Message):
    """Bot admin lock command with already lock check"""
    
    # Check if user is bot admin
    if not is_bot_admin(message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Bot Admin Required**\n"
            "Only bot admins can use this command."
            f"{beautiful_footer()}"
        )
        return
    
    # Check command format
    if len(message.command) < 3:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "🔒 **BOT ADMIN LOCK SYSTEM**\n\n"
            "**Usage:** `/glock <chat_id> <lock_type> [duration] [silent] [force]`\n\n"
            "**Examples:**\n"
            "• `/glock -100123456789 all` - Lock everything\n"
            "• `/glock -100123456789 text 1h` - Lock text for 1 hour\n"
            "• `/glock -100123456789 media 30m silent` - Lock media silently\n"
            "• `/glock -100123456789 text force` - Force lock even if already locked\n\n"
            "**Lock Types (17 options):**\n"
            "`all, text, media, stickers, polls, invites, pins, info, url, games, inline, voice, video, audio, documents, photos, forward`\n\n"
            "**Durations:** m=minutes, h=hours, d=days, w=weeks\n"
            "**Options:** silent (no announcement), force (override)"
            f"{beautiful_footer()}"
        )
        return
    
    try:
        # Parse arguments
        chat_id = int(message.command[1])
        lock_type = message.command[2].lower()
        duration = None
        silent = False
        force = False
        
        # Parse duration if provided
        if len(message.command) >= 4:
            for arg in message.command[3:]:
                arg_lower = arg.lower()
                if arg_lower == "silent":
                    silent = True
                elif arg_lower == "force":
                    force = True
                elif not silent and not force:  # Try to parse as duration
                    duration = parse_time_duration(arg)
        
        # Validate lock type
        if lock_type not in LOCK_PERMISSIONS:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Invalid lock type:** `{lock_type}`\n\n"
                f"**Available types:**\n"
                f"`all`, `text`, `media`, `stickers`, `polls`, `invites`, `pins`, `info`, `url`, `games`, `inline`, `voice`, `video`, `audio`, `documents`, `photos`, `forward`"
                f"{beautiful_footer()}"
            )
            return
        
        # Get chat info
        try:
            chat = await client.get_chat(chat_id)
            chat_title = chat.title
            chat_type = chat.type
        except Exception as e:
            chat_title = f"Chat ID: {chat_id}"
            chat_type = "Unknown"
            print(f"⚠️ Could not fetch chat info: {e}")
        
        # Check if bot is admin in target chat
        bot_is_admin = await can_bot_restrict(client, chat_id)
        if not bot_is_admin:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Bot Not Admin**\n\n"
                f"I need admin permissions in that chat.\n"
                f"Chat: {chat_title}\n"
                f"ID: `{chat_id}`\n\n"
                f"Please make me admin with 'Change Chat Info' permission."
                f"{beautiful_footer()}"
            )
            return
        
        # Check if already locked (without force)
        if not force:
            already_locked = False
            lock_reason = ""
            
            # Check in group_locks tracking
            if chat_id in group_locks:
                already_locked = True
                existing_lock = group_locks[chat_id]
                lock_reason = f"Already locked ({existing_lock.get('type', 'unknown')}) in group_locks"
            
            # Check in chat_locks tracking
            elif chat_id in chat_locks and lock_type in chat_locks[chat_id]:
                already_locked = True
                lock_reason = f"Already locked ({lock_type}) in chat_locks"
            
            # Check actual Telegram permissions
            try:
                chat_info = await client.get_chat(chat_id)
                current_perms = chat_info.permissions
                
                # Check if specific lock is already applied
                if lock_type == "all":
                    # Check if all permissions are disabled
                    if not (current_perms.can_send_messages or 
                           current_perms.can_send_media_messages or
                           current_perms.can_send_other_messages or
                           current_perms.can_send_polls or
                           current_perms.can_invite_users or
                           current_perms.can_pin_messages or
                           current_perms.can_change_info or
                           current_perms.can_add_web_page_previews):
                        already_locked = True
                        lock_reason = "All permissions already disabled in Telegram"
                
                elif lock_type == "text" and not current_perms.can_send_messages:
                    already_locked = True
                    lock_reason = "Text messages already disabled"
                
                elif lock_type == "media" and not current_perms.can_send_media_messages:
                    already_locked = True
                    lock_reason = "Media already disabled"
                
                elif lock_type == "stickers" and not current_perms.can_send_other_messages:
                    already_locked = True
                    lock_reason = "Stickers/GIFs already disabled"
                
                elif lock_type == "polls" and not current_perms.can_send_polls:
                    already_locked = True
                    lock_reason = "Polls already disabled"
                
                elif lock_type == "invites" and not current_perms.can_invite_users:
                    already_locked = True
                    lock_reason = "Invites already disabled"
                
                elif lock_type == "pins" and not current_perms.can_pin_messages:
                    already_locked = True
                    lock_reason = "Pin messages already disabled"
                
                elif lock_type == "info" and not current_perms.can_change_info:
                    already_locked = True
                    lock_reason = "Change info already disabled"
                
                elif lock_type == "url" and not current_perms.can_add_web_page_previews:
                    already_locked = True
                    lock_reason = "URLs already disabled"
                    
            except Exception as e:
                print(f"⚠️ Could not check current permissions: {e}")
        
            # If already locked and not forced, show status
            if already_locked:
                status_text = f"""
{beautiful_header('info')}

ℹ️ **CHAT ALREADY LOCKED**

**Chat Info:**
🏷️ **Title:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
📢 **Type:** {chat_type}

**Current Status:**
🔒 **Lock Type:** {lock_type}
📝 **Reason:** {lock_reason}

**No action needed!**

💡 **Options:**
• Add `force` parameter to override
• Use `/gunlock {chat_id}` to unlock first
• Check status with `/lockstatus` in group
"""
                
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 FORCE LOCK", 
                            callback_data=f"force_lock:{chat_id}:{lock_type}:{duration.total_seconds() if duration else 0}:{int(silent)}"),
                        InlineKeyboardButton("🔓 UNLOCK FIRST", 
                            callback_data=f"unlock_first:{chat_id}")
                    ],
                    [
                        InlineKeyboardButton("📊 CHECK STATUS", 
                            callback_data=f"check_lock_status:{chat_id}"),
                        InlineKeyboardButton("❌ CANCEL", 
                            callback_data="cancel_lock")
                    ]
                ])
                
                await message.reply_text(
                    status_text + beautiful_footer(),
                    reply_markup=buttons
                )
                return
        
        # Apply lock
        success = await apply_group_lock_by_id_checked(
            client, chat_id, lock_type, lock=True, duration=duration
        )
        
        if not success:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Failed to apply lock**\n\n"
                f"Chat: {chat_title}\n"
                f"ID: `{chat_id}`\n"
                f"Error: Check bot permissions"
                f"{beautiful_footer()}"
            )
            return
        
        # Send confirmation to bot admin
        duration_text = f"for {duration}" if duration else "permanently"
        silent_text = " (Silent)" if silent else ""
        force_text = " (Forced)" if force else ""
        
        admin_msg = f"""
{beautiful_header('admin')}

✅ **LOCK APPLIED**{silent_text}{force_text}

**Chat Info:**
🏷️ **Title:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
📢 **Type:** {chat_type}

**Lock Details:**
🔒 **Type:** {lock_type}
⏰ **Duration:** {duration_text or 'Permanent'}

**Admin Info:**
👨‍💼 **By:** {message.from_user.mention}
🆔 **Admin ID:** `{message.from_user.id}`

**Status:** ✅ Successfully locked
"""
        
        await message.reply_text(admin_msg + beautiful_footer())
        
        # Send announcement to group (if not silent)
        if not silent:
            try:
                lock_icon = "🔒" if lock_type == "all" else "🔐"
                duration_info = f"\n⏰ **Duration:** {duration}" if duration else ""
                force_info = "\n⚡ **Note:** Forced lock applied" if force else ""
                
                group_msg = f"""
{beautiful_header('settings')}

{lock_icon} **GROUP LOCKED** (by Bot Admin)

🔒 **Type:** {lock_type.title()} Lock
{duration_info}{force_info}
🤖 **Action:** Bot Admin Command

📋 **Permissions changed for all members.**
"""
                
                await client.send_message(chat_id, group_msg + beautiful_footer())
            except Exception as e:
                print(f"Error sending group announcement: {e}")
        
    except ValueError:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Invalid Chat ID**\n"
            "Chat ID must be a number (e.g., -100123456789)"
            f"{beautiful_footer()}"
        )
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"❌ **Error:** {str(e)[:100]}"
            f"{beautiful_footer()}"
                )


    
# ================= IMPROVED BOT ADMIN UNLOCK COMMAND =================
@app.on_message(filters.private & filters.command(["gunblock", "bunblock"]))
async def bot_admin_unlock_command_checked(client, message: Message):
    """Bot admin unlock command with already unlock check"""
    
    # Check if user is bot admin
    if not is_bot_admin(message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Bot Admin Required**"
            f"{beautiful_footer()}"
        )
        return
    
    # Check command format
    if len(message.command) < 2:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "🔓 **BOT ADMIN UNLOCK SYSTEM**\n\n"
            "**Usage:** `/gunlock <chat_id> [silent] [force]`\n\n"
            "**Examples:**\n"
            "• `/gunlock -100123456789` - Unlock everything\n"
            "• `/gunlock -100123456789 silent` - Unlock silently\n"
            "• `/gunlock -100123456789 force` - Force unlock\n\n"
            "**Options:** silent (no announcement), force (override)"
            f"{beautiful_footer()}"
        )
        return
    
    try:
        # Parse arguments
        chat_id = int(message.command[1])
        silent = "silent" in [arg.lower() for arg in message.command]
        force = "force" in [arg.lower() for arg in message.command]
        
        # Get chat info
        try:
            chat = await client.get_chat(chat_id)
            chat_title = chat.title
            chat_type = chat.type
        except Exception as e:
            chat_title = f"Chat ID: {chat_id}"
            chat_type = "Unknown"
            print(f"⚠️ Could not fetch chat info: {e}")
        
        # Check if bot is admin in target chat
        bot_is_admin = await can_bot_restrict(client, chat_id)
        if not bot_is_admin:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Bot Not Admin**\n\n"
                f"I need admin permissions in that chat.\n"
                f"Chat: {chat_title}\n"
                f"ID: `{chat_id}`\n\n"
                f"Please make me admin with 'Change Chat Info' permission."
                f"{beautiful_footer()}"
            )
            return
        
        # Check if already unlocked (without force)
        if not force:
            already_unlocked = False
            unlock_reason = ""
            
            # Check tracking
            if chat_id not in group_locks and (chat_id not in chat_locks or not chat_locks[chat_id]):
                already_unlocked = True
                unlock_reason = "Not found in lock tracking"
            
            # Check actual Telegram permissions
            try:
                chat_info = await client.get_chat(chat_id)
                current_perms = chat_info.permissions
                
                # Check if all permissions are enabled (default state)
                if (current_perms.can_send_messages and
                    current_perms.can_send_media_messages and
                    current_perms.can_send_other_messages and
                    current_perms.can_send_polls and
                    current_perms.can_invite_users and
                    current_perms.can_pin_messages and
                    current_perms.can_change_info and
                    current_perms.can_add_web_page_previews):
                    already_unlocked = True
                    unlock_reason = "All permissions already enabled in Telegram"
                    
            except Exception as e:
                print(f"⚠️ Could not check current permissions: {e}")
        
            # If already unlocked and not forced, show status
            if already_unlocked:
                status_text = f"""
{beautiful_header('info')}

ℹ️ **CHAT ALREADY UNLOCKED**

**Chat Info:**
🏷️ **Title:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
📢 **Type:** {chat_type}

**Current Status:**
🔓 **State:** Already unlocked
📝 **Reason:** {unlock_reason}

**No action needed!**

💡 **Options:**
• Add `force` parameter to override
• Use `/glock {chat_id} text` to lock first
• Check status with `/lockstatus` in group
"""
                
                buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 FORCE UNLOCK", 
                            callback_data=f"force_unlock_checked:{chat_id}:{int(silent)}"),
                        InlineKeyboardButton("🔒 LOCK FIRST", 
                            callback_data=f"lock_first:{chat_id}")
                    ],
                    [
                        InlineKeyboardButton("📊 CHECK STATUS", 
                            callback_data=f"check_unlock_status:{chat_id}"),
                        InlineKeyboardButton("❌ CANCEL", 
                            callback_data="cancel_unlock_checked")
                    ]
                ])
                
                await message.reply_text(
                    status_text + beautiful_footer(),
                    reply_markup=buttons
                )
                return
        
        # Check current lock status
        current_lock = group_locks.get(chat_id)
        
        # Apply unlock
        success = await apply_group_lock_by_id(client, chat_id, lock=False)
        
        if not success:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Failed to unlock**\n\n"
                f"Chat: {chat_title}\n"
                f"ID: `{chat_id}`\n"
                f"Error: Check bot permissions"
                f"{beautiful_footer()}"
            )
            return
        
        # Send confirmation to bot admin
        silent_text = " (Silent)" if silent else ""
        force_text = " (Forced)" if force else ""
        
        admin_msg = f"""
{beautiful_header('admin')}

✅ **UNLOCK APPLIED**{silent_text}{force_text}

**Chat Info:**
🏷️ **Title:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
📢 **Type:** {chat_type}

**Previous Lock:**
🔒 **Type:** {current_lock['type'] if current_lock else 'None'}
⏰ **Applied At:** {current_lock.get('applied_at', 'Unknown') if current_lock else 'N/A'}

**Admin Info:**
👨‍💼 **By:** {message.from_user.mention}
🆔 **Admin ID:** `{message.from_user.id}`

**Status:** ✅ Successfully unlocked
"""
        
        await message.reply_text(admin_msg + beautiful_footer())
        
        # Send announcement to group (if not silent)
        if not silent:
            try:
                force_info = "\n⚡ **Note:** Forced unlock applied" if force else ""
                
                group_msg = f"""
{beautiful_header('settings')}

🔓 **GROUP UNLOCKED** (by Bot Admin)

All permissions have been restored.
🤖 **Action:** Bot Admin Command{force_info}

📋 **Members can now send messages normally.**

👨‍💼 **By:** {message.from_user.mention}
"""
                
                await client.send_message(chat_id, group_msg + beautiful_footer())
            except Exception as e:
                print(f"Error sending group announcement: {e}")
        
    except ValueError:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Invalid Chat ID**"
            f"{beautiful_footer()}"
        )
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"❌ **Error:** {str(e)[:100]}"
            f"{beautiful_footer()}"
                )

async def apply_group_lock_by_id_checked(client, chat_id, lock_type="all", lock=True, duration=None):
    """Apply lock to group with checking"""
    try:
        if lock:
            perms = LOCK_PERMISSIONS.get(lock_type, LOCK_PERMISSIONS["all"])
        else:
            perms = UNLOCK_PERMISSIONS
        
        await client.set_chat_permissions(chat_id, perms)
        
        # Store lock info
        if lock:
            group_locks[chat_id] = {
                "type": lock_type,
                "applied_at": datetime.now(timezone.utc),
                "duration": duration,
                "expires": datetime.now(timezone.utc) + duration if duration else None,
                "applied_by": "Bot Admin"
            }
            
            # Also store in chat_locks for consistency
            if chat_id not in chat_locks:
                chat_locks[chat_id] = {}
            chat_locks[chat_id][lock_type] = {
                "applied_at": datetime.now(timezone.utc),
                "duration": duration,
                "applied_by": "Bot Admin"
            }
            
            # Schedule auto-unlock if duration specified
            if duration:
                asyncio.create_task(auto_unlock_by_id(client, chat_id, duration))
        else:
            # Remove from locks if unlocking
            group_locks.pop(chat_id, None)
            
            # Also remove from chat_locks
            if chat_id in chat_locks:
                chat_locks[chat_id] = {}
        
        return True
    except Exception as e:
        print(f"Error applying lock: {e}")
        return False

# Callback handlers for buttons
@app.on_callback_query(filters.regex("^force_lock:"))
async def handle_force_lock_callback(client, callback_query):
    """Handle force lock callback"""
    
    data = callback_query.data
    parts = data.split(":")
    
    if len(parts) < 5:
        await callback_query.answer("Invalid data!", show_alert=True)
        return
    
    chat_id = int(parts[1])
    lock_type = parts[2]
    duration_seconds = int(parts[3])
    silent = bool(int(parts[4]))
    
    await callback_query.answer("Applying force lock...")
    
    try:
        duration = timedelta(seconds=duration_seconds) if duration_seconds > 0 else None
        
        success = await apply_group_lock_by_id_checked(
            client, chat_id, lock_type, lock=True, duration=duration
        )
        
        if success:
            await callback_query.message.edit_text(
                f"✅ **Force Lock Applied**\n\n"
                f"**Chat ID:** `{chat_id}`\n"
                f"**Lock Type:** {lock_type}\n"
                f"**Duration:** {duration if duration else 'Permanent'}\n\n"
                f"Force lock has been applied successfully."
            )
        else:
            await callback_query.message.edit_text(
                f"❌ **Force Lock Failed**\n\n"
                f"Could not lock chat `{chat_id}`"
            )
            
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ **Error:** {str(e)[:100]}"
        )

@app.on_callback_query(filters.regex("^force_unlock_checked:"))
async def handle_force_unlock_checked_callback(client, callback_query):
    """Handle force unlock callback"""
    
    data = callback_query.data
    parts = data.split(":")
    
    if len(parts) < 3:
        await callback_query.answer("Invalid data!", show_alert=True)
        return
    
    chat_id = int(parts[1])
    silent = bool(int(parts[2]))
    
    await callback_query.answer("Applying force unlock...")
    
    try:
        success = await apply_group_lock_by_id(client, chat_id, lock=False)
        
        if success:
            await callback_query.message.edit_text(
                f"✅ **Force Unlock Applied**\n\n"
                f"**Chat ID:** `{chat_id}`\n\n"
                f"Force unlock has been applied successfully."
            )
        else:
            await callback_query.message.edit_text(
                f"❌ **Force Unlock Failed**\n\n"
                f"Could not unlock chat `{chat_id}`"
            )
            
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ **Error:** {str(e)[:100]}"
        )

@app.on_callback_query(filters.regex("^check_lock_status:|^check_unlock_status:"))
async def handle_check_status_callback(client, callback_query):
    """Check chat lock status"""
    
    chat_id = int(callback_query.data.split(":")[1])
    
    await callback_query.answer("Checking status...")
    
    try:
        chat = await client.get_chat(chat_id)
        perms = chat.permissions
        
        # Check tracking
        in_group_locks = chat_id in group_locks
        in_chat_locks = chat_id in chat_locks and chat_locks[chat_id]
        
        status_text = f"""
🔍 **CHAT LOCK STATUS**

**Basic Info:**
• **Title:** {chat.title}
• **ID:** `{chat_id}`
• **Type:** {chat.type.value if hasattr(chat.type, 'value') else str(chat.type)}

**Current Permissions:**
• 📝 Text: {'✅' if perms.can_send_messages else '❌'}
• 🖼️ Media: {'✅' if perms.can_send_media_messages else '❌'}
• 😀 Stickers: {'✅' if perms.can_send_other_messages else '❌'}
• 📊 Polls: {'✅' if perms.can_send_polls else '❌'}
• 🔗 URLs: {'✅' if perms.can_add_web_page_previews else '❌'}
• 👥 Invites: {'✅' if perms.can_invite_users else '❌'}
• 📌 Pin: {'✅' if perms.can_pin_messages else '❌'}
• ℹ️ Change Info: {'✅' if perms.can_change_info else '❌'}

**Lock Tracking:**
• group_locks: {'✅ Found' if in_group_locks else '❌ Not found'}
• chat_locks: {'✅ Found' if in_chat_locks else '❌ Not found'}

**Status:** {'🔒 LOCKED' if in_group_locks or in_chat_locks else '🔓 UNLOCKED'}
"""
        
        await callback_query.message.edit_text(
            status_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="back_to_main")]
            ])
        )
        
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ **Error checking status:**\n`{str(e)[:100]}`"
        )


# ================= ADD TO YOUR START_BACKGROUND_TASKS =================
# Add this function to your background tasks
async def cleanup_abuse_cache_task():
    """Clean old abuse cache entries"""
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            keys_to_delete = []
            
            for key in list(user_warnings_cache.keys()):
                if key.startswith("abuse:"):
                    incidents = user_warnings_cache[key]
                    # Keep only incidents from last 24 hours
                    recent_incidents = [
                        incident for incident in incidents
                        if (current_time - datetime.fromisoformat(incident.get("timestamp", "2000-01-01"))).seconds < 86400
                    ]
                    
                    if recent_incidents:
                        user_warnings_cache[key] = recent_incidents
                    else:
                        keys_to_delete.append(key)
            
            # Delete empty cache entries
            for key in keys_to_delete:
                del user_warnings_cache[key]
            
            print(f"Cleaned abuse cache: removed {len(keys_to_delete)} entries")
            
        except Exception as e:
            print(f"Error cleaning abuse cache: {e}")
        
        await asyncio.sleep(3600)  # Run every hour




# ================== UI CARDS ==================
START_INTRO = """
╔═══════════════════╗
 🌸 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗧𝗔𝗚𝗚𝗘𝗥 🌸
╚═══════════════════╝

✨ **Welcome {user}**

🚀 Fast • Safe • Premium  
👑 Admin-only tagging system

━━━━━━━━━━━━━━━━━━━
📌 Commands:
/tagall – Tag all members  
/tagadmin – Tag admins  
/stop – Stop tagging
"""

WELCOME_USER_CARD = """
╔═══════════════════╗
   🎉 𝗡𝗘𝗪 𝗠𝗘𝗠𝗕𝗘𝗥 🎉
╚═══════════════════╝

👋 **Welcome:** {mention}

━━━━━━━━━━━━━━━━━━━
🆔 **User ID:** `{user_id}`
👤 **Username:** {username}
🤖 **Account:** {account}
🕒 **Joined:** {time}

━━━━━━━━━━━━━━━━━━━
💎 **Group:** {group}

📌 Please follow group rules  
⚡ Enjoy your stay!
"""

START_CARD = """
╔═══════════════════╗
   💎 𝗣𝗥𝗘𝗠𝗜𝗨𝗠 𝗧𝗔𝗚𝗚𝗘𝗥
╚═══════════════════╝

🚀 **Tagging Started**
━━━━━━━━━━━━━━━━━━━
👑 **Admin:** {admin}
🎯 **Target:** {target}

🛑 Use Stop button to cancel
"""

DONE_CARD = """
╔═══════════════════╗
   ✅ 𝗧𝗔𝗦𝗞 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗
╚═══════════════════╝

👥 **Total Tagged:** {total}
👑 **By:** {admin}

💎 Premium Tagger
"""

STOP_CARD = """
╔═══════════════════╗
   🛑 𝗧𝗔𝗚𝗚𝗜𝗡𝗚 𝗦𝗧𝗢𝗣𝗣𝗘𝗗
╚═══════════════════╝
⚠️ Process cancelled by admin
"""


PURGE_DONE_CARD = """
╔═══════════════════╗
   🧹 𝗣𝗨𝗥𝗚𝗘 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘𝗗
╚═══════════════════╝

👑 **By:** {mention}
🆔 **User ID:** `{user_id}`
🛡 **Role:** {role}

━━━━━━━━━━━━━━━━━━━
🗑 **Deleted:** `{count}`
💬 **Chat:** {chat}
🕒 **Time:** {time}

💎 Premium Moderation
"""


PURGE_FAIL_CARD = """
╔═══════════════════╗
   ❌ 𝗣𝗨𝗥𝗚𝗘 𝗙𝗔𝗜𝗟𝗘𝗗
╚═══════════════════╝

👑 **Requested By:** {mention}
🆔 **User ID:** `{user_id}`
🛡 **Role:** {role}

━━━━━━━━━━━━━━━━━━━
⚠️ **Deleted:** `{deleted}`
🚫 **Failed:** `{failed}`

📌 **Reason:**
{reason}

💡 Tip: Check bot admin permissions
"""

PURGE_DONE_CARD = """
╔═══════════════════╗
   🧹 𝗕𝗨𝗟𝗞 𝗣𝗨𝗥𝗚𝗘 𝗗𝗢𝗡𝗘
╚═══════════════════╝

👑 **By:** {mention}
🆔 **User ID:** `{user_id}`
🛡 **Role:** {role}

━━━━━━━━━━━━━━━━━━━
🗑 **Deleted:** `{count}`
💬 **Chat:** {chat}
🕒 **Time:** {time}

💎 Premium Moderation
"""

PURGE_FAIL_CARD = """
╔═══════════════════╗
   ❌ 𝗕𝗨𝗟𝗞 𝗣𝗨𝗥𝗚𝗘 𝗙𝗔𝗜𝗟𝗘𝗗
╚═══════════════════╝

👑 **By:** {mention}
🆔 **User ID:** `{user_id}`
🛡 **Role:** {role}

━━━━━━━━━━━━━━━━━━━
⚠️ **Deleted:** `{deleted}`
🚫 **Failed:** `{failed}`

📌 **Reason:**
{reason}
"""


PRIVATE_ID_CARD = """
╔═══════════════════╗
   🆔 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗜𝗗
╚═══════════════════╝

👤 **Name:** {name}
🆔 **User ID:** `{user_id}`
👤 **Username:** {username}
🤖 **Account:** {account}

━━━━━━━━━━━━━━━━━━━
🆔 **Chat ID:** `{chat_id}`
💬 **Chat Type:** Private
📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}

"""

GROUP_ID_CARD = """
╔═══════════════════╗
   🆔 𝗚𝗥𝗢𝗨𝗣 𝗜𝗗
╚═══════════════════╝

👤 **User Info**
━━━━━━━━━━━━━━━━━━━
👤 **Name:** {name}
🆔 **User ID:** `{user_id}`
👤 **Username:** {username}
🤖 **Account:** {account}
🛡 **Role:** {role}

💬 **Group Info**
━━━━━━━━━━━━━━━━━━━
🆔 **Chat ID:** `{chat_id}`
💬 **Group Name:** {chat_name}
📢 **Chat Type:** {chat_type}

📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}

"""

CHANNEL_ID_CARD = """
╔═══════════════════╗
   📢 𝗖𝗛𝗔𝗡𝗡𝗘𝗟 𝗜𝗗
╚═══════════════════╝

📢 **Channel Info**
━━━━━━━━━━━━━━━━━━━
📛 **Name:** {name}
🆔 **Channel ID:** `{chat_id}`
👤 **Username:** {username}
📢 **Type:** Channel

━━━━━━━━━━━━━━━━━━━
📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}
"""

CHAT_ID_CARD = """
╔═══════════════════╗
   🆔 𝗖𝗛𝗔𝗧 𝗜𝗗
╚═══════════════════╝

💬 **Chat Info**
━━━━━━━━━━━━━━━━━━━
📛 **Name:** {name}
🆔 **Chat ID:** `{chat_id}`
📢 **Type:** {chat_type}

━━━━━━━━━━━━━━━━━━━
📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}
"""

MY_ID_CARD_PRIVATE = """
╔═══════════════════╗
   🆔 𝗠𝗬 𝗜𝗗 (𝗣𝗥𝗜𝗩𝗔𝗧𝗘)
╚═══════════════════╝

👤 **Name:** {name}
🆔 **User ID:** `{user_id}`
👤 **Username:** {username}
🤖 **Account:** {account}

━━━━━━━━━━━━━━━━━━━
💬 **Chat Type:** Private
📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}
"""

MY_ID_CARD_GROUP = """
╔═══════════════════╗
   🆔 𝗠𝗬 𝗜𝗗 (𝗚𝗥𝗢𝗨𝗣)
╚═══════════════════╝

👤 **User Info**
━━━━━━━━━━━━━━━━━━━
👤 **Name:** {name}
🆔 **User ID:** `{user_id}`
👤 **Username:** {username}
🤖 **Account:** {account}
🛡 **Role:** {role}

💬 **Group Info**
━━━━━━━━━━━━━━━━━━━
🆔 **Chat ID:** `{chat_id}`
💬 **Group Name:** {chat_name}
📢 **Chat Type:** {chat_type}

📩 **Message ID:** `{message_id}`
🕒 **Time:** {time}
"""

ADMIN_ABUSE_CARD = """
╔═══════════════════╗
   ⚠️ 𝗔𝗗𝗠𝗜𝗡 𝗡𝗢𝗧𝗜𝗖𝗘
╚═══════════════════╝

👤 **Admin:** {admin}
🛡 **Role:** {role}

━━━━━━━━━━━━━━━━━━━
🚫 **Abusive message removed**
📌 Discipline rules apply to **everyone**

🆔 **User ID:** `{user_id}`
🆔 **Chat ID:** `{chat_id}`
🕒 **Time:** {time}

❗ Please maintain professional behavior
"""

def buttons():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🛑 Stop", callback_data="stop_tag"),
            InlineKeyboardButton("👑 Tag Admins", callback_data="tag_admin")
        ]]
    )

# ================== SEND TAG MESSAGES ==================
async def send_reply_tag(client, chat_id, reply_id, users):
    text = (
        "╭──────── ✨ ────────╮\n"
        "   💌 𝗠𝗘𝗠𝗕𝗘𝗥 𝗧𝗔𝗚 💌\n"
        "╰──────── ✨ ────────╯\n\n"
    )

    for u in users:
        text += premium_tag(u) + "   "

    text += "\n\n━━━━━━━━━━━━━━━━━━\n⚡ Please check message above"

    await client.send_message(
        chat_id,
        text,
        reply_to_message_id=reply_id,
        disable_web_page_preview=True
    )

async def send_normal_tag(client, chat_id, users):
    text = (
        "╭──────── ✨ ────────╮\n"
        "   ✨ 𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 ✨\n"
        "╰──────── ✨ ────────╯\n\n"
    )
    
    for u in users:
        text += premium_tag(u) + "   "

    text += "\n\n━━━━━━━━━━━━━━━━━━\n⚡ Please check message above"
    
    await client.send_message(
        chat_id,
        text,
        disable_web_page_preview=True
    )


def is_on_cooldown(user_id):
    cur.execute("SELECT last_used FROM cooldown WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        return False
    return time.time() - row[0] < COOLDOWN

def update_cooldown(user_id):
    cur.execute(
        "REPLACE INTO cooldown VALUES (?,?)",
        (user_id, int(time.time()))
    )
    conn.commit()


async def can_purge(client, chat_id, user_id):
    if user_id in INITIAL_ADMINS:
        return True
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except:
        return False


async def get_user_role(client, chat_id, user_id):
    if user_id in INITIAL_ADMINS:
        return "Bot Admin 💎"
    try:
        m = await client.get_chat_member(chat_id, user_id)
        if m.status == ChatMemberStatus.OWNER:
            return "Group Owner 👑"
        if m.status == ChatMemberStatus.ADMINISTRATOR:
            return "Group Admin 🛡"
    except:
        pass
    return "User"


def purge_fail_reason(deleted, failed):
    if deleted == 0:
        return "Bot does not have permission to delete messages."
    if failed > 0:
        return "Some messages are too old or restricted by Telegram."
    return "Unknown error."


async def notify_admins(client, chat_id):
    text = "🚨 **Admin Notification** 🚨\n\n"

    async for m in client.get_chat_members(
        chat_id,
        filter=ChatMembersFilter.ADMINISTRATORS
    ):
        if not m.user.is_bot:
            text += f"[{m.user.first_name}](tg://user?id={m.user.id})  "

    return text

async def get_target_user(client, message: Message):
    """
    Returns (user_id, user_object)
    Priority:
    1. Reply
    2. Command argument (@username / user_id)
    3. Fallback: sender
    """
    # Reply se
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user

    # Command argument se
    if len(message.command) > 1:
        arg = message.command[1]
        try:
            if arg.startswith("@"):
                user = await client.get_users(arg)
            else:
                user = await client.get_users(int(arg))
            return user.id, user
        except:
            return None, None

    # Fallback: sender
    user = message.from_user
    return user.id, user
    
# ================== MENTION (NO VISIBLE LINK) ==================
def mention(user):
    return f"[{user.first_name}](tg://user?id={user.id})"

def premium_tag(user):
    emojis = ["🦋","🔥","✨","💖","👑","⚡"]
    return f"{emojis[user.id % len(emojis)]} {mention(user)}"



async def is_group_admin(client, chat_id, user_id):
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except:
        return False


def is_bot_admin(user_id: int) -> bool:
    return user_id in INITIAL_ADMINS

async def get_all_admins(client, chat_id):
    """
    Returns: dict {user_id: user_object}
    Includes:
    - Group Owner
    - Group Administrators
    - Bot Admins
    """
    admins = {}

    # ===== GROUP OWNER + ADMINS =====
    async for m in client.get_chat_members(
        chat_id,
        filter=ChatMembersFilter.ADMINISTRATORS
    ):
        if m.user and not m.user.is_bot:
            admins[m.user.id] = m.user

    # ===== BOT ADMINS =====
    for admin_id in INITIAL_ADMINS:
        if admin_id in admins:
            continue
        try:
            user = await client.get_users(admin_id)
            if not user.is_bot:
                admins[user.id] = user
        except:
            pass

    return admins

async def is_any_admin(client, chat_id, user_id):
    """
    Returns True if user is:
    - Group Owner
    - Group Admin
    - Bot Admin
    """
    # Bot admin
    if user_id in INITIAL_ADMINS:
        return True

    # Group admin / owner
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        )
    except:
        return False

@app.on_chat_member_updated()
async def welcome_with_userdata(client, update):

    if not update.old_chat_member or not update.new_chat_member:
        return

    if (
        update.old_chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]
        and update.new_chat_member.status == ChatMemberStatus.MEMBER
    ):
        user = update.new_chat_member.user
        chat = update.chat

        username = f"@{user.username}" if user.username else "Not set"
        account = "Bot 🤖" if user.is_bot else "User 👤"
        join_time = datetime.now().strftime("%d %b %Y • %I:%M %p")

        text = WELCOME_USER_CARD.format(
            mention=mention(user),
            user_id=user.id,
            username=username,
            account=account,
            time=join_time,
            group=chat.title
        )

        msg = await client.send_message(
            chat.id,
            text,
            disable_web_page_preview=True
        )

        # OPTIONAL: auto delete welcome after 2 minutes
        # await asyncio.sleep(120)
        # await msg.delete()

 
# ================== TAG ALL ==================
# ================== TAG ALL ==================
@app.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message):

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_any_admin(client, chat_id, user_id):
        return await message.reply("❌ **Only admin can use this command**")

    if is_on_cooldown(user_id):
        return await message.reply("⏳ **Cooldown active, try later**")

    update_cooldown(user_id)
    STOP_TAG.discard(chat_id)

    start_msg = await message.reply(
        START_CARD.format(
            admin=message.from_user.mention,
            target="All Members"
        ),
        reply_markup=buttons()
    )

    members = []
    async for m in client.get_chat_members(chat_id):
        if not m.user.is_bot:
            members.append(m.user)

    batch = []

    for user in members:
        if chat_id in STOP_TAG:
            await start_msg.edit(STOP_CARD)
            return

        batch.append(user)

        if len(batch) == TAG_LIMIT:
            if message.reply_to_message:
                await send_reply_tag(client, chat_id, message.reply_to_message.id, batch)
            else:
                await send_normal_tag(client, chat_id, batch)

            batch.clear()
            await asyncio.sleep(DELAY)

    if batch:
        if message.reply_to_message:
            await send_reply_tag(client, chat_id, message.reply_to_message.id, batch)
        else:
            await send_normal_tag(client, chat_id, batch)

    await start_msg.edit(
        DONE_CARD.format(
            total=len(members),
            admin=message.from_user.mention
        )
    )

# ================== TAG ADMINS ==================
@app.on_message(filters.command("tagadmin") & filters.group)
async def tag_admins(client, message: Message):
    text = "👑 **𝗔𝗗𝗠𝗜𝗡 𝗧𝗔𝗚** 👑\n\n"
    async for m in client.get_chat_members(message.chat.id, filter=ChatMembersFilter.ADMINISTRATORS):
        text += premium_tag(m.user) + "\n"
    await message.reply(text, disable_web_page_preview=True)

@app.on_message(filters.command("purge") & filters.group)
async def purge_cmd(client, message: Message):

    if not message.reply_to_message:
        return await message.reply("⚠️ **Reply to a message to purge**")

    user_id = message.from_user.id
    chat_id = message.chat.id

    if not (is_bot_admin(user_id) or await is_group_admin(client, chat_id, user_id)):
        return await message.reply("❌ **Admin only command**")

    start = message.reply_to_message.id
    end = message.id

    deleted = 0
    failed = 0

    for msg_id in range(start, end + 1):
        try:
            await client.delete_messages(chat_id, msg_id)
            deleted += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    await message.reply(
        PURGE_DONE_CARD.format(
            mention=mention(message.from_user),
            user_id=user_id,
            role=await get_user_role(client, chat_id, user_id),
            count=deleted,
            chat=message.chat.title,
            time=datetime.now().strftime("%d %b %Y • %I:%M %p")
        ),
        disable_web_page_preview=True
    )


@app.on_message(filters.command("purgeall") & filters.group)
async def purgeall_cmd(client, message: Message):

    silent = "-s" in message.command
    chat_id = message.chat.id
    user_id = message.from_user.id

    # ================= PERMISSION =================
    if not (is_bot_admin(user_id) or await is_group_admin(client, chat_id, user_id)):
        if not silent:
            await message.reply("❌ **Only admin can use this command**")
        return

    # ================= ARGUMENT =================
    if len(message.command) < 2:
        if not silent:
            await message.reply("⚠️ **Usage:** `/purgeall 50`")
        return

    try:
        limit = int(message.command[1])
        if limit <= 0:
            raise ValueError
    except:
        if not silent:
            await message.reply("❌ **Invalid number**")
        return

    # ================= DELETE =================
    deleted = 0
    failed = 0

    async for msg in client.get_chat_history(
        chat_id,
        limit=limit + 1   # include command message
    ):
        try:
            await msg.delete()
            deleted += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    if silent:
        return

    # ================= RESULT =================
    role = await get_user_role(client, chat_id, user_id)

    if failed > 0:
        await message.reply(
            PURGE_FAIL_CARD.format(
                mention=mention(message.from_user),
                user_id=user_id,
                role=role,
                deleted=deleted,
                failed=failed,
                reason=purge_fail_reason(deleted, failed)
            ),
            disable_web_page_preview=True
        )
    else:
        await message.reply(
            PURGE_DONE_CARD.format(
                mention=mention(message.from_user),
                user_id=user_id,
                role=role,
                count=deleted,
                chat=message.chat.title,
                time=datetime.now().strftime("%d %b %Y • %I:%M %p")
            ),
            disable_web_page_preview=True
        )


@app.on_message(filters.command("id"))
async def id_command(client, message: Message):

    chat = message.chat
    time_now = datetime.now().strftime("%d %b %Y • %I:%M %p")

    # ================= CHANNEL =================
    if chat.type == "channel":
        name = chat.title or "Unnamed Channel"
        username = f"@{chat.username}" if chat.username else "Not set"

        text = CHANNEL_ID_CARD.format(
            name=name,
            chat_id=chat.id,
            username=username,
            message_id=message.id,
            time=time_now
        )

        return await message.reply(
            text,
            disable_web_page_preview=True
        )

    # ================= PRIVATE / GROUP =================
    user_id, user = await get_target_user(client, message)
    if not user:
        return await message.reply("❌ Unable to fetch user")

    username = f"@{user.username}" if user.username else "Not set"
    account = "Bot 🤖" if user.is_bot else "User 👤"

    # ===== PRIVATE CHAT =====
    if chat.type == "private":
        text = PRIVATE_ID_CARD.format(
            name=user.first_name,
            user_id=user_id,
            username=username,
            account=account,
            chat_id=chat.id,
            message_id=message.id,
            time=time_now
        )

        return await message.reply(
            text,
            disable_web_page_preview=True
        )

    # ===== GROUP / SUPERGROUP =====
    role = "User"
    try:
        m = await client.get_chat_member(chat.id, user_id)
        if m.status == ChatMemberStatus.OWNER:
            role = "Group Owner 👑"
        elif m.status == ChatMemberStatus.ADMINISTRATOR:
            role = "Group Admin 🛡"
    except:
        pass

    text = GROUP_ID_CARD.format(
        name=user.first_name,
        user_id=user_id,
        username=username,
        account=account,
        role=role,
        chat_id=chat.id,
        chat_name=chat.title,
        chat_type=chat.type,
        message_id=message.id,
        time=time_now
    )

    await message.reply(
        text,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("chatid"))
async def chat_id_command(client, message: Message):

    chat = message.chat
    time_now = datetime.now().strftime("%d %b %Y • %I:%M %p")

    # Detect name safely
    if chat.type == "private":
        name = message.from_user.first_name
    else:
        name = chat.title or "Unnamed Chat"

    text = CHAT_ID_CARD.format(
        name=name,
        chat_id=chat.id,
        chat_type=chat.type,
        message_id=message.id,
        time=time_now
    )

    await message.reply(
        text,
        disable_web_page_preview=True
    )

@app.on_message(filters.command("myid"))
async def myid_command(client, message: Message):

    user = message.from_user
    chat = message.chat
    time_now = datetime.now().strftime("%d %b %Y • %I:%M %p")

    username = f"@{user.username}" if user.username else "Not set"
    account = "Bot 🤖" if user.is_bot else "User 👤"

    # ================= PRIVATE CHAT =================
    if chat.type == "private":
        text = MY_ID_CARD_PRIVATE.format(
            name=user.first_name,
            user_id=user.id,
            username=username,
            account=account,
            message_id=message.id,
            time=time_now
        )

        return await message.reply(
            text,
            disable_web_page_preview=True
        )

    # ================= GROUP / SUPERGROUP =================
    role = "User"
    try:
        m = await client.get_chat_member(chat.id, user.id)
        if m.status == ChatMemberStatus.OWNER:
            role = "Group Owner 👑"
        elif m.status == ChatMemberStatus.ADMINISTRATOR:
            role = "Group Admin 🛡"
    except:
        pass

    text = MY_ID_CARD_GROUP.format(
        name=user.first_name,
        user_id=user.id,
        username=username,
        account=account,
        role=role,
        chat_id=chat.id,
        chat_name=chat.title,
        chat_type=chat.type,
        message_id=message.id,
        time=time_now
    )

    await message.reply(
        text,
        disable_web_page_preview=True
    )
    

ADMIN_KEYWORDS = [
    "@admin",
    "@admins"
    
]



MAX_MENTIONS = 5

async def get_rotating_admin_mentions(client, chat_id, cur, conn):
    # 1️⃣ Group admins list
    admins = []
    async for m in client.get_chat_members(
        chat_id,
        filter=ChatMembersFilter.ADMINISTRATORS
    ):
        if not m.user.is_bot:
            admins.append(m.user)

    if not admins:
        return []

    total = len(admins)

    # 2️⃣ Last index load
    cur.execute(
        "SELECT last_index FROM notify_state WHERE chat_id=?",
        (chat_id,)
    )
    row = cur.fetchone()
    start = row[0] if row else 0

    # 3️⃣ Rotation batch
    batch = []
    for i in range(MAX_MENTIONS):
        idx = (start + i) % total
        batch.append(admins[idx].mention)

    # 4️⃣ Save next index
    next_index = (start + MAX_MENTIONS) % total
    cur.execute(
        "INSERT OR REPLACE INTO notify_state (chat_id, last_index) VALUES (?, ?)",
        (chat_id, next_index)
    )
    conn.commit()

    return batch


def contains_admin_keyword(text: str) -> str | None:
    if not text:
        return None

    text_low = text.lower()

    # 1️⃣ Direct mention check (best)
    for kw in ADMIN_KEYWORDS:
        if kw.startswith("@") and kw in text_low:
            return kw

    # 2️⃣ Word-based check (safe)
    words = re.findall(r"[a-zA-Z@]+", text_low)
    for kw in ADMIN_KEYWORDS:
        if kw in words:
            return kw

    return None


        
@app.on_message(filters.group & (filters.text | filters.caption), group=2)
async def admin_keyword_notify_even_if_group_muted(client, message):

    if message.from_user.is_bot:
        return

    text = message.text or message.caption
    if not text:
        return

    matched = contains_admin_keyword(text)
    if not matched:
        return

    # Sender agar admin hai to skip
    try:
        member = await client.get_chat_member(
            message.chat.id,
            message.from_user.id
        )
        if member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER
        ):
            return
    except:
        pass

    # 🔁 Rotating admin mentions
    mentions = await get_rotating_admin_mentions(
        client,
        message.chat.id,
        cur,
        conn
    )
    
    if not mentions:
        return

    alert = footer(
        "🚨 **ADMIN REPORTS ALERT**\n\n"
        f"🔑 Keyword detected\n"
        f"👤 User: {message.from_user.mention}\n\n"
        f"{' '.join(mentions)}"
    )

    # 🔔 Mention notification bypasses group mute
    await client.send_message(
        chat_id=message.chat.id,
        text=alert,
        reply_to_message_id=message.id,
        disable_notification=False  # important for mention
    )


# ================= WELCOME MESSAGE SETTING =================
@app.on_message(filters.command("setwelcome") & filters.group)
async def set_welcome_message(client, message: Message):
    """Set custom welcome message for the group"""
    
    # Check admin permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await is_group_admin(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "❌ **Permission Denied**\n"
            "Only group admins or bot admins can set welcome messages."
            f"{beautiful_footer()}"
        )
        return
    
    # Check if message has text
    if not message.text or len(message.text.split()) < 2:
        help_text = f"""
{beautiful_header('settings')}

📝 **SET WELCOME MESSAGE**

**Usage:** `/setwelcome [message]`

**Example:** `/setwelcome Welcome {{mention}} to {{group}}!`

**Available Variables:**
• `{{mention}}` - User mention
• `{{first_name}}` - User's first name
• `{{last_name}}` - User's last name
• `{{full_name}}` - User's full name
• `{{username}}` - User's username
• `{{user_id}}` - User's ID
• `{{group}}` - Group name
• `{{group_id}}` - Group ID
• `{{time}}` - Join time
• `{{date}}` - Join date

**Custom Format Example:**
`/setwelcome Hey {{mention}}! Welcome to {{group}}. Please read the rules.`

**To remove welcome message:** `/delwelcome`
**To see current welcome:** `/welcomesettings`
        """
        await message.reply_text(help_text + beautiful_footer())
        return
    
    # Extract welcome message (remove command)
    welcome_text = " ".join(message.text.split()[1:])
    
    # Save to database
    cur.execute(
        "INSERT OR REPLACE INTO welcome_messages (chat_id, message) VALUES (?, ?)",
        (chat_id, welcome_text)
    )
    conn.commit()
    
    # Show preview
    preview_text = welcome_text.replace("{{mention}}", message.from_user.mention)
    preview_text = preview_text.replace("{{first_name}}", message.from_user.first_name or "")
    preview_text = preview_text.replace("{{last_name}}", message.from_user.last_name or "")
    preview_text = preview_text.replace("{{full_name}}", f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip())
    preview_text = preview_text.replace("{{username}}", f"@{message.from_user.username}" if message.from_user.username else "No username")
    preview_text = preview_text.replace("{{user_id}}", str(message.from_user.id))
    preview_text = preview_text.replace("{{group}}", message.chat.title)
    preview_text = preview_text.replace("{{group_id}}", str(message.chat.id))
    preview_text = preview_text.replace("{{time}}", datetime.now().strftime("%I:%M %p"))
    preview_text = preview_text.replace("{{date}}", datetime.now().strftime("%d %b %Y"))
    
    await message.reply_text(
        f"{beautiful_header('settings')}\n\n"
        "✅ **Welcome Message Set**\n\n"
        f"**Preview:**\n{preview_text}\n\n"
        f"📊 **Length:** {len(welcome_text)} characters\n"
        f"💬 **Variables used:** {welcome_text.count('{{')}\n\n"
        f"**To check:** `/welcomesettings`\n"
        f"**To remove:** `/delwelcome`"
        f"{beautiful_footer()}"
    )

@app.on_message(filters.command("delwelcome") & filters.group)
async def delete_welcome_message(client, message: Message):
    """Delete custom welcome message"""
    
    # Check admin permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await is_group_admin(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "❌ **Permission Denied**\n"
            "Only group admins or bot admins can delete welcome messages."
            f"{beautiful_footer()}"
        )
        return
    
    # Check if welcome exists
    cur.execute("SELECT message FROM welcome_messages WHERE chat_id=?", (chat_id,))
    existing = cur.fetchone()
    
    if not existing:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "ℹ️ **No Welcome Message Set**\n"
            "There is no custom welcome message for this group.\n\n"
            "**To set one:** `/setwelcome [message]`"
            f"{beautiful_footer()}"
        )
        return
    
    # Delete from database
    cur.execute("DELETE FROM welcome_messages WHERE chat_id=?", (chat_id,))
    conn.commit()
    
    await message.reply_text(
        f"{beautiful_header('settings')}\n\n"
        "🗑️ **Welcome Message Deleted**\n\n"
        "Custom welcome message has been removed.\n"
        "Default welcome will be shown for new members.\n\n"
        "**To set new:** `/setwelcome [message]`"
        f"{beautiful_footer()}"
    )

@app.on_message(filters.command("welcomesettings") & filters.group)
async def welcome_settings(client, message: Message):
    """Show current welcome settings"""
    
    chat_id = message.chat.id
    
    # Get welcome message
    cur.execute("SELECT message FROM welcome_messages WHERE chat_id=?", (chat_id,))
    result = cur.fetchone()
    
    if result:
        welcome_text = result[0]
        status = "✅ **Custom Welcome Enabled**"
        preview_text = welcome_text.replace("{{mention}}", message.from_user.mention)
        preview_text = preview_text.replace("{{first_name}}", message.from_user.first_name or "")
        preview_text = preview_text.replace("{{last_name}}", message.from_user.last_name or "")
        preview_text = preview_text.replace("{{full_name}}", f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip())
        preview_text = preview_text.replace("{{username}}", f"@{message.from_user.username}" if message.from_user.username else "No username")
        preview_text = preview_text.replace("{{user_id}}", str(message.from_user.id))
        preview_text = preview_text.replace("{{group}}", message.chat.title)
        preview_text = preview_text.replace("{{group_id}}", str(message.chat.id))
        preview_text = preview_text.replace("{{time}}", datetime.now().strftime("%I:%M %p"))
        preview_text = preview_text.replace("{{date}}", datetime.now().strftime("%d %b %Y"))
    else:
        status = "ℹ️ **Default Welcome**"
        welcome_text = "Not set (using default format)"
        preview_text = f"👋 Welcome {message.from_user.mention} to {message.chat.title}!"
    
    await message.reply_text(
        f"{beautiful_header('settings')}\n\n"
        f"{status}\n\n"
        f"📝 **Current Welcome Text:**\n`{welcome_text}`\n\n"
        f"👤 **Preview:**\n{preview_text}\n\n"
        f"**Commands:**\n"
        f"• `/setwelcome [message]` - Set custom welcome\n"
        f"• `/delwelcome` - Remove custom welcome\n"
        f"• `/welcomesettings` - View current settings"
        f"{beautiful_footer()}"
    )

@app.on_chat_member_updated()
async def welcome_with_userdata(client, update):
    """Handle new member joins with custom welcome messages"""
    
    if not update.old_chat_member or not update.new_chat_member:
        return
    
    # Check if it's a join (not leave)
    if (
        update.old_chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]
        and update.new_chat_member.status == ChatMemberStatus.MEMBER
    ):
        user = update.new_chat_member.user
        chat = update.chat
        
        # Skip bots if needed
        if user.is_bot:
            return
        
        username = f"@{user.username}" if user.username else "Not set"
        account = "Bot 🤖" if user.is_bot else "User 👤"
        join_time = datetime.now().strftime("%d %b %Y • %I:%M %p")
        
        # Check for custom welcome message
        cur.execute("SELECT message FROM welcome_messages WHERE chat_id=?", (chat.id,))
        result = cur.fetchone()
        
        if result:
            # Use custom welcome message
            welcome_text = result[0]
            
            # Replace variables
            welcome_text = welcome_text.replace("{{mention}}", mention(user))
            welcome_text = welcome_text.replace("{{first_name}}", user.first_name or "")
            welcome_text = welcome_text.replace("{{last_name}}", user.last_name or "")
            welcome_text = welcome_text.replace("{{full_name}}", f"{user.first_name or ''} {user.last_name or ''}".strip())
            welcome_text = welcome_text.replace("{{username}}", username)
            welcome_text = welcome_text.replace("{{user_id}}", str(user.id))
            welcome_text = welcome_text.replace("{{group}}", chat.title)
            welcome_text = welcome_text.replace("{{group_id}}", str(chat.id))
            welcome_text = welcome_text.replace("{{time}}", join_time.split(" • ")[1])
            welcome_text = welcome_text.replace("{{date}}", join_time.split(" • ")[0])
            
            # Send custom welcome
            msg = await client.send_message(
                chat.id,
                f"{beautiful_header('welcome')}\n\n{welcome_text}",
                disable_web_page_preview=True
            )
        else:
            # Use default welcome format
            text = WELCOME_USER_CARD.format(
                mention=mention(user),
                user_id=user.id,
                username=username,
                account=account,
                time=join_time,
                group=chat.title
            )
            
            msg = await client.send_message(
                chat.id,
                text,
                disable_web_page_preview=True
            )
        
        # Optional: Auto-delete welcome after 2 minutes
        # await asyncio.sleep(120)
        # await msg.delete()



# ================= COMPLETE HELP COMMAND SYSTEM =================

# Define all command categories with descriptions
HELP_CATEGORIES = {
    "start": {"icon": "🚀", "title": "Start Commands", "admin_only": False},
    "moderation": {"icon": "🔨", "title": "Moderation Commands", "admin_only": True},
    "admin": {"icon": "👑", "title": "Admin Commands", "admin_only": True},
    "welcome": {"icon": "👋", "title": "Welcome System", "admin_only": False},
    "security": {"icon": "🛡️", "title": "Security & Locks", "admin_only": True},
    "info": {"icon": "ℹ️", "title": "Information", "admin_only": False},
    "support": {"icon": "💬", "title": "Support System", "admin_only": False},
    "cleanup": {"icon": "🧹", "title": "Cleanup Commands", "admin_only": True},
    "tagging": {"icon": "🏷️", "title": "Tagging System", "admin_only": True},
    "tools": {"icon": "🛠️", "title": "Tools & Utilities", "admin_only": False}
}

# Define all commands with descriptions, usage, and categories
ALL_COMMANDS = {
    # Start Commands
    "start": {
        "description": "Start the bot and see main menu",
        "usage": "/start",
        "category": "start",
        "admin_only": False,
        "group_only": False
    },
    "help": {
        "description": "Show this help message",
        "usage": "/help [category]",
        "category": "start",
        "admin_only": False,
        "group_only": False
    },
    "mystatus": {
        "description": "Check your admin status and permissions",
        "usage": "/mystatus",
        "category": "start",
        "admin_only": False,
        "group_only": True
    },
    
    # Moderation Commands
    "mute": {
        "description": "Mute a user (temporary or permanent)",
        "usage": "/mute [reply/user] [duration] [reason]\n/bmute - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "unmute": {
        "description": "Unmute a muted user",
        "usage": "/unmute [reply/user]\n/bunmute - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "warn": {
        "description": "Warn a user (3 warnings = auto-ban)",
        "usage": "/warn [reply/user] [reason]\n/bwarn - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "ban": {
        "description": "Ban a user from the group",
        "usage": "/ban [reply/user] [reason]\n/bban - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "unban": {
        "description": "Unban a previously banned user",
        "usage": "/unban [reply/user]\n/bunban - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "kick": {
        "description": "Kick a user from the group",
        "usage": "/kick [reply/user] [reason]\n/bkick - Bot admin version",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "promote": {
        "description": "Promote a user to admin",
        "usage": "/promote [reply/user] [title]",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    "demote": {
        "description": "Demote an admin to regular user",
        "usage": "/demote [reply/user]",
        "category": "moderation",
        "admin_only": True,
        "group_only": True
    },
    
    # Welcome System
    "setwelcome": {
        "description": "Set custom welcome message for new members",
        "usage": "/setwelcome [message]\nVariables: {{mention}}, {{first_name}}, {{group}}, etc.",
        "category": "welcome",
        "admin_only": True,
        "group_only": True
    },
    "delwelcome": {
        "description": "Delete custom welcome message",
        "usage": "/delwelcome",
        "category": "welcome",
        "admin_only": True,
        "group_only": True
    },
    "welcomesettings": {
        "description": "View current welcome settings",
        "usage": "/welcomesettings",
        "category": "welcome",
        "admin_only": False,
        "group_only": True
    },
    
    # Security & Locks
    "lock": {
        "description": "Lock specific permissions in group",
        "usage": "/lock [type] [duration]\nTypes: all, text, media, stickers, etc.",
        "category": "security",
        "admin_only": True,
        "group_only": True
    },
    "unlock": {
        "description": "Unlock specific permissions",
        "usage": "/unlock [type]\nTypes: all, text, media, stickers, etc.",
        "category": "security",
        "admin_only": True,
        "group_only": True
    },
    "lockstatus": {
        "description": "Check current lock status",
        "usage": "/lockstatus",
        "category": "security",
        "admin_only": False,
        "group_only": True
    },
    "glock": {
        "description": "Bot admin: Lock group by chat ID",
        "usage": "/glock [chat_id] [type] [duration] [silent]",
        "category": "security",
        "admin_only": True,
        "group_only": False
    },
    "gunlock": {
        "description": "Bot admin: Unlock group by chat ID",
        "usage": "/gunlock [chat_id] [silent]",
        "category": "security",
        "admin_only": True,
        "group_only": False
    },
    "adminabuse": {
        "description": "Toggle admin abuse detection system",
        "usage": "/adminabuse [on/off/status]",
        "category": "security",
        "admin_only": True,
        "group_only": True
    },
    
    # Information Commands
    "id": {
        "description": "Get user ID information",
        "usage": "/id [reply/user]\nWithout argument shows your own ID",
        "category": "info",
        "admin_only": False,
        "group_only": False
    },
    "myid": {
        "description": "Get your own ID with details",
        "usage": "/myid",
        "category": "info",
        "admin_only": False,
        "group_only": False
    },
    "chatid": {
        "description": "Get chat/channel ID",
        "usage": "/chatid",
        "category": "info",
        "admin_only": False,
        "group_only": False
    },
    
    # Support System
    "contact": {
        "description": "Contact support (PM the bot)",
        "usage": "Just send a message to the bot in PM",
        "category": "support",
        "admin_only": False,
        "group_only": False
    },
    "support": {
        "description": "Get support information",
        "usage": "/support",
        "category": "support",
        "admin_only": False,
        "group_only": False
    },
    
    # Cleanup Commands
    "purge": {
        "description": "Delete messages from replied to current",
        "usage": "/purge (reply to a message)",
        "category": "cleanup",
        "admin_only": True,
        "group_only": True
    },
    "purgeall": {
        "description": "Delete last N messages",
        "usage": "/purgeall [number] [-s for silent]",
        "category": "cleanup",
        "admin_only": True,
        "group_only": True
    },
    "pin": {
        "description": "Pin a message",
        "usage": "/pin [reply] [silent]\n/pinmsg - Alternative command",
        "category": "cleanup",
        "admin_only": True,
        "group_only": True
    },
    "unpin": {
        "description": "Unpin a message",
        "usage": "/unpin [reply]\n/unpinmsg - Alternative command",
        "category": "cleanup",
        "admin_only": True,
        "group_only": True
    },
    
    # Tagging System
    "tagall": {
        "description": "Tag all group members",
        "usage": "/tagall",
        "category": "tagging",
        "admin_only": True,
        "group_only": True
    },
    "tagadmin": {
        "description": "Tag all group admins",
        "usage": "/tagadmin",
        "category": "tagging",
        "admin_only": False,
        "group_only": True
    },
    "stop": {
        "description": "Stop ongoing tagging process",
        "usage": "/stop",
        "category": "tagging",
        "admin_only": True,
        "group_only": True
    },
    
    # Tools & Utilities
    "exportcsv": {
        "description": "Export support data to CSV (Bot admins only)",
        "usage": "/exportcsv",
        "category": "tools",
        "admin_only": True,
        "group_only": False
    },
    "listbotadmins": {
        "description": "List all bot admins",
        "usage": "/listbotadmins",
        "category": "tools",
        "admin_only": True,
        "group_only": False
    },
    "addbotadmin": {
        "description": "Add new bot admin (Super admin only)",
        "usage": "/addbotadmin [user_id]",
        "category": "tools",
        "admin_only": True,
        "group_only": False
    },
    "rules": {
        "description": "Show group rules",
        "usage": "/rules",
        "category": "tools",
        "admin_only": False,
        "group_only": True
    }
}

def create_help_buttons(categories, current_user_id, chat_type="private"):
    """Create category buttons for help command"""
    buttons = []
    row = []
    
    for category_id, category_info in categories.items():
        # Check if user can see this category
        if category_info["admin_only"]:
            if chat_type == "private":
                if not is_bot_admin(current_user_id):
                    continue
            else:
                # For groups, we need to check both bot admin and group admin
                # This is simplified - you might want to adjust this logic
                pass
        
        icon = category_info["icon"]
        title = category_info["title"]
        
        button = InlineKeyboardButton(
            f"{icon} {title}",
            callback_data=f"help_cat:{category_id}"
        )
        
        row.append(button)
        if len(row) == 2:  # 2 buttons per row
            buttons.append(row)
            row = []
    
    if row:  # Add remaining buttons if any
        buttons.append(row)
    
    # Add quick action buttons
    quick_buttons = [
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="help_main"),
            InlineKeyboardButton("🤖 Bot Info", callback_data="help_botinfo")
        ],
        [
            InlineKeyboardButton("👑 Admin Help", callback_data="help_admin"),
            InlineKeyboardButton("🆘 Quick Support", callback_data="help_support")
        ]
    ]
    
    buttons.extend(quick_buttons)
    
    return InlineKeyboardMarkup(buttons)

def create_category_help(category_id, user_id, is_group=False):
    """Create help text for a specific category"""
    category = HELP_CATEGORIES.get(category_id)
    if not category:
        return None
    
    icon = category["icon"]
    title = category["title"]
    admin_only = category["admin_only"]
    
    # Filter commands for this category
    category_commands = []
    for cmd_name, cmd_info in ALL_COMMANDS.items():
        if cmd_info["category"] == category_id:
            # Check if command is available in current context
            if cmd_info["group_only"] and not is_group:
                continue
            if cmd_info["admin_only"] and not is_bot_admin(user_id):
                continue
            
            category_commands.append((cmd_name, cmd_info))
    
    if not category_commands:
        return f"No commands available in {title} category for your access level."
    
    # Create help text
    help_text = f"{beautiful_header('guide')}\n\n"
    help_text += f"{icon} **{title}**\n\n"
    
    if admin_only:
        help_text += "🔐 *Admin only commands*\n\n"
    
    help_text += "📋 **Available Commands:**\n\n"
    
    for cmd_name, cmd_info in category_commands:
        help_text += f"• **/{cmd_name}**\n"
        help_text += f"  ↳ {cmd_info['description']}\n"
        help_text += f"  📝 Usage: `{cmd_info['usage']}`\n\n"
    
    help_text += f"📊 **Total:** {len(category_commands)} commands\n\n"
    help_text += "💡 **Tip:** Click/tap commands to copy them\n"
    help_text += "🔙 **Back:** Use buttons below to navigate"
    
    return help_text

@app.on_message(filters.command(["help", "commands", "menu"]) & filters.private)
async def help_command_private(client, message: Message):
    """Help command for private chats"""
    
    user_id = message.from_user.id
    is_admin_user = is_bot_admin(user_id)
    
    # Create welcome text
    welcome_text = f"""
{beautiful_header('guide')}

🤖 **Welcome to {BOT_BRAND} Help Center**

✨ **Premium Features:**
• Advanced Moderation Tools
• Custom Welcome System  
• Smart Abuse Detection
• Support Management
• Tagging System
• Security Locks

👤 **Your Status:** {'👑 Bot Admin' if is_admin_user else '👤 Regular User'}

📚 **Select a category below to explore commands:**

"""
    
    await message.reply_text(
        welcome_text + beautiful_footer(),
        reply_markup=create_help_buttons(HELP_CATEGORIES, user_id, "private")
    )

@app.on_message(filters.command(["help", "commands", "menu"]) & filters.group)
async def help_command_group(client, message: Message):
    """Help command for groups - shows relevant commands"""
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check if user is admin in this group
    try:
        member = await client.get_chat_member(chat_id, user_id)
        is_group_admin = member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        is_group_admin = False
    
    is_bot_admin_user = is_bot_admin(user_id)
    
    # Filter categories that are relevant for groups
    relevant_categories = {}
    for cat_id, cat_info in HELP_CATEGORIES.items():
        if cat_info["admin_only"] and not (is_group_admin or is_bot_admin_user):
            continue
        relevant_categories[cat_id] = cat_info
    
    # Create group-specific help
    help_text = f"""
{beautiful_header('guide')}

👥 **Group Help - {message.chat.title}**

🔧 **Available Commands for You:**

**👤 Member Commands:**
• `/help` - Show this menu
• `/id` - Get user ID
• `/myid` - Get your ID
• `/tagadmin` - Tag all admins
• `/welcomesettings` - View welcome settings
• `/rules` - Show group rules
• `/support` - Get support info

"""
    
    if is_group_admin or is_bot_admin_user:
        help_text += """
**👑 Admin Commands:**
• `/mute` `/unmute` - User management
• `/warn` `/ban` `/kick` - Moderation
• `/promote` `/demote` - Admin management
• `/purge` `/purgeall` - Message cleanup
• `/pin` `/unpin` - Message pinning
• `/lock` `/unlock` - Security locks
• `/setwelcome` - Custom welcome
• `/tagall` - Tag all members
"""
    
    help_text += f"\n👑 **Your Role:** "
    if is_bot_admin_user:
        help_text += "Bot Admin ⚡"
    elif is_group_admin:
        help_text += "Group Admin 🛡️"
    else:
        help_text += "Member 👤"
    
    help_text += f"\n💬 **Chat:** {message.chat.title}"
    help_text += f"\n🆔 **Chat ID:** `{chat_id}`"
    
    # Create buttons for group context
    buttons = []
    
    # Basic buttons for everyone
    basic_buttons = [
        [
            InlineKeyboardButton("ℹ️ My Info", callback_data="help_myinfo"),
            InlineKeyboardButton("🆔 Get IDs", callback_data="help_ids")
        ],
        [
            InlineKeyboardButton("📜 Rules", callback_data="help_rules"),
            InlineKeyboardButton("👋 Welcome", callback_data="help_welcome")
        ]
    ]
    
    # Admin buttons if applicable
    if is_group_admin or is_bot_admin_user:
        admin_buttons = [
            [
                InlineKeyboardButton("🔨 Moderation", callback_data="help_cat:moderation"),
                InlineKeyboardButton("🛡️ Security", callback_data="help_cat:security")
            ],
            [
                InlineKeyboardButton("🧹 Cleanup", callback_data="help_cat:cleanup"),
                InlineKeyboardButton("🏷️ Tagging", callback_data="help_cat:tagging")
            ]
        ]
        buttons.extend(admin_buttons)
    
    buttons.extend(basic_buttons)
    
    # Add support button
    buttons.append([
        InlineKeyboardButton("💬 PM Support", url=f"https://t.me/{client.me.username}"),
        InlineKeyboardButton("📚 Full Help", callback_data="help_full")
    ])
    
    await message.reply_text(
        help_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex("^help_cat:"))
async def help_category_callback(client, callback_query):
    """Handle category selection in help menu"""
    
    category_id = callback_query.data.split(":")[1]
    user_id = callback_query.from_user.id
    
    # Check if in group or private
    chat_type = callback_query.message.chat.type
    is_group = chat_type in ["group", "supergroup"]
    
    help_text = create_category_help(category_id, user_id, is_group)
    
    if not help_text:
        await callback_query.answer("Category not found!", show_alert=True)
        return
    
    # Create back button
    buttons = [
        [
            InlineKeyboardButton("🔙 Back", callback_data="help_main"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="help_start")
        ]
    ]
    
    try:
        await callback_query.message.edit_text(
            help_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        await callback_query.answer()
    except Exception as e:
        await callback_query.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^help_"))
async def help_quick_actions(client, callback_query):
    """Handle quick action buttons in help menu"""
    
    action = callback_query.data
    user_id = callback_query.from_user.id
    
    if action == "help_main":
        # Return to main help
        is_admin_user = is_bot_admin(user_id)
        
        welcome_text = f"""
{beautiful_header('guide')}

🤖 **Welcome to {BOT_BRAND} Help Center**

✨ **Premium Features:**
• Advanced Moderation Tools
• Custom Welcome System  
• Smart Abuse Detection
• Support Management
• Tagging System
• Security Locks

👤 **Your Status:** {'👑 Bot Admin' if is_admin_user else '👤 Regular User'}

📚 **Select a category below to explore commands:**
"""
        
        await callback_query.message.edit_text(
            welcome_text + beautiful_footer(),
            reply_markup=create_help_buttons(HELP_CATEGORIES, user_id)
        )
    
    elif action == "help_botinfo":
        # Show bot information
        uptime = get_uptime()
        
        botinfo_text = f"""
{beautiful_header('info')}

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

📊 **Statistics:**
• **Uptime:** {uptime}
• **Bot Admins:** {len(INITIAL_ADMINS)}
• **Abuse Words:** {len(ABUSE_WORDS)}
• **Features:** 50+ commands
• **Version:** 2.0 Premium

⚡ **Core Features:**
• Smart Moderation System
• Custom Welcome Messages
• Abuse Auto-Detection
• Support Ticket System
• Advanced Tagging
• Security Lock System

👨‍💻 **Developer:** @AnkitShakyaSupport
📚 **Documentation:** /help

💎 **Premium Bot - Fast & Secure**
"""
        
        buttons = [
            [
                InlineKeyboardButton("🔙 Back", callback_data="help_main"),
                InlineKeyboardButton("👑 Admin Panel", callback_data="help_admin")
            ],
            [
                InlineKeyboardButton("💬 Support", url=f"https://t.me/{client.me.username}"),
                InlineKeyboardButton("📚 Commands", callback_data="help_commands")
            ]
        ]
        
        await callback_query.message.edit_text(
            botinfo_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "help_admin":
        # Admin-specific help
        is_admin_user = is_bot_admin(user_id)
        
        if not is_admin_user:
            await callback_query.answer("Admin access required!", show_alert=True)
            return
        
        admin_text = f"""
{beautiful_header('admin')}

👑 **Admin Help Center**

**Bot Admin Commands:**
• `/addbotadmin [id]` - Add bot admin
• `/listbotadmins` - List all admins
• `/exportcsv` - Export support data
• `/glock` - Lock group by ID
• `/gunlock` - Unlock group by ID

**Group Admin Commands:**
• `/mute` `/unmute` - User restrictions
• `/ban` `/unban` - Ban management
• `/warn` - Warning system
• `/kick` - Remove users
• `/promote` `/demote` - Admin management
• `/purge` `/purgeall` - Message cleanup
• `/pin` `/unpin` - Message pinning
• `/lock` `/unlock` - Security locks
• `/setwelcome` - Welcome messages
• `/tagall` - Tag all members

**Super Admin Only:**
• Full bot control
• Add/remove bot admins
• Global configuration
• Database management

👤 **Your Status:** Bot Admin ⚡
"""
        
        buttons = [
            [
                InlineKeyboardButton("🔙 Back", callback_data="help_main"),
                InlineKeyboardButton("🛡️ Security", callback_data="help_cat:security")
            ],
            [
                InlineKeyboardButton("🔨 Moderation", callback_data="help_cat:moderation"),
                InlineKeyboardButton("📊 Stats", callback_data="help_stats")
            ]
        ]
        
        await callback_query.message.edit_text(
            admin_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "help_support":
        # Support information
        support_text = f"""
{beautiful_header('support')}

💬 **Support System**

**How to Get Support:**
1. Send a message to this bot in PM
2. Our support team will reply shortly
3. Use respectful language

**Support Rules:**
✅ Be patient - we'll reply ASAP
✅ Provide clear information
✅ Use English or Hindi
❌ No abuse or spam
❌ No excessive messages

**Quick Actions:**
• PM the bot directly for help
• Use /rules in groups
• Contact @AnkitShakyaSupport

**Support Hours:**
🕒 24/7 Automated Support
👨‍💻 Admin Response: Within hours

**Need Immediate Help?**
Send "Hello" to the bot in PM
"""
        
        buttons = [
            [
                InlineKeyboardButton("🔙 Back", callback_data="help_main"),
                InlineKeyboardButton("📨 PM Bot", url=f"https://t.me/{client.me.username}")
            ],
            [
                InlineKeyboardButton("📜 Rules", callback_data="help_rules"),
                InlineKeyboardButton("ℹ️ Info", callback_data="help_info")
            ]
        ]
        
        await callback_query.message.edit_text(
            support_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "help_start":
        # Simulate /start command
        from_user = callback_query.from_user
        
        start_text = f"""
{beautiful_header('welcome')}

👋 **Welcome {from_user.first_name}!**

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✨ **I'm a premium multi-feature bot with:**
• Advanced Moderation Tools
• Custom Welcome System
• Smart Abuse Detection
• Support Management
• Tagging System
• Security Lock System

📚 **Quick Start:**
1. Add me to your group
2. Make me admin with all permissions
3. Use /help to see all commands

👑 **Admin Features:**
• User management (mute/ban/warn)
• Message cleanup (purge/pin)
• Security locks
• Custom welcome messages
• Tagging system

👥 **Member Features:**
• User ID lookup
• Admin tagging
• Support system
• Group information

**Get Started:**
"""
        
        buttons = [
            [
                InlineKeyboardButton("📚 Commands", callback_data="help_main"),
                InlineKeyboardButton("👑 Admin Panel", callback_data="help_admin")
            ],
            [
                InlineKeyboardButton("➕ Add to Group", url=f"https://t.me/{client.me.username}?startgroup=true"),
                InlineKeyboardButton("💬 Support", url=f"https://t.me/{client.me.username}")
            ]
        ]
        
        await callback_query.message.edit_text(
            start_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    elif action == "help_full":
        # Show full command list
        is_admin_user = is_bot_admin(user_id)
        chat_type = callback_query.message.chat.type
        is_group = chat_type in ["group", "supergroup"]
        
        # Count available commands
        total_commands = 0
        available_commands = 0
        
        for cmd_name, cmd_info in ALL_COMMANDS.items():
            total_commands += 1
            if cmd_info["group_only"] and not is_group:
                continue
            if cmd_info["admin_only"] and not is_admin_user:
                continue
            available_commands += 1
        
        full_help = f"""
{beautiful_header('guide')}

📚 **Complete Command List**

📊 **Statistics:**
• Total Commands: {total_commands}
• Available to You: {available_commands}
• Admin Commands: {sum(1 for cmd in ALL_COMMANDS.values() if cmd['admin_only'])}

📋 **All Commands:**

"""
        
        # Group commands by category
        for category_id, category_info in HELP_CATEGORIES.items():
            category_commands = []
            for cmd_name, cmd_info in ALL_COMMANDS.items():
                if cmd_info["category"] == category_id:
                    if cmd_info["group_only"] and not is_group:
                        continue
                    if cmd_info["admin_only"] and not is_admin_user:
                        continue
                    category_commands.append(f"• `/{cmd_name}` - {cmd_info['description']}")
            
            if category_commands:
                full_help += f"\n{category_info['icon']} **{category_info['title']}**\n"
                full_help += "\n".join(category_commands) + "\n"
        
        full_help += f"\n💡 **Tip:** Use `/help [category]` for detailed help\n"
        full_help += f"👤 **Your Access Level:** {'👑 Admin' if is_admin_user else '👤 Member'}"
        
        buttons = [
            [
                InlineKeyboardButton("🔙 Back", callback_data="help_main"),
                InlineKeyboardButton("📖 Categories", callback_data="help_categories")
            ]
        ]
        
        await callback_query.message.edit_text(
            full_help + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
    
    await callback_query.answer()


# ================= ANIMATED START FUNCTION =================
async def send_animated_start(client, message):
    """Send animated start message with beautiful effects"""
    from_user = message.from_user
    
    # Step 1: Initial loading animation
    loading_msg = await message.reply_text(
        f"{beautiful_header('loading')}\n\n"
        "🎯 **Initializing Premium Bot...**\n"
        f"{progress_bar(10)}"
    )
    
    await asyncio.sleep(0.5)
    
    # Step 2: Feature loading animation
    features = [
        "🔨 Loading Moderation Tools",
        "🛡️ Loading Security Systems",
        "💬 Loading Support Features",
        "🏷️ Loading Tagging Engine",
        "✨ Loading UI Components",
        "⚡ Optimizing Performance"
    ]
    
    for i, feature in enumerate(features):
        percentage = 10 + ((i + 1) * 15)
        await loading_msg.edit_text(
            f"{beautiful_header('loading')}\n\n"
            f"{feature}...\n"
            f"{progress_bar(percentage)}\n"
            f"🔧 {i+1}/{len(features)} components loaded"
        )
        await asyncio.sleep(0.3)
    
    await loading_msg.delete()
    
    # Step 3: Send main welcome with animation
    welcome_frames = [
        # Frame 1: Welcome text
        f"""
{beautiful_header('welcome')}

✨ **WELCOME TO THE FUTURE** ✨

👋 **Hello {from_user.first_name}!**

⚡ **PREMIUM BOT ACTIVATED** ⚡

{BOT_BRAND}
{BOT_TAGLINE}
""",
        # Frame 2: Features reveal
        f"""
{beautiful_header('welcome')}

✨ **WELCOME TO THE FUTURE** ✨

👋 **Hello {from_user.first_name}!**

⚡ **PREMIUM BOT ACTIVATED** ⚡

{BOT_BRAND}
{BOT_TAGLINE}

🎯 **LOADED FEATURES:**
• 🔨 Advanced Moderation Suite
• 🛡️ Intelligent Security Layer
• 💬 24/7 Support System
""",
        # Frame 3: More features
        f"""
{beautiful_header('welcome')}

✨ **WELCOME TO THE FUTURE** ✨

👋 **Hello {from_user.first_name}!**

⚡ **PREMIUM BOT ACTIVATED** ⚡

{BOT_BRAND}
{BOT_TAGLINE}

🎯 **LOADED FEATURES:**
• 🔨 Advanced Moderation Suite
• 🛡️ Intelligent Security Layer
• 💬 24/7 Support System
• 🏷️ Smart Tagging Engine
• ✨ Beautiful UI System
• ⚡ Lightning Performance
""",
        # Frame 4: Final welcome
        f"""
{beautiful_header('welcome')}

✨ **WELCOME TO THE FUTURE** ✨

👋 **Hello {from_user.first_name}!**

⚡ **PREMIUM BOT ACTIVATED** ⚡

{BOT_BRAND}
{BOT_TAGLINE}

🌟 **YOUR PREMIUM EXPERIENCE AWAITS**

🎯 **LOADED FEATURES:**
• 🔨 Advanced Moderation Suite
• 🛡️ Intelligent Security Layer
• 💬 24/7 Support System
• 🏷️ Smart Tagging Engine
• ✨ Beautiful UI System
• ⚡ Lightning Performance

📊 **Ready to revolutionize your group management!**
"""
    ]
    
    welcome_msg = None
    for frame in welcome_frames:
        if welcome_msg:
            try:
                await welcome_msg.edit_text(frame + beautiful_footer())
            except:
                pass
        else:
            welcome_msg = await message.reply_text(frame + beautiful_footer())
        await asyncio.sleep(0.5)
    
    await asyncio.sleep(1)
    
    # Step 4: Create interactive buttons with animation
    buttons = create_start_buttons(client)
    
    # Step 5: Final message with all options
    final_text = f"""
{beautiful_header('sparkles')}

🎉 **WELCOME {from_user.first_name.upper()}!** 🎉

🤖 **{BOT_BRAND}** 
{BOT_TAGLINE}

✨ **YOUR ALL-IN-ONE SOLUTION FOR:**

🎯 **Group Management**
• Smart moderation tools
• Auto abuse detection
• Custom welcome system
• Advanced security locks

💎 **Premium Features**
• Beautiful animated UI
• 50+ powerful commands
• 24/7 support system
• Multi-admin support

⚡ **Quick Start**
1. Add me to your group
2. Grant admin permissions
3. Use /help to explore
4. Enjoy premium features!

📊 **Bot Status:**
• ✅ All systems operational
• ⚡ Premium mode: ACTIVE
• 🛡️ Security: ENABLED
• 💬 Support: ONLINE

🎁 **Ready to experience premium group management?**
"""
    
    try:
        await welcome_msg.edit_text(
            final_text + beautiful_footer(),
            reply_markup=buttons,
            disable_web_page_preview=True
        )
    except:
        welcome_msg = await message.reply_text(
            final_text + beautiful_footer(),
            reply_markup=buttons,
            disable_web_page_preview=True
        )

def create_start_buttons(client):
    """Create animated button grid for start command"""
    
    # Emoji animations for buttons
    button_rows = [
        # Row 1: Main actions
        [
            InlineKeyboardButton(
                "📚 EXPLORE COMMANDS",
                callback_data="help_main"
            ),
            InlineKeyboardButton(
                "👑 ADMIN PANEL",
                callback_data="help_admin"
            )
        ],
        # Row 2: Quick actions
        [
            InlineKeyboardButton(
                "➕ ADD TO GROUP",
                url=f"https://t.me/{client.me.username}?startgroup=true"
            ),
            InlineKeyboardButton(
                "💬 GET SUPPORT",
                url=f"https://t.me/{client.me.username}"
            )
        ],
        # Row 3: Features
        [
            InlineKeyboardButton(
                "✨ FEATURES TOUR",
                callback_data="help_features"
            ),
            InlineKeyboardButton(
                "🎯 QUICK START",
                callback_data="help_quickstart"
            )
        ],
        # Row 4: Info
        [
            InlineKeyboardButton(
                "📊 BOT STATS",
                callback_data="help_stats"
            ),
            InlineKeyboardButton(
                "⚙️ SETTINGS",
                callback_data="help_settings"
            )
        ],
        # Row 5: Developer
        [
            InlineKeyboardButton(
                "👨‍💻 DEVELOPER",
                url="https://t.me/AnkitShakyaSupport"
            ),
            InlineKeyboardButton(
                "🌟 RATE BOT",
                callback_data="help_rate"
            )
        ]
    ]
    
    return InlineKeyboardMarkup(button_rows)

# ================= ENHANCED START COMMAND =================
@app.on_message(filters.command("start") & filters.private)
async def animated_start_command(client, message: Message):
    """Main start command with animation + user tracking"""

    if not message.from_user or message.from_user.is_bot:
        return

    # ======== TRACK USER IN DATABASE ========
    user = message.from_user
    try:
        cur.execute(
            """
            INSERT OR REPLACE INTO users
            (user_id, username, first_name, last_name, last_active)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                user.id,
                user.username or "",
                user.first_name or "",
                user.last_name or ""
            )
        )
        conn.commit()
        print(f"✅ User {user.id} added to broadcast database")
    except Exception as e:
        print(f"⚠️ Error adding user to DB: {e}")
    # =======================================

    # -------- DEEP LINK HANDLING --------
    if len(message.command) > 1:
        arg = message.command[1].lower()

        if arg == "help":
            await help_command_private(client, message)
            return

        elif arg == "support":
            await message.reply_text(
                f"{beautiful_header('support')}\n\n"
                "💬 **Direct Support Access**\n\n"
                "Please send your message here.\n"
                "Our support team will reply shortly.\n\n"
                "🔸 Be clear and concise\n"
                "🔸 Include relevant details\n"
                "🔸 No abusive language\n\n"
                "🙏 Thank you for your patience!"
                f"{beautiful_footer()}"
            )
            return

        elif arg.startswith("group_"):
            await message.reply_text(
                f"{beautiful_header('group')}\n\n"
                "👥 **Group Management Tools**\n\n"
                "Add me to your group to access:\n"
                "• Advanced moderation\n"
                "• Security features\n"
                "• Tagging system\n\n"
                "Click 'Add to Group' below! 👇"
                f"{beautiful_footer()}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "➕ ADD TO GROUP",
                        url=f"https://t.me/{client.me.username}?startgroup=true"
                    )
                ]])
            )
            return
    # ------------------------------------

    # -------- NORMAL START --------
    await send_animated_start(client, message)

# ================= ANIMATED GROUP START =================
@app.on_message(filters.command("start") & filters.group)
async def group_start_command(client, message: Message):
    """Start command for groups with animation"""

    if not message.from_user or not message.chat:
        return

    user = message.from_user
    chat = message.chat

    # -------- CHECK USER ROLE --------
    try:
        member = await client.get_chat_member(chat.id, user.id)
        if member.status == ChatMemberStatus.OWNER:
            role = "👑 Owner"
        elif member.status == ChatMemberStatus.ADMINISTRATOR:
            role = "🛡️ Admin"
        else:
            role = "👤 Member"
    except Exception:
        role = "👤 Member"

    # -------- ANIMATED GROUP WELCOME --------
    group_frames = [
        f"""{beautiful_header('welcome')}

👥 **GROUP MANAGEMENT SYSTEM** 👥

🏷️ **Chat:** {chat.title}
👤 **User:** {user.first_name}
{role}
""",
        f"""{beautiful_header('welcome')}

👥 **GROUP MANAGEMENT SYSTEM** 👥

🏷️ **Chat:** {chat.title}
👤 **User:** {user.first_name}
{role}

⚡ **Bot Status:** ONLINE
🛡️ **Security:** ACTIVE
""",
        f"""{beautiful_header('welcome')}

👥 **GROUP MANAGEMENT SYSTEM** 👥

🏷️ **Chat:** {chat.title}
👤 **User:** {user.first_name}
{role}

⚡ **Bot Status:** ONLINE
🛡️ **Security:** ACTIVE
🎯 **Features:** ENABLED

💎 **Available Commands:**
"""
    ]

    available_commands = [
        "• `/help` - Show commands",
        "• `/id` - Get user ID",
        "• `/myid` - Get your ID",
        "• `/tagadmin` - Tag admins",
    ]

    if role in ("👑 Owner", "🛡️ Admin"):
        available_commands.extend([
            "• `/mute` `/unmute` - User control",
            "• `/ban` `/unban` - Ban management",
            "• `/warn` - Warning system",
            "• `/purge` - Clean messages",
            "• `/lock` `/unlock` - Security",
            "• `/setwelcome` - Custom welcome",
            "• `/tagall` - Tag all members",
        ])

    # -------- ANIMATION --------
    start_msg = None
    for frame in group_frames:
        if start_msg:
            try:
                await start_msg.edit_text(frame + beautiful_footer())
            except:
                pass
        else:
            start_msg = await message.reply_text(frame + beautiful_footer())
        await asyncio.sleep(0.5)

    current_commands = ""
    for i in range(0, len(available_commands), 3):
        current_commands += "\n".join(available_commands[i:i + 3]) + "\n"

        final_frame = f"""{beautiful_header('welcome')}

👥 **GROUP MANAGEMENT SYSTEM** 👥

🏷️ **Chat:** {chat.title}
👤 **User:** {user.first_name}
{role}

⚡ **Bot Status:** ONLINE
🛡️ **Security:** ACTIVE
🎯 **Features:** ENABLED

💎 **Available Commands:**
{current_commands}

📚 **For full commands:** /help
"""
        try:
            await start_msg.edit_text(final_frame + beautiful_footer())
        except:
            pass
        await asyncio.sleep(0.3)

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 FULL HELP", callback_data="help_main"),
            InlineKeyboardButton("👑 ADMIN HELP", callback_data="help_admin")
        ],
        [
            InlineKeyboardButton("💬 PM BOT", url=f"https://t.me/{client.me.username}"),
            InlineKeyboardButton("⚡ QUICK START", callback_data="help_quickstart")
        ]
    ])

    try:
        await start_msg.edit_text(
            final_frame + beautiful_footer(),
            reply_markup=buttons
        )
    except:
        pass

    # ======== TRACK GROUP IN DATABASE (SAFE PLACE) ========
    try:
        cur.execute(
            """
            INSERT OR REPLACE INTO groups
            (chat_id, title, username, added_by, added_date)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                chat.id,
                chat.title or "",
                chat.username or "",
                user.id
            )
        )
        conn.commit()
        print(f"✅ Group {chat.id} added to broadcast database")
    except Exception as e:
        print(f"⚠️ Error adding group to DB: {e}")

# ================= ADDITIONAL ANIMATED CALLBACKS =================
@app.on_callback_query(filters.regex("^help_features$"))
async def features_tour_callback(client, callback_query):
    """Animated features tour"""
    
    features = [
        ("🔨", "Advanced Moderation", "Mute, ban, warn, kick with custom durations"),
        ("🛡️", "Smart Security", "Auto abuse detection, lock system, admin protection"),
        ("💬", "Support System", "24/7 ticket system with admin management"),
        ("🏷️", "Tagging Engine", "Efficient member tagging with cooldown system"),
        ("✨", "Beautiful UI", "Animated messages, progress bars, visual feedback"),
        ("⚡", "High Performance", "Fast response, minimal latency, optimized code"),
        ("👑", "Admin Management", "Multi-level admin system with permissions"),
        ("📊", "Analytics", "User statistics, command usage, group insights"),
        ("🎯", "Customization", "Welcome messages, rules, settings per group"),
        ("🔔", "Notifications", "Admin alerts, user reports, system updates")
    ]
    
    # Animate features one by one
    tour_text = f"""
{beautiful_header('sparkles')}

🎬 **PREMIUM FEATURES TOUR** 🎬

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✨ **Loading premium features...**
{progress_bar(10)}
"""
    
    tour_msg = await callback_query.message.edit_text(
        tour_text + beautiful_footer()
    )
    await callback_query.answer()
    
    # Animate each feature
    for i, (emoji, title, description) in enumerate(features):
        percentage = 10 + ((i + 1) * 9)
        
        tour_text = f"""
{beautiful_header('sparkles')}

🎬 **PREMIUM FEATURES TOUR** 🎬

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✨ **Loaded Features ({i+1}/{len(features)}):**

"""
        
        # Show previous features
        for j in range(i + 1):
            emj, ttl, desc = features[j]
            tour_text += f"✅ **{emj} {ttl}**\n   ↳ {desc}\n\n"
        
        if i < len(features) - 1:
            next_emoji, next_title, _ = features[i + 1]
            tour_text += f"⏳ **Loading:** {next_emoji} {next_title}...\n"
        
        tour_text += f"\n{progress_bar(percentage)}"
        
        await tour_msg.edit_text(tour_text + beautiful_footer())
        await asyncio.sleep(0.5)
    
    # Final screen
    final_tour = f"""
{beautiful_header('sparkles')}

🎉 **FEATURES TOUR COMPLETE!** 🎉

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✅ **All {len(features)} Premium Features Loaded:**

🔨 **Moderation Suite** - Complete user management
🛡️ **Security Layer** - Intelligent protection system
💬 **Support Network** - 24/7 help desk
🏷️ **Tagging System** - Efficient communication
✨ **UI Experience** - Beautiful animations
⚡ **Performance** - Lightning fast response
👑 **Admin Tools** - Multi-level control
📊 **Analytics** - Data-driven insights
🎯 **Customization** - Personalize everything
🔔 **Alerts** - Stay informed

🚀 **Ready to experience premium management?**
"""
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 GET STARTED", callback_data="help_main"),
            InlineKeyboardButton("👑 ADMIN PANEL", callback_data="help_admin")
        ],
        [
            InlineKeyboardButton("➕ ADD TO GROUP", 
                url=f"https://t.me/{client.me.username}?startgroup=true"),
            InlineKeyboardButton("🔙 BACK", callback_data="help_main")
        ]
    ])
    
    await tour_msg.edit_text(
        final_tour + beautiful_footer(),
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex("^help_quickstart$"))
async def quickstart_guide(client, callback_query):
    """Animated quick start guide"""
    
    steps = [
        ("1️⃣", "Add Bot", f"Add @{client.me.username} to your group"),
        ("2️⃣", "Make Admin", "Grant all admin permissions to bot"),
        ("3️⃣", "Setup Welcome", "Use /setwelcome for custom greeting"),
        ("4️⃣", "Set Rules", "Establish group rules using /rules"),
        ("5️⃣", "Test Commands", "Try /help to see all features"),
        ("6️⃣", "Manage Members", "Use /mute, /ban, /warn as needed"),
        ("7️⃣", "Enable Security", "Configure /lock and abuse detection"),
        ("8️⃣", "Enjoy Premium", "Experience seamless group management!")
    ]
    
    # Animate steps
    guide_text = f"""
{beautiful_header('guide')}

🚀 **QUICK START GUIDE** 🚀

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

📋 **Follow these steps to get started:**

{progress_bar(0)}
"""
    
    guide_msg = await callback_query.message.edit_text(
        guide_text + beautiful_footer()
    )
    await callback_query.answer()
    
    # Animate each step
    for i, (num, title, description) in enumerate(steps):
        percentage = (i + 1) * 12.5
        
        guide_text = f"""
{beautiful_header('guide')}

🚀 **QUICK START GUIDE** 🚀

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

📋 **Follow these steps to get started:**

"""
        
        # Show completed steps
        for j in range(i + 1):
            nm, ttl, desc = steps[j]
            guide_text += f"✅ **{nm} {ttl}**\n   ↳ {desc}\n\n"
        
        guide_text += f"\n{progress_bar(percentage)}"
        
        await guide_msg.edit_text(guide_text + beautiful_footer())
        await asyncio.sleep(0.4)
    
    # Final step with buttons
    final_guide = f"""
{beautiful_header('guide')}

🎉 **QUICK START COMPLETE!** 🎉

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✅ **You're all set up!** 

🚀 **Next Steps:**
• Explore `/help` for all commands
• Configure `/setwelcome` for members
• Set up `/lock` for security
• Try `/tagall` to test tagging
• Use `/purge` for cleanup

⚡ **Pro Tips:**
• Make bot admin with ALL permissions
• Set custom welcome messages
• Configure auto-moderation rules
• Use cooldowns for frequent commands
• Enable admin abuse protection

🎯 **Need Help?** PM the bot anytime!
"""
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📚 EXPLORE COMMANDS", callback_data="help_main"),
            InlineKeyboardButton("👑 ADMIN TOOLS", callback_data="help_admin")
        ],
        [
            InlineKeyboardButton("➕ ADD BOT TO GROUP", 
                url=f"https://t.me/{client.me.username}?startgroup=true"),
            InlineKeyboardButton("💬 GET SUPPORT", 
                url=f"https://t.me/{client.me.username}")
        ],
        [
            InlineKeyboardButton("⚙️ BOT SETTINGS", callback_data="help_settings"),
            InlineKeyboardButton("🔙 MAIN MENU", callback_data="help_main")
        ]
    ])
    
    await guide_msg.edit_text(
        final_guide + beautiful_footer(),
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex("^help_stats$"))
async def bot_stats_callback(client, callback_query):
    """Animated bot statistics"""
    
    # Calculate some stats (you can make these dynamic)
    uptime = get_uptime()
    
    # Create animated stats
    stats_text = f"""
{beautiful_header('stats')}

📊 **BOT STATISTICS** 📊

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

⚡ **Loading statistics...**
{progress_bar(10)}
"""
    
    stats_msg = await callback_query.message.edit_text(
        stats_text + beautiful_footer()
    )
    await callback_query.answer()
    
    # Animate stats loading
    stats_categories = [
        ("🕒 Uptime", uptime, 30),
        ("📈 Commands", "50+ available", 50),
        ("👥 Users", "Growing daily", 70),
        ("👑 Admins", f"{len(INITIAL_ADMINS)} bot admins", 85),
        ("🛡️ Security", f"{len(ABUSE_WORDS)} abuse words", 95),
        ("⚡ Performance", "Optimized & fast", 100)
    ]
    
    for title, value, percentage in stats_categories:
        stats_text = f"""
{beautiful_header('stats')}

📊 **BOT STATISTICS** 📊

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

"""
        
        # Add loaded stats
        for cat_title, cat_value, cat_percent in stats_categories:
            if cat_percent <= percentage:
                stats_text += f"✅ **{cat_title}:** {cat_value}\n"
            else:
                break
        
        stats_text += f"\n{progress_bar(percentage)}"
        
        await stats_msg.edit_text(stats_text + beautiful_footer())
        await asyncio.sleep(0.3)
    
    # Final stats with buttons
    final_stats = f"""
{beautiful_header('stats')}

📊 **BOT STATISTICS** 📊

🤖 **{BOT_BRAND}**
{BOT_TAGLINE}

✅ **System Status:**
• 🕒 **Uptime:** {uptime}
• 📈 **Commands:** 50+ available
• 👥 **Users:** Growing daily
• 👑 **Admins:** {len(INITIAL_ADMINS)} bot admins
• 🛡️ **Security:** {len(ABUSE_WORDS)} abuse words
• ⚡ **Performance:** Optimized & fast
• 💎 **Features:** 10+ categories
• 🚀 **Version:** 2.0 Premium

🎯 **Premium Metrics:**
• 99.9% Uptime guarantee
• <100ms response time
• Multi-group support
• 24/7 active monitoring
• Regular updates
• Priority support

✨ **Your premium experience is active!**
"""
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 REFRESH STATS", callback_data="help_stats"),
            InlineKeyboardButton("📊 MORE ANALYTICS", callback_data="help_analytics")
        ],
        [
            InlineKeyboardButton("⚙️ SYSTEM SETTINGS", callback_data="help_settings"),
            InlineKeyboardButton("🔙 MAIN MENU", callback_data="help_main")
        ]
    ])
    
    await stats_msg.edit_text(
        final_stats + beautiful_footer(),
        reply_markup=buttons
    )

# ================= MANUAL ADD COMMANDS =================
@app.on_message(filters.command("adduser") & filters.private)
async def add_user_manually(client, message):
    """Manually add a user to database"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: `/adduser user_id`")
        return
    
    try:
        user_id = int(message.command[1])
        
        try:
            user = await client.get_users(user_id)
            username = user.username
            first_name = user.first_name
            last_name = user.last_name
        except:
            username = "unknown"
            first_name = "Unknown"
            last_name = "User"
        
        cur.execute("""
            INSERT OR REPLACE INTO users 
            (user_id, username, first_name, last_name) 
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, last_name))
        conn.commit()
        
        await message.reply_text(f"✅ User {user_id} added to database!")
        
    except ValueError:
        await message.reply_text("❌ Invalid user ID!")

@app.on_message(filters.command("addgroup") & filters.private)
async def add_group_manually(client, message):
    """Manually add a group to database"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    if len(message.command) < 2:
        await message.reply_text("Usage: `/addgroup chat_id`")
        return
    
    try:
        chat_id = int(message.command[1])
        
        try:
            chat = await client.get_chat(chat_id)
            title = chat.title
            username = chat.username
        except:
            title = "Unknown Group"
            username = None
        
        cur.execute("""
            INSERT OR REPLACE INTO groups 
            (chat_id, title, username, added_by) 
            VALUES (?, ?, ?, ?)
        """, (chat_id, title, username, message.from_user.id))
        conn.commit()
        
        await message.reply_text(f"✅ Group {chat_id} added to database!")
        
    except ValueError:
        await message.reply_text("❌ Invalid chat ID!")

# ================= LIST COMMANDS =================
@app.on_message(filters.command("listusers") & filters.private)
async def list_users(client, message):
    """List all users in database"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    
    if total == 0:
        await message.reply_text("📭 No users in database!")
        return
    
    cur.execute("SELECT user_id, username, first_name, last_active FROM users ORDER BY last_active DESC LIMIT 20")
    users = cur.fetchall()
    
    text = f"👥 **Users in Database ({total} total)**\n\n"
    
    for user_id, username, first_name, last_active in users:
        username_display = f"@{username}" if username else "No username"
        text += f"• `{user_id}` - {first_name} ({username_display})\n"
    
    await message.reply_text(text)

@app.on_message(filters.command("listgroups") & filters.private)
async def list_groups(client, message):
    """List all groups in database"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    cur.execute("SELECT COUNT(*) FROM groups")
    total = cur.fetchone()[0]
    
    if total == 0:
        await message.reply_text("📭 No groups in database!")
        return
    
    cur.execute("SELECT chat_id, title, username FROM groups ORDER BY added_date DESC LIMIT 20")
    groups = cur.fetchall()
    
    text = f"👥 **Groups in Database ({total} total)**\n\n"
    
    for chat_id, title, username in groups:
        username_display = f"@{username}" if username else "No username"
        text += f"• `{chat_id}` - {title} ({username_display})\n"
    
    await message.reply_text(text)

# ================= BROADCAST STATS COMMAND =================
@app.on_message(filters.command("broadcaststats") & filters.private)
async def broadcast_stats(client, message):
    """Show broadcast statistics"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    # User count
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    # Group count
    cur.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]
    
    # Total recipients
    total_recipients = user_count + group_count
    
    # Broadcast history
    cur.execute("SELECT COUNT(*) FROM broadcast_history")
    broadcast_count = cur.fetchone()[0]
    
    cur.execute("SELECT SUM(sent_count), SUM(failed_count) FROM broadcast_history")
    result = cur.fetchone()
    total_sent = result[0] or 0
    total_failed = result[1] or 0
    
    stats_text = f"""
📊 **Broadcast Statistics**

👤 **Users:** {user_count}
👥 **Groups:** {group_count}
📋 **Total Recipients:** {total_recipients}

📨 **Broadcast History:**
• Total Broadcasts: {broadcast_count}
• Total Messages Sent: {total_sent}
• Total Failed: {total_failed}
• Success Rate: {(total_sent/(total_sent+total_failed)*100 if (total_sent+total_failed) > 0 else 0):.1f}%

💡 **Tips:**
1. Users are auto-added when they PM bot
2. Groups are auto-added when bot is used
3. Use `/adduser` or `/addgroup` to add manually
4. Use `/listusers` or `/listgroups` to view
    """
    
    await message.reply_text(stats_text)

# ================= ENHANCED BROADCAST COMMAND =================
# ================= FIXED BROADCAST BUTTON SYSTEM =================

# Step 1: Ensure proper imports
import asyncio
from pyrogram.types import CallbackQuery

# Step 2: Store temporary broadcast data
broadcast_sessions = {}

# Step 3: Fixed Broadcast Command
@app.on_message(filters.command(["broadcast", "bc"]) & filters.private)
async def broadcast_command_fixed(client, message):
    """Fixed broadcast command with working buttons"""
    
    # Check if user is bot admin
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Only bot admins can use this command!")
        return
    
    # Check if replied to a message
    if not message.reply_to_message:
        help_text = """
📢 **BROADCAST COMMAND**

**Usage:**
1. Reply to any message (text/photo/video)
2. Type `/broadcast [target]`

**Targets:**
• `all` - All users + groups
• `pm` - PM users only
• `groups` - Groups only
• `support` - Support users only

**Example:** Reply + `/broadcast all`

**Other Commands:**
• `/listusers` - View all users
• `/listgroups` - View all groups
• `/testbc` - Test broadcast system
        """
        await message.reply_text(help_text)
        return
    
    # Check target
    if len(message.command) < 2:
        await message.reply_text("❌ Please specify target: `/broadcast all` or `/broadcast pm` etc.")
        return
    
    target = message.command[1].lower()
    valid_targets = ["all", "pm", "groups", "support"]
    
    if target not in valid_targets:
        await message.reply_text(f"❌ Invalid target! Use: {', '.join(valid_targets)}")
        return
    
    # Get counts for confirmation
    user_count = 0
    group_count = 0
    
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]
    
    # Calculate expected recipients
    if target == "all":
        expected = user_count + group_count
    elif target == "pm":
        expected = user_count
    elif target == "groups":
        expected = group_count
    elif target == "support":
        cur.execute("SELECT COUNT(DISTINCT user_id) FROM contact_history")
        expected = cur.fetchone()[0]
    
    if expected == 0:
        await message.reply_text(
            f"❌ No {target} found in database!\n\n"
            f"Use `/testbc` to add test users first."
        )
        return
    
    # Store broadcast session
    session_id = f"{message.from_user.id}_{message.id}"
    broadcast_sessions[session_id] = {
        "target": target,
        "message": message.reply_to_message,
        "admin": message.from_user,
        "expected": expected
    }
    
    # Get target name for display
    target_names = {
        "all": "All Users & Groups",
        "pm": "PM Users Only",
        "groups": "Groups Only",
        "support": "Support Users Only"
    }
    
    # Create confirmation message with working buttons
    confirm_text = f"""
⚠️ **Confirm Broadcast**

**Target:** {target_names[target]}
**Expected Recipients:** {expected}
**From:** {message.from_user.mention}
**Message Type:** {'Media' if message.reply_to_message.media else 'Text'}

**Are you sure you want to send this to {expected} recipients?**
    """
    
    # Create proper inline keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ YES, SEND NOW", callback_data=f"confirm_bc:{session_id}"),
        ],
        [
            InlineKeyboardButton("❌ CANCEL", callback_data=f"cancel_bc:{session_id}"),
            InlineKeyboardButton("📊 VIEW STATS", callback_data=f"stats_bc:{session_id}")
        ]
    ])
    
    confirm_msg = await message.reply_text(
        confirm_text,
        reply_markup=keyboard
    )
    
    # Store confirmation message ID
    broadcast_sessions[session_id]["confirm_msg_id"] = confirm_msg.id

# Step 4: Working Callback Handlers
@app.on_callback_query()
async def handle_all_callbacks(client, callback_query: CallbackQuery):
    """Handle all callback queries"""
    
    data = callback_query.data
    
    # Broadcast confirm handler
    if data.startswith("confirm_bc:"):
        await handle_broadcast_confirm(client, callback_query)
    
    # Broadcast cancel handler
    elif data.startswith("cancel_bc:"):
        await handle_broadcast_cancel(client, callback_query)
    
    # Broadcast stats handler
    elif data.startswith("stats_bc:"):
        await handle_broadcast_stats(client, callback_query)
    
    # Test broadcast handler
    elif data == "test_broadcast":
        await handle_test_broadcast(client, callback_query)
    
    # History handler
    elif data == "bc_history":
        await handle_broadcast_history(client, callback_query)
    
    # Back handler
    elif data == "bc_back":
        await handle_broadcast_back(client, callback_query)

async def handle_broadcast_confirm(client, callback_query):
    """Handle broadcast confirmation"""
    
    session_id = callback_query.data.split(":")[1]
    session_data = broadcast_sessions.get(session_id)
    
    if not session_data:
        await callback_query.answer("Session expired!", show_alert=True)
        return
    
    await callback_query.answer("Starting broadcast...")
    
    # Update message to show "Starting..."
    await callback_query.message.edit_text(
        "📤 **Starting Broadcast...**\n\n"
        "Please wait while we collect recipients...",
        reply_markup=None
    )
    
    # Get data from session
    target = session_data["target"]
    original_msg = session_data["message"]
    admin = session_data["admin"]
    expected = session_data["expected"]
    
    # Get recipients
    recipients = await get_recipients_list(target)
    
    if not recipients:
        await callback_query.message.edit_text(
            "❌ **No Recipients Found!**\n\n"
            "No users/groups found in database.\n"
            "Use `/testbc` to add test users first."
        )
        return
    
    total = len(recipients)
    sent = 0
    failed = 0
    
    # Show progress
    progress_msg = await callback_query.message.edit_text(
        f"📤 **Broadcasting...**\n\n"
        f"Target: {target}\n"
        f"Total: {total} recipients\n"
        f"Progress: {progress_bar(0)}\n"
        f"✅ Sent: 0/{total}\n"
        f"❌ Failed: 0"
    )
    
    # Send messages
    for i, chat_id in enumerate(recipients):
        try:
            if original_msg.text:
                await client.send_message(chat_id, original_msg.text)
            elif original_msg.photo:
                await client.send_photo(
                    chat_id,
                    original_msg.photo.file_id,
                    caption=original_msg.caption or ""
                )
            elif original_msg.video:
                await client.send_video(
                    chat_id,
                    original_msg.video.file_id,
                    caption=original_msg.caption or ""
                )
            elif original_msg.document:
                await client.send_document(
                    chat_id,
                    original_msg.document.file_id,
                    caption=original_msg.caption or ""
                )
            else:
                await original_msg.copy(chat_id)
            
            sent += 1
            
            # Update progress every 5 messages or at end
            if i % 5 == 0 or i == total - 1:
                percentage = int((i + 1) / total * 100)
                await progress_msg.edit_text(
                    f"📤 **Broadcasting...**\n\n"
                    f"Target: {target}\n"
                    f"Total: {total} recipients\n"
                    f"Progress: {progress_bar(percentage)}\n"
                    f"✅ Sent: {sent}/{total}\n"
                    f"❌ Failed: {failed}"
                )
            
            # Small delay
            await asyncio.sleep(0.1)
            
        except Exception as e:
            failed += 1
    
    # Save to history
    message_type = "text"
    caption = original_msg.text or ""
    file_id = ""
    
    if original_msg.photo:
        message_type = "photo"
        file_id = original_msg.photo.file_id
        caption = original_msg.caption or ""
    elif original_msg.video:
        message_type = "video"
        file_id = original_msg.video.file_id
        caption = original_msg.caption or ""
    
    cur.execute("""
        INSERT INTO broadcast_history 
        (admin_id, target, message_type, caption, file_id, sent_count, failed_count) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (admin.id, target, message_type, caption, file_id, sent, failed))
    conn.commit()
    
    # Show completion
    success_rate = (sent / total * 100) if total > 0 else 0
    broadcast_id = cur.lastrowid
    
    completion_text = f"""
✅ **Broadcast Completed!**

📊 **Statistics:**
• **Target:** {target}
• **Total Recipients:** {total}
• **Successfully Sent:** {sent}
• **Failed:** {failed}
• **Success Rate:** {success_rate:.1f}%
• **Broadcast ID:** #{broadcast_id}

👤 **Admin:** {admin.mention}
🕒 **Time:** {datetime.now().strftime('%I:%M %p')}
    """
    
    # Create completion buttons
    completion_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 SEND AGAIN", callback_data="test_broadcast"),
            InlineKeyboardButton("📋 HISTORY", callback_data="bc_history")
        ],
        [
            InlineKeyboardButton("📊 STATS", callback_data=f"stats_bc:{session_id}"),
            InlineKeyboardButton("🏠 HOME", callback_data="bc_back")
        ]
    ])
    
    await progress_msg.edit_text(
        completion_text,
        reply_markup=completion_buttons
    )
    
    # Clean up session
    if session_id in broadcast_sessions:
        del broadcast_sessions[session_id]

async def handle_broadcast_cancel(client, callback_query):
    """Handle broadcast cancellation"""
    
    session_id = callback_query.data.split(":")[1]
    
    await callback_query.answer("Broadcast cancelled!")
    
    await callback_query.message.edit_text(
        "❌ **Broadcast Cancelled**\n\n"
        "The broadcast has been cancelled."
    )
    
    # Clean up session
    if session_id in broadcast_sessions:
        del broadcast_sessions[session_id]

async def handle_broadcast_stats(client, callback_query):
    """Show broadcast statistics"""
    
    session_id = callback_query.data.split(":")[1]
    session_data = broadcast_sessions.get(session_id)
    
    if not session_data:
        await callback_query.answer("Session expired!", show_alert=True)
        return
    
    # Get counts
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM broadcast_history")
    bc_count = cur.fetchone()[0]
    
    stats_text = f"""
📊 **Broadcast Statistics**

👤 **Users in DB:** {user_count}
👥 **Groups in DB:** {group_count}
📨 **Total Broadcasts:** {bc_count}

📋 **Current Session:**
• Target: {session_data['target']}
• Expected: {session_data['expected']} recipients

💡 **Tip:** Use `/listusers` to see all users
    """
    
    await callback_query.answer()
    
    # Create back button
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 BACK", callback_data=f"back_to_confirm:{session_id}")]
    ])
    
    await callback_query.message.edit_text(
        stats_text,
        reply_markup=buttons
    )

async def handle_test_broadcast(client, callback_query):
    """Handle test broadcast button"""
    
    await callback_query.answer("Adding test users...")
    
    # Add current user
    user_id = callback_query.from_user.id
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (user_id, callback_query.from_user.first_name))
    
    # Add SUPER_ADMIN
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (SUPER_ADMIN, "Super Admin"))
    
    # Add 2 test users
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (999888777, "Test User 1"))
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (888777666, "Test User 2"))
    
    conn.commit()
    
    await callback_query.message.edit_text(
        "✅ **Test Users Added!**\n\n"
        "Added 4 test users to database.\n\n"
        "Now reply to a message and use:\n"
        "`/broadcast pm`\n\n"
        "Or click the button below to send a test message:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 SEND TEST BROADCAST", callback_data="send_test_bc")]
        ])
    )

async def handle_broadcast_history(client, callback_query):
    """Show broadcast history"""
    
    cur.execute("""
        SELECT id, target, sent_count, failed_count, timestamp 
        FROM broadcast_history 
        ORDER BY id DESC 
        LIMIT 5
    """)
    history = cur.fetchall()
    
    if not history:
        text = "📭 **No broadcast history found!**"
    else:
        text = "📋 **Last 5 Broadcasts:**\n\n"
        for row in history:
            bc_id, target, sent, failed, timestamp = row
            total = sent + failed
            rate = (sent/total*100) if total > 0 else 0
            text += f"**#{bc_id}** - {target}\n"
            text += f"✅ {sent} | ❌ {failed} | 📊 {rate:.1f}%\n"
            text += f"🕒 {timestamp}\n━━━━━━━━━━\n"
    
    await callback_query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 BACK", callback_data="bc_back")]
        ])
    )

async def handle_broadcast_back(client, callback_query):
    """Go back to main menu"""
    
    await callback_query.message.edit_text(
        "🏠 **Broadcast System**\n\n"
        "Available commands:\n"
        "• `/broadcast [target]` - Send broadcast\n"
        "• `/testbc` - Add test users\n"
        "• `/listusers` - View users\n"
        "• `/listgroups` - View groups\n\n"
        "**Usage:** Reply to message + `/broadcast pm`",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📤 TEST BROADCAST", callback_data="test_broadcast"),
                InlineKeyboardButton("📋 HISTORY", callback_data="bc_history")
            ]
        ])
    )

async def get_recipients_list(target):
    """Get list of recipients based on target"""
    
    recipients = []
    
    if target == "all":
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        recipients.extend([uid[0] for uid in users])
        
        cur.execute("SELECT chat_id FROM groups")
        groups = cur.fetchall()
        recipients.extend([gid[0] for gid in groups])
    
    elif target == "pm":
        cur.execute("SELECT user_id FROM users")
        users = cur.fetchall()
        recipients.extend([uid[0] for uid in users])
    
    elif target == "groups":
        cur.execute("SELECT chat_id FROM groups")
        groups = cur.fetchall()
        recipients.extend([gid[0] for gid in groups])
    
    elif target == "support":
        cur.execute("SELECT DISTINCT user_id FROM contact_history")
        users = cur.fetchall()
        recipients.extend([uid[0] for uid in users])
    
    # Remove duplicates and invalid IDs
    recipients = list(set([rid for rid in recipients if rid and rid > 0]))
    return recipients

# Step 5: TEST BROADCAST COMMAND (Quick fix)
@app.on_message(filters.command("testbc") & filters.private)
async def test_broadcast_fixed(client, message):
    """Test broadcast system"""
    
    if not is_bot_admin(message.from_user.id):
        return
    
    # Add test users
    added = []
    
    # Add current user
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (message.from_user.id, message.from_user.first_name))
    added.append(message.from_user.id)
    
    # Add SUPER_ADMIN
    cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
               (SUPER_ADMIN, "Super Admin"))
    added.append(SUPER_ADMIN)
    
    # Add some dummy users
    test_users = [
        (111222333, "Test User 1"),
        (222333444, "Test User 2"),
        (333444555, "Test User 3")
    ]
    
    for user_id, name in test_users:
        cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
                   (user_id, name))
        added.append(user_id)
    
    conn.commit()
    
    # Show test message with button
    await message.reply_text(
        f"✅ **Added {len(added)} test users!**\n\n"
        f"User IDs: {', '.join(map(str, added[:3]))}...\n\n"
        "**Now you can:**\n"
        "1. Reply to any message\n"
        "2. Type `/broadcast pm`\n"
        "3. Click YES to send\n\n"
        "Or send a test message now:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 SEND TEST MESSAGE", callback_data="send_test_bc")]
        ])
    )

# Step 6: SEND TEST BROADCAST BUTTON HANDLER
@app.on_callback_query(filters.regex("^send_test_bc$"))
async def send_test_broadcast(client, callback_query):
    """Send a test broadcast"""
    
    await callback_query.answer("Sending test message...")
    
    # Send a test message to yourself
    try:
        await client.send_message(
            callback_query.from_user.id,
            "📢 **Test Broadcast**\n\n"
            "This is a test broadcast message!\n"
            "✅ Broadcast system is working correctly.\n\n"
            "Now you can use `/broadcast pm` to send to all users."
        )
        
        await callback_query.message.edit_text(
            "✅ **Test message sent to you!**\n\n"
            "Check your PM for the test message.\n\n"
            "**Next step:**\n"
            "1. Reply to any message\n"
            "2. Type `/broadcast pm`\n"
            "3. Confirm and send!"
        )
        
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ **Error:** {str(e)[:100]}"
        )

# Step 7: SIMPLE LIST COMMANDS
@app.on_message(filters.command("listusers") & filters.private)
async def list_users_simple(client, message):
    """Simple list users command"""
    
    if not is_bot_admin(message.from_user.id):
        return
    
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    
    if total == 0:
        await message.reply_text("📭 No users found!\nUse `/testbc` to add test users.")
        return
    
    cur.execute("SELECT user_id, first_name FROM users LIMIT 20")
    users = cur.fetchall()
    
    text = f"👥 **Users in Database ({total} total)**\n\n"
    for user_id, first_name in users:
        text += f"• `{user_id}` - {first_name}\n"
    
    if total > 20:
        text += f"\n... and {total-20} more users"
    
    await message.reply_text(text)

@app.on_message(filters.command("listgroups") & filters.private)
async def list_groups_simple(client, message):
    """Simple list groups command"""
    
    if not is_bot_admin(message.from_user.id):
        return
    
    cur.execute("SELECT COUNT(*) FROM groups")
    total = cur.fetchone()[0]
    
    if total == 0:
        await message.reply_text("📭 No groups found!\nAdd bot to groups to track them.")
        return
    
    cur.execute("SELECT chat_id, title FROM groups LIMIT 10")
    groups = cur.fetchall()
    
    text = f"👥 **Groups in Database ({total} total)**\n\n"
    for chat_id, title in groups:
        text += f"• `{chat_id}` - {title}\n"
    
    await message.reply_text(text)




# Step 9: CLEANUP FUNCTION (optional)
async def cleanup_broadcast_sessions():
    """Clean up old broadcast sessions"""
    while True:
        try:
            current_time = time.time()
            sessions_to_delete = []
            
            for session_id, session_data in list(broadcast_sessions.items()):
                # Remove sessions older than 1 hour
                if "created_at" in session_data:
                    if current_time - session_data["created_at"] > 3600:
                        sessions_to_delete.append(session_id)
            
            for session_id in sessions_to_delete:
                del broadcast_sessions[session_id]
            
            await asyncio.sleep(300)  # Check every 5 minutes
            
        except Exception as e:
            print(f"Cleanup error: {e}")
            await asyncio.sleep(60)


# ================= QUICK ADD BOT USERS =================
@app.on_message(filters.command("quickadd") & filters.private)
async def quick_add_users(client, message):
    """Quickly add bot admins and known users to database"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Admin only!")
        return
    
    added_count = 0
    
    # Add all bot admins
    cur.execute("SELECT admin_id FROM admins")
    admins = cur.fetchall()
    
    for (admin_id,) in admins:
        try:
            user = await client.get_users(admin_id)
            cur.execute("""
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, last_name) 
                VALUES (?, ?, ?, ?)
            """, (admin_id, user.username, user.first_name, user.last_name))
            added_count += 1
        except:
            pass
    
    # Add SUPER_ADMIN
    try:
        user = await client.get_users(SUPER_ADMIN)
        cur.execute("""
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name) 
            VALUES (?, ?, ?, ?)
        """, (SUPER_ADMIN, user.username, user.first_name, user.last_name))
        added_count += 1
    except:
        pass
    
    conn.commit()
    
    await message.reply_text(f"✅ Added {added_count} users to database!\n\nNow use `/broadcast pm` to test.")


# ================= TEST BROADCAST COMMAND =================
@app.on_message(filters.command("testbroadcast") & filters.private)
async def test_broadcast(client, message):
    """Test broadcast with dummy data"""
    
    if not is_bot_admin(message.from_user.id):
        return
    
    # Add some dummy users if database empty
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        # Add current user
        cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
                   (message.from_user.id, message.from_user.first_name))
        
        # Add bot admins
        for admin_id in INITIAL_ADMINS[:3]:  # First 3 admins
            cur.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)",
                       (admin_id, f"Test Admin {admin_id}"))
        
        conn.commit()
        await message.reply_text("✅ Added test users. Now try `/broadcast pm`")
    else:
        await message.reply_text("✅ Database already has users. Use `/broadcast pm` to test.")


@app.on_message(filters.command("adminabuse") & filters.group)
async def admin_abuse_toggle(client, message: Message):

    chat_id = message.chat.id
    user_id = message.from_user.id

    # 🔐 Only owner or bot admin
    if user_id not in INITIAL_ADMINS:
        try:
            m = await client.get_chat_member(chat_id, user_id)
            if m.status != ChatMemberStatus.OWNER:
                return await message.reply("❌ **Only owner can control this setting**")
        except:
            return

    global ADMIN_ABUSE_ENABLED

    if len(message.command) < 2:
        return await message.reply("⚙️ Use: `/adminabuse on | off | status`")

    arg = message.command[1].lower()

    if arg == "on":
        ADMIN_ABUSE_ENABLED = True
        return await message.reply("✅ **Admin abuse system ENABLED**")

    if arg == "off":
        ADMIN_ABUSE_ENABLED = False
        return await message.reply("🚫 **Admin abuse system DISABLED**")

    if arg == "status":
        status = "ON ✅" if ADMIN_ABUSE_ENABLED else "OFF 🚫"
        return await message.reply(f"⚙️ **Admin abuse system:** {status}")

# ============================ Footer ============================
def footer(text):
    return f"""{text}

━━━━━━━━━━━━━━━━━━
🤖 {BOT_BRAND}
✨ {BOT_TAGLINE}
━━━━━━━━━━━━━━━━━━"""


@app.on_message(filters.group & filters.text, group=3)
async def admin_abuse_delete_handler(client, message: Message):

    if not ADMIN_ABUSE_ENABLED:
        return
        
    user = message.from_user
    if not user or user.is_bot:
        return

    chat_id = message.chat.id
    text = message.text.lower()

    # ✅ Only admins
    if not await is_any_admin(client, chat_id, user.id):
        return

    # ❌ No abuse word
    if not ABUSE_REGEX.search(message.text):
        return

    # ===== DELETE MESSAGE =====
    try:
        await message.delete()
    except:
        pass

    role = "Bot Admin " if user.id in INITIAL_ADMINS else "Admin 🛡"

    card = ADMIN_ABUSE_CARD.format(
        admin=user.mention,
        role=role,
        user_id=user.id,
        chat_id=chat_id,
        time=datetime.now().strftime("%d %b %Y • %I:%M %p")
    )

    await client.send_message(
        chat_id,
        card,
        disable_web_page_preview=True
    )


MUTE_TIME = 600  # 10 minutes

@app.on_message(filters.group & filters.text, group=4)
async def final_auto_abuse_handler(client, message):
    if not message.from_user:
        return

    if not ABUSE_REGEX.search(message.text):
        return

    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id

    # ===== IMMUNITY =====
    try:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            return
    except:
        pass

    if is_bot_admin(user_id):  # Bot admin / super admin
        return

    # ===== DELETE ABUSE MESSAGE =====
    try:
        await message.delete()
    except:
        pass

    # ===== WARN COUNT =====
    warns = add_warn(chat_id, user_id)

    # ===== ACTIONS =====
    if warns == 1:
        await message.reply_text(
            f"{beautiful_header('WARNING')}\n\n"
            f"⚠️ **WARNING 1/5**\n"
            f"👤 {user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"🚫 Abuse language is not allowed"
            f"{beautiful_footer()}"
        )

    elif warns == 2:
        await message.reply_text(
            f"{beautiful_header('WARNING')}\n\n"
            f"⚠️ **WARNING 2/5**\n"
            f"👤 {user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"🚫 Abuse language is not allowed"
            f"{beautiful_footer()}"
        )

    elif warns == 3:
        await message.reply_text(
            f"{beautiful_header('WARNING')}\n\n"
            f"⚠️ **WARNING 2/5**\n"
            f"👤 {user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"🚫 Abuse language is not allowed\n Next Warning As You Mute 🔕"
            f"{beautiful_footer()}"
        )
        
    elif warns == 4:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(seconds=MUTE_TIME)
        )

        save_mute(chat_id, user_id, MUTE_TIME)

        await message.reply_text(
            f"{beautiful_header('ABUSE WORDS')}\n\n"
            f"🔇 **MUTED (10 MINUTES)**\n"
            f"👤 {user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"❌ Reason: Repeated abuse (4/5)\n Last Warning Other Wise You Ban 🚫"
            f"{beautiful_footer()}"
        )

    elif warns >= 5:
        await client.ban_chat_member(chat_id, user_id)
        reset_warn(chat_id, user_id)

        await message.reply_text(
            f"{beautiful_header('ABUSE WORDS')}\n\n"
            f"🚫 **BANNED**\n"
            f"👤 {user.mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"❌ Reason: Repeated abuse (5/5)"
            f"{beautiful_footer()}"
        )


async def check_mutes_task():
    """Auto-unmute users after duration (including abuse mutes)"""
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            
            for chat_id in list(user_mutes.keys()):
                for user_id in list(user_mutes[chat_id].keys()):
                    unmute_time = user_mutes[chat_id][user_id]
                    
                    if current_time >= unmute_time:
                        try:
                            await app.restrict_chat_member(
                                chat_id=chat_id,
                                user_id=user_id,
                                permissions=ChatPermissions(
                                    can_send_messages=True,
                                    can_send_media_messages=True,
                                    can_send_other_messages=True,
                                    can_add_web_page_previews=True,
                                    can_send_polls=True,
                                    can_change_info=False,
                                    can_invite_users=True,
                                    can_pin_messages=False
                                )
                            )
                            
                            # Notify user about auto-unmute
                            try:
                                await app.send_message(
                                    user_id,
                                    f"{beautiful_header('support')}\n\n"
                                    f"⏰ **Auto-unmute Complete**\n\n"
                                    f"Your mute duration has ended.\n"
                                    f"You can now send messages in the group.\n\n"
                                    f"Please follow group rules."
                                    f"{beautiful_footer()}"
                                )
                            except:
                                pass
                            
                            del user_mutes[chat_id][user_id]
                            
                        except Exception as e:
                            print(f"Error auto-unmuting: {e}")
        
        except Exception as e:
            print(f"Error in check_mutes_task: {e}")
        
        await asyncio.sleep(60)  # Check every minute
        

    
# ================= SUPPORT SYSTEM =================


# ================= ADMIN ADD / REMOVE =================
@app.on_message(filters.command("addadmin") & filters.private)
async def add_admin(client, message: Message):
    if message.from_user.id != SUPER_ADMIN:
        return
    uid = int(message.command[1])
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))
    conn.commit()
    await message.reply_text(f"✅ `{uid}` added as admin")

@app.on_message(filters.command("removeadmin") & filters.private)
async def remove_admin(client, message: Message):
    if message.from_user.id != SUPER_ADMIN:
        return
    uid = int(message.command[1])
    if uid == SUPER_ADMIN:
        return
    cur.execute("DELETE FROM admins WHERE admin_id=?", (uid,))
    conn.commit()
    await message.reply_text(f"🚫 `{uid}` removed from admins")

# ================= CSV EXPORT =================
@app.on_message(filters.command("exportcsv") & filters.private)
async def export_csv(client, message: Message):
    if not is_admin(message.from_user.id):
        return

    cur.execute("SELECT DISTINCT user_id FROM contact_history")
    users = cur.fetchall()

    with open("users.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id"])
        for u in users:
            w.writerow(u)

    cur.execute("SELECT user_id,sender,message_type,content,timestamp FROM contact_history")
    rows = cur.fetchall()

    with open("chat_history.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id","sender","type","content","timestamp"])
        for r in rows:
            w.writerow(r)

    await client.send_document(message.chat.id, "users.csv")
    await client.send_document(message.chat.id, "chat_history.csv")

    os.remove("users.csv")
    os.remove("chat_history.csv")


async def start_background_tasks():
    """Start all background tasks"""
    tasks = [
        check_mutes_task(),
        cleanup_abuse_cache_task(), # Add this line
        cleanup_broadcast_sessions(),
    ]
    
    for task in tasks:
        asyncio.create_task(task)


# ================= MAIN EXECUTION =================
if __name__ == "__main__":
    print("=" * 50)
    print(f"🤖 {BOT_BRAND}")
    print(f"✨ {BOT_TAGLINE}")
    print("=" * 50)
    
    # Initialize all tables
    init_broadcast_tables()
    initialize_admins()
    
    # Show counts
    cur.execute("SELECT COUNT(*) FROM users")
    user_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM groups")
    group_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM admins")
    admin_count = cur.fetchone()[0]
    
    print(f"📊 Database initialized:")
    print(f"   👤 Users: {user_count}")
    print(f"   👥 Groups: {group_count}")
    print(f"   👑 Admins: {admin_count}")
    print("=" * 50)
    
    # Tips for user
    print("💡 **Broadcast System Ready!**")
    print("To use broadcast:")
    print("1. First, PM the bot (auto-adds you to users)")
    print("2. Or use `/quickadd` to add bot admins")
    print("3. Then reply to message + `/broadcast pm`")
    print("=" * 50)
    
    
    
    
    # Create event loop
    loop = asyncio.get_event_loop()
    
    # Start background tasks
    try:
        loop.create_task(start_background_tasks())
        print("✅ Background tasks initialized")
    except Exception as e:
        print(f"⚠️ Could not start background tasks: {e}")
    
    # Run the bot
    print("🚀 Starting bot...")
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
