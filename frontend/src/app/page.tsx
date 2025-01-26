"use client"; // Mark this as a Client Component

import { useState, useEffect } from "react";

export default function Home() {
  const [task, setTask] = useState(""); // State for the input field
  const [subtasks, setSubtasks] = useState([]); // State to store fetched subtasks
  const [checkInTask, setCheckInTask] = useState(null); // Task for check-in
  const [reason, setReason] = useState(""); // User's reason for procrastination

  // Function to handle task submission
  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      // Send the task to the backend
      const response = await fetch("http://127.0.0.1:5000/breakdown", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ goal: task }),
      });

      if (!response.ok) {
        throw new Error(`Failed to submit task: ${response.statusText}`);
      }

      const data = await response.json();
      console.log("Task Submission Response:", data);

      if (data.subtasks) {
        // Update the subtasks state with the newly generated subtasks
        setSubtasks(data.subtasks);
        setTask(""); // Clear the input field
      }
    } catch (error) {
      console.error("Error:", error);
      alert(`Error: ${error.message}`);
    }
  };

  // Function to fetch subtasks from the backend
  const fetchSubtasks = async () => {
    try {
      const response = await fetch("http://127.0.0.1:5000/subtasks");
      if (!response.ok) {
        throw new Error(`Failed to fetch subtasks: ${response.statusText}`);
      }

      const data = await response.json();

      // Ensure data is an array
      if (Array.isArray(data)) {
        setSubtasks(data);
      } else {
        console.error("Expected an array but got:", data);
        setSubtasks([]); // Set to an empty array to avoid errors
      }
    } catch (error) {
      console.error("Error fetching subtasks:", error);
      setSubtasks([]); // Set to an empty array to avoid errors
    }
  };

  // Function to handle subtask deletion
  const handleDeleteSubtask = async (subtaskId) => {
    try {
      // Send the subtask ID to the backend for deletion
      const response = await fetch("http://127.0.0.1:5000/delete-subtask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ subtask_id: subtaskId }),
      });

      if (!response.ok) {
        throw new Error(`Failed to delete subtask: ${response.statusText}`);
      }

      // Remove the deleted subtask from the frontend state
      setSubtasks((prevSubtasks) =>
        prevSubtasks.filter((subtask) => subtask._id !== subtaskId)
      );
    } catch (error) {
      console.error("Error deleting subtask:", error);
      alert("An error occurred while deleting the subtask. Please try again.");
    }
  };

  // Function to handle check-in response
  const handleCheckInResponse = async (isWorking: boolean) => {
    try {
      if (isWorking) {
        // User is working on the task
        alert("Good job! Keep it up.");
      } else {

        // User is not working on the task, ask for a reason
      const requestBody = {
        task_id: checkInTask._id,
        reason: reason,
      };
      console.log("Sending request to /analyze-reason:", requestBody); // Debug log

        // User is not working on the task, ask for a reason
        const response = await fetch("http://127.0.0.1:5000/analyze-reason", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
          throw new Error("Failed to analyze reason");
        }

        const data = await response.json();
        alert(data.motivation); // Show motivation message
      }

      // Reset check-in state
      setCheckInTask(null);
      setReason("");
    } catch (error) {
      console.error("Error during check-in:", error);
      alert("An error occurred during check-in. Please try again.");
    }
  };

  // Function to trigger check-ins
  const triggerCheckIn = async () => {
    try {
      console.log("Triggering check-in..."); // Debug log
      // Fetch all tasks from the backend
      const response = await fetch("http://127.0.0.1:5000/subtasks");
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks: ${response.statusText}`);
      }

      const tasks = await response.json();

      // Check if any task is due or overdue
      const now = new Date();
      for (const task of tasks) {
        const deadline = new Date(task.deadline);
        if (now > deadline) {
          // Task is overdue, trigger a check-in
          setCheckInTask(task);
          break;
        }
      }
    } catch (error) {
      console.error("Error triggering check-in:", error);
    }
  };

  // Fetch subtasks when the component mounts
  useEffect(() => {
    fetchSubtasks();
  }, []);

  // Trigger check-ins periodically (e.g., every 2 minutes)
  useEffect(() => {
    const interval = setInterval(triggerCheckIn, 2 * 60 * 1000); // 2 minutes
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: "20px" }}>
      <h1>Procrastination Kill App</h1>

      {checkInTask && (
        <div className="check-in-modal">
          <h2>Check-In: {checkInTask.task}</h2>
          <p>Deadline: {checkInTask.deadline}</p>
          <p>Are you working on this task?</p>
          <button
            className="yes-button"
            onClick={() => handleCheckInResponse(true)}
          >
            Yes
          </button>
          <button
            className="no-button"
            onClick={() => handleCheckInResponse(false)}
          >
            No
          </button>

          {!checkInTask.isWorking && (
            <div>
              <textarea
                placeholder="Why are you not doing it?"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button
                className="submit-button"
                onClick={() => handleCheckInResponse(false)}
              >
                Submit
              </button>
            </div>
          )}
        </div>
      )}

      <div className="task-input">
        <input
          type="text"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Enter your task"
          required
        />
        <button type="submit">Add Task</button>
      </div>

      <div className="subtasks-list">
        <h2>Subtasks</h2>
        {subtasks.length > 0 ? (
          <table className="subtasks-table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Time Required</th>
                <th>Deadline</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {subtasks.map((subtask, index) => (
                <tr key={index}>
                  <td>
                    <input
                      type="checkbox"
                      onChange={() => handleDeleteSubtask(subtask._id)}
                    />
                    <strong>{subtask.task}</strong>
                  </td>
                  <td>{subtask.time_required}</td>
                  <td>{subtask.deadline}</td>
                  <td>
                    <button onClick={() => handleDeleteSubtask(subtask._id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No subtasks available.</p>
        )}
      </div>
    </div>
  );
}
