## Data Upload: `sendHttpRequestEnd`

When you tap the **red STOP button** on the watch, the app calls:

```kotlin
suspend fun sendHttpRequestEnd(
    heartRates: List<HeartRateSample>,
    rotations: List<RotationVectorSample>,
    imu: List<ImuSample>,
    duration: Int,
    strikeCount: Int
)
```

This sends a POST request to:
```POST $URL/end
Content-Type: application/json; charset=utf-8
```

## JSON Body Format
```json
{
  "heart_rates": [
    { "t": 1677981234500, "bpm": 94 },
    { "t": 1677981235500, "bpm": 95 },
    ...
  ],
  "rotation_vectors": [
    { "t": 1677981234510, "x": 0.043, "y": -0.132, "z": -0.465, "w": 0.874 },
    ...
  ],
  "imu": [
    {
      "t": 1677981234510,
      "ax": 1.89, "ay": 1.93, "az": 9.30,
      "gx": 0.04, "gy": -0.01, "gz": 0.01
    },
    ...
  ],
  "duration": 12,
  "strike_count": 15,
  "heart_rate_hz": 0.1,
  "imu_hz": 20
}
```

## Fields

* `heart_rates`

Array of heart-rate samples.

t: Epoch timestamp in milliseconds (System.currentTimeMillis).

bpm: Heart rate in beats per minute.

* `rotation_vectors`

Array of orientation samples.

t: Epoch timestamp in milliseconds.

x, y, z, w: Rotation vector components (quaternion).

* `imu`

Array of IMU samples combining accelerometer + gyroscope:

t: Epoch timestamp in milliseconds.

ax, ay, az: linear acceleration (m/s²) along x/y/z.

gx, gy, gz: angular velocity (rad/s) around x/y/z.

* `duration`

Total recording time in seconds.

* `strike_count`

Total number of strikes detected on the device.

* `heart_rate_hz`

The sampling rate for heart rate in Hz.

* `imu_hz`

The sampling rate for IMU and rotation vector in Hz.

## Configuration Constants

```kotlin
const val URL = "http://192.168.0.107:5000" // Change to your server's IP/port
const val HEART_RATE_HZ = 2                 // Heart-rate samples per second
const val IMU_HZ = 20                       // IMU + rotation-vector samples per second
```