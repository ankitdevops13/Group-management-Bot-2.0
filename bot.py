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

# ================= DATABASE =================

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
conn.commit()


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
conn.commit()

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

conn.commit()
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


# Update get_uptime() function:
def get_uptime() -> str:
    """Get bot uptime as formatted string"""
    try:
        # Simple uptime calculation without psutil
        import time
        from datetime import datetime
        
        # Create a simple uptime counter
        global START_TIME
        if 'START_TIME' not in globals():
            START_TIME = time.time()
        
        uptime_seconds = time.time() - START_TIME
        uptime_str = str(timedelta(seconds=int(uptime_seconds)))
        return uptime_str
    except:
        return "Unknown"
# ================= HELPER FUNCTIONS =================
def get_uptime() -> str:
    """Get bot uptime as formatted string"""
    process = psutil.Process()
    uptime_seconds = time.time() - process.create_time()
    uptime_str = str(timedelta(seconds=int(uptime_seconds)))
    return uptime_str

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

    
def abuse_warning(uid):
    # ensure row exists
    cur.execute(
        "INSERT OR IGNORE INTO user_warnings (user_id, count) VALUES (?, 0)",
        (uid,)
    )

    # increment count
    cur.execute(
        "UPDATE user_warnings SET count = count + 1 WHERE user_id=?",
        (uid,)
    )

    conn.commit()

    # fetch updated count
    cur.execute(
        "SELECT count FROM user_warnings WHERE user_id=?",
        (uid,)
    )
    return cur.fetchone()[0]

    
# ================= HELPER FUNCTIONS =================
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


def abuse_warning(uid):
    cur.execute("INSERT OR IGNORE INTO abuse_warnings VALUES (?,0)", (uid,))
    cur.execute("UPDATE use_warnings SET count=count+1 WHERE user_id=?", (uid,))
    conn.commit()
    cur.execute("SELECT count FROM abuse_warnings WHERE user_id=?", (uid,))
    return cur.fetchone()[0]


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

# ================= START =================
# ================= ENHANCED START COMMAND =================
@app.on_message(filters.command("start") & filters.private)
async def enhanced_start_handler(client, message: Message):
    """Enhanced start command with feature showcase"""
    
    user = message.from_user
    user_name = user.first_name or "Friend"
    
    # Check admin status
    is_bot_admin_user = is_bot_admin(user.id)
    is_super_admin_user = (user.id == SUPER_ADMIN)
    
    # Beautiful animated loading
    loading_frames = [
        "🌙 Starting Advanced Support System...",
        "🌙✨ Loading All Modules...",
        "🌙✨💫 Connecting to Secure Database...",
        "🌙✨💫🌟 Initializing Security Protocols...",
        "🌙✨💫🌟🚀 Loading Admin Systems...",
        "🌙✨💫🌟🚀🔧 Preparing Moderation Tools...",
        "🌙✨💫🌟🚀🔧📊 Loading Analytics Engine...",
        "🌙✨💫🌟🚀🔧📊✅ System Ready!"
    ]
    
    # Send initial message
    msg = await message.reply_text(
        f"✨ **Welcome {user_name}!** ✨\n"
        f"🚀 Initializing {BOT_BRAND}..."
    )
    
    # Show loading animation
    for frame in loading_frames:
        try:
            await msg.edit_text(frame)
            await asyncio.sleep(0.3)
        except:
            pass
    
    # Simulate typing
    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    await asyncio.sleep(0.5)
    
    # Create feature showcase
    features = [
        ("🔒 **Advanced Lock System**", "17 different lock types with granular control"),
        ("🗑️ **Mass Purge Tools**", "Delete thousands of messages with no limits"),
        ("🤖 **Bot Admin System**", "Multi-tier admin hierarchy with special privileges"),
        ("🔍 **Smart Abuse Detection**", "100+ abusive words with evasion detection"),
        ("🚨 **Auto-Report System**", "@admin mentions trigger instant notifications"),
        ("📊 **Complete Information**", "Detailed user/chat info with analytics"),
        ("⚡ **Quick Moderation**", "One-click mute/ban/warn from notifications"),
        ("🛡️ **Security Suite**", "Flood protection, link filtering, auto-backup"),
        ("💬 **Support System**", "24/7 support ticket management"),
        ("🎯 **Group Management**", "Full moderation tools for group admins")
    ]
    
    # Build welcome message
    welcome_text = f"""
{beautiful_header('welcome')}

✨ **Hello {user_name}!** ❤️

🤖 **I'm {BOT_BRAND}**
*{BOT_TAGLINE}*

📊 **Your Status:** {await get_user_status_icon(client, user.id)}
👥 **Admin Level:** {await get_admin_level_text(user.id, is_bot_admin_user, is_super_admin_user)}

🚀 **FEATURES OVERVIEW:**
"""
    
    # Add features with icons
    for i, (feature, description) in enumerate(features[:6]):  # Show first 6 features
        welcome_text += f"\n{feature}\n   └ {description}"
    
    welcome_text += f"\n\n📈 **And {len(features)-6} more advanced features...**"
    
    # Add admin-specific features
    if is_super_admin_user:
        welcome_text += f"""

👑 **SUPER ADMIN PRIVILEGES:**
• Add/remove bot admins
• Mass delete all messages
• System backup & health check
• Full control over bot
"""
    elif is_bot_admin_user:
        welcome_text += f"""

⚡ **BOT ADMIN PRIVILEGES:**
• Use bot admin commands (/bmute, /bban, etc.)
• Works without group admin rights
• Access to special tools
• Priority support
"""
    
    welcome_text += f"""

📚 **QUICK START:**
1. Add me to your group
2. Make me admin with permissions
3. Use `/help` to see all commands
4. Configure settings as needed

💡 **Pro Tip:** Use `/mystatus` in groups to check your permissions!
"""
    
    # Create dynamic buttons based on user status
    buttons = []
    
    # Main navigation
    buttons.append([
        InlineKeyboardButton("📖 Complete Help", callback_data="help_main"),
        InlineKeyboardButton("🚀 Features", callback_data="features_showcase")
    ])
    
    # Admin specific buttons
    if is_bot_admin_user or is_super_admin_user:
        buttons.append([
            InlineKeyboardButton("⚡ Admin Panel", callback_data="admin_panel"),
            InlineKeyboardButton("📊 Bot Stats", callback_data="bot_stats")
        ])
    
    # Group management buttons
    buttons.append([
        InlineKeyboardButton("👥 Group Tools", callback_data="group_tools"),
        InlineKeyboardButton("🔧 Settings", callback_data="settings_menu")
    ])
    
    # Support and info
    buttons.append([
        InlineKeyboardButton("💬 Support", callback_data="contact_support"),
        InlineKeyboardButton("ℹ️ Bot Info", callback_data="bot_info")
    ])
    
    # Special super admin buttons
    if is_super_admin_user:
        buttons.append([
            InlineKeyboardButton("👑 Super Admin", callback_data="super_admin_panel"),
            InlineKeyboardButton("📋 Admin List", callback_data="list_admins")
        ])
    
    # Update the message with final content
    await msg.edit_text(
        welcome_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )


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


# ================= GROUP START COMMAND =================
@app.on_message(filters.command("start") & filters.group)
async def group_start_handler(client, message: Message):
    """Start command for groups"""
    
    user = message.from_user
    chat = message.chat
    
    # Check user permissions in this group
    is_bot_admin_user = is_bot_admin(user.id)
    is_group_admin_user = await can_user_restrict(client, chat.id, user.id)
    
    # Get group info
    member_count = "Unknown"
    try:
        chat_info = await client.get_chat(chat.id)
        if hasattr(chat_info, 'members_count'):
            member_count = chat_info.members_count
    except:
        pass
    
    welcome_text = f"""
{beautiful_header('welcome')}

🤖 **{BOT_BRAND} is Active!**

💬 **Chat:** {chat.title}
👥 **Members:** {member_count}
👤 **You:** {user.mention}

🎯 **Available Commands:**
"""
    
    # Show available commands based on permissions
    if is_group_admin_user or is_bot_admin_user:
        welcome_text += """
• `/help` - Full command list
• `/mystatus` - Your permissions
• `/lock` - Control permissions
• `/purge` - Clean messages
• `/mute` - Moderate users
• `/ban` - Ban users
• `/warn` - Warn users
"""
    else:
        welcome_text += """
• `/help` - Command list
• `/mystatus` - Your status
• `/id` - Get IDs
• `/info` - User info
• `/rules` - Group rules
• `/warns` - Check warnings
• `/admins` - List admins
"""
    
    welcome_text += f"""

🔔 **Quick Help:**
• Mention `@admin` for assistance
• Follow group rules
• Respect all members

⚡ **Bot Admin:** {'✅ Yes' if is_bot_admin_user else '❌ No'}
🔧 **Group Admin:** {'✅ Yes' if is_group_admin_user else '❌ No'}
"""
    
    # Create buttons for group
    buttons = []
    
    if is_group_admin_user or is_bot_admin_user:
        buttons.append([
            InlineKeyboardButton("🔧 Moderation", callback_data="moderation_menu"),
            InlineKeyboardButton("🔒 Lock Menu", callback_data="lock_menu")
        ])
    
    buttons.append([
        InlineKeyboardButton("📖 Help", callback_data="help_main"),
        InlineKeyboardButton("📊 Status", callback_data="my_status")
    ])
    
    buttons.append([
        InlineKeyboardButton("👥 Tag All", callback_data="tagall_menu"),
        InlineKeyboardButton("ℹ️ Chat Info", callback_data="chat_info")
    ])
    
    await message.reply_text(
        welcome_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons),
        reply_to_message_id=message.id
    )


# ================= FEATURES SHOWCASE =================
@app.on_callback_query(filters.regex("^features_showcase$"))
async def features_showcase_callback(client, cq):
    """Show all features in detail"""
    
    features = [
        {
            "icon": "🔒",
            "title": "Advanced Lock System",
            "description": "17 different lock types with granular control over chat permissions",
            "commands": ["/lock", "/unlock", "/lockstatus"],
            "types": "all, text, media, stickers, polls, invites, pins, info, url, games, inline, voice, video, audio, documents, photos, forward"
        },
        {
            "icon": "🗑️",
            "title": "Mass Purge Tools",
            "description": "Delete thousands of messages with no limits. Range delete, selective cleanup, and nuclear options",
            "commands": ["/purge", "/massdelete", "/cleanup", "/del", "/purgebots", "/purgeservice"],
            "types": "Number purge (0=ALL), Reply purge, Selective cleanup, Bot messages, Service messages"
        },
        {
            "icon": "🤖",
            "title": "Bot Admin System",
            "description": "Multi-tier admin hierarchy. Bot admins can moderate without group admin rights",
            "commands": ["/bmute", "/bban", "/bwarn", "/bpurge", "/block", "/mybotadmin"],
            "levels": "Super Admin → Bot Admin → Group Admin → Regular User"
        },
        {
            "icon": "🔍",
            "title": "Smart Abuse Detection",
            "description": "Detects 100+ abusive words in Hindi & English with evasion detection (misspellings, symbols)",
            "commands": ["/abusestats"],
            "actions": "Warning → 6h mute → 24h mute → 7d ban → Permanent ban"
        },
        {
            "icon": "🚨",
            "title": "Auto-Report System",
            "description": "@admin mentions trigger instant notifications to all group admins with quick action buttons",
            "triggers": "@admin, admin help, help admin, admins please, admin ji, @admins, call admin",
            "features": "Cooldown system, Priority tagging, Quick response buttons"
        },
        {
            "icon": "📊",
            "title": "Complete Information System",
            "description": "Detailed user and chat information with analytics, warnings, and activity tracking",
            "commands": ["/id", "/info", "/whois", "/mystatus", "/checkadmin", "/warns"],
            "info": "User ID, Name, Username, Premium, Role, Warnings, Reports, Bio, Last seen, Join date"
        },
        {
            "icon": "⚡",
            "title": "Quick Moderation",
            "description": "One-click moderation from notification messages. Mute, ban, warn directly from reports",
            "actions": "Mute, Ban, Warn, Message user, User info, Mark resolved",
            "access": "From auto-reports, Abuse notifications, User reports"
        },
        {
            "icon": "🛡️",
            "title": "Security Suite",
            "description": "Comprehensive security features including flood protection, link filtering, and auto-backup",
            "features": "Flood protection (10/10s), Malicious link blocking, Auto-backup daily, Service message cleanup",
            "protection": "Anti-spam, Anti-raid, Link validation, Message filtering"
        },
        {
            "icon": "💬",
            "title": "Support System",
            "description": "24/7 support ticket management with auto-reply and admin forwarding",
            "flow": "User message → Auto-reply → Forward to admins → Admin response → Mark resolved",
            "features": "Abuse filtering, Block system, Message history, Quick reply"
        },
        {
            "icon": "🎯",
            "title": "Group Management",
            "description": "Full suite of group management tools for administrators",
            "commands": ["/mute", "/ban", "/warn", "/kick", "/promote", "/demote", "/setrules", "/setwelcome"],
            "tools": "User management, Permission control, Rule setting, Welcome messages"
        }
    ]
    
    features_text = f"""
{beautiful_header('features')}

🚀 **{BOT_BRAND} - COMPLETE FEATURES**

📊 **Total Features:** {len(features)} advanced systems
✨ **Last Updated:** {datetime.now().strftime('%Y-%m-%d')}

"""
    
    # Show first 3 features in detail, then list others
    for i, feature in enumerate(features[:3]):
        features_text += f"""
{feature['icon']} **{feature['title']}**
{feature['description']}

**Commands:** `{', '.join(feature['commands'])}`
**Types:** {feature.get('types', feature.get('levels', feature.get('actions', feature.get('triggers', feature.get('info', feature.get('features', feature.get('flow', feature.get('tools', ''))))))))}

"""
    
    features_text += f"""
📋 **OTHER FEATURES:**
"""
    
    for i, feature in enumerate(features[3:], 4):
        features_text += f"{i}. {feature['icon']} {feature['title']}\n"
    
    features_text += f"""

💡 **Pro Features:**
• Multi-language support
• Customizable responses
• Exportable logs
• Web dashboard (coming soon)
• API access (planned)

🔧 **System Requirements:**
• Python 3.7+
• Pyrogram 2.0+
• SQLite3 database
• Admin rights in groups
"""
    
    buttons = [
        [
            InlineKeyboardButton("📖 Command List", callback_data="help_main"),
            InlineKeyboardButton("⚡ Quick Start", callback_data="quick_start")
        ],
        [
            InlineKeyboardButton("🔧 Setup Guide", callback_data="setup_guide"),
            InlineKeyboardButton("🎯 Use Cases", callback_data="use_cases")
        ],
        [
            InlineKeyboardButton("⬅️ Back to Start", callback_data="back_to_start"),
            InlineKeyboardButton("🤖 Bot Info", callback_data="bot_info")
        ]
    ]
    
    await cq.message.edit_text(
        features_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )
    
    await cq.answer()


