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
from pyrogram.errors import PeerIdInvalid
from pyrogram.enums import ChatAction, ChatMemberStatus
from pyrogram.errors import FloodWait
import time
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

# ================= CONFIG =================
API_ID = 32310443
API_HASH = "c356e2c32fca6e1ad119d5ea7134ae88"
BOT_TOKEN = "8558150478:AAGeNAXetoEx7qTNKrsqMAr3HaXVvCDBkyI"

SUPER_ADMIN = 6748792256  # Main super admin
BOT_BRAND = "Ankit Shakya Support"
BOT_TAGLINE = "Fast • Secure • Reliable"
DB_FILE = "support.db"

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
# ================= DATABASE SETUP ======================
# ======================================================


conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# ======================================================
# ================== BOT ADMINS ========================
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS admins (
    admin_id INTEGER PRIMARY KEY
)
""")

# Super admin (safe insert)
cur.execute(
    "INSERT OR IGNORE INTO admins (admin_id) VALUES (?)",
    (SUPER_ADMIN,)
)

# ======================================================
# ================= BLOCKED USERS ======================
# (PM support block)
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS blocked_users (
    user_id INTEGER PRIMARY KEY
)
""")

# ======================================================
# ================= SUPPORT CHAT HISTORY ===============
# (User ↔ Admin messages)
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS contact_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    sender TEXT,              -- 'user' / 'admin'
    message_type TEXT,        -- 'text' / 'media'
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# ======================================================
# ================= AUTO REPLY TRACKER =================
# (First PM auto-reply)
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS auto_reply_sent (
    user_id INTEGER PRIMARY KEY
)
""")

# ======================================================
# ================= ADMIN REPLY MODE ===================
# (Inline support reply target)
# ======================================================
cur.execute("""
CREATE TABLE IF NOT EXISTS admin_reply_target (
    admin_id INTEGER PRIMARY KEY,
    user_id INTEGER
)
""")

# ======================================================
# ================= ABUSE / WARN SYSTEM ================
# (GROUP-WISE — ACTIVE TABLE)
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
# ================= MUTE SCHEDULER =====================
# (Auto-unmute)
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
    status TEXT DEFAULT 'pending',   -- pending / resolved / rejected
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


cur.execute("""
CREATE TABLE IF NOT EXISTS tag_cooldown (
    chat_id INTEGER,
    user_id INTEGER,
    last_tag INTEGER,
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

# =========================== admin mention ==========================================

cur.execute("""
CREATE TABLE IF NOT EXISTS admin_ping_cooldown (
    chat_id INTEGER,
    user_id INTEGER,
    last_ping INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")

# ======================================================
# Tag cooldown
cur.execute("""
CREATE TABLE IF NOT EXISTS tag_cooldown (
    chat_id INTEGER,
    user_id INTEGER,
    last_time INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")

# Tag cancel
cur.execute("""
CREATE TABLE IF NOT EXISTS tag_cancel (
    chat_id INTEGER,
    admin_id INTEGER,
    cancelled INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, admin_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS cooldown (
    user_id INTEGER PRIMARY KEY,
    last_used INTEGER
)
""")


# ================= INDEXES =============================
# ======================================================
cur.execute("""
CREATE INDEX IF NOT EXISTS idx_admins
ON admins(admin_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_abuse_warns
ON abuse_warns(chat_id, user_id)
""")

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_reports
ON user_reports(chat_id, status)
""")

# ================= INSERT INITIAL ADMINS =================
for admin_id in INITIAL_ADMINS:
    cur.execute(
        "INSERT OR IGNORE INTO admins (admin_id) VALUES (?)",
        (admin_id,)
    )


# ================= ABUSE WARNINGS TABLE =================

cur.execute("""
CREATE TABLE IF NOT EXISTS abuse_warnings (
    chat_id INTEGER,
    user_id INTEGER,
    warns INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)
""")

# ================= INDEX (FAST LOOKUP) =================

cur.execute("""
CREATE INDEX IF NOT EXISTS idx_abuse_warnings
ON abuse_warnings(chat_id, user_id)
""")

# ======================================================
# ================= FINAL COMMIT =======================
# ======================================================
conn.commit()


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
        "guide": "╔═══════════════════╗\n      📚 GUIDE 📚\n╚═══════════════════╝"
    }
    return headers.get(title, f"╔═══════════════════╗\n        {title}\n╚═══════════════════╝")

def beautiful_footer() -> str:
    """Add beautiful footer to messages"""
    footer_line = "──────────────────────"
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
# Remove the duplicate abuse_warning functions and use this unified version:
def abuse_warning(chat_id, user_id):
    """Add abuse warning for user in chat"""
    cur.execute(
        "INSERT OR IGNORE INTO abuse_warnings (chat_id, user_id, warns) VALUES (?, ?, 0)",
        (chat_id, user_id)
    )
    cur.execute(
        "UPDATE abuse_warnings SET warns = warns + 1 WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    conn.commit()
    cur.execute(
        "SELECT warns FROM abuse_warnings WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    return cur.fetchone()[0]

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
    text = re.sub(r"[^a-zA-Z ]", "", text.lower())
    return any(w in text for w in ABUSE_WORDS)

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

def is_blocked_user(uid):
    """Check if user is blocked from support"""
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
def admin_buttons(uid):
    return create_button_grid([
        ("🟢 Reply", f"reply:{uid}"),
        ("🚫 Block", f"block:{uid}"),
        ("🔓 Unblock", f"unblock:{uid}"),
        ("📜 History", f"history:{uid}"),
        ("📊 Info", f"info:{uid}"),
        ("⚠️ Warn", f"warn:{uid}")
    ], columns=3)

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


# ================= ENHANCED START COMMAND =================





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


ABUSE_WORDS = [
    # English abuse words
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "dick", "pussy",
    "whore", "slut", "motherfucker", "damn", "hell", "crap", "bullshit",
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
    "land", "laund", "launda", "chut", "choot", "bhen", "maa", "maa ki",
    
    # Evasion attempts (common misspellings)
    "fuk", "shyt", "bich", "asshle", "mdrchod", "bhenchd", "chtiya", "gndu",
    "lundh", "rndi", "hrma", "kmina", "kuttaa", "kutti", "lawda", "lawde",
    "lauda", "laude", "choot", "gaandu", "bhonsdi", "bhosdika", "choduu",
    "fak", "shit", "bich", "ass", "mader", "behn", "chutia", "gando",
    
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

MUTE_TIME = 600  # 10 minutes


@app.on_message(filters.group & filters.text & ~filters.me)
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


# ================= UNIVERSAL MODERATION COMMAND HANDLER =========
async def handle_moderation_command(client, message: Message, command_type="mute"):
    """
    Universal handler for all moderation commands
    command_type: "mute", "unmute", "warn", "ban", "unban", "kick"
    """
    
    # Check admin status
    user_id = message.from_user.id
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, message.chat.id, user_id)
    
    # Determine which command prefix to use
    command_prefix = message.command[0]  # /mute, /bmute, etc.
    is_bot_command = command_prefix.startswith("b") and len(command_prefix) > 1
    
    # Check permissions
    if is_bot_command:
        # Bot admin command - require bot admin status
        if not is_bot_admin_user:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Bot Admin Required**\n"
                "This command is only for bot admins.\n"
                "Use `/mybotadmin` to check your status."
                + beautiful_footer()
            )
            return False
    else:
        # Regular command - require group admin OR bot admin
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
            return False
    
    # Check bot permissions
    if not await can_bot_restrict(client, message.chat.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "❌ **Bot Needs Admin Rights**\n"
            "I need admin permissions in this group.\n"
            "Please make me admin with 'Restrict Users' permission."
            + beautiful_footer()
        )
        return False
    
    # Get target user
    target_user = None
    args = []
    
    # Method 1: Reply to message
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        args = message.command[1:]  # Duration/reason
    
    # Method 2: User ID/Username from command
    elif len(message.command) > 1:
        user_arg = message.command[1]
        args = message.command[2:]  # Duration/reason
        
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
            return False
    
    if not target_user:
        usage_text = f"""
{beautiful_header('moderation')}

❌ **User Required**

**Usage:**
1. Reply to user + `/{command_prefix} [duration] [reason]`
2. `/{command_prefix} @username [duration] [reason]`

**Examples:**
• `/{command_prefix} @user 1h Spamming`
• `/{command_prefix}` (reply to user)
"""
        
        if command_type in ["mute", "ban", "warn"]:
            usage_text += "\n**Duration:** 30m, 2h, 1d, 1w"
        
        await message.reply_text(usage_text + beautiful_footer())
        return False
    
    # Prevent self-action
    if target_user.id == user_id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "😂 **Seriously?**\n"
            "You cannot perform this action on yourself!"
            + beautiful_footer()
        )
        return False
    
    # Check if target is admin (can't moderate admins)
    try:
        target_member = await client.get_chat_member(message.chat.id, target_user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                f"❌ **Cannot moderate admin**\n"
                f"User {target_user.mention} is an admin.\n"
                f"Only group owner can moderate admins."
                + beautiful_footer()
            )
            return False
    except:
        pass
    
    return target_user, args


# ================= MUTE COMMANDS =================
@app.on_message(filters.command(["mute", "bmute"]) & filters.group)
async def universal_mute(client, message: Message):
    """Universal mute command for both bot admins and group admins"""
    
    result = await handle_moderation_command(client, message, "mute")
    if not result:
        return
    
    target_user, args = result
    
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
    
    target_user, args = result
    
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
    
    target_user, args = result
    
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
    
    target_user, _ = result
    
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
    
    target_user, args = result
    
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

# ================= STORE LOCK STATES PER CHAT =================
chat_locks = {}

# ================= LOCK COMMAND =================
@app.on_message(filters.command(["lock", "block"]) & filters.group)
async def lock_chat_permissions(client, message: Message):
    """Lock specific permissions in the group - Command only version"""
    
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
            "4. Enable all permissions\n"
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

**🔐 MAJOR LOCKS:**
• `/lock all` - Lock everything completely
• `/lock text` - Disable text messages
• `/lock media` - Disable all media
• `/lock forward` - Auto-delete forwarded messages

**📱 MEDIA LOCKS:**
• `/lock photos` - Disable photos
• `/lock video` - Disable videos
• `/lock audio` - Disable audio
• `/lock voice` - Disable voice messages
• `/lock documents` - Disable documents

**⚙️ FEATURE LOCKS:**
• `/lock stickers` - Disable stickers/GIFs
• `/lock polls` - Disable polls
• `/lock invites` - Disable invite links
• `/lock pins` - Disable pinning
• `/lock games` - Disable games
• `/lock inline` - Disable inline bots
• `/lock url` - Disable links
• `/lock info` - Prevent info changes

**⏰ DURATION FORMAT:**
• `/lock text 30m` - Lock for 30 minutes
• `/lock all 2h` - Lock for 2 hours
• `/lock media 1d` - Lock for 1 day
• `/lock stickers 1w` - Lock for 1 week

**📊 Check Status:** `/lockstatus`
**🔓 Unlock:** `/unlock [type]`

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
            duration_text = str(duration)
    
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
            asyncio.create_task(auto_unlock_after_duration(client, chat_id, lock_type, duration))
        
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

📊 **To Check:** `/lockstatus`
🔓 **To Remove:** `/unlock {lock_type}`
"""
        
        await message.reply_text(success_text + beautiful_footer())
        
        # Send notification to chat (for major locks)
        if lock_type in ["all", "text", "media"]:
            await asyncio.sleep(1)
            notify_text = f"""
{beautiful_header('security')}

⚠️ **GROUP NOTICE**

{action_text}

The {lock_type} lock has been applied by an admin.
{duration_text.capitalize() if 'permanent' not in duration_text.lower() else ''}

Please follow group rules during this time.
"""
            notification = await message.reply_text(notify_text + beautiful_footer())
            await asyncio.sleep(10)
            await notification.delete()
        
    except Exception as e:
        error_text = f"""
{beautiful_header('danger')}

❌ **LOCK FAILED**

**Error:** {str(e)[:80]}

**Possible Reasons:**
1. Bot missing 'Change Chat Info' permission
2. Telegram API limit reached
3. Network connectivity issue

**Solutions:**
1. Check bot permissions
2. Wait a moment and try again
3. Contact bot admin if issue persists

**Your Command:** `/lock {lock_type} {duration_text if duration else ''}`
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


async def auto_unlock_after_duration(client, chat_id, lock_type, duration):
    """Auto-unlock after specified duration"""
    await asyncio.sleep(duration.total_seconds())
    
    try:
        # Remove lock from state
        if chat_id in chat_locks and lock_type in chat_locks[chat_id]:
            del chat_locks[chat_id][lock_type]
        
        # Restore default permissions for this specific lock
        if lock_type != "all" and lock_type != "forward":
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
            
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=default_permissions
            )
        
        # Send auto-unlock notification
        await client.send_message(
            chat_id,
            f"{beautiful_header('security')}\n\n"
            f"⏰ **AUTO UNLOCK COMPLETE**\n\n"
            f"🔓 **Lock Type:** {lock_type.title()}\n"
            f"⏳ **Duration expired automatically**\n"
            f"🤖 **System:** Automatic Bot\n\n"
            f"The {lock_type} lock has been automatically removed.\n"
            f"Permissions have been restored."
            f"{beautiful_footer()}"
        )
        
    except Exception as e:
        print(f"Error in auto-unlock: {e}")


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
👥 **Type:** {chat.type.title()}
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
          

# ================= FORWARDED MESSAGE FILTER =================
@app.on_message(filters.group & ~filters.service)
async def forward_lock_filter(client, message: Message):
    """Auto-delete forwarded messages if forward lock is active"""
    
    chat_id = message.chat.id
    
    # Check if forward lock is active
    if chat_id in chat_locks and "forward" in chat_locks[chat_id]:
        # Check if message is forwarded
        if message.forward_from or message.forward_from_chat or message.forward_from_message_id:
            # Check if sender is admin
            try:
                if await can_user_restrict(client, chat_id, message.from_user.id):
                    return  # Admins can forward
            except:
                pass
            
            # Delete forwarded message
            try:
                await message.delete()
                
                # Send warning that auto-deletes
                warning = await message.reply_text(
                    f"{beautiful_header('security')}\n\n"
                    "📨 **FORWARDED MESSAGE BLOCKED**\n\n"
                    f"👤 **User:** {message.from_user.mention}\n"
                    f"🆔 **ID:** `{message.from_user.id}`\n"
                    "❌ **Action:** Message deleted\n\n"
                    "⚠️ **Forward lock is active in this group.**\n"
                    "Forwarded messages are automatically deleted.\n"
                    "Please send original content instead."
                    f"{beautiful_footer()}"
                )
                
                await asyncio.sleep(5)
                await warning.delete()
                
                # Log this action
                print(f"Deleted forwarded message from {message.from_user.id} in chat {chat_id}")
                
            except Exception as e:
                print(f"Error deleting forwarded message: {e}")




@app.on_message(filters.command("promote") & filters.group)
async def promote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    # ================= CALLER STATUS =================
    member = await client.get_chat_member(chat_id, caller_id)

    is_owner = member.status == ChatMemberStatus.OWNER
    is_group_admin = member.status == ChatMemberStatus.ADMINISTRATOR
    is_bot_admin_user = is_admin(caller_id)  # bot/super admin

    if not (is_owner or is_group_admin or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Only admins can promote members**"
            f"{beautiful_footer()}"
        )
        return

    # ================= BOT PERMISSION =================
    bot = await client.get_chat_member(chat_id, "me")
    if bot.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ Make me admin with **Add New Admins** permission"
            f"{beautiful_footer()}"
        )
        return

    if hasattr(bot, "privileges") and not bot.privileges.can_promote_members:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ I need **Add New Admins** permission"
            f"{beautiful_footer()}"
        )
        return

    # ================= TARGET USER =================
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        target = await client.get_users(message.command[1])
    else:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ Reply to a user or use `/promote @user`"
            f"{beautiful_footer()}"
        )
        return

    if target.id == caller_id:
        return await message.reply_text("❌ You cannot promote yourself")

    target_member = await client.get_chat_member(chat_id, target.id)
    if target_member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        return await message.reply_text("⚠️ User already admin")

    # ================= PRIVILEGES LOGIC =================
    if is_owner or is_bot_admin_user:
        # 🔥 FULL ADMIN
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
        # 🔧 LIMITED ADMIN (GROUP ADMIN)
        privileges = ChatPrivileges(
            can_delete_messages=True,
            can_restrict_members=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_video_chats=True,
            can_promote_members=False,   # ❌
            can_change_info=True,
            can_manage_chat=True,
            is_anonymous=False           # ❌
        )
        promoter_type = "Group Admin"

    # ================= PROMOTE =================
    await client.promote_chat_member(chat_id, target.id, privileges)

    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        "✅ **PROMOTED SUCCESSFULLY**\n\n"
        f"👤 User: {target.mention}\n"
        f"🔧 By: {caller.mention} ({promoter_type})"
        f"{beautiful_footer()}"
  )

@app.on_message(filters.command("demote") & filters.group)
async def demote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    is_bot_admin_user = is_admin(caller_id)
    member = await client.get_chat_member(chat_id, caller_id)
    is_owner = member.status == ChatMemberStatus.OWNER

    if not (is_owner or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Only Group Owner or Bot Admin can demote admins**"
            f"{beautiful_footer()}"
        )
        return

    # ===== GET TARGET =====
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        target = await client.get_users(message.command[1])
    else:
        return await message.reply_text("❌ Reply or use `/demote @user`")

    target_member = await client.get_chat_member(chat_id, target.id)

    if target_member.status == ChatMemberStatus.OWNER:
        return await message.reply_text("❌ Cannot demote group owner")

    if target_member.status != ChatMemberStatus.ADMINISTRATOR:
        return await message.reply_text("⚠️ User is not admin")

    # ===== DEMOTE =====
    await client.promote_chat_member(
        chat_id,
        target.id,
        privileges=ChatPrivileges()  # remove admin
    )

    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        "🔻 **ADMIN REMOVED**\n\n"
        f"👤 User: {target.mention}\n"
        f"🔧 By: {caller.mention}"
        f"{beautiful_footer()}"
    )

# ================= Group lock by Bot admin COMMAND =================
group_locks = {}  
# ================= BOT ADMIN LOCK SYSTEM =================
# Store group locks with chat ID as key
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
async def bot_admin_lock_command(client, message: Message):
    """Bot admin lock command - works by chat ID"""
    
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
            "**Usage:** `/block <chat_id> <lock_type> [duration] [silent]`\n\n"
            "**Examples:**\n"
            "• `/gblock or gblock -100123456789 all` - Lock everything\n"
            "• `/glock -100123456789 text 1h` - Lock text for 1 hour\n"
            "• `/glock -100123456789 media 30m silent` - Lock media silently\n\n"
            "**Lock Types (17 options):**\n"
            "`all, text, media, stickers, polls, invites, pins, info, url, games, inline, voice, video, audio, documents, photos, forward`\n\n"
            "**Durations:** m=minutes, h=hours, d=days, w=weeks\n"
            "**Options:** silent (no announcement)"
            f"{beautiful_footer()}"
        )
        return
    
    try:
        # Parse arguments
        chat_id = int(message.command[1])
        lock_type = message.command[2].lower()
        duration = None
        silent = False
        
        # Parse duration if provided
        if len(message.command) >= 4 and not message.command[3].lower() == "silent":
            duration = parse_time_duration(message.command[3])
        
        # Check if silent mode
        if "silent" in [arg.lower() for arg in message.command]:
            silent = True
        
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
        except:
            chat_title = f"Chat ID: {chat_id}"
            chat_type = "Unknown"
        
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
        
        # Apply lock
        success = await apply_group_lock_by_id(
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
        
        admin_msg = f"""
{beautiful_header('admin')}

✅ **LOCK APPLIED**{silent_text}

🏷️ **Chat:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
🔒 **Lock Type:** {lock_type}
⏰ **Duration:** {duration_text or 'Permanent'}
👨‍💼 **By:** {message.from_user.mention}

⚡ **Status:** Successfully locked
"""
        
        await message.reply_text(admin_msg + beautiful_footer())
        
        # Send announcement to group (if not silent)
        if not silent:
            try:
                lock_icon = "🔒" if lock_type == "all" else "🔐"
                duration_info = f"\n⏰ **Duration:** {duration}" if duration else ""
                
                group_msg = f"""
{beautiful_header('settings')}

{lock_icon} **GROUP LOCKED** (by Bot Admin)

🔒 **Type:** {lock_type.title()} Lock
{duration_info}
🤖 **Action:** Bot Admin Command

📋 **Permissions changed for all members.**
⚠️ **Note:** This is a bot admin action.
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

@app.on_message(filters.private & filters.command(["gunblock", "bunblock"]))
async def bot_admin_unlock_command(client, message: Message):
    """Bot admin unlock command - works by chat ID"""
    
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
            "**Usage:** `/unblock <chat_id> [silent]`\n\n"
            "**Examples:**\n"
            "• `/unblock -100123456789` - Unlock everything\n"
            "• `/unblock -100123456789 silent` - Unlock silently\n\n"
            "**Options:** silent (no announcement)"
            f"{beautiful_footer()}"
        )
        return
    
    try:
        # Parse arguments
        chat_id = int(message.command[1])
        silent = "silent" in [arg.lower() for arg in message.command]
        
        # Get chat info
        try:
            chat = await client.get_chat(chat_id)
            chat_title = chat.title
        except:
            chat_title = f"Chat ID: {chat_id}"
        
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
        
        admin_msg = f"""
{beautiful_header('admin')}

✅ **UNLOCK APPLIED**{silent_text}

🏷️ **Chat:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
🔓 **Previous Lock:** {current_lock['type'] if current_lock else 'None'}
👨‍💼 **By:** {message.from_user.mention}

⚡ **Status:** Successfully unlocked
"""
        
        await message.reply_text(admin_msg + beautiful_footer())
        
        # Send announcement to group (if not silent)
        if not silent:
            try:
                group_msg = f"""
{beautiful_header('settings')}

🔓 **GROUP UNLOCKED** (by Bot Admin)

All permissions have been restored.
🤖 **Action:** Bot Admin Command

📋 **Members can now send messages normally.**
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




# ================= BOT ADMIN LOCK HELP =================
@app.on_message(filters.private & filters.command("lockhelp"))
async def bot_admin_lock_help(client, message: Message):
    """Show bot admin lock help"""
    
    if not is_bot_admin(message.from_user.id):
        await message.reply_text("❌ Bot admins only!")
        return
    
    help_text = f"""
{beautiful_header('admin')}

🔒 **BOT ADMIN LOCK SYSTEM**

⚡ **Commands (Private Chat Only):**
• `/glock <chat_id> <type> [duration] [silent]` - Lock group
• `/unblock <chat_id> [silent]` - Unlock group  
• `/lockstatus <chat_id>` - Check lock status

🔐 **17 Lock Types:**
• `all` - Lock everything
• `text` - Text messages only
• `media` - All media messages
• `stickers` - Stickers & GIFs
• `polls` - Polls
• `invites` - Invite links
• `pins` - Pin messages
• `info` - Change chat info
• `url` - URLs/links
• `games` - Games
• `inline` - Inline bots
• `voice` - Voice messages
• `video` - Video messages
• `audio` - Audio messages
• `documents` - Documents
• `photos` - Photos only
• `forward` - Forwarded messages

⏰ **Durations:**
• `30m` - 30 minutes
• `2h` - 2 hours
• `1d` - 1 day
• `1w` - 1 week
• (Empty = Permanent)

🔕 **Options:**
• `silent` - No announcement in group

📋 **Requirements:**
1. You must be bot admin
2. Bot must be admin in target group
3. Bot needs 'Change Chat Info' permission

🎯 **Examples:**
• `/block -100123456789 all 1h` - Lock everything for 1 hour
• `/block -100123456789 text silent` - Lock text silently
• `/gunblock -100123456789` - Unlock everything
• `/lockstatus -100123456789` - Check status

⚡ **Features:**
• Works without being group admin
• Auto-unlock after duration
• Silent mode available
• Status tracking
• Callback quick actions
"""
    
    await message.reply_text(help_text + beautiful_footer())
  
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

