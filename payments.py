import aiohttp
import base64
from config import settings


class PayPalClient:
    def __init__(self):
        self.client_id = settings.PAYPAL_CLIENT_ID
        self.client_secret = settings.PAYPAL_SECRET
        self.base_url = (
            "https://api-m.sandbox.paypal.com"
            if settings.PAYPAL_MODE == "sandbox"
            else "https://api-m.paypal.com"
        )

    async def get_access_token(self) -> str:
        """Запрос access_token от PayPal"""
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={"Authorization": f"Basic {auth}"},
                data={"grant_type": "client_credentials"},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"PayPal token error {resp.status}: {text}")
                data = await resp.json()
                return data["access_token"]

    async def create_order(self, value: str, plan: str):
        """Создание ордера PayPal"""
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
                    "purchase_units": [
                        {"amount": {"currency_code": "USD", "value": value}}
                    ],
                    "application_context": {
                        "return_url": f"{settings.BASE_URL}/pay/return",
                        "cancel_url": f"{settings.BASE_URL}/pay/cancel",
                    },
                },
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise Exception(f"PayPal create_order error {resp.status}: {text}")
                return await resp.json()

    async def capture_order(self, order_id: str):
        """Завершение (capture) платежа"""
        token = await self.get_access_token()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v2/checkout/orders/{order_id}/capture",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            ) as resp:
                if resp.status not in (200, 201):
                    text = await resp.text()
                    raise Exception(f"PayPal capture_order error {resp.status}: {text}")
                return await resp.json()