# ================= ADMIN PANEL =================
@app.on_callback_query(filters.regex("^admin_panel$"))
async def admin_panel_callback(client, cq):
    """Admin panel for bot admins"""
    
    user_id = cq.from_user.id
    is_bot_admin_user = is_admin(user_id)
    is_super_admin_user = (user_id == SUPER_ADMIN)
    
    if not is_bot_admin_user:
        await cq.answer("❌ Bot admins only!", show_alert=True)
        return
    
    # Get admin statistics
    cur.execute("SELECT COUNT(*) FROM admins")
    total_admins = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM blocked_users")
    blocked_users = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM user_warnings")
    total_warnings = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM user_reports WHERE status='pending'")
    pending_reports = cur.fetchone()[0]
    
    admin_text = f"""
{beautiful_header('admin')}

⚡ **BOT ADMIN PANEL**

👤 **Your Level:** {'👑 Super Admin' if is_super_admin_user else '⚡ Bot Admin'}
🆔 **Your ID:** `{user_id}`
🕒 **Login Time:** {datetime.now().strftime('%H:%M:%S')}

📊 **SYSTEM STATISTICS:**
• **Total Admins:** {total_admins}
• **Blocked Users:** {blocked_users}
• **Warnings Issued:** {total_warnings}
• **Pending Reports:** {pending_reports}
• **Database Size:** {os.path.getsize(DB_FILE) / 1024:.1f} KB

🔧 **ADMIN TOOLS:**
"""
    
    # Create buttons based on admin level
    buttons = []
    
    # Admin management (super admin only)
    if is_super_admin_user:
        buttons.append([
            InlineKeyboardButton("👥 Manage Admins", callback_data="manage_admins"),
            InlineKeyboardButton("📋 List Admins", callback_data="list_admins")
        ])
    
    # Moderation tools
    buttons.append([
        InlineKeyboardButton("🗑️ Purge Tools", callback_data="purge_tools"),
        InlineKeyboardButton("🔒 Lock Tools", callback_data="lock_tools")
    ])
    
    # Information
    buttons.append([
        InlineKeyboardButton("📊 System Stats", callback_data="system_stats"),
        InlineKeyboardButton("🚨 View Reports", callback_data="view_reports")
    ])
    
    # Utilities
    buttons.append([
        InlineKeyboardButton("💾 Backup", callback_data="backup_db"),
        InlineKeyboardButton("🩺 Health Check", callback_data="health_check")
    ])
    
    # Navigation
    buttons.append([
        InlineKeyboardButton("⬅️ Back", callback_data="back_to_start"),
        InlineKeyboardButton("📖 Help", callback_data="help_main")
    ])
    
    await cq.message.edit_text(
        admin_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()


# ================= BOT STATISTICS =================
@app.on_callback_query(filters.regex("^bot_stats$"))
async def bot_stats_callback(client, cq):
    """Show bot statistics"""
    
    # Get bot statistics
    cur.execute("SELECT COUNT(DISTINCT chat_id) FROM user_warnings")
    active_groups = cur.fetchone()[0] or 0
    
    cur.execute("SELECT COUNT(*) FROM user_warnings")
    total_actions = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_warnings")
    users_affected = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM user_reports")
    total_reports = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM contact_history")
    support_messages = cur.fetchone()[0]
    
    # Calculate uptime (simplified)
    import psutil
    import time
    process = psutil.Process()
    uptime_seconds = time.time() - process.create_time()
    uptime_str = str(timedelta(seconds=int(uptime_seconds)))
    
    stats_text = f"""
{beautiful_header('info')}

📊 **BOT STATISTICS**

🤖 **Bot Information:**
• **Name:** {BOT_BRAND}
• **Tagline:** {BOT_TAGLINE}
• **Uptime:** {uptime_str}
• **Version:** 3.0.0

📈 **ACTIVITY STATS:**
• **Active Groups:** {active_groups}
• **Total Mod Actions:** {total_actions}
• **Users Affected:** {users_affected}
• **Reports Handled:** {total_reports}
• **Support Messages:** {support_messages}

🔧 **SYSTEM INFO:**
• **Python:** {sys.version.split()[0]}
• **Pyrogram:** 2.0+
• **Database:** SQLite3
• **Filesize:** {os.path.getsize(DB_FILE) / 1024:.1f} KB

⚡ **PERFORMANCE:**
• **Memory Usage:** {process.memory_info().rss / 1024 / 1024:.1f} MB
• **CPU Usage:** {process.cpu_percent():.1f}%
• **Threads:** {process.num_threads()}
• **Status:** ✅ Operational
"""
    
    buttons = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="bot_stats"),
            InlineKeyboardButton("📈 Detailed", callback_data="detailed_stats")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="back_to_start"),
            InlineKeyboardButton("🤖 Bot Info", callback_data="bot_info")
        ]
    ]
    
    await cq.message.edit_text(
        stats_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer("Statistics updated")



# ================= GROUP TOOLS MENU =================
@app.on_callback_query(filters.regex("^group_tools$"))
async def group_tools_callback(client, cq):
    """Group tools menu"""
    
    tools_text = f"""
{beautiful_header('tools')}

👥 **GROUP MANAGEMENT TOOLS**

🎯 **For Group Admins:**
These tools help you manage your group effectively.

🗑️ **CLEANUP TOOLS:**
• **Purge Messages** - Delete multiple messages
• **Selective Cleanup** - Remove specific types
• **Mass Delete** - Complete reset (careful!)

🔒 **PERMISSION CONTROL:**
• **Lock Features** - Restrict what users can do
• **Permission Management** - Fine-grained control
• **Auto-moderation** - Set and forget

👤 **USER MANAGEMENT:**
• **Quick Moderation** - Mute/ban/warn from notifications
• **Warning System** - 3 strikes auto-ban
• **User Information** - Detailed user profiles

📊 **ANALYTICS:**
• **Activity Tracking** - Monitor group activity
• **Abuse Statistics** - Track problematic behavior
• **Report System** - Handle user reports

⚡ **AUTOMATION:**
• **Auto-responses** - Handle common queries
• **Scheduled Tasks** - Automatic actions
• **Reminder System** - Never forget important things
"""
    
    buttons = [
        [
            InlineKeyboardButton("🗑️ Purge Menu", callback_data="purge_menu"),
            InlineKeyboardButton("🔒 Lock Menu", callback_data="lock_menu")
        ],
        [
            InlineKeyboardButton("👤 Moderation", callback_data="moderation_menu"),
            InlineKeyboardButton("📊 Analytics", callback_data="analytics_menu")
        ],
        [
            InlineKeyboardButton("⚡ Automation", callback_data="automation_menu"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="back_to_start"),
            InlineKeyboardButton("📖 Help", callback_data="help_main")
        ]
    ]
    
    await cq.message.edit_text(
        tools_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

# ================= QUICK START GUIDE =================
@app.on_callback_query(filters.regex("^quick_start$"))
async def quick_start_callback(client, cq):
    """Quick start guide"""
    
    guide_text = f"""
{beautiful_header('guide')}

🚀 **QUICK START GUIDE**

✅ **Step 1: Add Bot to Group**
1. Go to your group
2. Add @{client.me.username} as member
3. Make bot admin with these permissions:
   • Delete Messages
   • Ban Users
   • Restrict Users
   • Pin Messages
   • Change Chat Info

✅ **Step 2: Basic Setup**
1. Set group rules: `/setrules [your rules]`
2. Set welcome message: `/setwelcome [message]`
3. Add trusted users as admins if needed

✅ **Step 3: Test Basic Commands**
1. Check your status: `/mystatus`
2. Test purge: `/purge 5` (deletes last 5 messages)
3. Test lock: `/lock text` then `/unlock text`

✅ **Step 4: Configure Auto-moderation**
1. Check abuse stats: `/abusestats`
2. Test @admin mentions
3. Set up reminders if needed

🎯 **PRO SETUP:**

🔧 **For Large Groups:**
• Set up multiple bot admins
• Use `/lock all` during raids
• Configure auto-delete for service messages
• Set up regular cleanup with `/purge`

🛡️ **For Security:**
• Monitor `/abusestats` regularly
• Review pending reports
• Keep admin list updated
• Regular database backups

⚡ **Advanced Features:**
• Bot admin system for trusted moderators
• Mass purge for complete cleanup
• Detailed analytics with `/id` command
• Custom lock configurations
"""
    
    buttons = [
        [
            InlineKeyboardButton("📖 Command Reference", callback_data="help_main"),
            InlineKeyboardButton("🎯 Features", callback_data="features_showcase")
        ],
        [
            InlineKeyboardButton("🔧 Setup Guide", callback_data="setup_guide"),
            InlineKeyboardButton("🎥 Video Tutorial", url="https://t.me/")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="back_to_start"),
            InlineKeyboardButton("🤖 Bot Info", callback_data="bot_info")
        ]
    ]
    
    await cq.message.edit_text(
        guide_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )
    
    await cq.answer()


# ================= BACK TO START HANDLER =================
@app.on_callback_query(filters.regex("^back_to_start$"))
async def back_to_start_callback(client, cq):
    """Return to start menu"""
    await enhanced_start_handler(client, cq.message)
    await cq.answer()

# ================= ADDITIONAL CALLBACK HANDLERS =================
@app.on_callback_query(filters.regex("^my_status$"))
async def my_status_callback(client, cq):
    """Show my status with detailed information for all user types"""
    
    user = cq.from_user
    chat = cq.message.chat
    
    # Get basic admin status
    is_bot_admin_user = is_bot_admin(user.id)
    is_super_admin_user = (user.id == SUPER_ADMIN)
    
    # Different display for private vs group chats
    if chat.type == "private":
        await show_private_chat_status(client, cq, user, is_bot_admin_user, is_super_admin_user)
    else:
        await show_group_chat_status(client, cq, user, chat, is_bot_admin_user, is_super_admin_user)
    
    await cq.answer("Status loaded ✓")


async def show_private_chat_status(client, cq, user, is_bot_admin, is_super_admin):
    """Show status in private chat"""
    
    # Get support stats if available
    cur.execute("SELECT COUNT(*) FROM contact_history WHERE user_id=?", (user.id,))
    support_tickets = cur.fetchone()[0] or 0
    
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user.id,))
    is_blocked = cur.fetchone() is not None
    
    # Get chat type as string
    chat_type_str = str(cq.message.chat.type).replace("ChatType.", "").title()
    
    # Build status text - FIXED
    status_text = f"""
{beautiful_header('info')}

👤 **PRIVATE CHAT STATUS**

📱 **YOUR INFORMATION:**
• **Name:** {user.first_name} {user.last_name or ''}
• **ID:** `{user.id}`
• **Username:** @{user.username or 'None'}
• **Premium:** {'✅ Yes' if getattr(user, 'is_premium', False) else '❌ No'}
• **Bot:** {'🤖 Yes' if user.is_bot else '👤 Human'}

💬 **CHAT TYPE:** {chat_type_str}
"""



async def show_group_chat_status(client, cq, user, chat, is_bot_admin, is_super_admin):
    """Show status in group chat"""
    
    # Get group-specific information
    try:
        member = await client.get_chat_member(chat.id, user.id)
        group_status = member.status
        
        if group_status == ChatMemberStatus.OWNER:
            group_role = "👑 **Group Owner**"
            role_icon = "👑"
            can_restrict = True
        elif group_status == ChatMemberStatus.ADMINISTRATOR:
            group_role = "⚡ **Group Admin**"
            role_icon = "⚡"
            can_restrict = await can_user_restrict(client, chat.id, user.id)
        elif group_status == ChatMemberStatus.MEMBER:
            group_role = "👤 **Group Member**"
            role_icon = "👤"
            can_restrict = False
        elif group_status == ChatMemberStatus.RESTRICTED:
            group_role = "🔇 **Restricted User**"
            role_icon = "🔇"
            can_restrict = False
        elif group_status == ChatMemberStatus.BANNED:
            group_role = "🚫 **Banned User**"
            role_icon = "🚫"
            can_restrict = False
        else:
            group_role = f"❓ **{group_status}**"
            role_icon = "❓"
            can_restrict = False
    except:
        group_role = "❓ **Unknown**"
        role_icon = "❓"
        can_restrict = False
    
    # Check bot permissions
    bot_is_admin = await can_bot_restrict(client, chat.id)
    
    # Get warning count
    cur.execute(
        "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
        (chat.id, user.id)
    )
    warn_count = cur.fetchone()[0]
    
    # Get report count
    cur.execute(
        "SELECT COUNT(*) FROM user_reports WHERE reported_user_id=? AND chat_id=?",
        (user.id, chat.id)
    )
    report_count = cur.fetchone()[0]
    
    # Get last seen in group (approximate)
    cur.execute(
        """
        SELECT MAX(timestamp) FROM user_warnings 
        WHERE chat_id=? AND user_id=?
        UNION
        SELECT MAX(timestamp) FROM user_reports 
        WHERE chat_id=? AND reported_user_id=?
        """,
        (chat.id, user.id, chat.id, user.id)
    )
    last_activity = cur.fetchone()[0]
    
    # Build status text
    status_text = f"""
{beautiful_header('info')}

{role_icon} **GROUP CHAT STATUS**

🏷️ **CHAT INFORMATION:**
• **Group:** {chat.title}
• **Chat ID:** `{chat.id}`
• **Type:** {chat.type.title()}
• **Bot Admin:** {'✅ Yes' if bot_is_admin else '❌ No'}

👤 **YOUR INFORMATION:**
• **Name:** {user.first_name} {user.last_name or ''}
• **ID:** `{user.id}`
• **Username:** @{user.username or 'None'}
• **Group Role:** {group_role}

🔑 **ADMIN TYPES:**
"""
    
    # Show all applicable admin types
    admin_types = []
    
    if is_super_admin:
        admin_types.append("👑 **Super Admin** (Full bot control)")
    if is_bot_admin:
        admin_types.append("⚡ **Bot Admin** (Special privileges)")
    if can_restrict:
        admin_types.append("🔧 **Group Admin** (Group permissions)")
    
    if admin_types:
        status_text += "\n".join([f"• {t}" for t in admin_types])
    else:
        status_text += "• 👤 **Regular User** (No admin rights)"
    
    status_text += f"""

📊 **YOUR STATS IN THIS GROUP:**
• Warnings: {warn_count}/3 {progress_bar((warn_count/3)*100, 5)}
• Reports: {report_count}
• Last Activity: {last_activity[:16] if last_activity else 'Never'}
• Can Restrict: {'✅ Yes' if can_restrict else '❌ No'}

🔧 **AVAILABLE COMMANDS:**
"""
    
    # Determine available commands
    if is_super_admin:
        status_text += """
• **All commands** (Full access everywhere)
• Bot admin commands (`/bmute`, `/bban`, etc.)
• Group admin commands (`/mute`, `/ban`, etc.)
• Super admin commands (`/addbotadmin`, etc.)
"""
    elif is_bot_admin:
        status_text += """
• **Bot admin commands** (Works without group admin)
• `/bmute`, `/bban`, `/bwarn`, `/bpurge`
• `/block`, `/unblock`, `/mybotadmin`
• Works in all groups where bot is admin
"""
    elif can_restrict:
        status_text += """
• **Group admin commands**
• `/mute`, `/ban`, `/warn`, `/kick`, `/purge`
• `/lock`, `/unlock`, `/promote`, `/demote`
• Requires group admin permissions
"""
    else:
        status_text += """
• **Public commands only**
• `/start`, `/help`, `/rules`, `/admins`
• `/id`, `/info`, `/mystatus`, `/warns`
• `/abusestats`, `/tagall`, `/remind`
"""
    
    # Add special notes
    status_text += f"\n💡 **SPECIAL NOTES:**"
    
    if not bot_is_admin:
        status_text += "\n• ⚠️ Bot needs admin rights for full functionality"
    
    if warn_count >= 2:
        status_text += f"\n• ⚠️ You have {warn_count} warnings. Next may result in mute/ban"
    
    # Create buttons
    buttons = []
    
    # Admin-specific buttons
    if is_bot_admin or is_super_admin or can_restrict:
        buttons.append([
            InlineKeyboardButton("🔧 Mod Tools", callback_data="moderation_menu"),
            InlineKeyboardButton("🔒 Lock Menu", callback_data="lock_menu")
        ])
    
    # Information buttons
    buttons.append([
        InlineKeyboardButton("📊 Check Admin", callback_data=f"checkadmin:{user.id}"),
        InlineKeyboardButton("⚠️ My Warnings", callback_data=f"view_warnings:{user.id}:{chat.id}")
    ])
    
    # Utility buttons
    buttons.append([
        InlineKeyboardButton("📖 Help", callback_data="help_main"),
        InlineKeyboardButton("💬 Chat Info", callback_data=f"chat_info:{chat.id}")
    ])
    
    # Navigation buttons
    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="my_status"),
        InlineKeyboardButton("📊 Group Stats", callback_data=f"group_stats:{chat.id}")
    ])
    
    # Bot admin panel for bot admins
    if is_bot_admin or is_super_admin:
        buttons.append([
            InlineKeyboardButton("⚡ Bot Admin", callback_data="admin_panel"),
            InlineKeyboardButton("📋 Admin List", callback_data="list_admins")
        ])
    
    await cq.message.edit_text(
        status_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ================= HELPER FUNCTION FOR PROGRESS BAR =================
def progress_bar(percentage: int, length: int = 10) -> str:
    """Create a visual progress bar"""
    filled = "█" * int(percentage * length / 100)
    empty = "░" * (length - len(filled))
    return f"[{filled}{empty}] {percentage}%"


# ================= ADDITIONAL CALLBACK HANDLERS =================

@app.on_callback_query(filters.regex("^view_warnings:"))
async def view_warnings_callback(client, cq):
    """View user warnings"""
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Get warnings
        cur.execute(
            """
            SELECT reason, timestamp 
            FROM user_warnings 
            WHERE chat_id=? AND user_id=?
            ORDER BY timestamp DESC
            LIMIT 10
            """,
            (chat_id, user_id)
        )
        warnings = cur.fetchall()
        
        if warnings:
            warnings_text = "\n".join([
                f"• **{i+1}.** {reason[:50]} ({timestamp[:16]})"
                for i, (reason, timestamp) in enumerate(warnings)
            ])
            warn_msg = f"""
{beautiful_header('moderation')}

⚠️ **WARNING HISTORY**

**Total Warnings:** {len(warnings)}/3
{progress_bar((len(warnings)/3)*100, 5)}

**Recent Warnings:**
{warnings_text}
            """
        else:
            warn_msg = f"""
{beautiful_header('moderation')}

✅ **NO WARNINGS**

This user has no warnings in this group.
Clean behavior record.
            """
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📊 Abuse Stats", callback_data=f"abuse_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            warn_msg + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Warnings loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)


