#!/usr/bin/env python3
"""
OpenAI Realtime API Integration for Pupper
Ultra-low latency voice interaction using WebSocket-based Realtime API.
Replaces the traditional Whisper → GPT → TTS pipeline with a single unified API.
Hope you're enjoying the new setup with little latency!
"""

import asyncio
import base64
import json
import logging
import os
import queue
import subprocess
import sys
import threading
from typing import Optional

import numpy as np
import rclpy
import sounddevice as sd
import websockets
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

# Import centralized API configuration
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'config'))
from api_keys import get_openai_api_key

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("realtime_voice")

DJI_DEVICE = "alsa_input.usb-DJI_Technology_Co.__Ltd._Wireless_Mic_Rx_XSP12345678B-01.analog-stereo"

class RealtimeVoiceNode(Node):
    """ROS2 node for OpenAI Realtime API voice interaction."""

    def __init__(self):
        super().__init__('realtime_voice_node')

        # ROS2 Publishers
        self.transcription_publisher = self.create_publisher(
            String,
            '/transcription',
            10
        )

        self.response_publisher = self.create_publisher(
            String,
            'gpt4_response_topic',
            10
        )

        # Microphone control subscriber
        self.mic_control_subscriber = self.create_subscription(
            String,
            '/microphone_control',
            self.microphone_control_callback,
            10
        )

        # Audio configuration
        self.sample_rate = 24000  # Realtime API uses 24kHz
        self.channels = 1
        self.chunk_size = 4800  # 200ms chunks at 24kHz

        # State management
        self.websocket = None
        self.audio_stream = None
        self.is_recording = False
        self.microphone_muted = False
        self.agent_speaking = False  # Track if agent is currently speaking
        self.running = True
        self.unmute_task: asyncio.Task | None = None

        # Audio buffers (use thread-safe queue for audio callback)
        self.audio_queue = queue.Queue(maxsize=100)
        self.playback_queue = queue.Queue(maxsize=100)

        # API key
        self.api_key = get_openai_api_key()

        # Text accumulator to see the full model output
        self.current_response_text = ""
        self.system_prompt = """
You are a robot dog with a limited set of movements, and you are listening to high-level commands and turning them into a sequence of movements.

You are allowed to return the following:

- `move`: Go forward at 0.7 m/s, once.
- `turn_left`: Turn left around your center, at an angular rate of 1 rad/s.
- `turn_right`: Turn right around your center, at an angular rate of 1 rad/s.
- `wiggle`: A preconfigured maneuver to stand in place but turn in different directions, resulting in a wiggle. You must give a time in seconds.
- `bob`: A preconfigured maneuver to stand in place but bob back and forth. You must give a time in seconds.
- `bark`: Produce a barking sound.
- `dance`: A preconfigured routine that lasts 15 seconds.

Return one command per newline. For commands that need a duration, return the duration as a floating point number in seconds, separated from the command with a space.

Respond only in commannds.

Examples:

User: Turn 180 degrees, move forward 1 metre, and bob for 3 seconds.
Response:
turn_right
turn_right
turn_right
move
move
bob 3.0
"""
        logger.info('Realtime Voice Node initialized')

    def microphone_control_callback(self, msg):
        """Handle microphone control commands."""
        command = msg.data.lower().strip()
        if command == 'mute':
            self.microphone_muted = True
            logger.info("🔇 Microphone MUTED")
        elif command == 'unmute':
            self.microphone_muted = False
            logger.info("🎤 Microphone UNMUTED")

    async def _delayed_unmute(self):
        """Unmute microphone after 3 second delay to prevent echo."""
        await asyncio.sleep(3.0)  # Longer delay to ensure no echo

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

        self.agent_speaking = False
        self.microphone_muted = False
        logger.info("🎤 Mic unmuted (after delay)")

    async def _clear_server_audio_buffer(self):
        """Tell the server to clear its input audio buffer."""
        try:
            clear_message = {
                "type": "input_audio_buffer.clear"
            }
            await self.websocket.send(json.dumps(clear_message))
            logger.info("🧹 Cleared server audio buffer")
        except Exception as e:
            logger.error(f"Error clearing server buffer: {e}")

    async def connect_realtime_api(self):
        """Connect to OpenAI Realtime API via WebSocket."""
        url = "wss://api.openai.com/v1/realtime?model=gpt-realtime-2"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            self.websocket = await websockets.connect(url, additional_headers=headers)
            logger.info("✅ Connected to OpenAI Realtime API")

            # Configure session
            await self.configure_session()

            return True
        except Exception as e:
            logger.error(f"Failed to connect to Realtime API: {e}")
            return False

    async def configure_session(self):
        """Configure the Realtime API session."""
        config = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "instructions": self.system_prompt,
                "audio": {
                    "input": {
                        "transcription": None,  # Disable to reduce ghost transcriptions
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.8,  # Much less sensitive - only clear speech
                            "prefix_padding_ms": 100,  # Reduced - less padding
                            "silence_duration_ms": 1500,  # Require 1 full second of silence
                            "create_response": True,
                            "interrupt_response": False,
                        },
                    },
                    "output": {
                        "voice": "alloy",
                    },
                },
                "max_output_tokens": 150
            }
        }

        await self.websocket.send(json.dumps(config))
        logger.info("📝 Session configured with system prompt")

    def start_audio_streaming(self):
        """Start capturing audio via parec (PipeWire)."""
        try:
            # Must specify format so parec resamples DJI mic's 48kHz to 24kHz PCM16 mono
            self.parec_proc = subprocess.Popen(
                [
                    "parec",
                    f"--device={DJI_DEVICE}",
                    "--format=s16le",
                    "--rate=24000",
                    "--channels=1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self.is_recording = True
            logger.info("🎤 Audio streaming started (via parec)")

            # Start a background thread to continuously read data and feed the queue
            self._reader_thread = threading.Thread(target=self.audio_callback_parec, daemon=True)
            self._reader_thread.start()

        except Exception as e:
            logger.error(f"Failed to start audio streaming: {e}")

    def audio_callback_parec(self):
        """Continuously read PCM chunks from parec and queue them."""
        # 24kHz * 0.1s = 2400 samples, each s16le is 2 bytes => 4800 bytes
        BYTES_PER_CHUNK = 4800
        chunk_count = 0

        while self.is_recording and self.parec_proc:
            raw = self.parec_proc.stdout.read(BYTES_PER_CHUNK)
            if not raw or len(raw) < BYTES_PER_CHUNK:
                break  # Stream ended or not enough data

            chunk_count += 1
            if chunk_count % 50 == 0:  # log every 50 chunks (~5 seconds at 100ms chunks)
                # Compute RMS so you can tell if it's silence vs. actual sound
                audio_data = np.frombuffer(raw, dtype=np.int16)
                rms = int(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
                logger.info(f"🎙️  parec chunk #{chunk_count}, RMS={rms}")

            # Critical: Don't capture while agent is speaking or muted
            if self.agent_speaking or self.microphone_muted or not self.running:
                continue

            # Convert to numpy int16 array (to keep consistent with your original queue format)
            audio_data = np.frombuffer(raw, dtype=np.int16)
            try:
                self.audio_queue.put_nowait(audio_data)
            except queue.Full:
                pass

    async def send_audio_loop(self):
        """Continuously send audio to Realtime API."""
        while self.running:
            try:
                # Get from thread-safe queue with timeout
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue

                # Skip sending if agent is speaking (prevents server-side transcription of echo)
                if self.agent_speaking or self.microphone_muted:
                    continue

                # Convert to base64
                audio_bytes = audio_data.tobytes()
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')

                # Send to API
                message = {
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64
                }

                await self.websocket.send(json.dumps(message))

            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                await asyncio.sleep(0.1)

    async def receive_events_loop(self):
        """Receive and process events from Realtime API."""
        while self.running:
            try:
                message = await self.websocket.recv()
                event = json.loads(message)

                await self.handle_event(event)

            except websockets.exceptions.ConnectionClosed:
                logger.error("WebSocket connection closed")
                break
            except Exception as e:
                logger.error(f"Error receiving event: {e}")
                await asyncio.sleep(0.1)

    async def handle_event(self, event):
        """Handle different event types from Realtime API."""
        event_type = event.get("type")

        if event_type == "error":
            logger.error(f"API Error: {event.get('error')}")
            logger.error(f"Full error event: {json.dumps(event, indent=2)}")

        elif event_type == "session.created":
            logger.info("✅ Session created")

        elif event_type == "session.updated":
            logger.info("✅ Session updated")

        elif event_type == "conversation.item.input_audio_transcription.completed":
            # User's speech was transcribed (this might not fire if transcription is disabled)
            transcription = event.get("transcript", "")
            if transcription.strip():
                logger.info(f"🎤 User: {transcription}")

                # Publish transcription
                msg = String()
                msg.data = transcription
                self.transcription_publisher.publish(msg)

        # This part is implemented for you to compensate for the lack of clarity in this lab's first iteration.
        # In the future, students should implement this themselves to understand the conversation flow.
        elif event_type == "conversation.item.created":
            # Item created in conversation - check if it's user input
            item = event.get("item", {})
            if item.get("role") == "user" and item.get("type") == "message":
                # Extract content if available
                content = item.get("content", [])
                for content_part in content:
                    if content_part.get("type") == "input_audio":
                        # We got user audio input confirmation
                        transcript = content_part.get("transcript")
                        if transcript:
                            logger.info(f"🎤 User: {transcript}")

        elif event_type == "response.output_text.delta":
            delta = event.get("delta", "")
            if delta:
                self.current_response_text += delta

        elif event_type == "response.output_text.done":
            text = event.get("text", "")
            if text.strip():
                self.current_response_text = text

        elif event_type == "response.output_audio_transcript.delta":
            delta = event.get("delta", "")
            if delta:
                self.current_response_text += delta

        elif event_type == "response.output_audio.delta":
            audio_b64 = event.get("delta", "")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
                try:
                    self.playback_queue.put_nowait(audio_data)
                except queue.Full:
                    pass

        elif event_type == "response.output_audio_transcript.done":
            pass

        elif event_type == "response.output_audio.done":
            if self.unmute_task and not self.unmute_task.done():
                self.unmute_task.cancel()
            self.unmute_task = asyncio.create_task(self._delayed_unmute())
            logger.info("⏱️  Scheduling unmute in 3s")

        elif event_type == "response.done":
            text = self.current_response_text.strip()

            if text:
                logger.info(f"🤖 Assistant: {self.current_response_text}")

                # Publish response text
                msg = String()
                msg.data = text
                self.response_publisher.publish(msg)

            self.current_response_text = ""

        elif event_type == "input_audio_buffer.speech_started":
            # User started speaking - handle interruption
            if self.agent_speaking:
                logger.info("⚠️  User interrupted")
                self.agent_speaking = False
                # Clear playback queue
                while not self.playback_queue.empty():
                    try:
                        self.playback_queue.get_nowait()
                    except queue.Empty:
                        break

        elif event_type == "response.created":
            # New response starting - clear buffer IMMEDIATELY before audio even arrives
            self.current_response_text = ""

            # CRITICAL: Mute IMMEDIATELY on response creation, before any audio arrives
            self.agent_speaking = True
            logger.info("🔇 Mic muted (response created)")

            # Drain local queue and tell server to discard buffered audio
            asyncio.create_task(self._clear_server_audio_buffer())
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break

            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                except queue.Empty:
                    break

        elif event_type == "response.content_part.done":
            # Content part completed - don't publish here (will publish in response.done)
            pass

    async def playback_audio_loop(self):
        """Play audio responses from the API."""
        output_stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.int16,
            latency="high",
        )
        output_stream.start()

        try:
            while self.running:
                try:
                    audio_data = self.playback_queue.get(timeout=0.1)
                    output_stream.write(audio_data)
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue
        finally:
            output_stream.stop()
            output_stream.close()

    async def run(self):
        """Main run loop."""
        # Connect to API
        if not await self.connect_realtime_api():
            logger.error("Failed to connect to Realtime API")
            return

        # Start audio capture
        self.start_audio_streaming()

        # Run all tasks concurrently
        await asyncio.gather(
            self.send_audio_loop(),
            self.receive_events_loop(),
            self.playback_audio_loop()
        )

    def cleanup(self):
        """Clean up resources."""
        self.running = False

        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()

        if self.websocket:
            asyncio.create_task(self.websocket.close())

        logger.info("Cleaned up resources")


async def main_async(args=None):
    """Async main function."""
    rclpy.init(args=args)

    node = RealtimeVoiceNode()
    executor = SingleThreadedExecutor()
    executor.add_node(node)

    try:
        logger.info("🚀 Realtime Voice Node starting...")
        logger.info("Speak to interact with Pupper!")

        # Create tasks
        ros_task = asyncio.create_task(spin_ros_async(executor))
        realtime_task = asyncio.create_task(node.run())

        # Wait for both
        await asyncio.gather(ros_task, realtime_task)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        node.cleanup()
        executor.shutdown()
        rclpy.shutdown()


async def spin_ros_async(executor):
    """Spin ROS2 executor in async-friendly way."""
    while rclpy.ok():
        executor.spin_once(timeout_sec=0.1)
        await asyncio.sleep(0.01)


def main(args=None):
    """Entry point."""
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Program interrupted")


if __name__ == '__main__':
    main()
