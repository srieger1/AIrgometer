from flask import Flask, request, jsonify, render_template

import time
import threading

#from codecarbon import EmissionsTracker

import asyncio
from ollama import AsyncClient

import RPi.GPIO as GPIO

PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(PIN, GPIO.IN)
pin_event = asyncio.Event()


def gpio_callback(channel):
    pin_event.set()

GPIO.add_event_detect(PIN, GPIO.BOTH, callback=gpio_callback)

async def wait_for_pin_change():
    while True:
        await pin_event.wait()
        pin_event.clear()
        state = GPIO.input(PIN)
        print(f"Pin {PIN} änderte sich auf {'HIGH' if state else 'LOW'}")

app = Flask(__name__)

# Global variables to track answer and progress
answer = ""
displayed_answer = ""
submitted_watt_seconds = 0
last_request_time = time.time()
timeout_occured = False
answerStreamRunning = False

# ollama
def query_ai_model(question):
    global answer
    
    # Send the request to Ollama
    async def chat():
        message = {'role': 'user', 'content': question}
        async for part in await AsyncClient().chat(model='llama3.2', messages=[message], stream=True):
            global answer, answerStreamRunning
            answerStreamRunning = True
            # print(part['message']['content'], end='', flush=True)
            partial_answer = part['message']['content']
            print(partial_answer)
            answer += partial_answer
        #print("Response complete.")
        answerStreamRunning = False

    asyncio.run(chat())

    return

def reset_state():
    global answer, displayed_answer, submitted_watt_seconds, last_request_time
    answer = ""
    displayed_answer = ""
    submitted_watt_seconds = 0
    last_request_time = time.time()

@app.route("/")
def index():
    reset_state()
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask_question():
    global answerStreamRunning

    if answerStreamRunning:
        print("Answer stream is running. Please wait.")
        return jsonify({"error": "Answer stream is running. Please wait."}), 400
    
    reset_state()

    question = request.json.get("question")
    if not question:
        return jsonify({"error": "Question is required"}), 400

    # Query AI model
    query_ai_model(question)

    return jsonify({
        "message": "Question received. Submit Watt seconds to display the answer."
    })

@app.route("/submit_watt_seconds", methods=["POST"])
def submit_watt_seconds():
    global answer, displayed_answer, submitted_watt_seconds, last_request_time, timeout_occured

    watt_seconds = request.json.get("watt_seconds")
    if not watt_seconds and watt_seconds != 0:
        return jsonify({"error": "Watt seconds are required"}), 400

    if watt_seconds == 0:
        if timeout_occured:
            timeout_occured = False
            return jsonify({"info": "Timeout"}), 200
        return jsonify({
            "info": "0 watt seconds submitted. Assumed backend status check",
            "answer_length": len(answer),
            "displayed_answer": displayed_answer,
            "displayed_answer_length": len(displayed_answer),
        }), 200

    # Update last request time
    last_request_time = time.time()

    # simulate a button press
    # GPIO.setup(PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Calculate fraction of the answer to display
    submitted_watt_seconds += watt_seconds
    displayed_answer = answer[:int(submitted_watt_seconds)] # one character per watt second, maybe adjust this later, or even
        # use a more complex formula, e.g., calculating the time it took the model to generate the answer and infer watt seconds
        # from that
    return jsonify({
        "displayed_answer": displayed_answer,
        "answer_length": len(answer),
        "displayed_answer_length": len(displayed_answer),
    })

def check_timeout():
    global timeout_occured
    while True:
        time.sleep(10)  # Check every 10 seconds
        if displayed_answer and (time.time() - last_request_time > 20):
            print("Timeout reached. Resetting UI.")
            timeout_occured = True
            reset_state()

# Start timeout thread
timeout_thread = threading.Thread(target=check_timeout)
timeout_thread.daemon = True
timeout_thread.start()

async def main():
    await wait_for_pin_change()
    # Start the Flask app
    app.run(debug=True)

if __name__ == "__main__":
    asyncio.run(main())