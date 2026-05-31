import React from "react";
import ChatInterface from "../components/ChatInterface";

const Home: React.FC = () => {
  const handleProjectCreated = (projectId: string) => {
    window.location.href = `/project/${projectId}`;
  };

  return (
    <div>
      <h1>AI Software Team</h1>
      <ChatInterface onProjectCreated={handleProjectCreated} />
    </div>
  );
};

export default Home;