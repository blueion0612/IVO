"""
IMU Streaming Test Application
- Real-time IMU acceleration and gyroscope visualization for watch and phone
- Haptic feedback demo with UDP command sending
- Auto-detects phone IP from incoming UDP packets

Requirements:
    pip install matplotlib numpy

Usage:
    python imu_test.py

Author: Claude Code
"""

import socket
import struct
import threading
import time
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.widgets import Button, Slider
import numpy as np

# Configuration
IMU_PORT = 65000          # Port for receiving IMU data
HAPTIC_PORT = 65010       # Port for sending haptic commands

# Data format: 30 floats total
# Watch (15): sw_dT, w_ts0-3, w_lacc0-2, w_gyro0-2, w_rotvec0-3
# Phone (15): p_dT, p_ts0-3, p_lacc0-2, p_gyro0-2, p_rotvec0-3
MSG_SIZE = 30 * 4  # 120 bytes

# Buffer size for plotting (number of samples to display)
BUFFER_SIZE = 200


class IMUDataReceiver:
    """Receives IMU data via UDP and auto-detects phone IP"""

    def __init__(self, port=IMU_PORT):
        self.port = port
        self.socket = None
        self.running = False
        self.thread = None

        # Auto-detected phone IP
        self.phone_ip = None
        self.phone_ip_callback = None

        # Data buffers (deques for efficient append/pop)
        # Watch data
        self.watch_lacc_x = deque(maxlen=BUFFER_SIZE)
        self.watch_lacc_y = deque(maxlen=BUFFER_SIZE)
        self.watch_lacc_z = deque(maxlen=BUFFER_SIZE)
        self.watch_gyro_x = deque(maxlen=BUFFER_SIZE)
        self.watch_gyro_y = deque(maxlen=BUFFER_SIZE)
        self.watch_gyro_z = deque(maxlen=BUFFER_SIZE)

        # Phone data
        self.phone_lacc_x = deque(maxlen=BUFFER_SIZE)
        self.phone_lacc_y = deque(maxlen=BUFFER_SIZE)
        self.phone_lacc_z = deque(maxlen=BUFFER_SIZE)
        self.phone_gyro_x = deque(maxlen=BUFFER_SIZE)
        self.phone_gyro_y = deque(maxlen=BUFFER_SIZE)
        self.phone_gyro_z = deque(maxlen=BUFFER_SIZE)

        # Statistics
        self.packet_count = 0
        self.last_packet_time = 0
        self.packet_rate = 0

        # Initialize buffers with zeros
        for _ in range(BUFFER_SIZE):
            self.watch_lacc_x.append(0)
            self.watch_lacc_y.append(0)
            self.watch_lacc_z.append(0)
            self.watch_gyro_x.append(0)
            self.watch_gyro_y.append(0)
            self.watch_gyro_z.append(0)
            self.phone_lacc_x.append(0)
            self.phone_lacc_y.append(0)
            self.phone_lacc_z.append(0)
            self.phone_gyro_x.append(0)
            self.phone_gyro_y.append(0)
            self.phone_gyro_z.append(0)

    def set_phone_ip_callback(self, callback):
        """Set callback to be called when phone IP is detected"""
        self.phone_ip_callback = callback

    def start(self):
        """Start receiving IMU data"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', self.port))
        self.socket.settimeout(0.1)  # 100ms timeout for clean shutdown

        self.running = True
        self.thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.thread.start()
        print(f"IMU receiver started on port {self.port}")

    def stop(self):
        """Stop receiving IMU data"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.socket:
            self.socket.close()
        print("IMU receiver stopped")

    def _receive_loop(self):
        """Main receive loop"""
        rate_calc_time = time.time()
        rate_calc_count = 0

        while self.running:
            try:
                data, addr = self.socket.recvfrom(MSG_SIZE + 100)

                if len(data) >= MSG_SIZE:
                    # Auto-detect phone IP from first packet
                    if self.phone_ip is None:
                        self.phone_ip = addr[0]
                        print(f"Phone IP auto-detected: {self.phone_ip}")
                        if self.phone_ip_callback:
                            self.phone_ip_callback(self.phone_ip)

                    self._parse_data(data)
                    self.packet_count += 1
                    rate_calc_count += 1

                    # Calculate packet rate every second
                    now = time.time()
                    if now - rate_calc_time >= 1.0:
                        self.packet_rate = rate_calc_count / (now - rate_calc_time)
                        rate_calc_time = now
                        rate_calc_count = 0

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Receive error: {e}")

    def _parse_data(self, data):
        """Parse received IMU data"""
        # Unpack 30 floats (big-endian, Java default)
        values = struct.unpack('>30f', data[:MSG_SIZE])

        # Watch data (indices 0-14)
        # sw_dT=0, ts0-3=1-4, lacc=5-7, gyro=8-10, rotvec=11-14
        self.watch_lacc_x.append(values[5])
        self.watch_lacc_y.append(values[6])
        self.watch_lacc_z.append(values[7])
        self.watch_gyro_x.append(values[8])
        self.watch_gyro_y.append(values[9])
        self.watch_gyro_z.append(values[10])

        # Phone data (indices 15-29)
        # p_dT=15, ts0-3=16-19, lacc=20-22, gyro=23-25, rotvec=26-29
        self.phone_lacc_x.append(values[20])
        self.phone_lacc_y.append(values[21])
        self.phone_lacc_z.append(values[22])
        self.phone_gyro_x.append(values[23])
        self.phone_gyro_y.append(values[24])
        self.phone_gyro_z.append(values[25])


