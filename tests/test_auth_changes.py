"""Regression tests for Rinnai HTTP authentication details."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "custom_components.rinnai"


class FakeResponse:
    """Minimal aiohttp response double."""

    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class FakeSession:
    """Capture HTTP requests made by the client."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []

    async def get(self, url, *, params=None, headers=None):
        self.calls.append(
            {"method": "GET", "url": url, "params": params, "headers": headers}
        )
        return FakeResponse(self._payloads.pop(0))

    async def post(self, url, *, data=None, headers=None):
        self.calls.append(
            {"method": "POST", "url": url, "params": data, "headers": headers}
        )
        return FakeResponse(self._payloads.pop(0))


def load_client_module():
    """Load client.py with only the Home Assistant pieces it imports."""
    custom_components = ModuleType("custom_components")
    custom_components.__path__ = [str(ROOT / "custom_components")]
    sys.modules["custom_components"] = custom_components

    rinnai_package = ModuleType(PACKAGE_NAME)
    rinnai_package.__path__ = [str(ROOT / "custom_components" / "rinnai")]
    sys.modules[PACKAGE_NAME] = rinnai_package

    homeassistant = ModuleType("homeassistant")
    homeassistant_core = ModuleType("homeassistant.core")
    homeassistant_core.HomeAssistant = object
    homeassistant_core.callback = lambda func: func
    homeassistant_helpers = ModuleType("homeassistant.helpers")
    aiohttp_client = ModuleType("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = lambda hass: hass.session
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = homeassistant_core
    sys.modules["homeassistant.helpers"] = homeassistant_helpers
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client

    aiohttp = ModuleType("aiohttp")
    aiohttp.ClientError = Exception
    sys.modules["aiohttp"] = aiohttp

    mqtt_client = ModuleType(f"{PACKAGE_NAME}.mqtt_client")

    class RinnaiMQTTClient:
        def __init__(self, *args, **kwargs):
            self.connected = False

    mqtt_client.RinnaiMQTTClient = RinnaiMQTTClient
    sys.modules[f"{PACKAGE_NAME}.mqtt_client"] = mqtt_client

    sys.modules.pop(f"{PACKAGE_NAME}.client", None)
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.client",
        ROOT / "custom_components" / "rinnai" / "client.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RinnaiAuthChangesTest(unittest.IsolatedAsyncioTestCase):
    async def test_login_uses_current_app_version(self):
        client_module = load_client_module()
        session = FakeSession([{"success": True, "data": {"token": "test-token"}}])
        client = client_module.RinnaiClient(SimpleNamespace(session=session), "u", "p")

        self.assertTrue(await client.login())

        # The API only accepts these credentials as GET query parameters.
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["params"]["appVersion"], "3.9.0")

    async def test_login_failure_clears_cached_token(self):
        """An expired token must not be reused for another 24 hours."""
        client_module = load_client_module()
        session = FakeSession([{"success": False, "msg": "token invalid"}])
        client = client_module.RinnaiClient(SimpleNamespace(session=session), "u", "p")
        client._token = "stale-token"

        self.assertFalse(await client.login())
        self.assertIsNone(client._token)
        self.assertEqual(client._last_login_time, 0)

    async def test_state_request_retries_once_after_auth_failure(self):
        """A rejected token triggers exactly one re-login and one retry."""
        client_module = load_client_module()
        session = FakeSession(
            [
                {"success": False, "code": 401, "msg": "token expired"},
                {"success": True, "data": {"token": "fresh-token"}},
                {"success": True, "data": {"heatingTempSetting": "3C"}},
            ]
        )
        client = client_module.RinnaiClient(SimpleNamespace(session=session), "u", "p")
        client._token = "stale-token"

        self.assertTrue(await client.fetch_device_state("device-1"))
        self.assertEqual(client._token, "fresh-token")
        # GET (rejected) -> GET login -> GET retry
        self.assertEqual(
            [call["method"] for call in session.calls],
            ["GET", "GET", "GET"],
        )

    async def test_protected_http_requests_use_basic_authorization(self):
        client_module = load_client_module()
        session = FakeSession(
            [
                {"success": True, "data": {"list": [{"id": "device-1"}]}},
                {"success": True, "data": {"heatingSwitch": "31"}},
            ]
        )
        client = client_module.RinnaiClient(SimpleNamespace(session=session), "u", "p")
        client._token = "test-token"

        self.assertTrue(await client.fetch_devices())
        self.assertTrue(await client.fetch_device_state("device-1"))

        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Basic test-token")
        self.assertEqual(session.calls[1]["headers"]["Authorization"], "Basic test-token")

    def test_manifest_version_matches_auth_fix_release(self):
        manifest_path = ROOT / "custom_components" / "rinnai" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "1.3.2")
