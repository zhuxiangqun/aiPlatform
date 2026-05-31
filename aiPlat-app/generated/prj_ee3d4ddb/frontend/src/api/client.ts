const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000/api";

export async function createProject(name: string, requirements: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, requirements }),
  });
  return response.json();
}

export async function getProject(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}`);
  return response.json();
}

export async function assignRoles(projectId: string, roles: Array<{ role_name: string; user_id: string }>): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/roles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ roles }),
  });
  return response.json();
}

export async function confirmPRD(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/confirm-prd`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return response.json();
}

export async function getArtifacts(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/artifacts`);
  return response.json();
}

export async function getTestCases(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/tests`);
  return response.json();
}

export async function getBugs(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/tests/bugs`);
  return response.json();
}

export async function getAuditLogs(projectId: string): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/audit-logs`);
  return response.json();
}