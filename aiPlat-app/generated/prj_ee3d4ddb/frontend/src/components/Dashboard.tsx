import React, { useEffect, useState } from "react";
import { getProject } from "../api/client";

interface DashboardProps {
  projectId: string;
}

const Dashboard: React.FC<DashboardProps> = ({ projectId }) => {
  const [project, setProject] = useState<any>(null);

  useEffect(() => {
    getProject(projectId).then(setProject).catch(console.error);
  }, [projectId]);

  if (!project) return <div>Loading...</div>;

  return (
    <div>
      <h2>Project Dashboard</h2>
      <p>Name: {project.name}</p>
      <p>Status: {project.status}</p>
      <p>Test Pass Rate: {project.test_pass_rate}%</p>
    </div>
  );
};

export default Dashboard;