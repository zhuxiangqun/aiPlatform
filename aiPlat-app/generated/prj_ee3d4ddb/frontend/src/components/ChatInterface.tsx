import React, { useState } from "react";
import { createProject, confirmPRD } from "../api/client";

interface ChatInterfaceProps {
  onProjectCreated: (projectId: string) => void;
}

const ChatInterface: React.FC<ChatInterfaceProps> = ({ onProjectCreated }) => {
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [input, setInput] = useState("");

  const sendMessage = async () => {
    if (!input.trim()) return;
    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    try {
      const project = await createProject("New Project", input);
      const botMessage = { role: "bot", content: `Project created with ID: ${project.project_id}` };
      setMessages((prev) => [...prev, botMessage]);
      onProjectCreated(project.project_id);
    } catch (error) {
      const botMessage = { role: "bot", content: "Error creating project" };
      setMessages((prev) => [...prev, botMessage]);
    }
  };

  return (
    <div>
      <div>
        {messages.map((msg, idx) => (
          <div key={idx} style={{ fontWeight: msg.role === "user" ? "bold" : "normal" }}>
            {msg.role}: {msg.content}
          </div>
        ))}
      </div>
      <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Enter requirements..." />
      <button onClick={sendMessage}>Send</button>
    </div>
  );
};

export default ChatInterface;