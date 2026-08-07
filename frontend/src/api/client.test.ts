import { academyApi, API_BASE } from "./client";

describe("academy API client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("executes every curriculum module through the structured module route", async () => {
    const response = new Response(JSON.stringify({ run_id: "run-foundation", module_id: "f0", status: "complete" }), { status: 200, headers: { "content-type": "application/json" } });
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    await academyApi.runModule("f0-assistant-to-agent");
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/modules/f0-assistant-to-agent/run`, expect.objectContaining({ method: "POST" }));
    expect(fetchMock.mock.calls[0][1]).not.toHaveProperty("body");
  });

  it("sends optional module configuration as JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await academyApi.runModule("f1", { challenge: "retry" });
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ challenge: "retry" }));
  });
});

