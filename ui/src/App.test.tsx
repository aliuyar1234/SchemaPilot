import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

type FetchResponse = {
  ok: boolean;
  json: () => Promise<unknown>;
};

function response(body: unknown, ok = true): FetchResponse {
  return {
    ok,
    json: async () => body
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("App", () => {
  it("loads health, workspaces, policy packs and review summary", async () => {
    const fetchMock = vi.fn(
      (input: RequestInfo | URL): Promise<FetchResponse> => {
        const url = String(input);
        if (url === "/api/v1/health") {
          return Promise.resolve(response({ status: "ok" }));
        }
        if (url === "/api/v1/workspaces") {
          return Promise.resolve(
            response([
              {
                workspace_id: "w1",
                name: "Primary",
                profile: "starter",
                security_baseline: "standard"
              }
            ])
          );
        }
        if (url === "/api/v1/policy-packs") {
          return Promise.resolve(
            response([
              { id: "starter_local_team", name: "Starter Local Team", description: "desc" }
            ])
          );
        }
        if (url === "/api/v1/workspaces/w1/review_tasks") {
          return Promise.resolve(response([]));
        }
        if (url === "/api/v1/workspaces/w1/review_tasks/summary") {
          return Promise.resolve(
            response({
              workspace_id: "w1",
              total_tasks: 0,
              blocking_open_tasks: 0,
              by_status: {},
              by_priority: {}
            })
          );
        }
        return Promise.resolve(response({}, false));
      }
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("API health: ok")).toBeTruthy();
    });
    expect(screen.getByText("Primary")).toBeTruthy();
    expect(screen.getByText("Starter Local Team")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText(/Total: 0, Blocking open: 0/)).toBeTruthy();
    });
  });

  it("bootstraps demo workspace and renders onboarding details", async () => {
    const workspaces = [
      {
        workspace_id: "w1",
        name: "Primary",
        profile: "starter",
        security_baseline: "standard"
      }
    ];

    const fetchMock = vi.fn(
      (input: RequestInfo | URL, init?: RequestInit): Promise<FetchResponse> => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url === "/api/v1/health") {
          return Promise.resolve(response({ status: "ok" }));
        }
        if (url === "/api/v1/workspaces" && method === "GET") {
          return Promise.resolve(response(workspaces));
        }
        if (url === "/api/v1/policy-packs") {
          return Promise.resolve(response([]));
        }
        if (url === "/api/v1/onboarding/demo_bootstrap" && method === "POST") {
          const demoWorkspace = {
            workspace_id: "w-demo",
            name: "Demo Workspace",
            profile: "starter",
            security_baseline: "standard"
          };
          workspaces.push(demoWorkspace);
          return Promise.resolve(
            response({
              workspace: demoWorkspace,
              demo_data_path: "./runtime/demo_data",
              first_query_example: {
                endpoint: "/api/v1/gateway/query",
                authorization: "Bearer local-analyst-token",
                payload: { query: { text: "select 1 as one" } }
              },
              next_steps: ["one", "two", "three"]
            })
          );
        }
        if (url === "/api/v1/workspaces/w1/review_tasks" || url === "/api/v1/workspaces/w-demo/review_tasks") {
          return Promise.resolve(response([]));
        }
        if (
          url === "/api/v1/workspaces/w1/review_tasks/summary" ||
          url === "/api/v1/workspaces/w-demo/review_tasks/summary"
        ) {
          return Promise.resolve(
            response({
              workspace_id: "w1",
              total_tasks: 0,
              blocking_open_tasks: 0,
              by_status: {},
              by_priority: {}
            })
          );
        }
        return Promise.resolve(response({}, false));
      }
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("API health: ok")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Create Demo Workspace" }));

    await waitFor(() => {
      expect(screen.getByText("Demo data path: ./runtime/demo_data")).toBeTruthy();
      expect(screen.getByText("Gateway auth: Bearer local-analyst-token")).toBeTruthy();
    });
  });
});
