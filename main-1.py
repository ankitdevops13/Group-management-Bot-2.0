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

# ================= CONFIG =================
API_ID = 32310443
API_HASH = "c356e2c32fca6e1ad119d5ea7134ae88"
BOT_TOKEN = "8108113571:AAHjmgKcVUUNR9kh49WEa34eGz4zRr5L9QA"

SUPER_ADMIN = 6748792256  # your Telegram ID
BOT_BRAND = "Ankit Shakya Support"
BOT_TAGLINE = "Fast • Secure • Reliable"
DB_FILE = "support.db"

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

cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (SUPER_ADMIN,))
conn.commit()

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

def beautiful_footer(text: str = "") -> str:
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

# ================= HELPER FUNCTIONS =================
def is_admin(uid):
    cur.execute("SELECT 1 FROM admins WHERE admin_id=?", (uid,))
    return cur.fetchone() is not None

def is_blocked(uid):
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

def footer(text):
    return f"""{text}

━━━━━━━━━━━━━━━━━━
🤖 {BOT_BRAND}
✨ {BOT_TAGLINE}
━━━━━━━━━━━━━━━━━━"""

async def send_with_typing(user_id, func):
    try:
        await app.send_chat_action(user_id, ChatAction.TYPING)
        await asyncio.sleep(2)
        await func()
    except:
        pass

def parse_time(t):
    if not t:
        return None

    unit = t[-1]
    num = int(t[:-1])

    if unit == "m":
        return timedelta(minutes=num)
    if unit == "h":
        return timedelta(hours=num)
    if unit == "d":
        return timedelta(days=num)

    return None

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

async def is_group_admin(client, chat_id, user_id):
    try:
        m = await client.get_chat_member(chat_id, user_id)
        return m.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except:
        return False

async def can_restrict(client, chat_id, user_id):
    """Check if user can restrict members"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER or (
            member.status == ChatMemberStatus.ADMINISTRATOR and member.privileges.can_restrict_members
        )
    except:
        return False

async def can_promote(client, chat_id, user_id):
    """Check if user can promote members"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status == ChatMemberStatus.OWNER or (
            member.status == ChatMemberStatus.ADMINISTRATOR and member.privileges.can_promote_members
        )
    except:
        return False

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


async def get_target_user(client, message):
    """Get target user from reply or command arguments"""
    
    # Method 1: Reply to message
    if message.reply_to_message:
        return message.reply_to_message.from_user
    
    # Method 2: User from command arguments
    elif len(message.command) > 1:
        user_input = message.command[1]
        
        # Remove @ if present
        if user_input.startswith("@"):
            user_input = user_input[1:]
        
        try:
            # Try as username/user_id
            return await client.get_users(user_input)
        except:
            try:
                # Try as direct ID
                return await client.get_users(int(user_input))
            except:
                return None
    
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

    # Main menu with beautiful UI
    kb = create_button_grid([
        ("📩 Contact Support", "contact_support"),
        ("🔧 Group Management", "management"),
        ("📜 Rules", "rules"),
        ("👑 Admin Panel", "admin_panel"),
        ("ℹ️ Bot Info", "bot_info"),
        ("⚙️ Settings", "settings_menu")
    ], columns=2)

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

📚 Use /help to see all commands
💬 Or use buttons below to navigate
    """

    await msg.edit_text(welcome_text + beautiful_footer(""), reply_markup=kb)

# ================= MANAGEMENT BOT COMMANDS =================
@app.on_message(filters.command("mystatus") & filters.group)
async def check_my_status(client, message: Message):
    """Check your exact status in group"""
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        status_map = {
            "owner": "👑 Owner",
            "administrator": "⚡ Admin",
            "member": "👤 Member",
            "restricted": "🔇 Restricted",
            "left": "🚪 Left",
            "kicked": "🚫 Banned"
        }
        
        your_status = status_map.get(str(member.status).lower(), str(member.status))
        
        await message.reply(
            f"**Your Status:** {your_status}\n"
            f"**User ID:** `{message.from_user.id}`\n"
            f"**Chat ID:** `{message.chat.id}`\n\n"
            f"**Note:** If you're not 'Owner' or 'Admin', you can't use mute command."
        )
    except Exception as e:
        await message.reply(f"Error: {str(e)}")


# ================= MUTE COMMAND =================
# ================= SIMPLE MUTE COMMAND (FIXED PERMISSIONS) =================
# ================= UPDATED HELPER FUNCTIONS =================
async def is_group_admin_simple(client, chat_id, user_id):
    """Simple admin check for Pyrogram v2+"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        # Pyrogram v2+ compatible check
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        print(f"Admin check error: {e}")
        return False

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

