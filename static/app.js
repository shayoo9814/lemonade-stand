const POLL_MS = 1000;
const USER_ID_HEADER = "X-User-Id";

const balanceEl = document.getElementById("balance");
const inventoryListEl = document.getElementById("inventory-list");
const menuListEl = document.getElementById("menu-list");
const playerLineEl = document.getElementById("player-line");
const phaseLineEl = document.getElementById("phase-line");
const dayStartEl = document.getElementById("day-start");
const buyRowsEl = document.getElementById("buy-rows");
const messageEl = document.getElementById("message");
const btnStart = document.getElementById("btn-start");
const btnContinue = document.getElementById("btn-continue");
const btnSetPrice = document.getElementById("btn-set-price");
const priceInput = document.getElementById("lemonade-price");

let pollTimer = null;
let catalog = [];
/** Set from GET /auth/me; sent on later requests as X-User-Id. */
let userId = null;

function unitFor(ingredientName) {
  const ing = catalog.find((item) => item.name === ingredientName);
  return ing ? ing.unit : "";
}

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

function phaseLabel(session) {
  if (!session) return "No game yet";
  const phase = session.phase.replaceAll("_", " ");
  if (session.phase === "running") {
    return `Day ${session.day} · Hour ${session.hour} · ${phase}`;
  }
  if (session.phase === "game_over") {
    return `Day ${session.day} · Game over`;
  }
  return `Day ${session.day} · ${phase}`;
}

function renderInventory(items) {
  if (!items.length) {
    inventoryListEl.innerHTML = "<li><span>Empty</span><span class='qty'>0</span></li>";
    return;
  }
  inventoryListEl.innerHTML = items
    .slice()
    .sort((a, b) => a.ingredient_name.localeCompare(b.ingredient_name))
    .map(
      (item) =>
        `<li><span>${item.ingredient_name}</span><span class="qty">${item.amount} ${item.unit}</span></li>`
    )
    .join("");
}

function renderMenu(items) {
  if (!items.length) {
    menuListEl.innerHTML = "<li class='menu-empty'>No drinks on the menu</li>";
    return;
  }
  menuListEl.innerHTML = items
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((drink) => {
      const recipe = Object.entries(drink.recipe)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([name, amount]) => {
          const unit = unitFor(name);
          const qty = unit ? `${amount} ${unit}` : String(amount);
          return `<li><span>${name}</span><span class="qty">${qty}</span></li>`;
        })
        .join("");
      return `
        <li class="menu-item">
          <div class="menu-item-header">
            <span class="menu-item-name">${drink.name}</span>
            <span class="menu-item-price">${money(drink.price)}</span>
          </div>
          <p class="menu-recipe-label">Per serving</p>
          <ul class="menu-recipe">${recipe}</ul>
        </li>`;
    })
    .join("");
}

function renderBuyRows(ingredients) {
  buyRowsEl.innerHTML = ingredients
    .map((ing) => {
      const unit = Number(ing.unit_price);
      return `
        <div class="buy-row" data-name="${ing.name}">
          <span>${ing.name} <small>($${unit.toFixed(2)}/${ing.unit})</small></span>
          <input type="number" min="0" step="1" value="0" aria-label="Buy ${ing.name}" />
          <button type="button" data-buy="${ing.name}">Buy</button>
        </div>`;
    })
    .join("");

  buyRowsEl.querySelectorAll("[data-buy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.getAttribute("data-buy");
      const row = buyRowsEl.querySelector(`[data-name="${name}"]`);
      const qty = Number(row.querySelector("input").value);
      if (!qty || qty <= 0) {
        showMessage("Enter a positive amount", true);
        return;
      }
      try {
        const ok = await api("/ingredients/buy", {
          method: "POST",
          body: JSON.stringify({
            ingredient_name: name,
            unit_count: String(qty),
          }),
        });
        if (!ok) {
          showMessage("Purchase failed (check balance or phase)", true);
          return;
        }
        showMessage(`Bought ${qty} ${name}`);
        row.querySelector("input").value = "0";
        await refresh();
      } catch (err) {
        showMessage(err.message, true);
      }
    });
  });
}

function renderPlayer(user) {
  playerLineEl.innerHTML = `${user.name}<span class="email">${user.email}</span>`;
}

async function refresh() {
  const [capital, inventory, session] = await Promise.all([
    api("/users/capital").catch(() => null),
    api("/inventory"),
    api("/game"),
  ]);

  balanceEl.textContent = capital ? money(capital.current_capital) : "—";
  renderInventory(inventory);
  phaseLineEl.textContent = phaseLabel(session);

  const atDayStart = session && session.phase === "day_start";
  dayStartEl.classList.toggle("hidden", !atDayStart);
  btnStart.textContent = session ? "Restart game" : "Start game";

  if (session && session.phase === "running") {
    startPolling();
  } else {
    stopPolling();
  }

  if (session && session.phase === "game_over") {
    showMessage("You're bankrupt — start a new game to try again.", true);
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    refresh().catch(() => {});
  }, POLL_MS);
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

btnStart.addEventListener("click", async () => {
  try {
    await api("/game/start", { method: "POST" });
    showMessage("Game started with $30. Buy supplies, then open.");
    await refresh();
  } catch (err) {
    showMessage(err.message, true);
  }
});

btnContinue.addEventListener("click", async () => {
  try {
    await api("/game/continue", { method: "POST" });
    showMessage("Stand is open — sales run each game hour.");
    await refresh();
  } catch (err) {
    showMessage(err.message, true);
  }
});

btnSetPrice.addEventListener("click", async () => {
  try {
    const ok = await api("/lemonades/price", {
      method: "POST",
      body: JSON.stringify({
        name: "classic",
        price: String(priceInput.value),
      }),
    });
    if (!ok) {
      showMessage("Could not set price", true);
      return;
    }
    showMessage(`Lemonade price set to ${money(priceInput.value)}`);
    renderMenu(await api("/lemonades"));
  } catch (err) {
    showMessage(err.message, true);
  }
});

async function init() {
  const me = await api("/auth/me");
  userId = me.id;
  renderPlayer(me);
  const [ingredients, menu] = await Promise.all([
    api("/ingredients"),
    api("/lemonades"),
  ]);
  catalog = ingredients;
  renderBuyRows(catalog);
  renderMenu(menu);
  await refresh();
}

init().catch((err) => showMessage(err.message, true));
