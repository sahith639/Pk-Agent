"use client"; // Mark this as a Client Component

import { useState, useEffect } from "react";

export default function Home() {
  const [task, setTask] = useState(""); // State for the input field
  const [subtasks, setSubtasks] = useState([]); // State to store fetched subtasks

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
        throw new Error("Failed to submit task");
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
    }
  };

  // Function to fetch subtasks from the backend
  const fetchSubtasks = async () => {
    try {
      const response = await fetch("http://127.0.0.1:5000/subtasks");
      if (!response.ok) {
        throw new Error("Failed to fetch subtasks");
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

  // Fetch subtasks when the component mounts
  useEffect(() => {
    fetchSubtasks();
  }, []);

  return (
    <div style={{ padding: "20px" }}>
      <h1>Procrastination Kill App</h1>

      {/* Input field for the task */}
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Enter your task"
          required
          style={{ padding: "10px", width: "300px", marginRight: "10px" }}
        />
        <button type="submit" style={{ padding: "10px 20px" }}>
          Add Task
        </button>
      </form>

      {/* Display fetched subtasks */}
      <div style={{ marginTop: "20px" }}>
        <h2>Subtasks</h2>
        {subtasks.length > 0 ? (
          <ul>
            {subtasks.map((subtask, index) => (
              <li key={index} style={{ marginBottom: "10px" }}>
                <strong>{subtask.task}</strong>
                <p>Time Required: {subtask.time_required}</p>
                <p>Deadline: {subtask.deadline}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p>No subtasks available.</p>
        )}
      </div>
    </div>
  );
}