# ================= FIXED MYPERMS COMMAND =================
@app.on_message(filters.command("myperms") & filters.group)
async def check_my_permissions(client, message: Message):
    """Check your admin permissions (Fixed for Pyrogram v2+)"""
    try:
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        perms_text = f"""
{beautiful_header('info')}

👤 **Your Status:** {member.status}

**Basic Info:**
• User ID: `{message.from_user.id}`
• First Name: {message.from_user.first_name or 'N/A'}
• Username: @{message.from_user.username or 'None'}
"""
        
        # Check permissions based on Pyrogram version
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            if hasattr(member, 'privileges'):
                # Pyrogram v2+ with privileges object
                priv = member.privileges
                perms_text += "\n**Your Permissions:**\n"
                perms_text += f"• Can change info: {priv.can_change_info}\n"
                perms_text += f"• Can delete messages: {priv.can_delete_messages}\n"
                perms_text += f"• Can restrict members: {priv.can_restrict_members}\n"
                perms_text += f"• Can invite users: {priv.can_invite_users}\n"
                perms_text += f"• Can pin messages: {priv.can_pin_messages}\n"
                perms_text += f"• Can promote members: {priv.can_promote_members}\n"
                perms_text += f"• Can manage chat: {priv.can_manage_chat}\n"
            elif hasattr(member, 'can_restrict_members'):
                # Older Pyrogram version
                perms_text += "\n**Your Permissions:**\n"
                perms_text += f"• Can restrict members: {member.can_restrict_members}\n"
                perms_text += f"• Can delete messages: {member.can_delete_messages}\n"
                perms_text += f"• Can invite users: {member.can_invite_users}\n"
        
        # Check bot permissions
        try:
            bot_member = await client.get_chat_member(message.chat.id, "me")
            perms_text += f"\n🤖 **Bot Status:** {bot_member.status}"
            
            if bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                if hasattr(bot_member, 'privileges'):
                    perms_text += f"\n• Can restrict: {bot_member.privileges.can_restrict_members}"
                    perms_text += f"\n• Can delete: {bot_member.privileges.can_delete_messages}"
        except:
            perms_text += "\n🤖 **Bot Status:** Not admin"
        
        await message.reply_text(perms_text + beautiful_footer())
        
    except Exception as e:
        error_text = f"""
{beautiful_header('info')}

❌ **Error Checking Permissions**

**Error:** `{str(e)[:200]}`

**Your Chat Member Info:**
• User ID: `{message.from_user.id}`
• Chat ID: `{message.chat.id}`

**Solution:**
Make sure you're a member of this group.
"""
        await message.reply_text(error_text + beautiful_footer())

# ================= SIMPLE MUTE COMMAND (NO PERMISSION CHECKS) =================
@app.on_message(filters.command("mute") & filters.group)
async def mute_command_no_checks(client, message: Message):
    """Mute command without complex permission checks"""
    
    # VERY SIMPLE ADMIN CHECK
    try:
        # Just try to mute - if you're not admin, it will fail anyway
        pass  # Skip permission check initially
    except:
        pass
    
    # Get target user
    target_user = None
    
    # Method 1: Reply to message
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        args = message.command[1:]  # Duration/reason
    
    # Method 2: User ID/Username from command
    elif len(message.command) > 1:
        user_arg = message.command[1]
        args = message.command[2:]  # Duration/reason
        
        try:
            # Try to resolve user
            if user_arg.startswith("@"):
                target_user = await client.get_users(user_arg[1:])
            else:
                # Try as ID
                target_user = await client.get_users(int(user_arg))
        except Exception as e:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                f"❌ **User Not Found**\n"
                f"Could not find user: `{user_arg}`\n"
                f"Error: `{str(e)[:50]}`"
                f"{beautiful_footer()}"
            )
            return
    
    # If no user specified
    if not target_user:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "❌ **User Required**\n\n"
            "**Usage:**\n"
            "1. Reply to user + `/mute [duration]`\n"
            "2. `/mute @username [duration]`\n"
            "3. `/mute 1234567890 [duration]`\n\n"
            "**Example:** `/mute 8085418235 1h`"
            f"{beautiful_footer()}"
        )
        return
    
    # Prevent self-mute
    if target_user.id == message.from_user.id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "😂 **Seriously?**\n"
            "You cannot mute yourself!"
            f"{beautiful_footer()}"
        )
        return
    
    # Get duration
    duration = "Permanent"
    if args:
        duration = args[0]
    
    # Try to apply mute
    try:
        # SIMPLE MUTE - let Telegram handle permission errors
        await client.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=target_user.id,
            permissions=ChatPermissions()  # All False = fully muted
        )
        
        # Success message
        success_text = f"""
{beautiful_header('moderation')}

✅ **USER MUTED SUCCESSFULLY**

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
⏰ **Duration:** {duration}
👨‍💼 **By:** {message.from_user.mention}

🔇 User restrictions applied
        """
        
        await message.reply_text(success_text + beautiful_footer())
        
    except Exception as e:
        error_msg = str(e).lower()
        
        if "rights" in error_msg or "permission" in error_msg or "admin" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

🔒 **PERMISSION DENIED**

**Reason:** You don't have permission to mute users.

**Requirements:**
1. You must be **Group Admin**
2. You need **"Ban Users"** permission
3. Bot must be **Admin** with same permissions

**Your Status:** Regular member (not admin)
**Bot Status:** {'Admin ✅' if await is_group_admin_simple(client, message.chat.id, "me") else 'Not admin ❌'}

**Solution:** Ask group owner to make you admin.
            """
        elif "user_admin_invalid" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

👑 **CANNOT MUTE ADMIN**

User {target_user.mention} is an **admin** or **owner**.

Only group creator can restrict admins.
            """
        elif "not found" in error_msg or "invalid" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

❌ **USER NOT IN GROUP**

User {target_user.mention} is not a member of this group.

You can only mute users who are in this group.
            """
        else:
            error_text = f"""
{beautiful_header('moderation')}

❌ **MUTE FAILED**

**Error:** `{str(e)[:150]}`

