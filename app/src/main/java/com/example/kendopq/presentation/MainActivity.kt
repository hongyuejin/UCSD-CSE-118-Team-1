package com.example.kendopq.presentation

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Bundle
import android.util.Log
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.wear.compose.material.Button
import androidx.wear.compose.material.ButtonDefaults
import androidx.wear.compose.material.MaterialTheme
import androidx.wear.compose.material.Text
import com.example.kendopq.presentation.theme.KendoPQTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.jvm.Volatile

// ----------------------
// Constants & Data Models
// ----------------------

const val URL = "http://192.168.1.137:5000" // Secondary Watch Server Endpoint
const val IMU_HZ = 20f

data class ImuSample(
    val t: Long,     // Epoch timestamp (System.currentTimeMillis)
    val ax: Float, val ay: Float, val az: Float,
    val gx: Float, val gy: Float, val gz: Float
)

// ----------------------
// Activity
// ----------------------

class MainActivity : ComponentActivity(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelSensor: Sensor? = null
    private var gyroSensor: Sensor? = null

    // Volatile storage to avoid UI recomposition on every sensor event
    @Volatile private var latestAccel = Triple(0f, 0f, 0f)
    @Volatile private var latestGyro = Triple(0f, 0f, 0f)

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setTheme(android.R.style.Theme_DeviceDefault)

        // REQUIREMENT: Keep screen on to prevent sensor throttling
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        gyroSensor = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)

        setContent {
            KendoPQTheme {
                ImuRecorderScreen(
                    getAccel = { latestAccel },
                    getGyro = { latestGyro },
                    onStartSensors = { startSensors() },
                    onStopSensors = { stopSensors() }
                )
            }
        }
    }

    private fun startSensors() {
        val periodUs = (1_000_000 / IMU_HZ).toInt()
        accelSensor?.let {
            sensorManager.registerListener(this, it, periodUs)
        }
        gyroSensor?.let {
            sensorManager.registerListener(this, it, periodUs)
        }
    }

    private fun stopSensors() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        val e = event ?: return
        when (e.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
                val v = e.values
                if (v.size >= 3) latestAccel = Triple(v[0], v[1], v[2])
            }
            Sensor.TYPE_GYROSCOPE -> {
                val v = e.values
                if (v.size >= 3) latestGyro = Triple(v[0], v[1], v[2])
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // No-op
    }
}

// ----------------------
// UI
// ----------------------

@Composable
fun ImuRecorderScreen(
    getAccel: () -> Triple<Float, Float, Float>,
    getGyro: () -> Triple<Float, Float, Float>,
    onStartSensors: () -> Unit,
    onStopSensors: () -> Unit
) {
    var isRecording by remember { mutableStateOf(false) }
    var sampleCount by remember { mutableIntStateOf(0) }

    // Store samples in a standard mutable list (more efficient for large appends than snapshotStateList)
    val recordedData = remember { mutableListOf<ImuSample>() }

    val scope = rememberCoroutineScope()

    // Recording Loop
    LaunchedEffect(isRecording) {
        if (isRecording) {
            val delayMs = (1000L / IMU_HZ).toLong()
            // Delay first to avoid immediate sample and race condition on restart
            delay(delayMs) 
            while (true) {
                // FIX: Check if we are still recording after delay to avoid ghost samples on stop
                if (!isRecording) break

                val now = System.currentTimeMillis() // REQUIREMENT: Epoch time
                val (ax, ay, az) = getAccel()
                val (gx, gy, gz) = getGyro()

                recordedData.add(ImuSample(now, ax, ay, az, gx, gy, gz))
                sampleCount = recordedData.size

                delay(delayMs)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colors.background),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = if (isRecording) "RECORDING" else "IDLE",
            style = MaterialTheme.typography.title2,
            color = if (isRecording) Color.Red else Color.Gray
        )

        Spacer(modifier = Modifier.height(10.dp))

        Text(
            // FIX: Force display to 0 when not recording to prevent visual glitches
            text = "Samples: ${if (isRecording) sampleCount else 0}",
            style = MaterialTheme.typography.body1
        )

        Spacer(modifier = Modifier.height(20.dp))

        Button(
            onClick = {
                if (!isRecording) {
                    // START
                    recordedData.clear()
                    sampleCount = 0
                    onStartSensors()
                    isRecording = true
                } else {
                    // STOP
                    isRecording = false
                    onStopSensors()

                    // Capture data to send
                    val dataToSend = recordedData.toList()
                    
                    // Reset local state immediately for UI feedback
                    recordedData.clear()
                    sampleCount = 0

                    scope.launch {
                        sendDataToServer(dataToSend)
                    }
                }
            },
            colors = ButtonDefaults.buttonColors(
                backgroundColor = if (isRecording) Color.Red else Color.Green
            ),
            modifier = Modifier
                .fillMaxWidth(0.8f)
                .height(60.dp)
        ) {
            Text(text = if (isRecording) "STOP" else "START")
        }
    }
}

// ----------------------
// Network
// ----------------------

suspend fun sendDataToServer(samples: List<ImuSample>) {
    withContext(Dispatchers.IO) {
        try {
            // REQUIREMENT: 60s timeouts
            val client = OkHttpClient.Builder()
                .connectTimeout(60, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .writeTimeout(60, TimeUnit.SECONDS)
                .build()

            val imuArray = JSONArray()
            samples.forEach { s ->
                val obj = JSONObject().apply {
                    put("t", s.t)
                    put("ax", s.ax)
                    put("ay", s.ay)
                    put("az", s.az)
                    put("gx", s.gx)
                    put("gy", s.gy)
                    put("gz", s.gz)
                }
                imuArray.put(obj)
            }

            // REQUIREMENT: Metadata
            val json = JSONObject().apply {
                put("device_id", "wrist_watch_B")
                put("data_type", "imu_only")
                put("imu_hz", IMU_HZ)
                put("sample_count", samples.size)
                put("imu", imuArray)
            }

            val mediaType = "application/json; charset=utf-8".toMediaType()
            val body = json.toString().toRequestBody(mediaType)

            val request = Request.Builder()
                .url("$URL/end")
                .post(body)
                .build()

            Log.d("Uploader", "Uploading ${samples.size} samples to $URL...")
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    Log.d("Uploader", "Success: ${response.code}")
                } else {
                    Log.e("Uploader", "Failed: ${response.code} ${response.message}")
                }
            }
        } catch (e: Exception) {
            Log.e("Uploader", "Exception during upload", e)
        }
    }
}
