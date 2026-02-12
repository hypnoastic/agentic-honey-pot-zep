
import asyncio
import websockets
import requests
import sys

TARGET_URL = "ws://127.0.0.1:8000/api/ws/logs"
TARGET_HTTP = "http://127.0.0.1:8000/api/ws/logs"

async def test_websocket():
    print(f"Testing WebSocket connection to {TARGET_URL}...")
    try:
        async with websockets.connect(TARGET_URL) as websocket:
            print("✅ WebSocket connection SUCCESS!")
            print("Waiting for data...")
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"✅ Received data: {msg}")
            except asyncio.TimeoutError:
                print("⚠️ Connected but no data received (timeout).")
    except Exception as e:
        print(f"❌ WebSocket connection FAILED: {e}")

def test_http():
    print(f"\nTesting HTTP GET to {TARGET_HTTP}...")
    try:
        response = requests.get(TARGET_HTTP)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        print(f"Content: {response.text[:100]}...")
        if response.status_code == 404:
             print("❌ 404 Not Found - Server rejected path.")
        elif response.status_code == 426:
             print("✅ 426 Upgrade Required - Server recognized path but requires WebSocket.")
        else:
             print(f"⚠️ Unexpected status: {response.status_code}")

    except Exception as e:
        print(f"❌ HTTP Request FAILED: {e}")

if __name__ == "__main__":
    print("--- DIAGNOSTIC START ---")
    test_http()
    asyncio.run(test_websocket())
    print("--- DIAGNOSTIC END ---")
