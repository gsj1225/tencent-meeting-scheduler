# -*- coding: utf-8 -*-
"""
腾讯会议排课调度工具 - 后端服务
用法: python server.py
访问: http://localhost:8080
"""

import json
import sqlite3
import os
import sys
import hashlib
import hmac
import base64
import time
import random
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from http.cookies import SimpleCookie
import secrets
import threading
import webbrowser
import requests as req_lib
import subprocess

PORT = int(os.getenv("SCHEDULE_PORT", "8080"))
BIND_HOST = os.getenv("SCHEDULE_BIND_HOST", "127.0.0.1")
IS_FROZEN = getattr(sys, 'frozen', False)
RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(sys.executable) if IS_FROZEN else RESOURCE_DIR
DB_FILE = os.getenv("SCHEDULE_DB_PATH", os.path.join(APP_DIR, 'schedule_data.db'))
APP_PASSWORD = os.getenv("SCHEDULE_APP_PASSWORD", "")
SESSION_SECRET = os.getenv("SCHEDULE_SESSION_SECRET", "") or secrets.token_hex(32)
SESSION_MAX_AGE = 12 * 60 * 60
_login_attempts = {}
_login_lock = threading.Lock()

# ========== 腾讯会议 API ==========
TC_APP_ID = os.getenv("TENCENT_MEETING_APP_ID", "")
TC_SDK_ID = os.getenv("TENCENT_MEETING_SDK_ID", "")
TC_SECRET_ID = os.getenv("TENCENT_MEETING_SECRET_ID", "")
TC_SECRET_KEY = os.getenv("TENCENT_MEETING_SECRET_KEY", "")
TC_API_BASE = "https://api.meeting.qq.com"

# 账号名 -> userid 映射（通过API拉取后缓存）
_account_userid_map = {}

def _tc_sign(http_method, header_nonce, header_timestamp, request_uri, request_body=""):
    """生成腾讯会议API签名"""
    _require_tc_config()
    header_string = f"X-TC-Key={TC_SECRET_ID}&X-TC-Nonce={header_nonce}&X-TC-Timestamp={header_timestamp}"
    string_to_sign = f"{http_method}\n{header_string}\n{request_uri}\n{request_body}"
    hmac_hash = hmac.new(TC_SECRET_KEY.encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha256).digest()
    hex_hash = hmac_hash.hex()
    return base64.b64encode(hex_hash.encode('utf-8')).decode('utf-8')

