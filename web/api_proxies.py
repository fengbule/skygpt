# -*- coding: utf-8 -*-
"""
Proxy Management REST API
Handles proxy addition, testing, deletion, and subscription import
"""
import logging
import yaml
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify
from web.database import ProxyDB
from core.proxy_checker import check_proxy_availability

logger = logging.getLogger(__name__)
proxy_bp = Blueprint("proxies", __name__, url_prefix="/api/proxies")

@proxy_bp.route("/add", methods=["POST"])
def add_proxy():
    try:
        data = request.get_json()
        url = data.get("url")
        type_ = data.get("type", "manual")
        source = data.get("source", "manual")
        
        if not url:
            return jsonify({"error": "Proxy URL is required"}), 400
        
        proxy = ProxyDB.add_proxy(url=url, type=type_, source=source)
        
        if not proxy:
            return jsonify({"error": "Proxy already exists"}), 400
        
        logger.info(f"Added proxy: {url}")
        
        available, latency, message = check_proxy_availability(url)
        ProxyDB.update_proxy(proxy["id"], available=available, latency=latency)
        
        return jsonify({
            "success": True,
            "proxy": proxy,
            "available": available,
            "latency": latency,
            "message": message
        }), 200
    except Exception as e:
        logger.error(f"Error adding proxy: {str(e)}")
        return jsonify({"error": str(e)}), 500

@proxy_bp.route("/<int:proxy_id>/test", methods=["POST"])
def test_proxy(proxy_id):
    try:
        proxy = ProxyDB.get_proxy(proxy_id)
        if not proxy:
            return jsonify({"error": "Proxy not found"}), 404
        
        available, latency, message = check_proxy_availability(proxy["url"])
        ProxyDB.update_proxy(proxy_id, available=available, latency=latency)
        
        logger.info(f"Tested proxy {proxy_id}: available={available}, latency={latency}")
        
        return jsonify({
            "success": True,
            "proxy_id": proxy_id,
            "available": available,
            "latency": latency,
            "message": message
        }), 200
    except Exception as e:
        logger.error(f"Error testing proxy {proxy_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@proxy_bp.route("/test_all", methods=["POST"])
def test_all_proxies():
    try:
        proxies = ProxyDB.list_proxies()
        results = []
        
        for proxy in proxies:
            available, latency, message = check_proxy_availability(proxy["url"])
            ProxyDB.update_proxy(proxy["id"], available=available, latency=latency)
            results.append({
                "proxy_id": proxy["id"],
                "url": proxy["url"],
                "available": available,
                "latency": latency,
                "message": message
            })
        
        logger.info(f"Tested {len(proxies)} proxies")
        
        return jsonify({
            "success": True,
            "results": results,
            "count": len(results)
        }), 200
    except Exception as e:
        logger.error(f"Error testing all proxies: {str(e)}")
        return jsonify({"error": str(e)}), 500

@proxy_bp.route("/import_subscription", methods=["POST"])
def import_subscription():
    try:
        data = request.get_json()
        sub_url = data.get("url")
        
        if not sub_url:
            return jsonify({"error": "Subscription URL is required"}), 400
        
        response = requests.get(sub_url, timeout=10)
        content = response.text
        
        proxies_added = []
        
        try:
            config = yaml.safe_load(content)
            if "proxies" in config:
                for proxy_node in config["proxies"]:
                    node_name = proxy_node.get("name", "Unnamed")
                    server = proxy_node.get("server")
                    port = proxy_node.get("port")
                    proxy_type = proxy_node.get("type", "socks5")
                    password = proxy_node.get("password", "")
                    username = proxy_node.get("username", "")
                    
                    if server and port:
                        if username and password:
                            url = f"{proxy_type}://{username}:{password}@{server}:{port}"
                        else:
                            url = f"{proxy_type}://{server}:{port}"
                        
                        proxy = ProxyDB.add_proxy(url=url, type=proxy_type, source="subscription")
                        if proxy:
                            proxies_added.append({
                                "id": proxy["id"],
                                "url": url,
                                "name": node_name
                            })
                            available, latency, message = check_proxy_availability(url)
                            ProxyDB.update_proxy(proxy["id"], available=available, latency=latency)
        except yaml.YAMLError:
            return jsonify({"error": "Failed to parse subscription content"}), 400
        
        logger.info(f"Imported {len(proxies_added)} proxies from subscription")
        
        return jsonify({
            "success": True,
            "proxies_added": proxies_added,
            "count": len(proxies_added),
            "message": f"Successfully imported {len(proxies_added)} proxies"
        }), 200
    except Exception as e:
        logger.error(f"Error importing subscription: {str(e)}")
        return jsonify({"error": str(e)}), 500

@proxy_bp.route("/list", methods=["GET"])
def list_proxies():
    try:
        source = request.args.get("source")
        proxies = ProxyDB.list_proxies(source=source)
        
        return jsonify({
            "proxies": proxies,
            "count": len(proxies)
        }), 200
    except Exception as e:
        logger.error(f"Error listing proxies: {str(e)}")
        return jsonify({"error": str(e)}), 500

@proxy_bp.route("/<int:proxy_id>", methods=["DELETE"])
def delete_proxy(proxy_id):
    try:
        ProxyDB.delete_proxy(proxy_id)
        logger.info(f"Deleted proxy {proxy_id}")
        
        return jsonify({
            "success": True,
            "message": "Proxy deleted successfully"
        }), 200
    except Exception as e:
        logger.error(f"Error deleting proxy {proxy_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500