@app.on_callback_query(filters.regex("^chat_info:"))
async def chat_info_callback(client, cq):
    """Show chat information"""
    try:
        chat_id = int(cq.data.split(":")[1])
        chat = await client.get_chat(chat_id)
        
        # Get member count
        member_count = "Unknown"
        if hasattr(chat, 'members_count'):
            member_count = chat.members_count
        
        # Get chat admins count
        admin_count = 0
        try:
            async for member in client.get_chat_members(chat_id, filter=ChatMemberStatus.ADMINISTRATOR):
                if not member.user.is_bot:
                    admin_count += 1
        except:
            pass
        
        info_text = f"""
{beautiful_header('info')}

💬 **CHAT INFORMATION**

🏷️ **Basic Info:**
• **Title:** {chat.title}
• **ID:** `{chat.id}`
• **Type:** {chat.type.title()}
• **Members:** {member_count}
• **Admins:** {admin_count}

📝 **Description:**
{chat.description or 'No description'}

🔧 **Bot Status:**
• Bot Admin: {'✅ Yes' if await can_bot_restrict(client, chat_id) else '❌ No'}
• Bot Member: ✅ Yes
• Can Delete: {'✅ Yes' if await can_bot_restrict(client, chat_id) else '❌ No'}

📊 **Moderation Stats:**
"""
        
        # Get moderation stats
        cur.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE chat_id=?",
            (chat_id,)
        )
        total_warnings = cur.fetchone()[0]
        
        cur.execute(
            "SELECT COUNT(*) FROM user_reports WHERE chat_id=? AND status='pending'",
            (chat_id,)
        )
        pending_reports = cur.fetchone()[0]
        
        info_text += f"""
• Total Warnings: {total_warnings}
• Pending Reports: {pending_reports}
• Active Users: {len([k for k in user_warnings_cache.keys() if f':{chat_id}:' in k])}
"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📊 Group Stats", callback_data=f"group_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            info_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Chat info loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)


# ================= CALLBACK HANDLERS FOR MY_STATUS =================

# These callbacks are referenced in the buttons of my_status

@app.on_callback_query(filters.regex("^super_admin_panel$"))
async def super_admin_panel_callback(client, cq):
    """Show super admin panel"""
    if cq.from_user.id != SUPER_ADMIN:
        await cq.answer("❌ Super admin only!", show_alert=True)
        return
    
    admin_text = f"""
{beautiful_header('admin')}

👑 **SUPER ADMIN PANEL**

⚡ **Full System Control:**
• Add/remove bot admins
• System backup & restore
• Database management
• Bot configuration

🔧 **System Tools:**
• Mass message deletion
• Global user blocking
• System health check
• Log viewer

📊 **Statistics:**
• Total bot admins: {cur.execute("SELECT COUNT(*) FROM admins").fetchone()[0]}
• Blocked users: {cur.execute("SELECT COUNT(*) FROM blocked_users").fetchone()[0]}
• Database size: {os.path.getsize(DB_FILE) / 1024:.1f} KB
"""
    
    buttons = [
        [
            InlineKeyboardButton("👥 Manage Admins", callback_data="manage_admins"),
            InlineKeyboardButton("📋 List Admins", callback_data="list_admins")
        ],
        [
            InlineKeyboardButton("💾 Backup DB", callback_data="backup_db"),
            InlineKeyboardButton("🩺 Health Check", callback_data="health_check")
        ],
        [
            InlineKeyboardButton("🗑️ Mass Delete", callback_data="mass_delete_menu"),
            InlineKeyboardButton("📊 System Stats", callback_data="system_stats")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="admin_panel"),
            InlineKeyboardButton("🤖 Bot Info", callback_data="bot_info")
        ]
    ]
    
    await cq.message.edit_text(
        admin_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

@app.on_callback_query(filters.regex("^list_admins$"))
async def list_admins_callback(client, cq):
    """List all bot admins"""
    if not is_bot_admin(cq.from_user.id):
        await cq.answer("❌ Bot admins only!", show_alert=True)
        return
    
    cur.execute("SELECT admin_id FROM admins ORDER BY admin_id")
    admins = cur.fetchall()
    
    if not admins:
        admin_list = "📭 **No Bot Admins Found**"
    else:
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
        
        admin_list = "\n".join(admin_list)
    
    admin_text = f"""
{beautiful_header('admin')}

👥 **BOT ADMINISTRATORS**

{admin_list}

📊 **Total:** {len(admins)} admins
"""
    
    buttons = [
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="list_admins")]
    ]
    
    if cq.from_user.id == SUPER_ADMIN:
        buttons.insert(0, [
            InlineKeyboardButton("➕ Add Admin", callback_data="add_admin_menu"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin_menu")
        ])
    
    await cq.message.edit_text(
        admin_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

@app.on_callback_query(filters.regex("^moderation_menu$"))
async def moderation_menu_callback(client, cq):
    """Show moderation menu"""
    if not await can_user_restrict(client, cq.message.chat.id, cq.from_user.id) and not is_admin(cq.from_user.id):
        await cq.answer("❌ Admin permission required!", show_alert=True)
        return
    
    menu_text = f"""
{beautiful_header('moderation')}

🔧 **MODERATION TOOLS**

👤 **User Management:**
• Mute/Unmute users
• Ban/Unban users  
• Warn users
• Kick users

🗑️ **Message Management:**
• Purge messages
• Mass delete
• Cleanup tools

🔒 **Permission Control:**
• Lock/unlock features
• Set permissions
• Auto-moderation

📊 **Information:**
• User information
• Chat statistics
• Warning history
"""
    
    buttons = [
        [
            InlineKeyboardButton("🔇 Mute", callback_data="mute_menu"),
            InlineKeyboardButton("🚫 Ban", callback_data="ban_menu")
        ],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data="warn_menu"),
            InlineKeyboardButton("👢 Kick", callback_data="kick_menu")
        ],
        [
            InlineKeyboardButton("🗑️ Purge", callback_data="purge_menu"),
            InlineKeyboardButton("🔒 Lock", callback_data="lock_menu")
        ],
        [
            InlineKeyboardButton("📊 Info", callback_data="info_menu"),
            InlineKeyboardButton("📜 Rules", callback_data="rules_menu")
        ],
        [
            InlineKeyboardButton("⬅️ Back", callback_data="my_status"),
            InlineKeyboardButton("📖 Help", callback_data="help_main")
        ]
    ]
    
    await cq.message.edit_text(
        menu_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

@app.on_callback_query(filters.regex("^lock_menu$"))
async def lock_menu_callback(client, cq):
    """Show lock menu"""
    if not await can_user_restrict(client, cq.message.chat.id, cq.from_user.id) and not is_admin(cq.from_user.id):
        await cq.answer("❌ Admin permission required!", show_alert=True)
        return
    
    await lock_chat_permissions(client, cq.message)
    await cq.answer()

@app.on_callback_query(filters.regex("^checkadmin:"))
async def checkadmin_callback(client, cq):
    """Check admin status of user"""
    try:
        user_id = int(cq.data.split(":")[1])
        chat_id = cq.message.chat.id
        
        # Get user info
        user = await client.get_users(user_id)
        
        # Check admin status
        is_bot_admin_user = is_admin(user_id)
        is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
        
        status_text = f"""
{beautiful_header('info')}

🔍 **ADMIN STATUS CHECK**

👤 **User:** {user.mention}
🆔 **ID:** `{user_id}`

📊 **Admin Types:**
"""
        
        if user_id == SUPER_ADMIN:
            status_text += "• 👑 **Super Admin** (Full bot control)\n"
        elif is_bot_admin_user:
            status_text += "• ⚡ **Bot Admin** (Special privileges)\n"
        
        if is_group_admin_user:
            status_text += "• 🔧 **Group Admin** (Group permissions)\n"
        
        if not (user_id == SUPER_ADMIN or is_bot_admin_user or is_group_admin_user):
            status_text += "• 👤 **Regular User** (No admin rights)\n"
        
        # Get group role
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status == ChatMemberStatus.OWNER:
                group_role = "👑 Group Owner"
            elif member.status == ChatMemberStatus.ADMINISTRATOR:
                group_role = "⚡ Group Admin"
            elif member.status == ChatMemberStatus.MEMBER:
                group_role = "👤 Group Member"
            elif member.status == ChatMemberStatus.RESTRICTED:
                group_role = "🔇 Restricted"
            elif member.status == ChatMemberStatus.BANNED:
                group_role = "🚫 Banned"
            else:
                group_role = str(member.status)
        except:
            group_role = "❓ Unknown"
        
        status_text += f"\n🏢 **Group Role:** {group_role}"
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📊 User Info", callback_data=f"userinfo:{user_id}")]
        ]
        
        await cq.message.edit_text(
            status_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Admin status loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^view_warnings:"))
async def view_warnings_callback(client, cq):
    """View user warnings"""
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Get warnings
        cur.execute(
            """
            SELECT reason, timestamp 
            FROM user_warnings 
            WHERE chat_id=? AND user_id=?
            ORDER BY timestamp DESC
            LIMIT 10
            """,
            (chat_id, user_id)
        )
        warnings = cur.fetchall()
        
        if warnings:
            warnings_text = "\n".join([
                f"• **{i+1}.** {reason[:50]}... ({timestamp[:16]})"
                for i, (reason, timestamp) in enumerate(warnings)
            ])
            warn_msg = f"""
{beautiful_header('moderation')}

⚠️ **WARNING HISTORY**

**Total Warnings:** {len(warnings)}/3
{progress_bar((len(warnings)/3)*100, 5)}

**Recent Warnings:**
{warnings_text}
            """
        else:
            warn_msg = f"""
{beautiful_header('moderation')}

✅ **NO WARNINGS**

This user has no warnings in this group.
Clean behavior record.
            """
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📊 Abuse Stats", callback_data=f"abuse_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            warn_msg + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Warnings loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^chat_info:"))
async def chat_info_callback(client, cq):
    """Show chat information"""
    try:
        chat_id = int(cq.data.split(":")[1])
        chat = await client.get_chat(chat_id)
        
        # Get member count
        member_count = "Unknown"
        if hasattr(chat, 'members_count'):
            member_count = chat.members_count
        
        # Get chat admins count
        admin_count = 0
        try:
            async for member in client.get_chat_members(chat_id, filter=ChatMemberStatus.ADMINISTRATOR):
                if not member.user.is_bot:
                    admin_count += 1
        except:
            pass
        
        info_text = f"""
{beautiful_header('info')}

💬 **CHAT INFORMATION**

🏷️ **Basic Info:**
• **Title:** {chat.title}
• **ID:** `{chat.id}`
• **Type:** {chat.type.title()}
• **Members:** {member_count}
• **Admins:** {admin_count}

📝 **Description:**
{chat.description[:200] + '...' if chat.description and len(chat.description) > 200 else chat.description or 'No description'}

🔧 **Bot Status:**
• Bot Admin: {'✅ Yes' if await can_bot_restrict(client, chat_id) else '❌ No'}
• Bot Member: ✅ Yes
• Can Delete: {'✅ Yes' if await can_bot_restrict(client, chat_id) else '❌ No'}
"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📊 Group Stats", callback_data=f"group_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            info_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Chat info loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^group_stats:"))
async def group_stats_callback(client, cq):
    """Show group statistics"""
    try:
        chat_id = int(cq.data.split(":")[1])
        
        # Get group stats
        cur.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE chat_id=?",
            (chat_id,)
        )
        total_warnings = cur.fetchone()[0]
        
        cur.execute(
            "SELECT COUNT(*) FROM user_reports WHERE chat_id=?",
            (chat_id,)
        )
        total_reports = cur.fetchone()[0]
        
        cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_warnings WHERE chat_id=?",
            (chat_id,)
        )
        warned_users = cur.fetchone()[0]
        
        # Count users in cache
        cached_users = len([k for k in user_warnings_cache.keys() if f':{chat_id}:' in k])
        
        stats_text = f"""
{beautiful_header('info')}

📊 **GROUP STATISTICS**

📈 **Moderation Stats:**
• Total Warnings: {total_warnings}
• Total Reports: {total_reports}
• Warned Users: {warned_users}
• Active Tracking: {cached_users}

⚡ **Activity:**
• Last 24h Warnings: {cur.execute("SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND timestamp > datetime('now', '-1 day')", (chat_id,)).fetchone()[0]}
• Pending Reports: {cur.execute("SELECT COUNT(*) FROM user_reports WHERE chat_id=? AND status='pending'", (chat_id,)).fetchone()[0]}
• Resolved Reports: {cur.execute("SELECT COUNT(*) FROM user_reports WHERE chat_id=? AND status='resolved'", (chat_id,)).fetchone()[0]}

🔧 **System:**
• 3-Strike System: ✅ Active
• Abuse Detection: ✅ Active
• Auto-Moderation: ✅ Active
"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data=f"chat_info:{chat_id}")],
            [InlineKeyboardButton("📊 Abuse Stats", callback_data=f"abuse_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            stats_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Group stats loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^abuse_stats:"))
async def abuse_stats_callback(client, cq):
    """Show abuse statistics"""
    try:
        chat_id = int(cq.data.split(":")[1])
        
        # Get abuse stats
        cur.execute(
            """
            SELECT COUNT(*) 
            FROM user_warnings 
            WHERE chat_id=? AND reason LIKE '%Auto-%'
            """,
            (chat_id,)
        )
        total_incidents = cur.fetchone()[0]
        
        cur.execute(
            """
            SELECT user_id, COUNT(*) as count
            FROM user_warnings 
            WHERE chat_id=? AND reason LIKE '%Auto-%'
            GROUP BY user_id 
            ORDER BY count DESC 
            LIMIT 5
            """,
            (chat_id,)
        )
        top_abusers = cur.fetchall()
        
        stats_text = f"""
{beautiful_header('moderation')}

📊 **ABUSE STATISTICS**

📈 **Overview:**
• Total Abuse Incidents: {total_incidents}
• Active Tracking: {len([k for k in user_warnings_cache.keys() if f':{chat_id}:' in k])}
• System Status: ✅ ACTIVE

👥 **TOP 5 ABUSERS:**
"""
        
        if top_abusers:
            for i, (user_id, count) in enumerate(top_abusers, 1):
                try:
                    user = await client.get_users(user_id)
                    username = f"@{user.username}" if user.username else "No username"
                    stats_text += f"{i}. {user.first_name} ({username}) - {count} incidents\n"
                except:
                    stats_text += f"{i}. User `{user_id}` - {count} incidents\n"
        else:
            stats_text += "✅ No abuse incidents recorded!\n"
        
        stats_text += f"""
