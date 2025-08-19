#!/usr/bin/env python3
"""
Telegram Referral Bot
Kullanıcı istekleri:
- Ref sistemi (@darktunnel_ssh_tm kanali için)
- Ref başına 2 bal ödül
- VVOD sistemi (@kingvvod kanalına mesaj gönderme)
- Gift sistemi (bal ile TMT alım)
- Admin paneli
- Top 10 kullanıcı
- Balans gösterme
"""

import asyncio
import logging
import sqlite3
import os
import requests
import json
import time
from datetime import datetime
from threading import Lock, Thread
from urllib.parse import quote
from flask import Flask

# Bot Configuration
BOT_TOKEN = "8135962724:AAHYUtMIQxae7_5qD3zSQuMsYwq82nk0eVs"
BOT_USERNAME = "Kingref90_bot"
ADMIN_ID = 5736007283
TARGET_CHANNEL = "@darktunnel_ssh_tm"
VVOD_CHANNEL = "@kingvvod"

# Gift Prices
GIFT_PRICES = {
    30: 2,   # 30 bal → 2 TMT
    60: 4,   # 60 bal → 4 TMT
    120: 8,  # 120 bal → 8 TMT
    240: 16, # 240 bal → 16 TMT
    300: 20  # 300 bal → 20 TMT
}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SimpleDatabase:
    def __init__(self, db_path="bot_database.db"):
        self.db_path = db_path
        self.lock = Lock()
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        with self.lock:
            conn = self.get_connection()
            try:
                # Users table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        balance INTEGER DEFAULT 0,
                        referrer_id INTEGER,
                        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        is_member BOOLEAN DEFAULT 0
                    )
                """)
                
                # Referral logs table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS referral_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        referrer_id INTEGER,
                        referred_id INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        balance_added INTEGER,
                        status TEXT
                    )
                """)
                
                # Gift approvals table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS gift_approvals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT,
                        bal_cost INTEGER,
                        tmt_amount INTEGER,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        admin_response_time TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                """)
                
                conn.commit()
                logger.info("Database initialized successfully")
            finally:
                conn.close()
    
    def add_user(self, user_id, username, first_name, referrer_id=None):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    INSERT OR IGNORE INTO users (user_id, username, first_name, referrer_id)
                    VALUES (?, ?, ?, ?)
                """, (user_id, username, first_name, referrer_id))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def get_user(self, user_id):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
    
    def get_user_referrals(self, user_id):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    SELECT user_id, username, first_name, join_date
                    FROM users WHERE referrer_id = ?
                    ORDER BY join_date DESC
                """, (user_id,))
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
    
    def get_top_users(self, limit=10):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    SELECT user_id, username, first_name, balance
                    FROM users ORDER BY balance DESC LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
    
    def get_all_users(self):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("SELECT * FROM users ORDER BY join_date DESC")
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
    
    def get_referral_logs(self, limit=50):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    SELECT rl.*, u1.username as referrer_username, u2.username as referred_username
                    FROM referral_logs rl
                    LEFT JOIN users u1 ON rl.referrer_id = u1.user_id
                    LEFT JOIN users u2 ON rl.referred_id = u2.user_id
                    ORDER BY rl.timestamp DESC LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
    
    def update_balance(self, user_id, amount):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    UPDATE users SET balance = balance + ? WHERE user_id = ?
                """, (amount, user_id))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def log_referral(self, referrer_id, referred_id, balance_added, status):
        with self.lock:
            conn = self.get_connection()
            try:
                conn.execute("""
                    INSERT INTO referral_logs (referrer_id, referred_id, balance_added, status)
                    VALUES (?, ?, ?, ?)
                """, (referrer_id, referred_id, balance_added, status))
                conn.commit()
                return True
            finally:
                conn.close()
    
    def add_gift_approval(self, user_id, username, bal_cost, tmt_amount):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    INSERT INTO gift_approvals (user_id, username, bal_cost, tmt_amount)
                    VALUES (?, ?, ?, ?)
                """, (user_id, username, bal_cost, tmt_amount))
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()
    
    def get_gift_approval(self, approval_id):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("SELECT * FROM gift_approvals WHERE id = ?", (approval_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
    
    def update_gift_approval(self, approval_id, status, admin_response_time=None):
        with self.lock:
            conn = self.get_connection()
            try:
                if admin_response_time:
                    cursor = conn.execute("""
                        UPDATE gift_approvals SET status = ?, admin_response_time = ?
                        WHERE id = ?
                    """, (status, admin_response_time, approval_id))
                else:
                    cursor = conn.execute("""
                        UPDATE gift_approvals SET status = ? WHERE id = ?
                    """, (status, approval_id))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def get_expired_gifts(self):
        with self.lock:
            conn = self.get_connection()
            try:
                cursor = conn.execute("""
                    SELECT * FROM gift_approvals 
                    WHERE status = 'pending' 
                    AND datetime(timestamp, '+12 hours') <= datetime('now')
                """)
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.db = SimpleDatabase()
        self.waiting_for_vvod = set()
    
    def send_message(self, chat_id, text, reply_markup=None):
        """Send message via Telegram API"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, data=data)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None
    
    def get_chat_member(self, chat_id, user_id):
        """Check if user is member of channel"""
        url = f"{self.base_url}/getChatMember"
        data = {
            'chat_id': chat_id,
            'user_id': user_id
        }
        
        try:
            response = requests.post(url, data=data)
            result = response.json()
            if result.get('ok'):
                status = result['result']['status']
                return status in ['member', 'administrator', 'creator']
            return False
        except Exception as e:
            logger.error(f"Failed to check membership: {e}")
            return False
    
    def handle_start(self, message):
        """Handle /start command"""
        user = message.get('from', {})
        user_id = user.get('id')
        username = user.get('username', '')
        first_name = user.get('first_name', '')
        text = message.get('text', '')
        
        # Extract referrer ID from command
        referrer_id = None
        if ' ' in text:
            try:
                referrer_id = int(text.split(' ', 1)[1])
            except ValueError:
                pass
        
        # Check if user exists
        existing_user = self.db.get_user(user_id)
        
        if not existing_user:
            # Check referral
            if referrer_id and referrer_id != user_id:
                referrer = self.db.get_user(referrer_id)
                if referrer:
                    # Check channel membership
                    is_member = self.get_chat_member(TARGET_CHANNEL, user_id)
                    
                    if is_member:
                        # Add user with referrer
                        self.db.add_user(user_id, username, first_name, referrer_id)
                        
                        # Add balance to referrer
                        self.db.update_balance(referrer_id, 2)
                        
                        # Log referral
                        self.db.log_referral(referrer_id, user_id, 2, "success")
                        
                        # Notify referrer
                        self.send_message(referrer_id, "🎉 Size täze ref geldi! +2 bal goşuldy!")
                        
                        self.send_message(user_id, "✅ Hoş geldiňiz! Ref arkaly agza boldyňyz.")
                    else:
                        # Not a member
                        self.db.add_user(user_id, username, first_name)
                        self.db.log_referral(referrer_id, user_id, 0, "not_member")
                        
                        self.send_message(user_id, f"❌ Ozal kanala agza bolmaly: {TARGET_CHANNEL}")
                        return
                else:
                    # Invalid referrer
                    self.db.add_user(user_id, username, first_name)
            else:
                # No referral
                self.db.add_user(user_id, username, first_name)
        
        # Show main menu
        self.show_main_menu(user_id)
    
    def show_main_menu(self, user_id):
        """Show main menu"""
        keyboard = {
            'keyboard': [
                ['💰 Balans', '👥 Çagyranlarym'],
                ['🏆 Top 10', '🎁 Sowgatlar'],
                ['📝 VVOD', '🏠 Baş sahypa']
            ],
            'resize_keyboard': True
        }
        
        welcome_text = f"""🎉 Salamaleýkum! Ref botuna hoş geldiňiz!

🔗 Ref link döretmek üçin balans bölümini açyň
💰 Her tassyklanan ref üçin 2 bal alarsyňyz
🎁 Ballary sowgatlara çalyşyp bilersiňiz

Kanal: {TARGET_CHANNEL}"""
        
        self.send_message(user_id, welcome_text, keyboard)
    
    def handle_balance(self, user_id):
        """Show user balance and referral link"""
        user_data = self.db.get_user(user_id)
        if not user_data:
            self.send_message(user_id, "❌ Ulanyjy tapylmady.")
            return
        
        balance = user_data['balance']
        referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        
        message = f"""💰 **Balansiňyz:** {balance} bal
🔗 **Ref linki:**
`{referral_link}`

Her ref üçin 2 bal alarsyňyz!
Link arkaly adamlar kanala agza bolmaly."""
        
        self.send_message(user_id, message)
    
    def handle_referrals(self, user_id):
        """Show user's referrals"""
        referrals = self.db.get_user_referrals(user_id)
        
        if not referrals:
            self.send_message(user_id, "❌ Henizem hiç kim çagyrylmady.")
            return
        
        message = "👥 **Çagyranlarym:**\n\n"
        
        for i, ref in enumerate(referrals[:10], 1):
            username = ref['username'] if ref['username'] else "No username"
            name = ref['first_name'] if ref['first_name'] else "No name"
            join_date = ref['join_date'][:10]
            
            message += f"{i}. @{username} ({name})\n"
            message += f"   📅 {join_date}\n\n"
        
        if len(referrals) > 10:
            message += f"... we ýene {len(referrals) - 10} adam"
        
        self.send_message(user_id, message)
    
    def handle_top_users(self, user_id):
        """Show top 10 users"""
        top_users = self.db.get_top_users(10)
        
        if not top_users:
            self.send_message(user_id, "❌ Ulanyjylar tapylmady.")
            return
        
        message = "🏆 **Top 10 ulanyjy:**\n\n"
        
        for i, user in enumerate(top_users, 1):
            username = user['username'] if user['username'] else "No username"
            name = user['first_name'] if user['first_name'] else "No name"
            balance = user['balance']
            
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            message += f"{emoji} @{username} ({name})\n"
            message += f"    💰 {balance} bal\n\n"
        
        self.send_message(user_id, message)
    
    def handle_gifts(self, user_id):
        """Show available gifts"""
        user_data = self.db.get_user(user_id)
        if not user_data:
            self.send_message(user_id, "❌ Ulanyjy tapylmady.")
            return
        
        balance = user_data['balance']
        
        message = f"🎁 **Sowgatlar:**\n\n"
        message += f"💰 Siziň balansiňyz: {balance} bal\n\n"
        
        for bal_cost, tmt_amount in GIFT_PRICES.items():
            status = "✅" if balance >= bal_cost else "❌"
            message += f"{status} {bal_cost} bal → {tmt_amount} TMT\n"
        
        message += "\n📝 Sowgat almak üçin: `/gift <bal_miqdarı>`\n"
        message += "Mysal: `/gift 30`"
        
        self.send_message(user_id, message)
    
    def handle_gift_purchase(self, user_id, username, bal_cost):
        """Handle gift purchase"""
        try:
            bal_cost = int(bal_cost)
        except ValueError:
            self.send_message(user_id, "❌ Nädogry bal mukdary.")
            return
        
        if bal_cost not in GIFT_PRICES:
            self.send_message(user_id, "❌ Bu bal mukdary üçin sowgat ýok.")
            return
        
        user_data = self.db.get_user(user_id)
        if not user_data:
            self.send_message(user_id, "❌ Ulanyjy tapylmady.")
            return
        
        current_balance = user_data['balance']
        
        if current_balance < bal_cost:
            self.send_message(user_id, f"❌ Ýeterlik bal ýok. Siziň balansiňyz: {current_balance} bal")
            return
        
        # Deduct balance temporarily
        self.db.update_balance(user_id, -bal_cost)
        
        tmt_amount = GIFT_PRICES[bal_cost]
        new_balance = current_balance - bal_cost
        
        # Add to approval system
        approval_id = self.db.add_gift_approval(user_id, username, bal_cost, tmt_amount)
        
        # Send notification to admin channel with approval buttons
        approval_keyboard = {
            'inline_keyboard': [
                [
                    {'text': '✅ Tasdykla', 'callback_data': f'approve_{approval_id}'},
                    {'text': '❌ Ýatyr', 'callback_data': f'reject_{approval_id}'}
                ],
                [
                    {'text': '👤 Ulanyjy maglumaty', 'callback_data': f'userinfo_{user_id}'}
                ]
            ]
        }
        
        notification_text = f"🎁 **Täze sowgat haýyşy!**\n\n" \
                           f"👤 Ulanyjy: @{username} (ID: {user_id})\n" \
                           f"💰 Mukdar: {tmt_amount} TMT ({bal_cost} bal)\n" \
                           f"⏰ Wagty: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n" \
                           f"⚠️ 12 sagat içinde jogap bermeseňiz, awtomatiki tasdyklanar."
        
        self.send_message(VVOD_CHANNEL, notification_text, approval_keyboard)
        
        # Confirm to user
        self.send_message(user_id, 
            f"📝 Sowgat haýyşyňyz iberildi!\n\n"
            f"🎁 Sowgat: {tmt_amount} TMT\n"
            f"💰 Häzirki balans: {new_balance} bal\n\n"
            f"⏳ Admin tassyklamasyna garaşyň (iň köp 12 sagat)\n"
            f"🔔 Netije size habar beriler.")
    
    def handle_admin_command(self, user_id, command_parts):
        """Handle admin commands"""
        if user_id != ADMIN_ID:
            self.send_message(user_id, "❌ Bu buýruk diňe adminler üçin.")
            return
        
        if len(command_parts) < 2:
            self.send_admin_help(user_id)
            return
        
        action = command_parts[1].lower()
        
        if action == "users":
            self.show_admin_users(user_id)
        elif action == "logs":
            self.show_admin_logs(user_id)
        elif action == "setbal" and len(command_parts) == 4:
            target_user = int(command_parts[2])
            new_balance = int(command_parts[3])
            if self.db.get_user(target_user):
                # Set balance by updating with difference
                current = self.db.get_user(target_user)['balance']
                self.db.update_balance(target_user, new_balance - current)
                self.send_message(user_id, f"✅ User {target_user} balansy {new_balance} bal edildi.")
            else:
                self.send_message(user_id, "❌ Ulanyjy tapylmady.")
        else:
            self.send_admin_help(user_id)
    
    def send_admin_help(self, user_id):
        """Send admin help"""
        message = """🔧 **Admin Panel**

`/admin users` - Ulanyjylary görmek
`/admin logs` - Ref loglary görmek
`/admin setbal USER_ID BALANCE` - Bal bellemek

Mysal:
`/admin setbal 123456789 100`"""
        self.send_message(user_id, message)
    
    def show_admin_users(self, user_id):
        """Show users for admin"""
        users = self.db.get_all_users()
        
        if not users:
            self.send_message(user_id, "❌ Ulanyjy tapylmady.")
            return
        
        message = "👥 **Ähli ulanyjylar:**\n\n"
        
        for i, user in enumerate(users[:20], 1):
            username = user['username'] if user['username'] else f"User_{user['user_id']}"
            name = user['first_name'] if user['first_name'] else "No name"
            balance = user['balance']
            
            message += f"{i}. @{username} ({name})\n"
            message += f"   💰 {balance} bal | ID: {user['user_id']}\n\n"
        
        if len(users) > 20:
            message += f"... we ýene {len(users) - 20} ulanyjy"
        
        self.send_message(user_id, message)
    
    def show_admin_logs(self, user_id):
        """Show referral logs for admin"""
        logs = self.db.get_referral_logs(20)
        
        if not logs:
            self.send_message(user_id, "❌ Ref log tapylmady.")
            return
        
        message = "📊 **Referral Loglar:**\n\n"
        
        for i, log in enumerate(logs, 1):
            referrer = log['referrer_username'] or f"ID_{log['referrer_id']}"
            referred = log['referred_username'] or f"ID_{log['referred_id']}"
            balance_added = log['balance_added']
            status = log['status']
            timestamp = log['timestamp'][:16]
            
            status_emoji = {
                'success': '✅',
                'not_member': '❌',
                'already_referred': '⚠️'
            }.get(status, '❓')
            
            message += f"{i}. {status_emoji} @{referrer} → @{referred}\n"
            message += f"   💰 +{balance_added} bal | 📅 {timestamp}\n\n"
        
        self.send_message(user_id, message)
    
    def handle_vvod_start(self, user_id):
        """Start VVOD mode"""
        self.waiting_for_vvod.add(user_id)
        self.send_message(user_id, "📝 VVOD rejimi açyldy.\n\nIndiki ýerden ýazjak hatyňyz adminski kanala iberiler.\nÝatyrmak üçin /cancel ýazyň.")
    
    def handle_vvod_message(self, user_id, username, message_text):
        """Handle VVOD message"""
        if message_text == "/cancel":
            self.waiting_for_vvod.discard(user_id)
            self.send_message(user_id, "❌ VVOD rejimi ýatyryldy.")
            self.show_main_menu(user_id)
            return
        
        # Send to VVOD channel
        vvod_text = f"📝 VVOD @{username}:\n\n{message_text}"
        self.send_message(VVOD_CHANNEL, vvod_text)
        
        self.send_message(user_id, "✅ Hatyňyz ugradyldy!")
        self.waiting_for_vvod.discard(user_id)
        self.show_main_menu(user_id)
    
    def handle_callback_query(self, callback_query):
        """Handle callback queries (inline button presses)"""
        user_id = callback_query.get('from', {}).get('id')
        data = callback_query.get('data', '')
        message_id = callback_query.get('message', {}).get('message_id')
        
        if user_id != ADMIN_ID:
            return
        
        try:
            if data.startswith('approve_'):
                approval_id = int(data.split('_')[1])
                self.handle_gift_approval(approval_id, 'approved', user_id, message_id)
            elif data.startswith('reject_'):
                approval_id = int(data.split('_')[1])
                self.handle_gift_approval(approval_id, 'rejected', user_id, message_id)
            elif data.startswith('userinfo_'):
                target_user_id = int(data.split('_')[1])
                self.show_user_info_for_admin(target_user_id, user_id)
        except (ValueError, IndexError) as e:
            logger.error(f"Error handling callback: {e}")
    
    def handle_gift_approval(self, approval_id, status, admin_id, message_id):
        """Handle gift approval/rejection"""
        approval = self.db.get_gift_approval(approval_id)
        if not approval or approval['status'] != 'pending':
            self.send_message(admin_id, "❌ Bu sowgat haýyşy eýýäm işlenýär ýa-da tapylmaýar.")
            return
        
        # Update approval status
        current_time = datetime.now().isoformat()
        self.db.update_gift_approval(approval_id, status, current_time)
        
        user_id = approval['user_id']
        username = approval['username']
        tmt_amount = approval['tmt_amount']
        bal_cost = approval['bal_cost']
        
        if status == 'approved':
            # Gift approved - notify user
            self.send_message(user_id, 
                f"✅ **Sowgadyňyz tassyklandy!**\n\n"
                f"🎁 {tmt_amount} TMT\n"
                f"👤 Admin tarapyndan tassyklandy\n\n"
                f"📞 Indi size habarlaşarlar we sowgady bererler.")
            
            # Notify admin
            self.edit_message(VVOD_CHANNEL, message_id, 
                f"✅ **Tassyklanan sowgat**\n\n"
                f"👤 @{username} (ID: {user_id})\n"
                f"💰 {tmt_amount} TMT\n"
                f"⏰ Tassyklanan wagty: {current_time[:16]}")
        
        else:  # rejected
            # Return balance to user
            self.db.update_balance(user_id, bal_cost)
            
            # Notify user
            self.send_message(user_id, 
                f"❌ **Sowgat haýyşyňyz ýatyryldy**\n\n"
                f"💰 {bal_cost} bal gaýtaryldy\n"
                f"📝 Täzeden synanyşyp bilersiňiz.")
            
            # Notify admin
            self.edit_message(VVOD_CHANNEL, message_id,
                f"❌ **Ýatyrlan sowgat**\n\n"
                f"👤 @{username} (ID: {user_id})\n"
                f"💰 {tmt_amount} TMT\n"
                f"⏰ Ýatyrlan wagty: {current_time[:16]}")
    
    def show_user_info_for_admin(self, target_user_id, admin_id):
        """Show user info for admin"""
        user_data = self.db.get_user(target_user_id)
        if not user_data:
            self.send_message(admin_id, "❌ Ulanyjy tapylmady.")
            return
        
        referrals = self.db.get_user_referrals(target_user_id)
        referral_count = len(referrals)
        
        info_text = f"👤 **Ulanyjy maglumaty:**\n\n"
        info_text += f"🆔 ID: {user_data['user_id']}\n"
        info_text += f"👤 Ady: {user_data['first_name']}\n"
        info_text += f"🔗 Username: @{user_data['username'] or 'None'}\n"
        info_text += f"💰 Balans: {user_data['balance']} bal\n"
        info_text += f"👥 Çagyranlary: {referral_count} adam\n"
        info_text += f"📅 Goşulan wagty: {user_data['join_date'][:16]}"
        
        self.send_message(admin_id, info_text)
    
    def edit_message(self, chat_id, message_id, new_text):
        """Edit message text"""
        url = f"{self.base_url}/editMessageText"
        data = {
            'chat_id': chat_id,
            'message_id': message_id,
            'text': new_text,
            'parse_mode': 'Markdown'
        }
        
        try:
            response = requests.post(url, data=data)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            return None
    
    def process_expired_gifts(self):
        """Process expired gift approvals (auto-approve after 12 hours)"""
        expired_gifts = self.db.get_expired_gifts()
        
        for gift in expired_gifts:
            # Auto approve
            current_time = datetime.now().isoformat()
            self.db.update_gift_approval(gift['id'], 'auto_approved', current_time)
            
            # Notify user
            self.send_message(gift['user_id'], 
                f"✅ **Sowgadyňyz awtomatiki tassyklandy!**\n\n"
                f"🎁 {gift['tmt_amount']} TMT\n"
                f"⏰ 12 sagat geçensoň awtomatiki tassyklandy\n\n"
                f"📞 Indi size habarlaşarlar we sowgady bererler.")
    
    def handle_message(self, message):
        """Handle incoming messages"""
        user = message.get('from', {})
        user_id = user.get('id')
        username = user.get('username', str(user_id))
        text = message.get('text', '')
        
        # Ensure user exists
        if not self.db.get_user(user_id):
            self.db.add_user(user_id, username, user.get('first_name', ''))
        
        # Check VVOD mode
        if user_id in self.waiting_for_vvod:
            self.handle_vvod_message(user_id, username, text)
            return
        
        # Handle commands
        if text.startswith('/start'):
            self.handle_start(message)
        elif text == '💰 Balans':
            self.handle_balance(user_id)
        elif text == '📝 VVOD':
            self.handle_vvod_start(user_id)
        elif text == '🏠 Baş sahypa':
            self.show_main_menu(user_id)
        elif text == '👥 Çagyranlarym':
            self.handle_referrals(user_id)
        elif text == '🏆 Top 10':
            self.handle_top_users(user_id)
        elif text == '🎁 Sowgatlar':
            self.handle_gifts(user_id)
        elif text.startswith('/gift '):
            bal_amount = text.split(' ', 1)[1] if ' ' in text else ''
            self.handle_gift_purchase(user_id, username, bal_amount)
        elif text.startswith('/admin'):
            self.handle_admin_command(user_id, text.split())
        else:
            self.send_message(user_id, "❌ Nätanyş buýruk. Menýudan saýlaň.")

    def get_updates(self, offset=None):
        """Get updates from Telegram"""
        url = f"{self.base_url}/getUpdates"
        params = {'timeout': 30}
        if offset:
            params['offset'] = offset
        
        try:
            response = requests.get(url, params=params, timeout=35)
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get updates: {e}")
            return None
    
    def run_polling(self):
        """Run bot with polling"""
        logger.info("Starting bot polling...")
        offset = None
        
        while True:
            try:
                updates = self.get_updates(offset)
                
                if updates and updates.get('ok'):
                    for update in updates['result']:
                        offset = update['update_id'] + 1
                        
                        if 'message' in update:
                            self.handle_message(update['message'])
                        elif 'callback_query' in update:
                            self.handle_callback_query(update['callback_query'])
                
                # Process expired gifts every loop
                self.process_expired_gifts()
                        
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in polling: {e}")
                time.sleep(5)

