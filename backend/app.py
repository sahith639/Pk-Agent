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
CORS(app, origins=["http://localhost:3000"])  # Enable CORS for all routes

# Configure MongoDB client
mongo_uri = os.getenv("MONGO_URI")
mongo_client = MongoClient(mongo_uri)
db = mongo_client["pk-agent"]  # Database name
tasks_collection = db["tasks"]  # Collection for storing tasks

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
            max_tokens=1000,
        )
        # Print the raw response for debugging
        raw_response = response.choices[0].message.content
        print("DeepSeek API Raw Response:", raw_response)

        # Attempt to parse the response as JSON
        try:
            subtasks = json.loads(raw_response)
            # Add a unique _id field to each subtask
            for subtask in subtasks:
                subtask["_id"] = str(ObjectId())  # Generate a new ObjectId
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
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415  # 415 Unsupported Media Type

    user_input = request.json.get("goal")
    if not user_input:
        return jsonify({"error": "No goal provided"}), 400

    # Generate subtasks using the DeepSeek API
    subtasks = generate_subtasks(user_input)
    if subtasks:
        # Save the task and subtasks to MongoDB
        task_document = {
            "goal": user_input,
            "subtasks": subtasks,  # Store subtasks as an array of objects
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
            subtasks = task.get("subtasks", [])
            all_subtasks.extend(subtasks)
        return jsonify(all_subtasks)  # Return the subtasks as a JSON response
    except Exception as e:
        print(f"Error fetching tasks: {str(e)}")
        return jsonify({"error": "Failed to fetch tasks"}), 500


@app.route("/delete-subtask", methods=["POST"])
def delete_subtask():
    """
    Endpoint to delete a subtask from the database.
    """
    try:
        # Get the subtask ID from the request
        subtask_id = request.json.get("subtask_id")
        if not subtask_id:
            return jsonify({"error": "Subtask ID is required"}), 400

        # Find the task containing the subtask and remove the subtask
        result = tasks_collection.update_many(
            {},  # Search all documents
            {"$pull": {"subtasks": {"_id": subtask_id}}}  # Remove the subtask with the matching ID
        )

        if result.modified_count > 0:
            return jsonify({"message": "Subtask deleted successfully"})
        else:
            return jsonify({"error": "Subtask not found"}), 404
    except Exception as e:
        print(f"Error deleting subtask: {str(e)}")
        return jsonify({"error": "Failed to delete subtask"}), 500


@app.route("/check-in", methods=["POST"])
def check_in_endpoint():
    """
    Endpoint to trigger a check-in for a task.
    """
    try:
        # Get the task ID from the request
        task_id = request.json.get("task_id")
        if not task_id:
            return jsonify({"error": "Task ID is required"}), 400

        # Find the task in the database
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Perform the check-in
        current_day = datetime.now().date()
        deadline = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
        difference = (current_day - deadline).days

        if difference < 0:
            # Task is not overdue
            return jsonify({
                "message": "Check-in triggered",
                "task": task["task"],
                "status": "pending",
                "deadline": task["deadline"]
            })
        else:
            # Task is overdue
            prompt = f"User passed the deadline for the '{task['task']}'. Urge them to do the task soon and explain that there are other pending tasks too, which would affect their final goal adversely."
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                )
                return jsonify({
                    "message": "Check-in triggered",
                    "task": task["task"],
                    "status": "overdue",
                    "motivation": response.choices[0].message.content
                })
            except Exception as e:
                print(f"Error calling DeepSeek API: {str(e)}")
                return jsonify({"error": "Failed to generate motivation"}), 500

    except Exception as e:
        print(f"Error during check-in: {str(e)}")
        return jsonify({"error": "Failed to perform check-in"}), 500


@app.route("/analyze-reason", methods=["POST"])
def analyze_reason_endpoint():
    """
    Endpoint to analyze the user's reason for procrastination and provide motivation.
    """
    try:
        # Get the task ID and reason from the request
        task_id = request.json.get("task_id")
        reason = request.json.get("reason")
        if not task_id or not reason:
            return jsonify({"error": "Task ID and reason are required"}), 400

        # Find the task in the database
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Analyze the reason and provide motivation
        prompt = f"I am procrastinating on '{task['task']}' due to '{reason}'. Analyze if the reason is strong and valid. If it's not, motivate me directly."
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            return jsonify({
                "message": "Reason analyzed",
                "motivation": response.choices[0].message.content
            })
        except Exception as e:
            print(f"Error calling DeepSeek API: {str(e)}")
            return jsonify({"error": "Failed to generate motivation"}), 500

    except Exception as e:
        print(f"Error analyzing reason: {str(e)}")
        return jsonify({"error": "Failed to analyze reason"}), 500
    

# Scheduler setup
scheduler_started = False
scheduler_lock = threading.Lock()


def run_scheduler():
    """
    Function to run the scheduler in a separate thread.
    """
    def check_in_job():
        try:
            # Fetch all tasks from the database
            tasks = list(tasks_collection.find({}))
            for task in tasks:
                # Trigger a check-in for each task
                current_day = datetime.now().date()
                deadline = datetime.strptime(task["deadline"], "%Y-%m-%d").date()
                difference = (current_day - deadline).days

                if difference < 0:
                    print(f"Checking in for task: {task['task']}")
                else:
                    print(f"Task '{task['task']}' is overdue!")

        except Exception as e:
            print(f"Error during scheduled check-in: {str(e)}")

    # Schedule the check-in job to run every 2 minutes
    schedule.every(2).minutes.do(check_in_job)

    # Run the scheduler
    while True:
        schedule.run_pending()
        time.sleep(1)

# Start the scheduler in a separate thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()


if __name__ == "__main__":
    # Start the scheduler thread only if it hasn't been started yet
    if not scheduler_started:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

    # Start Flask app
    app.run(debug=True, use_reloader=False)