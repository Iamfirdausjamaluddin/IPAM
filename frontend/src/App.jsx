import { useState, useEffect } from "react";

// The FastAPI backend. (Same value you confirmed working earlier.)
const API_BASE = "/api";

// The /24 subnets we track, from the context doc (section 13): 11 through 15.
const SUBNETS = [11, 12, 13, 14, 15];

// Static map so Tailwind can see every class as a literal string (see 4.6.1).
const STATUS_STYLES = {
  free: "bg-green-500",
  in_use: "bg-blue-500",
  reserved: "bg-orange-500",
  rogue: "bg-red-500",
  system: "bg-gray-400",
};

const STATUS_LABELS = {
  free: "Free",
  in_use: "In use",
  reserved: "Reserved",
  rogue: "Rogue",
  system: "System",
};

const EMPTY_FORM = {
  hostname: "",
  vm_id: "",
  mac_address: "",
  reserved_by: "",
  note: "",
};

// Given a subnet's 256 cells, how many are free (assignable). "Used" is simply
// everything else, so used + free always = 256.
function countFree(cells) {
  return cells.filter((c) => c.status === "free").length;
}

export default function App() {
  const [activeSubnet, setActiveSubnet] = useState(15);

  // CHANGED in 4.6.6: instead of one subnet's cells, we now hold ALL subnets'
  // grids, keyed by subnet number -> { 11: [...256], 12: [...256], ... }.
  // That's what lets every tab show its own used/free count without clicking
  // in, and it makes switching tabs instant (the data is already here).
  const [grids, setGrids] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [selectedIp, setSelectedIp] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const [refreshKey, setRefreshKey] = useState(0);

  // Fetch ALL five subnet grids at once. Promise.all fires the five requests
  // in parallel and resolves when every one is done. Re-runs on refreshKey, so
  // one save updates every tab's count AND recolors the active grid together.
  // Note: this no longer depends on activeSubnet — switching tabs just reads
  // from data we already have, so it costs no request.
  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all(
      SUBNETS.map((subnet) =>
        fetch(`${API_BASE}/grid/${subnet}`).then((res) => {
          if (!res.ok) throw new Error(`Subnet ${subnet}: ${res.status}`);
          return res.json().then((cells) => [subnet, cells]);
        })
      )
    )
      .then((entries) => {
        // entries is [[11, [...]], [12, [...]], ...]; Object.fromEntries turns
        // that into { 11: [...], 12: [...], ... }.
        setGrids(Object.fromEntries(entries));
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [refreshKey]);

  // The active tab's cells, pulled from the grids we already loaded.
  const cells = grids[activeSubnet] ?? [];

  // Fetch the selected IP's reservation. 404 = unclaimed (not an error).
  useEffect(() => {
    if (selectedIp === null) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetail(null);
    fetch(`${API_BASE}/reservations/${selectedIp}`)
      .then((res) => {
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setDetail(data);
        setDetailLoading(false);
      })
      .catch(() => {
        setDetail(null);
        setDetailLoading(false);
      });
  }, [selectedIp, refreshKey]);

  // Keep the form in sync with what we're looking at.
  useEffect(() => {
    setSaveError(null);
    if (detail) {
      setForm({
        hostname: detail.hostname ?? "",
        vm_id: detail.vm_id ?? "",
        mac_address: detail.mac_address ?? "",
        reserved_by: detail.reserved_by ?? "",
        note: detail.note ?? "",
      });
    } else {
      setForm(EMPTY_FORM);
    }
  }, [detail, selectedIp]);

  const selectedStatus = cells.find((c) => c.ip === selectedIp)?.status;

  function updateField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    const fields = {
      hostname: form.hostname.trim() || null,
      vm_id: form.vm_id === "" ? null : Number(form.vm_id),
      mac_address: form.mac_address.trim() || null,
      reserved_by: form.reserved_by.trim() || null,
      note: form.note.trim() || null,
    };
    const isEdit = detail !== null;
    const url = isEdit
      ? `${API_BASE}/reservations/${selectedIp}`
      : `${API_BASE}/reservations`;
    const method = isEdit ? "PUT" : "POST";
    const body = isEdit ? fields : { ip: selectedIp, ...fields };
    try {
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error(errBody?.detail || `Backend returned ${res.status}`);
      }
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleRelease() {
    if (!window.confirm(`Release the reservation for ${selectedIp}?`)) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await fetch(`${API_BASE}/reservations/${selectedIp}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const inputClass =
    "w-full rounded border border-slate-300 px-2 py-1 text-sm " +
    "focus:border-blue-500 focus:outline-none";

  return (
    <div className="min-h-screen bg-slate-100 p-8">
      <h1 className="text-2xl font-bold text-slate-800">Homelab IPAM</h1>
      <p className="mb-6 text-slate-500">Subnet 10.10.{activeSubnet}.0/24</p>

      <div className="flex gap-6">
        <div className="flex-1">
          {/* Tab strip — each tab now shows its own used/free count. */}
          <div className="mb-6 flex gap-1 border-b border-slate-300">
            {SUBNETS.map((subnet) => {
              const isActive = subnet === activeSubnet;
              const subnetCells = grids[subnet] ?? [];
              const loaded = subnetCells.length > 0;
              const free = countFree(subnetCells);
              const used = subnetCells.length - free;
              return (
                <button
                  key={subnet}
                  onClick={() => setActiveSubnet(subnet)}
                  className={
                    "rounded-t-md px-4 py-2 text-left transition-colors " +
                    (isActive
                      ? "border-b-2 border-blue-500 bg-white"
                      : "hover:bg-white/50")
                  }
                >
                  <div
                    className={
                      "text-sm font-medium " +
                      (isActive ? "text-slate-800" : "text-slate-500")
                    }
                  >
                    10.10.{subnet}.x
                  </div>
                  <div className="text-xs text-slate-400">
                    {loaded ? `${used} used · ${free} free` : "…"}
                  </div>
                </button>
              );
            })}
          </div>

          {error && (
            <p className="text-red-600">Could not load grid: {error}</p>
          )}

          {/* Only show "Loading" on the very first load (no data yet). On a
              refresh we keep the existing grid visible, so it never flashes. */}
          {!error && cells.length === 0 && (
            <p className="text-slate-500">Loading grid…</p>
          )}

          {!error && cells.length > 0 && (
            <div
              className="grid max-w-3xl gap-1"
              style={{ gridTemplateColumns: "repeat(16, minmax(0, 1fr))" }}
            >
              {cells.map((cell) => {
                const lastOctet = cell.ip.split(".")[3];
                const colorClass = STATUS_STYLES[cell.status] ?? "bg-slate-200";
                const isSelected = cell.ip === selectedIp;
                return (
                  <button
                    key={cell.ip}
                    onClick={() => setSelectedIp(cell.ip)}
                    title={`${cell.ip} — ${cell.status}`}
                    className={
                      `${colorClass} flex aspect-square select-none items-center ` +
                      "justify-center rounded-sm text-[10px] text-white/90 " +
                      "transition-transform hover:scale-110 " +
                      (isSelected ? "ring-2 ring-slate-800 ring-offset-1" : "")
                    }
                  >
                    {lastOctet}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Side panel */}
        {selectedIp && (
          <aside className="w-80 shrink-0 rounded-lg bg-white p-5 shadow">
            <div className="mb-3 flex items-start justify-between">
              <h2 className="text-lg font-bold text-slate-800">{selectedIp}</h2>
              <button
                onClick={() => setSelectedIp(null)}
                className="text-slate-400 hover:text-slate-700"
                title="Close"
              >
                ✕
              </button>
            </div>

            {selectedStatus && (
              <span
                className={`${STATUS_STYLES[selectedStatus]} mb-4 inline-block rounded-full px-3 py-1 text-xs font-medium text-white`}
              >
                {STATUS_LABELS[selectedStatus] ?? selectedStatus}
              </span>
            )}

            {detailLoading ? (
              <p className="text-sm text-slate-500">Loading…</p>
            ) : selectedStatus === "system" ? (
              <p className="text-sm text-slate-500">
                System address (network / broadcast / gateway) — not assignable.
              </p>
            ) : (
              <>
                <h3 className="mb-3 text-sm font-semibold text-slate-700">
                  {detail ? "Edit reservation" : "Reserve this IP"}
                </h3>

                <div className="space-y-3">
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      Hostname
                    </label>
                    <input
                      className={inputClass}
                      value={form.hostname}
                      onChange={(e) => updateField("hostname", e.target.value)}
                      placeholder="e.g. svr2"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      VM ID
                    </label>
                    <input
                      type="number"
                      className={inputClass}
                      value={form.vm_id}
                      onChange={(e) => updateField("vm_id", e.target.value)}
                      placeholder="700–799"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      MAC address
                    </label>
                    <input
                      className={inputClass}
                      value={form.mac_address}
                      onChange={(e) => updateField("mac_address", e.target.value)}
                      placeholder="AA:BB:CC:DD:EE:FF"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      Reserved by
                    </label>
                    <input
                      className={inputClass}
                      value={form.reserved_by}
                      onChange={(e) => updateField("reserved_by", e.target.value)}
                      placeholder="your name"
                    />
                  </div>

                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      Note
                    </label>
                    <textarea
                      className={inputClass}
                      rows={2}
                      value={form.note}
                      onChange={(e) => updateField("note", e.target.value)}
                      placeholder="optional note"
                    />
                  </div>
                </div>

                {saveError && (
                  <p className="mt-3 text-sm text-red-600">{saveError}</p>
                )}

                <div className="mt-4 flex gap-2">
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="flex-1 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {saving ? "Saving…" : detail ? "Save changes" : "Reserve"}
                  </button>
                  {detail && (
                    <button
                      onClick={handleRelease}
                      disabled={saving}
                      className="rounded border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      Release
                    </button>
                  )}
                </div>

                {detail && (
                  <p className="mt-3 text-xs text-slate-400">
                    Reserved {new Date(detail.created_at).toLocaleString()} · updated{" "}
                    {new Date(detail.updated_at).toLocaleString()}
                  </p>
                )}
              </>
            )}
          </aside>
        )}
      </div>
    </div>
  );
}