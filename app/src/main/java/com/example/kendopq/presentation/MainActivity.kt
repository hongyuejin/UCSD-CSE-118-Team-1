/* While this template provides a good starting point for using Wear Compose, you can always
 * take a look at https://github.com/android/wear-os-samples/tree/main/ComposeStarter to find the
 * most up to date changes to the libraries and their usages.
 */

package com.example.kendopq.presentation

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import androidx.wear.compose.material.TimeText
import com.example.kendopq.presentation.theme.KendoPQTheme
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.remember
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape

// Compose state & effects
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.rememberCoroutineScope

// Layout & size
import androidx.compose.foundation.layout.height

// Colors & button
import androidx.compose.ui.graphics.Color
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.ButtonDefaults

// Coroutines
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay

import androidx.compose.foundation.layout.Spacer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

import okhttp3.OkHttpClient
import okhttp3.Request

// For the heart rate list
import androidx.compose.runtime.mutableStateListOf

// For JSON
import org.json.JSONArray
import org.json.JSONObject

// For JSON request body with OkHttp
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

// New Android imports
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.util.Log

import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

// Compose state types
import androidx.compose.runtime.State
import android.os.SystemClock
import androidx.compose.runtime.mutableLongStateOf
import java.io.IOException
import java.util.Locale

// Logging if you want (optional)
// import android.util.Log

// ----------------------
// Data models & constants
// ----------------------

const val URL = "http://192.168.1.119:5000" // Change to the Server's IP
const val HEART_RATE_HZ = 0.1 // 6 times per min
const val IMU_HZ = 20      // shared for rotation + accel + gyro

data class HeartRateSample(val t: Long, val bpm: Int)

data class ImuSample(
    val t: Long,     // timestamp since start (ms)
    val ax: Float,
    val ay: Float,
    val az: Float,
    val gx: Float,
    val gy: Float,
    val gz: Float
)

data class RotationVectorSample(
    val x: Float,
    val y: Float,
    val z: Float,
    val w: Float
)

// ----------------------
// Activity + Sensors
// ----------------------

class MainActivity : ComponentActivity(), SensorEventListener {

    companion object {
        private const val BODY_SENSORS_REQUEST_CODE = 1001
    }

    private lateinit var sensorManager: SensorManager
    private var heartRateSensor: Sensor? = null
    private var rotationVectorSensor: Sensor? = null
    private var accelSensor: Sensor? = null
    private var gyroSensor: Sensor? = null

