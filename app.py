# app.py
from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()

app = Flask(__name__)

# Configure OpenAI client with DeepSeek base URL
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

def generate_subtasks(user_input):
    """
    Use the DeepSeek API to generate subtasks based on the user's input.
    """
    # Craft a prompt for the AI to generate subtasks
    prompt = f"""
    The user has the following goal: "{user_input}".
    Break this goal into smaller subtasks with estimated time to complete each subtask and a deadline for each.
    Return the response in the following JSON format:
    {{
        "subtasks": [
            {{
                "task": "subtask description",
                "time_required": "estimated time (e.g., 1 hour)",
                "deadline": "deadline (e.g., 2023-10-15)"
            }}
        ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling DeepSeek API: {str(e)}")
        return None

@app.route('/breakdown', methods=['POST'])
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
        return jsonify(subtasks)
    else:
        return jsonify({"error": "Failed to generate subtasks"}), 500

@app.route('/')
def index():
    return "Hello World"

if __name__ == '__main__':
    app.run(debug=True)
