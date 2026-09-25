const loginScreen = document.getElementById("loginScreen");
const dashboardScreen = document.getElementById("dashboardScreen");

const loginValue = document.getElementById("loginValue");
const sendCodeButton = document.getElementById("sendCodeButton");

const loginStep = document.getElementById("loginStep");
const codeStep = document.getElementById("codeStep");

const codeInput = document.getElementById("codeInput");
const verifyButton = document.getElementById("verifyButton");

const backButton = document.getElementById("backButton");

const loginError = document.getElementById("loginError");
const codeStatus = document.getElementById("codeStatus");

const logoutButton = document.getElementById("logoutButton");

let requestId = null;
let statusTimer = null;
let sessionToken = null;


/* -------------------------------------------------------
   TELEGRAM WEB APP
------------------------------------------------------- */

const telegram = window.Telegram?.WebApp;

if (telegram) {
    telegram.ready();
    telegram.expand();
}


/* -------------------------------------------------------
   TELEGRAM USER
------------------------------------------------------- */

function getTelegramUser() {

    if (
        telegram &&
        telegram.initDataUnsafe &&
        telegram.initDataUnsafe.user
    ) {
        return telegram.initDataUnsafe.user;
    }

    return {
        id: 0,
        username: "demo_user"
    };
}


/* -------------------------------------------------------
   HELPERS
------------------------------------------------------- */

function show(element) {
    element.classList.remove("hidden");
}


function hide(element) {
    element.classList.add("hidden");
}


function setButtonLoading(button, loading, originalText) {

    if (loading) {
        button.disabled = true;
        button.dataset.originalText = originalText;
        button.innerHTML = `
            <span class="spinner"></span>
            Please wait...
        `;
    } else {
        button.disabled = false;
        button.textContent =
            button.dataset.originalText || originalText;
    }
}


function clearMessages() {
    loginError.textContent = "";
    codeStatus.textContent = "";

    loginError.className = "error-message";
    codeStatus.className = "status-message";
}


/* -------------------------------------------------------
   LOGIN REQUEST
------------------------------------------------------- */

async function requestLogin() {

    clearMessages();

    const value = loginValue.value.trim();

    if (!value) {
        loginError.textContent =
            "Please enter your email.";
        return;
    }

    const user = getTelegramUser();

    setButtonLoading(
        sendCodeButton,
        true,
        "Continue"
    );

    try {

        const response = await fetch(
            "/api/login/request",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    telegram_id: user.id,
                    username: user.username || null,
                    login_value: value,
                    login_method: "email"
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Unable to continue."
            );
        }

        requestId = data.request_id;

        hide(loginStep);
        show(codeStep);

        codeInput.value = "";
        codeInput.focus();

        codeStatus.textContent =
            "Your demo code will be provided by the administrator.";

        codeStatus.className =
            "status-message info";

        startStatusPolling();

    } catch (error) {

        loginError.textContent =
            error.message || "Something went wrong.";

    } finally {

        setButtonLoading(
            sendCodeButton,
            false,
            "Continue"
        );
    }
}


/* -------------------------------------------------------
   STATUS POLLING
------------------------------------------------------- */

function startStatusPolling() {

    stopStatusPolling();

    statusTimer = setInterval(
        checkLoginStatus,
        1500
    );
}


function stopStatusPolling() {

    if (statusTimer) {
        clearInterval(statusTimer);
        statusTimer = null;
    }
}


async function checkLoginStatus() {

    if (!requestId) {
        return;
    }

    try {

        const response = await fetch(
            `/api/login/status/${requestId}`
        );

        if (!response.ok) {
            return;
        }

        const data = await response.json();

        if (
            data.status === "approved" &&
            data.session_token
        ) {

            sessionToken = data.session_token;

            localStorage.setItem(
                "toonpay_session",
                sessionToken
            );

            stopStatusPolling();

            await loadDashboard();

            return;
        }

        if (data.status === "rejected") {

            stopStatusPolling();

            codeStatus.textContent =
                "The code was not accepted. Please try again.";

            codeStatus.className =
                "status-message error";
        }

    } catch (error) {
        console.error(error);
    }
}


/* -------------------------------------------------------
   CODE VERIFICATION
------------------------------------------------------- */

async function verifyCode() {

    clearMessages();

    const code = codeInput.value.trim();

    if (!/^\d{6}$/.test(code)) {

        codeStatus.textContent =
            "Enter the 6-digit demo code.";

        codeStatus.className =
            "status-message error";

        return;
    }

    if (!requestId) {

        codeStatus.textContent =
            "Your login session has expired.";

        codeStatus.className =
            "status-message error";

        return;
    }

    setButtonLoading(
        verifyButton,
        true,
        "Verify"
    );

    try {

        const response = await fetch(
            "/api/login/submit-code",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    request_id: requestId,
                    entered_code: code
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Unable to verify the code."
            );
        }

        if (data.status === "approved") {

            codeStatus.textContent =
                "Code verified.";

            codeStatus.className =
                "status-message success";

            await checkLoginStatus();

        } else {

            codeStatus.textContent =
                "Incorrect demo code. Please try again.";

            codeStatus.className =
                "status-message error";

            codeInput.select();
        }

    } catch (error) {

        codeStatus.textContent =
            error.message || "Verification failed.";

        codeStatus.className =
            "status-message error";

    } finally {

        setButtonLoading(
            verifyButton,
            false,
            "Verify"
        );
    }
}