    // Compose state updated from sensors
    private val heartRateState = mutableIntStateOf(0)
    private val rotationVectorState = mutableStateOf(
        RotationVectorSample(0f, 0f, 0f, 1f)
    )
    private val accelState = mutableStateOf(Triple(0f, 0f, 0f))
    private val gyroState = mutableStateOf(Triple(0f, 0f, 0f))

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)

        setTheme(android.R.style.Theme_DeviceDefault)

        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        heartRateSensor = sensorManager.getDefaultSensor(Sensor.TYPE_HEART_RATE)
        rotationVectorSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        accelSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        gyroSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        checkHeartRatePermission()

        setContent {
            WearApp(
                heartRateState = heartRateState,
                rotationVectorState = rotationVectorState,
                accelState = accelState,
                gyroState = gyroState
            )
        }
    }

    private fun checkHeartRatePermission() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BODY_SENSORS
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.BODY_SENSORS),
                BODY_SENSORS_REQUEST_CODE
            )
        }
        // If already granted, we'll start the sensors in onResume()
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == BODY_SENSORS_REQUEST_CODE &&
            grantResults.isNotEmpty() &&
            grantResults[0] == PackageManager.PERMISSION_GRANTED
        ) {
            startSensors()
        }
    }

    private fun startSensors() {
        heartRateSensor?.let { sensor ->
            sensorManager.registerListener(
                this,
                sensor,
                SensorManager.SENSOR_DELAY_NORMAL
            )
        }
        rotationVectorSensor?.let { sensor ->
            sensorManager.registerListener(
                this,
                sensor,
                SensorManager.SENSOR_DELAY_GAME
            )
        }
        accelSensor?.let { sensor ->
            sensorManager.registerListener(
                this,
                sensor,
                SensorManager.SENSOR_DELAY_GAME
            )
        }
        gyroSensor?.let { sensor ->
            sensorManager.registerListener(
                this,
                sensor,
                SensorManager.SENSOR_DELAY_GAME
            )
        }
    }

    override fun onResume() {
        super.onResume()
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.BODY_SENSORS
            ) == PackageManager.PERMISSION_GRANTED
        ) {
            startSensors()
        }
    }

    override fun onPause() {
        super.onPause()
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        val e = event ?: return
        when (e.sensor.type) {
            Sensor.TYPE_HEART_RATE -> {
                val bpm = e.values.firstOrNull()?.toInt() ?: return
                heartRateState.intValue = bpm
            }
            Sensor.TYPE_ROTATION_VECTOR -> {
                val v = e.values
                if (v.size >= 3) {
                    val x = v[0]
                    val y = v[1]
                    val z = v[2]
                    val w = if (v.size >= 4) v[3] else 0f
                    rotationVectorState.value = RotationVectorSample(x, y, z, w)
                }
            }
            Sensor.TYPE_ACCELEROMETER -> {
                val v = e.values
                if (v.size >= 3) {
                    accelState.value = Triple(v[0], v[1], v[2])
                }
            }
            Sensor.TYPE_GYROSCOPE -> {
                val v = e.values
                if (v.size >= 3) {
                    gyroState.value = Triple(v[0], v[1], v[2])
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // Not used
    }
}



//@OptIn(ExperimentalFoundationApi::class)
//@Composable
//fun WearApp(greetingName: String) {
//    KendoPQTheme {
//        val pagerState = rememberPagerState(pageCount = { 2 })
//        Box(
//            modifier = Modifier
//                .fillMaxSize()
//                .background(MaterialTheme.colors.background),
//        ) {
//            HorizontalPager(
//                state = pagerState,
//                modifier = Modifier.fillMaxSize()
//            ) { page ->
//                when (page) {
//                    0 -> Page1(greetingName = greetingName)
//                    1 -> Page2()
//                }
//            }
//            TimeText(modifier = Modifier.align(Alignment.TopCenter))
//        }
//    }
//}

// ----------------------
// UI
// ----------------------

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun WearApp(
    heartRateState: State<Int>,
    rotationVectorState: State<RotationVectorSample>,
    accelState: State<Triple<Float, Float, Float>>,
    gyroState: State<Triple<Float, Float, Float>>
) {
    KendoPQTheme {
        val pageCount = 2
        val pagerState = rememberPagerState(pageCount = { pageCount })

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colors.background),
        ) {
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.fillMaxSize()
            ) { page ->
                when (page) {
                    0 -> Page1(heartRateState, rotationVectorState, accelState, gyroState)
                    1 -> Page2()
                }
            }

            TimeText(modifier = Modifier.align(Alignment.TopCenter))

            Row(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(bottom = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                repeat(pageCount) { index ->
                    val isSelected = pagerState.currentPage == index
                    Box(
                        modifier = Modifier
                            .size(10.dp)
                            .background(
                                color = if (isSelected) Color.White else Color.DarkGray,
                                shape = CircleShape
                            )
                    )
                }
            }
        }
    }
}

