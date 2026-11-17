import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { CornerDrop } from "../pages/benchmarks/CornerDrop";

const state = vi.hoisted(() => ({ allowed: true }));
vi.mock("../app/AppContext", () => ({ useApp: () => ({ me: {} }), canRun: () => state.allowed, NO_PERMISSION: "권한 없음" }));
vi.mock("../shell/Shell", () => ({ Shell: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }));
const methods = [
  ["displacement","D0"],["balanced_displacement","D1"],["physical_acceleration","P0"],
  ["contact_inertia_relief","P1"],["incremental_geometry","I0"],["ritz_reference","R0"],
].map(([id,code]) => ({ id, code, title:id, experimental:id !== "displacement" }));
const mount = () => render(<MemoryRouter initialEntries={["/p/p1/benchmarks/corner-drop"]}><Routes><Route path="/p/:projectId/benchmarks/corner-drop" element={<CornerDrop />} /></Routes></MemoryRouter>);
afterEach(() => { cleanup(); vi.unstubAllGlobals(); state.allowed = true; });

describe("실제 비교 실행 화면 연결", () => {
  it("6개 방법 버튼이 해당 방법과 고정 프리셋만 POST한다", async () => {
    const fetcher = vi.fn(async (_url: RequestInfo | URL, options?: RequestInit) => {
      const url=String(_url);
      if (url.endsWith("/settings")) return new Response(JSON.stringify({ available:true,can_execute:true,methods,presets:["full","smoke"],max_runtime_s:10800 }));
      if (options?.method === "POST") return new Response(JSON.stringify({ id:"a".repeat(32) }));
      return new Response("[]");
    });
    vi.stubGlobal("fetch",fetcher); mount();
    for (const method of methods) {
      const button=await screen.findByRole("button",{name:`${method.code} 실행`});
      await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(false));
      fireEvent.click(button);
      await waitFor(() => expect(fetcher.mock.calls.some(([,opts]) => opts?.body === JSON.stringify({method:method.id,preset:"full"}))).toBe(true));
    }
    const post=fetcher.mock.calls.find(([,opts]) => opts?.method === "POST")![1]!;
    expect((post.headers as Record<string,string>)["X-ESL-Request"]).toBe("1");
    expect(screen.getByText("아직 실행한 실험이 없습니다.")).toBeTruthy();
  });
  it("조회 역할에는 실행 버튼을 비활성화한다", async () => {
    state.allowed=false;
    vi.stubGlobal("fetch",vi.fn(async (url:RequestInfo|URL) => new Response(String(url).endsWith("/settings") ? JSON.stringify({available:true,can_execute:false,methods}) : "[]")));
    mount();const button=await screen.findByRole("button",{name:"P0 실행"});
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