🔧 **System Info:**
• Detection Methods: 6 types
• Languages: English, Hindi
• Words Database: {len(ABUSE_WORDS)} words
• Auto-Moderation: ✅ ENABLED
"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"abuse_stats:{chat_id}")]
        ]
        
        await cq.message.edit_text(
            stats_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Abuse stats loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^userinfo:"))
async def userinfo_callback(client, cq):
    """Show user information"""
    try:
        user_id = int(cq.data.split(":")[1])
        user = await client.get_users(user_id)
        
        info_text = f"""
{beautiful_header('info')}

👤 **USER INFORMATION**

📱 **Basic Info:**
• **Name:** {user.first_name or ''} {user.last_name or ''}
• **ID:** `{user.id}`
• **Username:** @{user.username or 'None'}
• **Premium:** {'✅ Yes' if getattr(user, 'is_premium', False) else '❌ No'}
• **Bot:** {'🤖 Yes' if user.is_bot else '👤 Human'}
• **DC ID:** {user.dc_id if user.dc_id else 'Unknown'}

📊 **Status:**
{await get_user_status(client, user_id)}

💬 **Bio:**
{await get_user_bio(client, user_id) or 'No bio available'}

📸 **Profile Photos:** {await get_profile_photos_count(client, user_id)}
"""
        
        buttons = [
            [InlineKeyboardButton("⬅️ Back", callback_data="my_status")],
            [InlineKeyboardButton("📋 Copy ID", callback_data=f"copyid:{user_id}")]
        ]
        
        await cq.message.edit_text(
            info_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("User info loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

# ================= HELPER FUNCTIONS =================
async def get_user_status(client, user_id: int) -> str:
    """Get user's last seen status"""
    try:
        user = await client.get_users(user_id)
        if hasattr(user, 'status'):
            status = user.status
            if status.value == "online":
                return "🟢 **Online now**"
            elif status.value == "recently":
                return "🟡 **Recently online**"
            elif status.value == "within_week":
                return "🟡 **Within this week**"
            elif status.value == "within_month":
                return "🟡 **Within this month**"
            elif status.value == "long_time_ago":
                return "⚫ **Long time ago**"
        return "⚪ **Unknown**"
    except:
        return "⚪ **Unknown**"

async def get_user_bio(client, user_id: int) -> str:
    """Get user's bio"""
    try:
        user = await client.get_users(user_id)
        return user.bio or ""
    except:
        return ""

async def get_profile_photos_count(client, user_id: int) -> str:
    """Get profile photos count"""
    try:
        photos = await client.get_profile_photos_count(user_id)
        return f"{photos} photo{'s' if photos != 1 else ''}"
    except:
        return "Unknown"


@app.on_callback_query(filters.regex("^chat_info$"))
async def chat_info_callback(client, cq):
    """Show chat info"""
    await enhanced_id_command(client, cq.message)
    await cq.answer()

@app.on_callback_query(filters.regex("^tagall_menu$"))
async def tagall_menu_callback(client, cq):
    """Tagall menu"""
    await cq.message.edit_text(
        f"{beautiful_header('tools')}\n\n"
        "👥 **TAG ALL MEMBERS**\n\n"
        "Use `/tagall [message]` to mention all group members.\n\n"
        "⚠️ **Note:** Can be used once every 5 minutes.\n"
        "📊 Shows progress and member count.\n"
        "🔧 Group admin permission required."
        f"{beautiful_footer()}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="group_tools")],
            [InlineKeyboardButton("📖 Help", callback_data="help_main")]
        ])
    )
    await cq.answer()

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


# ================= CHECK ADMIN TYPE COMMAND =================
@app.on_message(filters.command("checkadmin") & filters.group)
async def check_admin_command(client, message: Message):
    """Check admin type of user"""
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        user_id = message.from_user.id
        user_obj = message.from_user
    
    is_bot_admin, is_group_admin, admin_type = await check_admin_type(client, message.chat.id, user_id)
    
    # Get group role
    try:
        member = await client.get_chat_member(message.chat.id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            group_role = "👑 Group Owner"
        elif member.status == ChatMemberStatus.ADMINISTRATOR:
            group_role = "⚡ Group Admin"
        else:
            group_role = "👤 Group Member"
    except:
        group_role = "❓ Unknown"
    
    status_text = f"""
{beautiful_header('info')}

🔍 **ADMIN STATUS CHECK**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`

📊 **Admin Type:** 
"""
    
    if admin_type == "super":
        status_text += "👑 **Super Admin**\n• Bot admin + super privileges\n• Can manage bot admins\n• Full access everywhere"
    elif admin_type == "bot":
        status_text += "⚡ **Bot Admin**\n• Can use bot admin commands\n• Doesn't need group admin rights\n• Works where bot is admin"
    elif admin_type == "group":
        status_text += "🔧 **Group Admin**\n• Has group admin permissions\n• Can use group admin commands\n• Limited to this group"
    else:
        status_text += "👤 **Regular User**\n• No admin privileges\n• Can only use public commands"
    
    status_text += f"\n\n🏢 **Group Role:** {group_role}"
    
    # Additional info
    if is_bot_admin:
        status_text += f"\n✅ **Bot Admin:** Yes (in database)"
    if is_group_admin:
        status_text += f"\n✅ **Group Admin:** Yes"
    
    status_text += f"\n\n💡 **Available Commands:**"
    
    if admin_type == "super":
        status_text += "\n• All bot admin commands (`/bmute`, `/bban`, etc.)"
        status_text += "\n• All group admin commands (`/mute`, `/ban`, etc.)"
        status_text += "\n• Bot admin management (`/addbotadmin`, etc.)"
    elif admin_type == "bot":
        status_text += "\n• Bot admin commands (`/bmute`, `/bban`, etc.)"
        status_text += "\n• Works without group admin rights"
    elif admin_type == "group":
        status_text += "\n• Group admin commands (`/mute`, `/ban`, etc.)"
        status_text += "\n• Requires group admin permissions"
    else:
        status_text += "\n• Public commands only"
    
    await message.reply_text(status_text + beautiful_footer())

# ================= MY STATUS COMMAND =================
@app.on_message(filters.command("mystatus") & filters.group)
async def my_status_command(client, message: Message):
    """Check your detailed status"""
    user_id = message.from_user.id
    user_obj = message.from_user
    
    is_bot_admin, is_group_admin, admin_type = await check_admin_type(client, message.chat.id, user_id)
    
    # Get detailed group member info
    try:
        member = await client.get_chat_member(message.chat.id, user_id)
        group_status = member.status
        
        if group_status == ChatMemberStatus.OWNER:
            group_role = "👑 Group Owner"
        elif group_status == ChatMemberStatus.ADMINISTRATOR:
            group_role = "⚡ Group Admin"
            # Get permissions if admin
            if hasattr(member, 'privileges'):
                perms = member.privileges
                perms_list = []
                if perms.can_restrict_members: perms_list.append("Restrict")
                if perms.can_delete_messages: perms_list.append("Delete")
                if perms.can_promote_members: perms_list.append("Promote")
                if perms.can_invite_users: perms_list.append("Invite")
                if perms.can_pin_messages: perms_list.append("Pin")
                group_role += f" [{' '.join(perms_list)}]"
        elif group_status == ChatMemberStatus.MEMBER:
            group_role = "👤 Group Member"
        elif group_status == ChatMemberStatus.RESTRICTED:
            group_role = "🔇 Restricted"
        elif group_status == ChatMemberStatus.BANNED:
            group_role = "🚫 Banned"
        else:
            group_role = str(group_status)
    except:
        group_role = "❓ Unknown"
    
    # Check bot status in group
    bot_is_admin = await can_bot_restrict(client, message.chat.id)
    
    status_text = f"""
{beautiful_header('info')}

📊 **YOUR STATUS DETAILS**

👤 **You:** {user_obj.mention}
🆔 **Your ID:** `{user_id}`
💬 **Chat ID:** `{message.chat.id}`

🎭 **ADMIN TYPES:**
"""
    
    # Admin type
    if admin_type == "super":
        status_text += "• 👑 **Super Admin** (Highest level)\n"
    elif admin_type == "bot":
        status_text += "• ⚡ **Bot Admin** (Bot management)\n"
    
    if is_group_admin:
        status_text += f"• 🔧 **Group Admin** (This group)\n"
    
    if admin_type == "none" and not is_group_admin:
        status_text += "• 👤 **Regular User** (No admin rights)\n"
    
    status_text += f"""
🏢 **GROUP STATUS:**
• **Role:** {group_role}
• **Chat:** {message.chat.title}
• **Bot Admin:** {'✅ Yes' if bot_is_admin else '❌ No'}

🔧 **AVAILABLE COMMANDS:**
"""
    
    # Available commands based on status
    if admin_type == "super":
        status_text += "• **All commands** (Full access)\n"
        status_text += "• Bot admin commands: `/bmute`, `/bban`, etc.\n"
        status_text += "• Group admin commands: `/mute`, `/ban`, etc.\n"
        status_text += "• Admin management: `/addbotadmin`, etc.\n"
    elif admin_type == "bot":
        status_text += "• **Bot admin commands**\n"
        status_text += "• `/bmute`, `/bban`, `/bwarn`, etc.\n"
        status_text += "• Works even if not group admin\n"
    elif is_group_admin:
        status_text += "• **Group admin commands**\n"
        status_text += "• `/mute`, `/ban`, `/warn`, etc.\n"
        status_text += "• Requires group admin permissions\n"
    else:
        status_text += "• **Public commands only**\n"
        status_text += "• `/start`, `/help`, `/rules`, etc.\n"
    
    # Warnings count
    cur.execute(
        "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
        (message.chat.id, user_id)
    )
    warn_count = cur.fetchone()[0]
    status_text += f"\n⚠️ **Your Warnings:** {warn_count}/3"
    
    await message.reply_text(status_text + beautiful_footer())


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

@app.on_message(filters.command("removebotadmin") & filters.private)
async def remove_bot_admin_command(client, message: Message):
    """Remove a bot admin (super admin only)"""
    if message.from_user.id != SUPER_ADMIN:
        await message.reply_text("❌ **Access Denied** - Super admin only")
        return
    
    if len(message.command) < 2:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Usage:** `/removebotadmin [user_id]`\n\n"
            "**Example:** `/removebotadmin 1234567890`"
            + beautiful_footer()
        )
        return
    
    try:
        admin_id = int(message.command[1])
        
        # Prevent removing super admin
        if admin_id == SUPER_ADMIN:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n"
                f"❌ **Cannot remove super admin**"
                + beautiful_footer()
            )
            return
        
        cur.execute("DELETE FROM admins WHERE admin_id=?", (admin_id,))
        conn.commit()
        
        try:
            user_obj = await client.get_users(admin_id)
            user_name = user_obj.mention
        except:
            user_name = f"User ID: `{admin_id}`"
        
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"✅ **Bot Admin Removed**\n\n"
            f"👤 **User:** {user_name}\n"
            f"🆔 **ID:** `{admin_id}`\n"
            f"👑 **Removed by:** {message.from_user.mention}"
            + beautiful_footer()
        )
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"❌ **Failed to Remove Admin**\nError: {str(e)}"
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

# ================= HELP COMMANDS =================
# ================= COMPLETE HELP COMMAND =================
@app.on_message(filters.command("help") & (filters.group | filters.private))
async def complete_help_command(client, message: Message):
    """Complete help command with all features"""
    
    # Check user admin status
    user_id = message.from_user.id
    chat_id = message.chat.id if message.chat.type != "private" else None
    
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = False
    
    if chat_id:
        is_group_admin_user = await can_user_restrict(client, chat_id, user_id) if chat_id else False
    
    help_text = f"""
{beautiful_header('info')}

🤖 **{BOT_BRAND} - COMPLETE COMMAND GUIDE**

👤 **PUBLIC COMMANDS (Everyone):**
• `/start` - Start the bot
• `/help` - Show this help menu
• `/rules` - Show group rules
• `/id` - Get complete user/chat info
• `/myid` - Get your ID only
• `/chatid` - Get chat ID only
• `/info [user]` - Get user information
• `/whois [user]` - Alias for /info
• `/fwdid` - Get ID of forwarded message
• `/extract` - Extract IDs from mentions
• `/warns [user]` - Check warnings
• `/admins` - List group admins
• `/mystatus` - Check your detailed status
• `/checkadmin [user]` - Check admin type
• `/status` - Check admin availability
• `/abusestats` - Show abuse statistics
• `/tagall [message]` - Tag all members
• `/remind [time] [message]` - Set reminder

🔔 **AUTO-REPORT SYSTEM:**
• Mention `@admin` in any message
• Bot automatically forwards to all admins
• Use `/responded` (reply) to mark as helped
• Admins get notification with quick actions
• Auto-cooldown to prevent spam

🔇 **AUTO-MODERATION SYSTEM:**
• Detects abusive language (Hindi/English)
• Auto-mutes based on severity (6h, 24h, 7d, ban)
• Notifies all admins about actions
• 100+ abusive words/phrases in database
• Evasion detection (misspellings, symbols)
• Flood protection (10 messages/10 seconds)
• Link protection (malicious URLs)

🆔 **ENHANCED INFORMATION COMMANDS:**
• `/id` - Complete info with buttons
• `/info @username` - User details
• `/info` (reply) - User info
• `/myid` - Your ID only
• `/chatid` - Chat ID only
• `/fwdid` (reply) - Original sender info
• `/extract @user1 @user2` - Bulk ID extract
• Shows: ID, username, premium, role, warnings, bio, last seen

"""
    
    # Add group admin commands
    if is_group_admin_user:
        help_text += """
🔧 **GROUP ADMIN COMMANDS (Need Group Admin):**

🗑️ **PURGE & DELETE:**
• `/purge [number]` - Delete messages (0 = ALL)
• `/purge` (reply) - Delete from reply to now
• `/del` - Delete replied message
• `/cleanup` - Clean specific message types
• `/purgebots` - Delete all bot messages
• `/purgeservice` - Delete service messages

🔒 **LOCK & UNLOCK:**
• `/lock [type]` - Lock chat permissions
• `/unlock [type]` - Unlock permissions
• `/lockstatus` - Show current lock status
• `/block [type]` - Alias for lock
• `/unblock [type]` - Alias for unlock

👤 **USER MODERATION:**
• `/mute [user] [duration] [reason]` - Mute user
• `/unmute [user]` - Unmute user
• `/ban [user] [reason]` - Ban user
• `/unban [user]` - Unban user
• `/kick [user] [reason]` - Kick user
• `/warn [user] [reason]` - Warn user

⚡ **OTHER ADMIN COMMANDS:**
• `/promote [user] [title]` - Promote to admin
• `/demote [user]` - Demote admin
• `/setrules [rules]` - Set group rules
• `/setwelcome [message]` - Set welcome message
• `/pin` - Pin message (reply)
• `/unpin` - Unpin message

"""
    
    # Add bot admin commands
    if is_bot_admin_user:
        help_text += """
⚡ **BOT ADMIN COMMANDS (Added as Bot Admin):**

🗑️ **PURGE COMMANDS:**
• `/bpurge [number]` - Purge (bot admin)
• `/massdelete` - Delete ALL messages
• `/clearchat` - Alias for massdelete

🔒 **LOCK COMMANDS:**
• `/block [type]` - Lock permissions
• `/unblock [type]` - Unlock permissions

👤 **MODERATION COMMANDS:**
• `/bmute [user] [duration] [reason]` - Mute
• `/bunmute [user]` - Unmute
• `/bban [user] [reason]` - Ban
• `/bunban [user]` - Unban
• `/bkick [user] [reason]` - Kick
• `/bwarn [user] [reason]` - Warn

ℹ️ **INFO COMMANDS:**
• `/mybotadmin` - Check bot admin status
• `/bhelp` - Bot admin help

"""
    
    # Add super admin commands
    if user_id == SUPER_ADMIN:
        help_text += """
👑 **SUPER ADMIN COMMANDS (Private Chat Only):**
• `/addbotadmin [user_id]` - Add bot admin
• `/removebotadmin [user_id]` - Remove bot admin
• `/listbotadmins` - List all bot admins
• `/backup` - Create database backup
• `/health` - Check bot health stats

"""
    
    # Add detailed explanations
    help_text += """
📋 **COMMAND DETAILS:**

⏰ **DURATION FORMAT:**
• `30m` = 30 minutes
• `2h` = 2 hours  
• `1d` = 1 day
• `1w` = 1 week
• `0` = Permanent

🔒 **LOCK TYPES (17 Types):**
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
• `forward` - Forwarded messages (auto-delete)

🗑️ **PURGE MODES:**
• `/purge 50` - Delete last 50 messages
• `/purge 0` - Delete ALL messages (no limit)
• `/purge` (reply) - Delete from reply to command
• `/massdelete` - Nuclear option (super admin)

🧹 **CLEANUP TYPES:**
• `bots` - Bot messages only
• `service` - Service messages
• `links` - URLs only
• `media` - Photos/videos
• `games` - Games & bots
• `stickers` - Stickers only
• `all` - Everything

👥 **USER TARGETING:**
• Reply to user's message
• `@username`
• `user_id`
• Multiple `@user1 @user2 @user3`

📊 **ABUSE DETECTION LEVELS:**
• **Level 1-2:** Warning only
• **Level 3:** 6-hour mute
• **Level 4:** 24-hour mute
• **Level 5:** 7-day ban
• **Repeated offenses:** Permanent ban

🔔 **AUTO-REPORT TRIGGERS:**
• `@admin`
• `admin help`
• `help admin`
• `admins please`
• `admin ji`
• `@admins`
• `call admin`
• `admin aao`

"""
    
    # Add notes and tips
    help_text += """
💡 **TIPS & NOTES:**

✅ **For best results:**
1. Make bot admin with all permissions
2. Add trusted users as bot admins
3. Set group rules with `/setrules`
4. Use `/lock all` during raids
5. Use `/purge 0` for mass cleaning

⚠️ **Important:**
• Bot needs admin rights for moderation
• Cannot moderate group admins/owner
• Some commands work only in groups
• Mass delete requires confirmation
• Lock changes apply to all members

🛡️ **SECURITY FEATURES:**
• Multi-tier admin system
• Abuse word detection
• Flood protection
• Link filtering
• Auto-backup system
• Activity logging

📞 **SUPPORT:**
• Contact bot in private for support
• Use @admin mentions in groups
• Reports are forwarded to all admins
• Quick action buttons for admins

"""
    
    # Add buttons for quick navigation
    buttons = []
    
    if message.chat.type == "private":
        buttons.append([InlineKeyboardButton("📖 Basic Commands", callback_data="help_basic")])
    else:
        buttons.append([InlineKeyboardButton("👤 Public Commands", callback_data="help_public")])
    
    if is_group_admin_user:
        buttons.append([InlineKeyboardButton("🔧 Group Admin", callback_data="help_group_admin")])
    
    if is_bot_admin_user:
        buttons.append([InlineKeyboardButton("⚡ Bot Admin", callback_data="help_bot_admin")])
    
    if user_id == SUPER_ADMIN:
        buttons.append([InlineKeyboardButton("👑 Super Admin", callback_data="help_super_admin")])
    
    buttons.append([
        InlineKeyboardButton("🗑️ Purge Help", callback_data="help_purge"),
        InlineKeyboardButton("🔒 Lock Help", callback_data="help_lock")
    ])
    
    buttons.append([
        InlineKeyboardButton("🤖 Bot Info", callback_data="bot_info"),
        InlineKeyboardButton("⚙️ Settings", callback_data="settings_menu")
    ])
    
    await message.reply_text(
        help_text + beautiful_footer(),
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        disable_web_page_preview=True
  )




