// wearos/SovereignPulse.kt
// ABV Sovereign Stack — Wear OS Heart Rate + Gait Monitor
//
// Monitors heart rate and accelerometer data from a Wear OS smartwatch.
// If the watch is removed (HRM signal lost) or gait signature mismatches,
// a nuke signal is sent to the paired device via BLE.

package com.abv.sovereign.pulse

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.IBinder
import android.util.Log
import androidx.health.services.client.HealthServices
import androidx.health.services.client.MeasureCallback
import androidx.health.services.client.data.Availability
import androidx.health.services.client.data.DataPointContainer
import androidx.health.services.client.data.DataType
import androidx.health.services.client.data.DeltaDataType

/**
 * SovereignPulseService — Foreground service for continuous biometric monitoring.
 *
 * Dual-channel monitoring:
 * 1. Heart rate via Health Services API — detects watch removal (BPM = 0)
 * 2. Accelerometer via SensorManager — validates gait signature
 *
 * Trigger conditions:
 * - HRM unavailable or BPM = 0 for > 5 seconds → NUKE signal
 * - Gait signature deviation > threshold → alert + escalate
 */
class SovereignPulseService : Service(), SensorEventListener {

    companion object {
        private const val TAG = "SovereignPulse"
        private const val CHANNEL_ID = "sovereign_pulse_channel"
        private const val NOTIFICATION_ID = 1
        private const val HRM_TIMEOUT_MS = 5000L
        private const val GAIT_SAMPLE_WINDOW = 50
        private const val GAIT_DEVIATION_THRESHOLD = 2.5f
    }

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var lastHeartbeatTime: Long = System.currentTimeMillis()
    private var hrmAvailable: Boolean = true
    private val gaitSamples: MutableList<Float> = mutableListOf()

    // Baseline gait signature (calibrated during setup)
    private var baselineGaitMagnitude: Float = 9.81f
    private var baselineGaitVariance: Float = 0.5f

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildNotification())

        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }

        Log.i(TAG, "SovereignPulse service started")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startHeartRateMonitoring()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        sensorManager.unregisterListener(this)
        Log.i(TAG, "SovereignPulse service stopped")
        super.onDestroy()
    }

    // --- Heart Rate Monitoring ---

    private fun startHeartRateMonitoring() {
        val healthClient = HealthServices.getClient(this)
        val measureClient = healthClient.measureClient

        val heartRateCallback = object : MeasureCallback {
            override fun onAvailabilityChanged(
                dataType: DeltaDataType<*, *>,
                availability: Availability
            ) {
                hrmAvailable = availability.toString() != "UNAVAILABLE"
                if (!hrmAvailable) {
                    Log.w(TAG, "HRM availability changed: UNAVAILABLE")
                    checkHrmTimeout()
                }
            }

            override fun onDataReceived(data: DataPointContainer) {
                val heartRatePoints = data.getData(DataType.HEART_RATE_BPM)
                for (point in heartRatePoints) {
                    val bpm = point.value
                    Log.d(TAG, "Heart rate: $bpm BPM")

                    if (bpm == 0.0) {
                        Log.w(TAG, "Heart rate = 0 — possible watch removal")
                        checkHrmTimeout()
                    } else {
                        lastHeartbeatTime = System.currentTimeMillis()
                        hrmAvailable = true

                        // Check for tachycardia (duress signal)
                        if (bpm > 120.0) {
                            Log.w(TAG, "Tachycardia detected: $bpm BPM")
                            sendDuressSignal("tachycardia", bpm)
                        }
                    }
                }
            }
        }

        measureClient.registerMeasureCallback(DataType.HEART_RATE_BPM, heartRateCallback)
        Log.i(TAG, "Heart rate monitoring started")
    }

    private fun checkHrmTimeout() {
        val elapsed = System.currentTimeMillis() - lastHeartbeatTime
        if (elapsed > HRM_TIMEOUT_MS) {
            Log.e(TAG, "HRM timeout exceeded — triggering NUKE")
            triggerNuke("hrm_lost")
        }
    }

    // --- Gait Analysis ---

    override fun onSensorChanged(event: SensorEvent?) {
        event?.let {
            if (it.sensor.type == Sensor.TYPE_ACCELEROMETER) {
                val magnitude = Math.sqrt(
                    (it.values[0] * it.values[0] +
                     it.values[1] * it.values[1] +
                     it.values[2] * it.values[2]).toDouble()
                ).toFloat()

                gaitSamples.add(magnitude)

                if (gaitSamples.size >= GAIT_SAMPLE_WINDOW) {
                    analyzeGaitSignature()
                    gaitSamples.clear()
                }
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // Not used
    }

    private fun analyzeGaitSignature() {
        if (gaitSamples.isEmpty()) return

        val mean = gaitSamples.average().toFloat()
        val variance = gaitSamples.map { (it - mean) * (it - mean) }.average().toFloat()

        val magnitudeDeviation = Math.abs(mean - baselineGaitMagnitude)
        val varianceDeviation = Math.abs(variance - baselineGaitVariance)

        val totalDeviation = magnitudeDeviation + varianceDeviation

        if (totalDeviation > GAIT_DEVIATION_THRESHOLD) {
            Log.w(TAG, "Gait signature mismatch: deviation=$totalDeviation")
            sendDuressSignal("gait_mismatch", totalDeviation.toDouble())
        }
    }

    // --- Triggers ---

    private fun triggerNuke(reason: String) {
        Log.e(TAG, "NUKE TRIGGERED: $reason")
        // Send BLE nuke signal to paired device
        sendBleBroadcast("NUKE", reason)
    }

    private fun sendDuressSignal(type: String, value: Double) {
        Log.w(TAG, "Duress signal: type=$type, value=$value")
        sendBleBroadcast("DURESS", "$type:$value")
    }

    private fun sendBleBroadcast(command: String, payload: String) {
        // In production: BLE GATT write to paired Sovereign device
        val intent = Intent("com.abv.sovereign.BLE_COMMAND").apply {
            putExtra("command", command)
            putExtra("payload", payload)
        }
        sendBroadcast(intent)
        Log.d(TAG, "BLE broadcast: command=$command, payload=$payload")
    }

    // --- Notification ---

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Sovereign Pulse Monitor",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Continuous biometric monitoring"
        }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Sovereign Pulse")
            .setContentText("Monitoring active")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
    }
}
