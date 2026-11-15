// v0.21.0 BEAD_SHAPE 화면 증적(mock): ① 부분 W(비드 칩·트리 `W —`·변수 표 꼬리표)·범위 축소(guard 꼬리표·정보) · ④ 완화 직행 칩 + 메시 품질 ⚠ + 품질 통과 최상위 · ③ 결과 띠를 1920·2560 에서 찍는다.
// 가로 스크롤·잘린 카드 없음을 검사, 실패하면 종료 코드 1.
// 사용: npm run build:mock && node scripts/screenshots-v0210.mjs [출력폴더]
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const out = path.resolve(process.argv[2] ?? "/home/claude/screens/v0210-fe");
mkdirSync(out, { recursive: true });
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "/opt/pw-browsers";
const modPath = process.env.PLAYWRIGHT_MODULE ?? "/home/claude/.npm-global/lib/node_modules/playwright/index.mjs";
const { chromium } = await import(pathToFileURL(modPath).href);

const port = 5241;
const server = spawn(
  process.execPath,
  [path.join(root, "node_modules/vite/bin/vite.js"), "preview", "--mode", "mock", "--outDir", "dist-mock", "--port", String(port), "--strictPort", "--host", "127.0.0.1"],
  { cwd: root, stdio: "pipe" },
);
const base = `http://127.0.0.1:${port}/esl`;
const Q = "freeze=1&mockUser=power&seenVersion=0.21.0&demoShape=1";

let failed = 0;
const check = async (page, w, h, name, extra) => {
  const r = await page.evaluate(() => {
    const de = document.documentElement;
    const cut = [...document.querySelectorAll(".card, .page-title-row, .table-wrap, .doe-rank-wrap, .sg-tree")].filter((c) => c.getBoundingClientRect().right > de.clientWidth + 1).length;
    return { hScroll: de.scrollWidth > de.clientWidth + 1, cut };
  });
  const ok = !r.hScroll && r.cut === 0 && (extra?.ok ?? true);
  if (!ok) failed += 1;
  console.log(`${ok ? "OK  " : "FAIL"} ${w}×${h} ${name}: 가로 스크롤 ${r.hScroll ? "있음" : "없음"} · 잘린 카드 ${r.cut}${extra ? ` · ${extra.text}` : ""}`);
};
const shot = async (page, name) => {
  const p = path.join(out, name);
  await page.screenshot({ path: p });
  console.log(p);
};
const top = async (page, loc) => {
  await loc.evaluate((el) => el.scrollIntoView({ block: "start" }));
  await page.evaluate(() => window.scrollBy(0, -80));
  await page.waitForTimeout(700);
};
const txt = async (loc) => ((await loc.first().textContent()) ?? "").trim();

try {
  for (let i = 0; ; i++) {
    try {
      if ((await fetch(`${base}/`)).ok) break;
    } catch {
      /* 아직 */
    }
    if (i > 100) throw new Error("preview 서버 시작 시간 초과");
    await new Promise((r) => setTimeout(r, 200));
  }
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [w, h] of [
    [1920, 1080],
    [2560, 1440],
  ]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    // 1) ① 그래프 select — 부분 W: 비드 목록(칩) · 변수 표 꼬리표(부분·축소·조합 축소·막힘·미점검)
    await page.goto(`${base}/p/p-body/doe/doe-30?${Q}`);
    await page.getByTestId("bead-b5").waitFor({ timeout: 30000 });
    await page.getByTestId("guard-B1_D").waitFor({ timeout: 30000 });
    const chip = page.getByTestId("bead-wpart-b5");
    await top(page, page.getByRole("table", { name: "비드 변수" }));
    const tags = await page.locator('[data-testid^="guard-"]').evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute("data-state") + ":" + e.textContent))].sort());
    await check(page, w, h, "① 변수 표 꼬리표", { ok: tags.length >= 4 && (await page.getByTestId("wpart-B5_W").count()) === 1, text: tags.join(" ") });
    await shot(page, `1_vars_${w}.png`);
    await top(page, chip);
    await check(page, w, h, "① 비드 칩", { ok: /부분 2\/3/.test(await txt(chip)), text: await txt(chip) });
    await shot(page, `2_beadlist_${w}.png`);
    // 2) 트리 `W —`
    await page.getByTestId("bs-view-tree").click();
    const tree = page.getByTestId("sg-tree");
    await tree.waitFor({ timeout: 10000 });
    await top(page, tree);
    const n = await page.locator('[data-testid^="sg-now-"]').count();
    await check(page, w, h, "① 트리 W —", { ok: n === 2, text: `W — ${n}줄` });
    await shot(page, `3_tree_${w}.png`);
    // 3) ④ 형상 비교 — 완화 직행 칩 · 순위 ⚠ · 품질 통과 최상위
    await page.goto(`${base}/p/p-body/doe/doe-31?${Q}`);
    await page.getByTestId("prep-route-d001").waitFor({ timeout: 30000 });
    await top(page, page.getByRole("table", { name: "형상 표" }));
    await check(page, w, h, "④ 형상 표(완화 직행 칩)", { ok: (await page.locator('[data-testid^="prep-route-"]').count()) === 2, text: `칩 ${await page.locator('[data-testid^="prep-route-"]').count()}개` });
    await shot(page, `4_shapes_${w}.png`);
    const line = page.getByTestId("best-clean-mq");
    await line.waitFor({ timeout: 30000 });
    await top(page, line);
    await check(page, w, h, "④ 순위 ⚠ + 품질 통과 최상위", { ok: (await page.getByTestId("rank-warn-d001").count()) === 1, text: await txt(line) });
    await shot(page, `5_rank_${w}.png`);
    // 4) ③ 결과 띠
    await page.goto(`${base}/p/p-body/doe/doe-32?${Q}`);
    const strip = page.getByTestId("mq-base-strip");
    await strip.waitFor({ timeout: 40000 });
    await top(page, strip);
    await check(page, w, h, "③ 결과 띠", { ok: (await page.locator('[data-testid="mq-base-strip"]').count()) === 1, text: await txt(strip) });
    await shot(page, `6_base_strip_${w}.png`);
    await ctx.close();
  }
  await browser.close();
} finally {
  server.kill();
}
if (failed) {
  console.error(`실패 ${failed}건`);
  process.exit(1);
}