# ================= STORE LOCK STATES PER CHAT =================
chat_locks = {}


# ================= LOCK & UNLOCK COMMANDS =================
@app.on_message(filters.command(["lock", "block"]) & filters.group)
async def lock_chat_permissions(client, message: Message):
    """Lock specific permissions in the group"""
    
    # Check permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "❌ **Permission Denied**"
            f"{beautiful_footer()}"
        )
        return
    
    # Check bot permissions
    try:
        bot_member = await client.get_chat_member(chat_id, "me")
        if not (hasattr(bot_member, 'privileges') and bot_member.privileges.can_change_info):
            await message.reply_text(
                f"{beautiful_header('settings')}\n\n"
                "❌ **Bot Needs Change Info Permission**"
                f"{beautiful_footer()}"
            )
            return
    except:
        pass
    
    # Parse lock type
    lock_types = {
        "all": "🔒 Lock All",
        "text": "📝 Text Messages",
        "media": "🖼️ Media Messages",
        "stickers": "😀 Stickers & GIFs",
        "polls": "📊 Polls",
        "invites": "👥 Invite Links",
        "pins": "📌 Pin Messages",
        "info": "ℹ️ Chat Info",
        "url": "🔗 URLs/Links",
        "games": "🎮 Games",
        "inline": "🔍 Inline Bots",
        "voice": "🎤 Voice Messages",
        "video": "🎥 Video Messages",
        "audio": "🎵 Audio Messages",
        "documents": "📎 Documents",
        "photos": "📸 Photos",
        "forward": "📨 Forwarded Messages"
    }
    
    if len(message.command) < 2:
        # Show lock menu
        buttons = []
        row = []
        for i, (lock_type, lock_name) in enumerate(lock_types.items()):
            row.append(InlineKeyboardButton(lock_name, callback_data=f"lock:{lock_type}"))
            if (i + 1) % 2 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("🔓 Unlock All", callback_data="unlock:all")])
        
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "🔒 **LOCK SETTINGS**\n\n"
            "Select what you want to lock:\n\n"
            "• **all** - Lock everything\n"
            "• **text** - Text messages only\n"
            "• **media** - All media messages\n"
            "• **stickers** - Stickers & GIFs\n"
            "• **polls** - Polls\n"
            "• **invites** - Invite links\n"
            "• **pins** - Pin messages\n"
            "• **info** - Change chat info\n"
            "• **url** - URLs/links\n"
            "• **games** - Games\n"
            "• **inline** - Inline bots\n"
            "• **voice** - Voice messages\n"
            "• **video** - Video messages\n"
            "• **audio** - Audio messages\n"
            "• **documents** - Documents\n"
            "• **photos** - Photos only\n"
            "• **forward** - Forwarded messages"
            f"{beautiful_footer()}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    lock_type = message.command[1].lower()
    
    if lock_type not in lock_types:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"❌ **Invalid lock type:** `{lock_type}`\n\n"
            f"**Available types:**\n"
            f"`all`, `text`, `media`, `stickers`, `polls`, `invites`, `pins`, `info`, `url`, `games`, `inline`, `voice`, `video`, `audio`, `documents`, `photos`, `forward`"
            f"{beautiful_footer()}"
        )
        return
    
    # Apply lock
    try:
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
        
        # Apply specific lock
        if lock_type == "all":
            current_permissions = ChatPermissions()  # All False
            lock_message = "🔒 **Everything is now locked!**\nNo one can send anything."
        
        elif lock_type == "text":
            current_permissions.can_send_messages = False
            lock_message = "📝 **Text messages locked!**\nUsers cannot send text."
        
        elif lock_type == "media":
            current_permissions.can_send_media_messages = False
            current_permissions.can_send_other_messages = False
            lock_message = "🖼️ **Media locked!**\nUsers cannot send media."
        
        elif lock_type == "stickers":
            current_permissions.can_send_other_messages = False
            lock_message = "😀 **Stickers & GIFs locked!**\nUsers cannot send stickers/GIFs."
        
        elif lock_type == "polls":
            current_permissions.can_send_polls = False
            lock_message = "📊 **Polls locked!**\nUsers cannot create polls."
        
        elif lock_type == "invites":
            current_permissions.can_invite_users = False
            lock_message = "👥 **Invite links locked!**\nUsers cannot invite others."
        
        elif lock_type == "pins":
            current_permissions.can_pin_messages = False
            lock_message = "📌 **Pin messages locked!**\nUsers cannot pin messages."
        
        elif lock_type == "info":
            current_permissions.can_change_info = False
            lock_message = "ℹ️ **Chat info locked!**\nUsers cannot change chat info."
        
        elif lock_type == "url":
            current_permissions.can_add_web_page_previews = False
            lock_message = "🔗 **URLs locked!**\nUsers cannot send links."
        
        elif lock_type == "games":
            current_permissions.can_send_other_messages = False
            lock_message = "🎮 **Games locked!**\nUsers cannot send games."
        
        elif lock_type == "inline":
            current_permissions.can_send_other_messages = False
            lock_message = "🔍 **Inline bots locked!**\nUsers cannot use inline bots."
        
        elif lock_type == "voice":
            current_permissions.can_send_media_messages = False
            lock_message = "🎤 **Voice messages locked!**\nUsers cannot send voice."
        
        elif lock_type == "video":
            current_permissions.can_send_media_messages = False
            lock_message = "🎥 **Video messages locked!**\nUsers cannot send video."
        
        elif lock_type == "audio":
            current_permissions.can_send_media_messages = False
            lock_message = "🎵 **Audio messages locked!**\nUsers cannot send audio."
        
        elif lock_type == "documents":
            current_permissions.can_send_media_messages = False
            lock_message = "📎 **Documents locked!**\nUsers cannot send documents."
        
        elif lock_type == "photos":
            current_permissions.can_send_media_messages = False
            lock_message = "📸 **Photos locked!**\nUsers cannot send photos."
        
        elif lock_type == "forward":
            # Note: Forward locking requires message filtering
            lock_message = "📨 **Forwarded messages will be deleted!**\nAuto-delete enabled."
        
        # Store lock state
        if chat_id not in chat_locks:
            chat_locks[chat_id] = {}
        chat_locks[chat_id][lock_type] = True
        
        # Apply permissions (except for forward which needs filtering)
        if lock_type != "forward":
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=current_permissions
            )
        
        # Get admin type
        admin_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
        
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"✅ **LOCK APPLIED**\n\n"
            f"{lock_message}\n\n"
            f"🔒 **Type:** {lock_types[lock_type]}\n"
            f"👨‍💼 **By:** {message.from_user.mention}\n"
            f"🔧 **Admin Type:** {admin_type}\n\n"
            f"Use `/unlock {lock_type}` to remove this lock."
            f"{beautiful_footer()}"
        )
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"❌ **Lock Failed**\nError: {str(e)[:100]}"
            f"{beautiful_footer()}"
        )

@app.on_message(filters.command(["unlock", "unblock"]) & filters.group)
async def unlock_chat_permissions(client, message: Message):
    """Unlock specific permissions in the group"""
    
    # Check permissions
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "❌ **Permission Denied**"
            f"{beautiful_footer()}"
        )
        return
    
    # Parse unlock type
    unlock_types = {
        "all": "🔓 Unlock All",
        "text": "📝 Text Messages",
        "media": "🖼️ Media Messages",
        "stickers": "😀 Stickers & GIFs",
        "polls": "📊 Polls",
        "invites": "👥 Invite Links",
        "pins": "📌 Pin Messages",
        "info": "ℹ️ Chat Info",
        "url": "🔗 URLs/Links",
        "games": "🎮 Games",
        "inline": "🔍 Inline Bots",
        "voice": "🎤 Voice Messages",
        "video": "🎥 Video Messages",
        "audio": "🎵 Audio Messages",
        "documents": "📎 Documents",
        "photos": "📸 Photos",
        "forward": "📨 Forwarded Messages"
    }
    
    if len(message.command) < 2:
        # Show unlock menu
        buttons = []
        row = []
        for i, (unlock_type, unlock_name) in enumerate(unlock_types.items()):
            row.append(InlineKeyboardButton(unlock_name, callback_data=f"unlock:{unlock_type}"))
            if (i + 1) % 2 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("🔒 Lock All", callback_data="lock:all")])
        
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            "🔓 **UNLOCK SETTINGS**\n\n"
            "Select what you want to unlock:\n\n"
            "• **all** - Unlock everything\n"
            "• **text** - Text messages only\n"
            "• **media** - All media messages\n"
            "• **stickers** - Stickers & GIFs\n"
            "• **polls** - Polls\n"
            "• **invites** - Invite links\n"
            "• **pins** - Pin messages\n"
            "• **info** - Change chat info\n"
            "• **url** - URLs/links\n"
            "• **games** - Games\n"
            "• **inline** - Inline bots\n"
            "• **voice** - Voice messages\n"
            "• **video** - Video messages\n"
            "• **audio** - Audio messages\n"
            "• **documents** - Documents\n"
            "• **photos** - Photos only\n"
            "• **forward** - Forwarded messages"
            f"{beautiful_footer()}",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return
    
    unlock_type = message.command[1].lower()
    
    if unlock_type not in unlock_types:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"❌ **Invalid unlock type:** `{unlock_type}`\n\n"
            f"**Available types:**\n"
            f"`all`, `text`, `media`, `stickers`, `polls`, `invites`, `pins`, `info`, `url`, `games`, `inline`, `voice`, `video`, `audio`, `documents`, `photos`, `forward`"
            f"{beautiful_footer()}"
        )
        return
    
    # Apply unlock
    try:
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
                chat_locks[chat_id].clear()
            
            unlock_message = "🔓 **Everything unlocked!**\nAll permissions restored."
        
        elif unlock_type == "forward":
            # Remove forward lock
            if chat_id in chat_locks and "forward" in chat_locks[chat_id]:
                del chat_locks[chat_id]["forward"]
            unlock_message = "📨 **Forwarded messages allowed!**\nAuto-delete disabled."
        
        else:
            # Unlock specific permission
            await client.set_chat_permissions(
                chat_id=chat_id,
                permissions=default_permissions
            )
            
            # Remove from lock state
            if chat_id in chat_locks and unlock_type in chat_locks[chat_id]:
                del chat_locks[chat_id][unlock_type]
            
            unlock_message = f"🔓 **{unlock_types[unlock_type]} unlocked!**"
        
        # Get admin type
        admin_type = "Bot Admin" if is_bot_admin_user else "Group Admin"
        
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"✅ **UNLOCK APPLIED**\n\n"
            f"{unlock_message}\n\n"
            f"🔓 **Type:** {unlock_types[unlock_type]}\n"
            f"👨‍💼 **By:** {message.from_user.mention}\n"
            f"🔧 **Admin Type:** {admin_type}"
            f"{beautiful_footer()}"
        )
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"❌ **Unlock Failed**\nError: {str(e)[:100]}"
            f"{beautiful_footer()}"
      )

# ================= LOCK STATUS COMMAND =================
@app.on_message(filters.command("lockstatus") & filters.group)
async def lock_status_command(client, message: Message):
    """Show current lock status of the chat"""
    
    chat_id = message.chat.id
    
    # Get current permissions
    try:
        chat = await client.get_chat(chat_id)
        permissions = chat.permissions
        
        status_text = f"""
{beautiful_header('settings')}

🔒 **CHAT LOCK STATUS**

📊 **Current Permissions:**
• 📝 **Text:** {'✅ Allowed' if permissions.can_send_messages else '❌ Locked'}
• 🖼️ **Media:** {'✅ Allowed' if permissions.can_send_media_messages else '❌ Locked'}
• 😀 **Stickers/GIFs:** {'✅ Allowed' if permissions.can_send_other_messages else '❌ Locked'}
• 📊 **Polls:** {'✅ Allowed' if permissions.can_send_polls else '❌ Locked'}
• 🔗 **URLs:** {'✅ Allowed' if permissions.can_add_web_page_previews else '❌ Locked'}
• 👥 **Invites:** {'✅ Allowed' if permissions.can_invite_users else '❌ Locked'}
• 📌 **Pins:** {'✅ Allowed' if permissions.can_pin_messages else '❌ Locked'}
• ℹ️ **Change Info:** {'✅ Allowed' if permissions.can_change_info else '❌ Locked'}

"""
        
        # Show active locks
        if chat_id in chat_locks and chat_locks[chat_id]:
            active_locks = list(chat_locks[chat_id].keys())
            status_text += f"🔐 **Active Locks:** {', '.join(active_locks)}"
        else:
            status_text += "✅ **No active locks**\nChat is fully unlocked."
        
        # Add quick action buttons
        buttons = [
            [
                InlineKeyboardButton("🔒 Lock Menu", callback_data="lock_menu"),
                InlineKeyboardButton("🔓 Unlock Menu", callback_data="unlock_menu")
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="refresh_lock_status")
            ]
        ]
        
        await message.reply_text(
            status_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n"
            f"❌ **Failed to get status**\nError: {str(e)[:100]}"
            f"{beautiful_footer()}"
        )


# ================= LOCK/UNLOCK CALLBACK HANDLERS =================
@app.on_callback_query(filters.regex("^lock:"))
async def lock_callback_handler(client, cq):
    """Handle lock callbacks"""
    
    lock_type = cq.data.split(":")[1]
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id
    
    # Check permissions
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await cq.answer("Permission denied", show_alert=True)
        return
    
    # Create a fake message object
    class FakeMessage:
        def __init__(self):
            self.chat = cq.message.chat
            self.from_user = cq.from_user
            self.command = ["lock", lock_type]
    
    fake_msg = FakeMessage()
    
    # Call the lock function
    await lock_chat_permissions(client, fake_msg)
    
    await cq.answer(f"Locking {lock_type}...")
    await cq.message.delete()