**Quick Fix:**
1. Make sure you're admin
2. Make sure bot is admin
3. Try again
            """
        
        await message.reply_text(error_text + beautiful_footer())


# ================= UNMUTE COMMAND =================
@app.on_message(filters.command("unmute") & filters.group)
async def unmute_command(client, message: Message):
    """Unmute command - FIXED footer call"""
    
    # Check if user is admin (simple check)
    try:
        user_member = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        # CORRECT WAY to check status
        if user_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                "❌ **Permission Denied**\n"
                "You need to be an admin to unmute users."
                f"{beautiful_footer()}"  # ✅ NO PARAMETER
            )
            return
    except:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **Error checking permissions**"
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
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
        except:
            await message.reply_text(
                f"{beautiful_header('moderation')}\n\n"
                f"❌ **User Not Found**\n`{user_arg}`"
                f"{beautiful_footer()}"  # ✅ NO PARAMETER
            )
            return
    
    # If no user specified
    if not target_user:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            "❌ **User Required**\n\n"
            "**Usage:**\n"
            "• `/unmute @username`\n"
            "• `/unmute user_id`\n"
            "• `/unmute` (reply to user)"
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Try to unmute
    try:
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
        
        # Remove from cache
        if message.chat.id in user_mutes and target_user.id in user_mutes[message.chat.id]:
            del user_mutes[message.chat.id][target_user.id]
        
        success_msg = f"""
{beautiful_header('moderation')}

✅ **USER UNMUTED SUCCESSFULLY**

👤 **User:** {target_user.mention}
🆔 **ID:** `{target_user.id}`
👨‍💼 **By:** {message.from_user.mention}

🔊 User can now send messages again
        """
        
        await message.reply_text(success_msg + beautiful_footer())  # ✅ NO PARAMETER
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n"
            f"❌ **Failed to Unmute**\n`{str(e)[:100]}`"
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )


# ================= BAN COMMAND =================

# ================= UNBAN COMMAND =================
from pyrogram.enums import ChatMemberStatus

# ================= UPDATED HELPER FUNCTIONS =================
async def user_admin_simple(client, chat_id, user_id):
    """Simple admin check using string comparison"""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        status_str = str(member.status).lower()
        return "administrator" in status_str or "owner" in status_str
    except:
        return False

async def user_restrict_simple(client, chat_id, user_id):
    """Check if user can restrict members (simple version)"""
    try:
        # First check if user is admin
        if not await user_admin_simple(client, chat_id, user_id):
            return False
        
        # If user is owner, they can always restrict
        member = await client.get_chat_member(chat_id, user_id)
        status_str = str(member.status).lower()
        if "owner" in status_str:
            return True
        
        # For admins, check if they have restrict permission
        if hasattr(member, 'privileges') and member.privileges:
            return getattr(member.privileges, 'can_restrict_members', False)
        elif hasattr(member, 'can_restrict_members'):
            return member.can_restrict_members
        
        return True  # Default to True for admins
        
    except:
        return False

# ================= FIXED BAN COMMAND =================
@app.on_message(filters.command("ban") & filters.group)
async def ban_command_fixed(client, message: Message):
    """Fixed ban command with proper permission checks"""
    
    # Check if user can restrict (FIXED)
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Extract target user
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Invalid User**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Prevent self-ban
    if user_id == message.from_user.id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Self Action**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Prevent banning admins
    if await user_admin_simple(client, message.chat.id, user_id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Admin Protection**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Parse reason
    reason = "No reason provided"
    args = message.command[1:] if not message.reply_to_message else message.command
    if len(args) >= (2 if not message.reply_to_message else 1):
        reason_index = 2 if not message.reply_to_message else 1
        if len(args) > reason_index:
            reason = " ".join(args[reason_index:])
    
    try:
        # Apply ban
        await client.ban_chat_member(message.chat.id, user_id)
        
        ban_msg = f"""
{beautiful_header('moderation')}

🚫 **USER BANNED SUCCESSFULLY**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`
📝 **Reason:** {reason}
👨‍💼 **By:** {message.from_user.mention}

⛔ User removed from group
        """
        
        await message.reply_text(ban_msg + beautiful_footer())  # ✅ NO PARAMETER
        
    except Exception as e:
        error_msg = str(e).lower()
        
        if "chat_admin_required" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

❌ **BOT NEEDS ADMIN**

I need admin permissions with:
• **Ban Users** permission
• **Delete Messages** permission

Please promote me as admin.
"""
        elif "user_admin_invalid" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

❌ **CANNOT BAN ADMIN**

User {user_obj.mention} is an admin.

Only group creator can ban admins.
"""
        else:
            error_text = f"""
{beautiful_header('moderation')}

❌ **BAN FAILED**

Error: `{str(e)[:100]}`
"""
        
        await message.reply_text(error_text + beautiful_footer())  # ✅ NO PARAMETER

# ================= FIXED UNBAN COMMAND =================
@app.on_message(filters.command("unban") & filters.group)
async def unban_command_fixed(client, message: Message):
    """Fixed unban command with proper permission checks"""
    
    # Check if user can restrict (FIXED)
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    # Extract target user
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Invalid User**" 
            f"{beautiful_footer()}"  # ✅ NO PARAMETER
        )
        return
    
    try:
        # Apply unban
        await client.unban_chat_member(message.chat.id, user_id)
        
        unban_msg = f"""
{beautiful_header('moderation')}

✅ **USER UNBANNED SUCCESSFULLY**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`
👨‍💼 **By:** {message.from_user.mention}

