# Secondary Shinai IMU Tracker (IMU Only)

This app records continuous Accelerometer and Gyroscope data for placing at the tip of the shinai and uploads it to a server.

## Data Upload: `sendDataToServer`

When you tap the **red STOP button** on the watch, the app sends a POST request to:

```
$URL/end
Content-Type: application/json; charset=utf-8
```

## JSON Body Format

```json
{
  "device_id": "wrist_watch_B",
  "data_type": "imu_only",
  "imu_hz": 20.0,
  "sample_count": 300,
  "imu": [
    {
      "t": 1677981234567,
      "ax": 0.12,
      "ay": 9.81,
      "az": 0.05,
      "gx": 0.01,
      "gy": -0.02,
      "gz": 0.00
    },
    ...
  ]
}
```

## Fields

* `device_id`
  Identifier for the source device (fixed as "wrist_watch_B").

* `data_type`
  Type of data payload (fixed as IMU only).

* `imu_hz`
  The sampling rate in Hz (20 Hz).

* `sample_count`
  Total number of IMU samples in the payload.

* `imu`
  Array of IMU samples:
    * `t`: Epoch timestamp in milliseconds (System.currentTimeMillis), System.currentTimeMillis() returns the number of milliseconds since Jan 1, 1970 UTC.
    * `ax`, `ay`, `az`: Linear acceleration (m/s²).
    * `gx`, `gy`, `gz`: Angular velocity (rad/s).

## Configuration Constants

```kotlin
const val URL = "http://192.168.0.232:5000" // change to your server endpoint
const val IMU_HZ = 20f                      // change to the desired sampling rate in Hz
```