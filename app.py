# app.py
from flask import Flask, request, jsonify
import openai
import schedule
import time
import threading

app = Flask(__name__)

# Configure your OpenAI API key
openai.api_key = 'YOUR_OPENAI_API_KEY'

tasks = {}

@app.route('/task', methods=['POST'])
def create_task():
    data = request.json
    task_name = data['task']
    time_slot = data['time']  # Expected format 'HH:MM'
    tasks[task_name] = time_slot
    schedule.every().day.at(time_slot).do(check_in, task=task_name)
    return jsonify({"status": "Task created", "task": task_name})

def check_in(task):
    print(f"Checking in for task: {task}")
    # Here you would implement a mechanism to ask the user if they're doing the task
    user_response = input(f"Are you working on '{task}'? (yes/no): ")
    if user_response.lower() == 'no':
        reason = input("Why are you not doing it? ")
        motivate_user(task, reason)

def motivate_user(task, reason):
    prompt = f"User is procrastinating on '{task}' due to '{reason}'. Motivate them."
    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        max_tokens=100
    )
    message = response.choices[0].text.strip()
    print(f"Motivational Message: {message}")

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    # Run the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()
    app.run(debug=True)