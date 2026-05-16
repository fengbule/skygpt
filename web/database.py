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
    
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)

class TaskDB:
    @staticmethod
    def create_task(email: str, name: str = None, birthday: str = None, proxy: str = None) -> Dict:
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now().isoformat(timespec="seconds")
        log_file = str(DATA_DIR / f"logs/task_{now.replace(':', '-')}.log")
        
        cursor.execute("""
            INSERT INTO registration_tasks (email, name, birthday, proxy, status, created_at, log_file)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """, (email, name, birthday, proxy, now, log_file))
        
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
            "log_file": log_file
        }
    
    @staticmethod
    def get_task(task_id: int) -> Optional[Dict]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registration_tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
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
                "log_file": row[12]
            }
        return None
    
    @staticmethod
    def update_task(task_id: int, **kwargs) -> bool:
        conn = get_connection()
        cursor = conn.cursor()
        
        valid_fields = ["status", "started_at", "completed_at", "error", "account_id", "access_token"]
        updates = {}
        for field, value in kwargs.items():
            if field in valid_fields:
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
            tasks.append({
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
                "log_file": row[12]
            })
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

init_database()