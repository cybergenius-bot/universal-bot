import aiohttp
import base64
from config import settings


class PayPalClient:
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
      self.client_secret = settings.PAYPAL_SECRET
        self.base_url = "https://api-m.sandbox.paypal.com"  # ⚠️ для тестов Sandbox
        # self.base_url = "https://api-m.paypal.com"        # прод

    async def get_access_token(self):
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={"Authorization": f"Basic {auth}"},
                data={"grant_type": "client_credentials"}
            ) as resp:
                data = await resp.json()
                return data["access_token"]

    async def create_order(self, value: str, plan: str):
        token = await self.get_access_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{"amount": {"currency_code": "USD", "value": value}}],
                    "application_context": {
                        "return_url": f"{settings.BASE_URL}/pay/return",
                        "cancel_url": f"{settings.BASE_URL}/pay/cancel"
                    }
                }
            ) as resp:
                return await resp.json()

    async def capture_order(self, order_id: str):
        token = await self.get_access_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
            ) as resp:
                return await resp.json()
