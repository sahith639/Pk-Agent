"use client"; // Mark this as a Client Component

import { useState, useEffect } from "react";

interface Subtask {
  _id: string;
  task: string;
  time_required: string;
  estimated_hours: number;
  deadline: string;
  parent_goal: string;
  parent_goal_id: string;
  completed: boolean;
  completed_at: string | null;
  status: 'pending' | 'in_progress' | 'completed' | 'delayed';
  motivation_tips: string[];
  checkpoints: string[];
  check_ins: Array<{
    timestamp: string;
    status: string;
    reason?: string;
    response?: string;
    suggestions?: string[];
    motivation?: string;
  }>;
}

export default function Home() {
  const [task, setTask] = useState("");
  const [subtasks, setSubtasks] = useState<Subtask[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSubtasks, setIsLoadingSubtasks] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<Subtask | null>(null);
  const [checkInReason, setCheckInReason] = useState("");
  const [showCheckIn, setShowCheckIn] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(0);

  // Function to handle task submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      console.log("\n=== Submitting New Task ===");
      console.log("Task:", task);
      
      setIsLoading(true);
      setError(null);
      
      const response = await fetch("http://127.0.0.1:5000/add-task", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ task }),
      });

      console.log("Response status:", response.status);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to add task");
      }

      const data = await response.json();
      console.log("Response data:", data);
      
      if (data.success) {
        setTask("");
        // Update subtasks with the new data
        if (data.subtasks) {
          setSubtasks(prev => [...data.subtasks, ...prev]);
        } else {
          // Fetch all subtasks if new ones weren't returned
          fetchSubtasks(true);
        }
      }
    } catch (error) {
      console.error("Error submitting task:", error);
      setError(error instanceof Error ? error.message : "Failed to add task");
    } finally {
      setIsLoading(false);
    }
  };

  // Function to handle task check-in
  const handleCheckIn = async (status: string) => {
    if (!selectedTask) return;

    try {
      console.log("\n=== Task Check-in ===");
      console.log("Task:", selectedTask.task);
      console.log("Status:", status);
      console.log("Reason:", checkInReason);
      
      const response = await fetch(
        `http://127.0.0.1:5000/check-in/${selectedTask.parent_goal_id}/${selectedTask._id}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            status,
            reason: checkInReason,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to update task");
      }

      const data = await response.json();
      
      if (data.success) {
        // Update the local state
        setSubtasks(prev => prev.map(subtask => {
          if (subtask._id === selectedTask._id) {
            return {
              ...subtask,
              status,
              completed: status === 'completed',
              completed_at: status === 'completed' ? new Date().toISOString() : null,
              check_ins: [
                ...(subtask.check_ins || []),
                {
                  timestamp: new Date().toISOString(),
                  status,
                  reason: checkInReason,
                  response: data.motivation?.response,
                  suggestions: data.motivation?.suggestions,
                  motivation: data.motivation?.motivation,
                },
              ],
            };
          }
          return subtask;
        }));

        // Show motivation if provided
        if (data.motivation) {
          // You can show this in a nice UI component
          console.log("Motivation:", data.motivation);
        }
      }
    } catch (error) {
      console.error("Error in check-in:", error);
      setError(error instanceof Error ? error.message : "Failed to update task");
    } finally {
      setShowCheckIn(false);
      setCheckInReason("");
      setSelectedTask(null);
    }
  };

  // Function to fetch subtasks from the backend
  const fetchSubtasks = async (retry = false) => {
    // Prevent multiple fetches within 2 seconds
    const now = Date.now();
    if (now - lastFetchTime < 2000) {
      console.log("Skipping fetch - too soon since last fetch");
      return;
    }
    
    try {
      console.log("Fetching subtasks...", { retry });
      setError(null);
      setIsLoadingSubtasks(true);
      setLastFetchTime(now);
      
      const response = await fetch("http://127.0.0.1:5000/subtasks", {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch subtasks: ${response.statusText}`);
      }

      const data = await response.json();
      
      // Sort tasks by deadline
      const sortedSubtasks = data.sort((a: Subtask, b: Subtask) => {
        const dateA = new Date(a.deadline);
        const dateB = new Date(b.deadline);
        return dateA.getTime() - dateB.getTime();
      });

      setSubtasks(sortedSubtasks);
      console.log("Successfully updated subtasks state");
      
    } catch (error) {
      console.error("Error fetching subtasks:", error);
      setError(error instanceof Error ? error.message : "Failed to fetch subtasks");
      setSubtasks([]);
    } finally {
      setIsLoadingSubtasks(false);
    }
  };

  // Fetch subtasks on component mount
  useEffect(() => {
    fetchSubtasks(true);
  }, []);

  // Refresh subtasks every minute
  useEffect(() => {
    const interval = setInterval(fetchSubtasks, 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-8">Productivity Assistant</h1>
        
        {/* Add Task Form */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="flex gap-4">
            <input
              type="text"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              placeholder="Enter a new goal or task..."
              className="flex-1 rounded-lg border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-black"
            />
            <button
              type="submit"
              disabled={isLoading}
              className={`px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                isLoading ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              {isLoading ? 'Adding...' : 'Add Task'}
            </button>
          </div>
        </form>

        {/* Task List */}
        <div className="space-y-6">
          {isLoadingSubtasks ? (
            <div className="flex flex-col items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 mb-4"></div>
              <p className="text-sm text-gray-600">Loading tasks...</p>
            </div>
          ) : error ? (
            <div className="text-center text-red-500 mt-4 p-4 bg-red-50 rounded-lg">
              <p className="font-medium">Error loading tasks</p>
              <p className="text-sm mt-1">{error}</p>
              <button 
                onClick={() => fetchSubtasks(true)}
                className="mt-4 px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200 transition-colors"
              >
                Try Again
              </button>
            </div>
          ) : subtasks.length > 0 ? (
            <div className="space-y-6">
              {/* Group subtasks by parent goal */}
              {Array.from(new Set(subtasks.map(s => s.parent_goal))).map((goalName) => {
                const goalSubtasks = subtasks.filter(s => s.parent_goal === goalName);
                const goalId = goalSubtasks[0]?.parent_goal_id;
                
                return (
                  <div key={goalId} className="bg-white rounded-lg shadow p-6">
                    <h3 className="text-lg font-semibold mb-4">{goalName}</h3>
                    <div className="space-y-4">
                      {goalSubtasks.map((subtask) => (
                        <div 
                          key={subtask._id}
                          className={`flex items-start space-x-4 p-4 rounded-lg transition-colors ${
                            subtask.status === 'completed' ? 'bg-green-50' :
                            subtask.status === 'delayed' ? 'bg-yellow-50' :
                            'bg-gray-50 hover:bg-gray-100'
                          }`}
                        >
                          {/* Task Status */}
                          <div className="flex-shrink-0">
                            <button
                              onClick={() => {
                                setSelectedTask(subtask);
                                setShowCheckIn(true);
                              }}
                              className={`w-6 h-6 rounded border-2 ${
                                subtask.status === 'completed' ? 'bg-green-500 border-green-500' :
                                subtask.status === 'delayed' ? 'bg-yellow-500 border-yellow-500' :
                                'border-gray-300 hover:border-gray-400'
                              } transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500`}
                            >
                              {subtask.status === 'completed' && (
                                <svg className="w-5 h-5 text-white" viewBox="0 0 20 20" fill="currentColor">
                                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                </svg>
                              )}
                            </button>
                          </div>
                          
                          {/* Task Details */}
                          <div className="flex-grow">
                            <p className={`text-gray-900 ${subtask.completed ? 'line-through text-gray-500' : ''}`}>
                              {subtask.task}
                            </p>
                            <div className="mt-1 text-sm text-gray-500 space-y-1">
                              <p>Time: {subtask.time_required}</p>
                              <p>Due: {new Date(subtask.deadline).toLocaleDateString()}</p>
                              
                              {/* Checkpoints */}
                              {subtask.checkpoints && subtask.checkpoints.length > 0 && (
                                <div className="mt-2">
                                  <p className="font-medium text-gray-700">Checkpoints:</p>
                                  <ul className="list-disc list-inside">
                                    {subtask.checkpoints.map((checkpoint, index) => (
                                      <li key={index} className="text-gray-600">{checkpoint}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              
                              {/* Motivation Tips */}
                              {subtask.motivation_tips && subtask.motivation_tips.length > 0 && (
                                <div className="mt-2">
                                  <p className="font-medium text-gray-700">Motivation:</p>
                                  <ul className="list-disc list-inside">
                                    {subtask.motivation_tips.map((tip, index) => (
                                      <li key={index} className="text-gray-600">{tip}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              
                              {/* Latest Check-in */}
                              {subtask.check_ins && subtask.check_ins.length > 0 && (
                                <div className="mt-2 p-3 bg-gray-100 rounded">
                                  <p className="font-medium text-gray-700">Latest Update:</p>
                                  <p className="text-gray-600">{subtask.check_ins[subtask.check_ins.length - 1].response}</p>
                                  {subtask.check_ins[subtask.check_ins.length - 1].suggestions && (
                                    <ul className="list-disc list-inside mt-2">
                                      {subtask.check_ins[subtask.check_ins.length - 1].suggestions?.map((suggestion, index) => (
                                        <li key={index} className="text-gray-600">{suggestion}</li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center text-gray-500 mt-8">
              <p>No tasks found. Add a task to get started!</p>
            </div>
          )}
        </div>

        {/* Check-in Modal */}
        {showCheckIn && selectedTask && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-lg max-w-lg w-full p-6">
              <h3 className="text-lg font-semibold mb-4">Update: {selectedTask.task}</h3>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    How's it going?
                  </label>
                  <textarea
                    value={checkInReason}
                    onChange={(e) => setCheckInReason(e.target.value)}
                    placeholder="Share your progress or any challenges..."
                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-black"
                    rows={3}
                  />
                </div>
                
                <div className="flex gap-2">
                  <button
                    onClick={() => handleCheckIn('completed')}
                    className="flex-1 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
                  >
                    Completed
                  </button>
                  <button
                    onClick={() => handleCheckIn('in_progress')}
                    className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                  >
                    In Progress
                  </button>
                  <button
                    onClick={() => handleCheckIn('delayed')}
                    className="flex-1 px-4 py-2 bg-yellow-600 text-white rounded-md hover:bg-yellow-700 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:ring-offset-2"
                  >
                    Delayed
                  </button>
                </div>
                
                <button
                  onClick={() => {
                    setShowCheckIn(false);
                    setSelectedTask(null);
                    setCheckInReason("");
                  }}
                  className="w-full mt-4 px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
