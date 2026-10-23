import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Card, ErrorBox } from "../components/common";
import { api, type TriggerType } from "../lib/api";
import { TRIGGER_INFO, localInputToIso, timeOnly, toLocalInput } from "../lib/format";

const roundUp = (d: Date, minutes = 5) => {
  const ms = minutes * 60000;
  return new Date(Math.ceil(d.getTime() / ms) * ms);
};
const addMin = (d: Date, m: number) => new Date(d.getTime() + m * 60000);

function defaults() {
  const start = roundUp(new Date());
  const close = addMin(start, 60);
  return {
    name: "",
    reference_id: "",
    description: "",
    origin: "",
    destination: "",
    currency: "INR",
    pickup_date: toLocalInput(addMin(close, 60 * 24 * 3)).slice(0, 10),
    bid_start_at: toLocalInput(start),
    bid_close_at: toLocalInput(close),
    forced_close_at: toLocalInput(addMin(close, 30)),
    is_british_auction: true,
    trigger_window_minutes: "10",
    extension_minutes: "5",
    trigger_type: "BID_RECEIVED" as TriggerType,
  };
}

type Form = ReturnType<typeof defaults>;

/** Same rules the API enforces (assignment §7) so users get instant feedback. */
function validate(f: Form): Partial<Record<keyof Form, string>> {
  const e: Partial<Record<keyof Form, string>> = {};
  if (f.name.trim().length < 3) e.name = "Give the RFQ a name (at least 3 characters)";
  if (f.reference_id && !/^[A-Za-z0-9._\-/]+$/.test(f.reference_id)) e.reference_id = "Letters, digits and . _ - / only";
  const start = new Date(f.bid_start_at).getTime();
  const close = new Date(f.bid_close_at).getTime();
  const forced = new Date(f.forced_close_at).getTime();
  if (!f.bid_start_at) e.bid_start_at = "Required";
  if (!f.bid_close_at) e.bid_close_at = "Required";
  else if (close <= Date.now()) e.bid_close_at = "Bid close time must be in the future";
  else if (close <= start) e.bid_close_at = "Must be later than the bid start time";
  if (!f.pickup_date) e.pickup_date = "Required";
  else if (f.bid_start_at && f.pickup_date < f.bid_start_at.slice(0, 10)) e.pickup_date = "Cannot be before the bid start date";

  if (f.is_british_auction) {
    if (!f.forced_close_at) e.forced_close_at = "Required for a British auction";
    else if (forced <= close) e.forced_close_at = "Forced close must be later than the bid close time";
    const x = Number(f.trigger_window_minutes);
    const y = Number(f.extension_minutes);
    if (!Number.isInteger(x) || x < 1 || x > 1440) e.trigger_window_minutes = "Whole minutes, 1-1440";
    if (!Number.isInteger(y) || y < 1 || y > 1440) e.extension_minutes = "Whole minutes, 1-1440";
  }
  return e;
}

