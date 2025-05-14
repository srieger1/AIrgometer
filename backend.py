#!/usr/bin/env python3

from flask import Flask, request, jsonify, render_template

import time
import threading

#from codecarbon import EmissionsTracker

import asyncio
from ollama import AsyncClient

import io
import atexit



OLLAMA_API_URL = 'http://admiral-ms-7d30:11434'
OLLAMA_MODEL = "llama3.2"
#OLLAMA_MODEL = "deepseek-r1"

TIMEOUT= 300

DEFAULT_SUBMITTED_WATT_SECONDS = 10

# Global variables to track answer and progress
answer = ""
displayed_answer = ""
submitted_watt_seconds = 0
last_increment_time = time.time()
timeout_occured = False
answer_stream_running = False
gpio_initialized = False

def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower(): return True
    except Exception: pass
    return False

def init_raspberrypi():
    global gpio_initialized
    if gpio_initialized:
        return

    print ("Enabling GPIO input...")
    gpio_initialized = True

    PIN = 10

    import RPi.GPIO as GPIO

    #GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def gpio_cleanup():
        GPIO.cleanup(PIN)

    atexit.register(gpio_cleanup)

    def gpio_callback(channel):
        global submitted_watt_seconds
        print("PIN state changed to HIGH, adding watt seconds")
        add_watt_seconds(DEFAULT_SUBMITTED_WATT_SECONDS)

    GPIO.add_event_detect(PIN, GPIO.RISING, callback=gpio_callback, bouncetime=100)

app = Flask(__name__)

# ollama
def query_ai_model(question):
    global answer
    
    # Send the request to Ollama
    async def chat():
        message = {'role': 'user', 'content': question}
        async for part in await AsyncClient(host=OLLAMA_API_URL).chat(model=OLLAMA_MODEL, messages=[message], stream=True):
            global answer, answer_stream_running
            answer_stream_running = True
            # print(part['message']['content'], end='', flush=True)
            partial_answer = part['message']['content']
            print(partial_answer)
            answer += partial_answer
        #print("Response complete.")
        answer_stream_running = False

    asyncio.run(chat())

    return

def add_watt_seconds(watt_seconds):
    global last_increment_time, submitted_watt_seconds, displayed_answer
    # simulate a button press
    # GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Update last request time
    last_increment_time = time.time()

    # Calculate fraction of the answer to display
    submitted_watt_seconds += watt_seconds
    displayed_answer = answer[:int(submitted_watt_seconds)] # one character per watt second, maybe adjust this later, or even
        # use a more complex formula, e.g., calculating the time it took the model to generate the answer and infer watt seconds
        # from that

def reset_state():
    global answer, displayed_answer, submitted_watt_seconds, last_increment_time
    answer = ""
    displayed_answer = ""
    submitted_watt_seconds = 0
    last_increment_time = time.time()

@app.route("/")
def index():
    global TIMEOUT
    if request.args.get("timeout"):
        try:
            TIMEOUT = int(request.args.get("timeout"))
        except ValueError:
            return jsonify({"error": "Invalid timeout value"}), 400

    reset_state()
    return render_template("index.html", debug=request.args.get("debug", False))

@app.route("/ask", methods=["POST"])
def ask_question():
    global answer_stream_running, timeout_occured

    if answer_stream_running:
        print("Answer stream is running. Please wait.")
        return jsonify({"error": "Answer stream is running. Please wait."}), 400
    
    reset_state()

    question = request.json.get("question")
    if not question:
        return jsonify({"error": "Question is required"}), 400

    # Query AI model
    timeout_occured = False
    query_ai_model(question)

    return jsonify({
        "message": "Question received. Submit Watt seconds to display the answer."
    })

@app.route("/submit_watt_seconds", methods=["POST"])
def submit_watt_seconds():
    global answer, displayed_answer, submitted_watt_seconds, last_increment_time, timeout_occured

    watt_seconds = request.json.get("watt_seconds")
    cleared = request.json.get("cleared", False)
    if not watt_seconds and watt_seconds != 0:
        return jsonify({"error": "Watt seconds are required"}), 400

    if watt_seconds == 0:
        if timeout_occured == True:
            if cleared:
                timeout_occured = False
                return jsonify({"info": "Timeout cleared"}), 200
            else:
                return jsonify({"info": "Timeout"}), 200
        else:
            return jsonify({
                "info": "0 watt seconds submitted. Assumed backend status check",
                "answer_length": len(answer),
                "displayed_answer": displayed_answer,
                "displayed_answer_length": len(displayed_answer),
            }), 200
    else:
        # add watt seconds
        add_watt_seconds(watt_seconds)

        return jsonify({
            "displayed_answer": displayed_answer,
            "answer_length": len(answer),
            "displayed_answer_length": len(displayed_answer),
        })

def check_timeout():
    global timeout_occured
    while True:
        time.sleep(1)  # Check every second
        if answer and (time.time() - last_increment_time > TIMEOUT):
            print("Timeout reached. Resetting UI.")
            timeout_occured = True
            reset_state()

def main():
    # Start timeout thread
    timeout_thread = threading.Thread(target=check_timeout)
    timeout_thread.daemon = True
    timeout_thread.start()

    # Start the Flask app
    if is_raspberrypi() and not gpio_initialized:
        print("Detected raspberrypi, initializing GPIO...")
        init_raspberrypi()
    app.run(debug=False)

if __name__ == "__main__":
    main()
