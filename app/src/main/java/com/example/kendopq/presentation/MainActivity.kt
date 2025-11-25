/* While this template provides a good starting point for using Wear Compose, you can always
 * take a look at https://github.com/android/wear-os-samples/tree/main/ComposeStarter to find the
 * most up to date changes to the libraries and their usages.
 */

package com.example.kendopq.presentation

import android.os.Bundle
import android.view.WindowManager
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
import kotlin.math.roundToInt

import androidx.compose.ui.platform.LocalContext


// ----------------------
// Data models & constants
// ----------------------

const val URL = "http://192.168.0.108:5000" // Change to the Server's IP
const val HEART_RATE_HZ = 0.1 // 6 times per min
const val IMU_HZ = 20      // shared for rotation + accel + gyro

data class HeartRateSample(val t: Long, val bpm: Int)

data class ImuSample(
    val t: Long,     // timestamp (Epoch ms)
    val ax: Float,
    val ay: Float,
    val az: Float,
    val gx: Float,
    val gy: Float,
    val gz: Float
)

data class RotationVectorSample(
    val t: Long, // timestamp (Epoch ms)
    val x: Float,
    val y: Float,
    val z: Float,
    val w: Float
)

// Summary returned from /recent
data class TrainingSummary(
    val avgHeartRate: Double,
    val strikeCount: Int,
    val durationSeconds: Int?
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
        RotationVectorSample(0L, 0f, 0f, 0f, 1f)
    )
    private val accelState = mutableStateOf(Triple(0f, 0f, 0f))
    private val gyroState = mutableStateOf(Triple(0f, 0f, 0f))

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)

        setTheme(android.R.style.Theme_DeviceDefault)

        // Keep the screen on to prevent sensor throttling in low power mode
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

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
                    rotationVectorState.value = RotationVectorSample(0L, x, y, z, w)
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
        val scope = rememberCoroutineScope()
        val context = LocalContext.current

        // ---- Recording state (hoisted so it survives page changes) ----
        var isRunning by remember { mutableStateOf(false) }

        var elapsedSeconds by remember { mutableIntStateOf(0) }
        var startTimeMillis by remember { mutableLongStateOf(0L) }

        var strikeCount by remember { mutableIntStateOf(0) }
        var isSwingDetected by remember { mutableStateOf(false) }
        var lastStrikeTime by remember { mutableLongStateOf(0L) }

        val heartRateSamples = remember { mutableStateListOf<HeartRateSample>() }
        val rotationSamples = remember { mutableStateListOf<RotationVectorSample>() }
        val imuSamples = remember { mutableStateListOf<ImuSample>() }

        // Summary for second page
        var lastSummary by remember {
            mutableStateOf(loadSummaryFromPrefs(context))
        }
        // current HR for display
        val currentBpm = heartRateState.value

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
                    val bpm = heartRateState.value
                    Log.d("KendoPQ", "Heart Rate recorded: $bpm bpm")
                    heartRateSamples.add(
                        HeartRateSample(
                            t = System.currentTimeMillis(), // Use Epoch time
                            bpm = bpm
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

                    val now = System.currentTimeMillis() // Use Epoch time

                    // Rotation vector
                    val currentRot = rotationVectorState.value
                    rotationSamples.add(
                        RotationVectorSample(now, currentRot.x, currentRot.y, currentRot.z, currentRot.w)
                    )

                    // Accel + gyro
                    val (ax, ay, az) = accelState.value
                    val (gx, gy, gz) = gyroState.value

                    // --- Strike Detection Logic ---
                    val gyroMag = kotlin.math.sqrt(gx * gx + gy * gy + gz * gz)
                    if (gyroMag > 4.0f) { // Threshold: ~230 deg/s
                        if (!isSwingDetected && (now - lastStrikeTime > 400)) { // 400ms Cooldown to prevent double counts
                            strikeCount++
                            isSwingDetected = true
                            lastStrikeTime = now
                            Log.d("KendoPQ", "Strike detected! Total: $strikeCount")
                        }
                    } else if (gyroMag < 2.0f) { // Reset threshold
                        isSwingDetected = false
                    }
                    // ------------------------------

                    imuSamples.add(
                        ImuSample(
                            t = now,
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

        fun startRecording() {
            strikeCount = 0
            isSwingDetected = false
            lastStrikeTime = 0L
            heartRateSamples.clear()
            rotationSamples.clear()
            imuSamples.clear()
            startTimeMillis = SystemClock.elapsedRealtime()
            isRunning = true
            // (sendHttpRequestStart is defined but was not used before; keeping behavior the same)
        }

        fun stopRecording() {
            val hrToSend = heartRateSamples.toList()
            val rotToSend = rotationSamples.toList()
            val imuToSend = imuSamples.toList()
            val durationSeconds = elapsedSeconds
            val finalStrikeCount = strikeCount

            isRunning = false
            heartRateSamples.clear()
            rotationSamples.clear()
            imuSamples.clear()

            scope.launch {
                // 1) send /end with session data (existing behavior)
                sendHttpRequestEnd(
                    heartRates = hrToSend,
                    rotations = rotToSend,
                    imu = imuToSend,
                    duration = durationSeconds,
                    strikeCount = finalStrikeCount
                )

                // 2) wait 1 second
                delay(1000L)

                // 3) fetch /recent from the server
                val summary = fetchRecentSummary()
                if (summary != null) {
                    lastSummary = summary
                    // save to local storage so it's available next time app opens
                    saveSummaryToPrefs(context, summary)
                }
            }
        }

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
                    0 -> Page1(
                        isRunning = isRunning,
                        elapsedSeconds = elapsedSeconds,
                        strikeCount = strikeCount,
                        currentBpm = currentBpm,
                        onStart = { startRecording() },
                        onStop = { stopRecording() }
                    )
                    1 -> Page2(summary = lastSummary)
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
    isRunning: Boolean,
    elapsedSeconds: Int,
    strikeCount: Int,   // still here for future use, just not shown
    currentBpm: Int,
    onStart: () -> Unit,
    onStop: () -> Unit
) {
    // Fixed space for HR + timer so layout doesn't shift when recording starts
    val headerHeight = 56.dp

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(headerHeight),
            contentAlignment = Alignment.Center
        ) {
            if (isRunning) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    // Heart rate on top
                    Text(
                        text = "${currentBpm.coerceAtLeast(0)} bpm",
                        color = Color.White,
                        textAlign = TextAlign.Center,
                        style = MaterialTheme.typography.body1
                    )
                    Spacer(modifier = Modifier.height(4.dp))

                    // Timer
                    Text(
                        text = formatElapsedTime(elapsedSeconds),
                        color = Color.White,
                        textAlign = TextAlign.Center,
                    )
                }
            }
            // When not running, we keep this Box empty but same height
        }

        Spacer(modifier = Modifier.height(12.dp))

        Button(
            onClick = {
                if (!isRunning) onStart() else onStop()
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
    duration: Int,
    strikeCount: Int
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
                    put("t", rv.t)
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
                put("strike_count", strikeCount)
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

/**
 * GET /recent
 * Expected JSON example:
 * {
 *   "average_heart_rate": 85.3,
 *   "strike_count": 42,
 *   "duration": 120
 * }
 */
suspend fun fetchRecentSummary(): TrainingSummary? {
    return withContext(Dispatchers.IO) {
        try {
            val client = OkHttpClient()
            val request = Request.Builder()
                .url("$URL/recent")
                .get()
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.e("HTTP", "Error /recent: code=${response.code}")
                    return@withContext null
                }
                val bodyStr = response.body?.string() ?: return@withContext null
                val json = JSONObject(bodyStr)

                val avgHr = json.optDouble("average_heart_rate", Double.NaN)
                val strikes = json.optInt("strike_count", 0)
                val duration =
                    if (json.has("duration")) json.optInt("duration") else null

                if (avgHr.isNaN()) {
                    Log.e("HTTP", "No average_heart_rate in /recent")
                    return@withContext null
                }

                TrainingSummary(
                    avgHeartRate = avgHr,
                    strikeCount = strikes,
                    durationSeconds = duration
                )
            }
        } catch (e: Exception) {
            Log.e("HTTP", "Error fetching /recent", e)
            null
        }
    }
}

fun formatElapsedTime(totalSeconds: Int): String {
    val hours = totalSeconds / 3600
    val minutes = (totalSeconds % 3600) / 60
    val seconds = totalSeconds % 60
    return String.format(Locale.US, "%02d:%02d:%02d", hours, minutes, seconds)
}

// ---------- Persistence helpers ----------

private const val PREFS_NAME = "kendo_pq_prefs"
private const val KEY_AVG_HR = "avg_hr"
private const val KEY_STRIKES = "strikes"
private const val KEY_DURATION = "duration"

fun saveSummaryToPrefs(context: Context, summary: TrainingSummary) {
    val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    prefs.edit()
        .putFloat(KEY_AVG_HR, summary.avgHeartRate.toFloat())
        .putInt(KEY_STRIKES, summary.strikeCount)
        .apply {
            if (summary.durationSeconds != null) {
                putInt(KEY_DURATION, summary.durationSeconds)
            } else {
                remove(KEY_DURATION)
            }
        }
        .apply()
}

fun loadSummaryFromPrefs(context: Context): TrainingSummary? {
    val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    if (!prefs.contains(KEY_AVG_HR) || !prefs.contains(KEY_STRIKES)) {
        return null
    }

    val avgHr = prefs.getFloat(KEY_AVG_HR, -1f)
    val strikes = prefs.getInt(KEY_STRIKES, 0)
    val duration =
        if (prefs.contains(KEY_DURATION)) prefs.getInt(KEY_DURATION, 0) else null

    if (avgHr <= 0f) return null

    return TrainingSummary(
        avgHeartRate = avgHr.toDouble(),
        strikeCount = strikes,
        durationSeconds = duration
    )
}


@Composable
fun Page2(summary: TrainingSummary?) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 8.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        if (summary == null) {
            Text(
                text = "No recent training data.\nFinish a run to see stats.",
                textAlign = TextAlign.Center,
                color = MaterialTheme.colors.primary
            )
        } else {
            Text(
                text = "Last Session",
                style = MaterialTheme.typography.body2,
                color = MaterialTheme.colors.primary,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(8.dp))

            // Average Heart Rate
            Text(
                text = "${summary.avgHeartRate.roundToInt()} bpm",
                style = MaterialTheme.typography.title3,
                color = Color.White,
                textAlign = TextAlign.Center
            )
            Text(
                text = "avg heart rate",
                style = MaterialTheme.typography.caption1,
                color = Color.Gray,
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Strike count
            Text(
                text = "${summary.strikeCount}",
                style = MaterialTheme.typography.title3,
                color = Color.White,
                textAlign = TextAlign.Center
            )
            Text(
                text = "strikes",
                style = MaterialTheme.typography.caption1,
                color = Color.Gray,
                textAlign = TextAlign.Center
            )

            if (summary.durationSeconds != null) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = formatElapsedTime(summary.durationSeconds),
                    style = MaterialTheme.typography.body1,
                    color = Color.White,
                    textAlign = TextAlign.Center
                )
                Text(
                    text = "duration",
                    style = MaterialTheme.typography.caption1,
                    color = Color.Gray,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}
