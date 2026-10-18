
- `gpt-realtime-2`

DJI mic:

```
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ python3 -m sounddevice
  0 vc4-hdmi-0: MAI PCM i2s-hifi-0 (hw:1,0), ALSA (0 in, 2 out)
  1 pulse, ALSA (32 in, 32 out)
* 2 default, ALSA (32 in, 32 out)
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ lsusb
Bus 004 Device 002: ID 04e8:6300 Samsung Electronics Co., Ltd Flash Drive FIT
Bus 004 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 003 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 002: ID 2ca3:4011 DJI Technology Co., Ltd. Wireless Mic Rx
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ arecord -l
**** List of CAPTURE Hardware Devices ****
xcb_connection_has_error() returned true
card 3: Rx [Wireless Mic Rx], device 0: USB Audio [USB Audio]
  Subdevices: 0/1
  Subdevice #0: subdevice #0
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ arecord -D hw:3,0 -f S16_LE -r 48000 -c 1 -d 5 test.wav
xcb_connection_has_error() returned true
arecord: main:831: audio open error: Device or resource busy
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ pactl list short sources
xcb_connection_has_error() returned true
87      alsa_output.platform-soc_107c000000_sound.stereo-fallback.monitor       PipeWire        s32le 2ch 48000Hz       RUNNING
275     alsa_input.usb-DJI_Technology_Co.__Ltd._Wireless_Mic_Rx_XSP12345678B-01.analog-stereo   PipeWire  s24le 2ch 48000Hz       RUNNING
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ parecord alsa_input.usb-DJI_Technology_Co.__Ltd._Wireless_Mic_Rx_XSP12345678B-01.analog-stereo test.wav
Too many arguments.
pi@pupper:~/lab_6_fall_2025/pupper_llm/karel $ parecord --device=alsa_input.usb-DJI_Technology_Co.__Ltd._Wireless_Mic_Rx_XSP12345678B-01.analog-stereo test.wav
xcb_connection_has_error() returned true
```
