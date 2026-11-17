import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { cornerDrop, type DropRun, type DropSettings, type LegacyResult, type ShapeResult } from "../../api/cornerDrop";
import { errorText } from "../../api/client";
import { canRun, NO_PERMISSION, useApp } from "../../app/AppContext";
import { Badge, Card, Empty, ErrorLine, Field, PrimaryButton } from "../../components/ui";
import { Shell } from "../../shell/Shell";

const STATUS: Record<string,string> = { starting: "준비", running: "실행 중", completed: "완료", failed: "실패", canceled: "취소", interrupted: "중단" };
const fmt = (value: number | undefined | null, digits = 3) => value == null ? "–" : value.toFixed(digits);

export function CornerDrop() {
  const { projectId = "" } = useParams(); const { me } = useApp();
  const [settings, setSettings] = useState<DropSettings | null>(null);
  const [runs, setRuns] = useState<DropRun[]>([]); const [selected, setSelected] = useState("");
  const [error, setError] = useState<string | null>(null); const [pollError, setPollError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false); const [preset, setPreset] = useState("shape_corner");
  const reload = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([cornerDrop.settings(projectId), cornerDrop.runs(projectId)]);
      setSettings(s); setRuns(r); setPollError(null);
      setSelected(previous => r.some(run => run.id === previous) ? previous : r[0]?.id ?? "");
    } catch (e) { setPollError(errorText(e)); }
  }, [projectId]);
  useEffect(() => { void reload(); const timer = setInterval(() => void reload(), 2500); return () => clearInterval(timer); }, [reload]);
  const active = runs.some(run => run.alive); const allowed = canRun(me, projectId) && settings?.can_execute;
  const reason = !allowed ? NO_PERMISSION : !settings?.available ? settings?.reason ?? "설정 확인 중" : active ? "실행 중인 비교 실험이 있습니다" : null;
  const run = runs.find(r => r.id === selected);
  const shape = preset.startsWith("shape_");
  const shapeResult = run?.preset.startsWith("shape_") ? run.result as ShapeResult | null : null;
  const legacyResult = run && !run.preset.startsWith("shape_") ? run.result as LegacyResult | null : null;
  const start = async (method: string) => {
    setBusy(true); setError(null);
    try { const created = await cornerDrop.start(projectId, method, preset); setSelected(created.id); await reload(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!run) return; setBusy(true); setError(null);
    try { await cornerDrop.cancel(projectId, run.id); await reload(); }
    catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  return <Shell projectId={projectId} crumbs={[{label:"라이브러리",to:`/p/${projectId}/library`},{label:"코너 낙하 방법 비교"}]}>
    <div className="page-title-row"><h1 className="page-title">코너 낙하 방법 비교</h1><Badge kind="warn">실험</Badge></div>
    <p>탄성 판의 정해진 비드 형상 변경에 대해, ESL 방법별 예측을 실제 코너 낙하 변위장과 비교합니다.</p>
    <ErrorLine text={error} onClose={() => setError(null)} /><ErrorLine text={pollError} />
    {!settings?.available && <p role="status">{settings?.reason ?? "실행 환경 확인 중…"}</p>}
    <Card title="실행 방법" right={<PrimaryButton label="전체 방법 비교 실행" disabledReason={reason} busy={busy} onClick={() => void start("all")} />}>
      <Field label="실행 규모"><select value={preset} onChange={e => setPreset(e.target.value)} disabled={busy || active}>
        <option value="shape_corner">탄성 방법론 검증 · 수직 대각선 코너 낙하</option><option value="shape_flat">탄성 대조 조건 · 수평에서 약 5°</option><option value="full">기존 탄소성 실험 기록 재현 · 전체 검증 · 40 ms, 공통 후보 77개와 국부 탐색</option><option value="smoke">연결 확인 · 6 ms, 성능 판정용이 아님</option>
      </select></Field>
      <p className="muted small">{shape ? "기준 낙하와 독립 형상 재해석으로 변위장 오차, 변화 방향, 구속 의존성을 검증합니다. 1차 미분 방법은 보정용 동해석 12회가 추가됩니다." : "기존 탄소성 설계안 탐색 실험을 재현합니다. 새 탄성 방법론 선정과 구분됩니다."}</p>
      <div className="table-wrap"><table className="table" aria-label="후보 방법"><thead><tr><th>방법</th><th>지위</th><th>실행</th></tr></thead><tbody>
        {shape ? settings?.shape_methods?.map(method => <tr key={method.id}><td>{method.label}</td><td>{method.family} · 보정 낙하 {method.extra_dynamic_runs}회</td><td><button type="button" className="btn" disabled={!!reason || busy} title={reason ?? undefined} onClick={() => void start(method.id)}>{method.label} 실행</button></td></tr>) : settings?.methods.map(method => <tr key={method.id}><td>{method.code} · {method.title}</td><td>{method.experimental ? "실험적 확장·검증 필요" : "기존 방식 대조군"}</td><td>
          <button type="button" className="btn" disabled={!!reason || busy} title={reason ?? undefined} onClick={() => void start(method.id)}>{method.code} 실행</button>
        </td></tr>)}
      </tbody></table></div>
      <p className="muted small">단일 외부 반복의 비교입니다. 실제 TV 조립체나 최적화 수렴을 검증한 결과로 확대하지 않습니다.</p>
    </Card>
    <Card title="실행 기록">
      {!runs.length ? <Empty>아직 실행한 실험이 없습니다.</Empty> : <Field label="기록 선택"><select value={selected} onChange={e => setSelected(e.target.value)}>
        {runs.map(r => <option key={r.id} value={r.id}>{new Date(r.created_at * 1000).toLocaleString()} · {r.method} · {r.preset} · {STATUS[r.progress.status] ?? r.progress.status}</option>)}
      </select></Field>}
      {run && <>
        <p role="status">{STATUS[run.progress.status] ?? run.progress.status} · {run.progress.message ?? run.progress.stage}</p>
        {run.progress.total != null && <progress value={run.progress.completed ?? 0} max={run.progress.total} aria-label="공통 후보 진행" />}
        <ErrorLine text={run.progress.error} />
        {run.alive && <button type="button" className="btn" disabled={!allowed || busy} onClick={() => void cancel()}>실행 취소</button>}
        {shapeResult?.summary && <>
          <div className="table-wrap"><table className="table" aria-label="탄성 방법론 검증 결과"><thead><tr><th>방법</th><th>독립 사례 통과</th><th>최대 변위장 오차</th><th>변화 방향 일치</th><th>선정</th></tr></thead><tbody>{Object.entries(shapeResult.summary).map(([id,row]) => {
            const s = row.regions.small;
            const verdict = row.control ? "비교 대조군" : s.recommended_in_region ? "검증 범위 내 통과" : "선정 기준 미충족";
            return <tr key={id}><td>{row.label}</td><td>{s.passed}/{s.tests}</td><td>{s.worst_field_l2==null ? "–" : `${fmt(s.worst_field_l2*100,1)}%`}</td><td>{s.direction_agreement==null ? "–" : `${fmt(s.direction_agreement*100,1)}%`}</td><td>{verdict}</td></tr>;
          })}</tbody></table></div>
          <div className="actions">{[["report.html","그림 포함 보고서"],["method_results.json","전체 검증 JSON"],["benchmark.png","방법별 오차"],["contours.png","실제·예측 컨투어"]].map(([file,label]) => <a key={file} className="btn" href={cornerDrop.file(projectId,run.id,file)} download>{label} 받기</a>)}</div>
        </>}
        {legacyResult && <>
          {run.preset === "smoke" && <p className="error-text">이 기록은 실행 연결 확인입니다. 낙하 성능 개선 판정에 사용하지 마세요.</p>}
          <p>실제 기준 RMS: {fmt(legacyResult.baseline.peak_rms_mm)} mm · 재낙하 비교 {legacyResult.actual_drops}건</p>
          <div className="table-wrap"><table className="table" aria-label="방법별 실제 검증 결과"><thead><tr><th>방법</th><th>정적 예측 mm</th><th>실제 낙하 mm</th><th>실제 개선율</th><th>소성변형 p95</th><th>거친 메시 판정</th></tr></thead><tbody>
            {legacyResult.methods.map(r => <tr key={r.method}><td>{r.code ?? r.method}</td><td>{fmt(r.predicted_mm)}</td><td>{fmt(r.actual_mm)}</td><td>{r.improvement_fraction == null ? "–" : `${fmt(100*r.improvement_fraction,1)}%`}</td><td>{fmt(r.plastic_p95,5)}</td><td>{r.status !== "completed" ? r.error ?? "실패" : r.accepted ? "기준 충족 · 세분화 확인 필요" : "개선 기준 미충족"}</td></tr>)}
          </tbody></table></div>
          <p className="muted small">자세 변화와 메시 세분화 결과, 에너지 오차 및 실패 내역은 보고서에서 확인하세요.</p>
          <div className="actions">{[ ["report.html","보고서"],["comparison.csv","비교 CSV"],["result.json","전체 결과 JSON"],["benchmark.png","형상·결과 그림"],["drop_comparison.gif","낙하 영상"] ].map(([file,label]) => <a key={file} className="btn" href={cornerDrop.file(projectId,run.id,file)} download>{label} 받기</a>)}</div>
        </>}
        {!run.alive && <div className="actions"><a className="btn" href={cornerDrop.file(projectId,run.id,"worker.log")} download>실행 로그 받기</a><a className="btn" href={cornerDrop.file(projectId,run.id,"bundle.zip")} download>입력·로그·원자료 ZIP 받기</a></div>}
      </>}
    </Card>
  </Shell>;
}
