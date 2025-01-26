# app.py
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

load_dotenv()


app = Flask(__name__)

# Configure MongoDB client
mongo_uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(mongo_uri)
db = mongo_client["pk-agent"]  # Database name
tasks_collection = db["tasks"]  # Collection for storing tasks
sample_task = {
    "task": "Review the homework instructions and gather all necessary materials",
    "time_required": "30 minutes",
    "deadline": "2023-10-15",
}

# Configure OpenAI client with DeepSeek base URL
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com"
)


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
            max_tokens=500,
        )
        return response.choices[0].message.content
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
            "subtasks": subtasks,
            "created_at": datetime.now(),
        }
        tasks_collection.insert_one(task_document)
        return jsonify(subtasks)
    else:
        return jsonify({"error": "Failed to generate subtasks"}), 500


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
                subtasks = json.loads(subtasks_json_string)
                all_subtasks.extend(subtasks)
        return all_subtasks
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
        return jsonify({"error": "Failed to fetch tasks"}), 500


@app.route("/")
def index():
    return "Hello World"


def check_in(task):
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
            print("Good job continue what you are doing")
    else:
        prompt = f"User passed the deadline for the '{task[0]['task']}'. Urge him to do the task soon and explain that there are other pending tasks too and it would effect his final goal in a adverse way"
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
    prompt = f"Iam is procrastinating on '{task[0]['task']}' due to '{reason}'. Analyze if the reason is a strong and valid reason and if its not then motivate me dont talk like a third part just adress the message to the me directly"
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


# def update_streak(task_name):
#     if task_name not in streaks:
#         streaks[task_name] = 0
#     streaks[task_name] += 1
#     print(f"Great job! You're on a {streaks[task_name]} day streak for {task_name}!")


def run_scheduler():
    tasks = get_tasks()
    print(tasks)

    schedule.every(1).minutes.do(check_in, task=tasks)
    while True:

        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":

    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()
    app.run(debug=True)