🔓 User can now join the group again
        """
        
        await message.reply_text(unban_msg + beautiful_footer())  # ✅ NO PARAMETER
        
    except Exception as e:
        error_msg = str(e).lower()
        
        if "chat_admin_required" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

❌ **BOT NEEDS ADMIN**

I need admin permissions to unban users.

Please make me an admin with "Ban Users" permission.
"""
        elif "user_not_participant" in error_msg:
            error_text = f"""
{beautiful_header('moderation')}

ℹ️ **USER NOT BANNED**

User {user_obj.mention} is not currently banned.

No action needed.
"""
        else:
            error_text = f"""
{beautiful_header('moderation')}

❌ **UNBAN FAILED**

Error: `{str(e)[:100]}`
"""
        
        await message.reply_text(error_text + beautiful_footer())  # ✅ NO PARAMETER



# ================= KICK COMMAND =================
@app.on_message(filters.command("kick") & filters.group)
async def kick_command(client, message: Message):
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Invalid User**" + beautiful_footer()
        )
        return
    
    if user_id == message.from_user.id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Self Action**" + beautiful_footer()
        )
        return
    
    if await is_group_admin(client, message.chat.id, user_id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Admin Protection**" + beautiful_footer()
        )
        return
    
    reason = "No reason provided"
    args = message.command[1:] if not message.reply_to_message else message.command
    if len(args) >= (2 if not message.reply_to_message else 1):
        reason_index = 2 if not message.reply_to_message else 1
        if len(args) > reason_index:
            reason = " ".join(args[reason_index:])
    
    try:
        await client.ban_chat_member(message.chat.id, user_id)
        await asyncio.sleep(1)
        await client.unban_chat_member(message.chat.id, user_id)
        
        kick_msg = f"""
{beautiful_header('moderation')}

👢 **USER KICKED SUCCESSFULLY**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`
📝 **Reason:** {reason}
👨‍💼 **By:** {message.from_user.mention}

🚶 User removed from group
        """
        
        await message.reply_text(kick_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Failed to Kick**\n`{str(e)}`" + beautiful_footer()
        )

# ================= WARN SYSTEM =================
@app.on_message(filters.command("warn") & filters.group)
async def warn_command(client, message: Message):
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
        
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Invalid User**" + beautiful_footer()
        )
        return
    
    if user_id == message.from_user.id:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Self Action**" + beautiful_footer()
        )
        return
    
    if await is_group_admin(client, message.chat.id, user_id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Admin Protection**" + beautiful_footer()
        )
        return
    
    reason = "No reason provided"
    args = message.command[1:] if not message.reply_to_message else message.command
    if len(args) >= (2 if not message.reply_to_message else 1):
        reason_index = 2 if not message.reply_to_message else 1
        if len(args) > reason_index:
            reason = " ".join(args[reason_index:])
    
    # Save warning to database
    cur.execute(
        "INSERT INTO user_warnings (chat_id, user_id, reason) VALUES (?, ?, ?)",
        (message.chat.id, user_id, reason)
    )
    conn.commit()
    
    # Get warning count
    cur.execute(
        "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
        (message.chat.id, user_id)
    )
    warning_count = cur.fetchone()[0]
    
    # Check for auto-ban
    action = None
    if warning_count >= 3:
        try:
            await client.ban_chat_member(message.chat.id, user_id)
            action = "banned"
            # Clear warnings
            cur.execute(
                "DELETE FROM user_warnings WHERE chat_id=? AND user_id=?",
                (message.chat.id, user_id)
            )
            conn.commit()
        except:
            action = "ban failed"
    
    warn_msg = f"""
{beautiful_header('moderation')}

⚠️ **WARNING #{warning_count} ISSUED**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`
📝 **Reason:** {reason}
📊 **Total Warnings:** {warning_count}/3
👨‍💼 **By:** {message.from_user.mention}
    """
    
    if action == "banned":
        warn_msg += "\n\n🚫 **AUTO-BANNED** for reaching 3 warnings!"
    
    warning_msg = await message.reply_text(warn_msg + beautiful_footer())
    
    if action == "banned":
        await warning_msg.edit_text(
            warn_msg + "\n\n🚫 **AUTO-BANNED** for reaching 3 warnings!" + beautiful_footer()
        )

@app.on_message(filters.command("warns") & filters.group)
async def warns_command(client, message: Message):
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        user_id = message.from_user.id
        user_obj = message.from_user
    
    cur.execute(
        "SELECT reason, timestamp FROM user_warnings WHERE chat_id=? AND user_id=? ORDER BY timestamp DESC",
        (message.chat.id, user_id)
    )
    warnings = cur.fetchall()
    
    if warnings:
        warnings_text = "\n".join([f"• {i+1}. {warn[0]} ({warn[1][:16]})" for i, warn in enumerate(warnings)])
        
        warns_msg = f"""
{beautiful_header('info')}

⚠️ **WARNINGS FOR {user_obj.mention}**

📊 **Total:** {len(warnings)}/3
{progress_bar((len(warnings)/3)*100)}

📜 **Warnings:**
{warnings_text}
        """
        
        await message.reply_text(warns_msg + beautiful_footer())
    else:
        await message.reply_text(
            f"{beautiful_header('info')}\n\n✅ **No Warnings**\n{user_obj.mention} has no warnings." + beautiful_footer()
        )


