import React, { useState } from "react";
import { assignRoles } from "../api/client";

interface RoleSelectorProps {
  projectId: string;
}

const RoleSelector: React.FC<RoleSelectorProps> = ({ projectId }) => {
  const [roles, setRoles] = useState<Array<{ role_name: string; user_id: string }>>([]);
  const [roleName, setRoleName] = useState("");
  const [userId, setUserId] = useState("");

  const addRole = () => {
    if (!roleName || !userId) return;
    setRoles((prev) => [...prev, { role_name: roleName, user_id: userId }]);
    setRoleName("");
    setUserId("");
  };

  const submitRoles = async () => {
    try {
      await assignRoles(projectId, roles);
      alert("Roles assigned successfully");
    } catch (error) {
      alert("Error assigning roles");
    }
  };

  return (
    <div>
      <h3>Role Selector</h3>
      <input value={roleName} onChange={(e) => setRoleName(e.target.value)} placeholder="Role name (e.g., PM)" />
      <input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="User ID" />
      <button onClick={addRole}>Add Role</button>
      <ul>
        {roles.map((role, idx) => (
          <li key={idx}>{role.role_name} - {role.user_id}</li>
        ))}
      </ul>
      <button onClick={submitRoles}>Submit Roles</button>
    </div>
  );
};

export default RoleSelector;