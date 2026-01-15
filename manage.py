import asyncio
import re
import sqlite3
import csv
import os
from datetime import datetime, timedelta, timezone
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from pyrogram.enums import ChatAction, ChatMemberStatus
from pyrogram.errors import PeerIdInvalid
from pyrogram.enums import ChatAction, ChatMemberStatus

# Add ChatPrivileges conditionally
try:
    from pyrogram.enums import ChatPrivileges
    CHAT_PRIVILEGES_AVAILABLE = True
except ImportError:
    # For older Pyrogram versions
    from pyrogram.types import ChatPrivileges
    CHAT_PRIVILEGES_AVAILABLE = True
    print("⚠️ Using ChatPrivileges from pyrogram.types (older version)")
    
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
    2345678901,  # Admin 3
    3456789012,  # Admin 4
    # Add more admin IDs here
]

# ================= BOT =================
app = Client(
    "support-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ================= DATABASE =================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

# Existing tables
cur.execute("CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS blocked_users (user_id INTEGER PRIMARY KEY)")
cur.execute("""
CREATE TABLE IF NOT EXISTS contact_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    sender TEXT,
    message_type TEXT,
    content TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
cur.execute("CREATE TABLE IF NOT EXISTS auto_reply_sent (user_id INTEGER PRIMARY KEY)")
cur.execute("CREATE TABLE IF NOT EXISTS abuse_warnings (user_id INTEGER PRIMARY KEY, count INTEGER)")
cur.execute("""
CREATE TABLE IF NOT EXISTS admin_reply_target (
    admin_id INTEGER PRIMARY KEY,
    user_id INTEGER
)
""")

# New tables for management bot
cur.execute("""
CREATE TABLE IF NOT EXISTS user_warnings (
    chat_id INTEGER,
    user_id INTEGER,
    reason TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chat_id, user_id, timestamp)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS group_rules (
    chat_id INTEGER PRIMARY KEY,
    rules TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS welcome_messages (
    chat_id INTEGER PRIMARY KEY,
    message TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS user_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    reporter_id INTEGER,
    reported_user_id INTEGER,
    reason TEXT,
    status TEXT DEFAULT 'pending',  -- pending, resolved, rejected
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
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    chat_id INTEGER,
    reminder_text TEXT,
    remind_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
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

# ================= BEAUTIFUL UI COMPONENTS =================
def beautiful_header(title: str) -> str:
    """Create beautiful header for messages"""
    headers = {
        "welcome": "╔═══════════════════╗\n        🌟 WELCOME 🌟\n╚═══════════════════╝",
        "moderation": "╔═══════════════════╗\n      🔧 MODERATION 🔧\n╚═══════════════════╝",
        "info": "╔═══════════════════╗\n       ℹ️ INFORMATION ℹ️\n╚═══════════════════╝",
        "admin": "╔═══════════════════╗\n      ⚡ ADMIN PANEL ⚡\n╚═══════════════════╝",
        "support": "╔═══════════════════╗\n     💬 SUPPORT SYSTEM 💬\n╚═══════════════════╝",
        "settings": "╔═══════════════════╗\n      ⚙️ SETTINGS ⚙️\n╚═══════════════════╝"
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
    filled = "█" * int(percentage * length / 100)
    empty = "░" * (length - len(filled))
    return f"[{filled}{empty}] {percentage}%"

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

# ================= HELPER FUNCTIONS =================
def is_admin(uid):
    """Check if user is bot admin"""
    cur.execute("SELECT 1 FROM admins WHERE admin_id=?", (uid,))
    return cur.fetchone() is not None

def is_super_admin(uid):
    """Check if user is super admin"""
    return uid == SUPER_ADMIN

def is_blocked(uid):
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

async def can_user_restrict(client, chat_id, user_id):
    """Check if user can restrict members (Pyrogram v2+ compatible)"""
    try:
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
        print(f"Restrict check error: {e}")
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

# ================= ABUSE =================
ABUSE_WORDS = [
    "fuck","shit","bitch","asshole",
    "madarchod","behenchod","chutiya",
    "gandu","bhosdike","lund","randi",
    "harami","kamina"
]

def contains_abuse(text):
    if not text:
        return False
    text = re.sub(r"[^a-zA-Z ]", "", text.lower())
    return any(w in text for w in ABUSE_WORDS)

def abuse_warning(uid):
    cur.execute("INSERT OR IGNORE INTO abuse_warnings VALUES (?,0)", (uid,))
    cur.execute("UPDATE abuse_warnings SET count=count+1 WHERE user_id=?", (uid,))
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
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user = message.from_user.first_name or "Friend"

    # Check admin status
    is_bot_admin_user = is_admin(message.from_user.id)
    
    # Beautiful loading animation
    frames = [
        "🌙 Starting Support System...",
        "🌙✨ Loading Modules...",
        "🌙✨💫 Connecting to Database...",
        "🌙✨💫🌟 Initializing Security...",
        "🌙✨💫🌟🚀 System Ready!"
    ]

    msg = await message.reply_text("🌙 Booting Support System...")
    for f in frames:
        try:
            await msg.edit_text(f)
            await asyncio.sleep(0.4)
        except:
            pass

    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    await asyncio.sleep(1)

    # Create menu based on admin status
    buttons = [
        ("📩 Contact Support", "contact_support"),
        ("🔧 Group Management", "management"),
        ("📜 Rules", "rules"),
        ("ℹ️ Bot Info", "bot_info"),
        ("⚙️ Settings", "settings_menu")
    ]
    
    if is_bot_admin_user:
        buttons.insert(3, ("👑 Admin Panel", "admin_panel"))
    
    kb = create_button_grid(buttons, columns=2)

    welcome_text = f"""
{beautiful_header("welcome")}

✨ **Hello {user}!** ❤️

🤖 **I'm {BOT_BRAND}**
A powerful multi-purpose bot with:

✅ **Support System** - 24/7 customer support
✅ **Group Management** - Full moderation tools
✅ **Admin Controls** - User management
✅ **Security** - Anti-abuse protection
✅ **Automation** - Smart responses
"""
    
    # Show admin status
    if message.from_user.id == SUPER_ADMIN:
        welcome_text += "\n👑 **Your Status:** **Super Admin** (Full access to all commands)"
    elif is_bot_admin_user:
        welcome_text += "\n⚡ **Your Status:** **Bot Admin** (Can use bot admin commands)"
    
    welcome_text += f"""
    
📚 Use /help to see all commands
💬 Or use buttons below to navigate
    """

    await msg.edit_text(welcome_text + beautiful_footer(), reply_markup=kb)

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
    is_bot_admin_user = is_admin(user_id)
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
    is_bot_admin_user = is_admin(message.from_user.id)
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
    is_bot_admin_user = is_admin(message.from_user.id)
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
    is_bot_admin_user = is_admin(message.from_user.id)
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
    is_bot_admin_user = is_admin(message.from_user.id)
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
    if not is_admin(message.from_user.id):
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
@app.on_message(filters.command("help") & filters.group)
async def help_command(client, message: Message):
    """Universal help command"""
    
    # Check user admin status
    is_bot_admin_user = is_admin(message.from_user.id)
    is_group_admin_user = await can_user_restrict(client, message.chat.id, message.from_user.id)
    
    help_text = f"""
{beautiful_header('info')}

🤖 **BOT COMMANDS GUIDE**

👤 **PUBLIC COMMANDS:**
• `/start` - Start the bot
• `/help` - Show this help
• `/rules` - Show group rules
• `/id` - Get chat/user ID
• `/info [user]` - Get user info
• `/warns [user]` - Check warnings
• `/admins` - List group admins
• `/mystatus` - Check your status

🔔 **AUTO-REPORT SYSTEM:**

• Mention `@admin` in any message
• Bot automatically forwards to all admins
• Use `/reports` to view pending reports
• Use `/resolve [id]` to mark as resolved
• Use `/reject [id]` to reject false reports

🔇 **AUTO-MODERATION:**

• Automatically detects abusive language
• Auto-mutes users based on severity
• Notifies admins about actions
• Use `/abusestats` to view statistics
• Admins can override actions via buttons

🆔 **ID & INFORMATION COMMANDS:**
• `/id` - Complete information (reply to user or mention)
• `/myid` - Show only your ID
• `/chatid` - Show chat ID
• `/fwdid` - Get ID of forwarded message sender
• `/extract` - Extract IDs from mentioned users (admin)
• `/info` - Detailed user information

📱 **Information includes:**

• User ID, Username, Name
• Premium status, Bot status
• Group role (Owner/Admin/Member)
• Warnings count, Reports count
• Join date, Last seen
• Profile photos count, Bio
• Admin permissions (if admin)
"""
    
    # Add group admin commands
    if is_group_admin_user:
        help_text += """
🔧 **GROUP ADMIN COMMANDS:**
• `/mute [user] [duration] [reason]` - Mute user
• `/unmute [user]` - Unmute user
• `/ban [user] [reason]` - Ban user
• `/unban [user]` - Unban user
• `/kick [user] [reason]` - Kick user
• `/warn [user] [reason]` - Warn user
• `/purge [amount]` - Delete messages
• `/promote [user] [title]` - Promote to admin
• `/demote [user]` - Demote admin
• `/setrules [rules]` - Set group rules
• `/setwelcome [message]` - Set welcome
"""
    
    # Add bot admin commands
    if is_bot_admin_user:
        help_text += """
⚡ **BOT ADMIN COMMANDS:**
• `/bmute [user] [duration] [reason]` - Mute (bot admin)
• `/bunmute [user]` - Unmute (bot admin)
• `/bban [user] [reason]` - Ban (bot admin)
• `/bunban [user]` - Unban (bot admin)
• `/bwarn [user] [reason]` - Warn (bot admin)
• `/bkick [user] [reason]` - Kick (bot admin)
• `/mybotadmin` - Check bot admin status
• `/checkadmin [user]` - Check admin type
"""
    
    # Add admin management for super admin
    if message.from_user.id == SUPER_ADMIN:
        help_text += """
👑 **SUPER ADMIN COMMANDS (Private):**
• `/addbotadmin [user_id]` - Add bot admin
• `/removebotadmin [user_id]` - Remove bot admin
• `/listbotadmins` - List all bot admins
"""
    
    help_text += """
⏰ **DURATION FORMAT:**
• 30m = 30 minutes
• 2h = 2 hours
• 1d = 1 day
• 1w = 1 week

📝 **NOTE:**
• Bot must be admin for moderation commands
• Use `/mystatus` to check your permissions
"""
    
    await message.reply_text(help_text + beautiful_footer())

@app.on_message(filters.command("bhelp") & filters.group)
async def bot_admin_help(client, message: Message):
    """Bot admin specific help"""
    
    if not is_admin(message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n"
            "❌ **Bot Admins Only**\n"
            "This help is only for bot admins."
            + beautiful_footer()
        )
        return
    
    help_text = f"""
{beautiful_header('admin')}

⚡ **BOT ADMIN COMMANDS GUIDE**

🔧 **MODERATION COMMANDS:**
• `/bmute [user] [duration] [reason]` - Mute user
• `/bunmute [user]` - Unmute user
• `/bban [user] [reason]` - Ban user
• `/bunban [user]` - Unban user
• `/bwarn [user] [reason]` - Warn user
• `/bkick [user] [reason]` - Kick user

📊 **INFO COMMANDS:**
• `/mybotadmin` - Check your bot admin status
• `/checkadmin [user]` - Check admin type of user
• `/mystatus` - Detailed status information
• `/bhelp` - This help menu

🎯 **KEY FEATURES:**
• Works without being group admin
• Requires bot to be admin in group
• Cannot moderate group admins
• Works across all groups where bot is admin

⏰ **DURATION FORMAT:**
• 30m = 30 minutes
• 2h = 2 hours
• 1d = 1 day
• 1w = 1 week

💡 **HOW TO USE:**
1. Bot must be admin in the group
2. You must be added as bot admin
3. Use commands with 'b' prefix (e.g., /bmute)
4. Works the same as regular commands

🚫 **LIMITATIONS:**
• Cannot mute/ban group admins
• Cannot promote/demote users
• Bot needs 'Restrict Users' permission
"""
    
    await message.reply_text(help_text + beautiful_footer())




# ================= ENHANCED ABUSE WORDS LIST =================
ABUSE_WORDS = [
    # English abuse words
    "fuck", "shit", "bitch", "asshole", "bastard", "cunt", "dick", "pussy",
    "whore", "slut", "motherfucker", "damn", "hell", "crap", "bullshit",
    
    # Hindi abuse words
    "madarchod", "behenchod", "chutiya", "gandu", "bhosdike", "lund", "randi",
    "harami", "kamina", "kutta", "kutte", "kuttiya", "lauda", "lavde", "lode",
    "chut", "gand", "bhenchod", "maderchod", "bosdike", "bosdi", "rand",
    "choot", "gaand", "bhosdi", "bhosda", "chodu", "chod", "chudai", "chud",
    
    # Romanized Hindi abuse
    "mc", "bc", "randi", "chutiye", "bkl", "bsdk", "bsdka", "lodu", "lavdu",
    
    # Evasion attempts (common misspellings)
    "fuk", "shyt", "bich", "asshle", "mdrchod", "bhenchod", "chtiya", "gndu",
    "lundh", "rndi", "hrma", "kmina", "kuttaa", "kutti", "lawda", "lawde",
    "lauda", "laude", "choot", "gaandu", "bhonsdi", "bhosdika", "choduu",
    
    # Additional abusive terms
    "nigger", "nigga", "faggot", "retard", "idiot", "moron", "stupid",
    "dog", "pig", "animal", "janwar", "bewakoof", "ullu", "gadha"
]

# ================= CLEVER WORD DETECTION FUNCTIONS =================
def contains_abuse_enhanced(text: str) -> bool:
    """Enhanced abuse detection with evasion detection"""
    if not text:
        return False
    
    # Clean the text
    text = text.lower().strip()
    
    # Remove special characters but keep spaces
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    
    # Check for exact matches
    for word in ABUSE_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            return True
    
    # Check for common evasion techniques
    evasion_patterns = [
        # Letter repetition (e.g., fuuuck, shiiit)
        r'f+u+c+k+', r's+h+i+t+', r'b+i+t+c+h+',
        # Character substitution (e.g., f*ck, sh!t, @ss)
        r'f[!@#$%^&*]ck', r'sh[!@#$%^&*]t', r'b[!@#$%^&*]tch',
        r'@ss', r'@ssh[o0]le', r'[!@#$%^&*]ss',
        # Mixed language abuse
        r'madar\s*chod', r'behen\s*chod', r'bosdi\s*ke',
        # Number substitution (e.g., f0ck, sh1t, b1tch)
        r'f[0o]ck', r'sh[1i]t', r'b[1i]tch', r'[4a]ss',
    ]
    
    for pattern in evasion_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    # Check for spaced abuse (e.g., f u c k, s h i t)
    spaced_text = text.replace(' ', '')
    for word in ABUSE_WORDS:
        if word in spaced_text and len(word) > 3:
            return True
    
    return False

def get_abuse_severity(text: str) -> int:
    """Determine severity of abuse (1-5 scale)"""
    if not contains_abuse_enhanced(text):
        return 0
    
    text = text.lower()
    severity = 0
    
    # Highly severe words
    severe_words = ["madarchod", "behenchod", "motherfucker", "nigger", "faggot", "randi"]
    for word in severe_words:
        if word in text:
            severity += 3
    
    # Medium severity words
    medium_words = ["fuck", "bitch", "asshole", "chutiya", "gandu", "bhosdike"]
    for word in medium_words:
        if word in text:
            severity += 2
    
    # Mild words
    mild_words = ["shit", "damn", "hell", "idiot", "stupid", "bewakoof"]
    for word in mild_words:
        if word in text:
            severity += 1
    
    return min(severity, 5)  # Cap at 5

# ================= AUTO MUTE ON ABUSE DETECTION =================
@app.on_message(filters.group & ~filters.service)
async def auto_mute_on_abuse(client, message: Message):
    """Automatically mute users who use abusive language"""
    
    # Skip if message is from admin or bot
    if await can_user_restrict(client, message.chat.id, message.from_user.id):
        return
    
    # Get message text
    if not message.text and not message.caption:
        return
    
    text = message.text or message.caption
    
    # Check for abuse
    if not contains_abuse_enhanced(text):
        return
    
    # Get abuse severity
    severity = get_abuse_severity(text)
    
    # Track abuse count for user in this chat
    abuse_key = f"{message.chat.id}:{message.from_user.id}"
    
    if abuse_key not in user_warnings_cache:
        user_warnings_cache[abuse_key] = []
    
    # Add this abuse incident
    user_warnings_cache[abuse_key].append({
        "text": text[:100],
        "severity": severity,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Keep only last 10 incidents
    if len(user_warnings_cache[abuse_key]) > 10:
        user_warnings_cache[abuse_key] = user_warnings_cache[abuse_key][-10:]
    
    # Calculate total abuse score (last 10 messages)
    total_severity = sum(incident["severity"] for incident in user_warnings_cache[abuse_key])
    
    # Determine mute duration based on severity and history
    mute_duration = None
    mute_reason = ""
    
    if severity >= 4 or total_severity >= 8:
        # Severe abuse or pattern of abuse
        mute_duration = timedelta(days=7)
        mute_reason = "Severe abusive language detected"
        action = "🚫 **BANNED**"
    elif severity >= 3 or total_severity >= 5:
        # Medium abuse
        mute_duration = timedelta(hours=24)
        mute_reason = "Abusive language detected (repeated offense)"
        action = "🔇 **MUTED (24h)**"
    elif severity >= 2:
        # First medium offense
        mute_duration = timedelta(hours=6)
        mute_reason = "Abusive language detected"
        action = "🔇 **MUTED (6h)**"
    else:
        # Mild offense - warning only
        mute_duration = None
        mute_reason = "Mild inappropriate language"
        action = "⚠️ **WARNING**"
    
    try:
        # Send warning to user
        warning_msg = await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"🚫 **ABUSE DETECTED**\n\n"
            f"👤 **User:** {message.from_user.mention}\n"
            f"📊 **Severity:** {severity}/5\n"
            f"📝 **Reason:** {mute_reason}\n"
            f"💬 **Message:** {text[:150]}...\n\n"
            f"❌ Abusive language is not allowed in this group.\n"
            f"⚠️ Next offense will result in longer mute/ban."
            f"{beautiful_footer()}"
        )
        
        # Delete the abusive message
        try:
            await message.delete()
        except:
            pass
        
        # Apply mute if duration specified
        if mute_duration:
            try:
                # Calculate unmute time
                unmute_time = datetime.now(timezone.utc) + mute_duration
                
                if "BANNED" in action:
                    # Permanent ban for severe abuse
                    await client.ban_chat_member(
                        chat_id=message.chat.id,
                        user_id=message.from_user.id
                    )
                    
                    ban_message = f"""
{beautiful_header('moderation')}

🚫 **USER BANNED FOR ABUSE**

👤 **User:** {message.from_user.mention}
🆔 **ID:** `{message.from_user.id}`
📊 **Severity:** {severity}/5
📝 **Reason:** {mute_reason}
🤖 **Action:** Auto-ban by bot

💬 **Abusive Message:**
{text[:200]}...

⚠️ **Note:** User has been permanently banned for severe abusive language.
                    """
                    
                    await message.chat.send_message(ban_message + beautiful_footer())
                    
                else:
                    # Apply mute
                    await client.restrict_chat_member(
                        chat_id=message.chat.id,
                        user_id=message.from_user.id,
                        permissions=ChatPermissions(),
                        until_date=unmute_time
                    )
                    
                    # Store mute info for auto-unmute
                    if message.chat.id not in user_mutes:
                        user_mutes[message.chat.id] = {}
                    
                    user_mutes[message.chat.id][message.from_user.id] = unmute_time
                    
                    mute_message = f"""
{beautiful_header('moderation')}

🔇 **USER AUTO-MUTED**

👤 **User:** {message.from_user.mention}
🆔 **ID:** `{message.from_user.id}`
⏰ **Duration:** {mute_duration}
📊 **Severity:** {severity}/5
📝 **Reason:** {mute_reason}
🤖 **Action:** Auto-mute by bot

💬 **Abusive Message:**
{text[:200]}...

⚠️ **Note:** User will be unmuted automatically after {mute_duration}.
                    """
                    
                    await message.chat.send_message(mute_message + beautiful_footer())
                
                # Add to warning database
                cur.execute(
                    "INSERT INTO user_warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
                    (message.chat.id, message.from_user.id, f"Auto-warning: {mute_reason}")
                )
                conn.commit()
                
                # Notify admins about auto-mute
                await notify_admins_about_auto_mute(client, message, severity, mute_reason, action)
                
            except Exception as e:
                print(f"Error applying auto-mute: {e}")
        
        # Delete warning message after 10 seconds
        await asyncio.sleep(10)
        await warning_msg.delete()
        
    except Exception as e:
        print(f"Error in auto-mute: {e}")

# ================= NOTIFY ADMINS ABOUT AUTO-MUTE =================
async def notify_admins_about_auto_mute(client, message, severity, reason, action):
    """Notify admins about auto-mute action"""
    
    user = message.from_user
    chat = message.chat
    text = message.text or message.caption or ""
    
    notification = f"""
{beautiful_header('moderation')}

🤖 **AUTO-MODERATION ACTION**

{action}

👤 **User:** {user.mention}
🆔 **User ID:** `{user.id}`
💬 **Chat:** {chat.title}
📊 **Severity:** {severity}/5
📝 **Reason:** {reason}

💬 **Abusive Message:**
{text[:300]}{'...' if len(text) > 300 else ''}

🕒 **Time:** {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}

✅ **Action taken automatically by bot**
    """
    
    # Send to all admins
    try:
        async for member in client.get_chat_members(chat.id, filter=ChatMemberStatus.ADMINISTRATOR):
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and not member.user.is_bot:
                try:
                    await client.send_message(
                        member.user.id,
                        notification + beautiful_footer(),
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("👤 User Info", 
                                   callback_data=f"report_user_info:{user.id}:{chat.id}"),
                                InlineKeyboardButton("📊 Warnings", 
                                   callback_data=f"report_user_warns:{user.id}:{chat.id}")
                            ],
                            [
                                InlineKeyboardButton("🔓 Unmute" if "MUTED" in action else "✅ OK", 
                                   callback_data=f"unmute_abuser:{user.id}:{chat.id}" if "MUTED" in action else "dismiss"),
                                InlineKeyboardButton("🚫 Perm Ban", 
                                   callback_data=f"perm_ban:{user.id}:{chat.id}")
                            ]
                        ])
                    )
                except:
                    continue
    except Exception as e:
        print(f"Error notifying admins about auto-mute: {e}")

# ================= ADDITIONAL CALLBACK HANDLERS =================

@app.on_callback_query(filters.regex("^unmute_abuser:"))
async def unmute_abuser_callback(client, cq):
    """Unmute user who was auto-muted for abuse"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Check if callback user is admin
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("Permission denied", show_alert=True)
            return
        
        # Unmute the user
        await client.restrict_chat_member(
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
        
        # Remove from mute cache
        if chat_id in user_mutes and user_id in user_mutes[chat_id]:
            del user_mutes[chat_id][user_id]
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n✅ **USER UNMUTED**\nBy: {cq.from_user.mention}"
        )
        
        # Notify user
        try:
            user = await client.get_users(user_id)
            await client.send_message(
                user_id,
                f"{beautiful_header('support')}\n\n"
                f"✅ **You have been unmuted**\n\n"
                f"Your mute in the group has been lifted by an admin.\n"
                f"Please follow group rules and avoid abusive language.\n\n"
                f"Thank you for understanding."
                f"{beautiful_footer()}"
            )
        except:
            pass
        
        await cq.answer("User unmuted ✅")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^perm_ban:"))
async def perm_ban_callback(client, cq):
    """Permanently ban abusive user"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Check if callback user is admin
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("Permission denied", show_alert=True)
            return
        
        # Apply permanent ban
        await client.ban_chat_member(chat_id, user_id)
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n🚫 **PERMANENTLY BANNED**\nBy: {cq.from_user.mention}"
        )
        
        await cq.answer("User permanently banned 🚫")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

# ================= ABUSE STATISTICS COMMAND =================
@app.on_message(filters.command("abusestats") & filters.group)
async def abuse_stats_command(client, message: Message):
    """Show abuse statistics for the group"""
    
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    # Get abuse warnings from database
    cur.execute(
        """
        SELECT user_id, COUNT(*) as abuse_count 
        FROM user_warnings 
        WHERE chat_id=? AND reason LIKE '%Auto-warning:%'
        GROUP BY user_id 
        ORDER BY abuse_count DESC 
        LIMIT 10
        """,
        (message.chat.id,)
    )
    top_abusers = cur.fetchall()
    
    # Get total abuse incidents
    cur.execute(
        """
        SELECT COUNT(*) 
        FROM user_warnings 
        WHERE chat_id=? AND reason LIKE '%Auto-warning:%'
        """,
        (message.chat.id,)
    )
    total_incidents = cur.fetchone()[0]
    
    stats_text = f"""
{beautiful_header('moderation')}

📊 **ABUSE STATISTICS**

📈 **Total Abuse Incidents:** {total_incidents}
👥 **Top 10 Abusers:**
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
        stats_text += "✅ No abuse incidents recorded!"
    
    stats_text += f"""
    
🔧 **Auto-Moderation Settings:**
• Abusive language detection: ✅ **ACTIVE**
• Auto-mute: ✅ **ENABLED**
• Severity-based actions: ✅ **ENABLED**
• Admin notifications: ✅ **ENABLED**

📋 **Abuse Words Detected:** {len(ABUSE_WORDS)} words/phrases
"""
    
    await message.reply_text(stats_text + beautiful_footer())

# ================= UPDATE AUTO-UNMUTE TASK =================
# Update the existing check_mutes_task function to handle abuse mutes

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



# ================= AUTO REPORT ON @admin MENTION (FINAL VERSION) =================
def contains_admin_mention(text: str) -> bool:
    """Check if text contains @admin mention (various formats)"""
    if not text:
        return False
    
    text = text.lower()
    
    # Check for various admin mention patterns
    patterns = [
        r'@admin\b',
        r'admin\s+help',
        r'help\s+admin',
        r'admins\s+please',
        r'please\s+admin',
        r'admin\s+ji',
        r'@admins\b',
        r'admin\s+sir',
        r'sir\s+admin',
        r'hey\s+admin',
        r'hello\s+admin',
        r'hi\s+admin',
        r'attention\s+admin',
        r'admin\s+attention',
        r'call\s+admin',
        r'admin\s+call',
        r'admin\s+ko\s+bulao',
        r'bulao\s+admin',
        r'admin\s+aao',
        r'aao\s+admin'
    ]
    
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    
    # Also check for simple @admin in any form
    if '@admin' in text or ' admin ' in text:
        return True
    
    return False

@app.on_message(filters.group & ~filters.service)
async def auto_report_on_admin_mention(client, message: Message):
    """Automatically report when @admin is mentioned - FINAL VERSION"""
    
    # Skip if message is from admin or bot
    if await can_user_restrict(client, message.chat.id, message.from_user.id):
        return
    
    # Get message text
    if not message.text and not message.caption:
        return
    
    text = message.text or message.caption
    
    # Check if contains admin mention
    if not contains_admin_mention(text):
        return
    
    # Check cooldown (1 auto-report per 15 minutes per user)
    current_time = datetime.now(timezone.utc)
    cur.execute(
        "SELECT last_report_time FROM report_cooldown WHERE user_id=? AND chat_id=?",
        (message.from_user.id, message.chat.id)
    )
    row = cur.fetchone()
    
    if row:
        last_report = datetime.fromisoformat(row[0])
        cooldown_remaining = (last_report + timedelta(minutes=15)) - current_time
        if cooldown_remaining.total_seconds() > 0:
            # Still in cooldown, send reminder instead
            try:
                minutes = int(cooldown_remaining.total_seconds() / 60)
                seconds = int(cooldown_remaining.total_seconds() % 60)
                
                reminder = await message.reply_text(
                    f"{beautiful_header('moderation')}\n\n"
                    "⏳ **Request Already Sent**\n\n"
                    f"You have already mentioned admins recently.\n"
                    f"Please wait **{minutes}m {seconds}s** before mentioning again.\n\n"
                    "🙏 **Patience is appreciated**"
                    f"{beautiful_footer()}"
                )
                await asyncio.sleep(8)
                await reminder.delete()
            except:
                pass
            return
    
    # Create automatic report
    reason = f"Auto-report: Mentioned admins (Message: {text[:50]}...)"
    
    # Save report to database
    cur.execute(
        """
        INSERT INTO user_reports 
        (chat_id, reporter_id, reported_user_id, reason, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (message.chat.id, client.me.id, message.from_user.id, reason, "pending")
    )
    conn.commit()
    
    # Update cooldown
    cur.execute(
        """
        INSERT OR REPLACE INTO report_cooldown 
        (user_id, chat_id, last_report_time)
        VALUES (?, ?, ?)
        """,
        (message.from_user.id, message.chat.id, current_time.isoformat())
    )
    conn.commit()
    
    report_id = cur.lastrowid
    
    # Notify admins about auto-report
    await notify_admins_about_auto_report(client, message, report_id, reason)
    
    # Send confirmation to user (temporary)
    try:
        # Different responses based on message content
        text_lower = text.lower()
        if "vc" in text_lower or "voice" in text_lower or "call" in text_lower:
            response_text = "🎤 **Voice Chat Request Received**\n✅ Admins have been notified about your VC request."
        elif "help" in text_lower or "problem" in text_lower or "issue" in text_lower:
            response_text = "🆘 **Help Request Received**\n✅ Your help request has been forwarded to admins."
        elif "urgent" in text_lower or "emergency" in text_lower:
            response_text = "🚨 **Urgent Request Received**\n✅ Your urgent message has been prioritized and sent to all admins."
        else:
            response_text = "🔔 **Admin Mention Detected**\n✅ Your message has been forwarded to all admins."
        
        # Fix the f-string formatting issue
        confirmation_text = f"""{beautiful_header('moderation')}

{response_text}

📋 **Report ID:** `{report_id}`
👮 **Admins will respond shortly.**
⏳ Please wait patiently.
{beautiful_footer()}"""
        
        confirmation = await message.reply_text(confirmation_text)
        
        # Delete confirmation after 30 seconds
        await asyncio.sleep(30)
        await confirmation.delete()
        
    except Exception as e:
        print(f"Error sending confirmation: {e}")

# ================= NOTIFY ADMINS ABOUT AUTO-REPORT =================
async def notify_admins_about_auto_report(client, message, report_id, reason):
    """Send auto-report notification to all group admins"""
    
    user = message.from_user
    chat = message.chat
    
    # Get message preview
    message_preview = message.text or message.caption or "No text content"
    if len(message_preview) > 300:
        message_preview = message_preview[:300] + "..."
    
    report_message = f"""
{beautiful_header('support')}

🔔 **ADMIN MENTION DETECTED**

📋 **Report ID:** `{report_id}`
🚨 **Type:** Auto-generated Report
💬 **Group:** {chat.title}
👤 **From:** {user.mention}
🆔 **User ID:** `{user.id}`

💬 **Message Preview:**
{message_preview}

📝 **Reason:** {reason}
🕒 **Time:** {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}

📎 **Message Link:** [Click to view]({message.link})

✅ **Suggested Actions:**
• Check if user needs help
• Respond appropriately
• Resolve the report
    """
    
    # Create buttons based on message content
    buttons = []
    text_lower = (message.text or "").lower()
    
    # Always have reply button
    buttons.append([InlineKeyboardButton("💬 Reply to User", callback_data=f"reply:{user.id}")])
    
    # Context-specific buttons
    if "vc" in text_lower or "voice" in text_lower or "call" in text_lower:
        buttons.append([
            InlineKeyboardButton("🎤 VC Request", callback_data=f"vc_request:{user.id}:{chat.id}"),
            InlineKeyboardButton("✅ Mark Resolved", callback_data=f"resolve_report:{report_id}")
        ])
    elif "urgent" in text_lower or "emergency" in text_lower:
        buttons.append([
            InlineKeyboardButton("🚨 URGENT", callback_data=f"urgent_report:{report_id}"),
            InlineKeyboardButton("✅ Responded", callback_data=f"resolve_report:{report_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("✅ Mark Resolved", callback_data=f"resolve_report:{report_id}"),
            InlineKeyboardButton("❌ Ignore", callback_data=f"reject_report:{report_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton("👤 User Info", callback_data=f"report_user_info:{user.id}:{chat.id}"),
        InlineKeyboardButton("👀 View Message", url=message.link)
    ])
    
    # Send to all admins
    admin_count = 0
    try:
        async for member in client.get_chat_members(chat.id, filter=ChatMemberStatus.ADMINISTRATOR):
            if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER] and not member.user.is_bot:
                try:
                    await client.send_message(
                        member.user.id,
                        report_message + beautiful_footer(),
                        reply_markup=InlineKeyboardMarkup(buttons)
                    )
                    admin_count += 1
                except Exception as e:
                    print(f"Error sending to admin {member.user.id}: {e}")
                    continue
    except Exception as e:
        print(f"Error getting chat members: {e}")
    
    # Log how many admins were notified
    print(f"Auto-report {report_id}: Notified {admin_count} admins about @admin mention from {user.id}")

# ================= CALLBACK HANDLERS FOR AUTO-REPORT =================
# Add these to your existing callback handlers

@app.on_callback_query(filters.regex("^vc_request:"))
async def vc_request_callback(client, cq):
    """Handle VC request callback"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Check if callback user is admin in that chat
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("Permission denied", show_alert=True)
            return
        
        # Get user info
        user = await client.get_users(user_id)
        chat = await client.get_chat(chat_id)
        
        # Update the report message
        await cq.message.edit_text(
            cq.message.text + f"\n\n✅ **VC RESPONSE SENT**\n👨‍💼 By: {cq.from_user.mention}\n🕒 {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # Notify user about VC
        try:
            await client.send_message(
                user_id,
                f"{beautiful_header('support')}\n\n"
                f"🎤 **Voice Chat Update**\n\n"
                f"✅ Your VC request in **{chat.title}** has been noted.\n"
                f"👨‍💼 Admin **{cq.from_user.first_name}** will start VC shortly.\n\n"
                f"Please stay online and wait for the VC to start."
                f"{beautiful_footer()}"
            )
        except:
            pass
        
        # Also mark report as resolved
        cur.execute(
            """
            UPDATE user_reports 
            SET status='resolved', resolved_by=?, resolved_at=?
            WHERE reported_user_id=? AND chat_id=? AND status='pending'
            ORDER BY timestamp DESC LIMIT 1
            """,
            (cq.from_user.id, datetime.now(timezone.utc).isoformat(), user_id, chat_id)
        )
        conn.commit()
        
        await cq.answer("User notified about VC ✅")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^urgent_report:"))
async def urgent_report_callback(client, cq):
    """Handle urgent report callback"""
    
    try:
        report_id = int(cq.data.split(":")[1])
        
        # Mark as urgent responded
        cur.execute(
            """
            UPDATE user_reports 
            SET status='urgent_responded', resolved_by=?, resolved_at=?
            WHERE id=?
            """,
            (cq.from_user.id, datetime.now(timezone.utc).isoformat(), report_id)
        )
        conn.commit()
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n🚨 **URGENT RESPONSE**\n👨‍💼 By: {cq.from_user.mention}\n🕒 {datetime.now().strftime('%H:%M:%S')}"
        )
        
        await cq.answer("Marked as urgent response 🚨")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^report_user_info:"))
async def report_user_info_callback(client, cq):
    """Show user info for report"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Get user info
        user = await client.get_users(user_id)
        
        # Get user warnings
        cur.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        warn_count = cur.fetchone()[0]
        
        # Get report count
        cur.execute(
            "SELECT COUNT(*) FROM user_reports WHERE reported_user_id=? AND chat_id=?",
            (user_id, chat_id)
        )
        report_count = cur.fetchone()[0]
        
        info_text = f"""
{beautiful_header('info')}

👤 **User Information for Report**

**Basic Info:**
• Name: {user.first_name or ''} {user.last_name or ''}
• ID: `{user_id}`
• Username: @{user.username if user.username else 'None'}
• Bot: {'🤖 Yes' if user.is_bot else '👤 No'}

**In This Group:**
• Warnings: {warn_count}/3
• Reports: {report_count}
• Status: {'Admin' if await is_group_admin(client, chat_id, user_id) else 'Member'}

**Actions:**
• Use buttons below for quick actions
        """
        
        buttons = [
            [
                InlineKeyboardButton("🔇 Mute", callback_data=f"mute_reported:{user_id}:{chat_id}"),
                InlineKeyboardButton("🚫 Ban", callback_data=f"ban_reported:{user_id}:{chat_id}")
            ],
            [
                InlineKeyboardButton("⚠️ Warn", callback_data=f"warn_reported:{user_id}:{chat_id}"),
                InlineKeyboardButton("💬 Message", callback_data=f"message_user:{user_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Back", callback_data="back_to_report")
            ]
        ]
        
        await cq.message.edit_text(
            info_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("User info loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^report_user_warns:"))
async def report_user_warns_callback(client, cq):
    """Show user warnings for report"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        # Get user warnings
        cur.execute(
            "SELECT reason, timestamp FROM user_warnings WHERE chat_id=? AND user_id=? ORDER BY timestamp DESC",
            (chat_id, user_id)
        )
        warnings = cur.fetchall()
        
        if warnings:
            warnings_text = "\n".join([f"• {i+1}. {warn[0]} ({warn[1][:16]})" for i, warn in enumerate(warnings)])
            warn_msg = f"""
{beautiful_header('info')}

⚠️ **WARNINGS FOR USER**

**Total Warnings:** {len(warnings)}/3
{progress_bar((len(warnings)/3)*100)}

**Warning History:**
{warnings_text}
            """
        else:
            warn_msg = f"""
{beautiful_header('info')}

✅ **No Warnings**

This user has no warnings in this group.
Good behavior record.
            """
        
        buttons = [
            [
                InlineKeyboardButton("⚠️ Add Warning", callback_data=f"add_warning:{user_id}:{chat_id}"),
                InlineKeyboardButton("⬅️ Back", callback_data="back_to_report")
            ]
        ]
        
        await cq.message.edit_text(
            warn_msg + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
        await cq.answer("Warnings loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

# ================= ADDITIONAL CALLBACK HANDLERS =================

@app.on_callback_query(filters.regex("^mute_reported:"))
async def mute_reported_callback(client, cq):
    """Mute reported user directly from callback"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("You don't have permission to mute", show_alert=True)
            return
        
        # Apply mute
        await client.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions()  # All False = fully muted
        )
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n🔇 **USER MUTED**\nBy: {cq.from_user.mention}"
        )
        
        await cq.answer("User muted successfully")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^ban_reported:"))
async def ban_reported_callback(client, cq):
    """Ban reported user directly from callback"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("You don't have permission to ban", show_alert=True)
            return
        
        # Apply ban
        await client.ban_chat_member(chat_id, user_id)
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n🚫 **USER BANNED**\nBy: {cq.from_user.mention}"
        )
        
        await cq.answer("User banned successfully")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^add_warning:"))
async def add_warning_callback(client, cq):
    """Add warning to user from callback"""
    
    try:
        parts = cq.data.split(":")
        user_id = int(parts[1])
        chat_id = int(parts[2])
        
        if not await can_user_restrict(client, chat_id, cq.from_user.id):
            await cq.answer("You don't have permission to warn", show_alert=True)
            return
        
        # Add warning
        reason = "Warning from report system"
        cur.execute(
            "INSERT INTO user_warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
            (chat_id, user_id, reason)
        )
        conn.commit()
        
        # Check for auto-ban
        cur.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        warning_count = cur.fetchone()[0]
        
        action = ""
        if warning_count >= 3:
            try:
                await client.ban_chat_member(chat_id, user_id)
                action = "\n\n🚫 **AUTO-BANNED** for reaching 3 warnings!"
                cur.execute(
                    "DELETE FROM user_warnings WHERE chat_id=? AND user_id=?",
                    (chat_id, user_id)
                )
                conn.commit()
            except:
                action = "\n\n⚠️ Ban failed (check permissions)"
        
        # Update message
        await cq.message.edit_text(
            cq.message.text + f"\n\n⚠️ **WARNING ADDED**\nTotal: {warning_count}/3{action}"
        )
        
        await cq.answer(f"Warning added ({warning_count}/3)")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

# ================= UPDATE HELP COMMAND =================
# Add this to your help_command function:
"""
🔔 **AUTO-REPORT SYSTEM:**
• Mention `@admin` in any message
• Bot automatically forwards to all admins
• Use `/reports` to view pending reports
• Use `/resolve [id]` to mark as resolved
• Use `/reject [id]` to reject false reports
"""

# ================= ADD TO EXISTING CALLBACK HANDLERS =================
# Add these new callback patterns to existing regex filters


# ================= ADMIN RESPONSE TRACKING =================
@app.on_message(filters.command("responded") & filters.group)
async def mark_as_responded(client, message: Message):
    """Mark that admin has responded to user's request"""
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        return
    
    if message.reply_to_message:
        # Find report for this message
        user_id = message.reply_to_message.from_user.id
        cur.execute(
            """
            UPDATE user_reports 
            SET status='responded', resolved_by=?, resolved_at=?
            WHERE reported_user_id=? AND chat_id=? AND status='pending'
            ORDER BY timestamp DESC LIMIT 1
            """,
            (message.from_user.id, datetime.now(timezone.utc).isoformat(), user_id, message.chat.id)
        )
        conn.commit()
        
        await message.reply_text(
            f"{beautiful_header('support')}\n\n✅ **Marked as responded**\nUser has been helped."
            f"{beautiful_footer()}"
        )

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
@app.on_message(filters.command("tagall") & filters.group)
async def tag_all_members(client, message: Message):
    """Tag all group members"""
    
    # Check permission
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    # Check cooldown (once per 5 minutes)
    tag_cooldown_key = f"tagall:{message.chat.id}"
    current_time = datetime.now(timezone.utc)
    
    if tag_cooldown_key in user_warnings_cache:
        last_tag = user_warnings_cache[tag_cooldown_key]
        if (current_time - last_tag).seconds < 300:  # 5 minutes
            remaining = 300 - (current_time - last_tag).seconds
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                f"⏳ **Please Wait**\n\n"
                f"Tagall can be used once every 5 minutes.\n"
                f"⏰ Remaining: {remaining//60}m {remaining%60}s"
                f"{beautiful_footer()}"
            )
            return
    
    user_warnings_cache[tag_cooldown_key] = current_time
    
    # Get custom message
    tag_message = " ".join(message.command[1:]) if len(message.command) > 1 else "Attention everyone!"
    
    # Inform about tag starting
    processing_msg = await message.reply_text(
        f"{beautiful_header('moderation')}\n\n"
        f"🔔 **TAGGING ALL MEMBERS**\n\n"
        f"⏳ Please wait, fetching members..."
        f"{beautiful_footer()}"
    )
    
    try:
        # Fetch all members (limited to avoid timeout)
        members_list = []
        member_count = 0
        
        async for member in client.get_chat_members(message.chat.id, limit=200):
            if not member.user.is_bot and member.user.id != client.me.id:
                members_list.append(member.user)
                member_count += 1
        
        # Create mentions
        mentions = []
        for user in members_list[:100]:  # Limit to 100 mentions per message
            if user.username:
                mentions.append(f"@{user.username}")
            else:
                mentions.append(f"[{user.first_name or 'User'}](tg://user?id={user.id})")
        
        # Split into chunks of 20 mentions each
        chunk_size = 20
        mention_chunks = [mentions[i:i + chunk_size] for i in range(0, len(mentions), chunk_size)]
        
        # Send tag messages
        for i, chunk in enumerate(mention_chunks):
            tag_text = f"""
{beautiful_header('moderation')}

🔔 **{tag_message.upper()}**

{' '.join(chunk)}

📢 **Tagged by:** {message.from_user.mention}
👥 **Page:** {i+1}/{len(mention_chunks)}
            """
            
            await message.chat.send_message(
                tag_text + beautiful_footer(),
                parse_mode="Markdown"
            )
            await asyncio.sleep(1)  # Delay between messages
        
        # Update processing message
        await processing_msg.edit_text(
            f"{beautiful_header('moderation')}\n\n"
            f"✅ **TAG COMPLETE**\n\n"
            f"📢 Message: {tag_message}\n"
            f"👥 Members tagged: {member_count}\n"
            f"📨 Messages sent: {len(mention_chunks)}\n"
            f"👨‍💼 Tagged by: {message.from_user.mention}"
            f"{beautiful_footer()}"
        )
        
    except Exception as e:
        await processing_msg.edit_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **TAG FAILED**\n\n"
            f"Error: {str(e)[:100]}"
            f"{beautiful_footer()}"
        )