# ================= PROMOTE COMMAND =================
@app.on_message(filters.command("promote") & filters.group)
async def promote_command(client, message: Message):
    try:
        promoter = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        if promoter.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Permission Denied**" + beautiful_footer()
            )
            return
        
        if promoter.status == ChatMemberStatus.ADMINISTRATOR and not promoter.privileges.can_promote_members:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **No Promote Rights**" + beautiful_footer()
            )
            return
        
        user_id, user_obj = await extract_user(client, message)
        if not user_id or not user_obj:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Invalid User**" + beautiful_footer()
            )
            return
        
        if user_id == message.from_user.id:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Self Action**" + beautiful_footer()
            )
            return
        
        target_member = await client.get_chat_member(message.chat.id, user_id)
        if target_member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\nℹ️ **Already Admin**" + beautiful_footer()
            )
            return
        
        title = "Admin"
        args = message.command[1:] if not message.reply_to_message else message.command
        
        if len(args) >= (3 if not message.reply_to_message else 2):
            title_index = 3 if not message.reply_to_message else 2
            if len(args) > title_index:
                title = " ".join(args[title_index:title_index+1])
                if len(title) > 16:
                    title = title[:16]
        
        if promoter.status == ChatMemberStatus.OWNER:
            # Creator can give all permissions
            privileges = ChatPrivileges(
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_restrict_members=True,
                can_promote_members=True,
                can_change_info=True,
                can_post_messages=True,
                can_edit_messages=True,
                can_invite_users=True,
                can_pin_messages=True,
                is_anonymous=False
            )
        else:
            # Regular admin cannot give promote rights
            privileges = ChatPrivileges(
                can_manage_chat=promoter.privileges.can_manage_chat,
                can_delete_messages=promoter.privileges.can_delete_messages,
                can_manage_video_chats=promoter.privileges.can_manage_video_chats,
                can_restrict_members=promoter.privileges.can_restrict_members,
                can_promote_members=False,
                can_change_info=promoter.privileges.can_change_info,
                can_post_messages=promoter.privileges.can_post_messages,
                can_edit_messages=promoter.privileges.can_edit_messages,
                can_invite_users=promoter.privileges.can_invite_users,
                can_pin_messages=promoter.privileges.can_pin_messages,
                is_anonymous=False
            )
        
        await client.promote_chat_member(
            chat_id=message.chat.id,
            user_id=user_id,
            privileges=privileges
        )
        
        # Set custom title
        try:
            await client.set_administrator_title(message.chat.id, user_id, title)
        except:
            pass
        
        success_msg = f"""
{beautiful_header('admin')}

⚡ **USER PROMOTED TO ADMIN**

👤 **User:** {user_obj.mention}
🏷️ **Title:** {title}
👑 **Promoted by:** {message.from_user.mention}

✅ **Permissions Granted:**
{'• All permissions including promote rights' if promoter.status == ChatMemberStatus.OWNER else '• Limited admin rights (no promote rights)'}
        """
        
        await message.reply_text(success_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n❌ **Failed to Promote**\n`{str(e)}`" + beautiful_footer()
      )


# ================= DEMOTE COMMAND =================
@app.on_message(filters.command("demote") & filters.group)
async def demote_command(client, message: Message):
    try:
        demoter = await client.get_chat_member(message.chat.id, message.from_user.id)
        
        if demoter.status not in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Permission Denied**" + beautiful_footer()
            )
            return
        
        if demoter.status == ChatMemberStatus.ADMINISTRATOR and not demoter.privileges.can_promote_members:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **No Demote Rights**" + beautiful_footer()
            )
            return
        
        user_id, user_obj = await extract_user(client, message)
        if not user_id or not user_obj:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Invalid User**" + beautiful_footer()
            )
            return
        
        if user_id == message.from_user.id:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Self Action**" + beautiful_footer()
            )
            return
        
        target_member = await client.get_chat_member(message.chat.id, user_id)
        
        if target_member.status == ChatMemberStatus.OWNER:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Cannot Demote Owner**" + beautiful_footer()
            )
            return
        
        if target_member.status != ChatMemberStatus.ADMINISTRATOR:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\nℹ️ **Not an Admin**" + beautiful_footer()
            )
            return
        
        if demoter.status == ChatMemberStatus.ADMINISTRATOR and target_member.status == ChatMemberStatus.ADMINISTRATOR:
            await message.reply_text(
                f"{beautiful_header('admin')}\n\n❌ **Only Owner Can Demote Admins**" + beautiful_footer()
            )
            return
        
        # Demote to member (remove all privileges)
        await client.promote_chat_member(
            chat_id=message.chat.id,
            user_id=user_id,
            privileges=ChatPrivileges()
        )
        
        demote_msg = f"""
{beautiful_header('admin')}

📉 **ADMIN DEMOTED TO MEMBER**

👤 **User:** {user_obj.mention}
🆔 **ID:** `{user_id}`
👑 **Demoted by:** {message.from_user.mention}

✅ All admin permissions removed
        """
        
        await message.reply_text(demote_msg + beautiful_footer())
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n❌ **Failed to Demote**\n`{str(e)}`" + beautiful_footer()
        )

