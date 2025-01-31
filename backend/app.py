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
from datetime import timedelta

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


def parse_relative_deadline(deadline_str):
    """Parse a relative deadline string into an absolute date."""
    try:
        deadline = datetime.now()
        if "day" in deadline_str.lower():
            days = int(''.join(filter(str.isdigit, deadline_str)))
            deadline += timedelta(days=days)
        elif "week" in deadline_str.lower():
            weeks = int(''.join(filter(str.isdigit, deadline_str)))
            deadline += timedelta(weeks=weeks)
        else:
            deadline += timedelta(weeks=1)
    except:
        deadline = datetime.now() + timedelta(weeks=1)
    return deadline


def parse_breakdown_to_subtasks(breakdown, parent_task):
    """Parse the OpenAI response into structured subtasks."""
    try:
        # Clean the response by removing markdown code block markers and any leading/trailing whitespace
        cleaned_response = breakdown.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()
        
        print(f"Cleaned response for parsing: {cleaned_response}")
        
        # Parse the cleaned JSON response
        subtasks_data = json.loads(cleaned_response)
        
        # Ensure it's a list
        if not isinstance(subtasks_data, list):
            subtasks_data = [subtasks_data]
        
        # Process each subtask
        subtasks = []
        for subtask_data in subtasks_data:
            # Convert relative deadline to absolute date
            deadline = parse_relative_deadline(subtask_data.get('deadline', 'in 1 day'))
            
            # Get time required string or generate from estimated hours
            time_required = subtask_data.get('time_required')
            if not time_required and 'estimated_hours' in subtask_data:
                hours = float(subtask_data['estimated_hours'])
                if hours >= 24:
                    days = hours / 24
                    time_required = f"{int(days)} days"
                else:
                    time_required = f"{int(hours)} hours"
            
            subtask = {
                'task': subtask_data.get('task', ''),
                'time_required': time_required or '1 hour',
                'estimated_hours': float(subtask_data.get('estimated_hours', 1)),
                'deadline': deadline.isoformat(),
                'parent_goal': parent_task,
                'parent_goal_id': str(ObjectId()),  # Generate a new ObjectId for the parent goal
                'completed': False,
                'completed_at': None,
                'status': 'pending',
                'motivation_tips': subtask_data.get('motivation_tips', []),
                'checkpoints': subtask_data.get('checkpoints', []),
                'check_ins': []
            }
            subtasks.append(subtask)
        
        return subtasks
        
    except Exception as e:
        print(f"Error parsing breakdown: {str(e)}")
        print(f"Response was: {breakdown}")
        # Return a default subtask if parsing fails
        return [{
            'task': f"Work on {parent_task}",
            'time_required': '2 hours',
            'estimated_hours': 2,
            'deadline': (datetime.now() + timedelta(days=1)).isoformat(),
            'parent_goal': parent_task,
            'parent_goal_id': str(ObjectId()),  # Generate a new ObjectId for the parent goal
            'completed': False,
            'completed_at': None,
            'status': 'pending',
            'motivation_tips': ['Break the task into smaller steps', 'Take regular breaks'],
            'checkpoints': ['Start the task', 'Complete 50%', 'Review and finalize'],
            'check_ins': []
        }]


