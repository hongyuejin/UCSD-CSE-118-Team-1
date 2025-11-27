import urllib.request
import json
import random

def generate_dummy_data(device_id="wrist_watch_A"):
    # Generate some dummy IMU data
    imu = []
    # Create a consistent strike pattern
    strike_pattern = [0.0, 0.5, 2.0, 5.0, 2.0, 0.5, 0.0] 
    
    for i in range(200): # 20 Hz for 10 seconds
        t = i * 50
        
        # Base gravity
        ax = 0.0
        ay = 0.0
        az = 9.8
        
        # Inject strikes every 20 samples (1 second)
        if i % 20 == 0:
            # Add pattern
            for j, val in enumerate(strike_pattern):
                if i + j < 200:
                    # Add to ax for simplicity
                    # For shinai, we want consistent strikes
                    if device_id == "wrist_watch_B":
                        ax += val
                    else:
                        # Wrist moves differently
                        ay += val * 0.5
        
        # Add small noise
        ax += random.random() * 0.1
        ay += random.random() * 0.1
        az += random.random() * 0.1
        
        gx = 0.1
        gy = 0.1
        gz = 0.1
        
        imu.append({"t": t, "ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz})

    payload = {
        "device_id": device_id,
        "imu": imu,
        "duration": 10,
        "imu_hz": 20
    }
    return payload

def upload_data(payload):
    url = "http://localhost:5000/end"
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        resp_json = json.loads(response.read().decode('utf-8'))
        return resp_json.get("session", {}).get("raw")

def test_dual_analysis():
    print("Uploading Wear Data...")
    wear_payload = generate_dummy_data("wrist_watch_A")
    wear_filename = upload_data(wear_payload)
    print(f"Wear Session: {wear_filename}")

    print("Uploading Shinai Data...")
    shinai_payload = generate_dummy_data("wrist_watch_B")
    shinai_filename = upload_data(shinai_payload)
    print(f"Shinai Session: {shinai_filename}")

    print("Requesting Dual Analysis...")
    url = "http://localhost:5000/analyze_dual"
    req_data = {
        "wear_session_id": wear_filename,
        "shinai_session_id": shinai_filename,
        "distance_inches": 30,
        "sword_weight_lbs": 1.1
    }
    
    data = json.dumps(req_data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        with urllib.request.urlopen(req) as response:
            print(f"Status Code: {response.getcode()}")
            print(f"Response: {response.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_dual_analysis()