# ================= COMPLETE ID COMMAND =================
@app.on_message(filters.command(["id", "info", "whois"]) & (filters.group | filters.private))
async def enhanced_id_command(client, message: Message):
    """Enhanced ID command with complete user/chat information"""
    
    try:
        # Initialize variables
        chat = message.chat
        user = message.from_user
        target_user = None
        target_chat = None
        
        # Check if we're getting info for a specific user
        if message.reply_to_message:
            # Get info from replied message
            target_user = message.reply_to_message.from_user
            if message.reply_to_message.forward_from:
                target_user = message.reply_to_message.forward_from
                is_forwarded = True
            else:
                is_forwarded = False
                
        elif len(message.command) > 1:
            # Get user from command argument
            user_arg = message.command[1]
            try:
                if user_arg.startswith("@"):
                    target_user = await client.get_users(user_arg[1:])
                else:
                    target_user = await client.get_users(int(user_arg))
            except Exception as e:
                await message.reply_text(f"❌ User not found: `{user_arg}`\nError: {str(e)[:100]}")
                return
        
        # Determine if we're in a group or private chat
        if message.chat.type == "private":
            # Private chat info
            info_text = f"""
{beautiful_header('info')}

💬 **PRIVATE CHAT INFORMATION**

👤 **YOUR INFORMATION:**
• **Name:** {user.first_name or ''} {user.last_name or ''}
• **ID:** `{user.id}`
• **Username:** @{user.username if user.username else 'None'}
• **Premium:** {'✅ Yes' if user.is_premium else '❌ No'}
• **Bot:** {'🤖 Yes' if user.is_bot else '👤 Human'}
• **DC ID:** {user.dc_id if user.dc_id else 'Unknown'}
• **Language:** {user.language_code if user.language_code else 'Unknown'}

📱 **CHAT INFORMATION:**
• **Chat ID:** `{chat.id}`
• **Chat Type:** Private
• **With:** {target_user.first_name if target_user else 'Yourself'}

📊 **ADDITIONAL INFO:**
• **Profile Photos:** {await get_profile_photos_count(client, user.id)}
• **Last Online:** {await get_user_status(client, user.id)}
• **Account Age:** {await get_account_age(user.id) if hasattr(user, 'date') else 'Unknown'}
            """
            
        else:
            # Group chat info
            chat_member = None
            user_to_display = target_user or user
            
            try:
                chat_member = await client.get_chat_member(chat.id, user_to_display.id)
            except:
                pass
            
            # Get role
            role = "👤 Member"
            role_icon = "👤"
            if chat_member:
                if chat_member.status == ChatMemberStatus.OWNER:
                    role = "👑 Owner"
                    role_icon = "👑"
                elif chat_member.status == ChatMemberStatus.ADMINISTRATOR:
                    role = "⚡ Admin"
                    role_icon = "⚡"
                elif chat_member.status == ChatMemberStatus.RESTRICTED:
                    role = "🔇 Restricted"
                    role_icon = "🔇"
                elif chat_member.status == ChatMemberStatus.BANNED:
                    role = "🚫 Banned"
                    role_icon = "🚫"
                elif chat_member.status == ChatMemberStatus.LEFT:
                    role = "🚪 Left"
                    role_icon = "🚪"
            
            # Get warnings count
            cur.execute(
                "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
                (chat.id, user_to_display.id)
            )
            warning_count = cur.fetchone()[0]
            
            # Get reports count
            cur.execute(
                "SELECT COUNT(*) FROM user_reports WHERE reported_user_id=? AND chat_id=?",
                (user_to_display.id, chat.id)
            )
            report_count = cur.fetchone()[0]
            
            # Get message count (approximate)
            cur.execute(
                "SELECT COUNT(*) FROM user_warnings WHERE user_id=? AND chat_id=?",
                (user_to_display.id, chat.id)
            )
            message_activity = cur.fetchone()[0]
            
            info_text = f"""
{beautiful_header('info')}

{role_icon} **USER INFORMATION**

👤 **BASIC INFO:**
• **Name:** {user_to_display.first_name or ''} {user_to_display.last_name or ''}
• **ID:** `{user_to_display.id}`
• **Username:** @{user_to_display.username if user_to_display.username else 'None'}
• **Premium:** {'✅ Yes' if getattr(user_to_display, 'is_premium', False) else '❌ No'}
• **Bot:** {'🤖 Yes' if user_to_display.is_bot else '👤 Human'}
• **DC ID:** {user_to_display.dc_id if user_to_display.dc_id else 'Unknown'}

👥 **GROUP STATUS:**
• **Role:** {role}
• **Joined:** {chat_member.joined_date.strftime('%Y-%m-%d %H:%M') if chat_member and hasattr(chat_member, 'joined_date') and chat_member.joined_date else 'Unknown'}
• **Until Date:** {chat_member.until_date.strftime('%Y-%m-%d %H:%M') if chat_member and hasattr(chat_member, 'until_date') and chat_member.until_date else 'Permanent'}

📊 **ACTIVITY & MODERATION:**
• **Warnings:** {warning_count}/3 {progress_bar((warning_count/3)*100, 5)}
• **Reports:** {report_count}
• **Message Activity:** {message_activity} actions
• **Bio:** {await get_user_bio(client, user_to_display.id)[:100]}

💬 **CHAT INFO:**
• **Chat:** {chat.title}
• **Chat ID:** `{chat.id}`
• **Chat Type:** {chat.type.title()}
• **Members:** {await get_chat_member_count(client, chat.id)}
            """
            
            # Add permissions if admin
            if chat_member and chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                if hasattr(chat_member, 'privileges'):
                    info_text += "\n\n🔧 **ADMIN PERMISSIONS:**\n"
                    priv = chat_member.privileges
                    info_text += f"• Change Info: {'✅' if priv.can_change_info else '❌'}\n"
                    info_text += f"• Delete Messages: {'✅' if priv.can_delete_messages else '❌'}\n"
                    info_text += f"• Restrict Members: {'✅' if priv.can_restrict_members else '❌'}\n"
                    info_text += f"• Invite Users: {'✅' if priv.can_invite_users else '❌'}\n"
                    info_text += f"• Pin Messages: {'✅' if priv.can_pin_messages else '❌'}\n"
                    info_text += f"• Promote Members: {'✅' if priv.can_promote_members else '❌'}\n"
                    info_text += f"• Manage Video Chats: {'✅' if priv.can_manage_video_chats else '❌'}\n"
                    info_text += f"• Anonymous: {'✅' if priv.is_anonymous else '❌'}\n"
            
            # Add custom title if exists
            if chat_member and hasattr(chat_member, 'custom_title') and chat_member.custom_title:
                info_text += f"\n🏷️ **Custom Title:** {chat_member.custom_title}"
        
        # Add footer with action buttons
        buttons = []
        
        if target_user and target_user.id != user.id:
            buttons.append([
                InlineKeyboardButton("👤 User Info", callback_data=f"userinfo:{target_user.id}"),
                InlineKeyboardButton("📊 Stats", callback_data=f"userstats:{target_user.id}:{chat.id}")
            ])
            buttons.append([
                InlineKeyboardButton("🔇 Mute", callback_data=f"mute:{target_user.id}:{chat.id}"),
                InlineKeyboardButton("🚫 Ban", callback_data=f"ban:{target_user.id}:{chat.id}")
            ])
            buttons.append([
                InlineKeyboardButton("⚠️ Warn", callback_data=f"warn:{target_user.id}:{chat.id}"),
                InlineKeyboardButton("💬 Message", callback_data=f"msg:{target_user.id}")
            ])
        
        buttons.append([
            InlineKeyboardButton("📋 Copy ID", callback_data=f"copyid:{target_user.id if target_user else user.id}"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_id")
        ])
        
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        
        await message.reply_text(
            info_text + beautiful_footer(),
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"❌ **Error getting information**\n\n"
            f"**Error:** `{str(e)[:200]}`\n\n"
            f"**Your Info:**\n"
            f"• User ID: `{message.from_user.id}`\n"
            f"• Chat ID: `{message.chat.id}`\n"
            f"• Chat Type: {message.chat.type}"
            f"{beautiful_footer()}"
        )

# ================= HELPER FUNCTIONS FOR ID COMMAND =================

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

async def get_user_bio(client, user_id: int) -> str:
    """Get user's bio/description"""
    try:
        user = await client.get_users(user_id)
        if hasattr(user, 'bio') and user.bio:
            return user.bio
        return "No bio"
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

# ================= CALLBACK HANDLERS FOR ID COMMAND =================

@app.on_callback_query(filters.regex("^copyid:"))
async def copy_id_callback(client, cq):
    """Copy ID to clipboard callback"""
    try:
        user_id = cq.data.split(":")[1]
        await cq.answer(f"ID copied: {user_id}\n\nYou can paste it anywhere!", show_alert=True)
        
        # Update message to show copied status
        await cq.message.edit_text(
            cq.message.text + f"\n\n✅ **ID Copied:** `{user_id}`",
            reply_markup=cq.message.reply_markup
        )
    except:
        await cq.answer("Failed to copy ID", show_alert=True)

@app.on_callback_query(filters.regex("^refresh_id$"))
async def refresh_id_callback(client, cq):
    """Refresh ID information"""
    try:
        await cq.answer("Refreshing...")
        
        # Create a fake message to reuse the ID command
        class FakeMessage:
            def __init__(self, original_msg):
                self.chat = original_msg.chat
                self.from_user = original_msg.from_user
                self.command = ["id"]
                self.reply_to_message = None
                self.text = "/id"
        
        fake_msg = FakeMessage(cq.message)
        
        # Call the ID command again
        await enhanced_id_command(client, fake_msg)
        
        # Delete old message
        await cq.message.delete()
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

@app.on_callback_query(filters.regex("^userinfo:"))
async def userinfo_callback(client, cq):
    """Show detailed user info"""
    try:
        user_id = int(cq.data.split(":")[1])
        user = await client.get_users(user_id)
        
        # Get detailed information
        info_text = f"""
{beautiful_header('info')}

👤 **DETAILED USER INFORMATION**

**Basic Information:**
• **Full Name:** {user.first_name or ''} {user.last_name or ''}
• **User ID:** `{user.id}`
• **Username:** @{user.username if user.username else 'None'}
• **Premium User:** {'✅ Yes' if getattr(user, 'is_premium', False) else '❌ No'}
• **Verified:** {'✅ Yes' if getattr(user, 'is_verified', False) else '❌ No'}
• **Bot:** {'🤖 Yes' if user.is_bot else '👤 Human'}

**Technical Information:**
• **DC ID:** {user.dc_id if user.dc_id else 'Unknown'}
• **Language:** {user.language_code if user.language_code else 'Unknown'}
• **Scam:** {'⚠️ Yes' if getattr(user, 'is_scam', False) else '✅ No'}
• **Fake:** {'⚠️ Yes' if getattr(user, 'is_fake', False) else '✅ No'}

**Status:**
{await get_user_status(client, user_id)}

**Bio:**
{await get_user_bio(client, user_id) or 'No bio available'}

**Profile Photos:** {await get_profile_photos_count(client, user_id)}
**Account Age:** {await get_account_age(user.id)}
        """
        
        await cq.message.edit_text(
            info_text + beautiful_footer(),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_id")],
                [InlineKeyboardButton("📋 Copy ID", callback_data=f"copyid:{user_id}")]
            ])
        )
        
        await cq.answer("User info loaded")
        
    except Exception as e:
        await cq.answer(f"Error: {str(e)[:50]}", show_alert=True)

