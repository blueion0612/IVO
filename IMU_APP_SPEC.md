# IMU Streaming App - 데이터 통신 명세서

## 1. 개요

| 항목 | 값 |
|------|-----|
| 앱 이름 | IMU Streaming App |
| 버전 | 0.4.1 |
| 플랫폼 | Android (Phone + WearOS Watch) |
| 통신 방식 | Watch → Phone (Bluetooth), Phone → Server (UDP) |

---

## 2. IMU 데이터 (Phone → Server)

### 연결 정보
| 항목 | 값 |
|------|-----|
| 프로토콜 | UDP |
| 포트 | 65000 |
| 엔디안 | **Big Endian** (Java 기본값) |
| 메시지 크기 | 120 bytes (30 floats × 4 bytes) |

### 데이터 구조 (30 floats)

#### Watch 데이터 (인덱스 0-14)
| 인덱스 | 필드명 | 설명 | 단위 |
|--------|--------|------|------|
| 0 | sw_dT | 샘플 간 시간 간격 | 초 (seconds) |
| 1 | w_ts_hour | 타임스탬프 - 시 | - |
| 2 | w_ts_min | 타임스탬프 - 분 | - |
| 3 | w_ts_sec | 타임스탬프 - 초 | - |
| 4 | w_ts_nano | 타임스탬프 - 나노초 | - |
| 5 | w_lacc_x | 선형 가속도 X | m/s² |
| 6 | w_lacc_y | 선형 가속도 Y | m/s² |
| 7 | w_lacc_z | 선형 가속도 Z | m/s² |
| 8 | w_gyro_x | 자이로스코프 X | rad/s |
| 9 | w_gyro_y | 자이로스코프 Y | rad/s |
| 10 | w_gyro_z | 자이로스코프 Z | rad/s |
| 11 | w_rotvec_w | 회전 벡터 W (쿼터니언) | - |
| 12 | w_rotvec_x | 회전 벡터 X (쿼터니언) | - |
| 13 | w_rotvec_y | 회전 벡터 Y (쿼터니언) | - |
| 14 | w_rotvec_z | 회전 벡터 Z (쿼터니언) | - |

#### Phone 데이터 (인덱스 15-29)
| 인덱스 | 필드명 | 설명 | 단위 |
|--------|--------|------|------|
| 15 | p_dT | 샘플 간 시간 간격 | 초 (seconds) |
| 16 | p_ts_hour | 타임스탬프 - 시 | - |
| 17 | p_ts_min | 타임스탬프 - 분 | - |
| 18 | p_ts_sec | 타임스탬프 - 초 | - |
| 19 | p_ts_nano | 타임스탬프 - 나노초 | - |
| 20 | p_lacc_x | 선형 가속도 X | m/s² |
| 21 | p_lacc_y | 선형 가속도 Y | m/s² |
| 22 | p_lacc_z | 선형 가속도 Z | m/s² |
| 23 | p_gyro_x | 자이로스코프 X | rad/s |
| 24 | p_gyro_y | 자이로스코프 Y | rad/s |
| 25 | p_gyro_z | 자이로스코프 Z | rad/s |
| 26 | p_rotvec_w | 회전 벡터 W (쿼터니언) | - |
| 27 | p_rotvec_x | 회전 벡터 X (쿼터니언) | - |
| 28 | p_rotvec_y | 회전 벡터 Y (쿼터니언) | - |
| 29 | p_rotvec_z | 회전 벡터 Z (쿼터니언) | - |

### Python 파싱 예제
```python
import struct

MSG_SIZE = 120  # 30 floats × 4 bytes
data, addr = udp_socket.recvfrom(MSG_SIZE)

# Big Endian으로 파싱 ('>': Big Endian, '30f': 30 floats)
values = struct.unpack('>30f', data[:MSG_SIZE])

# Watch 데이터 추출
watch_lacc = (values[5], values[6], values[7])      # X, Y, Z
watch_gyro = (values[8], values[9], values[10])     # X, Y, Z
watch_rotvec = (values[11], values[12], values[13], values[14])  # W, X, Y, Z

# Phone 데이터 추출
phone_lacc = (values[20], values[21], values[22])   # X, Y, Z
phone_gyro = (values[23], values[24], values[25])   # X, Y, Z
phone_rotvec = (values[26], values[27], values[28], values[29])  # W, X, Y, Z
```

---

## 3. 햅틱 피드백 (Server → Phone → Watch)

### 연결 정보
| 항목 | 값 |
|------|-----|
| 프로토콜 | UDP (Server → Phone) |
| 포트 | 65010 |
| 엔디안 | **Little Endian** (Python 기본값) |
| 메시지 크기 | 12 bytes (3 integers × 4 bytes) |

### 데이터 흐름
```
Server (Python) --UDP/Little Endian--> Phone --Bluetooth/Big Endian--> Watch
```

### 데이터 구조 (3 integers)
| 인덱스 | 필드명 | 설명 | 범위 | 기본값 |
|--------|--------|------|------|--------|
| 0 | intensity | 진동 강도 | 1-255 | 200 |
| 1 | count | 진동 횟수 | 1-10 | 1 |
| 2 | duration | 진동 지속시간 | 50-500 | 100 (ms) |