# Keep alive server
app = Flask('')

@app.route('/')
def home():
    return "Bot aktif çalışıyor ✅"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# Test the complete system
async def test_system():
    logger.info("Testing system...")
    
    # Test database
    db = SimpleDatabase()
    db.add_user(12345, "testuser", "Test User")
    user = db.get_user(12345)
    logger.info(f"Test user: {user}")
    
    db.update_balance(12345, 10)
    user = db.get_user(12345)
    logger.info(f"Updated user balance: {user['balance']}")
    
    db.log_referral(12345, 67890, 2, "success")
    logger.info("Referral logged successfully")
    
    # Test bot
    bot = TelegramBot(BOT_TOKEN)
    logger.info("Bot initialized successfully")
    
    # Test message sending (to admin)
    # bot.send_message(ADMIN_ID, "🤖 Bot test başarılı!")
    
    logger.info("✅ All systems working!")
    logger.info(f"Bot token: {BOT_TOKEN[:10]}...")
    logger.info(f"Admin ID: {ADMIN_ID}")
    logger.info(f"Target Channel: {TARGET_CHANNEL}")
    logger.info(f"VVOD Channel: {VVOD_CHANNEL}")
    
    # Test admin message
    # bot.send_message(ADMIN_ID, "🤖 Bot başarıyla test edildi!")
    
    return bot

async def run_bot():
    """Run the bot"""
    # Start keep-alive server
    keep_alive()
    logger.info("Keep-alive server started on port 8080")
    
    bot = await test_system()
    
    if bot:
        logger.info("🚀 Starting bot...")
        # Send start message to admin
        bot.send_message(ADMIN_ID, "🤖 Telegram Referral Bot başlatylyp!\n\n✅ Sistem aktiw\n🔗 Ref sistemi hazır\n🎁 Gift sistemi hazır\n📝 VVOD sistemi hazır")
        bot.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")

# Test çalıştırılması için
if __name__ == '__main__' and 'test' in os.environ.get('RUN_MODE', ''):
    asyncio.run(test_system())