def generate_subtasks(user_input):
    """
    Use the DeepSeek API to generate subtasks based on the user's input.
    """
    prompt = f"""
    The user has the following goal: "{user_input}".
    Break this goal into smaller, actionable subtasks. For each subtask:
    1. Make it specific and clear
    2. Estimate realistic time required
    3. Set appropriate deadline considering the task complexity
    4. Add motivation tips specific to that subtask
    
    Return the response in the following format without any text before it:
    [
        {{
            "task": "subtask description",
            "time_required": "estimated time (e.g., 1 hour)",
            "deadline": "YYYY-MM-DD",
            "motivation_tips": "specific tips for this subtask"
        }}
    ]
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
        )
        return parse_breakdown_to_subtasks(response.choices[0].message.content, user_input)
    except Exception as e:
        print(f"Error calling DeepSeek API: {str(e)}")
        return None


@app.route("/breakdown", methods=["POST"])
def task_breakdown():
    """
    Endpoint to handle task breakdown requests.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
            
        goal = data.get("goal")
        if not goal:
            return jsonify({"error": "Goal is required"}), 400

        subtasks = generate_subtasks(goal)
        if not subtasks:
            return jsonify({"error": "Failed to generate subtasks"}), 500

        # Store tasks in MongoDB with additional fields
        stored_subtasks = []
        current_time = datetime.now()
        
        for subtask in subtasks:
            # Validate required fields
            if not all(key in subtask for key in ["task", "time_required", "deadline", "motivation_tips"]):
                continue  # Skip invalid subtasks
                
            task_doc = {
                "task": subtask["task"],
                "time_required": subtask["time_required"],
                "deadline": subtask["deadline"],
                "motivation_tips": subtask["motivation_tips"],
                "created_at": current_time,
                "last_check_in": None,
                "check_in_count": 0,
                "completed": False,
                "progress_notes": [],
                "parent_goal": goal
            }
            
            try:
                result = tasks_collection.insert_one(task_doc)
                task_doc["_id"] = str(result.inserted_id)
                stored_subtasks.append(task_doc)
            except Exception as e:
                print(f"Error storing subtask: {str(e)}")
                continue

        if not stored_subtasks:
            return jsonify({"error": "Failed to store any subtasks"}), 500

        return jsonify({
            "success": True,
            "message": f"Successfully created {len(stored_subtasks)} subtasks",
            "subtasks": stored_subtasks
        }), 201

    except Exception as e:
        print(f"Error in task breakdown: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/check-in", methods=["POST"])
def check_in_endpoint():
    """
    Endpoint to trigger a check-in for a task.
    """
    try:
        task_id = request.json.get("task_id")
        if not task_id:
            return jsonify({"error": "Task ID is required"}), 400

        # Find the task in the database
        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        current_time = datetime.now()
        deadline = datetime.strptime(task["deadline"], "%Y-%m-%d")
        time_left = deadline - current_time

        # Update check-in stats
        tasks_collection.update_one(
            {"_id": ObjectId(task_id)},
            {
                "$set": {"last_check_in": current_time},
                "$inc": {"check_in_count": 1}
            }
        )

        if time_left.days < 0:
            # Task is overdue
            prompt = f"""
            The user has missed the deadline for: "{task['task']}"
            Time overdue: {abs(time_left.days)} days
            Previous motivation tip: {task['motivation_tips']}
            
            Generate a motivational message that:
            1. Acknowledges the missed deadline without being negative
            2. Emphasizes that it's still important to complete the task
            3. Provides specific tips to get started right now
            4. Reminds them how this task fits into their larger goal
            """
        else:
            # Task is upcoming
            prompt = f"""
            The user has this upcoming task: "{task['task']}"
            Time remaining: {time_left.days} days
            Previous motivation tip: {task['motivation_tips']}
            
            Generate a motivational message that:
            1. Creates a sense of urgency without causing stress
            2. Provides specific tips to make progress today
            3. Reminds them of the benefits of completing this task early
            4. Suggests breaking the task into smaller chunks if needed
            """

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            motivation = response.choices[0].message.content

            return jsonify({
                "message": "Check-in recorded",
                "task": task["task"],
                "status": "overdue" if time_left.days < 0 else "upcoming",
                "days_remaining": time_left.days,
                "motivation": motivation,
                "check_in_count": task["check_in_count"] + 1
            })

        except Exception as e:
            print(f"Error generating motivation: {str(e)}")
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
        task_id = request.json.get("task_id")
        reason = request.json.get("reason")
        if not task_id or not reason:
            return jsonify({"error": "Task ID and reason are required"}), 400

        task = tasks_collection.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Store the procrastination reason for future analysis
        tasks_collection.update_one(
            {"_id": ObjectId(task_id)},
            {
                "$push": {
                    "progress_notes": {
                        "type": "procrastination",
                        "reason": reason,
                        "timestamp": datetime.now()
                    }
                }
            }
        )

        prompt = f"""
        Task: "{task['task']}"
        User's reason for not working: "{reason}"
        Previous motivation tip: {task['motivation_tips']}
        
        Analyze this situation and provide:
        1. Understanding of their challenge without judgment
        2. Practical solutions to overcome their specific reason
        3. A motivational message that addresses their concerns
        4. A small, easy first step they can take right now
        
        Keep the tone supportive and focus on solutions rather than the problem.
        """

        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            
            analysis = response.choices[0].message.content
            return jsonify({
                "message": "Reason analyzed",
                "motivation": analysis
            })

        except Exception as e:
            print(f"Error generating analysis: {str(e)}")
            return jsonify({"error": "Failed to analyze reason"}), 500

    except Exception as e:
        print(f"Error analyzing reason: {str(e)}")
        return jsonify({"error": "Failed to analyze reason"}), 500


