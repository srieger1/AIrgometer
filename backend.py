#!/usr/bin/env python3

from flask import Flask, request, jsonify, render_template

import time
import threading

#from codecarbon import EmissionsTracker

import asyncio
from ollama import AsyncClient

import io
import atexit
import sys



OLLAMA_API_URL = 'http://admiral-ms-7d30:11434'
#OLLAMA_MODEL = "llama3.2"
#OLLAMA_MODEL = "deepseek-r1"
OLLAMA_MODEL = "qwen3:8b"

TIMEOUT= 300 # timeout in seconds after which the UI is reset if no watt seconds are submitted

DEBUG_MODE = False # debug mode is set to False for production use and to avoid issues with duplicate GPIO initialization
MAXIMUM_ANSWER_LENGTH = 10000  # maximum length of the answer to display

DEFAULT_SUBMITTED_WATT_SECONDS = 4

PROLOG = '/no_think Du sollst Kindern zeigen, wieviel Energie für Anfragen an eine künstliche Intelligenz benötigt wird. Du musst aber in Deiner Antwort nicht sagen, was Du bist. Antworte so, dass es ein Kind zwischen 7 und 14 versteht. Du wurdest vom Magrathea Laboratories e.V. gebaut, einem Hackspace in Fulda. Man kann den Hackspace freitags ab 20 Uhr in der Lindenstraße besuchen. Meine Frage an Dich ist: '

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
    # can be removed as GPIO errors seam to be coming from Flask debug mode
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
        message = {'role': 'user', 'content': PROLOG + question}
        # message = {'role': 'user', 'content': question}
        async for part in await AsyncClient(host=OLLAMA_API_URL).chat(model=OLLAMA_MODEL, messages=[message], stream=True):
            global answer, answer_stream_running
            answer_stream_running = True
            # print(part['message']['content'], end='', flush=True)
            partial_answer = part['message']['content']
            print(partial_answer)
            answer += partial_answer
            # if answer is too long, stop streaming
            if len(answer) > MAXIMUM_ANSWER_LENGTH:
                print("Answer too long, stopping streaming.")
                break
        #print("Response complete.")
        answer_stream_running = False

    asyncio.run(chat())

    return

def add_watt_seconds(watt_seconds):
    global last_increment_time, submitted_watt_seconds, answer, displayed_answer
    # simulate a button press
    # GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Update last request time
    last_increment_time = time.time()

    # Calculate fraction of the answer to display
    submitted_watt_seconds += watt_seconds

    # intial cleanup of answer, e.g., remove leading whitespace and <think> tags
    if len(displayed_answer) == 0 and len(answer) > 0:
        # remove leading whitespace and <think> tags
        answer = answer.replace('<think>', '').replace('</think>', '').lstrip(" \n\t")

    # append addtional fraction to displayed answer
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
    if request.json.get("test", False):
        submit_watt_seconds()
    else:
        if answer_stream_running:
            print("Answer stream is running. Please wait.")
            return jsonify({"error": "Answer stream is running. Please wait."}), 400
        
        reset_state()

        question = request.json.get("question")
        if not question:
            print("No question provided.")
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
            print("No watt seconds submitted, assuming backend status check.")
            return jsonify({
                "info": "0 watt seconds submitted. Assumed backend status check",
                "answer_length": len(answer),
                "displayed_answer": displayed_answer,
                "displayed_answer_length": len(displayed_answer),
            }), 200
    else:
        # add watt seconds
        add_watt_seconds(watt_seconds)

        print(f"Added {watt_seconds} watt seconds. Total watt seconds: {submitted_watt_seconds}")
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
    global DEBUG_MODE, TIMEOUT
    # Start timeout thread
    timeout_thread = threading.Thread(target=check_timeout)
    timeout_thread.daemon = True
    timeout_thread.start()

    # Start the Flask app
    if is_raspberrypi() and not gpio_initialized:
        print("Detected raspberrypi, initializing GPIO...")
        init_raspberrypi()
    
    # if arguments are passed, use them as debug mode
    if len(sys.argv) > 1 and sys.argv[1] == "debug":
        DEBUG_MODE = True
        TIMEOUT = 10  # Set a shorter timeout for debugging

    app.run(debug=DEBUG_MODE,host='0.0.0.0')

if __name__ == "__main__":
    main()