def _require_tc_config():
    """确保腾讯会议 API 凭据已通过环境变量配置。"""
    required = {
        "TENCENT_MEETING_APP_ID": TC_APP_ID,
        "TENCENT_MEETING_SDK_ID": TC_SDK_ID,
        "TENCENT_MEETING_SECRET_ID": TC_SECRET_ID,
        "TENCENT_MEETING_SECRET_KEY": TC_SECRET_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("缺少腾讯会议环境变量: " + ", ".join(missing))

def _tc_headers(uri, method="GET", body=""):
    """构建腾讯会议API请求头"""
    timestamp = str(int(time.time()))
    nonce = str(random.randint(10000, 99999))
    signature = _tc_sign(method, nonce, timestamp, uri, body)
    return {
        "Content-Type": "application/json",
        "X-TC-Key": TC_SECRET_ID,
        "X-TC-Timestamp": timestamp,
        "X-TC-Nonce": nonce,
        "X-TC-Signature": signature,
        "AppId": TC_APP_ID,
        "SdkId": TC_SDK_ID,
        "X-TC-Registered": "1",
    }

def _tc_get(uri):
    """GET请求腾讯会议API"""
    url = TC_API_BASE + uri
    headers = _tc_headers(uri, "GET", "")
    return req_lib.get(url, headers=headers, timeout=15)

def _tc_post(uri, body_dict):
    """POST请求腾讯会议API"""
    body_str = json.dumps(body_dict, ensure_ascii=False)
    url = TC_API_BASE + uri
    headers = _tc_headers(uri, "POST", body_str)
    return req_lib.post(url, headers=headers, data=body_str.encode('utf-8'), timeout=15)

def _tc_response_error(resp, action):
    """将腾讯会议上游错误转换成可读信息。"""
    try:
        data = resp.json()
        info = data.get('error_info', {})
        code = info.get('error_code', resp.status_code)
        message = info.get('message', resp.text)
        return f'{action}失败（{code}）：{message}'
    except Exception:
        return f'{action}失败：HTTP {resp.status_code} {resp.text[:200]}'

def refresh_account_userid_map():
    """从腾讯会议API拉取企业用户列表，建立账号名->userid映射"""
    global _account_userid_map
    operator_id = "wemeeting7699953"
    all_users = []
    pos = ""
    while True:
        uri = f"/v1/corp/users?page_size=20&operator_id={operator_id}&operator_id_type=1"
        if pos:
            uri += f"&pos={pos}"
        resp = _tc_get(uri)
        if resp.status_code != 200:
            raise RuntimeError(_tc_response_error(resp, '获取企业用户'))
        data = resp.json()
        all_users.extend(data.get("users", []))
        if data.get("has_remaining"):
            pos = data.get("next_pos", "")
        else:
            break
    _account_userid_map = {u.get("user_name", "").strip(): u.get("userid", "") for u in all_users}
    _account_userid_map = {name: uid for name, uid in _account_userid_map.items() if name and uid}
    if not _account_userid_map:
        raise RuntimeError('腾讯会议企业用户列表为空，请检查应用权限和 operator_id 配置')
    return _account_userid_map

def create_tencent_meeting(account_name, subject, start_ts, end_ts):
    """调用腾讯会议API创建会议，返回会议号"""
    if not _account_userid_map:
        refresh_account_userid_map()
    
    userid = _account_userid_map.get(account_name.strip())
    if not userid:
        return {'error': f'账号 {account_name} 未找到对应的腾讯会议userid'}
    
    body = {
        "userid": userid,
        "instanceid": 1,
        "subject": subject,
        "type": 0,
        "start_time": str(start_ts),
        "end_time": str(end_ts),
        "settings": {
            "mute_enable_join": True,
            "allow_unmute_self": True,
            "allow_in_before_host": True,
            "auto_in_waiting_room": False
        }
    }
    
    resp = _tc_post("/v1/meetings", body)
    if resp.status_code == 200:
        data = resp.json()
        meeting_info = data.get("meeting_info_list", [{}])[0]
        return {
            'meeting_code': meeting_info.get('meeting_code', ''),
            'meeting_id': meeting_info.get('meeting_id', ''),
            'join_url': meeting_info.get('join_url', '')
        }
    else:
        try:
            err = resp.json()
            return {'error': f"创建会议失败: {err.get('error_info', {}).get('message', resp.text)}"}
        except:
            return {'error': f'创建会议失败: HTTP {resp.status_code}'}

def _safe_nonnegative_int(value):
    """将腾讯会议接口中的数字字段安全转换为非负整数。"""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0

def _select_longest_recording(record_meetings):
    """从多条会议录制中选择时长最长的文件。"""
    candidates = []
    seen_files = set()

    for meeting in record_meetings:
        for record_file in meeting.get("record_files", []) or []:
            start_ms = _safe_nonnegative_int(record_file.get("record_start_time"))
            end_ms = _safe_nonnegative_int(record_file.get("record_end_time"))
            duration_ms = max(0, end_ms - start_ms)
            record_size = _safe_nonnegative_int(record_file.get("record_size"))
            sharing_url = str(record_file.get("sharing_url", "") or "").strip()
            file_key = (
                str(record_file.get("record_file_id", "") or ""),
                sharing_url,
                start_ms,
                end_ms,
            )
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            candidates.append({
                "meeting": meeting,
                "file": record_file,
                "duration_ms": duration_ms,
                "record_size": record_size,
                "sharing_url": sharing_url,
            })

    if not candidates:
        return None, 0

    # 正常情况下用起止时间计算时长；接口未返回时间时，用文件大小作为后备判断。
    selected = max(
        candidates,
        key=lambda item: (
            item["duration_ms"],
            item["record_size"],
            _safe_nonnegative_int(item["file"].get("record_end_time")),
        ),
    )
    return selected, len(candidates)

# ========== Database ==========
def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=10000')
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        edge_profile TEXT DEFAULT ''
    )''')
    # 兼容旧表：如果没有edge_profile列则添加
    try:
        c.execute('SELECT edge_profile FROM accounts LIMIT 1')
    except:
        c.execute("ALTER TABLE accounts ADD COLUMN edge_profile TEXT DEFAULT ''")
    c.execute('''CREATE TABLE IF NOT EXISTS schedules (
        id TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        student TEXT NOT NULL,
        course TEXT DEFAULT '',
        meeting_id TEXT DEFAULT ''
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sched_account_date ON schedules(account, date)')
    conn.commit()
    conn.close()

def get_all_data():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, edge_profile FROM accounts ORDER BY id')
    accounts = [{'name': row['name'], 'edge_profile': row['edge_profile'] or ''} for row in c.fetchall()]
    c.execute('SELECT id, account, date, start_time as startTime, end_time as endTime, student, course, meeting_id as meetingId FROM schedules ORDER BY date DESC, start_time ASC')
    schedules = [dict(row) for row in c.fetchall()]
    conn.close()
    return {'accounts': accounts, 'schedules': schedules}

# ========== API Handler ==========
class ScheduleHandler(SimpleHTTPRequestHandler):
    
    def log_message(self, format, *args):
        print('%s - %s' % (self.address_string(), format % args))

    def _session_token(self):
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(16)
        payload = timestamp + '.' + nonce
        signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return payload + '.' + signature

    def _authenticated(self):
        if not APP_PASSWORD:
            return True
        raw_cookie = self.headers.get('Cookie', '')
        try:
            cookie = SimpleCookie(raw_cookie)
            token = cookie['schedule_session'].value
            timestamp, nonce, signature = token.split('.', 2)
            payload = timestamp + '.' + nonce
            expected = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
            age = time.time() - int(timestamp)
            return hmac.compare_digest(signature, expected) and 0 <= age <= SESSION_MAX_AGE
        except (KeyError, ValueError, TypeError):
            return False

    def _require_auth(self, api=False):
        if self._authenticated():
            return True
        if api:
            self.send_error_json('登录已失效，请重新登录', 401)
        else:
            self.send_response(302)
            self.send_header('Location', '/login')
            self.end_headers()
        return False

    def _security_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'")

    def _origin_allowed(self):
        origin = self.headers.get('Origin')
        if not origin:
            return True
        forwarded_proto = self.headers.get('X-Forwarded-Proto', 'http').split(',')[0].strip()
        host = self.headers.get('Host', '')
        return origin == forwarded_proto + '://' + host

    def handle_login(self, body):
        client_ip = self.client_address[0]
        if BIND_HOST in ('127.0.0.1', '::1', 'localhost'):
            client_ip = self.headers.get('X-Real-IP', client_ip).strip()
        now = time.time()
        with _login_lock:
            attempts = [t for t in _login_attempts.get(client_ip, []) if now - t < 600]
            _login_attempts[client_ip] = attempts
            if len(attempts) >= 10:
                self.send_error_json('登录尝试过多，请10分钟后再试', 429)
                return
        password = str(body.get('password', ''))
        if not APP_PASSWORD or not hmac.compare_digest(password, APP_PASSWORD):
            with _login_lock:
                _login_attempts.setdefault(client_ip, []).append(now)
            self.send_error_json('密码错误', 401)
            return
        with _login_lock:
            _login_attempts.pop(client_ip, None)
        secure = self.headers.get('X-Forwarded-Proto', '').split(',')[0].strip() == 'https'
        cookie = 'schedule_session=' + self._session_token() + '; Path=/; HttpOnly; SameSite=Strict; Max-Age=' + str(SESSION_MAX_AGE)
        if secure:
            cookie += '; Secure'
        self.send_json({'success': True}, extra_headers={'Set-Cookie': cookie})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/api/health':
            self.send_json({'app': 'tencent-meeting-scheduler', 'status': 'ok', 'port': PORT, 'pid': os.getpid()})

        elif path == '/login':
            if self._authenticated():
                self.send_response(302)
                self.send_header('Location', '/')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self._security_headers()
            self.end_headers()
            login_path = os.path.join(RESOURCE_DIR, 'login.html')
            with open(login_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))

        elif path == '/' or path == '/index.html':
            if not self._require_auth():
                return
            # Serve the HTML file from same directory
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self._security_headers()
            self.end_headers()
            html_path = os.path.join(RESOURCE_DIR, 'index.html')
            with open(html_path, 'r', encoding='utf-8') as f:
                self.wfile.write(f.read().encode('utf-8'))
        
        elif path == '/api/data':
            if not self._require_auth(api=True):
                return
            self.send_json(get_all_data())
        
        elif path == '/favicon.png':
            favicon_path = os.path.join(RESOURCE_DIR, 'favicon.png')
            if os.path.exists(favicon_path):
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.send_header('Cache-Control', 'max-age=86400')
                self.end_headers()
                with open(favicon_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length).decode('utf-8')) if content_length > 0 else {}
        except:
            body = {}

        if path == '/api/login':
            self.handle_login(body)
            return
        if path == '/api/logout':
            self.send_json({'success': True}, extra_headers={'Set-Cookie': 'schedule_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0'})
            return
        if not self._require_auth(api=True):
            return
        if not self._origin_allowed():
            self.send_error_json('请求来源无效', 403)
            return

        if path == '/api/schedule/add':
            self.handle_add_schedule(body)
        elif path == '/api/tencent/create-meeting':
            self.handle_create_meeting(body)
        elif path == '/api/tencent/sync':
            self.handle_sync_meetings()
        elif path == '/api/tencent/playback':
            self.handle_query_playback(body)
        elif path == '/api/tencent/cancel-meeting':
            self.handle_cancel_meeting(body)
        elif path == '/api/tencent/recording-capacity':
            self.handle_recording_capacity()
        elif path == '/api/accounts/add':
            self.handle_add_accounts(body)
        elif path == '/api/account/remove':
            self.handle_remove_account(body)
        elif path == '/api/account/update_edge_profile':
            self.handle_update_edge_profile(body)
        elif path == '/api/edge/open-meeting':
            self.handle_open_edge_meeting(body)
        elif path == '/api/schedule/update':
            self.handle_update_schedule(body)
        elif path == '/api/schedule/delete':
            self.handle_delete_schedule(body)
        else:
            self.send_error(404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length).decode('utf-8')) if content_length > 0 else {}
        except:
            body = {}

        if not self._require_auth(api=True):
            return
        if not self._origin_allowed():
            self.send_error_json('请求来源无效', 403)
            return

        if path == '/api/data/import':
            self.handle_import_data(body)
        else:
            self.send_error(404)

    def send_json(self, data, status=200, extra_headers=None):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self._security_headers()
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def send_error_json(self, msg, status=400):
        self.send_json({'error': msg}, status)

    def handle_add_schedule(self, body):
        required = ['account', 'date', 'startTime', 'endTime', 'student']
        for field in required:
            if field not in body or not body[field]:
                self.send_error_json('缺少必填字段: ' + field)
                return
        
        sched_id = body.get('id', '')
        if not sched_id:
            sched_id = str(int(time.time() * 1000)) + ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))
        
        account = body['account']
        date = body['date']
        start_time = body['startTime']
        end_time = body['endTime']
        student = body['student']
        course = body.get('course', '')
        meeting_id = body.get('meetingId', '')
        auto_create = body.get('autoCreateMeeting', False)
        invitation_text = ''

        # Check conflict
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM schedules WHERE account=? AND date=? AND start_time<? AND end_time>?', 
                  (account, date, end_time, start_time))
        if c.fetchone():
            conn.close()
            self.send_error_json('冲突：该账号在此时间段已有排课')
            return

        # 如果需要自动创建腾讯会议且没有填会议号
        if auto_create and not meeting_id:
            # 构建会议主题
            subject = student
            if course:
                subject = student + ' ' + course
            # 转换时间为时间戳
            try:
                from datetime import datetime
                start_dt = datetime.strptime(date + ' ' + start_time, '%Y-%m-%d %H:%M')
                end_dt = datetime.strptime(date + ' ' + end_time, '%Y-%m-%d %H:%M')
                start_ts = int(start_dt.timestamp()) - 900  # 提前15分钟
                end_ts = int(end_dt.timestamp())
                
                result = create_tencent_meeting(account, subject, start_ts, end_ts)
                if 'error' in result:
                    conn.close()
                    self.send_error_json(result['error'])
                    return
                meeting_id = result.get('meeting_code', '')
                join_url = result.get('join_url', '')
                # 生成邀请文本
                meeting_code_fmt = meeting_id
                if len(meeting_id) >= 9:
                    meeting_code_fmt = meeting_id[:3] + '-' + meeting_id[3:6] + '-' + meeting_id[6:]
                start_fmt = start_dt.strftime('%Y/%m/%d') + ' ' + start_dt.strftime('%H:%M')
                end_fmt = end_dt.strftime('%H:%M')
                invitation_text = (
                    account + ' 邀请您参加腾讯会议\n'
                    '会议主题：' + subject + '\n'
                    '会议时间：' + start_fmt + '-' + end_fmt + ' (GMT+08:00) 中国标准时间 - 北京\n'
                    '\n'
                    '点击链接入会，或添加至会议列表：\n'
                    + join_url + '\n'
                    '\n'
                    '#腾讯会议：' + meeting_code_fmt
                )
            except Exception as e:
                conn.close()
                self.send_error_json(f'创建腾讯会议异常: {str(e)}')
                return

        # Auto-add account if not exists
        c.execute('SELECT id FROM accounts WHERE name=?', (account,))
        if not c.fetchone():
            c.execute('INSERT INTO accounts (name) VALUES (?)', (account,))

        c.execute('''INSERT INTO schedules (id, account, date, start_time, end_time, student, course, meeting_id) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (sched_id, account, date, start_time, end_time, student, course, meeting_id))
        conn.commit()
        conn.close()
        
        resp = {'success': True, 'id': sched_id}
        if meeting_id:
            resp['meetingId'] = meeting_id
        if invitation_text:
            resp['invitation'] = invitation_text
        self.send_json(resp)

    # 同步锁和缓存
    _sync_lock = threading.Lock()
    _last_sync_time = 0
    _last_sync_result = None
    _SYNC_CACHE_SECONDS = 300  # 5分钟缓存

    def handle_sync_meetings(self):
        """从腾讯会议API同步最新会议数据到数据库"""
        try:
            # 检查缓存：5分钟内不重复同步
            now_ts = time.time()
            if self._last_sync_result and (now_ts - self._last_sync_time) < self._SYNC_CACHE_SECONDS:
                cached = self._last_sync_result.copy()
                cached['cached'] = True
                self.send_json(cached)
                return
            
            # 同步锁：如果已有同步在进行中，直接返回跳过
            if not self._sync_lock.acquire(blocking=False):
                self.send_json({'success': True, 'new_meetings': 0, 'deleted_meetings': 0, 'total': 0, 'skipped': '同步正在进行中'})
                return
            
            try:
                if not _account_userid_map:
                    refresh_account_userid_map()
                
                from concurrent.futures import ThreadPoolExecutor, as_completed
                
                def fetch_user_meetings(acc_name, uid):
                    meetings = []
                    pos = 0
                    while True:
                        uri = f"/v1/meetings?userid={uid}&instanceid=1"
                        if pos:
                            uri += f"&pos={pos}"
                        resp = _tc_get(uri)
                        if resp.status_code != 200:
                            raise RuntimeError(_tc_response_error(resp, f'查询账号 {acc_name} 的会议'))
                        data = resp.json()
                        meetings.extend(data.get("meeting_info_list", []))
                        if data.get("remaining", 0) == 0:
                            break
                        pos = data.get("next_pos", 0)
                    return [(acc_name, m) for m in meetings]
                
                all_meetings = []
                fetch_errors = []
                with ThreadPoolExecutor(max_workers=8) as executor:
                    futures = [executor.submit(fetch_user_meetings, name, uid) for name, uid in _account_userid_map.items()]
                    for f in as_completed(futures):
                        try:
                            results = f.result()
                            for acc_name, m in results:
                                all_meetings.append({
                                    "account_name": acc_name,
                                    "subject": m.get("subject", ""),
                                    "meeting_code": m.get("meeting_code", ""),
                                    "start_time": m.get("start_time", ""),
                                    "end_time": m.get("end_time", ""),
                                })
                        except Exception as fetch_error:
                            fetch_errors.append(str(fetch_error))

                if fetch_errors:
                    preview = '；'.join(fetch_errors[:3])
                    if len(fetch_errors) > 3:
                        preview += f'；另有 {len(fetch_errors) - 3} 个账号失败'
                    raise RuntimeError(preview)
                
                conn = get_db()
                c = conn.cursor()
                c.execute('SELECT meeting_id FROM schedules')
                existing_codes = set(row[0] for row in c.fetchall() if row[0])
                
                from datetime import datetime
                new_count = 0
                for m in all_meetings:
                    code = m["meeting_code"]
                    if code in existing_codes:
                        continue
                    try:
                        start_ts = int(m["start_time"])
                        end_ts = int(m["end_time"])
                        start_dt = datetime.fromtimestamp(start_ts)
                        end_dt = datetime.fromtimestamp(end_ts)
                        date_str = start_dt.strftime("%Y-%m-%d")
                        start_str = start_dt.strftime("%H:%M")
                        end_str = end_dt.strftime("%H:%M")
                    except:
                        continue
                    
                    acc_name = m["account_name"]
                    c.execute('SELECT id FROM accounts WHERE name=?', (acc_name,))
                    if not c.fetchone():
                        c.execute('INSERT INTO accounts (name) VALUES (?)', (acc_name,))
                    
                    import uuid
                    sched_id = str(int(time.time()*1000)) + uuid.uuid4().hex[:6]
                    c.execute(
                        'INSERT INTO schedules (id, account, date, start_time, end_time, student, course, meeting_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (sched_id, acc_name, date_str, start_str, end_str, '', m['subject'], code)
                    )
                    existing_codes.add(code)
                    new_count += 1
                
                remote_codes = set(m['meeting_code'] for m in all_meetings)
                c.execute('SELECT id, meeting_id FROM schedules WHERE meeting_id != ""')
                local_records = c.fetchall()
                deleted_count = 0
                for row in local_records:
                    local_code = row[1]
                    local_code_clean = local_code.replace('-', '')
                    if local_code not in remote_codes and local_code_clean not in remote_codes:
                        c.execute('DELETE FROM schedules WHERE id=?', (row[0],))
                        deleted_count += 1
                
                conn.commit()
                conn.close()
                result = {'success': True, 'new_meetings': new_count, 'deleted_meetings': deleted_count, 'total': len(all_meetings)}
                self._last_sync_time = time.time()
                self._last_sync_result = result
                self.send_json(result)
            except Exception as e_inner:
                self.send_error_json(f'同步失败: {str(e_inner)}')
            finally:
                self._sync_lock.release()
        except Exception as e:
            self.send_error_json(f'同步失败: {str(e)}')

    def handle_create_meeting(self, body):
        """单独创建腾讯会议"""
        account = body.get('account', '')
        subject = body.get('subject', '')
        date = body.get('date', '')
        start_time = body.get('startTime', '')
        end_time = body.get('endTime', '')
        
        if not account or not subject or not date or not start_time or not end_time:
            self.send_error_json('缺少必要参数')
            return
        
        try:
            from datetime import datetime
            start_dt = datetime.strptime(date + ' ' + start_time, '%Y-%m-%d %H:%M')
            end_dt = datetime.strptime(date + ' ' + end_time, '%Y-%m-%d %H:%M')
            start_ts = int(start_dt.timestamp()) - 900  # 提前15分钟
            end_ts = int(end_dt.timestamp())
            
            result = create_tencent_meeting(account, subject, start_ts, end_ts)
            if 'error' in result:
                self.send_error_json(result['error'])
            else:
                self.send_json({'success': True, **result})
        except Exception as e:
            self.send_error_json(f'创建会议异常: {str(e)}')

    def handle_query_playback(self, body):
        """根据会议号查询会议录制回放信息"""
        meeting_code = body.get('meetingCode', '').strip()
        if not meeting_code:
            self.send_error_json('请输入会议号')
            return
        
        meeting_code_clean = meeting_code.replace('-', '')
        
        try:
            if not _account_userid_map:
                refresh_account_userid_map()
            
            # 用 /v1/records 接口按 meeting_code 并发查询所有用户
            now_ts = int(time.time())
            start_ts = now_ts - 30 * 86400  # 30天内
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            def query_user_records(uid):
                user_records = []
                page = 1
                while True:
                    uri = f"/v1/records?meeting_code={meeting_code_clean}&userid={uid}&start_time={start_ts}&end_time={now_ts}&page_size=20&page={page}"
                    resp = _tc_get(uri)
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    records = data.get("record_meetings", []) or []
                    for record in records:
                        returned_code = str(record.get("meeting_code", "") or "").replace("-", "").replace(" ", "")
                        if returned_code == meeting_code_clean:
                            user_records.append(record)
                    total_page = _safe_nonnegative_int(data.get("total_page"))
                    if not records or (total_page and page >= total_page) or (not total_page and len(records) < 20):
                        break
                    page += 1
                return user_records
            
            all_records = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(query_user_records, uid): uid for uid in _account_userid_map.values()}
                for f in as_completed(futures):
                    try:
                        result = f.result()
                        if result:
                            all_records.extend(result)
                    except Exception:
                        pass
            
            if not all_records:
                self.send_json({'error': '未找到该会议号的录制，可能未开启云录制或会议号有误'})
                return

            selected, record_count = _select_longest_recording(all_records)
            if not selected:
                self.send_json({'error': '已找到会议录制，但没有可用的录制文件'})
                return
            
            found_record = selected["meeting"]
            selected_file = selected["file"]
            subject = found_record.get("subject", "")
            record_time = ''
            media_start = selected_file.get("record_start_time") or found_record.get("media_start_time", 0)
            if media_start:
                try:
                    from datetime import datetime
                    rt = datetime.fromtimestamp(int(media_start) / 1000)
                    record_time = rt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    record_time = str(media_start)
            
            playback_url = selected["sharing_url"]
            if not playback_url:
                self.send_json({'error': '已找到最长的录制文件，但该文件尚未开启共享，请在腾讯会议中开启共享后重试'})
                return
            
            self.send_json({
                'subject': subject,
                'recordTime': record_time,
                'playbackUrl': playback_url,
                'durationSeconds': selected["duration_ms"] // 1000,
                'recordSize': selected["record_size"],
                'recordCount': record_count,
                'selection': 'longest'
            })
        except Exception as e:
            self.send_error_json(f'查询回放失败: {str(e)}')

    _capacity_cache = None
    _capacity_cache_time = 0
    _CAPACITY_CACHE_SECONDS = 1800  # 30分钟缓存

    def handle_recording_capacity(self):
        """查询每个教师账号的录制文件总容量"""
        # 30分钟缓存
        now_ts = time.time()
        if self._capacity_cache and (now_ts - self._capacity_cache_time) < self._CAPACITY_CACHE_SECONDS:
            self.send_json(self._capacity_cache)
            return
        try:
            if not _account_userid_map:
                refresh_account_userid_map()
            
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            now_ts = int(time.time())
            # API限制时间范围不超过31天，分段查询180天
            segments = []
            seg_end = now_ts
            while seg_end > now_ts - 180 * 86400:
                seg_start = max(seg_end - 30 * 86400, now_ts - 180 * 86400)
                segments.append((seg_start, seg_end))
                seg_end = seg_start
            
            def query_user_records_all(acc_name, uid):
                total_size = 0
                file_count = 0
                for seg_start, seg_end in segments:
                    pos = 1
                    while True:
                        uri = f"/v1/records?userid={uid}&start_time={seg_start}&end_time={seg_end}&page_size=20&page={pos}"
                        resp = _tc_get(uri)
                        if resp.status_code != 200:
                            break
                        data = resp.json()
                        records = data.get("record_meetings", [])
                        for rm in records:
                            for rf in rm.get("record_files", []):
                                size = rf.get("record_size", 0)
                                if isinstance(size, str):
                                    try:
                                        size = int(size)
                                    except:
                                        size = 0
                                total_size += size
                                file_count += 1
                        total = data.get("total_count", 0)
                        remaining = data.get("remaining", 0)
                        if remaining == 0 or pos * 20 >= total:
                            break
                        pos += 1
                return {'account': acc_name, 'total_size': total_size, 'file_count': file_count}
            
            results = []
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(query_user_records_all, name, uid) for name, uid in _account_userid_map.items()]
                for f in as_completed(futures):
                    try:
                        results.append(f.result())
                    except:
                        pass
            
            # 按容量降序排列
            results.sort(key=lambda x: x['total_size'], reverse=True)
            
            # 转换为可读大小
            def format_size(size_bytes):
                if size_bytes == 0:
                    return '0 B'
                gb = size_bytes / (1024**3)
                mb = size_bytes / (1024**2)
                if gb >= 1:
                    return f'{gb:.2f} GB'
                elif mb >= 1:
                    return f'{mb:.1f} MB'
                else:
                    return f'{size_bytes / 1024:.0f} KB'
            
            for r in results:
                r['size_text'] = format_size(r['total_size'])
            
            total_all = sum(r['total_size'] for r in results)
            total_files = sum(r['file_count'] for r in results)
            
            capacity_result = {
                'accounts': results,
                'total_size': total_all,
                'total_size_text': format_size(total_all),
                'total_files': total_files
            }
            self._capacity_cache = capacity_result
            self._capacity_cache_time = time.time()
            self.send_json(capacity_result)
        except Exception as e:
            self.send_error_json(f'查询录制容量失败: {str(e)}')

    def handle_add_accounts(self, body):
        names = body.get('names', [])
        if not names:
            self.send_error_json('请提供账号列表')
            return
        
        conn = get_db()
        c = conn.cursor()
        added = 0
        for name in names:
            if name.strip():
                try:
                    c.execute('INSERT OR IGNORE INTO accounts (name) VALUES (?)', (name.strip(),))
                    if c.rowcount > 0:
                        added += 1
                except:
                    pass
        conn.commit()
        conn.close()
        self.send_json({'success': True, 'added': added})

    def handle_remove_account(self, body):
        name = body.get('name', '')
        if not name:
            self.send_error_json('请提供账号名称')
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM schedules WHERE account=?', (name,))
        if c.fetchone():
            conn.close()
            self.send_error_json('该账号有排课记录，请先删除相关排课')
            return
        
        c.execute('DELETE FROM accounts WHERE name=?', (name,))
        conn.commit()
        conn.close()
        self.send_json({'success': True})

    def handle_update_edge_profile(self, body):
        name = body.get('name', '')
        edge_profile = body.get('edge_profile', '')
        if not name:
            self.send_error_json('请提供账号名称')
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE accounts SET edge_profile=? WHERE name=?', (edge_profile, name))
        conn.commit()
        conn.close()
        self.send_json({'success': True})

    def handle_open_edge_meeting(self, body):
        edge_profile = body.get('edge_profile', '').strip()
        account_name = body.get('account_name', '')
        if not edge_profile:
            self.send_error_json('未指定Edge配置文件')
            return
        
        url = 'https://meeting.tencent.com/user-center'
        try:
            if sys.platform == 'win32':
                edge_paths = [
                    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
                    os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
                ]
                edge_exe = next((p for p in edge_paths if os.path.isfile(p)), None)
                if not edge_exe:
                    self.send_error_json('未找到Edge浏览器，请确认Edge已安装')
                    return
                subprocess.Popen(
                    [edge_exe, '--profile-directory=' + edge_profile, url],
                    creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
                )
            elif sys.platform == 'darwin':
                edge_apps = [
                    '/Applications/Microsoft Edge.app',
                    os.path.expanduser('~/Applications/Microsoft Edge.app'),
                ]
                if not any(os.path.isdir(path) for path in edge_apps):
                    self.send_error_json('未找到Microsoft Edge，请先在Mac上安装Edge浏览器')
                    return
                subprocess.Popen(
                    [
                        'open', '-na', 'Microsoft Edge', '--args',
                        '--profile-directory=' + edge_profile, url
                    ],
                    start_new_session=True
                )
            else:
                self.send_error_json('当前系统暂不支持自动打开Edge配置文件')
                return
            self.send_json({
                'success': True,
                'message': '已打开Edge浏览器',
                'account': account_name
            })
        except Exception as e:
            self.send_error_json('打开Edge失败: ' + str(e))

    def handle_update_schedule(self, body):
        sched_id = body.get('id', '')
        if not sched_id:
            self.send_error_json('缺少排课ID')
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM schedules WHERE id=?', (sched_id,))
        if not c.fetchone():
            conn.close()
            self.send_error_json('排课记录不存在')
            return
        
        account = body.get('account', '')
        date = body.get('date', '')
        start_time = body.get('startTime', '')
        end_time = body.get('endTime', '')
        
        # Check conflict (exclude self)
        if account and date and start_time and end_time:
            c.execute('SELECT id FROM schedules WHERE account=? AND date=? AND start_time<? AND end_time>? AND id!=?',
                      (account, date, end_time, start_time, sched_id))
            if c.fetchone():
                conn.close()
                self.send_error_json('冲突：该账号在此时间段已有其他排课')
                return
        
        sets = []
        params = []
        for key, col in [('account', 'account'), ('date', 'date'), ('startTime', 'start_time'), 
                          ('endTime', 'end_time'), ('student', 'student'), ('course', 'course'), ('meetingId', 'meeting_id')]:
            if key in body:
                sets.append(col + '=?')
                params.append(body[key])
        
        if sets:
            params.append(sched_id)
            c.execute('UPDATE schedules SET ' + ', '.join(sets) + ' WHERE id=?', params)
            conn.commit()
        
        conn.close()
        self.send_json({'success': True})

    def handle_delete_schedule(self, body):
        sched_id = body.get('id', '')
        if not sched_id:
            self.send_error_json('缺少排课ID')
            return
        
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM schedules WHERE id=?', (sched_id,))
        conn.commit()
        conn.close()
        self.send_json({'success': True})

    def handle_import_data(self, body):
        accounts = body.get('accounts', [])
        schedules = body.get('schedules', [])
        
        if not isinstance(accounts, list) or not isinstance(schedules, list):
            self.send_error_json('数据格式不正确')
            return
        
        conn = get_db()
        c = conn.cursor()
        
        # Clear existing data
        c.execute('DELETE FROM schedules')
        c.execute('DELETE FROM accounts')
        
        # Insert accounts
        for name in accounts:
            if name:
                c.execute('INSERT OR IGNORE INTO accounts (name) VALUES (?)', (name,))
        
        # Insert schedules
        for s in schedules:
            c.execute('''INSERT OR IGNORE INTO schedules (id, account, date, start_time, end_time, student, course, meeting_id)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                      (s.get('id', ''), s.get('account', ''), s.get('date', ''), 
                       s.get('startTime', ''), s.get('endTime', ''), s.get('student', ''),
                       s.get('course', ''), s.get('meetingId', '')))
        
        conn.commit()
        conn.close()
        self.send_json({'success': True, 'accounts': len(accounts), 'schedules': len(schedules)})

    # CORS
    def do_OPTIONS(self):
        self.send_error(405)


    def handle_cancel_meeting(self, body):
        """根据会议号取消腾讯会议"""
        meeting_code = body.get('meetingCode', '').strip()
        if not meeting_code:
            self.send_error_json('请输入会议号')
            return
        
        meeting_code_clean = meeting_code.replace('-', '')
        
        try:
            if not _account_userid_map:
                refresh_account_userid_map()
            
            # 先找到该会议号的 meeting_id 和创建者 userid
            meeting_id = None
            host_userid = None
            subject = ''
            
            for acc_name, uid in _account_userid_map.items():
                uri = f"/v1/meetings?userid={uid}&instanceid=1"
                resp = _tc_get(uri)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                meetings = data.get("meeting_info_list", [])
                for m in meetings:
                    code = m.get("meeting_code", "")
                    if code == meeting_code_clean or code == meeting_code:
                        meeting_id = m.get("meeting_id", "")
                        host_userid = uid
                        subject = m.get("subject", "")
                        break
                if meeting_id:
                    break
            
            if not meeting_id:
                self.send_json({'error': '未找到该会议号的有效会议，可能会议已结束或已取消'})
                return
            
            # 调用取消会议接口
            cancel_uri = f"/v1/meetings/{meeting_id}/cancel"
            cancel_body = {
                "userid": host_userid,
                "instanceid": 1,
                "reason_code": 1,
                "reason_detail": "排课工具取消"
            }
            resp = _tc_post(cancel_uri, cancel_body)
            
            if resp.status_code == 200:
                # 同时删除本地数据库中的排课记录
                conn = get_db()
                c = conn.cursor()
                c.execute("DELETE FROM schedules WHERE meeting_id=? OR meeting_id=?", (meeting_code_clean, meeting_code))
                conn.commit()
                conn.close()
                self.send_json({'success': True, 'subject': subject})
            else:
                try:
                    err = resp.json()
                    self.send_json({'error': f"取消会议失败: {err.get('error_info', {}).get('message', resp.text)}"})
                except:
                    self.send_json({'error': f'取消会议失败: HTTP {resp.status_code}'})
        except Exception as e:
            self.send_error_json(f'取消会议失败: {str(e)}')

# ========== Main ==========
if __name__ == '__main__':
    init_db()
    
    server = ThreadingHTTPServer((BIND_HOST, PORT), ScheduleHandler)
    
    print('=' * 50)
    print('  腾讯会议排课调度工具 已启动!')
    print('=' * 50)
    print(f'  本机访问:  http://localhost:{PORT}')
    print(f'  数据库文件: {DB_FILE}')
    print(f'  登录保护:   {"已启用" if APP_PASSWORD else "未启用（仅建议本地使用）"}')
    print(f'  每位同事请在自己的电脑上运行本工具')
    print('=' * 50)
    print('  按 Ctrl+C 停止服务')
    print()

    if os.getenv('SCHEDULE_OPEN_BROWSER', '1' if IS_FROZEN else '0') == '1':
        threading.Timer(1.0, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
        server.server_close()