@app.route("/toggle-task/<goal_id>/<task_id>", methods=["POST", "OPTIONS"])
def toggle_task_completion(goal_id, task_id):
    """
    Toggle the completion status of a specific task
    """
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
        
    try:
        print(f"\n=== Toggling Task Completion ===")
        print(f"Goal ID: {goal_id}")
        print(f"Task ID: {task_id}")
        
        # Validate ObjectIds
        if not ObjectId.is_valid(goal_id):
            error_msg = f"Invalid goal_id format: {goal_id}"
            print(error_msg)
            return jsonify({"error": error_msg}), 400
            
        if not ObjectId.is_valid(task_id):
            error_msg = f"Invalid task_id format: {task_id}"
            print(error_msg)
            return jsonify({"error": error_msg}), 400
            
        # Convert string IDs to ObjectId
        goal_obj_id = ObjectId(goal_id)
        task_obj_id = ObjectId(task_id)
        
        # Find the goal document
        goal = tasks_collection.find_one({"_id": goal_obj_id})
        
        if not goal:
            error_msg = f"Goal not found with ID: {goal_id}"
            print(error_msg)
            return jsonify({"error": error_msg}), 404
            
        print(f"Found goal: {goal.get('goal', 'Untitled')}")
            
        # Find and update the specific subtask
        updated = False
        if "subtasks" in goal and isinstance(goal["subtasks"], list):
            for subtask in goal["subtasks"]:
                subtask_id = subtask.get("_id")
                if isinstance(subtask_id, ObjectId):
                    subtask_id = str(subtask_id)
                elif not isinstance(subtask_id, str):
                    continue
                    
                print(f"Comparing task IDs: {subtask_id} == {task_id}")
                if subtask_id == task_id:
                    # Toggle the completed status
                    subtask["completed"] = not subtask.get("completed", False)
                    subtask["completed_at"] = datetime.now().isoformat() if subtask["completed"] else None
                    updated = True
                    print(f"Updated task completion status to: {subtask['completed']}")
                    break
        
        if not updated:
            error_msg = f"Task not found with ID: {task_id}"
            print(error_msg)
            return jsonify({"error": error_msg}), 404
            
        # Update the document in MongoDB
        result = tasks_collection.update_one(
            {"_id": goal_obj_id},
            {"$set": {"subtasks": goal["subtasks"]}}
        )
        
        if result.modified_count == 0:
            error_msg = "Failed to update task in database"
            print(error_msg)
            return jsonify({"error": error_msg}), 500
            
        print("Successfully updated task completion status")
        return jsonify({
            "success": True,
            "message": "Task status updated successfully",
            "completed": subtask["completed"]
        })
        
    except Exception as e:
        error_msg = f"Error toggling task completion: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500


