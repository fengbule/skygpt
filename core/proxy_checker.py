# -*- coding: utf-8 -*-
"""
Proxy Checker Module
Tests proxy availability and latency
"""
import time
import logging
from typing import Tuple
from curl_cffi.requests import Session

logger = logging.getLogger(__name__)

def check_proxy_availability(proxy_url: str) -> Tuple[int, float, str]:
    """
    Check if a proxy is available and measure latency.
    
    Args:
        proxy_url: Proxy URL in format socks5://user:pass@host:port
        
    Returns:
        Tuple of (available: int, latency: float, message: str)
        available: 1 if available, 0 if not
        latency: Response time in seconds
        message: Status message
    """
    try:
        test_url = "https://chatgpt.com"
        timeout = 10
        
        session = Session(impersonate="chrome110")
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        session.timeout = timeout
        
        start_time = time.time()
        response = session.get(test_url, timeout=timeout)
        latency = time.time() - start_time
        
        if response.status_code == 200:
            logger.info(f"Proxy {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url} is available, latency: {latency:.2f}s")
            return (1, latency, "Proxy is available")
        else:
            logger.warning(f"Proxy returned status code {response.status_code}")
            return (0, 0.0, f"Proxy returned error: {response.status_code}")
    
    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Proxy test failed: {error_msg}")
        return (0, 0.0, f"Proxy connection failed: {error_msg}")

def test_proxy_with_auth(proxy_url: str) -> Tuple[int, float, str]:
    """
    Test proxy with authentication support.
    
    Args:
        proxy_url: Proxy URL including credentials
        
    Returns:
        Same as check_proxy_availability
    """
    return check_proxy_availability(proxy_url)