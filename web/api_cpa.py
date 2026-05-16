# -*- coding: utf-8 -*-
"""
CPA File Management REST API
Handles CPA file generation, download, and batch export
"""
import json
import logging
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, send_from_directory
from web.database import AccountDB

logger = logging.getLogger(__name__)
cpa_bp = Blueprint("cpa", __name__, url_prefix="/api/cpa")

CPA_DIR = Path(__file__).parent.parent / "cpa_files"

@cpa_bp.route("/list", methods=["GET"])
def list_cpa_files():
    try:
        accounts = AccountDB.list_accounts()
        
        cpa_files = []
        for account in accounts:
            cpa_file_path = CPA_DIR / account["cpa_file"] if account["cpa_file"] else None
            
            if cpa_file_path and cpa_file_path.exists():
                with open(cpa_file_path, "r") as f:
                    cpa_data = json.load(f)
                
                cpa_files.append({
                    "id": account["id"],
                    "email": account["email"],
                    "account_id": account["account_id"],
                    "expired": account["expired"],
                    "created_at": account["created_at"],
                    "cpa_file": account["cpa_file"],
                    "disabled": account["disabled"],
                    "file_exists": True,
                    "data": cpa_data
                })
            else:
                cpa_files.append({
                    "id": account["id"],
                    "email": account["email"],
                    "account_id": account["account_id"],
                    "expired": account["expired"],
                    "created_at": account["created_at"],
                    "cpa_file": account["cpa_file"],
                    "disabled": account["disabled"],
                    "file_exists": False
                })
        
        return jsonify({
            "cpa_files": cpa_files,
            "count": len(cpa_files)
        }), 200
    except Exception as e:
        logger.error(f"Error listing CPA files: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cpa_bp.route("/download/<filename>", methods=["GET"])
def download_cpa_file(filename):
    try:
        cpa_file_path = CPA_DIR / filename
        
        if not cpa_file_path.exists():
            return jsonify({"error": "CPA file not found"}), 404
        
        return send_file(
            cpa_file_path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/json"
        )
    except Exception as e:
        logger.error(f"Error downloading CPA file {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cpa_bp.route("/download_batch", methods=["POST"])
def download_batch_cpa_files():
    try:
        data = request.get_json()
        emails = data.get("emails", [])
        
        if not emails:
            accounts = AccountDB.list_accounts()
            emails = [acc["email"] for acc in accounts]
        
        if not emails:
            return jsonify({"error": "No CPA files to download"}), 400
        
        temp_dir = tempfile.mkdtemp()
        zip_path = Path(temp_dir) / f"cpa_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for email in emails:
                account = AccountDB.get_account(email)
                if account and account["cpa_file"]:
                    cpa_file_path = CPA_DIR / account["cpa_file"]
                    if cpa_file_path.exists():
                        zipf.write(cpa_file_path, account["cpa_file"])
        
        logger.info(f"Created batch ZIP with {len(emails)} CPA files")
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_path.name,
            mimetype="application/zip"
        )
    except Exception as e:
        logger.error(f"Error creating batch ZIP: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cpa_bp.route("/disable/<email>", methods=["POST"])
def disable_account(email):
    try:
        conn = AccountDB.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE accounts SET disabled = 1 WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        
        logger.info(f"Disabled account {email}")
        
        return jsonify({
            "success": True,
            "message": f"Account {email} disabled successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error disabling account {email}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@cpa_bp.route("/enable/<email>", methods=["POST"])
def enable_account(email):
    try:
        conn = AccountDB.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE accounts SET disabled = 0 WHERE email = ?", (email,))
        conn.commit()
        conn.close()
        
        logger.info(f"Enabled account {email}")
        
        return jsonify({
            "success": True,
            "message": f"Account {email} enabled successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error enabling account {email}: {str(e)}")
        return jsonify({"error": str(e)}), 500