def check_tasks_job():
    """
    Scheduled job to check tasks and trigger notifications.
    """
    try:
        current_time = datetime.now()
        tasks = list(tasks_collection.find({"completed": False}))
        
        for task in tasks:
            deadline = datetime.strptime(task["deadline"], "%Y-%m-%d")
            time_left = deadline - current_time
            
            # Check if we need to send a notification
            last_check_in = task.get("last_check_in")
            hours_since_check_in = float('inf')
            if last_check_in:
                hours_since_check_in = (current_time - last_check_in).total_seconds() / 3600

            # Determine if we should trigger a check-in based on urgency
            should_check_in = (
                (time_left.days <= 0) or  # Task is overdue
                (time_left.days <= 1 and hours_since_check_in >= 4) or  # Last day, check every 4 hours
                (time_left.days <= 3 and hours_since_check_in >= 8) or  # Last 3 days, check every 8 hours
                (hours_since_check_in >= 24)  # Regular check-in every 24 hours
            )

            if should_check_in:
                print(f"Triggering check-in for task: {task['task']}")
                # The actual check-in will be handled by the frontend when it polls

    except Exception as e:
        print(f"Error in check_tasks_job: {str(e)}")

# Schedule the check-in job
schedule.every(30).minutes.do(check_tasks_job)


# Scheduler setup
scheduler_started = False
scheduler_lock = threading.Lock()


def run_scheduler():
    """
    Function to run the scheduler in a separate thread.
    """
    while True:
        schedule.run_pending()
        time.sleep(1)


# Start the scheduler in a separate thread
scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()


@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'http://localhost:3000')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response


@app.route("/subtasks", methods=["GET"])
def get_subtasks():
    """
    Get all subtasks from all goals, flattened into a single list
    """
    try:
        print("\n=== Fetching Subtasks ===")
        print("Fetching subtasks from MongoDB...")
        
        # Get all goals that have subtasks
        goals = list(tasks_collection.find({"subtasks": {"$exists": True, "$ne": []}}))
        print(f"Found {len(goals)} goals")
        
        # Flatten all subtasks into a single list with parent goal info
        flattened_subtasks = []
        for goal in goals:
            print(f"Processing goal {goal.get('_id')}: {goal.get('goal', 'Untitled')}")
            
            if not isinstance(goal.get("subtasks"), list):
                print(f"No subtasks found for goal {goal.get('_id')}")
                continue
                
            for subtask in goal["subtasks"]:
                if not isinstance(subtask, dict):
                    print(f"Invalid subtask format in goal {goal.get('_id')}: {subtask}")
                    continue
                    
                # Ensure subtask has an _id
                if "_id" not in subtask:
                    subtask["_id"] = str(ObjectId())
                elif isinstance(subtask["_id"], ObjectId):
                    subtask["_id"] = str(subtask["_id"])
                    
                # Add parent goal information
                subtask["parent_goal"] = goal.get("goal", "Untitled")
                subtask["parent_goal_id"] = str(goal["_id"])
                
                required_fields = {
                    "task": "Untitled Task",
                    "time_required": "Not specified",
                    "deadline": (datetime.now() + timedelta(weeks=1)).isoformat(),
                    "motivation_tips": []
                }
                
                for field, default in required_fields.items():
                    if field not in subtask:
                        print(f"Missing {field} in subtask, using default: {default}")
                        subtask[field] = default
                    elif field == "motivation_tips" and not isinstance(subtask[field], list):
                        print(f"Invalid {field} format, using default: {default}")
                        subtask[field] = default
                
                # Ensure completed and completed_at fields exist
                if "completed" not in subtask:
                    subtask["completed"] = False
                if "completed_at" not in subtask:
                    subtask["completed_at"] = None
                    
                print(f"Adding subtask: {subtask.get('task')} (ID: {subtask['_id']})")
                flattened_subtasks.append(subtask)
        
        print(f"Returning {len(flattened_subtasks)} flattened subtasks")
        return jsonify(flattened_subtasks)
        
    except Exception as e:
        error_msg = f"Error fetching subtasks: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500


