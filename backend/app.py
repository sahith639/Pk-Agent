import schedule
import threading
import time
from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import json_util  # To handle JSON serialization
from datetime import datetime
import json
from openai import OpenAI
from flask_cors import CORS  # Import CORS
from bson import ObjectId

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure MongoDB client
mongo_uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(mongo_uri)
db = mongo_client["pk-agent"]  # Database name
tasks_collection = db["tasks"]  # Collection for storing tasks

# Configure OpenAI client with DeepSeek base URL
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
)


def serialize_task(task):
    """
    Serialize MongoDB document to JSON, converting ObjectId to string.
    """
    if "_id" in task:
        task["_id"] = str(task["_id"])
    return task


def generate_subtasks(user_input):
    """
    Use the DeepSeek API to generate subtasks based on the user's input.
    """
    # Craft a prompt for the AI to generate subtasks
    prompt = f"""
    The user has the following goal: "{user_input}".
    Break this goal into smaller subtasks with estimated time to complete each subtask and a deadline for each.
    Return the response in the following format without any text before it:
     [
            {{
                "task": "subtask description",
                "time_required": "estimated time (e.g., 1 hour)",
                "deadline": "deadline (e.g., 2023-10-15)"
            }}
    ]   
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )
        # Print the raw response for debugging
        raw_response = response.choices[0].message.content
        print("DeepSeek API Raw Response:", raw_response)

        # Attempt to parse the response as JSON
        try:
            subtasks = json.loads(raw_response)
            return subtasks
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON response from DeepSeek API: {e}")
            print("Raw Response:", raw_response)  # Print the raw response for debugging
            return None
    except Exception as e:
        print(f"Error calling DeepSeek API: {str(e)}")
        return None


@app.route("/breakdown", methods=["POST"])
def task_breakdown():
    """
    Endpoint to handle task breakdown requests.
    """
    user_input = request.json.get("goal")
    if not user_input:
        return jsonify({"error": "No goal provided"}), 400

    # Generate subtasks using the DeepSeek API
    subtasks = generate_subtasks(user_input)
    if subtasks:
        # Save the task and subtasks to MongoDB
        task_document = {
            "goal": user_input,
            "subtasks": json.dumps(subtasks),  # Store subtasks as a JSON string
            "created_at": datetime.now(),
        }
        tasks_collection.insert_one(task_document)

        # Return the newly generated subtasks in the response
        return jsonify({"message": "Task breakdown successful", "subtasks": subtasks})
    else:
        return jsonify({"error": "Failed to generate subtasks"}), 500


@app.route("/subtasks")
def get_tasks():
    """
    Endpoint to fetch all tasks from MongoDB.
    """
    try:
        tasks = list(tasks_collection.find({}))
        all_subtasks = []
        for task in tasks:
            subtasks_json_string = task.get("subtasks")
            if subtasks_json_string:
                try:
                    # Parse the JSON string and add subtasks to the list
                    subtasks = json.loads(subtasks_json_string)
                    all_subtasks.extend(subtasks)
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON for task {task['_id']}: {e}")
                    continue  # Skip this task and continue with the next one
        return jsonify(all_subtasks)  # Return the subtasks as a JSON response
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
        return jsonify({"error": "Failed to fetch tasks"}), 500


@app.route("/")
def index():
    return "Hello World"


def check_in(task):
    """
    Function to check in on a task and provide reminders or motivation.
    """
    print(f"Checking in for task: {task[0]['task']}")
    current_day = datetime.now().date()
    difference = (
        current_day - datetime.strptime(task[0]["deadline"], "%Y-%m-%d").date()
    ).days
    if difference < 0:
        user_response = input(f"Are you working on '{task[0]['task']}'? (yes/no): ")
        if "no" in user_response.lower():
            reason = input("Why are you not doing it? ")
            print(analyze_reason_and_motivate(task, reason))
        else:
            print("Good job! Continue what you are doing.")
    else:
        prompt = f"User passed the deadline for the '{task[0]['task']}'. Urge them to do the task soon and explain that there are other pending tasks too, which would affect their final goal adversely."
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            print(response.choices[0].message.content)
        except Exception as e:
            print(f"Error calling DeepSeek API: {str(e)}")
            return None


def analyze_reason_and_motivate(task, reason):
    """
    Analyze the reason for procrastination and provide motivation.
    """
    prompt = f"I am procrastinating on '{task[0]['task']}' due to '{reason}'. Analyze if the reason is strong and valid. If it's not, motivate me directly."
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling DeepSeek API: {str(e)}")
        return None


# Scheduler setup
scheduler_started = False
scheduler_lock = threading.Lock()


def run_scheduler():
    """
    Function to run the scheduler in a separate thread.
    """
    global scheduler_started

    # Use a lock to ensure the scheduler starts only once
    with scheduler_lock:
        if not scheduler_started:
            tasks = list(tasks_collection.find({}))
            print("Scheduling check_in job...")  # Debug message
            if tasks:
                schedule.every(2).minutes.do(check_in, task=tasks)
            scheduler_started = True

    while True:
        # Run scheduled tasks
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    # Start the scheduler thread only if it hasn't been started yet
    if not scheduler_started:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

    # Start Flask app
    app.run(debug=True, use_reloader=False)