const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand();
}


const app = document.getElementById("app");

const u =
  tg?.initDataUnsafe?.user || {};


const telegramId =
  u.id || 999000001;


const username =
  u.username || "demo_user";


let requestId = null;

let pollTimer = null;

let sessionToken =
  localStorage.getItem(
    "toonpay_demo_session"
  );


const esc = v =>
  String(v).replace(
    /[&<>"']/g,
    c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[c])
  );


const render = html => {
  app.innerHTML = html;
};


const logo = () =>
  `<img
    class="brand-logo"
    src="/toonpay-logo.jpg"
    alt="ToonPay"
  >`;


function showLogin() {

  clearInterval(pollTimer);

  render(`
    <div class="screen">

      <div class="topbar">

        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <div class="demo-pill">
          DEMO
        </div>

      </div>

      <div class="auth-wrap">

        <div class="auth-title">
          Welcome back
        </div>

        <div class="auth-subtitle">
          Enter your email address to continue with the demo.
        </div>

        <div class="input-wrap">

          <input
            id="emailInput"
            class="input"
            type="email"
            autocomplete="off"
            placeholder="name@example.com"
          >

        </div>

        <button
          class="primary-button"
          onclick="startLogin()"
        >
          Continue
        </button>

        <div class="secure-note">
          <span>●</span>
          Demo verification • no real account access
        </div>

      </div>

    </div>
  `);
}


async function startLogin() {

  const input =
    document.getElementById(
      "emailInput"
    );

  const value =
    input.value.trim();


  if (!value) {

    return toast(
      "Enter an email address."
    );

  }


  try {

    const r = await fetch(
      "/api/login/request",
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body: JSON.stringify({
          telegram_id: telegramId,
          username: username,
          login_value: value,
          login_method: "email"
        })
      }
    );


    const d = await r.json();


    if (!r.ok) {

      return toast(
        d.detail ||
        "Unable to continue."
      );

    }


    requestId =
      d.request_id;


    showOtp(value);


  } catch (e) {

    toast(
      "Connection error. Please try again."
    );

  }
}


function showOtp(email) {

  render(`
    <div class="screen">

      <div class="topbar">

        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <div class="demo-pill">
          DEMO
        </div>

      </div>

      <div class="auth-wrap otp-wrap">

        <div class="code-icon">
          ✓
        </div>

        <div class="auth-title">
          Enter your code
        </div>

        <div class="auth-subtitle">

          A demo verification code was
          generated for

          <strong>
            ${esc(email)}
          </strong>.

          Ask the demo administrator
          for the code.

        </div>

        <input
          id="otpInput"
          class="otp-box"
          inputmode="numeric"
          maxlength="6"
          autocomplete="one-time-code"
          placeholder="000000"
        >

        <button
          class="primary-button"
          onclick="submitOtp()"
        >
          Verify
        </button>

        <button
          class="secondary-button"
          onclick="showLogin()"
        >
          Use another email
        </button>

        <div
          id="otpStatus"
          class="waiting"
        >
          Waiting for your demo code...
        </div>

      </div>

    </div>
  `);


  document
    .getElementById("otpInput")
    .addEventListener(
      "input",
      function () {

        this.value =
          this.value
            .replace(/\D/g, "")
            .slice(0, 6);

      }
    );


  pollTimer =
    setInterval(
      checkStatus,
      1500
    );
}


async function submitOtp() {

  const code =
    document
      .getElementById("otpInput")
      .value;


  if (!/^\d{6}$/.test(code)) {

    return otpMsg(
      "Enter the 6-digit demo code.",
      "error"
    );

  }


  try {

    const r = await fetch(
      "/api/login/submit-code",
      {
        method: "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body: JSON.stringify({
          request_id: requestId,
          entered_code: code
        })
      }
    );


    const d =
      await r.json();


    if (!r.ok) {

      return otpMsg(
        d.detail ||
        "Unable to verify.",
        "error"
      );

    }


    if (
      d.status === "rejected"
    ) {

      return otpMsg(
        "That demo code is not correct.",
        "error"
      );

    }


    otpMsg(
      "Code accepted. Waiting for administrator approval...",
      "success"
    );


  } catch (e) {

    otpMsg(
      "Connection error.",
      "error"
    );

  }
}


async function checkStatus() {

  if (!requestId) {
    return;
  }


  try {

    const r =
      await fetch(
        `/api/login/status/${requestId}`
      );


    const d =
      await r.json();


    if (
      d.status === "approved"
    ) {

      clearInterval(
        pollTimer
      );


      sessionToken =
        d.session_token;


      localStorage.setItem(
        "toonpay_demo_session",
        sessionToken
      );


      success();


    } else if (
      d.status === "rejected"
    ) {

      clearInterval(
        pollTimer
      );


      otpMsg(
        "Demo verification was rejected. Please try again.",
        "error"
      );

    }


  } catch (e) {}

}


function otpMsg(
  message,
  type
) {

  const x =
    document.getElementById(
      "otpStatus"
    );


  if (x) {

    x.innerHTML =
      `<span class="${type}">
        ${esc(message)}
      </span>`;

  }
}


function success() {

  render(`
    <div class="screen center">

      <div>

        <img
          class="success-logo"
          src="/toonpay-logo.jpg"
          alt="ToonPay"
        >

        <div
          class="auth-title success-title"
        >
          Welcome back
        </div>

        <div class="auth-subtitle">

          Verification approved.

          <br>

          Opening your dashboard...

        </div>

      </div>

    </div>
  `);


  setTimeout(
    loadDashboard,
    800
  );
}