@app.route("/get-tasks", methods=["GET"])
def get_tasks():
    """
    Endpoint to fetch all tasks.
    """
    try:
        # Fetch all tasks from MongoDB
        tasks = list(tasks_collection.find())
        
        # Convert ObjectId to string for JSON serialization
        for task in tasks:
            task["_id"] = str(task["_id"])
        
        return jsonify(tasks), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/add-task", methods=["POST"])
def add_task():
    """
    Add a new task and generate subtasks with OpenAI
    """
    try:
        data = request.json
        task = data.get("task")
        
        if not task:
            return jsonify({"error": "Task is required"}), 400

        print(f"\n=== Adding New Task ===")
        print(f"Task: {task}")
            
        # Create a new task document
        task_doc = {
            "goal": task,
            "created_at": datetime.now().isoformat(),
            "subtasks": [],
            "status": "active"  # active, completed, delayed
        }
        
        # Insert the task into MongoDB
        result = tasks_collection.insert_one(task_doc)
        goal_id = str(result.inserted_id)
        print(f"Created task with ID: {goal_id}")
        
        # Get task breakdown from OpenAI
        try:
            print("Getting task breakdown from OpenAI...")
            prompt = f"""Break down this goal into 3-5 specific, actionable subtasks: "{task}"

            For each subtask, provide:
            1. A clear, specific action item
            2. Estimated time to complete (e.g. "2 hours", "3 days")
            3. Suggested deadline relative to now (e.g. "in 2 days", "by next week")
            4. 2-3 motivation tips specific to this subtask
            5. Key milestones or checkpoints

            Format as JSON array with these fields:
            {{
                "task": "specific action",
                "estimated_hours": number,
                "deadline": "relative deadline",
                "motivation_tips": ["tip1", "tip2"],
                "checkpoints": ["milestone1", "milestone2"]
            }}"""
            
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a helpful task breakdown and productivity assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse the response
            subtasks_str = response.choices[0].message.content
            print("OpenAI Response:", subtasks_str)
            
            try:
                subtasks = parse_breakdown_to_subtasks(subtasks_str, task)
                if not isinstance(subtasks, list):
                    raise ValueError("Expected a list of subtasks")
                    
                # Process each subtask
                processed_subtasks = []
                for subtask in subtasks:
                    # Generate unique ID
                    subtask_id = str(ObjectId())
                    
                    # Convert estimated hours to duration string
                    hours = subtask.get("estimated_hours", 1)
                    if hours < 1:
                        time_required = f"{int(hours * 60)} minutes"
                    elif hours == 1:
                        time_required = "1 hour"
                    else:
                        time_required = f"{hours} hours"
                    
                    # Parse relative deadline
                    deadline_str = subtask.get("deadline", "in 1 week")
                    try:
                        deadline = datetime.now()
                        if "day" in deadline_str.lower():
                            days = int(''.join(filter(str.isdigit, deadline_str)))
                            deadline += timedelta(days=days)
                        elif "week" in deadline_str.lower():
                            weeks = int(''.join(filter(str.isdigit, deadline_str)))
                            deadline += timedelta(weeks=weeks)
                        else:
                            deadline += timedelta(weeks=1)
                    except:
                        deadline = datetime.now() + timedelta(weeks=1)
                    
                    processed_subtask = {
                        "_id": subtask_id,
                        "task": subtask.get("task", "Untitled Task"),
                        "time_required": time_required,
                        "estimated_hours": hours,
                        "deadline": deadline.isoformat(),
                        "motivation_tips": subtask.get("motivation_tips", []),
                        "checkpoints": subtask.get("checkpoints", []),
                        "completed": False,
                        "completed_at": None,
                        "status": "pending",  # pending, in_progress, completed, delayed
                        "check_ins": [],
                        "parent_goal_id": goal_id
                    }
                    processed_subtasks.append(processed_subtask)
                
                print(f"Generated {len(processed_subtasks)} subtasks")
                
                # Update the task with subtasks
                update_result = tasks_collection.update_one(
                    {"_id": ObjectId(goal_id)},
                    {"$set": {"subtasks": processed_subtasks}}
                )
                
                if update_result.modified_count == 0:
                    print("Warning: Failed to update task with subtasks")
                    
                return jsonify({
                    "success": True,
                    "message": "Task added successfully",
                    "goal_id": goal_id,
                    "subtasks": processed_subtasks
                }), 201
                
            except json.JSONDecodeError as e:
                print(f"Error parsing OpenAI response: {e}")
                print("Response was:", subtasks_str)
                return jsonify({"error": "Failed to parse task breakdown"}), 500
                
        except Exception as e:
            print(f"Error getting task breakdown: {e}")
            return jsonify({"error": "Failed to generate subtasks"}), 500
            
    except Exception as e:
        error_msg = f"Error adding task: {str(e)}"
        print(error_msg)
        return jsonify({"error": error_msg}), 500


