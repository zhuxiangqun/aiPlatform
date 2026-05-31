import React, { useEffect, useState } from "react";
import { getTestCases, getBugs } from "../api/client";

interface TestReportProps {
  projectId: string;
}

const TestReport: React.FC<TestReportProps> = ({ projectId }) => {
  const [testCases, setTestCases] = useState<any[]>([]);
  const [bugs, setBugs] = useState<any[]>([]);

  useEffect(() => {
    getTestCases(projectId).then(setTestCases).catch(console.error);
    getBugs(projectId).then(setBugs).catch(console.error);
  }, [projectId]);

  return (
    <div>
      <h3>Test Report</h3>
      <h4>Test Cases ({testCases.length})</h4>
      <ul>
        {testCases.map((tc) => (
          <li key={tc.id}>{tc.description} - {tc.status}</li>
        ))}
      </ul>
      <h4>Bugs ({bugs.length})</h4>
      <ul>
        {bugs.map((bug) => (
          <li key={bug.id}>{bug.description} - {bug.status}</li>
        ))}
      </ul>
    </div>
  );
};

export default TestReport;