# karel.py
import time
import os
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import simpleaudio as sa
import pygame

class KarelPupper:
    def start():
        if not rclpy.ok():
            rclpy.init()

    def __init__(self):
        if not rclpy.ok():
            rclpy.init()
        self.node = Node('karel_node')
        self.publisher = self.node.create_publisher(Twist, 'cmd_vel', 10)

    def move(self, linear_x, linear_y, angular_z):
        move_cmd = Twist()
        move_cmd.linear.x = linear_x
        move_cmd.linear.y = linear_y
        move_cmd.angular.z = angular_z
        self.publisher.publish(move_cmd)
        rclpy.spin_once(self.node, timeout_sec=1.0)
        self.stop()

    def wiggle(self, wiggle_time=6, play_sound=True):
        # Play wiggle sound if requested
        if play_sound:
            pygame.mixer.init()
            current_dir = os.path.dirname(os.path.abspath(__file__))
            sounds_dir = os.path.join(current_dir, '..', '..', 'sounds')
            wav_path = os.path.join(sounds_dir, 'puppy_wiggle.wav')
            wav_path = os.path.normpath(wav_path)

            try:
                wiggle_sound = pygame.mixer.Sound(wav_path)
                wiggle_sound.play()
                self.node.get_logger().info(f'Playing wiggle sound from: {wav_path}')
            except Exception as e:
                self.node.get_logger().warning(f"Could not play wiggle sound: {e}")

        move_cmd = Twist()
        move_cmd.linear.x = 0.0
        # Alternate wiggle directions for a total of 1 second
        single_wiggle_duration = 0.2  # seconds per half-wiggle
        angular_speed = 0.8

        start_time = time.time()
        direction = 1
        while time.time() - start_time < wiggle_time:
            move_cmd.angular.z = direction * angular_speed
            self.publisher.publish(move_cmd)
            rclpy.spin_once(self.node, timeout_sec=0.01)
            time.sleep(single_wiggle_duration)
            direction *= -1  # Switch direction

        self.stop()

        self.node.get_logger().info('Wiggle!')

    def bob(self, bob_time=5, play_sound=True):
        """
        Makes the robot bob back and forth by moving forward and backward with a specified speed and duration.
        """
        if play_sound:
            pygame.mixer.init()
            current_dir = os.path.dirname(os.path.abspath(__file__))
            sounds_dir = os.path.join(current_dir, '..', '..', 'sounds')
            wav_path = os.path.join(sounds_dir, 'puppy_bob.wav')
            wav_path = os.path.normpath(wav_path)

            try:
                wiggle_sound = pygame.mixer.Sound(wav_path)
                wiggle_sound.play()
                self.node.get_logger().info(f'Playing wiggle sound from: {wav_path}')
            except Exception as e:
                self.node.get_logger().warning(f"Could not play wiggle sound: {e}")

        move_cmd = Twist()
        move_cmd.angular.z = 0.0
        bob_speed = 0.5

        start_time = time.time()
        direction = 1
        while time.time() - start_time < bob_time:
            move_cmd.linear.x = direction * bob_speed
            self.publisher.publish(move_cmd)
            rclpy.spin_once(self.node, timeout_sec=0.01)
            time.sleep(0.2)
            direction *= -1  # Switch direction

        self.stop()

        self.node.get_logger().info('Bob!')

    def move_forward(self):
        self.move(linear_x=0.7, linear_y=0.0, angular_z=0.0)

    def move_backward(self):
        self.move(linear_x=-0.3, linear_y=0.0, angular_z=0.0)

    def move_left(self):
        self.move(linear_x=0.0, linear_y=0.5, angular_z=0.0)

    def move_right(self):
        self.move(linear_x=0.0, linear_y=-0.5, angular_z=0.0)

    def turn_left(self):
        self.move(linear_x=0.0, linear_y=0.0, angular_z=1.0)

    def turn_right(self):
        self.move(linear_x=0.0, linear_y=0.0, angular_z=-1.0)

    def bark(self):
        self.node.get_logger().info('Bark...')
        pygame.mixer.init()
        # Directory-independent path to sound file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sounds_dir = os.path.join(current_dir, '..', '..', 'sounds')
        bark_sound_path = os.path.join(sounds_dir, 'dog_bark.wav')

        bark_sound_path = os.path.normpath(bark_sound_path)
        bark_sound = pygame.mixer.Sound(bark_sound_path)
        bark_sound.play()
        self.node.get_logger().info(f'Playing bark sound from: {bark_sound_path}')
        self.stop()

    def dance(self):
        self.node.get_logger().info('Rick Rolling...')
        pygame.mixer.init()
        # Directory-independent path to sound file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sounds_dir = os.path.join(current_dir, '..', '..', 'sounds')
        dance_sound_path = os.path.join(sounds_dir, 'rickroll.wav')

        dance_sound_path = os.path.normpath(dance_sound_path)
        dance_sound = pygame.mixer.Sound(dance_sound_path)
        self.node.get_logger().info(f'Playing dance sound from: {dance_sound_path}')
        dance_sound.play()

        self.wiggle(wiggle_time=3)
        self.move_left()
        self.bob(bob_time=4)
        self.move_right()
        self.bob(bob_time=4)
        self.move_forward()
        self.move_backward()
        self.wiggle(wiggle_time=4)
        self.turn_left()
        self.turn_left()
        self.wiggle(wiggle_time=4)


    def stop(self):
        self.node.get_logger().info('Stopping...')
        move_cmd = Twist()
        move_cmd.linear.x = 0.0
        move_cmd.linear.y = 0.0
        move_cmd.linear.z = 0.0
        move_cmd.angular.x = 0.0
        move_cmd.angular.y = 0.0
        move_cmd.angular.z = 0.0
        self.publisher.publish(move_cmd)
        rclpy.spin_once(self.node, timeout_sec=1.0)

    def __del__(self):
        self.node.get_logger().info('Tearing down...')
        self.node.destroy_node()
        rclpy.shutdown()
