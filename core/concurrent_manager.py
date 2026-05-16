# -*- coding: utf-8 -*-
"""
Concurrent Registration Manager
Manages multiple concurrent registration tasks with independent proxy configuration
"""
import logging
import threading
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from web.database import TaskDB
from core.pausable_registration import RegistrationManager

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = 10

class ConcurrentRegistrationManager:
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, max_workers: int = MAX_CONCURRENT_TASKS):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.active_tasks: Dict[int, threading.Event] = {}
        self.socketio = None
        self.max_workers = max_workers
    
    @classmethod
    def get_instance(cls, max_workers: int = MAX_CONCURRENT_TASKS):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_workers)
        return cls._instance
    
    def set_socketio(self, socketio):
        self.socketio = socketio
        RegistrationManager.get_instance().set_socketio(socketio)
    
    def start_batch_registration(self, emails: List[str], proxies: List[str] = None, names: List[str] = None, birthdays: List[str] = None) -> List[Dict]:
        tasks = []
        
        for i, email in enumerate(emails):
            proxy = proxies[i] if proxies and i < len(proxies) else None
            name = names[i] if names and i < len(names) else None
            birthday = birthdays[i] if birthdays and i < len(birthdays) else "2000-01-01"
            
            task_data = TaskDB.create_task(email=email, name=name, birthday=birthday, proxy=proxy)
            tasks.append(task_data)
            
            reg_manager = RegistrationManager.get_instance()
            reg_manager.start_task(task_data["id"], email, name, birthday, proxy)
        
        logger.info(f"Started batch registration with {len(tasks)} tasks")
        
        return tasks
    
    def start_single_registration(self, email: str, proxy: str = None, name: str = None, birthday: str = "2000-01-01") -> Dict:
        task_data = TaskDB.create_task(email=email, name=name, birthday=birthday, proxy=proxy)
        
        reg_manager = RegistrationManager.get_instance()
        reg_manager.start_task(task_data["id"], email, name, birthday, proxy)
        
        logger.info(f"Started single registration for {email} with task ID {task_data['id']}")
        
        return task_data
    
    def get_active_tasks_count(self) -> int:
        return len([t for t in TaskDB.list_tasks() if t["status"] in ["pending", "running"]])
    
    def get_all_tasks_status(self) -> List[Dict]:
        return TaskDB.list_tasks()
    
    def cancel_all_pending_tasks(self) -> int:
        tasks = TaskDB.list_tasks(status="pending")
        cancelled_count = 0
        
        for task in tasks:
            reg_manager = RegistrationManager.get_instance()
            if reg_manager.cancel_task(task["id"]):
                cancelled_count += 1
        
        logger.info(f"Cancelled {cancelled_count} pending tasks")
        
        return cancelled_count
    
    def shutdown(self):
        self.executor.shutdown(wait=False)
        logger.info("Concurrent registration manager shutdown")

def get_manager():
    return ConcurrentRegistrationManager.get_instance()