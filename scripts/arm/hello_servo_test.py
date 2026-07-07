import time
import hiwonder

print("Hello, JetMax!")
hiwonder.serial_servo.set_position(1, 450, 1000)
time.sleep(1.5)
hiwonder.serial_servo.set_position(1, 550, 1000)
time.sleep(1.5)
print("Done.")