# ================= INFO COMMAND =================
@app.on_message(filters.command("info") & filters.group)
async def info_command(client, message: Message):
    user_id, user_obj = await extract_user(client, message)
    if not user_id or not user_obj:
        user_id = message.from_user.id
        user_obj = message.from_user
    
    try:
        member = await client.get_chat_member(message.chat.id, user_id)
        status = member.status
        
        if status == ChatMemberStatus.OWNER:
            role = "👑 Owner"
            role_icon = "👑"
        elif status == ChatMemberStatus.ADMINISTRATOR:
            role = "⚡ Admin"
            role_icon = "⚡"
        else:
            role = "👤 Member"
            role_icon = "👤"
        
        info_text = f"""
{beautiful_header('info')}

{role_icon} **USER INFORMATION**

👤 **Name:** {user_obj.first_name or ''} {user_obj.last_name or ''}
🆔 **ID:** `{user_id}`
📛 **Username:** @{user_obj.username if user_obj.username else 'None'}
👥 **Role:** {role}
🏢 **DC:** {user_obj.dc_id if user_obj.dc_id else 'Unknown'}
🤖 **Type:** {'🤖 Bot' if user_obj.is_bot else '👤 User'}

📊 **In this group:**
• Joined: {member.joined_date.strftime('%Y-%m-%d %H:%M') if hasattr(member, 'joined_date') and member.joined_date else 'Unknown'}
• Status: {status}
        """
        
        if hasattr(member, 'until_date') and member.until_date:
            until_date = datetime.fromtimestamp(member.until_date, timezone.utc)
            remaining = until_date - datetime.now(timezone.utc)
            if remaining.total_seconds() > 0:
                info_text += f"\n⏰ **Restricted until:** {until_date.strftime('%Y-%m-%d %H:%M UTC')}"
        
        # Get warnings
        cur.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE chat_id=? AND user_id=?",
            (message.chat.id, user_id)
        )
        warn_count = cur.fetchone()[0]
        info_text += f"\n⚠️ **Warnings:** {warn_count}/3"
        
        await message.reply_text(info_text + beautiful_footer(""))
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('info')}\n\n❌ **Failed to Get Info**\n`{str(e)}`" + beautiful_footer("")
          )


# ================= ID COMMAND =================
@app.on_message(filters.command("id") & filters.group)
async def id_command(client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    reply_text = f"""
{beautiful_header('info')}

📱 **ID INFORMATION**

💬 **Chat ID:** `{chat_id}`
📛 **Chat Title:** {message.chat.title}
👤 **Your ID:** `{user_id}`
👤 **Your Name:** {message.from_user.first_name or ''}
    """
    
    if message.reply_to_message:
        replied_user = message.reply_to_message.from_user
        reply_text += f"\n\n👥 **Replied User:**"
        reply_text += f"\n• Name: {replied_user.first_name or ''}"
        reply_text += f"\n• ID: `{replied_user.id}`"
        if replied_user.username:
            reply_text += f"\n• Username: @{replied_user.username}"
    
    await message.reply_text(reply_text + beautiful_footer())

# ================= ADMINS COMMAND =================
@app.on_message(filters.command("admins") & filters.group)
async def admins_command(client, message: Message):
    try:
        admins_text = f"""
{beautiful_header('admin')}

👑 **GROUP ADMINISTRATORS**

"""
        admin_count = 0
        owner_count = 0
        
        async for member in client.get_chat_members(message.chat.id, filter=ChatMemberStatus.ADMINISTRATOR):
            if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]:
                role = "👑 Owner" if member.status == ChatMemberStatus.OWNER else "⚡ Admin"
                user = member.user
                name = user.first_name or ""
                if user.last_name:
                    name += f" {user.last_name}"
                
                if member.status == ChatMemberStatus.OWNER:
                    owner_count += 1
                    admins_text += f"• {role}: {name}"
                else:
                    admin_count += 1
                    admins_text += f"• {role}: {name}"
                    
                    # Show promote rights
                    if member.privileges and member.privileges.can_promote_members:
                        admins_text += " 🔑"
                
                if user.username:
                    admins_text += f" (@{user.username})"
                
                if hasattr(member, 'custom_title') and member.custom_title:
                    admins_text += f" - [{member.custom_title}]"
                
                admins_text += f"\n"
        
        admins_text += f"\n📊 **Total:** {owner_count + admin_count} ({owner_count} owner, {admin_count} admins)"
        admins_text += f"\n🔑 = Has promotion rights"
        
        await message.reply_text(admins_text + beautiful_footer())
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('admin')}\n\n❌ **Failed to Get Admins**\n`{str(e)}`" + beautiful_footer()
      )


# ================= PURGE COMMAND =================
@app.on_message(filters.command("purge") & filters.group)
async def purge_command(client, message: Message):
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    if not message.reply_to_message:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Reply Required**" + beautiful_footer()
        )
        return
    
    try:
        count = 100  # Default
        if len(message.command) > 1:
            try:
                count = int(message.command[1])
                if count < 1 or count > 100:
                    count = 100
            except:
                count = 100
        
        # Delete command message
        await message.delete()
        
        # Delete messages
        deleted = 0
        message_ids = []
        
        async for msg in client.get_chat_history(
            chat_id=message.chat.id,
            limit=count,
            offset_id=message.reply_to_message.id
        ):
            message_ids.append(msg.id)
            deleted += 1
            if deleted >= count:
                break
        
        # Delete in batches
        for i in range(0, len(message_ids), 100):
            await client.delete_messages(message.chat.id, message_ids[i:i+100])
            await asyncio.sleep(0.5)
        
        # Send confirmation
        purge_msg = await message.reply(
            f"{beautiful_header('moderation')}\n\n✅ **Purged {deleted} messages**" + beautiful_footer()
        )
        await asyncio.sleep(5)
        await purge_msg.delete()
        
    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('moderation')}\n\n❌ **Failed to Purge**\n`{str(e)}`" + beautiful_footer()
        )