export function CreateRfqPage() {
  const navigate = useNavigate();
  const [f, setF] = useState<Form>(defaults);
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const errors = useMemo(() => validate(f), [f]);
  const show = (k: keyof Form) => (touched ? errors[k] : undefined);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((prev) => ({ ...prev, [k]: v }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(errors).length) return;
    setSubmitting(true);
    setServerError(null);
    try {
      const british = f.is_british_auction;
      const rfq = await api.createRfq({
        name: f.name.trim(),
        reference_id: f.reference_id.trim() || undefined,
        description: f.description.trim() || undefined,
        origin: f.origin.trim() || undefined,
        destination: f.destination.trim() || undefined,
        currency: f.currency,
        pickup_date: f.pickup_date,
        bid_start_at: localInputToIso(f.bid_start_at),
        bid_close_at: localInputToIso(f.bid_close_at),
        forced_close_at: british ? localInputToIso(f.forced_close_at) : undefined,
        is_british_auction: british,
        trigger_window_minutes: british ? Number(f.trigger_window_minutes) : undefined,
        extension_minutes: british ? Number(f.extension_minutes) : undefined,
        trigger_type: british ? f.trigger_type : undefined,
      });
      navigate(`/rfqs/${rfq.id}`);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  // Preview of how the configuration plays out, using the example format from the brief.
  const preview = useMemo(() => {
    if (!f.is_british_auction || errors.bid_close_at || errors.forced_close_at) return null;
    const x = Number(f.trigger_window_minutes);
    const y = Number(f.extension_minutes);
    if (!(x > 0 && y > 0)) return null;
    const close = new Date(f.bid_close_at);
    const forced = new Date(f.forced_close_at);
    const headroom = (forced.getTime() - close.getTime()) / 60000;
    return {
      windowFrom: timeOnly(addMin(close, -x).toISOString()),
      windowTo: timeOnly(close.toISOString()),
      extendedTo: timeOnly(new Date(Math.min(addMin(close, y).getTime(), forced.getTime())).toISOString()),
      maxExtensions: Math.ceil(headroom / y),
      headroom,
    };
  }, [f, errors]);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Create RFQ</h1>
          <p className="sub">Set up the lane, the bidding schedule and how the auction should extend.</p>
        </div>
      </div>

      <form onSubmit={submit} noValidate className="form-grid">
        <div className="form-main">
          <Card title="RFQ details">
            <div className="grid-2">
              <Field label="RFQ name" error={show("name")} required>
                <input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Mumbai → Delhi | 20ft FTL" />
              </Field>
              <Field label="Reference ID" hint="Leave blank to auto-generate (RFQ-YYYY-NNNNN)" error={show("reference_id")}>
                <input value={f.reference_id} onChange={(e) => set("reference_id", e.target.value)} placeholder="Auto" />
              </Field>
              <Field label="Origin">
                <input value={f.origin} onChange={(e) => set("origin", e.target.value)} placeholder="Pickup location" />
              </Field>
              <Field label="Destination">
                <input value={f.destination} onChange={(e) => set("destination", e.target.value)} placeholder="Delivery location" />
              </Field>
              <Field label="Pickup / Service date" error={show("pickup_date")} required>
                <input type="date" value={f.pickup_date} onChange={(e) => set("pickup_date", e.target.value)} />
              </Field>
              <Field label="Currency">
                <select value={f.currency} onChange={(e) => set("currency", e.target.value)}>
                  {["INR", "USD", "EUR", "AED", "SGD"].map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
            </div>
            <Field label="Description">
              <textarea rows={3} value={f.description} onChange={(e) => set("description", e.target.value)}
                placeholder="Cargo, equipment, special handling…" />
            </Field>
          </Card>

          <Card title="Bidding schedule">
            <div className="grid-3">
              <Field label="Bid start" error={show("bid_start_at")} required>
                <input type="datetime-local" value={f.bid_start_at} onChange={(e) => set("bid_start_at", e.target.value)} />
              </Field>
              <Field label="Bid close" error={show("bid_close_at")} required>
                <input type="datetime-local" value={f.bid_close_at} onChange={(e) => set("bid_close_at", e.target.value)} />
              </Field>
              <Field label="Forced bid close" hint="Hard stop; extensions never pass it" error={show("forced_close_at")}
                required={f.is_british_auction}>
                <input type="datetime-local" value={f.forced_close_at} disabled={!f.is_british_auction}
                  onChange={(e) => set("forced_close_at", e.target.value)} />
              </Field>
            </div>
          </Card>

          <Card
            title="British Auction"
            actions={
              <label className="switch">
                <input type="checkbox" checked={f.is_british_auction}
                  onChange={(e) => set("is_british_auction", e.target.checked)} />
                <span className="slider" />
                <span>{f.is_british_auction ? "Enabled" : "Disabled"}</span>
              </label>
            }
          >
            {f.is_british_auction ? (
              <>
                <div className="grid-2">
                  <Field label="Trigger window (X minutes)" hint="How close to the end bidding activity is monitored"
                    error={show("trigger_window_minutes")} required>
                    <input type="number" min={1} max={1440} value={f.trigger_window_minutes}
                      onChange={(e) => set("trigger_window_minutes", e.target.value)} />
                  </Field>
                  <Field label="Extension duration (Y minutes)" hint="Time added each time the trigger fires"
                    error={show("extension_minutes")} required>
                    <input type="number" min={1} max={1440} value={f.extension_minutes}
                      onChange={(e) => set("extension_minutes", e.target.value)} />
                  </Field>
                </div>
                <div className="field">
                  <span className="label">Extension trigger <em>*</em></span>
                  <div className="choice-grid">
                    {(Object.keys(TRIGGER_INFO) as TriggerType[]).map((t) => (
                      <label key={t} className={`choice ${f.trigger_type === t ? "selected" : ""}`}>
                        <input type="radio" name="trigger" checked={f.trigger_type === t} onChange={() => set("trigger_type", t)} />
                        <strong>{TRIGGER_INFO[t].title}</strong>
                        <span>{TRIGGER_INFO[t].help}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <p className="muted">
                Standard RFQ: bidding closes exactly at the bid close time with no automatic extensions.
              </p>
            )}
          </Card>
        </div>

        <aside className="form-side">
          <Card title="How this auction will behave" className="sticky">
            {f.is_british_auction ? (
              preview ? (
                <ul className="explain">
                  <li>Activity is monitored between <strong>{preview.windowFrom}</strong> and <strong>{preview.windowTo}</strong>.</li>
                  <li>
                    If <strong>{TRIGGER_INFO[f.trigger_type].short.toLowerCase()}</strong> happens in that window, the close
                    time moves from <strong>{preview.windowTo}</strong> to <strong>{preview.extendedTo}</strong>; the window
                    moves with it.
                  </li>
                  <li>
                    The forced close leaves {preview.headroom} min of headroom: at most <strong>{preview.maxExtensions}</strong>{" "}
                    extension{preview.maxExtensions === 1 ? "" : "s"}
                    {preview.headroom % Number(f.extension_minutes) !== 0 && ", the last one shortened so it ends exactly at the forced close"}.
                    Bidding never continues past the forced close.
                  </li>
                </ul>
              ) : (
                <p className="muted">Fix the highlighted fields to see a preview.</p>
              )
            ) : (
              <p className="muted">No extensions. The auction closes at the bid close time.</p>
            )}
            {serverError && <ErrorBox message={serverError} />}
            {touched && Object.keys(errors).length > 0 && (
              <div className="alert alert-warn">Please fix {Object.keys(errors).length} field(s) before creating.</div>
            )}
            <div className="actions">
              <button type="button" className="btn btn-ghost" onClick={() => navigate(-1)}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={submitting}>
                {submitting ? "Creating…" : "Create RFQ"}
              </button>
            </div>
          </Card>
        </aside>
      </form>
    </>
  );
}

function Field({ label, hint, error, required, children }: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`field ${error ? "has-error" : ""}`}>
      <span className="label">
        {label} {required && <em>*</em>}
      </span>
      {children}
      {error ? <span className="error">{error}</span> : hint ? <span className="hint">{hint}</span> : null}
    </label>
  );
}
