import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/render";

describe("smoke", () => {
  it("doe-30", async () => {
    const r = renderApp("/p/p-body/doe/doe-30", "power", (s) => s.doe.demoShape());
    await waitFor(() => expect(screen.getByTestId("bead-b1")).toBeTruthy(), { timeout: 10000 });
    await waitFor(() => expect(document.querySelectorAll('[data-testid^="guard-"]').length).toBeGreaterThan(0), { timeout: 10000 });
    console.log([...document.querySelectorAll('[data-testid^="guard-"],[data-testid^="wpart-"],[data-testid^="bead-wpart-"]')].map((e) => `${e.getAttribute("data-testid")}=${e.textContent}`).join("\n"));
    void r;
  }, 30000);
});
