import React from "react";
import { useParams } from "react-router-dom";
import Dashboard from "../components/Dashboard";
import RoleSelector from "../components/RoleSelector";
import ArtifactViewer from "../components/ArtifactViewer";
import TestReport from "../components/TestReport";

const ProjectPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  if (!projectId) return <div>Project ID not found</div>;

  return (
    <div>
      <h1>Project Details</h1>
      <Dashboard projectId={projectId} />
      <RoleSelector projectId={projectId} />
      <ArtifactViewer projectId={projectId} />
      <TestReport projectId={projectId} />
    </div>
  );
};

export default ProjectPage;