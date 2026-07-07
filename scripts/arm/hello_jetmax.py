#!/usr/bin/env python3
"""
hello_jetmax.py — Simplest possible JetMax movement script.
Uses ROS topics to move the arm through positions.
Run with: python3 hello_jetmax.py
"""
import rospy
import time
from jetmax_control.msg import SetJetMax

rospy.init_node('hello_jetmax', anonymous=True)
pub = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)

# Wait until the jetmax_control node is actually subscribed
print("Waiting for jetmax_control to connect...")
while pub.get_num_connections() == 0:
    time.sleep(0.1)
print("Connected!")

def move(x, y, z, duration=1.5):
    msg = SetJetMax()
    msg.x = float(x)
    msg.y = float(y)
    msg.z = float(z)
    msg.duration = float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.5)

print("Moving to home position...")
move(0, -160, 200)

print("Moving down...")
move(0, -160, 120)

print("Moving left...")
move(-80, -160, 150)

print("Moving right...")
move(80, -160, 150)

print("Returning home...")
move(0, -160, 200)

print("Done!")
