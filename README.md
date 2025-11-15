## Data Upload: `sendHttpRequestEnd`

When you tap the **red STOP button** on the watch, the app calls:

```kotlin
suspend fun sendHttpRequestEnd(
    heartRates: List<Int>,
    rotations: List<RotationVectorSample>,
    imu: List<ImuSample>,
    duration: Int
)
```

This sends a POST request to:
```POST $URL/end
Content-Type: application/json; charset=utf-8
```

## JSON Body Format
```json
{
  "heart_rates": [94, 95, 95, 94],
  "rotation_vectors": [
    { "x": 0.04314, "y": -0.132579, "z": -0.46504, "w": 0.874242 },
    { "x": 0.044147, "y": -0.133233, "z": -0.465508, "w": 0.873843 },
    { "x": 0.044869, "y": -0.133211, "z": -0.464318, "w": 0.874442 },
    ...
  ],
  "imu": [
    {
      "t": 160,
      "ax": 1.8962077,
      "ay": 1.9321208,
      "az": 9.306262,
      "gx": 0.04520403,
      "gy": -0.013439035,
      "gz": 0.014660766
    },
    {
      "t": 215,
      "ax": 1.8483237,
      "ay": 2.006341,
      "az": 9.313444,
      "gx": 0.012217305,
      "gy": 0.0036651916,
      "gz": -0.02443461
    },
    ...
  ],
  "duration": 2
}
```

## Fields

* `heart_rates`

Array of integer heart-rate readings in bpm, sampled at HEART_RATE_HZ.

* `rotation_vectors`

Array of orientation samples from the Android rotation-vector sensor, stored as quaternions:

x, y, z, w: float components of the rotation vector.

* `imu`

Array of IMU samples combining accelerometer + gyroscope:

t: timestamp in milliseconds since recording started.

ax, ay, az: linear acceleration (m/s²) along x/y/z.

gx, gy, gz: angular velocity (rad/s) around x/y/z.


* `duration`

Total recording time in seconds, computed from wall-clock time.

## Configuration Constants

```kotlin
const val URL = "http://192.168.0.107:5000" // Change to your server's IP/port
const val HEART_RATE_HZ = 2                 // Heart-rate samples per second
const val IMU_HZ = 20                       // IMU + rotation-vector samples per second
```
