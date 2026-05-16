# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import web.database as web_database


class SkyGPTSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._orig_data_dir = web_database.DATA_DIR
        cls._orig_db_path = web_database.DB_PATH
        cls._tmpdir = tempfile.TemporaryDirectory()
        web_database.DATA_DIR = Path(cls._tmpdir.name)
        web_database.DB_PATH = web_database.DATA_DIR / "test_skygpt.db"
        web_database.init_database()

        from web.app import app

        cls.app = app
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        web_database.DATA_DIR = cls._orig_data_dir
        web_database.DB_PATH = cls._orig_db_path
        cls._tmpdir.cleanup()

    def setUp(self):
        conn = web_database.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sms_provider_settings")
        cursor.execute("DELETE FROM registration_tasks")
        conn.commit()
        conn.close()

    def test_save_and_load_sms_provider_settings(self):
        response = self.client.put(
            "/api/settings/sms/hero_sms",
            json={
                "display_name": "HeroSMS",
                "enabled": True,
                "is_default": True,
                "config": {
                    "api_key": "secret-key",
                    "default_country": "151",
                    "default_service": "dr",
                    "auto_select_best_country": True,
                    "best_country_min_stock": 30,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["item"]["provider"], "hero_sms")
        self.assertTrue(data["item"]["is_default"])
        self.assertEqual(data["item"]["config"]["default_country"], "151")
        self.assertTrue(data["item"]["config"]["auto_select_best_country"])

        get_response = self.client.get("/api/settings/sms/default")
        self.assertEqual(get_response.status_code, 200)
        get_data = get_response.get_json()
        self.assertEqual(get_data["item"]["provider"], "hero_sms")
        self.assertEqual(get_data["item"]["config"]["default_service"], "dr")

    @patch("web.api_settings.get_balance")
    def test_test_sms_provider_route(self, mock_get_balance):
        mock_get_balance.return_value = {"status": "ACCESS_BALANCE", "balance": 12.34}
        response = self.client.post(
            "/api/settings/sms/hero_sms/test",
            json={
                "config": {
                    "api_key": "test-key",
                    "base_url": "https://example.invalid/api",
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["result"]["balance"], 12.34)

    @patch("web.api_tasks.RegistrationManager.get_instance")
    def test_create_phone_task_uses_saved_default_provider(self, mock_get_instance):
        manager = MagicMock()
        mock_get_instance.return_value = manager

        save_resp = self.client.put(
            "/api/settings/sms/sms_activate",
            json={
                "display_name": "SMS-Activate",
                "enabled": True,
                "is_default": True,
                "config": {
                    "default_service": "dr",
                    "default_country": "151",
                },
            },
        )
        self.assertEqual(save_resp.status_code, 200)

        response = self.client.post(
            "/api/tasks/create",
            json={
                "registration_mode": "phone",
                "email": "",
                "birthday": "2000-01-01",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["task"]["sms_provider"], "sms_activate")
        manager.start_task.assert_called_once()
        self.assertEqual(manager.start_task.call_args.kwargs["sms_provider"], "sms_activate")

    @patch("core.sms_provider.HeroSMSClient")
    def test_auto_select_best_country_overrides_default_country(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get_best_country.return_value = {"country": "151", "price": 0.1, "count": 99}
        mock_client.get_number.return_value = {
            "activation_id": "1001",
            "phone_number": "+56999999999",
            "status": "ACCESS_NUMBER",
        }
        mock_client.set_status.return_value = {"status": "ACCESS_READY", "success": True}

        from core.sms_provider import SMSActivateCompatibleProvider

        provider = SMSActivateCompatibleProvider(
            settings={
                "provider": "hero_sms",
                "default_country": "0",
                "default_service": "dr",
                "auto_select_best_country": True,
                "best_country_min_stock": 20,
                "best_country_max_price": 0,
            },
            provider_name="hero_sms",
        )
        provider.acquire_phone_number(country=None, service="dr")

        self.assertEqual(mock_client.get_number.call_args.kwargs["country"], "151")


if __name__ == "__main__":
    unittest.main()