# ================= SIMPLE ID COMMAND (BACKUP) =================
@app.on_message(filters.command(["myid", "chatid"]) & filters.group)
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

# ================= FORWARDED MESSAGE ID =================
@app.on_message(filters.command("fwdid") & filters.group)
async def forwarded_id_command(client, message: Message):
    """Get ID of forwarded message sender"""
    if not message.reply_to_message or not message.reply_to_message.forward_from:
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"❌ **No forwarded message**\n\n"
            f"Please reply to a **forwarded message** to get the original sender's ID."
            f"{beautiful_footer()}"
        )
        return
    
    original_sender = message.reply_to_message.forward_from
    
    await message.reply_text(
        f"{beautiful_header('info')}\n\n"
        f"📩 **FORWARDED MESSAGE INFO**\n\n"
        f"👤 **Original Sender:**\n"
        f"• Name: {original_sender.first_name or ''} {original_sender.last_name or ''}\n"
        f"• ID: `{original_sender.id}`\n"
        f"• Username: @{original_sender.username or 'None'}\n"
        f"• Bot: {'🤖 Yes' if original_sender.is_bot else '👤 Human'}\n\n"
        f"💬 **Forwarded by:** {message.reply_to_message.from_user.mention}\n"
        f"🕒 **Time:** {message.reply_to_message.date.strftime('%Y-%m-%d %H:%M:%S') if hasattr(message.reply_to_message, 'date') else 'Unknown'}"
        f"{beautiful_footer()}"
    )