# ================= SET RULES COMMAND =================
@app.on_message(filters.command("setrules") & filters.group)
async def setrules_command(client, message: Message):
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    if len(message.command) < 2:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n❌ **Usage:** `/setrules [rules text]`" + beautiful_footer()
        )
        return
    
    rules_text = " ".join(message.command[1:])
    
    # Save to database
    cur.execute(
        "INSERT OR REPLACE INTO group_rules (chat_id, rules) VALUES (?, ?)",
        (message.chat.id, rules_text)
    )
    conn.commit()
    
    await message.reply_text(
        f"{beautiful_header('settings')}\n\n✅ **Group rules have been set!**" + beautiful_footer()
    )

# ================= RULES COMMAND =================
@app.on_message(filters.command("rules") & filters.group)
async def rules_command(client, message: Message):
    cur.execute("SELECT rules FROM group_rules WHERE chat_id=?", (message.chat.id,))
    row = cur.fetchone()
    
    if row:
        rules = row[0]
        rules_msg = f"""
{beautiful_header('settings')}

📜 **GROUP RULES**

{rules}
        """
        await message.reply_text(rules_msg + beautiful_footer())
    else:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\nℹ️ **No rules set for this group**\n\nUse `/setrules [rules]` to set group rules." + beautiful_footer()
        )

# ================= SET WELCOME COMMAND =================
@app.on_message(filters.command("setwelcome") & filters.group)
async def setwelcome_command(client, message: Message):
    if not await can_user_restrict(client, message.chat.id, message.from_user.id):
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n❌ **Permission Denied**" + beautiful_footer()
        )
        return
    
    if len(message.command) < 2:
        await message.reply_text(
            f"{beautiful_header('settings')}\n\n❌ **Usage:** `/setwelcome [message]`" + beautiful_footer()
        )
        return
    
    welcome_text = " ".join(message.command[1:])
    
    # Save to database
    cur.execute(
        "INSERT OR REPLACE INTO welcome_messages (chat_id, message) VALUES (?, ?)",
        (message.chat.id, welcome_text)
    )
    conn.commit()
    
    await message.reply_text(
        f"{beautiful_header('settings')}\n\n✅ **Welcome message has been set!**" + beautiful_footer()
    )



# ================= WELCOME NEW MEMBERS =================
@app.on_message(filters.new_chat_members & filters.group)
async def welcome_new_member(client, message: Message):
    for user in message.new_chat_members:
        if user.is_bot and user.id == client.me.id:
            # Bot added to group
            welcome_msg = f"""
{beautiful_header('welcome')}

🤖 **Thanks for adding me!**

I'm **{BOT_BRAND}** - a powerful group management bot.

🔧 **Features:**
• Full moderation tools
• Support system
• User management
• Security protection

⚡ **Setup:**
1. Promote me as admin
2. Give me all permissions
3. Use `/help` for commands

💬 Enjoy managing your group!
            """
            await message.reply_text(welcome_msg + beautiful_footer(""))
        elif not user.is_bot:
            # Human user joined
            cur.execute("SELECT message FROM welcome_messages WHERE chat_id=?", (message.chat.id,))
            row = cur.fetchone()
            
            if row:
                welcome_text = row[0]
                welcome_text = welcome_text.replace("{name}", user.first_name or "User")
                welcome_text = welcome_text.replace("{username}", f"@{user.username}" if user.username else "No username")
                welcome_text = welcome_text.replace("{mention}", user.mention)
                welcome_text = welcome_text.replace("{id}", str(user.id))
                welcome_text = welcome_text.replace("{title}", message.chat.title)
                
                welcome_msg = f"""
{beautiful_header('welcome')}

{welcome_text}
                """
                await message.reply_text(welcome_msg + beautiful_footer())
            else:
                # Default welcome
                default_welcome = f"""
🌸 **Welcome to the Group!** 🌸

👤 **Name:** {user.mention}
🆔 **User ID:** `{user.id}`
🏡 **Group:** {message.chat.title}

✨ Please read the group rules
🤝 Be respectful to everyone
💬 Enjoy your stay!
                """
                await message.reply_text(default_welcome + beautiful_footer())

# ================= HELP COMMAND =================
@app.on_message(filters.command("help") & filters.group)
async def help_command(client, message: Message):
    help_text = f"""
{beautiful_header('info')}

🤖 **BOT COMMANDS GUIDE**

🔧 **MODERATION COMMANDS:**
• `/mute [user] [duration] [reason]` - Mute user
• `/unmute [user]` - Unmute user
• `/ban [user] [reason]` - Ban user
• `/unban [user]` - Unban user
• `/kick [user] [reason]` - Kick user
• `/warn [user] [reason]` - Warn user
• `/warns [user]` - Check warnings
• `/purge [amount]` - Delete messages

👑 **ADMIN MANAGEMENT:**
• `/promote [user] [title]` - Promote to admin
• `/demote [user]` - Demote admin
• `/admins` - List admins
• `/info [user]` - User info

⚙️ **GROUP SETTINGS:**
• `/setrules [rules]` - Set group rules
• `/rules` - Show rules
• `/setwelcome [message]` - Set welcome
• `/id` - Get chat/user ID

💬 **SUPPORT SYSTEM:**
• Just message in private for support
• Admins will reply directly

📝 **VARIABLES FOR WELCOME:**
• {{name}} - User's first name
• {{username}} - User's username
• {{mention}} - User mention
• {{id}} - User ID
• {{title}} - Group title

⏰ **DURATION FORMAT:**
• 30m = 30 minutes
• 2h = 2 hours
• 1d = 1 day
• 1w = 1 week
    """
    
    await message.reply_text(help_text + beautiful_footer())


# ================= CALLBACK HANDLERS =================

