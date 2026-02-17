import { FormEvent, useEffect, useMemo, useState } from "react";

type HealthState = "loading" | "ok" | "error";

type Workspace = {
  workspace_id: string;
  name: string;
  profile: string;
  security_baseline: string;
};

type ReviewTask = {
  task_id: string;
  priority: string;
  status: string;
  subject_ref: string;
  evidence_bundle_uri: string | null;
  confidence: number | null;
  proposal_type: string | null;
};

type Recommendation = {
  report_id: string;
  confidence: number;
  approval_required: boolean;
  approval_reasons: string[];
  missing_evidence: string[];
  ranked_templates: { template_id: string; score: number }[];
};

const WIZARD_STEPS = [
  "Connect sources",
  "Set profiling budget",
  "Choose security baseline",
  "Review recommendations"
];

export function App(): JSX.Element {
  const [health, setHealth] = useState<HealthState>("loading");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [newWorkspaceName, setNewWorkspaceName] = useState<string>("");
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [decisionReason, setDecisionReason] = useState<string>("");
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);

  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.workspace_id === selectedWorkspaceId),
    [selectedWorkspaceId, workspaces]
  );

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const healthResponse = await fetch("/api/v1/health");
        setHealth(healthResponse.ok ? "ok" : "error");
        await refreshWorkspaces();
      } catch {
        setHealth("error");
      }
    };
    void bootstrap();
  }, []);

  useEffect(() => {
    if (!selectedWorkspaceId) {
      setReviewTasks([]);
      return;
    }
    const loadReviewTasks = async () => {
      try {
        const response = await fetch(`/api/v1/workspaces/${selectedWorkspaceId}/review_tasks`);
        if (!response.ok) {
          setReviewTasks([]);
          return;
        }
        const data: ReviewTask[] = await response.json();
        setReviewTasks(data);
      } catch {
        setReviewTasks([]);
      }
    };
    void loadReviewTasks();
  }, [selectedWorkspaceId]);

  const refreshWorkspaces = async () => {
    const response = await fetch("/api/v1/workspaces");
    if (!response.ok) {
      setWorkspaces([]);
      return;
    }
    const data: Workspace[] = await response.json();
    setWorkspaces(data);
    if (!selectedWorkspaceId && data.length > 0) {
      setSelectedWorkspaceId(data[0].workspace_id);
    }
  };

  const createWorkspace = async (event: FormEvent) => {
    event.preventDefault();
    if (!newWorkspaceName.trim()) {
      return;
    }
    const response = await fetch("/api/v1/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: newWorkspaceName.trim(),
        profile: "starter",
        security_baseline: "standard"
      })
    });
    if (!response.ok) {
      return;
    }
    const created: Workspace = await response.json();
    await refreshWorkspaces();
    setSelectedWorkspaceId(created.workspace_id);
    setNewWorkspaceName("");
  };

  const decideTask = async (taskId: string, decision: "approve" | "reject" | "defer") => {
    if (!selectedWorkspaceId) {
      return;
    }
    await fetch(`/api/v1/workspaces/${selectedWorkspaceId}/review_tasks/${taskId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        actor_id: "user:ui",
        decision_reason: decisionReason
      })
    });
    const response = await fetch(`/api/v1/workspaces/${selectedWorkspaceId}/review_tasks`);
    if (response.ok) {
      const data: ReviewTask[] = await response.json();
      setReviewTasks(data);
    }
  };

  const generateRecommendation = async () => {
    if (!selectedWorkspaceId) {
      return;
    }
    const response = await fetch(`/api/v1/workspaces/${selectedWorkspaceId}/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent: {
          strict_security: true,
          needs_documents: true,
          confidence_signal: 0.65,
          evidence_completeness: 0.6
        }
      })
    });
    if (!response.ok) {
      return;
    }
    const data: Recommendation = await response.json();
    setRecommendation(data);
  };

  return (
    <main style={{ margin: "2rem auto", maxWidth: "960px", fontFamily: "sans-serif" }}>
      <h1>SchemaPilot</h1>
      <p>API health: {health}</p>

      <section>
        <h2>Workspace</h2>
        <form onSubmit={createWorkspace}>
          <input
            placeholder="Workspace name"
            value={newWorkspaceName}
            onChange={(event) => setNewWorkspaceName(event.target.value)}
          />
          <button type="submit">Create</button>
        </form>
        <label htmlFor="workspace-select">Select workspace:</label>
        <select
          id="workspace-select"
          value={selectedWorkspaceId}
          onChange={(event) => setSelectedWorkspaceId(event.target.value)}
        >
          <option value="">-- choose --</option>
          {workspaces.map((workspace) => (
            <option key={workspace.workspace_id} value={workspace.workspace_id}>
              {workspace.name} ({workspace.profile})
            </option>
          ))}
        </select>
        {selectedWorkspace ? (
          <p>
            Active workspace: <strong>{selectedWorkspace.name}</strong>
          </p>
        ) : null}
      </section>

      <section>
        <h2>Wizard Stepper</h2>
        <ol>
          {WIZARD_STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      <section>
        <h2>Review Queue</h2>
        <input
          placeholder="Decision reason (for reject/defer)"
          value={decisionReason}
          onChange={(event) => setDecisionReason(event.target.value)}
        />
        {selectedWorkspaceId ? (
          reviewTasks.length > 0 ? (
            <ul>
              {reviewTasks.map((task) => (
                <li key={task.task_id}>
                  <strong>{task.proposal_type ?? "proposal"}</strong> :: {task.priority} ::{" "}
                  {task.status}
                  <div>Task: {task.task_id}</div>
                  <div>Evidence: {task.evidence_bundle_uri ?? "n/a"}</div>
                  <div>Confidence: {task.confidence ?? "n/a"}</div>
                  <button type="button" onClick={() => decideTask(task.task_id, "approve")}>
                    Approve
                  </button>
                  <button type="button" onClick={() => decideTask(task.task_id, "reject")}>
                    Reject
                  </button>
                  <button type="button" onClick={() => decideTask(task.task_id, "defer")}>
                    Defer
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p>No review tasks yet.</p>
          )
        ) : (
          <p>Select a workspace to load review tasks.</p>
        )}
      </section>

      <section>
        <h2>Recommendation Report</h2>
        <button type="button" onClick={generateRecommendation}>
          Generate Recommendation
        </button>
        {recommendation ? (
          <div>
            <div>Confidence: {recommendation.confidence}</div>
            <div>Approval required: {String(recommendation.approval_required)}</div>
            <div>Approval reasons: {recommendation.approval_reasons.join(", ") || "none"}</div>
            <div>Missing evidence: {recommendation.missing_evidence.join(", ") || "none"}</div>
            <ul>
              {recommendation.ranked_templates.slice(0, 3).map((item) => (
                <li key={item.template_id}>
                  {item.template_id} :: {item.score}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p>No recommendation generated yet.</p>
        )}
      </section>
    </main>
  );
}
