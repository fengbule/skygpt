# -*- coding: utf-8 -*-
"""
Database Models and Operations
SQLite for storing tasks, proxies, and accounts
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "skygpt.db"

TASK_EXTRA_COLUMNS = {
    "registration_mode": "TEXT DEFAULT 'email'",
    "phone_country": "TEXT",
    "sms_service_code": "TEXT",
    "sms_operator": "TEXT",
    "sms_activation_id": "TEXT",
    "phone_number": "TEXT",
    "sms_provider": "TEXT",
}

SMS_SETTING_DEFAULTS = {
    "auto_select_best_country": False,
    "best_country_min_stock": 20,
    "best_country_max_price": 0,
}


def _ensure_task_columns(cursor) -> None:
    cursor.execute("PRAGMA table_info(registration_tasks)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    for column_name, ddl in TASK_EXTRA_COLUMNS.items():
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE registration_tasks ADD COLUMN {column_name} {ddl}")


def _task_row_to_dict(row) -> Dict[str, Any]:
    if not row:
        return None

    task = {
        "id": row[0],
        "email": row[1],
        "name": row[2],
        "birthday": row[3],
        "proxy": row[4],
        "status": row[5],
        "created_at": row[6],
        "started_at": row[7],
        "completed_at": row[8],
        "error": row[9],
        "account_id": row[10],
        "access_token": row[11],
        "log_file": row[12],
        "registration_mode": "email",
        "phone_country": None,
        "sms_service_code": None,
        "sms_operator": None,
        "sms_activation_id": None,
        "phone_number": None,
        "sms_provider": None,
    }

    extra_keys = list(TASK_EXTRA_COLUMNS.keys())
    for offset, key in enumerate(extra_keys, start=13):
        if len(row) > offset:
            task[key] = row[offset]

    task["registration_mode"] = (task.get("registration_mode") or "email").lower()
    return task

def init_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registration_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT,
            birthday TEXT,
            proxy TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            error TEXT,
            account_id TEXT,
            access_token TEXT,
            log_file TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            type TEXT,
            source TEXT,
            available INTEGER DEFAULT 0,
            latency REAL,
            last_check TEXT,
            created_at TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            account_id TEXT,
            access_token TEXT,
            refresh_token TEXT,
            id_token TEXT,
            cpa_file TEXT,
            expired TEXT,
            created_at TEXT,
            disabled INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sms_provider_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL UNIQUE,
            display_name TEXT,
            enabled INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            config_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    _ensure_task_columns(cursor)
    
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)

class TaskDB:
    @staticmethod
    def create_task(
        email: str,
        name: str = None,
        birthday: str = None,
        proxy: str = None,
        registration_mode: str = "email",
        phone_country: str = None,
        sms_service_code: str = None,
        sms_operator: str = None,
        sms_activation_id: str = None,
        phone_number: str = None,
        sms_provider: str = None,
    ) -> Dict:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        log_file = str(DATA_DIR / f"logs/task_{now.replace(':', '-')}.log")
        registration_mode = (registration_mode or "email").strip().lower()
        
        cursor.execute("""
            INSERT INTO registration_tasks (
                email, name, birthday, proxy, status, created_at, log_file,
                registration_mode, phone_country, sms_service_code, sms_operator,
                sms_activation_id, phone_number, sms_provider
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            email,
            name,
            birthday,
            proxy,
            now,
            log_file,
            registration_mode,
            phone_country,
            sms_service_code,
            sms_operator,
            sms_activation_id,
            phone_number,
            sms_provider,
        ))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {
            "id": task_id,
            "email": email,
            "name": name,
            "birthday": birthday,
            "proxy": proxy,
            "status": "pending",
            "created_at": now,
            "log_file": log_file,
            "registration_mode": registration_mode,
            "phone_country": phone_country,
            "sms_service_code": sms_service_code,
            "sms_operator": sms_operator,
            "sms_activation_id": sms_activation_id,
            "phone_number": phone_number,
            "sms_provider": sms_provider,
        }
    
    @staticmethod
    def get_task(task_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registration_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        return _task_row_to_dict(row)
    
    @staticmethod
    def update_task(task_id: int, **kwargs) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        
        valid_fields = [
            "status", "started_at", "completed_at", "error", "account_id", "access_token",
            "registration_mode", "phone_country", "sms_service_code", "sms_operator",
            "sms_activation_id", "phone_number", "sms_provider",
        ]
        updates = {}
        for field, value in kwargs.items():
            if field in valid_fields:
                if field == "registration_mode":
                    value = (value or "email").strip().lower()
                updates[field] = value
        
        if not updates:
            conn.close()
            return False
        
        sql = "UPDATE registration_tasks SET " + ", ".join([f"{k} = ?" for k in updates.keys()]) + " WHERE id = ?"
        values = list(updates.values()) + [task_id]
        
        cursor.execute(sql, values)
        conn.commit()
        conn.close()
        return True
    
    @staticmethod
    def list_tasks(status: str = None) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("SELECT * FROM registration_tasks WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cursor.execute("SELECT * FROM registration_tasks ORDER BY created_at DESC")
        
        rows = cursor.fetchall()
        conn.close()
        
        tasks = []
        for row in rows:
            tasks.append(_task_row_to_dict(row))
        return tasks

class ProxyDB:
    @staticmethod
    def add_proxy(url: str, type: str = "manual", source: str = "manual") -> Dict:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        
        try:
            cursor.execute("""
                INSERT INTO proxies (url, type, source, created_at)
                VALUES (?, ?, ?, ?)
            """, (url, type, source, now))
            
            proxy_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return {
                "id": proxy_id,
                "url": url,
                "type": type,
                "source": source,
                "available": 0,
                "created_at": now
            }
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    @staticmethod
    def get_proxy(proxy_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM proxies WHERE id = ?", (proxy_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "url": row[1],
                "type": row[2],
                "source": row[3],
                "available": row[4],
                "latency": row[5],
                "last_check": row[6],
                "created_at": row[7]
            }
        return None
    
    @staticmethod
    def update_proxy(proxy_id: int, available: int, latency: float = None) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        
        cursor.execute("""
            UPDATE proxies SET available = ?, latency = ?, last_check = ?
            WHERE id = ?
        """, (available, latency, now, proxy_id))
        
        conn.commit()
        conn.close()
        return True
    
    @staticmethod
    def list_proxies(source: str = None) -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        
        if source:
            cursor.execute("SELECT * FROM proxies WHERE source = ? ORDER BY created_at DESC", (source,))
        else:
            cursor.execute("SELECT * FROM proxies ORDER BY created_at DESC")
        
        rows = cursor.fetchall()
        conn.close()
        
        proxies = []
        for row in rows:
            proxies.append({
                "id": row[0],
                "url": row[1],
                "type": row[2],
                "source": row[3],
                "available": row[4],
                "latency": row[5],
                "last_check": row[6],
                "created_at": row[7]
            })
        return proxies
    
    @staticmethod
    def delete_proxy(proxy_id: int) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM proxies WHERE id = ?", (proxy_id,))
        conn.commit()
        conn.close()
        return True

class AccountDB:
    @staticmethod
    def save_account(email: str, account_data: Dict) -> Dict:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        
        cursor.execute("""
            INSERT OR REPLACE INTO accounts (
                email, account_id, access_token, refresh_token, id_token, 
                cpa_file, expired, created_at, disabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            email,
            account_data.get("account_id"),
            account_data.get("access_token"),
            account_data.get("refresh_token"),
            account_data.get("id_token"),
            account_data.get("cpa_file"),
            account_data.get("expired"),
            now
        ))
        
        account_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {
            "id": account_id,
            "email": email,
            "account_id": account_data.get("account_id"),
            "access_token": account_data.get("access_token"),
            "refresh_token": account_data.get("refresh_token"),
            "id_token": account_data.get("id_token"),
            "cpa_file": account_data.get("cpa_file"),
            "expired": account_data.get("expired"),
            "created_at": now,
            "disabled": 0
        }
    
    @staticmethod
    def get_account(email: str) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "email": row[1],
                "account_id": row[2],
                "access_token": row[3],
                "refresh_token": row[4],
                "id_token": row[5],
                "cpa_file": row[6],
                "expired": row[7],
                "created_at": row[8],
                "disabled": row[9]
            }
        return None
    
    @staticmethod
    def list_accounts() -> List[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()
        
        accounts = []
        for row in rows:
            accounts.append({
                "id": row[0],
                "email": row[1],
                "account_id": row[2],
                "access_token": row[3],
                "refresh_token": row[4],
                "id_token": row[5],
                "cpa_file": row[6],
                "expired": row[7],
                "created_at": row[8],
                "disabled": row[9]
            })
        return accounts


class SMSProviderSettingsDB:
    @staticmethod
    def _row_to_dict(row) -> Optional[Dict[str, Any]]:
        if not row:
            return None
        try:
            config = json.loads(row[5] or "{}")
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        merged_config = {**SMS_SETTING_DEFAULTS, **config}
        return {
            "id": row[0],
            "provider": row[1],
            "display_name": row[2] or row[1],
            "enabled": bool(row[3]),
            "is_default": bool(row[4]),
            "config": merged_config,
            "created_at": row[6],
            "updated_at": row[7],
        }

    @staticmethod
    def list_provider_settings() -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, provider, display_name, enabled, is_default, config_json, created_at, updated_at FROM sms_provider_settings ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
        return [item for item in (SMSProviderSettingsDB._row_to_dict(row) for row in rows) if item]

    @staticmethod
    def get_provider_setting(provider: str) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, provider, display_name, enabled, is_default, config_json, created_at, updated_at FROM sms_provider_settings WHERE provider = ?",
            (provider,),
        )
        row = cursor.fetchone()
        conn.close()
        return SMSProviderSettingsDB._row_to_dict(row)

    @staticmethod
    def get_default_provider() -> Optional[str]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT provider FROM sms_provider_settings WHERE enabled = 1 AND is_default = 1 ORDER BY id ASC LIMIT 1"
        )
        row = cursor.fetchone()
        conn.close()
        return str(row[0]) if row and row[0] else None

    @staticmethod
    def save_provider_setting(
        provider: str,
        *,
        display_name: str | None = None,
        enabled: bool = True,
        is_default: bool = False,
        config: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        provider = (provider or "").strip().lower()
        if not provider:
            raise ValueError("provider 不能为空")

        now = datetime.now().isoformat(timespec="seconds")
        payload = {**SMS_SETTING_DEFAULTS, **dict(config or {})}

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, created_at FROM sms_provider_settings WHERE provider = ?", (provider,))
        existing = cursor.fetchone()

        if is_default:
            cursor.execute("UPDATE sms_provider_settings SET is_default = 0, updated_at = ?", (now,))

        if existing:
            setting_id, created_at = existing
            cursor.execute(
                """
                UPDATE sms_provider_settings
                SET display_name = ?, enabled = ?, is_default = ?, config_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (display_name or provider, int(bool(enabled)), int(bool(is_default)), json.dumps(payload, ensure_ascii=False), now, setting_id),
            )
        else:
            created_at = now
            cursor.execute(
                """
                INSERT INTO sms_provider_settings (provider, display_name, enabled, is_default, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (provider, display_name or provider, int(bool(enabled)), int(bool(is_default)), json.dumps(payload, ensure_ascii=False), created_at, now),
            )

        conn.commit()
        conn.close()
        return SMSProviderSettingsDB.get_provider_setting(provider)

init_database()