function toast(message) {

  const x =
    document.createElement(
      "div"
    );


  x.textContent =
    message;


  Object.assign(
    x.style,
    {
      position: "fixed",
      left: "18px",
      right: "18px",
      bottom: "105px",
      padding: "15px 17px",
      background: "#1b1b1e",
      border: "1px solid #333338",
      borderRadius: "18px",
      color: "#fff",
      textAlign: "center",
      zIndex: 9999,
      boxShadow:
        "0 14px 40px #000b"
    }
  );


  document.body.appendChild(x);


  setTimeout(
    () => x.remove(),
    2600
  );
}


async function loadDashboard() {

  if (!sessionToken) {

    return showLogin();

  }


  try {

    const r =
      await fetch(
        "/api/dashboard",
        {
          headers: {
            Authorization:
              "Bearer " +
              sessionToken
          }
        }
      );


    if (!r.ok) {

      localStorage.removeItem(
        "toonpay_demo_session"
      );

      sessionToken = null;

      return showLogin();

    }


    renderHome(
      await r.json()
    );


  } catch (e) {

    toast(
      "Unable to load dashboard."
    );

  }
}


function nav(active) {

  return `
    <div class="bottom-nav">

      ${
        [
          [
            "⌂",
            "Home",
            "home",
            "loadDashboard()"
          ],
          [
            "◇",
            "Plans",
            "plans",
            "simple('Plans')"
          ],
          [
            "♣",
            "Referrals",
            "referrals",
            "simple('Referrals')"
          ],
          [
            "⚙",
            "Settings",
            "settings",
            "simple('Settings')"
          ]
        ]
        .map(
          x =>
            `
            <div
              class="nav-item ${
                active === x[2]
                  ? "active"
                  : ""
              }"
              onclick="${x[3]}"
            >

              <div class="nav-icon">
                ${x[0]}
              </div>

              ${x[1]}

            </div>
            `
        )
        .join("")
      }

    </div>
  `;
}


function renderHome(d) {

  render(`
    <div class="screen">

      <div class="topbar">

        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <div class="icon-button">
          🔔
        </div>

      </div>


      <div class="dashboard-hero">

        <div class="eyebrow">
          AVAILABLE BALANCE
        </div>

        <div class="balance-value">
          $${esc(d.balance)}
        </div>

        <div class="currency-chip">
          USD
        </div>

      </div>


      <div class="action-grid">

        <div
          class="action-card"
          onclick="simple('Receive')"
        >

          <div class="action-icon">
            ↓
          </div>

          <span>
            Receive
          </span>

        </div>


        <div
          class="action-card"
          onclick="simple('Details')"
        >

          <div class="action-icon">
            ▣
          </div>

          <span>
            Details
          </span>

        </div>


        <div
          class="action-card"
          onclick="simple('Send')"
        >

          <div class="action-icon">
            ➤
          </div>

          <span>
            Send
          </span>

        </div>

      </div>


      <div class="dashboard-card">

        <div class="card-head">

          <div class="card-title">
            Cashback Balance
          </div>

          <div class="mini-icon">
            🎁
          </div>

        </div>


        <div class="progress">

          <div
            class="progress-fill"
            style="width:${d.points}%"
          ></div>

        </div>


        <div class="points-row">

          <span>
            Points earned
          </span>

          <strong>
            ${d.points}/${d.points_target}
          </strong>

        </div>

      </div>


      <div class="dashboard-card">

        <div class="card-head">

          <div>

            <div class="muted small">
              CURRENT PLAN
            </div>

            <div class="plan-name">
              ${esc(d.plan)}
            </div>

          </div>


          <div class="muted small right">

            Expires

            <br>

            <strong>
              ${esc(d.plan_expiry)}
            </strong>

          </div>

        </div>


        <div class="manage">
          Manage plan
          <span>→</span>
        </div>

      </div>


      <div class="dashboard-card">

        <div class="card-title">
          Recent activity
        </div>


        ${
          d.transactions
            .map(
              t =>
                `
                <div class="transaction">

                  <div class="transaction-left">

                    <div class="transaction-icon">
                      ${
                        t.amount.startsWith("+")
                          ? "↓"
                          : "↑"
                      }
                    </div>

                    <div>

                      <div>
                        ${esc(t.title)}
                      </div>

                      <div class="transaction-status">
                        ${esc(t.status)}
                      </div>

                    </div>

                  </div>


                  <div
                    class="amount ${
                      t.amount.startsWith("+")
                        ? "green"
                        : ""
                    }"
                  >
                    ${esc(t.amount)}
                  </div>

                </div>
                `
            )
            .join("")
        }

      </div>


      <div class="demo-footer">
        Demo dashboard • simulated data only
      </div>


      ${nav("home")}

    </div>
  `);
}


function simple(title) {

  render(`
    <div class="screen">

      <div class="topbar">

        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <button
          class="icon-button"
          onclick="loadDashboard()"
        >
          ←
        </button>

      </div>


      <div class="page-title">
        ${esc(title)}
      </div>


      <div class="list-card">

        <div class="list-row">

          <span class="muted">
            Environment
          </span>

          <strong>
            Demo
          </strong>

        </div>


        <div class="list-row">

          <span class="muted">
            Account
          </span>

          <strong>
            @${esc(username)}
          </strong>

        </div>


        <div class="list-row">

          <span class="muted">
            Status
          </span>

          <strong class="green">
            Active
          </strong>

        </div>

      </div>


      ${
        title === "Settings"
          ? `
            <button
              class="primary-button"
              onclick="logout()"
            >
              Log out
            </button>
          `
          : ""
      }


      <div class="demo-footer">
        Demo environment • simulated data only
      </div>


      ${nav(title.toLowerCase())}

    </div>
  `);
}


function logout() {

  sessionToken = null;

  localStorage.removeItem(
    "toonpay_demo_session"
  );

  showLogin();
}


if (sessionToken) {

  loadDashboard();

} else {

  showLogin();

}