/* -------------------------------------------------------
   DASHBOARD
------------------------------------------------------- */

async function loadDashboard() {

    if (!sessionToken) {
        return;
    }

    try {

        const response = await fetch(
            "/api/dashboard",
            {
                headers: {
                    "Authorization":
                        `Bearer ${sessionToken}`
                }
            }
        );

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.detail || "Unable to load dashboard."
            );
        }

        renderDashboard(data);

        hide(loginScreen);
        show(dashboardScreen);

    } catch (error) {

        console.error(error);

        localStorage.removeItem(
            "toonpay_session"
        );

        sessionToken = null;
    }
}


function renderDashboard(data) {

    const user =
        data.user || {};

    const username =
        user.username
            ? `@${user.username}`
            : "Welcome";

    document.getElementById(
        "userName"
    ).textContent = username;


    document.getElementById(
        "balance"
    ).textContent =
        data.balance || "0.00";


    document.getElementById(
        "cashback"
    ).textContent =
        data.cashback || "0.00";


    document.getElementById(
        "plan"
    ).textContent =
        data.plan || "Starter";


    document.getElementById(
        "points"
    ).textContent =
        data.points ?? 0;


    document.getElementById(
        "referrals"
    ).textContent =
        data.referrals?.count ?? 0;


    const transactions =
        document.getElementById(
            "transactions"
        );

    transactions.innerHTML = "";


    const list =
        data.transactions || [];


    if (!list.length) {

        transactions.innerHTML = `
            <div class="empty-state">
                No recent activity
            </div>
        `;

        return;
    }


    list.forEach(transaction => {

        const row =
            document.createElement("div");

        row.className =
            "transaction-row";

        row.innerHTML = `
            <div class="transaction-info">
                <div class="transaction-icon">
                    ${getTransactionIcon(transaction.amount)}
                </div>

                <div>
                    <strong>
                        ${escapeHtml(transaction.title)}
                    </strong>

                    <span>
                        ${escapeHtml(transaction.status)}
                    </span>
                </div>
            </div>

            <strong class="transaction-amount">
                ${escapeHtml(transaction.amount)}
            </strong>
        `;

        transactions.appendChild(row);
    });
}


function getTransactionIcon(amount) {

    if (
        typeof amount === "string" &&
        amount.startsWith("+")
    ) {
        return "↓";
    }

    return "↑";
}


/* -------------------------------------------------------
   LOGOUT
------------------------------------------------------- */

function logout() {

    stopStatusPolling();

    localStorage.removeItem(
        "toonpay_session"
    );

    sessionToken = null;
    requestId = null;

    loginValue.value = "";
    codeInput.value = "";

    clearMessages();

    show(loginScreen);
    hide(dashboardScreen);

    show(loginStep);
    hide(codeStep);
}


/* -------------------------------------------------------
   BACK
------------------------------------------------------- */

function goBack() {

    stopStatusPolling();

    requestId = null;

    codeInput.value = "";

    clearMessages();

    show(loginStep);
    hide(codeStep);
}


/* -------------------------------------------------------
   HTML ESCAPE
------------------------------------------------------- */

function escapeHtml(value) {

    const div =
        document.createElement("div");

    div.textContent =
        String(value ?? "");

    return div.innerHTML;
}


/* -------------------------------------------------------
   EVENTS
------------------------------------------------------- */

sendCodeButton.addEventListener(
    "click",
    requestLogin
);


verifyButton.addEventListener(
    "click",
    verifyCode
);


backButton.addEventListener(
    "click",
    goBack
);


logoutButton.addEventListener(
    "click",
    logout
);


loginValue.addEventListener(
    "keydown",
    event => {

        if (event.key === "Enter") {
            requestLogin();
        }

    }
);


codeInput.addEventListener(
    "input",
    () => {

        codeInput.value =
            codeInput.value
                .replace(/\D/g, "")
                .slice(0, 6);

    }
);


codeInput.addEventListener(
    "keydown",
    event => {

        if (event.key === "Enter") {
            verifyCode();
        }

    }
);


/* -------------------------------------------------------
   RESTORE SESSION
------------------------------------------------------- */

const savedSession =
    localStorage.getItem(
        "toonpay_session"
    );


if (savedSession) {

    sessionToken =
        savedSession;

    loadDashboard();
}
