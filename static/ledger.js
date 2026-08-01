const USER_ID_HEADER = "X-User-Id";

const balanceEl = document.getElementById("balance");
const verifyLineEl = document.getElementById("verify-line");
const playerLineEl = document.getElementById("player-line");
const ledgerBodyEl = document.getElementById("ledger-body");
const messageEl = document.getElementById("message");
const btnClearLedger = document.getElementById("btn-clear-ledger");

/** Set from GET /auth/me; sent on later requests as X-User-Id. */
let userId = null;

function money(value) {
  const n = Number(value);
  return Number.isFinite(n)
    ? n.toLocaleString(undefined, { style: "currency", currency: "USD" })
    : "—";
}

function showMessage(text, isError = false) {
  messageEl.hidden = !text;
  messageEl.textContent = text || "";
  messageEl.classList.toggle("error", Boolean(isError));
}

function formatApiDetail(detail) {
  if (detail == null || detail === "") return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "string" ? item : item.msg || JSON.stringify(item)
      )
      .join("; ");
  }
  if (typeof detail === "object" && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(userId ? { [USER_ID_HEADER]: userId } : {}),
    ...(options.headers || {}),
  };
  const res = await fetch(path, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(formatApiDetail(body.detail) || res.statusText);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

function actionLabel(action) {
  return String(action || "").replaceAll("_", " ");
}

function formatWhen(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

function amountClass(action) {
  if (action === "purchase" || action === "reset-ledger") return "outflow";
  if (action === "sale" || action === "opening_balance") return "inflow";
  return "";
}

function signedAmount(entry) {
  const value = money(entry.amount);
  if (entry.action === "purchase" || entry.action === "reset-ledger") {
    return `−${value}`;
  }
  if (entry.action === "sale" || entry.action === "opening_balance") {
    const n = Number(entry.amount);
    if (n < 0) return money(entry.amount);
    return `+${value}`;
  }
  return value;
}

function renderEntries(entries) {
  if (!entries.length) {
    ledgerBodyEl.innerHTML =
      '<tr><td colspan="6" class="empty">No entries yet</td></tr>';
    return;
  }

  const rows = entries.map((entry, index) => {
    const isLatest = index === entries.length - 1;
    const item = entry.item_id || "—";
    return `
      <tr class="${isLatest ? "latest" : ""}">
        <td>${formatWhen(entry.timestamp)}</td>
        <td>${actionLabel(entry.action)}</td>
        <td class="item-id">${item}</td>
        <td class="num ${amountClass(entry.action)}">${signedAmount(entry)}</td>
        <td class="num">${money(entry.current_capital)}</td>
        <td class="num">${money(entry.expenses_incurred)}</td>
      </tr>`;
  });

  ledgerBodyEl.innerHTML = rows.join("");
}

function renderPlayer(user) {
  playerLineEl.innerHTML = `${user.name}<span class="email">${user.email}</span>`;
}

async function refresh() {
  const [capital, entries] = await Promise.all([
    api("/users/capital").catch(() => null),
    api("/users/ledger"),
  ]);

  const latest = entries.length ? entries[entries.length - 1] : null;
  const ledgerBalance = latest ? latest.current_capital : null;
  balanceEl.textContent = money(ledgerBalance);
  renderEntries(entries);

  if (ledgerBalance != null && capital != null) {
    const match = Number(ledgerBalance) === Number(capital.current_capital);
    verifyLineEl.hidden = false;
    verifyLineEl.textContent = match
      ? `Matches stand balance (${money(capital.current_capital)})`
      : `Does not match stand balance (${money(capital.current_capital)})`;
    verifyLineEl.classList.toggle("mismatch", !match);
  } else {
    verifyLineEl.hidden = true;
  }
}

async function init() {
  const me = await api("/auth/me");
  userId = me.id;
  renderPlayer(me);
  await refresh();
}

btnClearLedger.addEventListener("click", async () => {
  const ok = window.confirm(
    "Clear the entire ledger history for this player? This cannot be undone."
  );
  if (!ok) return;
  try {
    await api("/users/ledger", { method: "DELETE" });
    showMessage("Ledger cleared.");
    await refresh();
  } catch (err) {
    showMessage(err.message, true);
  }
});

init().catch((err) => showMessage(err.message, true));
