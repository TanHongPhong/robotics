import requests
import json

# Test API endpoints
BASE_URL = "http://localhost:5001"

print("Testing Arduino API...")
print("="*50)

# Test Home
print("\n1. Testing HOME command...")
try:
    response = requests.post(
        f"{BASE_URL}/api/arduino/command",
        json={"command": "home"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

# Test Start
print("\n2. Testing START command with class_ids...")
try:
    response = requests.post(
        f"{BASE_URL}/api/arduino/command",
        json={"command": "start", "class_ids": [0, 1, 2]}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

# Test Stop
print("\n3. Testing STOP command...")
try:
    response = requests.post(
        f"{BASE_URL}/api/arduino/command",
        json={"command": "stop"}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "="*50)
print("Testing complete!")