# ================= BULK ID EXTRACTOR =================
@app.on_message(filters.command(["extract", "getids"]) & filters.group)
async def extract_ids_command(client, message: Message):
    """Extract IDs from multiple users mentioned"""
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text("❌ Permission denied!")
        return
    
    extracted_ids = []
    extracted_users = []
    
    # Check mentioned users
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                username = message.text[entity.offset:entity.offset + entity.length]
                try:
                    user = await client.get_users(username[1:])  # Remove @
                    extracted_ids.append(str(user.id))
                    extracted_users.append(f"@{user.username} - `{user.id}`")
                except:
                    pass
    
    # Check replied message
    if message.reply_to_message:
        extracted_ids.append(str(message.reply_to_message.from_user.id))
        extracted_users.append(f"{message.reply_to_message.from_user.first_name} - `{message.reply_to_message.from_user.id}`")
    
    # Add command sender
    extracted_ids.append(str(message.from_user.id))
    extracted_users.append(f"{message.from_user.first_name} - `{message.from_user.id}`")
    
    if extracted_users:
        ids_text = "\n".join(extracted_users)
        all_ids = ", ".join(extracted_ids)
        
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"📋 **EXTRACTED IDs**\n\n"
            f"{ids_text}\n\n"
            f"📎 **All IDs:** `{all_ids}`\n"
            f"👥 **Total:** {len(extracted_users)} users"
            f"{beautiful_footer()}"
        )
    else:
        await message.reply_text(
            f"{beautiful_header('info')}\n\n"
            f"❌ **No users found**\n\n"
            f"**Usage:**\n"
            f"1. Mention users with @username\n"
            f"2. Reply to a user's message\n"
            f"3. Use `/extract` command"
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


# ================= SUPPORT SYSTEM =================
@app.on_message(filters.private, group=1)
async def user_handler(client, message: Message):
    if message.from_user.is_bot:
        return

    uid = message.from_user.id

    # ---------- ADMIN CHECK ----------
    if is_admin(uid):
        return

    # ---------- BLOCK CHECK ----------
    if is_blocked(uid):
        await message.reply_text(
            f"{beautiful_header('support')}\n\n"
            "🔴 **Access Blocked**\n"
            "Aap admin dwara block kiye gaye hain."
            + beautiful_footer()
        )
        return

    # ---------- ABUSE CHECK ----------
    abuse_text = message.text or message.caption
    if abuse_text and contains_abuse(abuse_text):
        count = abuse_warning(uid)

        if count >= 2:
            cur.execute(
                "INSERT OR IGNORE INTO blocked_users VALUES (?)",
                (uid,)
            )
            conn.commit()

            await message.reply_text(
                f"{beautiful_header('support')}\n\n"
                "🔴 **Blocked**\n"
                "Repeated abusive language detected."
                + beautiful_footer()
            )
            return
        else:
            await message.reply_text(
                f"{beautiful_header('support')}\n\n"
                "⚠️ **Warning**\n"
                "Abusive language detected. Please behave."
                + beautiful_footer()
            )
            return

    # ---------- AUTO REPLY LOGIC ----------
    cur.execute("SELECT 1 FROM auto_reply_sent WHERE user_id=?", (uid,))
    first_time = not cur.fetchone()

    if first_time:
        await message.reply_text(
            f"{beautiful_header('support')}\n\n"
            "📨 **Message Received!**\n"
            "Thanks for contacting us ✨\n"
            "Our **Ankit Shakya** will reply shortly ⏳"
            + beautiful_footer()
        )
        cur.execute("INSERT INTO auto_reply_sent VALUES (?)", (uid,))
        conn.commit()
    else:
        await message.reply_text(
            f"{beautiful_header('support')}\n\n"
            "✅ **Message received**"
            + beautiful_footer()
        )

    # ---------- FORWARD USER MESSAGE TO ADMINS ----------
    cur.execute("SELECT admin_id FROM admins")
    admins = cur.fetchall()

    header = f"""
{beautiful_header('support')}

📩 **New User Message**

👤 **Name:** {message.from_user.first_name}
🆔 **ID:** `{uid}`
📛 **Username:** @{message.from_user.username or 'None'}
    """

    for (aid,) in admins:
        try:
            if message.text:
                await client.send_message(
                    aid,
                    f"{header}\n\n💬 **Message:** {message.text}",
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


# ================= AUTO BACKUP =================
import shutil
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

# ================= SCHEDULED MESSAGES =================
@app.on_message(filters.command("schedule") & filters.group)
async def schedule_message(client, message: Message):
    """Schedule a message"""
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        return
    
    if len(message.command) < 3:
        await message.reply_text(
            "Usage: /schedule [HH:MM] [message]\n"
            "Example: /schedule 09:00 Good morning everyone!"
        )
        return
    
    time_str = message.command[1]
    msg_text = " ".join(message.command[2:])
    
    # Validate time format
    try:
        from datetime import time as dt_time
        schedule_time = dt_time.fromisoformat(time_str)
    except:
        await message.reply_text("Invalid time format! Use HH:MM (24-hour)")
        return
    
    cur.execute(
        """
        INSERT INTO scheduled_messages (chat_id, message_text, schedule_time, repeat_daily)
        VALUES (?, ?, ?, 1)
        """,
        (message.chat.id, msg_text, time_str)
    )
    conn.commit()
    
    await message.reply_text(
        f"✅ Message scheduled!\n"
        f"⏰ Time: {time_str} daily\n"
        f"💬 Message: {msg_text[:50]}..."
    )
  
# ================= AUTO UNMUTE TASK =================
async def check_mutes_task():
    """Auto-unmute users after duration"""
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
                            
                            del user_mutes[chat_id][user_id]
                            
                        except:
                            pass
        
        except:
            pass
        
        await asyncio.sleep(60)

# ================= RUN =================
async def start_background_tasks():
    """Start all background tasks"""
    tasks = [
        check_mutes_task(),
        check_reminders_task(),
        auto_backup_task(),
        # Add other tasks here
    ]
    
    for task in tasks:
        asyncio.create_task(task)


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
    
    # Start auto-unmute task
    asyncio.get_event_loop().run_until_complete(start_background_tasks())
  
    app.run()
  