@app.on_callback_query(filters.regex("^unlock:"))
async def unlock_callback_handler(client, cq):
    """Handle unlock callbacks"""
    
    unlock_type = cq.data.split(":")[1]
    chat_id = cq.message.chat.id
    user_id = cq.from_user.id
    
    # Check permissions
    is_bot_admin_user = is_bot_admin(user_id)
    is_group_admin_user = await can_user_restrict(client, chat_id, user_id)
    
    if not (is_group_admin_user or is_bot_admin_user):
        await cq.answer("Permission denied", show_alert=True)
        return
    
    # Create a fake message object
    class FakeMessage:
        def __init__(self):
            self.chat = cq.message.chat
            self.from_user = cq.from_user
            self.command = ["unlock", unlock_type]
    
    fake_msg = FakeMessage()
    
    # Call the unlock function
    await unlock_chat_permissions(client, fake_msg)
    
    await cq.answer(f"Unlocking {unlock_type}...")
    await cq.message.delete()

@app.on_callback_query(filters.regex("^lock_menu$"))
async def lock_menu_callback(client, cq):
    """Show lock menu"""
    
    lock_types = {
        "all": "🔒 Lock All",
        "text": "📝 Text Messages",
        "media": "🖼️ Media Messages",
        "stickers": "😀 Stickers & GIFs",
        "polls": "📊 Polls",
        "invites": "👥 Invite Links",
        "pins": "📌 Pin Messages",
        "info": "ℹ️ Chat Info",
        "url": "🔗 URLs/Links",
        "games": "🎮 Games",
        "inline": "🔍 Inline Bots",
        "voice": "🎤 Voice Messages",
        "video": "🎥 Video Messages",
        "audio": "🎵 Audio Messages",
        "documents": "📎 Documents",
        "photos": "📸 Photos",
        "forward": "📨 Forwarded Messages"
    }
    
    buttons = []
    row = []
    for i, (lock_type, lock_name) in enumerate(lock_types.items()):
        row.append(InlineKeyboardButton(lock_name, callback_data=f"lock:{lock_type}"))
        if (i + 1) % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("🔓 Unlock Menu", callback_data="unlock_menu")])
    buttons.append([InlineKeyboardButton("📊 Status", callback_data="refresh_lock_status")])
    
    await cq.message.edit_text(
        f"{beautiful_header('settings')}\n\n"
        "🔒 **SELECT LOCK TYPE**\n\n"
        "Choose what you want to lock:"
        f"{beautiful_footer()}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

@app.on_callback_query(filters.regex("^unlock_menu$"))
async def unlock_menu_callback(client, cq):
    """Show unlock menu"""
    
    unlock_types = {
        "all": "🔓 Unlock All",
        "text": "📝 Text Messages",
        "media": "🖼️ Media Messages",
        "stickers": "😀 Stickers & GIFs",
        "polls": "📊 Polls",
        "invites": "👥 Invite Links",
        "pins": "📌 Pin Messages",
        "info": "ℹ️ Chat Info",
        "url": "🔗 URLs/Links",
        "games": "🎮 Games",
        "inline": "🔍 Inline Bots",
        "voice": "🎤 Voice Messages",
        "video": "🎥 Video Messages",
        "audio": "🎵 Audio Messages",
        "documents": "📎 Documents",
        "photos": "📸 Photos",
        "forward": "📨 Forwarded Messages"
    }
    
    buttons = []
    row = []
    for i, (unlock_type, unlock_name) in enumerate(unlock_types.items()):
        row.append(InlineKeyboardButton(unlock_name, callback_data=f"unlock:{unlock_type}"))
        if (i + 1) % 2 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton("🔒 Lock Menu", callback_data="lock_menu")])
    buttons.append([InlineKeyboardButton("📊 Status", callback_data="refresh_lock_status")])
    
    await cq.message.edit_text(
        f"{beautiful_header('settings')}\n\n"
        "🔓 **SELECT UNLOCK TYPE**\n\n"
        "Choose what you want to unlock:"
        f"{beautiful_footer()}",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    
    await cq.answer()

@app.on_callback_query(filters.regex("^refresh_lock_status$"))
async def refresh_lock_status_callback(client, cq):
    """Refresh lock status"""
    await lock_status_command(client, cq.message)
    await cq.answer("Status refreshed")


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
                
                # Send warning (auto-delete after 5 seconds)
                warning = await message.reply_text(
                    f"{beautiful_header('security')}\n\n"
                    "📨 **Forwarded Message Blocked**\n\n"
                    f"👤 **User:** {message.from_user.mention}\n"
                    "❌ **Action:** Message deleted\n\n"
                    "⚠️ Forwarding messages is currently locked in this group."
                    f"{beautiful_footer()}"
                )
                
                await asyncio.sleep(5)
                await warning.delete()
                
            except:
                pass



# ================= ADMIN PROMOTION SYSTEM (COMPLETE) =================
from pyrogram import filters
from pyrogram.types import Message, ChatPrivileges
from pyrogram.enums import ChatMemberStatus

@app.on_message(filters.command("promote") & filters.group)
async def promote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    # ================= CALLER STATUS =================
    member = await client.get_chat_member(chat_id, caller_id)

    is_owner = member.status == ChatMemberStatus.OWNER
    is_group_admin = member.status == ChatMemberStatus.ADMINISTRATOR
    is_bot_admin_user = is_bot_admin(caller_id)  # bot / super admin

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
            "❌ **Make me admin first**\n"
            "I need **Add New Admins** permission."
            f"{beautiful_footer()}"
        )
        return

    if hasattr(bot, "privileges") and not bot.privileges.can_promote_members:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Bot missing permission**\n"
            "Enable **Add New Admins**."
            f"{beautiful_footer()}"
        )
        return

    # ================= TARGET USER =================
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        args = message.command[1:]
    elif len(message.command) > 1:
        target = await client.get_users(message.command[1])
        args = message.command[2:]
    else:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Usage:**\n"
            "`/tpromote @user [title]`\n"
            "or reply + `/tpromote [title]`"
            f"{beautiful_footer()}"
        )
        return

    if target.id == caller_id:
        await message.reply_text("❌ You cannot promote yourself")
        return

    if target.is_bot:
        await message.reply_text("❌ Bots cannot be promoted")
        return

    target_member = await client.get_chat_member(chat_id, target.id)
    if target_member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        await message.reply_text("⚠️ User is already an admin")
        return

    # ================= ADMIN TITLE =================
    title = "Admin"
    if args:
        title = " ".join(args)[:16]  # Telegram limit = 16 chars

    # ================= PRIVILEGES =================
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
            can_promote_members=False,
            can_change_info=False,
            can_manage_chat=False,
            is_anonymous=False
        )
        promoter_type = "Group Admin"

    # ================= PROMOTE =================
    await client.promote_chat_member(chat_id, target.id, privileges)

    # ================= SET ADMIN TITLE =================
    try:
        await client.set_administrator_title(
            chat_id=chat_id,
            user_id=target.id,
            title=title
        )
    except Exception as e:
        print(f"Admin title set failed: {e}")

    # ================= SUCCESS MESSAGE =================
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        "✅ **PROMOTED SUCCESSFULLY**\n\n"
        f"👤 **User:** {target.mention}\n"
        f"🏷️ **Title:** {title}\n"
        f"🔧 **By:** {caller.mention} ({promoter_type})"
        f"{beautiful_footer()}"
    )

@app.on_message(filters.command("demote") & filters.group)
async def demote_command(client, message: Message):
    chat_id = message.chat.id
    caller = message.from_user
    caller_id = caller.id

    is_bot_admin_user = is_bot_admin(caller_id)
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



# ================= HELPER FUNCTIONS =================
async def can_user_promote(client, chat_id, user_id):
    """Check if user can promote members"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        
        # Owner can always promote
        if member.status == ChatMemberStatus.OWNER:
            return True
        
        # Check admin privileges
        if member.status == ChatMemberStatus.ADMINISTRATOR:
            if hasattr(member, 'privileges'):
                return member.privileges.can_promote_members
            elif hasattr(member, 'can_promote_members'):
                return member.can_promote_members
        
        return False
    except:
        return False


async def can_bot_promote(client, chat_id):
    """Check if bot can promote members"""
    return await can_user_promote(client, chat_id, "me")



# ================= PROMOTION REQUEST STORAGE =================
promotion_requests = {}

# ================= HANDLE TITLE INPUT =================
@app.on_message(filters.text & filters.group)
async def handle_promotion_title(client, message: Message):
    """Handle promotion title input"""
    user_key = f"{message.from_user.id}:{message.chat.id}"
    
    # Find matching promotion request
    for key, data in list(promotion_requests.items()):
        if key.startswith(user_key + ":"):
            if message.text.lower() == "cancel":
                await message.reply_text("❌ Promotion cancelled.")
                del promotion_requests[key]
                return
            
            parts = key.split(":")
            target_user_id = int(parts[2])
            target_user = data["user"]
            
            try:
                # Promote with title
                privileges = ChatPrivileges(
                    can_change_info=True,
                    can_delete_messages=True,
                    can_restrict_members=True,
                    can_invite_users=True,
                    can_pin_messages=True,
                    can_promote_members=False,
                    can_manage_video_chats=True,
                    is_anonymous=False,
                    can_manage_chat=False
                )
                
                await client.promote_chat_member(
                    chat_id=message.chat.id,
                    user_id=target_user_id,
                    privileges=privileges
                )
                
                # Set title
                title = message.text[:16]  # Max 16 chars
                try:
                    await client.set_administrator_title(
                        chat_id=message.chat.id,
                        user_id=target_user_id,
                        title=title
                    )
                except:
                    pass
                
                # Send success message
                promo_msg = promotion_card(
                    user_mention=target_user.mention,
                    user_id=target_user_id,
                    title=title
                )
                
                await message.reply_text(promo_msg)
                
                # Log promotion
                cur.execute(
                    "INSERT INTO admin_promotions (chat_id, user_id, promoted_by, title) VALUES (?, ?, ?, ?)",
                    (message.chat.id, target_user_id, message.from_user.id, title)
                )
                conn.commit()
                
                # Delete request
                del promotion_requests[key]
                
                # Delete title message
                await message.delete()
                
            except Exception as e:
                await message.reply_text(f"❌ Promotion failed: {str(e)[:100]}")
                del promotion_requests[key]
            
            break

        
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


@app.on_message(filters.private & filters.command("lockstatus"))
async def bot_admin_lock_status_command(client, message: Message):
    """Check lock status by chat ID"""
    
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
            "📊 **LOCK STATUS CHECK**\n\n"
            "**Usage:** `/lockstatus <chat_id>`\n\n"
            "**Example:** `/lockstatus -100123456789`"
            f"{beautiful_footer()}"
        )
        return
    
    try:
        chat_id = int(message.command[1])
        
        # Get chat info
        try:
            chat = await client.get_chat(chat_id)
            chat_title = chat.title
            chat_type = chat.type
        except:
            chat_title = f"Chat ID: {chat_id}"
            chat_type = "Unknown"
        
        # Get current lock info
        current_lock = group_locks.get(chat_id)
        
        # Get current permissions from Telegram
        try:
            chat_info = await client.get_chat(chat_id)
            perms = chat_info.permissions
            
            # Check bot admin status
            bot_is_admin = await can_bot_restrict(client, chat_id)
        except:
            perms = None
            bot_is_admin = False
        
        # Build status message
        status_msg = f"""
{beautiful_header('admin')}

📊 **LOCK STATUS REPORT**

🏷️ **Chat:** {chat_title}
🆔 **Chat ID:** `{chat_id}`
👥 **Type:** {chat_type}
🤖 **Bot Admin:** {'✅ Yes' if bot_is_admin else '❌ No'}

"""
        
        if current_lock:
            time_since = datetime.now(timezone.utc) - current_lock["applied_at"]
            hours = int(time_since.total_seconds() // 3600)
            minutes = int((time_since.total_seconds() % 3600) // 60)
            
            status_msg += f"""
🔒 **CURRENT LOCK:**
• Type: {current_lock['type']}
• Applied: {current_lock['applied_at'].strftime('%Y-%m-%d %H:%M:%S UTC')}
• Duration: {current_lock['duration'] or 'Permanent'}
• Expires: {current_lock['expires'].strftime('%Y-%m-%d %H:%M:%S UTC') if current_lock['expires'] else 'Never'}
• Active For: {hours}h {minutes}m
"""
        else:
            status_msg += "🔓 **NO ACTIVE LOCK**\nChat is currently unlocked.\n"
        
        if perms:
            status_msg += f"""