@Composable
fun Page1(
    heartRateState: State<Int>,
    rotationVectorState: State<RotationVectorSample>,
    accelState: State<Triple<Float, Float, Float>>,
    gyroState: State<Triple<Float, Float, Float>>
) {
    var isRunning by remember { mutableStateOf(false) }

    // For display + duration
    var elapsedSeconds by remember { mutableIntStateOf(0) }
    var startTimeMillis by remember { mutableLongStateOf(0L) }

    val scope = rememberCoroutineScope()

    // Recorded samples
    val heartRateSamples = remember { mutableStateListOf<HeartRateSample>() }
    val rotationSamples = remember { mutableStateListOf<RotationVectorSample>() }
    val imuSamples = remember { mutableStateListOf<ImuSample>() }

    // ---- TIMER LOOP: purely for the 00:00:00 display ----
    LaunchedEffect(isRunning) {
        if (isRunning) {
            while (true) {
                val now = SystemClock.elapsedRealtime()
                elapsedSeconds = ((now - startTimeMillis) / 1000L).toInt()
                delay(200L)
            }
        } else {
            elapsedSeconds = 0
        }
    }

    // ---- HEART RATE SAMPLING LOOP: HEART_RATE_HZ ----
    LaunchedEffect(isRunning) {
        if (isRunning && HEART_RATE_HZ > 0) {
            val intervalMs = (1000L / HEART_RATE_HZ).toLong()
            while (true) {
                delay(intervalMs)
                heartRateSamples.add(
                    HeartRateSample(
                        t = SystemClock.elapsedRealtime() - startTimeMillis,
                        bpm = heartRateState.value
                    )
                )
            }
        } else {
            heartRateSamples.clear()
        }
    }

    // ---- IMU & ROTATION SAMPLING LOOP: IMU_HZ ----
    LaunchedEffect(isRunning) {
        if (isRunning && IMU_HZ > 0) {
            val intervalMs = (1000L / IMU_HZ).toLong()
            while (true) {
                delay(intervalMs)

                // Rotation vector
                rotationSamples.add(rotationVectorState.value)

                // Accel + gyro
                val (ax, ay, az) = accelState.value
                val (gx, gy, gz) = gyroState.value
                imuSamples.add(
                    ImuSample(
                        t = SystemClock.elapsedRealtime() - startTimeMillis,
                        ax = ax,
                        ay = ay,
                        az = az,
                        gx = gx,
                        gy = gy,
                        gz = gz
                    )
                )
            }
        } else {
            rotationSamples.clear()
            imuSamples.clear()
        }
    }

    val timerHeight = 24.dp

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(timerHeight),
            contentAlignment = Alignment.Center
        ) {
            if (isRunning) {
                Text(
                    text = formatElapsedTime(elapsedSeconds),
                    color = Color.White,
                    textAlign = TextAlign.Center,
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        Button(
            onClick = {
                scope.launch {
                    if (!isRunning) {
                        // START
                        startTimeMillis = SystemClock.elapsedRealtime()
                        isRunning = true
                    } else {
                        // STOP: snapshot samples & duration
                        val hrToSend = heartRateSamples.toList()
                        val rotToSend = rotationSamples.toList()
                        val imuToSend = imuSamples.toList()
                        val durationSeconds = elapsedSeconds

                        isRunning = false
                        heartRateSamples.clear()
                        rotationSamples.clear()
                        imuSamples.clear()

                        sendHttpRequestEnd(hrToSend, rotToSend, imuToSend, durationSeconds)
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth(0.8f)
                .height(72.dp),
            colors = ButtonDefaults.buttonColors(
                backgroundColor = if (isRunning) Color.Red else Color.Green
            )
        ) {
            Text(
                text = if (isRunning) "STOP" else "START",
                color = Color.White
            )
        }
    }
}

// ----------------------
// Networking
// ----------------------

suspend fun sendHttpRequestStart() {
    withContext(Dispatchers.IO) {
        val client = OkHttpClient()
        val request = Request.Builder()
            .url("$URL/start")
            .build()

        client.newCall(request).execute().use { response ->
            // Optionally check response.isSuccessful, log, etc.
        }
    }
}

suspend fun sendHttpRequestEnd(
    heartRates: List<HeartRateSample>,
    rotations: List<RotationVectorSample>,
    imu: List<ImuSample>,
    duration: Int
) {
    withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient()

            val heartArray = JSONArray()
            heartRates.forEach { hr ->
                val obj = JSONObject().apply {
                    put("t", hr.t)
                    put("bpm", hr.bpm)
                }
                heartArray.put(obj)
            }

            val rotationArray = JSONArray()
            rotations.forEach { rv ->
                val obj = JSONObject().apply {
                    put("x", rv.x)
                    put("y", rv.y)
                    put("z", rv.z)
                    put("w", rv.w)
                }
                rotationArray.put(obj)
            }

            val imuArray = JSONArray()
            imu.forEach { sample ->
                val obj = JSONObject().apply {
                    put("t", sample.t)
                    put("ax", sample.ax)
                    put("ay", sample.ay)
                    put("az", sample.az)
                    put("gx", sample.gx)
                    put("gy", sample.gy)
                    put("gz", sample.gz)
                }
                imuArray.put(obj)
            }

            val json = JSONObject().apply {
                put("heart_rates", heartArray)
                put("rotation_vectors", rotationArray)
                put("imu", imuArray)
                put("duration", duration)
                put("heart_rate_hz", HEART_RATE_HZ)
                put("imu_hz", IMU_HZ)
            }.toString()

            val mediaType = "application/json; charset=utf-8".toMediaType()
            val body = json.toRequestBody(mediaType)

            val request = Request.Builder()
                .url("$URL/end")
                .post(body)
                .build()

            client.newCall(request).execute().use { _ ->
                // Optionally log or check response.isSuccessful
            }
        } catch (e: Exception) {
            Log.e("HTTP", "Error sending /end", e)
        }
    }
}

fun formatElapsedTime(totalSeconds: Int): String {
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return String.format(Locale.US, "%02d:%02d:%02d", hours, minutes, seconds)
}


@Composable
fun Page2() {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "This is the second page.",
            textAlign = TextAlign.Center,
            color = MaterialTheme.colors.primary,
        )
    }
}