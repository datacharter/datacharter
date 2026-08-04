import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LLMConfig from "./LLMConfig";

// global.fetch spy over top-level vi.mock: the api module builds on fetch, and
// mocking at the seam keeps request shapes honest.
function stubFetch(routes: Record<string, unknown>) {
  return vi.spyOn(global, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    for (const [path, body] of Object.entries(routes)) {
      if (url.includes(path)) {
        return new Response(JSON.stringify(body), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
    }
    return new Response("{}", { status: 404 });
  });
}

afterEach(() => vi.restoreAllMocks());

describe("LLMConfig local-runtime picker", () => {
  it("lists detected local models and connects one on click", async () => {
    const spy = stubFetch({
      "/api/llm/local": {
        runtimes: [
          { provider: "ollama", base_url: "http://127.0.0.1:11434/v1", models: ["qwen2.5:7b"] },
        ],
      },
      "/api/agent/config": { ok: true },
    });
    const onDone = vi.fn();
    const { findByLabelText, getByText } = render(
      <LLMConfig current={null} onDone={onDone} onCancel={() => {}} />,
    );
    expect(getByText("Connect an LLM")).toBeTruthy();
    const btn = await findByLabelText("Use local model qwen2.5:7b");
    fireEvent.click(btn);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const configCall = spy.mock.calls.find(
      ([u, init]) => String(u).includes("/api/agent/config") && init?.method === "POST",
    );
    expect(configCall).toBeTruthy();
    const sent = JSON.parse(String(configCall![1]!.body));
    expect(sent).toMatchObject({ base_url: "http://127.0.0.1:11434/v1", model: "qwen2.5:7b" });
  });

  it("renders the manual form when no local runtimes are found", async () => {
    stubFetch({ "/api/llm/local": { runtimes: [] } });
    const { getByText, queryByText } = render(
      <LLMConfig current={null} onDone={() => {}} onCancel={() => {}} />,
    );
    await waitFor(() => expect(queryByText("Running on this machine")).toBeNull());
    expect(getByText("Base URL")).toBeTruthy();
  });

  it("shows the endpoint error instead of closing when connect fails", async () => {
    vi.spyOn(global, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/llm/local")) {
        return new Response(
          JSON.stringify({
            runtimes: [{ provider: "ollama", base_url: "http://x/v1", models: ["m"] }],
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (init?.method === "POST") {
        return new Response(
          JSON.stringify({ error: { type: "llm_error", message: "endpoint unreachable" } }),
          { status: 400, headers: { "content-type": "application/json" } },
        );
      }
      return new Response("{}", { status: 404 });
    });
    const onDone = vi.fn();
    const { findByLabelText, findByText } = render(
      <LLMConfig current={null} onDone={onDone} onCancel={() => {}} />,
    );
    fireEvent.click(await findByLabelText("Use local model m"));
    expect(await findByText(/endpoint unreachable/)).toBeTruthy();
    expect(onDone).not.toHaveBeenCalled();
  });
});