📋 **CURRENT PERMISSIONS:**
• Send Messages: {'✅' if perms.can_send_messages else '❌'}
• Send Media: {'✅' if perms.can_send_media_messages else '❌'}
• Send Other: {'✅' if perms.can_send_other_messages else '❌'}
• Web Previews: {'✅' if perms.can_add_web_page_previews else '❌'}
• Send Polls: {'✅' if perms.can_send_polls else '❌'}
• Change Info: {'✅' if perms.can_change_info else '❌'}
• Invite Users: {'✅' if perms.can_invite_users else '❌'}
• Pin Messages: {'✅' if perms.can_pin_messages else '❌'}
"""
        
        # Add quick action buttons
        buttons = []
        if current_lock:
            buttons.append([
                InlineKeyboardButton("🔓 Unlock", callback_data=f"bunlock:{chat_id}"),
                InlineKeyboardButton("⏰ Extend", callback_data=f"bextend:{chat_id}")
            ])
        else:
            buttons.append([
                InlineKeyboardButton("🔒 Lock All", callback_data=f"block:{chat_id}:all"),
                InlineKeyboardButton("🔐 Lock Text", callback_data=f"block:{chat_id}:text")
            ])
        
        buttons.append([
            InlineKeyboardButton("🔄 Refresh", callback_data=f"brefresh:{chat_id}"),
            InlineKeyboardButton("📊 Chat Info", callback_data=f"bchatinfo:{chat_id}")
        ])
        
        await message.reply_text(
            status_msg + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )
        
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


# ================= CALLBACK HANDLERS FOR BOT ADMIN LOCKS =================
@app.on_callback_query(filters.regex("^block:"))
async def bot_admin_lock_callback(client, cq):
    """Quick lock from callback"""
    if not is_bot_admin(cq.from_user.id):
        await cq.answer("❌ Bot admin only!", show_alert=True)
        return
    
    try:
        parts = cq.data.split(":")
        chat_id = int(parts[1])
        lock_type = parts[2] if len(parts) > 2 else "all"
        
        # Apply lock
        success = await apply_group_lock_by_id(client, chat_id, lock_type, lock=True)
        
        if success:
            await cq.answer(f"✅ Locked {lock_type} in chat", show_alert=True)
            
            # Update message
            await cq.message.edit_text(
                cq.message.text + f"\n\n✅ **LOCK APPLIED:** {lock_type}",
                reply_markup=cq.message.reply_markup
            )
        else:
            await cq.answer("❌ Failed to apply lock", show_alert=True)
            
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)


@app.on_callback_query(filters.regex("^bunlock:"))
async def bot_admin_unlock_callback(client, cq):
    """Quick unlock from callback"""
    if not is_bot_admin(cq.from_user.id):
        await cq.answer("❌ Bot admin only!", show_alert=True)
        return
    
    try:
        chat_id = int(cq.data.split(":")[1])
        
        # Apply unlock
        success = await apply_group_lock_by_id(client, chat_id, lock=False)
        
        if success:
            await cq.answer("✅ Chat unlocked", show_alert=True)
            
            # Update message
            await cq.message.edit_text(
                cq.message.text + "\n\n✅ **UNLOCK APPLIED**",
                reply_markup=cq.message.reply_markup
            )
        else:
            await cq.answer("❌ Failed to unlock", show_alert=True)
            
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)


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

# ================= ABUSE CACHE VIEWER =================

# ================= TEST ABUSE DETECTION =================

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


            
# ================= TAG FUNCTION, PURGE FUNCTION, ADMIN REPORT FUNCTION =========

# ================== IMPORTS ==================

TAG_LIMIT = 5          # per message
DELAY = 2              # seconds
COOLDOWN = 120         # seconds

PURGE_REPORT_DELETE_AFTER = 15  # seconds

STOP_TAG = set()

# ================== HELPERS ==================
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

async def gc_admin(client, chat_id, user_id):
    # 🔹 Bot admin always allowed
    if user_id in INITIAL_ADMINS:
        return True

    # 🔹 Check group admin / owner
    async for m in client.get_chat_members(
        chat_id,
        filter=ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER
    ):
        if m.user and m.user.id == user_id:
            return True

    return False



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
# ================== MENTION (NO VISIBLE LINK) ==================
def mention(user):
    return f"[{user.first_name}](tg://user?id={user.id})"

def premium_tag(user):
    emojis = ["🦋","🔥","✨","💖","👑","⚡"]
    return f"{emojis[user.id % len(emojis)]} {mention(user)}"

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
        "   💌 𝗔𝗧𝗧𝗘𝗡𝗧𝗜𝗢𝗡 💌\n"
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


# ================== TAG ALL ==================
@app.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message):

    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_group_admin(client, chat_id, user_id):
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
    async for m in client.get_chat_members(message.chat.id, filter=ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        text += premium_tag(m.user) + "\n"
    await message.reply(text, disable_web_page_preview=True)

# ================== STOP ==================
@app.on_message(filters.command("stop") & filters.group)
async def stop_cmd(client, message: Message):
    STOP_TAG.add(message.chat.id)
    await message.reply("🛑 **Tagging stopped**")

@app.on_callback_query(filters.regex("stop_tag"))
async def stop_cb(client, cb):
    STOP_TAG.add(cb.message.chat.id)
    await cb.message.edit(STOP_CARD)

@app.on_callback_query(filters.regex("tag_admin"))
async def tag_admin_cb(client, cb):
    text = "👑 **𝗔𝗗𝗠𝗜𝗡 𝗧𝗔𝗚** 👑\n\n"
    async for m in client.get_chat_members(cb.message.chat.id, filter=ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
        text += premium_tag(m.user) + "\n"
    await cb.message.reply(text, disable_web_page_preview=True)


@app.on_message(filters.command("purge") & filters.group)
async def purge_cmd(client, message):

    silent = "-s" in message.command

    if not await can_purge(client, message.chat.id, message.from_user.id):
        if not silent:
            await message.reply("❌ **Admin only command**")
        return

    if not message.reply_to_message:
        if not silent:
            await message.reply("⚠️ **Reply to a message to purge**")
        return

    start_id = message.reply_to_message.id
    end_id = message.id

    deleted = 0
    failed = 0

    for msg_id in range(start_id, end_id + 1):
        try:
            await client.delete_messages(message.chat.id, msg_id)
            deleted += 1
            await asyncio.sleep(0.08)
        except:
            failed += 1

    if silent:
        return

    role = await get_user_role(client, message.chat.id, message.from_user.id)

    # ❌ FAILURE / PARTIAL FAILURE
    if failed > 0:
        report = await message.reply(
            PURGE_FAIL_CARD.format(
                mention=mention(message.from_user),
                user_id=message.from_user.id,
                role=role,
                deleted=deleted,
                failed=failed,
                reason=purge_fail_reason(deleted, failed)
            ),
            disable_web_page_preview=True
        )
    else:
        # ✅ SUCCESS (already implemented)
        report = await message.reply(
            PURGE_DONE_CARD.format(
                mention=mention(message.from_user),
                user_id=message.from_user.id,
                role=role,
                count=deleted,
                chat=message.chat.title,
                time=datetime.now().strftime("%d %b %Y • %I:%M %p")
            ),
            disable_web_page_preview=True
        )

    # auto delete report
    await asyncio.sleep(PURGE_REPORT_DELETE_AFTER)
    await report.delete()

@app.on_message(filters.command("purgeall") & filters.group)
async def bulk_purge(client, message):

    silent = "-s" in message.command

    if not await can_purge(client, message.chat.id, message.from_user.id):
        if not silent:
            await message.reply("❌ **Only Group Admin or Bot Admin can use this command**")
        return

    if len(message.command) < 2:
        if not silent:
            await message.reply("⚠️ Usage: `/purgeall 50`")
        return

    try:
        limit = int(message.command[1])
        if limit <= 0:
            raise ValueError
    except:
        if not silent:
            await message.reply("❌ Invalid number")
        return

    deleted = 0
    failed = 0

    async for msg in client.get_chat_history(
        message.chat.id,
        limit=limit + 1
    ):
        try:
            await msg.delete()
            deleted += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1

    if silent:
        return

    role = await get_user_role(client, message.chat.id, message.from_user.id)

    # ❌ FAILURE / PARTIAL
    if failed > 0:
        report = await message.reply(
            PURGE_FAIL_CARD.format(
                mention=mention(message.from_user),
                user_id=message.from_user.id,
                role=role,
                deleted=deleted,
                failed=failed,
                reason=purge_fail_reason(deleted, failed)
            ),
            disable_web_page_preview=True
        )
    else:
        # ✅ SUCCESS
        report = await message.reply(
            PURGE_DONE_CARD.format(
                mention=mention(message.from_user),
                user_id=message.from_user.id,
                role=role,
                count=deleted,
                chat=message.chat.title,
                time=datetime.now().strftime("%d %b %Y • %I:%M %p")
            ),
            disable_web_page_preview=True
        )

    # 🧹 Auto-delete report
    await asyncio.sleep(PURGE_REPORT_DELETE_AFTER)
    await report.delete()

ADMIN_KEYWORDS = ["admin", "@admin", "admins", "help", "support"]

@app.on_message(filters.group & filters.text)
async def admin_call_detector(client, message):

    text = message.text.lower()

    if any(word in text for word in ADMIN_KEYWORDS):
        notify_text = await notify_admins(client, message.chat.id)

        await message.reply(
            notify_text,
            disable_web_page_preview=True
        )



# ================= ADDITIONAL HELPER FUNCTIONS =================
async def is_group_admin(client, chat_id, user_id):
    """Check if user is group admin"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

async def get_user_bio(client, user_id: int) -> str:
    """Get user's bio/description"""
    try:
        user = await client.get_users(user_id)
        if hasattr(user, 'bio') and user.bio:
            return user.bio
        return "No bio"
    except:
        return "Unknown"


# ================= ADMIN AVAILABILITY STATUS =================
@app.on_message(filters.command("status") & filters.group)
async def admin_status_command(client, message: Message):
    """Show which admins are currently active"""
    status_text = f"{beautiful_header('info')}\n\n👑 **Admin Availability**\n\n"
    
    active_admins = []
    inactive_admins = []
    
    async for member in client.get_chat_members(message.chat.id, filter=ChatMemberStatus.ADMINISTRATOR):
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and not member.user.is_bot:
            # Check if admin is online (last seen recently)
            try:
                user_status = await client.get_users(member.user.id)
                if hasattr(user_status, 'status'):
                    if user_status.status.value == "online":
                        active_admins.append(f"🟢 {member.user.first_name}")
                    elif user_status.status.value == "recently":
                        active_admins.append(f"🟡 {member.user.first_name}")
                    else:
                        inactive_admins.append(f"🔴 {member.user.first_name}")
            except:
                inactive_admins.append(f"⚪ {member.user.first_name}")
    
    if active_admins:
        status_text += "**🟢 Active Now:**\n" + "\n".join(active_admins) + "\n\n"
    
    if inactive_admins:
        status_text += "**🔴 Currently Offline:**\n" + "\n".join(inactive_admins)
    
    await message.reply_text(status_text + beautiful_footer())

# ================= TAG ALL MEMBERS =================

TAG_BATCH_SIZE = 5        # ek message me kitne mentions
TAG_COOLDOWN = 300        # 5 minutes


def check_tag_cooldown(chat_id, user_id):
    now = int(time.time())
    cur.execute(
        "SELECT last_time FROM tag_cooldown WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    row = cur.fetchone()

    if row and now - row[0] < TAG_COOLDOWN:
        return False

    cur.execute(
        "INSERT OR REPLACE INTO tag_cooldown VALUES (?, ?, ?)",
        (chat_id, user_id, now)
    )
    conn.commit()
    return True

def set_tag_cancel(chat_id, admin_id):
    cur.execute(
        "INSERT OR REPLACE INTO tag_cancel (chat_id, admin_id, cancelled) VALUES (?, ?, 1)",
        (chat_id, admin_id)
    )
    conn.commit()


def clear_tag_cancel(chat_id, admin_id):
    cur.execute(
        "DELETE FROM tag_cancel WHERE chat_id=? AND admin_id=?",
        (chat_id, admin_id)
    )
    conn.commit()


def is_tag_cancelled(chat_id, admin_id):
    cur.execute(
        "SELECT cancelled FROM tag_cancel WHERE chat_id=? AND admin_id=?",
        (chat_id, admin_id)
    )
    return cur.fetchone() is not None



async def get_user_role(client, chat_id, user_id):
    member = await client.get_chat_member(chat_id, user_id)
    if member.status == ChatMemberStatus.OWNER:
        return "👑 Owner"
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        return "🛡️ Admin"
    return "👤 Member"


async def build_tag_user_card(client, message):
    user = message.from_user
    chat = message.chat
    role = await get_user_role(client, chat.id, user.id)

    return (
        f"{beautiful_header('card')}\n\n"
        "🪪 **TAG INITIATOR INFO**\n\n"
        f"👤 **Name:** {user.mention}\n"
        f"🧾 **Username:** @{user.username or 'None'}\n"
        f"🆔 **User ID:** `{user.id}`\n"
        f"🎭 **Role:** {role}\n"
        f"🏠 **Group:** {chat.title}\n"
        f"⏰ **Time:** {datetime.now().strftime('%d %b %Y, %I:%M %p')}"
        f"{beautiful_footer()}"
    )


# ================= COMPLETE ID COMMAND =================
async def get_profile_photos_count(client, user_id: int) -> str:
    """Get count of user's profile photos"""
    try:
        photos = await client.get_profile_photos_count(user_id)
        return f"{photos} photos"
    except:
        return "Unknown"

async def get_user_status(client, user_id: int) -> str:
    """Get user's last seen status"""
    try:
        user = await client.get_users(user_id)
        
        if hasattr(user, 'status'):
            status = user.status
            if status.value == "online":
                return "🟢 Online now"
            elif status.value == "offline":
                if hasattr(user, 'last_online_date'):
                    last_online = user.last_online_date
                    time_diff = datetime.now(timezone.utc) - last_online
                    
                    if time_diff.days > 30:
                        return "⚫ Last seen a long time ago"
                    elif time_diff.days > 0:
                        return f"⚫ Last seen {time_diff.days} days ago"
                    elif time_diff.seconds > 3600:
                        hours = time_diff.seconds // 3600
                        return f"⚫ Last seen {hours} hours ago"
                    elif time_diff.seconds > 60:
                        minutes = time_diff.seconds // 60
                        return f"⚫ Last seen {minutes} minutes ago"
                    else:
                        return "⚫ Last seen just now"
            elif status.value == "recently":
                return "🟡 Recently"
            elif status.value == "within_week":
                return "🟡 Within this week"
            elif status.value == "within_month":
                return "🟡 Within this month"
            elif status.value == "long_time_ago":
                return "⚫ A long time ago"
        
        return "Unknown"
    except:
        return "Unknown"

async def get_account_age(user_id: int) -> str:
    """Calculate account age based on user ID"""
    try:
        # Telegram user IDs increase over time, we can estimate account age
        # This is approximate and for demonstration only
        
        # User IDs before 2015 were lower
        if user_id < 100000000:
            return "Very old account (before 2015)"
        elif user_id < 200000000:
            return "Old account (2015-2017)"
        elif user_id < 400000000:
            return "Medium age (2017-2019)"
        elif user_id < 600000000:
            return "Recent (2019-2021)"
        else:
            return "New account (2021+)"
    except:
        return "Unknown"

async def get_chat_member_count(client, chat_id: int) -> str:
    """Get chat member count"""
    try:
        chat = await client.get_chat(chat_id)
        if hasattr(chat, 'members_count'):
            return str(chat.members_count)
        return "Unknown"
    except:
        return "Unknown"


            

# ================= SIMPLE ID COMMAND (BACKUP) =================

async def simple_id_commands(client, message: Message):
    """Simple ID commands for quick access"""
    
    cmd = message.command[0].lower()
    
    if cmd == "myid":
        # Show only user's ID
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"👤 **YOUR INFORMATION**\n\n"
            f"🆔 **Your ID:** `{message.from_user.id}`\n"
            f"📛 **Username:** @{message.from_user.username or 'None'}\n"
            f"💬 **Chat ID:** `{message.chat.id}`\n"
            f"🏷️ **Chat:** {message.chat.title}"
            f"{beautiful_footer()}"
        )
    
    elif cmd == "chatid":
        # Show only chat ID
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"💬 **CHAT INFORMATION**\n\n"
            f"🏷️ **Chat Title:** {message.chat.title}\n"
            f"🆔 **Chat ID:** `{message.chat.id}`\n"
            f"👥 **Type:** {message.chat.type.title()}\n"
            f"👤 **Your ID:** `{message.from_user.id}`"
            f"{beautiful_footer()}"
        )

# ================= MYBOTADMIN COMMAND =================
@app.on_message(filters.command("mybotadmin") & (filters.group | filters.private))
async def mybotadmin_command(client, message: Message):
    """Check if user is bot admin"""
    
    user_id = message.from_user.id
    is_bot_admin_user = is_bot_admin(user_id)
    
    if is_bot_admin_user:
        if user_id == SUPER_ADMIN:
            status = "👑 **Super Admin**"
            description = "You have full control over the bot including adding/removing bot admins."
        else:
            status = "⚡ **Bot Admin**"
            description = "You can use bot admin commands without needing group admin permissions."
        
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"{status}\n\n"
            f"🆔 **Your ID:** `{user_id}`\n"
            f"{description}\n\n"
            f"**Commands available:** `/bhelp` for bot admin commands."
            f"{beautiful_footer()}"
        )
    else:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            f"❌ **Not a Bot Admin**\n\n"
            f"You are not in the bot admin list.\n"
            f"Only super admin can add bot admins.\n\n"
            f"**Contact super admin:** `{SUPER_ADMIN}`"
            f"{beautiful_footer()}"
        )

# ================= FLOOD/SPAM PROTECTION =================
user_message_times = {}
user_message_counts = {}

