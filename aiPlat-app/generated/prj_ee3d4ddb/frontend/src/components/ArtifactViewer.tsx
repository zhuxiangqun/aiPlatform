import React, { useEffect, useState } from "react";
import { getArtifacts } from "../api/client";

interface ArtifactViewerProps {
  projectId: string;
}

const ArtifactViewer: React.FC<ArtifactViewerProps> = ({ projectId }) => {
  const [artifacts, setArtifacts] = useState<any[]>([]);

  useEffect(() => {
    getArtifacts(projectId).then(setArtifacts).catch(console.error);
  }, [projectId]);

  return (
    <div>
      <h3>Artifacts</h3>
      {artifacts.length === 0 ? (
        <p>No artifacts yet.</p>
      ) : (
        <ul>
          {artifacts.map((artifact) => (
            <li key={artifact.id}>
              <strong>{artifact.type}</strong> (v{artifact.version}) - {artifact.created_by}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default ArtifactViewer;