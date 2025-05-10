import RPi.GPIO as GPIO # Import Raspberry Pi GPIO library
import asyncio
import signal
import atexit
import threading

# def button_callback(channel):
#     print("Button was pushed!")
# GPIO.setwarnings(False) # Ignore warning for now
# GPIO.setmode(GPIO.BOARD) # Use physical pin numbering
# GPIO.setup(10, GPIO.IN, pull_up_down=GPIO.PUD_OFF) # Set pin 10 to be an input pin and set initial value to be pulled low (off)
# GPIO.add_event_detect(10,GPIO.RISING,callback=button_callback,bouncetime=100) # Setup event on pin 10 rising edge
# message = input("Press enter to quit\n\n") # Run until someone presses enter
# GPIO.cleanup() # Clean up

PIN = 10

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
pin_event = asyncio.Event()

def gpio_cleanup(*args):
    GPIO.cleanup(PIN)
    exit(0)

atexit.register(gpio_cleanup)
signal.signal(signal.SIGTERM, gpio_cleanup)
signal.signal(signal.SIGINT, gpio_cleanup)

def gpio_callback(channel):
    print("setting event..." + str(channel))
    pin_event.set()

GPIO.add_event_detect(PIN, GPIO.RISING, callback=gpio_callback, bouncetime=1)

async def wait_for_pin_change():
    global pin_event
    print("Waiting for GPIO event...")
    pin_event.clear()
    while True:
        await pin_event.wait()
        print("Received GPIO event...")
        pin_event.clear()
        state = GPIO.input(PIN)
        # Handle the pin change event
        if state == GPIO.HIGH:
            # PIN changed to high
            # add watt seconds
            #watt_seconds = DEFAULT_SUBMITTED_WATT_SECONDS
            #submitted_watt_seconds += watt_seconds
            print("high")

# Start gpio thread
#gpio_thread = threading.Thread(target=wait_for_pin_change)
#gpio_thread.daemon = True
#gpio_thread.start()

asyncio.run(wait_for_pin_change())