@app.on_message(filters.group & ~filters.service)
async def anti_flood_system(client, message: Message):
    """Protect against message flooding"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    current_time = datetime.now(timezone.utc)
    
    key = f"{chat_id}:{user_id}"
    
    if key not in user_message_times:
        user_message_times[key] = []
        user_message_counts[key] = 0
    
    # Add current message time
    user_message_times[key].append(current_time)
    user_message_counts[key] += 1
    
    # Keep only last 10 seconds
    user_message_times[key] = [
        t for t in user_message_times[key] 
        if (current_time - t).seconds < 10
    ]
    
    # Check flood conditions
    if len(user_message_times[key]) > 10:  # More than 10 messages in 10 seconds
        # Auto-mute for 5 minutes
        try:
            await client.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(),
                until_date=current_time + timedelta(minutes=5)
            )
            
            flood_msg = await message.reply_text(
                f"{beautiful_header('security')}\n\n"
                f"🚫 **FLOOD DETECTED**\n\n"
                f"👤 User: {message.from_user.mention}\n"
                f"⏰ Muted for: 5 minutes\n"
                f"📊 Messages: {len(user_message_times[key])} in 10 seconds\n\n"
                f"⚠️ Please don't spam the group."
                f"{beautiful_footer()}"
            )
            
            await asyncio.sleep(5)
            await flood_msg.delete()
            await message.delete()
            
        except:
            pass
        
        # Clear flood tracking
        user_message_times[key] = []
        user_message_counts[key] = 0

# ================= LINK PROTECTION =================
ALLOWED_DOMAINS = ["t.me", "telegram.me", "youtube.com", "youtu.be", "github.com", "instagram.com"]
RESTRICTED_LINKS = ["porn", "xxx", "adult", "virus", "hack", "cheat", "spam"]

@app.on_message(filters.group & ~filters.service)
async def link_protection(client, message: Message):
    """Protect against malicious links"""
    if not message.text and not message.caption:
        return
    
    text = (message.text or message.caption).lower()
    
    # Extract URLs from text
    import re
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', text)
    
    if not urls:
        return
    
    for url in urls:
        # Check for restricted links
        for restricted in RESTRICTED_LINKS:
            if restricted in url:
                # Delete message and warn user
                try:
                    await message.delete()
                    
                    warning = await message.reply_text(
                        f"{beautiful_header('security')}\n\n"
                        f"🚫 **RESTRICTED LINK DETECTED**\n\n"
                        f"👤 User: {message.from_user.mention}\n"
                        f"🔗 Link type: {restricted.upper()}\n"
                        f"⚠️ Action: Message deleted\n\n"
                        f"❌ Posting {restricted} links is not allowed."
                        f"{beautiful_footer()}"
                    )
                    
                    await asyncio.sleep(5)
                    await warning.delete()
                    
                    # Add warning to user
                    cur.execute(
                        "INSERT INTO user_warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
                        (message.chat.id, message.from_user.id, f"Posted restricted link: {restricted}")
                    )
                    conn.commit()
                    
                except:
                    pass
                return



  # ================= AUTO-DELETE SERVICE MESSAGES =================
@app.on_message(filters.service & filters.group)
async def auto_delete_service_messages(client, message: Message):
    """Auto-delete service messages after delay"""
    service_messages_to_delete = [
        "new_chat_members", "left_chat_member", 
        "new_chat_title", "new_chat_photo", "delete_chat_photo",
        "group_chat_created", "supergroup_chat_created",
        "channel_chat_created", "migrate_to_chat_id",
        "migrate_from_chat_id", "pinned_message"
    ]
    
    # Check if this is a service message type we want to auto-delete
    for attr in service_messages_to_delete:
        if getattr(message, attr, None):
            await asyncio.sleep(30)  # Wait 30 seconds
            try:
                await message.delete()
            except:
                pass
            break

# ================= REMINDER SYSTEM =================
@app.on_message(filters.command("remind") & filters.group)
async def set_reminder(client, message: Message):
    """Set a reminder"""
    if len(message.command) < 3:
        await message.reply_text(
            f"{beautiful_header('tools')}\n\n"
            f"⏰ **Usage:** `/remind [time] [message]`\n\n"
            f"**Examples:**\n"
            f"• `/remind 30m Meeting starts`\n"
            f"• `/remind 2h Call mom`\n"
            f"• `/remind 1d Pay bills`\n\n"
            f"**Time formats:** m=minutes, h=hours, d=days"
            f"{beautiful_footer()}"
        )
        return
    
    time_str = message.command[1]
    reminder_text = " ".join(message.command[2:])
    
    # Parse time
    duration = parse_duration(time_str)
    if not duration:
        await message.reply_text("Invalid time format!")
        return
    
    remind_time = datetime.now(timezone.utc) + duration
    
    # Save reminder
    cur.execute(
        """
        INSERT INTO reminders (user_id, chat_id, reminder_text, remind_time)
        VALUES (?, ?, ?, ?)
        """,
        (message.from_user.id, message.chat.id, reminder_text, remind_time.isoformat())
    )
    conn.commit()
    
    reminder_id = cur.lastrowid
    
    await message.reply_text(
        f"{beautiful_header('tools')}\n\n"
        f"✅ **REMINDER SET**\n\n"
        f"📝 **Reminder #{reminder_id}:** {reminder_text}\n"
        f"⏰ **Time:** {remind_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"👤 **For:** {message.from_user.mention}\n\n"
        f"🔔 I'll remind you at the specified time!"
        f"{beautiful_footer()}"
    )

# ================= BACKGROUND TASKS =================
async def check_reminders_task():
    """Check and send reminders"""
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            
            cur.execute(
                "SELECT id, user_id, chat_id, reminder_text FROM reminders WHERE remind_time <= ?",
                (current_time.isoformat(),)
            )
            reminders = cur.fetchall()
            
            for reminder_id, user_id, chat_id, text in reminders:
                try:
                    await app.send_message(
                        chat_id=chat_id,
                        text=f"{beautiful_header('tools')}\n\n"
                             f"🔔 **REMINDER**\n\n"
                             f"📝 {text}\n"
                             f"👤 For: <a href='tg://user?id={user_id}'>User</a>\n"
                             f"⏰ Set at: {current_time.strftime('%H:%M:%S')}"
                             f"{beautiful_footer()}",
                        parse_mode="HTML"
                    )
                    
                    # Delete sent reminder
                    cur.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
                    conn.commit()
                    
                except:
                    pass
                    
        except Exception as e:
            print(f"Error in reminder task: {e}")
        
        await asyncio.sleep(60)  # Check every minute

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

async def auto_backup_task():
    """Auto-backup database daily"""
    while True:
        try:
            # Create backup at 2 AM daily
            now = datetime.now()
            if now.hour == 2 and now.minute == 0:
                backup_file = f"backup_{now.strftime('%Y%m%d')}.db"
                shutil.copy2(DB_FILE, backup_file)
                
                # Keep only last 7 backups
                import glob
                backups = glob.glob("backup_*.db")
                backups.sort()
                
                if len(backups) > 7:
                    for old_backup in backups[:-7]:
                        os.remove(old_backup)
                
                print(f"Database backed up to {backup_file}")
                
        except Exception as e:
            print(f"Backup error: {e}")
        
        await asyncio.sleep(3600)  # Check every hour

async def cleanup_cache_task():
    """Clean old cache entries"""
    while True:
        try:
            current_time = datetime.now(timezone.utc)
            # Clean abuse cache older than 1 hour
            for key in list(user_warnings_cache.keys()):
                if not key.startswith("tagall:"):
                    # Check if entries are old
                    if len(user_warnings_cache[key]) > 0:
                        # Keep only recent entries
                        user_warnings_cache[key] = [
                            entry for entry in user_warnings_cache[key]
                            if (current_time - datetime.fromisoformat(entry.get("timestamp", "2000-01-01"))).seconds < 3600
                        ]
                        if not user_warnings_cache[key]:
                            del user_warnings_cache[key]
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        await asyncio.sleep(300)  # Every 5 minutes

# ================= HEALTH CHECK COMMAND =================
@app.on_message(filters.command("health") & filters.private)
async def health_check(client, message: Message):
    """Check bot health and statistics"""
    if not is_admin(message.from_user.id):
        return
    
    # Get database stats
    stats = {
        "Admins": cur.execute("SELECT COUNT(*) FROM admins").fetchone()[0],
        "Blocked Users": cur.execute("SELECT COUNT(*) FROM blocked_users").fetchone()[0],
        "Total Warnings": cur.execute("SELECT COUNT(*) FROM user_warnings").fetchone()[0],
        "Pending Reports": cur.execute("SELECT COUNT(*) FROM user_reports WHERE status='pending'").fetchone()[0],
        "Active Mutes": sum(len(v) for v in user_mutes.values()),
        "Cache Size": len(user_warnings_cache)
    }
    
    stats_text = "\n".join([f"• **{k}:** {v}" for k, v in stats.items()])
    
    await message.reply_text(
        f"{beautiful_header('info')}\n\n"
        f"🩺 **BOT HEALTH CHECK**\n\n"
        f"📊 **Statistics:**\n{stats_text}\n\n"
        f"🔄 **Background Tasks:** Running\n"
        f"💾 **Database:** {os.path.getsize(DB_FILE) / 1024:.1f} KB\n"
        f"⏰ **Uptime:** {get_uptime()}"
        f"{beautiful_footer()}"
    )




@app.on_message(filters.new_chat_members & filters.group)
async def welcome_handler(client, message: Message):
    for user in message.new_chat_members:

        # ================= BOT JOIN =================
        if user.is_bot:
            bot_welcome = f"""
{beautiful_header('welcome')}

🤖 **Bot Added Successfully!**

👋 Welcome {user.mention}

🔧 This bot is now part of **{message.chat.title}**

📌 **Next Steps**
• Promote the bot as admin
• Give required permissions
• Use `/help` to see commands

⚡ Make sure permissions are set correctly!
"""
            await message.reply_text(bot_welcome + beautiful_footer())
            continue

        # ================= HUMAN JOIN =================
        member_welcome = f"""
{beautiful_header('welcome')}

🌸 **Welcome to {message.chat.title}!** 🌸

👋 Hey {user.mention},
We’re happy to have you here 😊

📌 **Your Info**
• 🆔 ID: `{user.id}`
• 👤 Name: {user.first_name or 'User'}
• 🔗 Username: @{user.username if user.username else 'Not set'}

📜 **Group Rules**
• Be respectful 🤝  
• No spam or abuse 🚫  
• Follow admin instructions 👮  

💬 **Tip:**  
Say hi and enjoy chatting with everyone!

✨ Have a great time here!
"""
        await message.reply_text(member_welcome + beautiful_footer())

def abuse_warning(chat_id, user_id):
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


def contains_abuse(text: str) -> bool:
    if not text:
        return False

    text = text.lower()
    return bool(ABUSE_REGEX.search(text))
    
# ================= SUPPORT SYSTEM =================
def admin_button(uid):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Reply", callback_data=f"reply:{uid}"),
            InlineKeyboardButton("🚫 Block", callback_data=f"block:{uid}")
        ],
        [
            InlineKeyboardButton("🔓 Unblock", callback_data=f"unblock:{uid}"),
            InlineKeyboardButton("📜 History", callback_data=f"history:{uid}")
        ]
    ])


@app.on_callback_query(filters.regex("^rules$"))
async def rules_cb(client, cq):
    await cq.answer()
    await cq.message.reply_text(
        f"{beautiful_header('rules')}\n\n"
        "📜 **Support Rules**\n\n"
        "✅ Respectful language ka use karein\n"
        "❌ Abuse bilkul allowed nahi\n"
        "🚫 Repeat violation par block\n"
        "⏳ Thoda patience rakhein\n\n"
        "🙏 Dhanyavaad"
        f"{beautiful_footer()}"
    )

@app.on_callback_query(filters.regex("^contact_support$"))
async def contact_support_cb(client, cq):
    await cq.answer()
    await cq.message.reply_text(
        f"{beautiful_header('support')}\n\n"
        "📩 **Contact Support**\n\n"
        "Bas apna message likhiye ✍️\n"
        "Support team jald reply karegi 😊"
        f"{beautiful_footer()}"
    )


@app.on_callback_query(filters.regex("^reply:"))
async def cb_reply(client, cq):

    if cq.from_user.is_bot:
        return

    admin_id = cq.from_user.id

    if not is_admin(admin_id):
        await cq.answer("Not allowed", show_alert=True)
        return

    try:
        user_id = int(cq.data.split(":")[1])
    except:
        await cq.answer("Invalid target", show_alert=True)
        return

    cur.execute(
        "INSERT OR REPLACE INTO admin_reply_target (admin_id, user_id) VALUES (?, ?)",
        (admin_id, user_id)
    )
    conn.commit()

    await cq.message.reply_text(
        f"{beautiful_header('support')}\n\n"
        "✍️ **Reply Mode ON**\n\n"
        "Ab aap apna message (text / photo / video / document / voice) bhejein.\n"
        "Agla message **direct user ko** jayega ✅"
        f"{beautiful_footer()}"
    )

    await cq.answer("Reply mode enabled ✅")

@app.on_message(filters.private, group=1)
async def user_handler(client, message: Message):

    if not message.from_user or message.from_user.is_bot:
        return

    uid = message.from_user.id

    # ---------- ADMIN CHECK ----------
    if is_admin(uid):
        return

    # ---------- BLOCK CHECK ----------
    if is_blocked_user(uid):
        await message.reply_text(
            "🔴 **Access Blocked**\n"
            "Aap admin dwara block kiye gaye hain."
            + beautiful_footer()
        )
        return

    # ---------- ABUSE CHECK ----------
    abuse_text = message.text or message.caption
    if abuse_text and contains_abuse(abuse_text):

        # ✅ FIXED CALL
        count = abuse_warning(message.chat.id, uid)

        if count >= 2:
            cur.execute(
                "INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)",
                (uid,)
            )
            conn.commit()

            await message.reply_text(
                "🔴 **Blocked**\nRepeated abusive language detected."
                + beautiful_footer()
            )
            return
        else:
            await message.reply_text(
                "⚠️ **Warning**\nAbusive language detected. Please behave."
                + beautiful_footer()
            )
            return

    # ---------- AUTO REPLY ----------
    cur.execute(
        "SELECT 1 FROM auto_reply_sent WHERE user_id=?",
        (uid,)
    )
    first_time = not cur.fetchone()

    if first_time:
        await message.reply_text(
            "📨 **Message Received!**\n"
            "Thanks for contacting us ✨\n"
            "Our **Ankit Shakya** will reply shortly ⏳"
            + beautiful_footer()
        )
        cur.execute(
            "INSERT OR IGNORE INTO auto_reply_sent (user_id) VALUES (?)",
            (uid,)
        )
        conn.commit()
    else:
        await message.reply_text(
            "✅ **Message received**"
            + beautiful_footer()
        )

    # ---------- FORWARD TO ADMINS ----------
    cur.execute("SELECT admin_id FROM admins")
    admins = cur.fetchall()

    header = (
        f"{beautiful_header('support')}\n\n"
        "📩 **New User Message**\n\n"
        f"👤 Name: {message.from_user.first_name}\n"
        f"🆔 ID: `{uid}`\n"
        f"👤 Username: @{message.from_user.username or 'None'}\n\n"
    )

    for (aid,) in admins:
        try:
            if message.text:
                await client.send_message(
                    aid,
                    f"{header}💬 {message.text}",
                    reply_markup=admin_buttons(uid)
                )
            else:
                await message.copy(
                    aid,
                    caption=header,
                    reply_markup=admin_buttons(uid)
                )
        except:
            continue


            
# ================= ADMIN REPLY (TEXT + ALL MEDIA) =================

@app.on_message(filters.private, group=0)
async def admin_reply_handler(client, message: Message):

    if message.from_user.is_bot:
        return

    admin_id = message.from_user.id

    if not is_admin(admin_id):
        return

    cur.execute(
        "SELECT user_id FROM admin_reply_target WHERE admin_id=?",
        (admin_id,)
    )
    row = cur.fetchone()

    if not row:
        return

    user_id = row[0]

    # Clear reply mode first
    cur.execute(
        "DELETE FROM admin_reply_target WHERE admin_id=?",
        (admin_id,)
    )
    conn.commit()

    try:
        if message.text:
            await client.send_message(
                user_id,
                f"{beautiful_header('SUPPORT REPLY')}\n\n"
                f"💌 {message.text}\n\n"
                f"{beautiful_footer()}"
            )
            mtype, content = "text", message.text
        else:
            await message.copy(user_id)
            mtype, content = "media", "MEDIA"

        cur.execute(
            """
            INSERT INTO contact_history
            (user_id, sender, message_type, content)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, "admin", mtype, content)
        )
        conn.commit()

        await message.reply_text("✅ Reply sent to user")

    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('alert')}\n\n"
            f"❌ Failed to send reply\n`{e}`"
            f"{beautiful_footer()}"
        )


# ================= START BACKGROUND TASKS =================
# Update your start_background_tasks function
async def start_background_tasks():
    """Start all background tasks"""
    tasks = [
        check_mutes_task(),
        check_reminders_task(),
        auto_backup_task(),
        cleanup_abuse_cache_task(),  # Add this line
    ]
    
    for task in tasks:
        asyncio.create_task(task)

# ================= MAIN EXECUTION =================
if __name__ == "__main__":
    print("=" * 50)
    print(f"🤖 {BOT_BRAND}")
    print(f"✨ {BOT_TAGLINE}")
    print("=" * 50)
    print("✅ Bot starting with features:")
    print("• Support System")
    print("• Group Management")
    print("• Bot Admin System")
    print("• Group Admin System")
    print("• Admin Type Checking")
    print("• Beautiful UI")
    print("• Auto-Moderation System with abuse detection")
    print(f"• {len(ABUSE_WORDS)} abusive words/phrases in database")
    print("=" * 50)
    print(f"📋 Initialized {len(INITIAL_ADMINS)} bot admins")
    
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
          
