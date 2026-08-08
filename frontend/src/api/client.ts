import type {
  AssessmentResult,
  CapstoneDefinition,
  ContractDetail,
  ContractMutation,
  ContractSummary,
  ContractValidation,
  CurriculumCatalog,
  Dashboard,
  DemoOptions,
  DemoStory,
  Glossary,
  RemediationRegistry,
  Health,
  LessonTeaching,
  LiveModelSettingsResponse,
  Orientation,
  PlatformInfo,
  PublicAssessment,
  ScenarioRun,
  StageMap,
  StructuredLabRun,
} from "../types";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(message: string, status = 0, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function errorMessage(body: unknown, response: Response): string {
  if (body && typeof body === "object") {
    const value = body as Record<string, unknown>;
    if (typeof value.detail === "string") return value.detail;
    if (value.detail && typeof value.detail === "object") {
      const detail = value.detail as Record<string, unknown>;
      if (typeof detail.message === "string") {
        return typeof detail.code === "string" ? `${detail.code}: ${detail.message}` : detail.message;
      }
    }
    if (typeof value.message === "string") return value.message;
  }
  if (response.status === 404) return "This academy capability is not available from the connected service.";
  return response.statusText || "The academy service did not complete the request.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch (error) {
    throw new ApiError(
      error instanceof Error
        ? `Cannot reach the local academy service: ${error.message}`
        : "Cannot reach the local academy service.",
    );
  }

  const contentType = response.headers.get("content-type") ?? "";
  const body: unknown = contentType.includes("application/json")
    ? await response.json().catch(() => null)
    : await response.text().catch(() => "");
  if (!response.ok) {
    const code = body && typeof body === "object" && "code" in body
      ? String((body as { code: unknown }).code)
      : undefined;
    throw new ApiError(errorMessage(body, response), response.status, code);
  }
  return body as T;
}

const encode = (value: string) => encodeURIComponent(value);

export const academyApi = {
  health: () => request<Health>("/health"),
  platform: () => request<PlatformInfo>("/platform"),
  catalog: () => request<CurriculumCatalog>("/catalog"),
  progress: () => request<Dashboard>("/progress"),
  orientation: () => request<Orientation>("/orientation"),
  glossary: () => request<Glossary>("/glossary"),
  remediation: () => request<RemediationRegistry>("/remediation"),
  stages: () => request<StageMap>("/stages"),
  demoStory: () => request<DemoStory>("/demo/story"),
  teaching: (moduleId: string) => request<LessonTeaching>(`/modules/${encode(moduleId)}/teaching`),
  contracts: () => request<ContractSummary[]>("/contracts"),
  contract: (id: string) => request<ContractDetail>(`/contracts/${encode(id)}`),
  assessment: (id: string) => request<PublicAssessment>(`/assessments/${encode(id)}`),
  runDemo: (options: DemoOptions) =>
    request<ScenarioRun>("/demo/run", { method: "POST", body: JSON.stringify(options) }),
  runModule: (moduleId: string, configuration?: Record<string, unknown>) =>
    request<StructuredLabRun>(`/modules/${encode(moduleId)}/run`, {
      method: "POST",
      ...(configuration ? { body: JSON.stringify(configuration) } : {}),
    }),
  runLab: (legacyId: string) =>
    request<StructuredLabRun>(`/labs/${encode(legacyId)}/run`, { method: "POST" }),
  submitAssessment: (id: string, answers: string[]) =>
    request<AssessmentResult>(`/assessments/${encode(id)}/submit`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
  validateWorkbench: (contractId: "atlas" | "ledger", mutations: ContractMutation[]) =>
    request<ContractValidation>("/contracts/workbench", {
      method: "POST",
      body: JSON.stringify({ contract_id: contractId, mutations }),
    }),
  liveSettings: () => request<LiveModelSettingsResponse>("/settings/live"),
  saveLiveSettings: (settings: {
    enabled: boolean;
    provider: "anthropic";
    model: string;
    api_key: string | null;
  }) =>
    request<LiveModelSettingsResponse>("/settings/live", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  resetProgress: () => request<Dashboard>("/progress/reset", { method: "POST" }),
  exportProgress: () => request<Record<string, unknown>>("/progress/export"),
  capstone: () => request<CapstoneDefinition>("/capstone"),
  runCapstone: (configuration: Record<string, unknown> = {}) =>
    request<StructuredLabRun>("/capstone/run", {
      method: "POST",
      body: JSON.stringify(configuration),
    }),
};

export function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
