from flask import Flask, request, jsonify, render_template
import time
import threading

from transformers import AutoModelForCausalLM, AutoTokenizer
# reduce memory usage and improve performance, using CUDA
#from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from codecarbon import EmissionsTracker

import requests


app = Flask(__name__)

# Simulated AI model
#def query_ai_model(question):
#    # Replace this with actual AI model query
#    answer = "This is the generated answer from the AI model."
#    estimated_watt_minutes = 0.5  # Example: 0.5 Watt Minutes
#    return answer, estimated_watt_minutes


# deepseekv3 CPU
#model_name = "deepseek/deepseekv3"
# deepseekv3 with CUDA - also change import above
#model = AutoModelForCausalLM.from_pretrained("deepseek/deepseekv3", torch_dtype=torch.float16)
#model = model.to("cuda")

# Load the model and tokenizer
#tokenizer = AutoTokenizer.from_pretrained(model_name)
#model = AutoModelForCausalLM.from_pretrained(model_name)

# deepseekv3 api version
#def query_ai_model(question):
#    # Tokenize the input question
#    inputs = tokenizer(question, return_tensors="pt")
#
#    # Generate the answer
#    with torch.no_grad():
#       outputs = model.generate(**inputs, max_length=100)
#
#    # Decode the generated tokens to text
#    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
#
#    # Estimate the cost in Watt Minutes (example calculation)
#    # This is a placeholder; replace with actual energy consumption metrics.
#    estimated_watt_minutes = len(answer.split()) * 0.01  # Example: 0.01 Watt Minutes per word
#
#    return answer, estimated_watt_minutes


# deepseekv3 with "real" estiamated watt minutes / carbon footprint
#def query_ai_model(question):
#    tracker = EmissionsTracker()
#    tracker.start()
#
#    inputs = tokenizer(question, return_tensors="pt")
#    with torch.no_grad():
#        outputs = model.generate(**inputs, max_length=100)
#    answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
#
#    tracker.stop()
#    emissions = tracker.final_emissions
#    estimated_watt_minutes = emissions * 1000 / 60  # Convert kgCO2 to Watt Minutes (example)
#
#    return answer, estimated_watt_minutes

# ollama
def query_ai_model(question):
    # Ollama API endpoint
    url = "http://localhost:11434/api/generate"

    # Payload for the API request
    payload = {
        "model": "llama2",  # Replace with the model you pulled
        "prompt": question,
        "stream": False  # Set to True if you want streaming responses
    }

    # Send the request to Ollama
    response = requests.post(url, json=payload)
    response_data = response.json()

    # Extract the generated answer
    answer = response_data.get("response", "")

    # Estimate the cost in Watt Minutes (example calculation)
    # Replace with actual energy consumption metrics.
    estimated_watt_minutes = len(answer.split()) * 0.01  # Example: 0.01 Watt Minutes per word

    return answer, estimated_watt_minutes

# Global variables to track answer and progress
current_answer = ""
displayed_answer = ""
estimated_watt_minutes = 0
last_request_time = time.time()

def reset_state():
    global current_answer, displayed_answer, estimated_watt_minutes, last_request_time
    current_answer = ""
    displayed_answer = ""
    estimated_watt_minutes = 0
    last_request_time = time.time()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask_question():
    global current_answer, displayed_answer, estimated_watt_minutes, last_request_time
    reset_state()

    question = request.json.get("question")
    if not question:
        return jsonify({"error": "Question is required"}), 400

    # Query AI model
    answer, watt_minutes = query_ai_model(question)
    current_answer = answer
    estimated_watt_minutes = watt_minutes

    # Convert Watt Minutes to Watt Seconds
    estimated_watt_seconds = watt_minutes * 60

    return jsonify({
        "estimated_watt_seconds": estimated_watt_seconds,
        "message": "Question received. Submit Watt seconds to display the answer."
    })

@app.route("/submit_watt_seconds", methods=["POST"])
def submit_watt_seconds():
    global displayed_answer, last_request_time

    watt_seconds = request.json.get("watt_seconds")
    if not watt_seconds:
        return jsonify({"error": "Watt seconds are required"}), 400

    # Update last request time
    last_request_time = time.time()

    # Calculate fraction of the answer to display
    total_watt_seconds = estimated_watt_minutes * 60
    fraction = min(watt_seconds / total_watt_seconds, 1.0)
    displayed_answer = current_answer[:int(fraction * len(current_answer))]

    return jsonify({
        "displayed_answer": displayed_answer,
        "fraction_displayed": fraction
    })

def check_timeout():
    while True:
        time.sleep(10)  # Check every 10 seconds
        if current_answer and (time.time() - last_request_time > 60):
            print("Timeout reached. Resetting UI.")
            reset_state()

# Start timeout thread
timeout_thread = threading.Thread(target=check_timeout)
timeout_thread.daemon = True
timeout_thread.start()

if __name__ == "__main__":
    app.run(debug=True)