class HapticController:
    """Sends haptic commands via UDP"""

    def __init__(self, port=HAPTIC_PORT):
        self.phone_ip = None
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.haptic_count = 0

    def set_phone_ip(self, ip):
        """Set phone IP address"""
        self.phone_ip = ip
        print(f"Haptic controller target IP set to: {ip}")

    def send_haptic(self, intensity=200, count=1, duration=100):
        """
        Send haptic command to phone

        Args:
            intensity: Vibration intensity (0-255)
            count: Number of vibrations
            duration: Duration of each vibration in milliseconds
        """
        if self.phone_ip is None:
            print("Cannot send haptic: Phone IP not detected yet. Wait for IMU data.")
            return

        # Pack 3 integers (12 bytes, little-endian)
        data = struct.pack('<iii', intensity, count, duration)
        try:
            self.socket.sendto(data, (self.phone_ip, self.port))
            self.haptic_count += 1
            print(f"Haptic sent to {self.phone_ip}: intensity={intensity}, count={count}, duration={duration}ms")
        except Exception as e:
            print(f"Failed to send haptic: {e}")

    def close(self):
        """Close socket"""
        self.socket.close()


class IMUVisualizer:
    """Real-time visualization of IMU data with auto-scaling"""

    def __init__(self):
        self.receiver = IMUDataReceiver()
        self.haptic = HapticController()

        # Set callback for phone IP auto-detection
        self.receiver.set_phone_ip_callback(self.haptic.set_phone_ip)

        # Phone IP text reference for updating
        self.phone_ip_text = None

        # Create figure with subplots
        self.fig = plt.figure(figsize=(14, 10))
        self.fig.suptitle('IMU Streaming Test', fontsize=14, fontweight='bold')

        # Create grid spec for layout
        gs = self.fig.add_gridspec(3, 2, height_ratios=[1, 1, 0.4], hspace=0.3, wspace=0.3)

        # Fixed Y-axis ranges
        ACC_RANGE = (-25, 25)    # Accelerometer range in m/s²
        GYRO_RANGE = (-15, 15)   # Gyroscope range in rad/s

        # Watch Accelerometer (top left)
        self.ax_watch_acc = self.fig.add_subplot(gs[0, 0])
        self.ax_watch_acc.set_title('Watch Linear Acceleration', fontweight='bold')
        self.ax_watch_acc.set_ylabel('m/s²')
        self.ax_watch_acc.set_xlim(0, BUFFER_SIZE)
        self.ax_watch_acc.set_ylim(ACC_RANGE)
        self.ax_watch_acc.grid(True, alpha=0.3)

        # Phone Accelerometer (top right)
        self.ax_phone_acc = self.fig.add_subplot(gs[0, 1])
        self.ax_phone_acc.set_title('Phone Linear Acceleration', fontweight='bold')
        self.ax_phone_acc.set_ylabel('m/s²')
        self.ax_phone_acc.set_xlim(0, BUFFER_SIZE)
        self.ax_phone_acc.set_ylim(ACC_RANGE)
        self.ax_phone_acc.grid(True, alpha=0.3)

        # Watch Gyroscope (middle left)
        self.ax_watch_gyro = self.fig.add_subplot(gs[1, 0])
        self.ax_watch_gyro.set_title('Watch Gyroscope', fontweight='bold')
        self.ax_watch_gyro.set_ylabel('rad/s')
        self.ax_watch_gyro.set_xlabel('Samples')
        self.ax_watch_gyro.set_xlim(0, BUFFER_SIZE)
        self.ax_watch_gyro.set_ylim(GYRO_RANGE)
        self.ax_watch_gyro.grid(True, alpha=0.3)

        # Phone Gyroscope (middle right)
        self.ax_phone_gyro = self.fig.add_subplot(gs[1, 1])
        self.ax_phone_gyro.set_title('Phone Gyroscope', fontweight='bold')
        self.ax_phone_gyro.set_ylabel('rad/s')
        self.ax_phone_gyro.set_xlabel('Samples')
        self.ax_phone_gyro.set_xlim(0, BUFFER_SIZE)
        self.ax_phone_gyro.set_ylim(GYRO_RANGE)
        self.ax_phone_gyro.grid(True, alpha=0.3)

        # X data for plotting
        self.x_data = np.arange(BUFFER_SIZE)

        # Initialize plot lines
        colors = ['#E53935', '#43A047', '#1E88E5']  # Red, Green, Blue for X, Y, Z

        self.watch_acc_lines = [
            self.ax_watch_acc.plot([], [], color=colors[0], label='X', linewidth=1)[0],
            self.ax_watch_acc.plot([], [], color=colors[1], label='Y', linewidth=1)[0],
            self.ax_watch_acc.plot([], [], color=colors[2], label='Z', linewidth=1)[0]
        ]
        self.ax_watch_acc.legend(loc='upper right', fontsize=8)

        self.phone_acc_lines = [
            self.ax_phone_acc.plot([], [], color=colors[0], label='X', linewidth=1)[0],
            self.ax_phone_acc.plot([], [], color=colors[1], label='Y', linewidth=1)[0],
            self.ax_phone_acc.plot([], [], color=colors[2], label='Z', linewidth=1)[0]
        ]
        self.ax_phone_acc.legend(loc='upper right', fontsize=8)

        self.watch_gyro_lines = [
            self.ax_watch_gyro.plot([], [], color=colors[0], label='X', linewidth=1)[0],
            self.ax_watch_gyro.plot([], [], color=colors[1], label='Y', linewidth=1)[0],
            self.ax_watch_gyro.plot([], [], color=colors[2], label='Z', linewidth=1)[0]
        ]
        self.ax_watch_gyro.legend(loc='upper right', fontsize=8)

        self.phone_gyro_lines = [
            self.ax_phone_gyro.plot([], [], color=colors[0], label='X', linewidth=1)[0],
            self.ax_phone_gyro.plot([], [], color=colors[1], label='Y', linewidth=1)[0],
            self.ax_phone_gyro.plot([], [], color=colors[2], label='Z', linewidth=1)[0]
        ]
        self.ax_phone_gyro.legend(loc='upper right', fontsize=8)

        # Status text
        self.status_text = self.fig.text(0.02, 0.02, '', fontsize=10,
                                         family='monospace', verticalalignment='bottom')

        # Create sliders for haptic parameters
        ax_intensity = plt.axes([0.15, 0.15, 0.25, 0.03])
        ax_count = plt.axes([0.15, 0.10, 0.25, 0.03])
        ax_duration = plt.axes([0.15, 0.05, 0.25, 0.03])

        self.slider_intensity = Slider(ax_intensity, 'Intensity', 1, 255, valinit=200, valstep=1)
        self.slider_count = Slider(ax_count, 'Count', 1, 10, valinit=1, valstep=1)
        self.slider_duration = Slider(ax_duration, 'Duration (ms)', 50, 500, valinit=100, valstep=10)

        # Create haptic button
        ax_button = plt.axes([0.55, 0.08, 0.15, 0.08])
        self.btn_haptic = Button(ax_button, 'Send Haptic', color='#2196F3', hovercolor='#1976D2')
        self.btn_haptic.on_clicked(self._on_haptic_click)

        # Info labels
        self.phone_ip_text = self.fig.text(0.75, 0.15, 'Phone IP: (waiting...)', fontsize=10)
        self.fig.text(0.75, 0.10, f'IMU Port: {IMU_PORT}', fontsize=10)
        self.fig.text(0.75, 0.05, f'Haptic Port: {HAPTIC_PORT}', fontsize=10)

        # Animation
        self.ani = None

    def _on_haptic_click(self, event):
        """Handle haptic button click"""
        intensity = int(self.slider_intensity.val)
        count = int(self.slider_count.val)
        duration = int(self.slider_duration.val)
        self.haptic.send_haptic(intensity, count, duration)

    def _update_plot(self, frame):
        """Update plot data with auto-scaling"""
        # Get data as lists
        watch_acc_x = list(self.receiver.watch_lacc_x)
        watch_acc_y = list(self.receiver.watch_lacc_y)
        watch_acc_z = list(self.receiver.watch_lacc_z)
        phone_acc_x = list(self.receiver.phone_lacc_x)
        phone_acc_y = list(self.receiver.phone_lacc_y)
        phone_acc_z = list(self.receiver.phone_lacc_z)
        watch_gyro_x = list(self.receiver.watch_gyro_x)
        watch_gyro_y = list(self.receiver.watch_gyro_y)
        watch_gyro_z = list(self.receiver.watch_gyro_z)
        phone_gyro_x = list(self.receiver.phone_gyro_x)
        phone_gyro_y = list(self.receiver.phone_gyro_y)
        phone_gyro_z = list(self.receiver.phone_gyro_z)

        # Update watch acceleration
        self.watch_acc_lines[0].set_data(self.x_data, watch_acc_x)
        self.watch_acc_lines[1].set_data(self.x_data, watch_acc_y)
        self.watch_acc_lines[2].set_data(self.x_data, watch_acc_z)

        # Update phone acceleration
        self.phone_acc_lines[0].set_data(self.x_data, phone_acc_x)
        self.phone_acc_lines[1].set_data(self.x_data, phone_acc_y)
        self.phone_acc_lines[2].set_data(self.x_data, phone_acc_z)

        # Update watch gyroscope
        self.watch_gyro_lines[0].set_data(self.x_data, watch_gyro_x)
        self.watch_gyro_lines[1].set_data(self.x_data, watch_gyro_y)
        self.watch_gyro_lines[2].set_data(self.x_data, watch_gyro_z)

        # Update phone gyroscope
        self.phone_gyro_lines[0].set_data(self.x_data, phone_gyro_x)
        self.phone_gyro_lines[1].set_data(self.x_data, phone_gyro_y)
        self.phone_gyro_lines[2].set_data(self.x_data, phone_gyro_z)

        # Update phone IP text if detected
        if self.receiver.phone_ip:
            self.phone_ip_text.set_text(f'Phone IP: {self.receiver.phone_ip}')

        # Update status text
        phone_status = self.receiver.phone_ip if self.receiver.phone_ip else "waiting..."
        status = f"Packets: {self.receiver.packet_count:,}  |  Rate: {self.receiver.packet_rate:.1f} Hz  |  Phone: {phone_status}  |  Haptics: {self.haptic.haptic_count}"
        self.status_text.set_text(status)

        # Return all artists that need to be redrawn
        artists = (self.watch_acc_lines + self.phone_acc_lines +
                   self.watch_gyro_lines + self.phone_gyro_lines +
                   [self.status_text, self.phone_ip_text])
        return artists

    def run(self):
        """Start visualization"""
        print("=" * 50)
        print("IMU Streaming Test Application")
        print("=" * 50)
        print(f"Listening for IMU data on port {IMU_PORT}")
        print("Phone IP will be auto-detected from incoming UDP packets")
        print("-" * 50)
        print("Instructions:")
        print("1. Start the IMU app on watch and phone")
        print("2. Set the server IP to this computer's IP")
        print("3. Start streaming from the watch")
        print("4. Phone IP will be detected automatically")
        print("5. Use sliders to adjust haptic parameters")
        print("6. Click 'Send Haptic' to trigger vibration")
        print("-" * 50)

        # Start receiver
        self.receiver.start()

        # Start animation (blit=False to avoid the axes issue)
        self.ani = animation.FuncAnimation(
            self.fig, self._update_plot, interval=50, blit=False, cache_frame_data=False
        )

        try:
            plt.show()
        finally:
            self.receiver.stop()
            self.haptic.close()
            print("Application closed")


def main():
    """Main entry point"""
    visualizer = IMUVisualizer()
    visualizer.run()


if __name__ == "__main__":
    main()