### Python 전송 예제
```python
import socket
import struct

HAPTIC_PORT = 65010
phone_ip = "192.168.x.x"  # 폰 IP (IMU 패킷에서 자동 감지 가능)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# 햅틱 파라미터
intensity = 200   # 진동 강도 (1-255)
count = 2         # 진동 횟수
duration = 150    # 진동 시간 (ms)

# Little Endian으로 패킹 ('<': Little Endian, 'iii': 3 integers)
data = struct.pack('<iii', intensity, count, duration)
sock.sendto(data, (phone_ip, HAPTIC_PORT))
```

---

## 4. 데이터 흐름 다이어그램

```
┌─────────────┐    Bluetooth    ┌─────────────┐      UDP        ┌─────────────┐
│   Watch     │  ───────────>   │   Phone     │  ───────────>   │   Server    │
│  (WearOS)   │    IMU 15f      │  (Android)  │   IMU 30f       │  (Python)   │
│             │                 │             │   Port 65000    │             │
│             │                 │             │   Big Endian    │             │
└─────────────┘                 └─────────────┘                 └─────────────┘
      ▲                               ▲                               │
      │        Bluetooth              │           UDP                 │
      │        Big Endian             │        Little Endian          │
      └───────────────────────────────┴───────────────────────────────┘
                              Haptic Command (12 bytes)
                              Port 65010
```

---

## 5. 주요 상수 정리

### Android 앱 (Kotlin)
```kotlin
// DataSingleton.kt
const val IMU_MSG_SIZE = 120        // 30 floats × 4 bytes
const val HAPTIC_CMD_SIZE = 12      // 3 integers × 4 bytes
const val IMU_PORT_DEFAULT = 65000  // IMU UDP 포트
const val HAPTIC_PORT = 65010       // Haptic UDP 포트
const val IP_DEFAULT = "192.168.1.138"

// 경로 (Wearable Message API)
const val IMU_PATH = "/imu"
const val HAPTIC_PATH = "/haptic"
const val PING_REQ = "/ping_request"
const val PING_REP = "/ping_reply"

// Capability
const val WATCH_CAPABILITY = "watch"
const val PHONE_CAPABILITY = "phone"
```

### Python 테스트 코드
```python
IMU_PORT = 65000          # IMU 수신 포트
HAPTIC_PORT = 65010       # 햅틱 전송 포트
MSG_SIZE = 120            # 30 floats × 4 bytes

# 그래프 스케일 범위
ACC_RANGE = (-25, 25)     # 가속도계 m/s²
GYRO_RANGE = (-15, 15)    # 자이로스코프 rad/s
```

---

## 6. 엔디안 정리

| 통신 구간 | 프로토콜 | 엔디안 | 비고 |
|-----------|----------|--------|------|
| Watch → Phone | Bluetooth (Channel) | Big Endian | Java 기본값 |
| Phone → Server | UDP (IMU) | **Big Endian** | ByteBuffer 기본값 |
| Server → Phone | UDP (Haptic) | **Little Endian** | Python struct 기본값 |
| Phone → Watch | Bluetooth (Message) | Big Endian | Java 기본값 |

---

## 7. 센서 샘플링 정보

| 센서 | 타입 | Android Sensor ID |
|------|------|-------------------|
| Linear Acceleration | TYPE_LINEAR_ACCELERATION | 10 |
| Gyroscope | TYPE_GYROSCOPE | 4 |
| Rotation Vector | TYPE_ROTATION_VECTOR | 11 |

- 샘플링 레이트: SENSOR_DELAY_FASTEST (~200Hz 목표)
- 실제 전송률: 디바이스 및 네트워크 상태에 따라 다름

---

## 8. 파일 구조 요약

```
imu-streaming-app/
├── phone/src/main/java/com/imu/phone/
│   ├── activity/PhoneMain.kt       # 메인 액티비티
│   ├── viewmodel/PhoneViewModel.kt # 상태 관리
│   ├── service/
│   │   ├── ImuService.kt           # IMU 수신 및 UDP 전송
│   │   └── HapticService.kt        # 햅틱 UDP 수신 및 워치 전달
│   ├── ui/view/RenderHome.kt       # UI 렌더링
│   └── DataSingleton.kt            # 전역 상수 및 상태
│
├── watch/src/main/java/com/imu/watch/
│   ├── activity/WatchMain.kt       # 메인 액티비티
│   ├── viewmodel/WatchViewModel.kt # 상태 관리 및 햅틱 실행
│   ├── service/ImuService.kt       # IMU 센서 읽기 및 전송
│   └── DataSingleton.kt            # 전역 상수 및 상태
│
└── test/imu_test.py                # Python 테스트 코드
```

---

## 9. 빠른 참조 - 데이터 파싱

### IMU 수신 (Python)
```python
import socket
import struct

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 65000))

data, addr = sock.recvfrom(120)
values = struct.unpack('>30f', data)  # Big Endian

# 주요 데이터
watch_acc = values[5:8]    # Watch 가속도 (x, y, z)
watch_gyro = values[8:11]  # Watch 자이로 (x, y, z)
phone_acc = values[20:23]  # Phone 가속도 (x, y, z)
phone_gyro = values[23:26] # Phone 자이로 (x, y, z)
```

### 햅틱 전송 (Python)
```python
import socket
import struct

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
data = struct.pack('<iii', 200, 1, 100)  # Little Endian
sock.sendto(data, (phone_ip, 65010))
```