def generate_motivation(task_info, status, reason=None):
    """Generate a motivational response based on task status and reason."""
    try:
        prompt = f"""Task: {task_info.get('task', 'your task')}
Status: {status}
Reason: {reason if reason else 'No reason provided'}

Please provide:
1. A supportive and understanding response
2. 2-3 specific suggestions to help overcome any challenges
3. A motivational message to encourage progress

Format the response as a JSON object with these fields:
{{
    "response": "The main response message",
    "suggestions": ["suggestion1", "suggestion2", "suggestion3"],
    "motivation": "A brief motivational message"
}}"""

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are an empathetic productivity coach."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,
        )

        # Clean the response
        response_text = response.choices[0].message.content.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Parse the JSON response
        motivation_data = json.loads(response_text)
        
        # Ensure all required fields are present
        motivation_data.setdefault('response', "Keep going! Every step forward counts.")
        motivation_data.setdefault('suggestions', [
            "Break the task into smaller, manageable steps",
            "Take short breaks to maintain focus",
            "Celebrate small wins along the way"
        ])
        motivation_data.setdefault('motivation', "You've got this! Progress is progress, no matter how small.")
        
        return motivation_data

    except Exception as e:
        print(f"Error generating motivation: {str(e)}")
        # Return a default response if generation fails
        return {
            "response": "I understand you're facing some challenges. Remember that setbacks are temporary and part of the journey.",
            "suggestions": [
                "Break the task into smaller, more manageable steps",
                "Take care of your health first - it's okay to rest when needed",
                "Consider adjusting your timeline to reduce pressure"
            ],
            "motivation": "Every small step counts. You've got this!"
        }

@app.route("/check-in/<goal_id>/<task_id>", methods=["POST"])
def check_in(goal_id, task_id):
    """Handle task check-ins and provide motivation."""
    try:
        data = request.json
        status = data.get("status", "in_progress")
        reason = data.get("reason", "")

        # Find the task in MongoDB
        task = db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            return jsonify({"error": "Task not found"}), 404

        # Generate motivation based on status and reason
        motivation = generate_motivation(task, status, reason)

        # Create check-in record
        check_in = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "reason": reason,
            "response": motivation.get("response"),
            "suggestions": motivation.get("suggestions", []),
            "motivation": motivation.get("motivation")
        }

        # Update task in MongoDB
        update_result = db.tasks.update_one(
            {"_id": ObjectId(task_id)},
            {
                "$set": {
                    "status": status,
                    "completed": status == "completed",
                    "completed_at": datetime.now().isoformat() if status == "completed" else None
                },
                "$push": {"check_ins": check_in}
            }
        )

        if update_result.modified_count == 0:
            return jsonify({"error": "Failed to update task"}), 500

        return jsonify({
            "success": True,
            "motivation": motivation
        })

    except Exception as e:
        print(f"Error in check-in: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)