# ================= START BUTTON CALLBACKS =================
@app.on_callback_query(filters.regex("^contact_support$"))
async def contact_support_cb(client, cq):
    await cq.answer()
    await cq.message.reply_text(
        f"{beautiful_header('support')}\n\n"
        "📩 **Contact Support**\n\n"
        "Bas apna message likhiye ✍️\n"
        "Support team jald reply karegi 😊"
        + beautiful_footer()
    )

@app.on_callback_query(filters.regex("^management$"))
async def management_cb(client, cq):
    await cq.answer()
    await cq.message.reply_text(
        f"{beautiful_header('moderation')}\n\n"
        "🔧 **Group Management Panel**\n\n"
        "Use buttons below or commands:\n"
        "• /help - All commands\n"
        "• /mute - Mute users\n"
        "• /ban - Ban users\n"
        "• /promote - Promote admins\n"
        + beautiful_footer(),
        reply_markup=moderation_buttons()
    )

@app.on_callback_query(filters.regex("^rules$"))
async def rules_cb(client, cq):
    await cq.answer()
    await cq.message.reply_text(
        f"{beautiful_header('settings')}\n\n"
        "📜 **Support Rules**\n\n"
        "✅ Respectful language ka use karein\n"
        "❌ Abuse bilkul allowed nahi\n"
        "🚫 Repeat violation par block\n"
        "⏳ Thoda patience rakhein\n\n"
        "🙏 Dhanyavaad"
        + beautiful_footer()
    )

# ================= USER HANDLER =================
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



# ================= REPLY BUTTON =================
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
        + beautiful_footer()
    )

    await cq.answer("Reply mode enabled ✅")

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

    cur.execute(
        "DELETE FROM admin_reply_target WHERE admin_id=?",
        (admin_id,)
    )
    conn.commit()

    try:
        if message.text:
            await client.send_message(
                user_id,
                f"{beautiful_header('support')}\n\n"
                f"**╭── 👨‍💼 SUPPORT REPLY ──╮**\n\n{message.text}"
                + beautiful_footer()
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

        await message.reply_text(
            f"{beautiful_header('support')}\n\n"
            "✅ **Reply sent to user**"
            + beautiful_footer()
        )

    except Exception as e:
        await message.reply_text(
            f"{beautiful_header('support')}\n\n"
            f"❌ **Failed to send reply**\n`{e}`"
            + beautiful_footer()
        )

# ================= BLOCK / UNBLOCK / HISTORY =================
@app.on_callback_query(filters.regex("^block:"))
async def cb_block(client, cq):
    user_id = int(cq.data.split(":")[1])
    cur.execute("INSERT OR IGNORE INTO blocked_users VALUES (?)", (user_id,))
    conn.commit()
    try:
        await client.send_message(
            user_id,
            f"{beautiful_header('support')}\n\n"
            "🔴 **You are blocked by admin.**"
            + beautiful_footer()
        )
    except:
        pass
    await cq.answer("Blocked")

@app.on_callback_query(filters.regex("^unblock:"))
async def cb_unblock(client, cq):
    user_id = int(cq.data.split(":")[1])
    cur.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM abuse_warnings WHERE user_id=?", (user_id,))
    cur.execute("DELETE FROM auto_reply_sent WHERE user_id=?", (user_id,))
    conn.commit()
    try:
        await client.send_message(
            user_id,
            f"{beautiful_header('support')}\n\n"
            "✅ **You are unblocked now.**"
            + beautiful_footer()
        )
    except:
        pass
    await cq.answer("Unblocked")

@app.on_callback_query(filters.regex("^history:"))
async def cb_history(client, cq):
    user_id = int(cq.data.split(":")[1])
    cur.execute("""
        SELECT sender,message_type,content,timestamp
        FROM contact_history
        WHERE user_id=?
        ORDER BY id DESC LIMIT 5
    """, (user_id,))
    rows = cur.fetchall()

    text = f"{beautiful_header('support')}\n\n📜 **History ({user_id})**\n\n"
    for s,t,c,ts in rows:
        text += f"🕒 {ts}\n{s.upper()} | {t}\n{c}\n———\n"

    await cq.message.reply_text(text[:3900])
    await cq.answer()

# ================= ADMIN ADD / REMOVE =================
@app.on_message(filters.command("addadmin") & filters.private)
async def add_admin(client, message: Message):
    if message.from_user.id != SUPER_ADMIN:
        return
    uid = int(message.command[1])
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?)", (uid,))
    conn.commit()
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        f"✅ **`{uid}` added as admin**"
        + beautiful_footer()
    )

@app.on_message(filters.command("removeadmin") & filters.private)
async def remove_admin(client, message: Message):
    if message.from_user.id != SUPER_ADMIN:
        return
    uid = int(message.command[1])
    if uid == SUPER_ADMIN:
        return
    cur.execute("DELETE FROM admins WHERE admin_id=?", (uid,))
    conn.commit()
    await message.reply_text(
        f"{beautiful_header('admin')}\n\n"
        f"🚫 **`{uid}` removed from admins**"
        + beautiful_footer(ho)
      )



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
if __name__ == "__main__":
    print("=" * 50)
    print(f"🤖 {BOT_BRAND}")
    print(f"✨ {BOT_TAGLINE}")
    print("=" * 50)
    print("✅ Bot starting with features:")
    print("• Support System")
    print("• Group Management")
    print("• Beautiful UI")
    print("• Database Backup")
    print("• Anti-Abuse Protection")
    print("=" * 50)
    
    # Start auto-unmute task
    asyncio.get_event_loop().create_task(check_mutes_task())
    
    app.run()
  
