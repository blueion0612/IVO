# IMU input

IVO listens on UDP 65000 for the packet that
[IMU_Streamer](https://github.com/blueion0612/IMU_Streamer) sends: **30
big-endian floats, 120 bytes**, a watch block followed by a phone block. The wire
format is documented in full
[there](https://github.com/blueion0612/IMU_Streamer/blob/main/docs/protocol.md).
Haptic commands go back on UDP 65010 as three little-endian integers.

## Which channels reach the model

The classifier uses six channels, all from the watch, in this order:

    sw_lacc_x, sw_lacc_y, sw_lacc_z, sw_gyro_x, sw_gyro_y, sw_gyro_z

Their positions differ between the two packet formats in this family, so the index
map matters:

| Channel | in the 30-float packet IVO reads | in the 55-float upstream packet |
|---|---|---|
| `sw_lacc_x/y/z` | 5, 6, 7 | 16, 17, 18 |
| `sw_gyro_x/y/z` | 8, 9, 10 | 10, 11, 12 |

[IMU_Gesture_Classifier](https://github.com/blueion0612/IMU_Gesture_Classifier),
which trained the checkpoints IVO loads, records against the 55-float upstream
layout. IVO reads the 30-float layout and remaps, so the six values reaching the
model are the same six in the same order. **The two index maps are not
interchangeable**: copying one into the other silently feeds the model the wrong
channels rather than failing.
