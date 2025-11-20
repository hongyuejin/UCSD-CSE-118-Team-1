import urllib.request
import json
import random
import time

def generate_dummy_data():
    # Generate some dummy heart rate data
    heart_rates = []
    for i in range(60):
        t = i * 1000
        bpm = 80 + (i % 40) * 2  # Varying BPM from 80 to 160
        heart_rates.append({"t": t, "bpm": bpm})

    # Generate some dummy IMU data with STRIKES
    imu = []
    strike_indices = [50, 150, 250, 350, 450] # Indices where strikes occur
    
    for i in range(600): # 10 Hz for 60 seconds
        t = i * 100
        
        # Base movement (low intensity)
        ax = 0.1 + random.random() * 0.5
        ay = 0.1 + random.random() * 0.5
        az = 0.8 + random.random() * 0.5 # Gravity mostly on Z
        
        # Inject strikes
        if i in strike_indices:
            # Simulate a strong strike (e.g., 4G)
            ax += 3.0
            ay += 2.0
            az += 2.0
            
        gx = random.random() * 0.1
        gy = random.random() * 0.1
        gz = random.random() * 0.1
        imu.append({"t": t, "ax": ax, "ay": ay, "az": az, "gx": gx, "gy": gy, "gz": gz})

    payload = {
        "heart_rates": heart_rates,
        "imu": imu,
        "duration": 60,
        "heart_rate_hz": 1,
        "imu_hz": 10
    }
    return payload

def test_server():
    url = "http://localhost:5000/end"
    payload = generate_dummy_data()
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    
    try:
        print("Sending data to server...")
        with urllib.request.urlopen(req) as response:
            print(f"Status Code: {response.getcode()}")
            print(f"Response: {response.read().decode('utf-8')}")
    except Exception as e:
        print(f"Error sending request: {e}")

if __name__ == "__main__":
    test_server()
