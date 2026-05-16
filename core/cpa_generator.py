# -*- coding: utf-8 -*-
"""
CPA File Generator Module
Generates CPA (CLIProxyAPI) authentication files
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict

logger = logging.getLogger(__name__)

CPA_DIR = Path(__file__).parent.parent / "cpa_files"

def generate_cpa_file(account_data: Dict, email: str) -> Dict:
    """
    Generate CPA authentication file for CLIProxyAPI.
    
    Args:
        account_data: Account information including tokens
        email: Account email
        
    Returns:
        CPA file data
    """
    CPA_DIR.mkdir(parents=True, exist_ok=True)
    
    access_token = account_data.get("access_token", "")
    account_id = account_data.get("account_id", "")
    
    refresh_token = account_data.get("refresh_token", "")
    id_token = account_data.get("id_token", "")
    
    expired_time = calculate_expired_time(access_token)
    
    cpa_data = {
        "access_token": access_token,
        "account_id": account_id,
        "disabled": False,
        "email": email,
        "expired": expired_time,
        "id_token": id_token,
        "last_refresh": datetime.now().isoformat(timespec="seconds"),
        "refresh_token": refresh_token,
        "type": "codex"
    }
    
    filename = f"{email.replace('@', '_at_')}_cpa.json"
    file_path = CPA_DIR / filename
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(cpa_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Generated CPA file for {email}: {filename}")
    
    cpa_data["cpa_file"] = filename
    
    return cpa_data

def calculate_expired_time(access_token: str) -> str:
    """
    Calculate expiration time from access token.
    
    Args:
        access_token: JWT access token
        
    Returns:
        Expiration time in ISO format
    """
    try:
        if access_token and "." in access_token:
            parts = access_token.split(".")
            if len(parts) >= 2:
                import base64
                payload_b64 = parts[1] + "=="
                payload_json = base64.b64decode(payload_b64).decode("utf-8")
                payload = json.loads(payload_json)
                
                if "exp" in payload:
                    exp_timestamp = payload["exp"]
                    expired_dt = datetime.fromtimestamp(exp_timestamp)
                    return expired_dt.isoformat(timespec="seconds")
    except Exception as e:
        logger.warning(f"Failed to parse token expiration: {str(e)[:100]}")
    
    default_expired = datetime.now() + timedelta(days=30)
    return default_expired.isoformat(timespec="seconds")

def update_cpa_file(email: str, updates: Dict) -> bool:
    """
    Update existing CPA file.
    
    Args:
        email: Account email
        updates: Fields to update
        
    Returns:
        True if successful, False otherwise
    """
    try:
        filename = f"{email.replace('@', '_at_')}_cpa.json"
        file_path = CPA_DIR / filename
        
        if not file_path.exists():
            logger.warning(f"CPA file not found for {email}")
            return False
        
        with open(file_path, "r", encoding="utf-8") as f:
            cpa_data = json.load(f)
        
        for key, value in updates.items():
            cpa_data[key] = value
        
        cpa_data["last_refresh"] = datetime.now().isoformat(timespec="seconds")
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cpa_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Updated CPA file for {email}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to update CPA file for {email}: {str(e)}")
        return False